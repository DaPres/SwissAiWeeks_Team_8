"""Offline eval of the deterministic spine over the whole dataset — no model, no network.

Input:  data/jira.json, bucketed by its 11 text templates (the ground truth we have).
Output: printed table — quality-gate flag rates per ticket class, and the deterministic
        classifier fallback's service accuracy against the dataset's own service field.
Run:    uv run python scripts/eval_spine.py
Failure mode it prevents: shipping gates that look right on 6 unit tests but fire on the
wrong 40% of the queue; this is the regression check for stages 2-3.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run without installing

from app.classify import _fallback
from app.quality import assess
from app.safety import screen
from app.schemas import Ticket

ROOT = Path(__file__).resolve().parent.parent


def category(desc: str) -> str:
    d = desc.lower()
    if "automated monitoring alert" in d:
        return "automated alert"
    if "third party" in d or "external party" in d:
        return "external email"
    if "title suggests" in d or "not aligned with the expected" in d or "unclear" in d:
        return "trap"
    return "normal"


def main() -> None:
    rows = json.loads((ROOT / "data" / "jira.json").read_text(encoding="utf-8"))
    per = defaultdict(Counter)
    svc_ok = Counter()
    svc_n = Counter()
    inj = 0

    for i, r in enumerate(rows):
        cat = category(r["Description"])
        ticket = Ticket(
            id=f"JIRA-{i + 1:05d}", summary=r["Summary"], description=r["Description"],
            claimed_service=r["Affected Business or IT Services"][0], entity=r["Business Entity"][0],
        )
        rep = screen(ticket.text(), names=[r.get("Reporter") or "", r.get("Assignee") or ""])
        inj += bool(rep.injection)

        q = assess(ticket)
        per[cat]["n"] += 1
        per[cat]["unclear"] += q.unclear
        per[cat]["mismatch"] += q.title_mismatch
        per[cat]["not_actionable"] += not q.actionable

        guess = _fallback(ticket, q).service
        svc_n[cat] += 1
        svc_ok[cat] += guess == ticket.claimed_service

    print(f"{'CLASS':<16}{'N':>7}{'unclear':>10}{'mismatch':>10}{'blocked':>9}   fallback service acc.")
    for cat in ("automated alert", "external email", "trap", "normal"):
        c = per[cat]
        n = c["n"] or 1
        print(f"{cat:<16}{c['n']:>7}{c['unclear'] / n:>9.1%}{c['mismatch'] / n:>10.1%}"
              f"{c['not_actionable'] / n:>9.1%}   {svc_ok[cat] / (svc_n[cat] or 1):>6.1%}")

    total = sum(per[c]["n"] for c in per)
    flagged = sum(per[c]["unclear"] + per[c]["mismatch"] for c in per)
    print(f"\ntotal tickets {total}, flagged by a quality gate {flagged} ({flagged / total:.1%})")
    print(f"false-positive injection flags on real tickets: {inj} ({inj / total:.2%})")
    print("(Injection should be ~0 here: the corpus contains no attacks. The attack cases live in tests.)")


if __name__ == "__main__":
    main()
