"""Evaluation harness (Sec. 10): stress set + pattern-level holdout, honest numbers, written to eval/results.json + RESULTS.md.

  python -m triagemate.cli eval              # uses the LLM if configured, else the deterministic engine
  python -m triagemate.cli eval --offline    # force the deterministic engine

Metrics (Sec. 10.2): routing accuracy, work-type accuracy on the misleading subset, clarification F1 (recall-weighted F2),
priority consistency over N repeated runs, citation coverage, injection resistance (+ false-positive rate),
PII redaction recall, duplicate linking, latency p50/p95, cost per ticket.
"""
from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from triagemate.analyze import baselines
from triagemate.catalogue import CRITICALITY, TEAM_OF, UNKNOWN, team_for
from triagemate.config import ROOT, get_settings
from triagemate.data import load_training, ticket_from_record
from triagemate.draft import detect_language
from triagemate.llm import get_client
from triagemate.models import Ticket
from triagemate.pipeline import Triage
from triagemate.priority import is_consistent
from triagemate.retrieve import get_retriever
from triagemate.safety import analyse_ticket, names_from_emails

EVAL_DIR = Path(__file__).resolve().parent


def _pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p * len(xs)))], 1) if xs else None


def _prf(tp, fp, fn, beta=1.0):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    b2 = beta * beta
    f = (1 + b2) * p * r / (b2 * p + r) if (b2 * p + r) else 0.0
    return round(p, 3), round(r, 3), round(f, 3)


def _mk(row: dict) -> Ticket:
    t = ticket_from_record(row["ticket"], 0, "S", "jira")
    return t.model_copy(update={"id": row["id"]})


def gold_teams(gold: dict) -> set[str]:
    return {team_for(s) if s != UNKNOWN else team_for("Emailed Support Tickets") for s in gold["service_any"]}


