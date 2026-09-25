"""Self-audit of a challenge output file against the organisers' README (run it before submitting).

    python scripts/validate_submission.py                                   # bundled challenge file vs outputs/challenge_predictions.json
    python scripts/validate_submission.py --input NEW.json --pred OUT.json  # any new bundle

Everything is checked *independently of the engine's own code*: the priority matrix is re-typed from the README, the
service -> team mapping is re-derived from the 20,000 training tickets, and the vocabularies come from the training data.
Exit code 0 = every hard check passed.
"""
from __future__ import annotations

import argparse
import ast
import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from triagemate.config import get_settings  # noqa: E402
from triagemate.data import find_challenge_file, read_records  # noqa: E402

# Incident Priority Calculation Matrix, typed in from the challenge README (rows = urgency, columns = impact Major..None)
MATRIX = {
    "highest": ["highest", "highest", "high", "medium", "medium"],
    "high": ["highest", "high", "high", "medium", "low"],
    "medium": ["high", "high", "medium", "low", "low"],
    "low": ["medium", "medium", "low", "low", "lowest"],
    "lowest": ["medium", "low", "low", "lowest", "lowest"],
}
LEVELS = ["highest", "high", "medium", "low", "lowest"]
GENERIC = re.compile(r"^\W*(?:[\w.@-]+:\s*)?(?:resolution:\s*)?(?:issue |problem )?(?:fixed|resolved|done|ok)\W*$", re.I)
PII = re.compile(r"(?:\+\d[\d ()-]{8,}|\b[A-Z]{2}\d{2}(?: ?\d{4}){3,}\b)")


