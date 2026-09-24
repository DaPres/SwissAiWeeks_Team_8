"""Pre-analysis of the ticket history before it becomes knowledge.

Levels: gold = root cause documented · silver = closed with a short outcome (good for routing, thin on "how")
        bronze = closed without detail · reject = open, generic bucket or no usable signal.

1. Score every ticket (0-100) on how much it can teach: resolution evidence, closure, routing validity,
   input clarity and triage trail. Flags explain the deductions (bad data is labelled, not silently dropped).
2. Cluster tickets into problem classes per service, on a resolution-weighted embedding
   (training descriptions are templates; the resolution is what distinguishes one problem class from another).
3. Score each cluster (mean ticket quality + coherence of its resolutions) and assign a level.
4. Publish: every cluster at or above the chosen level becomes one `training` knowledge item.
"""
import collections
import json
import logging
import re
import time
from functools import lru_cache

import numpy as np

from . import catalog
from .config import settings
from .llm import get_llm
from .store import Store

log = logging.getLogger(__name__)

LEVELS = ["gold", "silver", "bronze", "reject"]
LEVEL_MIN_SCORE = {"gold": 80, "silver": 60, "bronze": 40, "reject": 0}

BOILERPLATE = re.compile(r"^(Initial triage assigned|We validated the issue|Impact assessment confirmed|Follow-up review completed)")
UNCLEAR_FAMILIES = re.compile(r"^(Unclear incident input|General request for .* with unclear details|External email warning|Email notification received)")

FLAG_LABELS = {
    "no_resolution_detail": "No resolution recorded",
    "problem_fixed_only": "Only 'Problem fixed.'",
    "canned_resolution": "Canned one-liner resolution",
    "not_closed": "Not closed (open / in progress)",
    "generic_bucket": "Generic 'Emailed Support Tickets' bucket",
    "unclear_input": "Unclear / generic input",
    "label_conflict": "Fix documented but label says cancelled / cannot reproduce",
}


def level_for(score: float) -> str:
    return next(lvl for lvl in LEVELS if score >= LEVEL_MIN_SCORE[lvl])


def levels_at_or_above(min_level: str) -> list[str]:
    return LEVELS[: LEVELS.index(min_level) + 1]


@lru_cache(maxsize=1)
def training_tickets() -> list[dict]:
    return json.load(open(settings.training_file))


def _split(comment: str) -> tuple[str, str]:
    author, _, body = comment.partition(": ")
    return author, body


def score_ticket(t: dict) -> dict:
    comments = [_split(c) for c in t["All Comments"]]
    rich = next(((a, b) for a, b in comments if b.startswith("Resolution: ")), None)
    canned = next(((a, b) for a, b in comments if b.startswith("Resolution recorded:")), None)
    fixed_only = any(b == "Problem fixed." for _, b in comments)
    service = t["Affected Business or IT Services"][0] if t["Affected Business or IT Services"] else catalog.GENERIC_BUCKET
    closed = t["Status"] == "done" and t["Resolution"] is not None
    flags: list[str] = []

    if rich:
        kind, evidence = "rich", 50
    elif canned:
        kind, evidence = "canned", 25
        flags.append("canned_resolution")
    elif fixed_only:
        kind, evidence = "fixed_only", 5
        flags.append("problem_fixed_only")
    else:
        kind, evidence = "none", 0
        flags.append("no_resolution_detail")

    closure = 15 if closed else 5 if t["Status"] == "done" else 0
    if not closed:
        flags.append("not_closed")
    routing = 15 if service in catalog.SERVICES else 0
    if not routing:
        flags.append("generic_bucket")
    clarity = 2 if UNCLEAR_FAMILIES.match(t["Summary"]) else 10
    if clarity < 10:
        flags.append("unclear_input")
    trail = min(sum(1 for _, b in comments if BOILERPLATE.match(b)), 5) + (5 if rich else 0)
    penalty = 5 if rich and t["Resolution"] in ("cancelled", "cannot reproduce") else 0
    if penalty:
        flags.append("label_conflict")

    score = max(0, evidence + closure + routing + clarity + trail - penalty)
    if not routing:
        score = min(score, LEVEL_MIN_SCORE["bronze"] - 5)  # unroutable: can never teach where a problem belongs
    resolution = rich or canned or (None, "Problem fixed." if fixed_only else "")
    return {
        "service": service,
        "score": score,
        "components": {"evidence": evidence, "closure": closure, "routing": routing, "clarity": clarity, "trail": trail, "penalty": -penalty},
        "flags": flags,
        "kind": kind,
        "resolver": rich[0] if rich else None,
        "resolution": re.sub(r"^Resolution( recorded)?: ", "", resolution[1]),
        "problem": "\n".join([t["Summary"], t["Description"]]),
    }