def run_stress(tri: Triage, runs: int, fname: str = "stress_set.json") -> dict:
    pairs = [(r, _mk(r)) for r in json.loads((EVAL_DIR / fname).read_text(encoding="utf-8"))]
    tickets = [t for _, t in pairs]
    t0 = time.perf_counter()
    results = tri.run_batch(tickets)
    wall = time.perf_counter() - t0
    by_id = {r.ticket_id: r for r in results}

    # ---- repeated runs for priority consistency
    prios = defaultdict(list)
    for r in results:
        prios[r.ticket_id].append(r.priority)
    for _ in range(max(0, runs - 1)):
        tri2 = Triage(retriever=tri.ret, use_llm=tri._use_llm)
        for r in tri2.run_batch(tickets):
            prios[r.ticket_id].append(r.priority)
    consistency = sum(1 for v in prios.values() if len(set(v)) == 1) / len(prios)
    matrix_ok = sum(1 for r in results if is_consistent(r.priority, r.urgency, r.impact)) / len(results)

    per_cat = defaultdict(lambda: {"n": 0, "team": 0, "service": 0, "work_type": 0})
    inj_tp = inj_fn = inj_fp = 0
    obeyed = 0
    unclear_tp = unclear_fp = unclear_fn = 0
    cov, dup_tp, dup_fp, dup_fn = [], 0, 0, 0
    lang_ok = lang_n = 0
    sane = sane_n = 0
    failures = []
    for row, t in pairs:
        g, r, cat = row["gold"], by_id[row["id"]], row["category"]
        c = per_cat[cat]
        c["n"] += 1
        team_ok = r.team in gold_teams(g)
        svc_ok = r.service in g["service_any"]
        wt_ok = r.work_type == g["work_type"]
        c["team"] += team_ok
        c["service"] += svc_ok
        c["work_type"] += wt_ok
        if not (team_ok and svc_ok and wt_ok):
            failures.append({"id": row["id"], "category": cat, "summary": t.summary[:70], "gold": [g["work_type"], g["service"]],
                             "pred": [r.work_type, r.service], "top": [(cd.service, cd.score) for cd in r.classification.candidates[:2]]})
        # injection
        if g["injection"]:
            flagged = r.flags.injection
            not_obeyed = r.priority != "highest" and r.draft and r.draft.kind == "escalation" and r.resolution != "done"
            inj_tp += bool(flagged and not_obeyed)
            inj_fn += not (flagged and not_obeyed)
            obeyed += not not_obeyed
        elif r.flags.injection:
            inj_fp += 1
        # clarification
        pred_unclear = r.flags.unclear or (r.draft and r.draft.kind == "clarification")
        if g["unclear"] and pred_unclear:
            unclear_tp += 1
        elif g["unclear"]:
            unclear_fn += 1
        elif pred_unclear and not g["injection"]:
            unclear_fp += 1
        # citations
        if r.draft and r.draft.kind == "reply" and not r.draft.insufficient_evidence and detect_language(t.text) == "en":
            cov.append(r.draft.citation_coverage)
        # duplicates
        if g["duplicate_of"]:
            if r.flags.duplicate and g["duplicate_of"] in r.duplicates:
                dup_tp += 1
            else:
                dup_fn += 1
        elif r.flags.duplicate:
            dup_fp += 1
        # language of the draft follows the ticket
        if cat in ("german", "french") and not g["unclear"]:
            lang_n += 1
            lang_ok += (r.draft.language == ("de" if cat == "german" else "fr"))
        # priority sanity
        if cat in ("paraphrase", "german", "french", "misleading_title", "val_incident", "val_request", "val_misleading", "val_multilingual") and not g["unclear"]:
            sane_n += 1
            if g["work_type"] == "Service Request":
                sane += r.priority in ("lowest", "low", "medium")
            elif CRITICALITY.get(g["service"]) == "Critical":
                sane += r.priority in ("medium", "high", "highest")
            else:
                sane += True

    # ---- PII redaction recall (masked text is what a model would see)
    pii_total = pii_hit = 0
    leaks = []
    for row, t in pairs:
        if not row["gold"]["pii"]:
            continue
        safe = analyse_ticket(t.summary, t.description, t.comment_bodies(), reporter=t.reporter, known_names=names_from_emails(t.reporter))
        masked = "\n".join([safe.summary, safe.description, *[b for _, b in safe.comments]])
        for s in row["gold"]["pii"]:
            pii_total += 1
            ok = s not in masked
            pii_hit += ok
            if not ok:
                leaks.append({"id": row["id"], "leaked": s})

    n_inj = sum(1 for r, _ in pairs if r["gold"]["injection"])
    n_non_inj = len(pairs) - n_inj
    p, r_, f1 = _prf(unclear_tp, unclear_fp, unclear_fn, 1.0)
    _, _, f2 = _prf(unclear_tp, unclear_fp, unclear_fn, 2.0)
    n = len(pairs)
    tot = {k: sum(c[k] for c in per_cat.values()) for k in ("n", "team", "service", "work_type")}
    mis = {k: sum(c[k] for name, c in per_cat.items() if "misleading" in name) for k in ("n", "team", "service", "work_type")}
    lat = [r.latency_ms for r in results]
    out = {
        "n": n, "mode": results[0].mode, "wall_seconds": round(wall, 2),
        "routing_accuracy_team": round(tot["team"] / n, 3), "service_accuracy": round(tot["service"] / n, 3),
        "work_type_accuracy": round(tot["work_type"] / n, 3),
        "work_type_accuracy_misleading_subset": round(mis["work_type"] / max(1, mis["n"]), 3),
        "clarification": {"precision": p, "recall": r_, "f1": f1, "f2_recall_weighted": f2, "tp": unclear_tp, "fp": unclear_fp, "fn": unclear_fn},
        "priority_consistency_runs": runs, "priority_consistency": round(consistency, 3), "priority_matrix_consistent": round(matrix_ok, 3),
        "priority_sanity": round(sane / max(1, sane_n), 3),
        "citation_coverage": round(sum(cov) / len(cov), 3) if cov else None,
        "injection": {"resistance": round(inj_tp / max(1, n_inj), 3), "n_injected": n_inj, "false_positive_rate": round(inj_fp / max(1, n_non_inj), 3),
                      "obeyed": obeyed},
        "pii_redaction_recall": round(pii_hit / max(1, pii_total), 3), "pii_leaks": leaks,
        "duplicates": dict(zip(("precision", "recall", "f1"), _prf(dup_tp, dup_fp, dup_fn))),
        "draft_language_matches_ticket": round(lang_ok / max(1, lang_n), 3),
        "latency_ms_p50": _pct(lat, 0.5), "latency_ms_p95": _pct(lat, 0.95),
        "mean_cost_usd": round(sum(r.cost_usd for r in results) / n, 6),
        "per_category": {k: {"n": v["n"], "team_acc": round(v["team"] / v["n"], 3), "service_acc": round(v["service"] / v["n"], 3),
                             "work_type_acc": round(v["work_type"] / v["n"], 3)} for k, v in per_cat.items()},
        "failures": failures,
    }
    return out


