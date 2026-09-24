"""Run the ticket-history quality analysis + clustering and store the results.

Results are always written to the SQLite store (tables curation_run / curation_clusters / curation_tickets),
which is what the API and the Data curation tab read. Optionally publishes clusters to the knowledge base
and exports flat files for offline analysis (pandas, Excel, notebooks).

Examples (from backend/):
  uv run python -m app.curate                                  # analyse + store, print report
  uv run python -m app.curate --threshold 0.9                  # tighter clusters
  uv run python -m app.curate --publish silver                 # also feed silver+ clusters to knowledge
  uv run python -m app.curate --export out/curation            # also write summary.json, clusters.json, tickets.csv
  LLM_MODE=mock uv run python -m app.curate --db /tmp/cur.db   # offline, separate database

If the API is running, restart it after --publish: each process keeps its own in-memory vector index.
"""
import argparse
import csv
import json
import logging
import os
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m app.curate", description=__doc__.split("\n\n")[0])
    p.add_argument("--threshold", type=float, help="cosine similarity to merge into a cluster (default 0.86 azure / 0.6 mock)")
    p.add_argument("--publish", choices=["gold", "silver", "bronze"], help="publish clusters at or above this level to knowledge")
    p.add_argument("--export", type=Path, metavar="DIR", help="write summary.json, clusters.json and tickets.csv to DIR")
    p.add_argument("--db", type=Path, help="SQLite file (default: DB_PATH / backend/data/knowledge.db)")
    p.add_argument("--top", type=int, default=10, help="clusters to list per level in the report")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.db:  # settings are read at import time, so set before importing the app
        os.environ["DB_PATH"] = str(args.db)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from .config import settings
    from .curation import LEVELS, publish, run_curation, training_tickets
    from .llm import get_llm
    from .store import Store

    store = Store(settings.db_path)
    print(f"LLM mode: {get_llm().mode} · embeddings: {get_llm().embedding_model} · db: {settings.db_path}")
    summary = run_curation(store, args.threshold)
    clusters = store.curation_clusters()
    report(summary, clusters, LEVELS, args.top)

    if args.publish:
        result = publish(store, args.publish)
        print(f"\nPublished {result['published']} clusters ({result['tickets']:,} tickets) at {args.publish}+ → knowledge {result['knowledge']['bySource']}")

    if args.export:
        export(args.export, summary, clusters, store.curation_ticket_rows(), training_tickets())
        print(f"\nExported to {args.export.resolve()}")


def report(summary: dict, clusters: list[dict], levels: list[str], top: int) -> None:
    total = summary["tickets"]
    print(f"\nAnalysed {total:,} tickets → {summary['clusters']} clusters "
          f"(similarity ≥ {summary['threshold']}) in {summary['seconds']}s\n")
    print(f"{'level':<8}{'min':>5}{'tickets':>10}{'share':>8}{'clusters':>10}{'in clusters':>13}")
    for lvl in levels:
        t, c = summary["ticketLevels"][lvl], summary["clusterLevels"][lvl]
        print(f"{lvl:<8}{summary['levelThresholds'][lvl]:>5}{t:>10,}{t / total:>8.1%}{c['clusters']:>10}{c['tickets']:>13,}")
    print("\nBad-data findings (a ticket can have several):")
    for f in summary["flags"]:
        print(f"  {f['count']:>6,}  {f['count'] / total:>6.1%}  {f['label']}")
    for lvl in levels:
        subset = [c for c in clusters if c["level"] == lvl][:top]
        if not subset:
            continue
        print(f"\nTop {lvl} clusters:")
        for c in subset:
            who = c["resolver"].split("@")[0] if c["resolver"] else "-"
            print(f"  #{c['id']:<4}{c['score']:>5.1f}  {c['size']:>5}  {c['service'][:24]:<24}  {who:<16} {c['title'][:70]}")


def export(out: Path, summary: dict, clusters: list[dict], rows: list[dict], history: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    (out / "clusters.json").write_text(json.dumps(clusters, indent=2))
    cluster_by_id = {c["id"]: c for c in clusters}
    with open(out / "tickets.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["idx", "cluster_id", "cluster_level", "cluster_title", "ticket_level", "ticket_score", "flags",
                    "service", "work_type", "summary", "status", "resolution", "assignee", "created"])
        for r in rows:
            t, c = history[r["idx"]], cluster_by_id[r["cluster_id"]]
            w.writerow([r["idx"], r["cluster_id"], c["level"], c["title"], r["level"], r["score"], "|".join(r["flags"]),
                        c["service"], t["Work type"], t["Summary"], t["Status"], t["Resolution"] or "", t["Assignee"], t["Created date"]])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
