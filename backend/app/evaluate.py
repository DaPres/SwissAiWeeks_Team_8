"""Run the triage pipeline over the blind-eval challenge file and write the answers in the challenge format.

Per ticket (the same pipeline the assistant uses, see triage.py):
  embed ticket text -> retrieve knowledge -> LLM decides work type / service / urgency / impact
  -> code: team lookup, assignee = resolver of the most similar fixes, priority = urgency x impact matrix
  -> LLM picks the resolution status and writes the resolution comment from precedent resolutions.

The reporter-selected service, priority, urgency and impact in the challenge file are treated as untrusted hints.

Outputs (in --out, named after the input's runId):
  <runId>.results.json   the challenge file with the 7 answer fields filled in (submit this)
  <runId>.trace.json     per ticket: rationale, knowledge matches, assignee reasoning, fields changed vs input
  <runId>.report.md      human-readable summary table + consistency checks

Examples (from backend/):
  uv run python -m app.evaluate                                   # default challenge file in the repo root
  uv run python -m app.evaluate --input ../other_challenge.json --out out/eval
  uv run python -m app.evaluate --limit 3 --workers 1              # quick smoke run
  uv run python -m app.evaluate --llm apertus --top-k 8 --min-score 0.4
  LLM_MODE=mock uv run python -m app.evaluate --db /tmp/eval.db    # offline, heuristic triage

The same engine (`evaluate()`) backs the Evaluation tab: /api/eval/* in main.py, runs managed by eval_runs.py.
"""
import argparse
import collections
import copy
import json
import logging
import os
import re
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Runs started from the UI can overlap; the store shares one SQLite connection, so retrieval is serialised.
_retrieval_lock = threading.Lock()

RESOLUTIONS = ["done", "cancelled", "clarification", "cannot reproduce"]

RESOLUTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["resolution", "resolution_text"],
    "properties": {
        "resolution": {"type": "string", "enum": RESOLUTIONS},
        "resolution_text": {"type": "string", "description": "The resolution comment, without author or 'Resolution:' prefix."},
    },
}

RESOLUTION_OUTCOME_RULES = """
Also choose the resolution status, using the service desk's vocabulary:
- done: the request was fulfilled or the incident fixed (the normal outcome when the ticket is actionable).
- clarification: the input is too vague to act on (no system, identifier or concrete symptom) and the requester
  had to be asked for details; the comment says what was asked.
- cannot reproduce: the reported symptom could not be found or confirmed on investigation.
- cancelled: the request was withdrawn, a duplicate, or not needed.
Prefer done unless the ticket content clearly points to another outcome. A clear request about a person the ticket does
not name (the contractor, the new joiner) is actionable: the agent identifies them from the requester or HR records, so
refer to them by role and resolve it."""


@dataclass
class EvalConfig:
    llm: str | None = None           # chat provider id; None = default
    top_k: int | None = None         # knowledge items in the prompt; None = TOP_K setting
    min_score: float = 0.0           # drop knowledge matches at or below this cosine similarity (0 = keep all)
    workers: int = 4                 # parallel LLM calls
    limit: int | None = None         # only the first N tickets


def challenge_files() -> list[Path]:
    from .config import REPO_DIR, settings

    found = sorted(REPO_DIR.glob("jira_hackathon_blind_eval_challenge_*.json"))
    if settings.challenge_file and settings.challenge_file.exists() and settings.challenge_file not in found:
        found.insert(0, settings.challenge_file)
    return found


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m app.evaluate", description=__doc__.split("\n\n")[0])
    p.add_argument("--input", type=Path, default=next(iter(challenge_files()), None),
                   help="challenge file (default: jira_hackathon_blind_eval_challenge_*.json in the repo root)")
    p.add_argument("--out", type=Path, default=Path("out/eval"), help="output directory (default out/eval)")
    p.add_argument("--db", type=Path, help="SQLite knowledge base (default: DB_PATH / backend/data/knowledge.db)")
    p.add_argument("--limit", type=int, help="only the first N tickets")
    p.add_argument("--workers", type=int, default=4, help="parallel LLM calls (default 4)")
    p.add_argument("--llm", help="chat provider: foundry, openai or apertus (default: LLM_MODE / first configured)")
    p.add_argument("--top-k", type=int, help="knowledge items per prompt (default: TOP_K)")
    p.add_argument("--min-score", type=float, default=0.0,
                   help="minimum knowledge similarity to use a match (default 0 = keep all)")
    return p.parse_args()


