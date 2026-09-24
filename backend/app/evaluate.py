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
  LLM_MODE=mock uv run python -m app.evaluate --db /tmp/eval.db    # offline, heuristic triage
"""
import argparse
import collections
import copy
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
Prefer done unless the ticket content clearly points to another outcome."""


def parse_args() -> argparse.Namespace:
    from .config import REPO_DIR

    p = argparse.ArgumentParser(prog="python -m app.evaluate", description=__doc__.split("\n\n")[0])
    p.add_argument("--input", type=Path, default=next(iter(sorted(REPO_DIR.glob("jira_hackathon_blind_eval_challenge_*.json"))), None),
                   help="challenge file (default: jira_hackathon_blind_eval_challenge_*.json in the repo root)")
    p.add_argument("--out", type=Path, default=Path("out/eval"), help="output directory (default out/eval)")
    p.add_argument("--db", type=Path, help="SQLite knowledge base (default: DB_PATH / backend/data/knowledge.db)")
    p.add_argument("--limit", type=int, help="only the first N tickets")
    p.add_argument("--workers", type=int, default=4, help="parallel LLM calls (default 4)")
    p.add_argument("--llm", help="chat provider: foundry, openai or apertus (default: LLM_MODE / first configured)")
    return p.parse_args()


def ticket_text(r: dict) -> str:
    """Everything the reporter gave us. Pre-filled routing fields are labelled as unverified."""
    services = ", ".join(r.get("Affected Business or IT Services") or []) or "(none)"
    comments = "\n".join(f"- {c}" for c in r.get("All Comments") or [])
    return "\n".join(filter(None, [
        f"Summary: {r.get('Summary') or ''}",
        f"Description: {r.get('Description') or ''}",
        f"Request type (intake channel): {r.get('Request type') or '(none)'}",
        f"Business entity: {', '.join(r.get('Business Entity') or []) or '(none)'}",
        f"Reporter-selected service (unverified, often wrong): {services}",
        f"Reporter-selected work type (unverified, titles can be misleading): {r.get('Work type')}",
        f"Comments:\n{comments}" if comments else "",
    ]))


def title(level: str) -> str:
    return level.capitalize()


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


def main() -> None:
    args = parse_args()
    if args.db:  # settings are read at import time, so set before importing the app
        os.environ["DB_PATH"] = str(args.db)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for name in ("httpx", "httpx2"):
        logging.getLogger(name).setLevel(logging.WARNING)

    from . import catalog
    from .config import settings
    from .knowledge import ensure_ready
    from .llm import get_llm
    from .store import Store
    from .triage import RESOLUTION_SYSTEM, _format_hits, pick_assignee, triage

    if not args.input or not args.input.exists():
        sys.exit(f"challenge file not found: {args.input}")
    challenge = json.load(open(args.input))
    records = challenge["records"][: args.limit] if args.limit else challenge["records"]
    run_id = challenge.get("runId") or args.input.stem

    llm = get_llm(args.llm)
    store = Store(settings.db_path)
    ensure_ready(store)
    experts = service_resolvers()
    t0 = time.time()
    print(f"Evaluating {len(records)} tickets from {args.input.name} (mode={llm.mode}, knowledge={store.knowledge_stats()['total']})")

    # Retrieval is done up front on this thread (the store shares one SQLite connection); only LLM calls fan out.
    texts = [ticket_text(r) for r in records]
    vectors = llm.embed(texts)
    # Wider net for assignee voting than for the prompt, so the chosen service usually has a precedent resolver.
    all_hits = [store.search_knowledge(v, settings.top_k * 3) for v in vectors]
    resolution_hits = [[h for h in store.search_knowledge(v, settings.top_k * 4) if h.row.get("resolution")] for v in vectors]

    def run(i: int) -> dict:
        r, text, hits = records[i], texts[i], all_hits[i]
        decision, routing = triage(text, [], hits[: settings.top_k], provider=llm.mode)
        if not routing["assignee"]:  # same voting over the wider net, then the service's main resolver
            routing["assignee"], routing["assigneeReason"] = pick_assignee(routing["service"], hits)
            if not routing["assignee"] and experts.get(routing["service"]):
                routing["assignee"] = experts[routing["service"]]
                routing["assigneeReason"] = f"most frequent author of documented {routing['service']} fixes in the history"

        precedents = [h for h in resolution_hits[i] if h.row["service"] == routing["service"]][: settings.top_k] \
            or resolution_hits[i][: settings.top_k]
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
        print(f"  [{i + 1:>2}/{len(records)}] {routing['workType']:<15} {routing['service']:<28} "
              f"{title(routing['priority']):<8} {resolution:<16} {r.get('Summary', '')[:60]}")
        return {"decision": decision, "routing": routing, "resolution": resolution,
                "resolutionText": resolution_text, "matches": hits[: settings.top_k], "precedents": precedents[:3]}

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        outputs = list(pool.map(run, range(len(records))))

    answered, traces = [], []
    for r, o in zip(records, outputs):
        rt = o["routing"]
        a = copy.deepcopy(r)
        a["Work type"] = rt["workType"]
        a["Affected Business or IT Services"] = [rt["service"]]
        a["Service Team(s)"] = [rt["team"]]
        a["Assignee"] = rt["assignee"]
        a["Urgency"], a["Impact"], a["Priority"] = title(rt["urgency"]), title(rt["impact"]), title(rt["priority"])
        a["Resolution"] = o["resolution"]
        a["All Comments"] = [*(r.get("All Comments") or []), f"{rt['assignee'] or rt['team']}: Resolution: {o['resolutionText']}"]
        answered.append(a)
        fields = ["Work type", "Affected Business or IT Services", "Service Team(s)", "Assignee", "Urgency", "Impact",
                  "Priority", "Resolution"]
        traces.append({
            "summary": r.get("Summary"),
            "changed": {f: {"input": r.get(f), "output": a[f]} for f in fields if r.get(f) != a[f]},
            "understanding": o["decision"].get("understanding"),
            "rationale": o["decision"].get("rationale"),
            "assigneeReason": rt["assigneeReason"],
            "resolutionText": o["resolutionText"],
            "matches": [{"id": h.row["id"], "service": h.row["service"], "resolver": h.row.get("resolver"),
                         "score": round(h.score, 3), "title": h.row["title"]} for h in o["matches"]],
            "precedents": [{"id": h.row["id"], "resolution": h.row["resolution"], "score": round(h.score, 3)}
                           for h in o["precedents"]],
        })

    # Consistency checks the judges score on: priority follows the matrix, team follows the catalog.
    problems = []
    for n, a in enumerate(answered, 1):
        svc = a["Affected Business or IT Services"][0]
        if catalog.priority(a["Urgency"].lower(), a["Impact"].lower()) != a["Priority"].lower():
            problems.append(f"#{n}: priority {a['Priority']} inconsistent with {a['Urgency']} x {a['Impact']}")
        if svc not in catalog.SERVICES or a["Service Team(s)"] != [catalog.team_for(svc)]:
            problems.append(f"#{n}: service/team mismatch {svc} / {a['Service Team(s)']}")
        if not a["Assignee"]:
            problems.append(f"#{n}: no precedent resolver for {svc}, left in the {a['Service Team(s)'][0]} queue")

    args.out.mkdir(parents=True, exist_ok=True)
    meta = {"evaluatedAtUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "llmMode": llm.mode,
            "chatDeployment": llm.chat_model if llm.mode != "mock" else None,
            "embeddingModel": llm.embedding_model, "knowledge": store.knowledge_stats(), "source": args.input.name}
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