def _cluster(vectors: np.ndarray, weights: list[int], threshold: float) -> list[int]:
    """Greedy leader clustering, heaviest signatures first. Deterministic and fast at this scale."""
    order = np.argsort(-np.array(weights))
    centroids: list[np.ndarray] = []
    assign = [-1] * len(weights)
    for i in order:
        v = vectors[i]
        if centroids:
            sims = np.array([c @ v / (np.linalg.norm(c) or 1) for c in centroids])
            j = int(sims.argmax())
            if sims[j] >= threshold:
                assign[i] = j
                centroids[j] = centroids[j] + v * weights[i]
                continue
        assign[i] = len(centroids)
        centroids.append(v * weights[i])
    return assign


def run_curation(store: Store, threshold: float | None = None) -> dict:
    llm = get_llm()
    threshold = threshold if threshold is not None else (0.6 if llm.embedding_model.startswith("mock:") else 0.86)
    t0 = time.time()
    tickets = training_tickets()
    scored = [score_ticket(t) for t in tickets]

    # Unique signatures -> one embedding each (≈1k instead of 20k).
    sig_index: dict[tuple, int] = {}
    sig_members: list[list[int]] = []
    for idx, s in enumerate(scored):
        key = (s["service"], s["problem"], s["resolution"])
        if key not in sig_index:
            sig_index[key] = len(sig_members)
            sig_members.append([])
        sig_members[sig_index[key]].append(idx)
    sigs = list(sig_index)

    problems = sorted({k[1] for k in sigs})
    resolutions = sorted({k[2] for k in sigs if k[2]})
    pv = dict(zip(problems, llm.embed(problems)))
    rv = dict(zip(resolutions, llm.embed(resolutions))) if resolutions else {}

    def sig_vector(key: tuple) -> np.ndarray:
        v = pv[key[1]] * 0.35 + (rv[key[2]] * 0.65 if key[2] in rv else 0)
        return v / (np.linalg.norm(v) or 1)

    clusters = []
    by_service = collections.defaultdict(list)
    for si, key in enumerate(sigs):
        by_service[key[0]].append(si)
    for service, sis in by_service.items():
        vecs = np.vstack([sig_vector(sigs[si]) for si in sis])
        assign = _cluster(vecs, [len(sig_members[si]) for si in sis], threshold)
        groups = collections.defaultdict(list)
        for si, a in zip(sis, assign):
            groups[a].extend(sig_members[si])
        for members in groups.values():
            clusters.append(_summarise_cluster(service, members, scored))

    clusters.sort(key=lambda c: (-c["score"], -c["size"]))
    for i, c in enumerate(clusters, 1):
        c["id"] = i
    ticket_rows = []
    for c in clusters:
        for idx in c.pop("members"):
            ticket_rows.append((idx, c["id"], scored[idx]["score"], level_for(scored[idx]["score"]), json.dumps(scored[idx]["flags"])))

    summary = _summarise_run(scored, clusters, threshold, time.time() - t0)
    store.save_curation(summary, clusters, ticket_rows)
    log.info("curation: %d tickets -> %d clusters in %.1fs", len(tickets), len(clusters), summary["seconds"])
    return summary


