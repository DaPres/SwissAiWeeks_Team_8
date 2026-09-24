"""Dry run: the full pipeline over N random TRAINING tickets, against the real providers.

Input:  the loaded corpus; a seeded random sample (default 20).
Output: the 7 graded fields for the first 3, the resolution-status distribution, mean
        comment length vs the training comments, provider/latency stats, and a JSON dump.
Results are cached by ticket id + task, so a re-run costs nothing and is reproducible.
Run: uv run python scripts/dry_run.py [n]
"""

import json
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import store
from app.pipeline import triage
from app.rag.hybrid import HybridIndex
from app.rag.patterns import strip_author

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
OUT = Path(__file__).resolve().parent.parent / "docs" / "dry_run.json"


def main() -> None:
    con = store.connect()
    if store.ticket_count(con) == 0:
        store.load_corpus(con)
    index = HybridIndex.from_store(con)

    rows = con.execute("SELECT id FROM tickets").fetchall()
    random.seed(11)
    ids = [r["id"] for r in random.sample(rows, N)]

    results, timings = [], []
    for i, tid in enumerate(ids, 1):
        ticket = store.get_ticket(con, tid)
        t0 = time.perf_counter()
        try:
            r = triage(ticket, con, index)
        except Exception as e:  # a dry run must report, not crash
            print(f"[{i}/{N}] {tid} FAILED: {type(e).__name__}: {e}")
            continue
        timings.append(time.perf_counter() - t0)
        results.append(r)
        store.save_result(con, r)
        print(f"[{i}/{N}] {tid} -> {r.graded.priority.value:<7} {r.graded.resolution.value:<16} "
              f"conf={r.confidence:<5} {timings[-1]:.1f}s")

    if not results:
        print("no results")
        return

    print("\n" + "=" * 78 + "\nTHREE FULL RESULTS (the 7 graded fields)\n" + "=" * 78)
    for r in results[:3]:
        t = store.get_ticket(con, r.ticket_id)
        print(f"\n--- {r.ticket_id}  (training labels: service={t.claimed_service})")
        print(f"    Summary    : {t.summary[:90]}")
        print(f"    Description: {t.description[:140]}...")
        g = r.graded
        print(f"  1 Work type  : {g.work_type.value}")
        print(f"  2 Service    : {g.service}")
        print(f"  3 Team       : {g.team}")
        print(f"  4 Assignee   : {g.assignee}")
        print(f"  5 Priority   : {g.priority.value}   (urgency={r.urgency.value.value}, impact={r.impact.value.value})")
        print(f"      reason   : {r.priority_reason}")
        print(f"      evidence : urgency quote: {r.urgency.quote[:90]!r}")
        print(f"  6 Resolution : {g.resolution.value}")
        print(f"  7 Comment    : {g.resolution_comment}")
        print(f"    confidence : {r.confidence}   flags: {', '.join(r.flags.badges()) or 'none'}")
        print(f"    citations  : {', '.join(c.id for c in r.citations) or 'none'}")
        print(f"    trace      : {len(r.trace)} steps, "
              f"{sum(s.latency_ms for s in r.trace) / 1000:.1f}s total")

    print("\n" + "=" * 78 + "\nDISTRIBUTIONS\n" + "=" * 78)
    res_dist = Counter(r.graded.resolution.value for r in results)
    for k, v in res_dist.most_common():
        print(f"  resolution {k:<18} {v:>3}  {v / len(results):>6.1%}")
    print()
    for k, v in Counter(r.graded.priority.value for r in results).most_common():
        print(f"  priority   {k:<18} {v:>3}  {v / len(results):>6.1%}")
    print()
    flag_counts = Counter(f for r in results for f in r.flags.badges())
    print(f"  flags: {dict(flag_counts) or 'none'}")
    print(f"  mean confidence: {statistics.mean(r.confidence for r in results):.3f}")
    print(f"  below floor      : {sum(1 for r in results if r.confidence < 0.6)}/{len(results)}")

    ours = [len(r.graded.resolution_comment) for r in results]
    train = [len(strip_author(c)) for row in con.execute("SELECT comments FROM tickets LIMIT 4000")
             for c in json.loads(row["comments"] or "[]")]
    print("\n" + "=" * 78 + "\nCOMMENT LENGTH vs TRAINING\n" + "=" * 78)
    print(f"  ours     : mean {statistics.mean(ours):>6.1f}  median {statistics.median(ours):>6.1f}  "
          f"min {min(ours)}  max {max(ours)}")
    print(f"  training : mean {statistics.mean(train):>6.1f}  median {statistics.median(train):>6.1f}  "
          f"min {min(train)}  max {max(train)}")
    cited = sum(1 for r in results if "[" in r.graded.resolution_comment)
    print(f"  comments carrying a citation id: {cited}/{len(results)}")

    providers = Counter(s.detail.split("source=")[-1].rstrip(")") for r in results for s in r.trace if s.step == "classify")
    print(f"\n  classify sources: {dict(providers)}")
    print(f"  wall time: mean {statistics.mean(timings):.1f}s per ticket, {sum(timings):.0f}s total")

    OUT.write_text(json.dumps([r.model_dump(mode="json") for r in results], indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
