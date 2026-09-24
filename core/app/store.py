"""SQLite store for tickets, triage results, analyst decisions and eval runs.

Input:  data/jira.json (corpus load), plus results/decisions written at runtime.
Output: a queryable local DB at data/triagemate.db; also serves open-ticket load for
        assignee balancing and the same-service/recent window for duplicate correlation.
Everything is read-only from the agent's point of view: tools may query, never write.
Failure mode it prevents: holding 20k tickets in memory per request, and losing analyst
decisions (which are the feedback loop and the demo's metrics) when the process restarts.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from app.schemas import Ticket, TriageResult

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "triagemate.db"
JIRA_JSON = ROOT / "data" / "jira.json"
OPEN_STATUSES = ("open", "in progress")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY, summary TEXT, description TEXT, service TEXT, team TEXT,
  entity TEXT, reporter TEXT, assignee TEXT, priority TEXT, urgency TEXT, impact TEXT,
  work_type TEXT, status TEXT, resolution TEXT, created TEXT, resolved TEXT, comments TEXT
);
CREATE INDEX IF NOT EXISTS ix_tickets_service ON tickets(service);
CREATE INDEX IF NOT EXISTS ix_tickets_status  ON tickets(status);
CREATE INDEX IF NOT EXISTS ix_tickets_created ON tickets(created);

CREATE TABLE IF NOT EXISTS results (
  ticket_id TEXT PRIMARY KEY, created_at TEXT, payload TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT, decision TEXT, reason TEXT,
  edit_distance INTEGER, dwell_seconds REAL, edited_text TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS eval_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, created_at TEXT, payload TEXT
);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def _first(v):
    return v[0] if isinstance(v, list) and v else (None if isinstance(v, list) else v)


def load_corpus(con: sqlite3.Connection, src: Path = JIRA_JSON, limit: int | None = None) -> int:
    """Load the challenge dataset. Ids are synthesised (JIRA-00001) — the file has none."""
    rows = json.loads(src.read_text(encoding="utf-8"))[:limit]
    con.executemany(
        """INSERT OR REPLACE INTO tickets VALUES
           (:id,:summary,:description,:service,:team,:entity,:reporter,:assignee,:priority,
            :urgency,:impact,:work_type,:status,:resolution,:created,:resolved,:comments)""",
        [
            {
                "id": f"JIRA-{i + 1:05d}",
                "summary": r["Summary"],
                "description": r["Description"],
                "service": _first(r["Affected Business or IT Services"]),
                "team": _first(r["Service Team(s)"]),
                "entity": _first(r["Business Entity"]),
                "reporter": r.get("Reporter"),
                "assignee": r.get("Assignee"),
                "priority": r.get("Priority"),
                "urgency": r.get("Urgency"),
                "impact": r.get("Impact"),
                "work_type": r.get("Work type"),
                "status": r.get("Status"),
                "resolution": r.get("Resolution"),
                "created": r.get("Created date"),
                "resolved": r.get("Resolution date"),
                "comments": json.dumps(r.get("All Comments", []), ensure_ascii=False),
            }
            for i, r in enumerate(rows)
        ],
    )
    con.commit()
    return len(rows)


def ticket_count(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COUNT(*) AS n FROM tickets").fetchone()["n"]


def get_ticket(con: sqlite3.Connection, ticket_id: str) -> Ticket | None:
    r = con.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    return _to_ticket(r) if r else None


def _to_ticket(r: sqlite3.Row) -> Ticket:
    return Ticket(
        id=r["id"], summary=r["summary"] or "", description=r["description"] or "",
        claimed_service=r["service"], entity=r["entity"], reporter=r["reporter"],
        created=r["created"], status=r["status"], comments=json.loads(r["comments"] or "[]"),
    )


def open_load(con: sqlite3.Connection) -> dict[str, int]:
    """Open/in-progress ticket count per assignee — the input to assignee balancing."""
    q = f"""SELECT assignee, COUNT(*) AS n FROM tickets
            WHERE status IN ({",".join("?" * len(OPEN_STATUSES))}) AND assignee IS NOT NULL
            GROUP BY assignee"""
    return {r["assignee"]: r["n"] for r in con.execute(q, OPEN_STATUSES)}


def find_open_related(
    con: sqlite3.Connection, service: str, created: str | None, window_hours: float, exclude_id: str | None = None
) -> list[Ticket]:
    """Same service, not done, created within +/- window_hours. Duplicate/alert correlation.

    The window is OUR parameter (RELATED_WINDOW_HOURS, default 4) — see README.
    """
    if not service or not created:
        return []
    try:
        t0 = datetime.strptime(created, "%Y-%m-%d %H:%M")
    except ValueError:
        return []
    lo = (t0 - timedelta(hours=window_hours)).strftime("%Y-%m-%d %H:%M")
    hi = (t0 + timedelta(hours=window_hours)).strftime("%Y-%m-%d %H:%M")
    q = f"""SELECT * FROM tickets
            WHERE service = ? AND status IN ({",".join("?" * len(OPEN_STATUSES))})
              AND created BETWEEN ? AND ? AND id != ?
            ORDER BY created LIMIT 20"""
    rows = con.execute(q, (service, *OPEN_STATUSES, lo, hi, exclude_id or "")).fetchall()
    return [_to_ticket(r) for r in rows]


# --- results, decisions, evals ------------------------------------------------------


def save_result(con: sqlite3.Connection, result: TriageResult) -> None:
    con.execute(
        "INSERT OR REPLACE INTO results VALUES (?,?,?)",
        (result.ticket_id, datetime.now().isoformat(timespec="seconds"), result.model_dump_json()),
    )
    con.commit()


def get_result(con: sqlite3.Connection, ticket_id: str) -> TriageResult | None:
    r = con.execute("SELECT payload FROM results WHERE ticket_id = ?", (ticket_id,)).fetchone()
    return TriageResult.model_validate_json(r["payload"]) if r else None


def save_decision(
    con: sqlite3.Connection, ticket_id: str, decision: str, reason: str = "",
    edit_distance: int = 0, dwell_seconds: float = 0.0, edited_text: str = "",
) -> int:
    cur = con.execute(
        "INSERT INTO decisions (ticket_id,decision,reason,edit_distance,dwell_seconds,edited_text,created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (ticket_id, decision, reason, edit_distance, dwell_seconds, edited_text,
         datetime.now().isoformat(timespec="seconds")),
    )
    con.commit()
    return cur.lastrowid


def decision_metrics(con: sqlite3.Connection) -> dict:
    rows = con.execute(
        "SELECT decision, COUNT(*) n, AVG(edit_distance) ed, AVG(dwell_seconds) dw"
        " FROM decisions GROUP BY decision"
    ).fetchall()
    by = {r["decision"]: {"n": r["n"], "avg_edit_distance": r["ed"], "avg_dwell_seconds": r["dw"]} for r in rows}
    total = sum(v["n"] for v in by.values())
    return {
        "total_decisions": total,
        "by_decision": by,
        "approval_rate": (by.get("approve", {}).get("n", 0) / total) if total else None,
    }


def save_eval_run(con: sqlite3.Connection, name: str, payload: dict) -> None:
    con.execute(
        "INSERT INTO eval_runs (name, created_at, payload) VALUES (?,?,?)",
        (name, datetime.now().isoformat(timespec="seconds"), json.dumps(payload, ensure_ascii=False)),
    )
    con.commit()
