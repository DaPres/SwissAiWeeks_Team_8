"""Measure assignee prediction against baselines. Timeboxed: run once, record, move on.

Input:  the loaded corpus; a random sample of tickets held out as queries.
Output: hit rate for uniform / modal-per-service / modal-per-service+work-type / our
        similar-ticket method.
Assignment is random in this data, so every method lands near the ~3-6% floor. The point is
to document that honestly, not to optimise it.
Run: uv run python scripts/eval_assignee.py [n]
"""

import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import store
from app.rag.hybrid import HybridIndex
from app.rag.tickets import find_similar_tickets, suggest_assignee, suggest_assignee_from_patterns

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200


def main() -> None:
    con = store.connect()
    if store.ticket_count(con) == 0:
        store.load_corpus(con)
    rows = con.execute("SELECT id, summary, description, service, work_type, assignee FROM tickets").fetchall()
    random.seed(7)
    sample = random.sample(rows, min(N, len(rows)))
    sample_ids = {r["id"] for r in sample}

    by_service, by_service_wt, roster = defaultdict(Counter), defaultdict(Counter), Counter()
    for r in rows:
        if r["id"] in sample_ids or not r["assignee"]:
            continue  # held out
        by_service[r["service"]][r["assignee"]] += 1
        by_service_wt[(r["service"], r["work_type"])][r["assignee"]] += 1
        roster[r["assignee"]] += 1

    index = HybridIndex.from_store(con)
    hits = Counter()
    for r in sample:
        truth = r["assignee"]
        query = f"{r['summary']}. {r['description']}"
        if by_service[r["service"]]:
            hits["modal_per_service"] += by_service[r["service"]].most_common(1)[0][0] == truth
        if by_service_wt[(r["service"], r["work_type"])]:
            hits["modal_per_service_worktype"] += by_service_wt[(r["service"], r["work_type"])].most_common(1)[0][0] == truth
        sims = [s for s in find_similar_tickets(con, index, query, service=r["service"], work_type=r["work_type"], k=5)
                if s.id != r["id"]]
        who, _ = suggest_assignee(sims)
        hits["similar_ticket exemplar"] += who == truth
        who2, _ = suggest_assignee_from_patterns(con, index, query, service=r["service"], work_type=r["work_type"], exclude_id=r["id"])
        hits["similar_pattern modal (ours)"] += who2 == truth

    n = len(sample)
    print(f"sample {n} tickets, roster {len(roster)} assignees\n")
    print(f"{'METHOD':<32}{'HIT RATE':>10}")
    print(f"{'uniform random (1/roster)':<32}{1 / max(len(roster), 1):>9.1%}")
    for k, v in hits.most_common():
        print(f"{k:<32}{v / n:>9.1%}")
    print("\nAssignment is random in this data: every method sits at the floor. Documented, not optimised.")


if __name__ == "__main__":
    main()
