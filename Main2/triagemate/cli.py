"""Command line: ``python -m triagemate.cli <command>``

  analyze          reproduce the dataset findings            -> eval/dataset_analysis.json
  run-challenge    triage a challenge file                    -> outputs/challenge_predictions.{json,csv}
  eval             run the stress set + holdout               -> eval/results.json
  triage           triage one pasted ticket (text on stdin or --text)
  intake           enrich ONE incident from just its description        -> JSON for the UI (see docs/INTAKE_HANDOFF.md)
  assist           typing-assist suggestions for partial text          -> JSON
  schema           write the JSON Schemas of the intake contracts      -> docs/intake_schema.json
  serve            start the API + UI                         -> http://127.0.0.1:8000
  smoke            provider smoke test (chat, JSON, tools, embeddings)
"""
from __future__ import annotations

import argparse
import json
import sys


def _force_utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    ap = argparse.ArgumentParser(prog="triagemate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("analyze")
    rc = sub.add_parser("run-challenge")
    rc.add_argument("--input", default=None)
    rc.add_argument("--out", default=None)
    rc.add_argument("--offline", action="store_true", help="force the deterministic engine even if an LLM key is configured")
    rc.add_argument("--tag", default="")
    ev = sub.add_parser("eval")
    ev.add_argument("--offline", action="store_true")
    ev.add_argument("--runs", type=int, default=5, help="repeat runs for the priority-consistency metric")
    tr = sub.add_parser("triage")
    tr.add_argument("--text", default=None)
    tr.add_argument("--service", default=None)
    tr.add_argument("--offline", action="store_true")
    ik = sub.add_parser("intake")
    ik.add_argument("--text", default=None)
    ik.add_argument("--offline", action="store_true")
    asx = sub.add_parser("assist")
    asx.add_argument("--text", default="")
    asx.add_argument("--mode", default="fast", choices=["fast", "smart"])
    sub.add_parser("schema")
    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sub.add_parser("smoke")
    a = ap.parse_args(argv)

    if a.cmd == "analyze":
        from .analyze import analyze, print_summary
        print_summary(analyze())
        return 0
    if a.cmd == "run-challenge":
        from .challenge import run_challenge
        from .data import find_challenge_file
        path = a.input or find_challenge_file()
        if not path:
            print("no challenge file found in data/ (expected jira_hackathon*challenge*.json); pass --input", file=sys.stderr)
            return 2
        summary = run_challenge(path, a.out, use_llm=False if a.offline else None, tag=a.tag)
        print(json.dumps(summary, indent=2))
        return 0
    if a.cmd == "eval":
        from eval.run_eval import main as eval_main
        return eval_main(offline=a.offline, runs=a.runs)
    if a.cmd == "triage":
        from .models import Ticket
        from .pipeline import Triage
        text = a.text or sys.stdin.read()
        summary, _, desc = text.partition("\n")
        t = Ticket(id="PASTE-1", summary=summary.strip(), description=(desc or summary).strip(), services=[a.service] if a.service else [], source="paste")
        r = Triage(use_llm=False if a.offline else None).run_ticket(t)
        print(r.model_dump_json(indent=2))
        return 0
    if a.cmd == "intake":
        from .intake import enrich_incident
        text = a.text or sys.stdin.read()
        print(json.dumps(enrich_incident(text, use_llm=False if a.offline else None, commit_assign=False).to_json(), indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "assist":
        from .assist import assist
        print(json.dumps(assist(a.text, mode=a.mode).to_json(), indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "schema":
        from pathlib import Path
        from .config import ROOT
        from .intake import json_schemas
        out = Path(ROOT) / "docs" / "intake_schema.json"
        out.write_text(json.dumps(json_schemas(), indent=2, ensure_ascii=False), encoding="utf-8")
        print("written", out)
        return 0
    if a.cmd == "serve":
        import uvicorn
        uvicorn.run("triagemate.api:app", host=a.host, port=a.port, reload=False)
        return 0
    if a.cmd == "smoke":
        from scripts.smoke_llm import main as smoke_main
        return smoke_main()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