def _summarise_cluster(service: str, members: list[int], scored: list[dict]) -> dict:
    items = [scored[i] for i in members]
    resolutions = collections.Counter(s["resolution"] for s in items if s["resolution"])
    kinds = collections.Counter(s["kind"] for s in items)
    top_resolution, top_count = resolutions.most_common(1)[0] if resolutions else (None, 0)
    top_kind = next(s["kind"] for s in items if s["resolution"] == top_resolution) if top_resolution else "none"
    resolvers = collections.Counter(s["resolver"] for s in items if s["resolver"] and s["resolution"] == top_resolution)
    problems = collections.Counter(s["problem"] for s in items)
    flags = collections.Counter(f for s in items for f in s["flags"])
    mean = float(np.mean([s["score"] for s in items]))
    coherence = top_count / len(items)  # share of tickets agreeing on the representative resolution
    # Coherent clusters (tickets agree on one fix) are more trustworthy; a documented root cause counts double.
    score = round(0.9 * mean + 10 * coherence * (1 if top_kind == "rich" else 0.5), 1)
    components = {k: round(float(np.mean([s["components"][k] for s in items])), 1) for k in items[0]["components"]}
    title = (re.split(r"(?<=[.;])\s", top_resolution)[0].rstrip(".;") if top_kind == "rich" else problems.most_common(1)[0][0].split("\n")[0])
    return {
        "service": service,
        "team": catalog.team_for(service) if service in catalog.SERVICES else "Service Desk",
        "size": len(items),
        "score": score,
        "level": level_for(score),
        "meanTicketScore": round(mean, 1),
        "coherence": round(coherence, 3),
        "resolutionKind": top_kind,
        "kinds": dict(kinds),
        "title": title,
        "problem": problems.most_common(1)[0][0],
        "problemVariants": len(problems),
        "resolution": top_resolution,
        "resolver": resolvers.most_common(1)[0][0] if resolvers else None,
        "flags": dict(flags),
        "components": components,
        "members": members,
    }


def _summarise_run(scored: list[dict], clusters: list[dict], threshold: float, seconds: float) -> dict:
    ticket_levels = collections.Counter(level_for(s["score"]) for s in scored)
    hist = collections.Counter(min(int(s["score"] // 10) * 10, 90) for s in scored)
    flags = collections.Counter(f for s in scored for f in s["flags"])
    by_level = {lvl: {"clusters": 0, "tickets": 0} for lvl in LEVELS}
    for c in clusters:
        by_level[c["level"]]["clusters"] += 1
        by_level[c["level"]]["tickets"] += c["size"]
    return {
        "createdAt": time.time(),
        "embeddingModel": get_llm().embedding_model,
        "threshold": threshold,
        "seconds": round(seconds, 1),
        "tickets": len(scored),
        "clusters": len(clusters),
        "ticketLevels": {lvl: ticket_levels.get(lvl, 0) for lvl in LEVELS},
        "clusterLevels": by_level,
        "scoreHistogram": [{"bucket": b, "count": hist.get(b, 0)} for b in range(0, 100, 10)],
        "flags": [{"flag": f, "label": FLAG_LABELS[f], "count": n} for f, n in flags.most_common()],
        "levelThresholds": LEVEL_MIN_SCORE,
    }


def publish(store: Store, min_level: str) -> dict:
    """Replace the history-derived knowledge with clusters at or above `min_level`."""
    clusters = [c for c in store.curation_clusters() if c["level"] in levels_at_or_above(min_level)
                and c["service"] in catalog.SERVICES and c["resolution"]]
    items = [
        {
            "id": f"cluster-{c['id']}",
            "source": "training",
            "service": c["service"],
            "team": c["team"],
            "resolver": c["resolver"],
            "title": c["title"],
            "problem": c["problem"],
            "resolution": c["resolution"],
            "occurrences": c["size"],
            "quality": c["score"],
            "level": c["level"],
        }
        for c in clusters
    ]
    from .knowledge import embedding_text  # local import: knowledge imports this module

    store.delete_knowledge_source("training")
    if items:
        store.add_knowledge(items, get_llm().embed([embedding_text(i) for i in items]))
    store.set_meta("knowledge_min_level", min_level)
    return {"minLevel": min_level, "published": len(items), "tickets": sum(c["size"] for c in clusters), "knowledge": store.knowledge_stats()}
