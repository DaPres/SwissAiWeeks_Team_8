"""Measure the duplicate rate across the whole corpus at several similarity thresholds.

Input:  the loaded corpus. For each ticket: same service, inside RELATED_WINDOW_HOURS, and
        text similarity >= threshold.
Output: the fraction of 20,000 tickets that would be flagged duplicate at each threshold.
Above ~5% the gate is too loose - cancelling that much of a real queue is an incident.
Run: uv run python scripts/eval_duplicates.py [sample]
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import store
from app.rag.tickets import find_open_related, text_similarity

SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
THRESHOLDS = [0.5, 0.6, 0.75, 0.85, 0.95]


def main() -> None:
    con = store.connect()
    if store.ticket_count(con) == 0:
        store.load_corpus(con)
    rows = con.execute(
        "SELECT id, summary, description, service, created FROM tickets ORDER BY id LIMIT ?", (SAMPLE,)
    ).fetchall()

    hits = Counter()
    related_any = 0
    for r in rows:
        rel = find_open_related(con, r["service"], r["created"], exclude_id=r["id"])
        if rel:
            related_any += 1
        text = f"{r['description']}\n\n[title] {r['summary']}"
        best = max((text_similarity(text, t.text()) for t in rel), default=0.0)
        for th in THRESHOLDS:
            if best >= th:
                hits[th] += 1

    n = len(rows)
    print(f"sample {n} tickets, window {store.OPEN_STATUSES} within RELATED_WINDOW_HOURS\n")
    print(f"{'GATE':<42}{'FLAGGED':>9}{'RATE':>9}")
    print(f"{'same service + window only (old rule)':<42}{related_any:>9}{related_any / n:>9.1%}")
    for th in THRESHOLDS:
        mark = "  <- current default" if th == 0.75 else ""
        print(f"{'+ text similarity >= ' + str(th):<42}{hits[th]:>9}{hits[th] / n:>9.1%}{mark}")
    print("\nTarget: under ~5%. The old rule cancels far too much of a real queue.")


if __name__ == "__main__":
    main()