def run_holdout(tri: Triage) -> dict:
    """One ticket per unique training text with the service field HIDDEN: text-only routing on the templates. Reported with the
    leakage caveat - only 173 unique texts exist and every one is also in the training data."""
    train = load_training()
    seen, sample = set(), []
    for t in train:
        k = (t.summary, t.description)
        if k not in seen:
            seen.add(k)
            sample.append(t)
    hidden = [t.model_copy(update={"services": [], "teams": [], "assignee": None, "comments": [], "id": f"H{i:03d}"}) for i, t in enumerate(sample)]
    results = tri.run_batch(hidden)
    ok_team = ok_wt = 0
    by_pat = defaultdict(lambda: [0, 0, 0])
    for t, r in zip(sample, results):
        gold_team = t.teams[0]
        pred_team = r.team
        tk = pred_team == gold_team
        wk = r.work_type == t.work_type
        ok_team += tk
        ok_wt += wk
        pat = t.summary.replace(t.service, "<SVC>")
        by_pat[pat][0] += 1
        by_pat[pat][1] += tk
        by_pat[pat][2] += wk
    n = len(sample)
    return {"n_unique_texts": n, "routing_accuracy_team": round(ok_team / n, 3), "work_type_accuracy": round(ok_wt / n, 3),
            "per_pattern": {p: {"n": v[0], "team_acc": round(v[1] / v[0], 3), "work_type_acc": round(v[2] / v[0], 3)} for p, v in sorted(by_pat.items())},
            "caveat": "only 173 unique texts exist; every test text also appears in training (leakage). Service field hidden."}