def ticket_text(r: dict) -> str:
    """Everything the reporter gave us. Pre-filled routing fields are labelled as unverified. The reporter's address is
    replaced by their role (domain kept, so vendor mails stay recognisable): otherwise the model takes the requester for
    the affected user and writes "licence provisioned for / access removed from <reporter>"."""
    services = ", ".join(r.get("Affected Business or IT Services") or []) or "(none)"
    comments = "\n".join(f"- {c}" for c in r.get("All Comments") or [])
    text = "\n".join(filter(None, [
        f"Summary: {r.get('Summary') or ''}",
        f"Description: {r.get('Description') or ''}",
        f"Request type (intake channel): {r.get('Request type') or '(none)'}",
        f"Business entity: {', '.join(r.get('Business Entity') or []) or '(none)'}",
        f"Reporter-selected service (unverified, often wrong): {services}",
        f"Reporter-selected work type (unverified, titles can be misleading): {r.get('Work type')}",
        f"Comments:\n{comments}" if comments else "",
    ]))
    reporter = r.get("Reporter")
    if reporter and "@" in reporter:
        text = re.sub(re.escape(reporter), f"the reporter (@{reporter.split('@', 1)[1]})", text, flags=re.IGNORECASE)
    return text


def title(level: str) -> str:
    return level.capitalize()


@lru_cache(maxsize=1)
def service_resolvers() -> dict[str, str]:
    """Each service's most frequent author of documented fixes across the whole history (not just published
    knowledge). Services whose history only has "Problem fixed." have no reliable expert and stay unassigned."""
    from .curation import score_ticket, training_tickets

    votes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for t in training_tickets():
        s = score_ticket(t)
        if s["resolver"]:
            votes[s["service"]][s["resolver"]] += 1
    return {svc: c.most_common(1)[0][0] for svc, c in votes.items()}


ANSWER_FIELDS = ["Work type", "Affected Business or IT Services", "Service Team(s)", "Assignee", "Urgency", "Impact",
                 "Priority", "Resolution"]


def ticket_problems(a: dict) -> list[str]:
    """Consistency checks the judges score on: priority follows the matrix, team follows the catalog."""
    from . import catalog

    problems = []
    svc = a["Affected Business or IT Services"][0]
    if catalog.priority(a["Urgency"].lower(), a["Impact"].lower()) != a["Priority"].lower():
        problems.append(f"priority {a['Priority']} inconsistent with {a['Urgency']} x {a['Impact']}")
    if svc not in catalog.SERVICES or a["Service Team(s)"] != [catalog.team_for(svc)]:
        problems.append(f"service/team mismatch {svc} / {a['Service Team(s)']}")
    if not a["Assignee"]:
        problems.append(f"no precedent resolver for {svc}, left in the {a['Service Team(s)'][0]} queue")
    return problems