def _lst(v):
    if isinstance(v, list):
        return v
    try:
        x = ast.literal_eval(v) if isinstance(v, str) else []
        return x if isinstance(x, list) else []
    except Exception:  # noqa: BLE001
        return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None, help="the challenge file that was triaged (default: bundled)")
    ap.add_argument("--pred", default=None, help="the predictions file (default: outputs/challenge_predictions.json)")
    a = ap.parse_args()
    s = get_settings()
    inp_path = Path(a.input) if a.input else find_challenge_file()
    pred_path = Path(a.pred) if a.pred else s.outputs_dir / "challenge_predictions.json"
    inp, env_in = read_records(inp_path)
    out, env_out = read_records(pred_path)

    import json
    train = json.loads((s.data_dir / "jira_first_20000_requested_fields_synthetic.json").read_text(encoding="utf-8"))
    team_votes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for r in train:
        for sv in _lst(r["Affected Business or IT Services"]):
            for tm in _lst(r["Service Team(s)"]):
                team_votes[sv][tm] += 1
    team_of = {sv: c.most_common(1)[0][0] for sv, c in team_votes.items()}
    services = set(team_of)
    assignees = {r["Assignee"] for r in train if r.get("Assignee")}
    vocab_res = {r["Resolution"] for r in train if r.get("Resolution")}
    vocab_wt = {r["Work type"] for r in train}

    rows: list[tuple[str, bool, str, bool]] = []          # (check, ok, detail, hard)

    def check(name: str, ok: bool, detail: str = "", hard: bool = True):
        rows.append((name, bool(ok), detail, hard))

    check("record count equals input", len(inp) == len(out), f"{len(out)} of {len(inp)}")
    check("same columns, same order", all(list(x) == list(y) for x, y in zip(inp, out)))
    check("envelope metadata preserved", all(k in env_out for k in env_in) if env_in else True)
    bad = collections.defaultdict(list)
    for i, (x, r) in enumerate(zip(inp, out)):
        tag = f"#{i + 1}"
        if r["Work type"] not in vocab_wt:
            bad["work type in {Incident, Service Request}"].append(tag)
        svc = _lst(r["Affected Business or IT Services"]) if not isinstance(r["Affected Business or IT Services"], list) else r["Affected Business or IT Services"]
        if len(svc) != 1 or svc[0] not in services:
            bad["exactly one service, from the 20-service catalogue"].append(tag)
        else:
            teams = r["Service Team(s)"] if isinstance(r["Service Team(s)"], list) else _lst(r["Service Team(s)"])
            if teams != [team_of[svc[0]]]:
                bad["team is the owning team of the service (re-derived from training data)"].append(tag)
        if r["Resolution"] not in vocab_res:
            bad["resolution in {done, cancelled, clarification, cannot reproduce}"].append(tag)
        u, im, p = (str(r[k]).lower() for k in ("Urgency", "Impact", "Priority"))
        if u not in MATRIX or im not in LEVELS or p not in LEVELS:
            bad["urgency / impact / priority use the 5-level vocabulary"].append(tag)
        elif MATRIX[u][LEVELS.index(im)] != p:
            bad["priority == matrix(urgency, impact)"].append(tag)
        if r["Assignee"] not in assignees:
            bad["assignee is a known agent from the training data"].append(tag)
        cm_in, cm_out = _lst(x.get("All Comments")) if not isinstance(x.get("All Comments"), list) else x["All Comments"], r["All Comments"]
        if len(cm_out) != len(cm_in) + 1:
            bad["exactly one resolution comment appended"].append(tag)
            continue
        note = str(cm_out[-1])
        if not note.startswith(f"{r['Assignee']}:"):
            bad["comment is written in the voice of the assignee"].append(tag)
        body = note.split(":", 1)[-1].strip()
        if len(body) < 120 or GENERIC.match(body):
            bad["comment is concrete, not generic filler (>=120 chars)"].append(tag)
        ticket_words = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9_&-]{4,}", f"{x.get('Summary', '')} {x.get('Description', '')}")}
        if not (ticket_words & {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9_&-]{4,}", body)}):
            bad["comment refers to the ticket's own content"].append(tag)
        if PII.search(note):
            bad["comment contains no phone / IBAN pattern"].append(tag)
    every = ["work type in {Incident, Service Request}", "exactly one service, from the 20-service catalogue",
             "team is the owning team of the service (re-derived from training data)", "resolution in {done, cancelled, clarification, cannot reproduce}",
             "urgency / impact / priority use the 5-level vocabulary", "priority == matrix(urgency, impact)", "assignee is a known agent from the training data",
             "exactly one resolution comment appended", "comment is written in the voice of the assignee", "comment is concrete, not generic filler (>=120 chars)",
             "comment refers to the ticket's own content", "comment contains no phone / IBAN pattern"]
    for name in every:
        check(name, not bad.get(name), ("violations: " + ", ".join(bad[name])) if bad.get(name) else f"{len(out)}/{len(out)}")

    # informational statistics
    def first(v):
        v = v if isinstance(v, list) else _lst(v)
        return v[0] if v else None
    svc_changed = sum(first(x["Affected Business or IT Services"]) != first(r["Affected Business or IT Services"]) for x, r in zip(inp, out))
    wt_changed = sum(x["Work type"] != r["Work type"] for x, r in zip(inp, out))
    check("info: services corrected vs. the (deliberately unreliable) input", True, f"{svc_changed} of {len(out)}", hard=False)
    check("info: work types corrected", True, f"{wt_changed} of {len(out)}", hard=False)
    check("info: distinct assignees used", True, f"{len({r['Assignee'] for r in out})} across {len(out)} tickets", hard=False)
    check("info: resolution mix", True, str(dict(collections.Counter(r['Resolution'] for r in out))), hard=False)

    width = max(len(r[0]) for r in rows)
    print(f"input : {inp_path.name}\npred  : {pred_path.name}\n")
    for name, ok, detail, hard in rows:
        print(f"  {'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
    failed = [r for r in rows if r[3] and not r[1]]
    print(f"\n{'ALL HARD CHECKS PASSED' if not failed else str(len(failed)) + ' HARD CHECK(S) FAILED'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