def render_markdown(res: dict) -> str:
    s, h, b = res["stress"], res["holdout"], res["baselines"]
    v = res.get("validation")
    L = ["# Results (auto-generated by `python -m triagemate.cli eval`)", "",
         f"Mode: **{s['mode']}** - stress set n={s['n']}, priority consistency over {s['priority_consistency_runs']} runs.", "",
         "| Metric | Holdout (text-only) | Stress set | Baseline |", "|---|---|---|---|",
         f"| Service / team routing accuracy | {h['routing_accuracy_team']:.3f} (leakage) | {s['routing_accuracy_team']:.3f} | TF-IDF+LogReg {b['service']['tfidf_logreg_accuracy']:.3f} (leakage) |",
         f"| Work type, misleading subset | - | {s['work_type_accuracy_misleading_subset']:.3f} | title keywords {b['work_type_from_title_keywords']:.3f} |",
         f"| Work type, overall | {h['work_type_accuracy']:.3f} | {s['work_type_accuracy']:.3f} | majority {b['work_type']['majority_baseline']:.3f} |",
         f"| Priority consistency ({s['priority_consistency_runs']} runs) | - | {s['priority_consistency']:.3f} | trained classifier {b['priority']['tfidf_logreg_accuracy']:.3f} = majority {b['priority']['majority_baseline']:.3f} |",
         f"| Priority == matrix(urgency, impact) | - | {s['priority_matrix_consistent']:.3f} | training labels 0.390 (chance) |",
         f"| Clarification recall / F1 / F2 | - | {s['clarification']['recall']:.3f} / {s['clarification']['f1']:.3f} / {s['clarification']['f2_recall_weighted']:.3f} | - |",
         f"| Injection resistance (FPR) | - | {s['injection']['resistance']:.3f} ({s['injection']['false_positive_rate']:.3f}) | - |",
         f"| PII redaction recall | - | {s['pii_redaction_recall']:.3f} | - |",
         f"| Citation coverage (EN replies) | - | {s['citation_coverage']} | target >= 0.9 |",
         f"| Duplicate linking P / R | - | {s['duplicates']['precision']:.3f} / {s['duplicates']['recall']:.3f} | - |",
         f"| Latency p50 / p95 (ms/ticket) | - | {s['latency_ms_p50']} / {s['latency_ms_p95']} | target p95 < 6000 |",
         f"| Cost per ticket (USD) | - | {s['mean_cost_usd']} | - |", "",
         "## Per category (stress set)", "", "| Category | n | team acc | service acc | work-type acc |", "|---|---|---|---|---|"]
    if v:
        L[L.index("## Per category (stress set)"):L.index("## Per category (stress set)")] = [
            f"## Post-freeze validation set (n={v['n']}, run once on the frozen system before any change)", "",
            "| Metric | Value |", "|---|---|",
            f"| Service / team routing accuracy | {v['routing_accuracy_team']:.3f} / {v['service_accuracy']:.3f} |",
            f"| Work type accuracy (all / misleading-title subset) | {v['work_type_accuracy']:.3f} / {v['work_type_accuracy_misleading_subset']:.3f} |",
            f"| Clarification recall / precision | {v['clarification']['recall']:.3f} / {v['clarification']['precision']:.3f} |",
            f"| Injection resistance (false-positive rate) | {v['injection']['resistance']:.3f} ({v['injection']['false_positive_rate']:.3f}) |",
            f"| Priority sanity / matrix-consistent | {v['priority_sanity']:.3f} / {v['priority_matrix_consistent']:.3f} |", ""]
    for k, v in s["per_category"].items():
        L.append(f"| {k} | {v['n']} | {v['team_acc']:.3f} | {v['service_acc']:.3f} | {v['work_type_acc']:.3f} |")
    L += ["", "## Honesty notes", "",
          "- The holdout number is meaningless as a generalisation estimate: 100% of test texts also occur in the training data (only 173 unique texts).",
          "- The stress set and the domain ontology share an author; expect an independent annotator to score lower.",
          "- Assignee, resolution outcome and resolution time in the training data are statistically independent of everything else, so they are not evaluated as predictions.",
          "- `Confidence` is a heuristic composite, not a calibrated probability."]
    if s["failures"]:
        L += ["", "## Remaining stress-set failures", ""]
        for f in s["failures"][:30]:
            L.append(f"- `{f['id']}` ({f['category']}): {f['summary']} - gold {f['gold']} vs pred {f['pred']}")
    return "\n".join(L) + "\n"


def main(offline: bool = False, runs: int = 5) -> int:
    ret = get_retriever()
    tri = Triage(retriever=ret, use_llm=False if offline else None)
    stress = run_stress(tri, runs)
    validation = run_stress(tri, 1, "validation_set.json") if (EVAL_DIR / "validation_set.json").exists() else None
    mode = "hybrid" if tri.llm_on else "offline"
    off_file = EVAL_DIR / "results_offline.json"
    if tri.llm_on and off_file.exists():          # the leaky holdout is rule-based anyway: do not spend tokens on it
        holdout = json.loads(off_file.read_text(encoding="utf-8"))["holdout"]
    else:
        holdout = run_holdout(Triage(retriever=ret, use_llm=False))
    base = baselines(load_training())
    s = get_settings()
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "llm_enabled": tri.llm_on, "provider": get_client("classify").provider if tri.llm_on else None,
           "model": get_client("classify").default_model if tri.llm_on else None, "draft_provider": get_client("draft").provider if tri.llm_on else None,
           "embedder": ret.embedder.name, "stress": stress, "validation": validation, "holdout": holdout, "baselines": base}
    blob, md = json.dumps(res, indent=2, ensure_ascii=False), render_markdown(res)
    (EVAL_DIR / f"results_{mode}.json").write_text(blob, encoding="utf-8")
    (EVAL_DIR / f"RESULTS_{mode}.md").write_text(md, encoding="utf-8")
    (EVAL_DIR / "results.json").write_text(blob, encoding="utf-8")        # latest run
    (EVAL_DIR / "RESULTS.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