def evaluate(store, records: list[dict], config: EvalConfig,
             on_ticket: Callable[[int, dict], None] | None = None,
             should_stop: Callable[[], bool] = lambda: False) -> list[dict | None]:
    """Triage every record. Returns one result per record (None if stopped before it ran):
    {"record": answered challenge record, "trace": rationale/matches/changes, "problems": [...], "seconds": ...}.
    `on_ticket(index, result)` is called from worker threads as each ticket finishes."""
    from .config import settings
    from .llm import get_llm
    from .triage import RESOLUTION_SYSTEM, _format_hits, pick_assignee, triage

    llm = get_llm(config.llm)
    top_k = config.top_k or settings.top_k
    experts = service_resolvers()

    # Retrieval is done up front on this thread (the store shares one SQLite connection); only LLM calls fan out.
    texts = [ticket_text(r) for r in records]
    vectors = llm.embed(texts)
    with _retrieval_lock:
        # Wider net for assignee voting than for the prompt, so the chosen service usually has a precedent resolver.
        all_hits = [[h for h in store.search_knowledge(v, top_k * 3) if h.score > config.min_score] for v in vectors]
        resolution_hits = [[h for h in store.search_knowledge(v, top_k * 4) if h.row.get("resolution")
                            and h.score > config.min_score] for v in vectors]

    def run(i: int) -> dict | None:
        if should_stop():
            return None
        started = time.time()
        r, text, hits = records[i], texts[i], all_hits[i]
        decision, routing = triage(text, [], hits[:top_k], provider=llm.mode)
        if not routing["assignee"]:  # same voting over the wider net, then the service's main resolver
            routing["assignee"], routing["assigneeReason"] = pick_assignee(routing["service"], hits)
            if not routing["assignee"] and experts.get(routing["service"]):
                routing["assignee"] = experts[routing["service"]]
                routing["assigneeReason"] = f"most frequent author of documented {routing['service']} fixes in the history"

        precedents = [h for h in resolution_hits[i] if h.row["service"] == routing["service"]][:top_k] \
            or resolution_hits[i][:top_k]
        user = (
            f"Ticket [{routing['workType']}] service={routing['service']} team={routing['team']} "
            f"assigned agent={routing['assignee']}\n{text}\n"
            f"\nTriage understanding: {decision.get('understanding', '')}"
            f"\n\nPrecedent resolutions:\n{_format_hits(precedents)}"
        )

        def fallback() -> dict:
            unclear = (r.get("Request type") or "").startswith("Nonsense")
            return {"resolution": "clarification" if unclear else "done",
                    "resolution_text": precedents[0].row["resolution"] if precedents else
                    "Investigated the reported issue, applied the fix and confirmed with the requester."}

        outcome = llm.complete_json(RESOLUTION_SYSTEM + RESOLUTION_OUTCOME_RULES, user, RESOLUTION_SCHEMA,
                                    "resolution", fallback=fallback)
        resolution = outcome.get("resolution") if outcome.get("resolution") in RESOLUTIONS else "done"
        resolution_text = (outcome.get("resolution_text") or fallback()["resolution_text"]).strip()

        a = copy.deepcopy(r)
        a["Work type"] = routing["workType"]
        a["Affected Business or IT Services"] = [routing["service"]]
        a["Service Team(s)"] = [routing["team"]]
        a["Assignee"] = routing["assignee"]
        a["Urgency"], a["Impact"], a["Priority"] = title(routing["urgency"]), title(routing["impact"]), title(routing["priority"])
        a["Resolution"] = resolution
        a["All Comments"] = [*(r.get("All Comments") or []),
                             f"{routing['assignee'] or routing['team']}: Resolution: {resolution_text}"]
        result = {
            "record": a,
            "trace": {
                "summary": r.get("Summary"),
                "changed": {f: {"input": r.get(f), "output": a[f]} for f in ANSWER_FIELDS if r.get(f) != a[f]},
                "understanding": decision.get("understanding"),
                "rationale": decision.get("rationale"),
                "assigneeReason": routing["assigneeReason"],
                "resolutionText": resolution_text,
                "matches": [{"id": h.row["id"], "service": h.row["service"], "resolver": h.row.get("resolver"),
                             "score": round(h.score, 3), "title": h.row["title"]} for h in hits[:top_k]],
                "precedents": [{"id": h.row["id"], "resolution": h.row["resolution"], "score": round(h.score, 3)}
                               for h in precedents[:3]],
            },
            "problems": ticket_problems(a),
            "seconds": round(time.time() - started, 2),
        }
        if on_ticket:
            on_ticket(i, result)
        return result

    with ThreadPoolExecutor(max_workers=max(1, config.workers)) as pool:
        return list(pool.map(run, range(len(records))))


def run_meta(store, config: EvalConfig, source: str) -> dict:
    from .config import settings
    from .llm import get_llm

    llm = get_llm(config.llm)
    return {"evaluatedAtUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "llmMode": llm.mode,
            "chatDeployment": llm.chat_model if llm.mode != "mock" else None,
            "embeddingModel": llm.embedding_model, "knowledge": store.knowledge_stats(), "source": source,
            "topK": config.top_k or settings.top_k, "minScore": config.min_score}


def main() -> None:
    args = parse_args()
    if args.db:  # settings are read at import time, so set before importing the app
        os.environ["DB_PATH"] = str(args.db)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for name in ("httpx", "httpx2"):
        logging.getLogger(name).setLevel(logging.WARNING)

    from .config import settings
    from .knowledge import ensure_ready
    from .llm import get_llm
    from .store import Store

    if not args.input or not args.input.exists():
        sys.exit(f"challenge file not found: {args.input}")
    challenge = json.load(open(args.input))
    records = challenge["records"][: args.limit] if args.limit else challenge["records"]
    run_id = challenge.get("runId") or args.input.stem
    config = EvalConfig(llm=args.llm, top_k=args.top_k, min_score=args.min_score, workers=args.workers)

    llm = get_llm(args.llm)
    store = Store(settings.db_path)
    ensure_ready(store)
    t0 = time.time()
    print(f"Evaluating {len(records)} tickets from {args.input.name} (mode={llm.mode}, "
          f"knowledge={store.knowledge_stats()['total']}, top_k={config.top_k or settings.top_k}, min_score={config.min_score})")

    def progress(i: int, o: dict) -> None:
        a = o["record"]
        print(f"  [{i + 1:>2}/{len(records)}] {a['Work type']:<15} {a['Affected Business or IT Services'][0]:<28} "
              f"{a['Priority']:<8} {a['Resolution']:<16} {records[i].get('Summary', '')[:60]}")

    outputs = evaluate(store, records, config, on_ticket=progress)
    answered = [o["record"] for o in outputs]
    traces = [o["trace"] for o in outputs]
    problems = [f"#{n}: {p}" for n, o in enumerate(outputs, 1) for p in o["problems"]]

    args.out.mkdir(parents=True, exist_ok=True)
    meta = run_meta(store, config, args.input.name)
    results_path = args.out / f"{run_id}.results.json"
    trace_path = args.out / f"{run_id}.trace.json"
    report_path = args.out / f"{run_id}.report.md"
    json.dump({**challenge, "records": answered, "triage": meta}, open(results_path, "w"), indent=2, ensure_ascii=False)
    json.dump({"meta": meta, "tickets": traces}, open(trace_path, "w"), indent=2, ensure_ascii=False)
    report_path.write_text(render_report(run_id, meta, records, answered, traces, problems))

    print(f"\nDone in {time.time() - t0:.1f}s. Consistency: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    for p in problems:
        print("  " + p)
    print(f"  results: {results_path}\n  trace:   {trace_path}\n  report:  {report_path}")


def render_report(run_id: str, meta: dict, records: list[dict], answered: list[dict], traces: list[dict],
                  problems: list[str]) -> str:
    def cell(v) -> str:
        v = ", ".join(v) if isinstance(v, list) else ("" if v is None else str(v))
        return v.replace("|", "\\|").replace("\n", " ")

    lines = [
        f"# Blind eval results — {run_id}",
        "",
        f"{meta['evaluatedAtUtc']} · mode `{meta['llmMode']}` · chat `{meta['chatDeployment']}` · "
        f"embeddings `{meta['embeddingModel']}` · {meta['knowledge']['total']} knowledge items (min level {meta['knowledge']['minLevel']})",
        "",
        "Consistency checks: " + ("all passed" if not problems else "; ".join(problems)),
        "",
        "| # | Summary | Work type | Service (input → output) | Team | Assignee | Urgency × Impact → Priority | Resolution |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for n, (r, a) in enumerate(zip(records, answered), 1):
        svc_in, svc_out = cell(r.get("Affected Business or IT Services")), cell(a["Affected Business or IT Services"])
        wt = a["Work type"] if a["Work type"] == r.get("Work type") else f"**{a['Work type']}** (was {r.get('Work type')})"
        lines.append(
            f"| {n} | {cell(r.get('Summary'))} | {wt} | {svc_out if svc_in == svc_out else f'~~{svc_in}~~ → **{svc_out}**'} | "
            f"{cell(a['Service Team(s)'])} | {cell(a['Assignee'])} | {a['Urgency']} × {a['Impact']} → **{a['Priority']}** | "
            f"{a['Resolution']} |")
    lines += ["", "## Resolution comments and rationale", ""]
    for n, (a, t) in enumerate(zip(answered, traces), 1):
        lines += [
            f"### {n}. {t['summary']}",
            "",
            f"- **Resolution ({a['Resolution']}):** {t['resolutionText']}",
            f"- **Why:** {t['rationale'] or ''}",
            f"- **Assignee:** {a['Assignee']} — {t['assigneeReason']}",
            "",
        ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
