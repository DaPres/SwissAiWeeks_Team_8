"""State model (Sec. 6.11): SQLite with tickets / results / decisions / kb_chunks / eval_runs.

Every decision writes a row (ticket id, model outputs, human action, edited text, reason, edit distance, dwell time).
From these rows: acceptance rate, edit distance, throughput, latency percentiles, cost per ticket - and *accepted edits
become few-shot examples* for future drafts of the same pattern (Sec. 6.10: the smallest honest version of "it learns").
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import threading
import time
from pathlib import Path

from .models import Ticket, TriageResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY, raw_text TEXT, redacted_text TEXT, source TEXT, created_at TEXT, status TEXT, ticket_json TEXT);
CREATE TABLE IF NOT EXISTS results (
  ticket_id TEXT PRIMARY KEY, work_type TEXT, service TEXT, team TEXT, assignee TEXT, priority TEXT, urgency TEXT, impact TEXT,
  resolution TEXT, confidence REAL, flags_json TEXT, result_json TEXT, latency_ms REAL, cost_usd REAL, mode TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT, action TEXT, edited_text TEXT, reason TEXT, edit_distance REAL,
  dwell_ms INTEGER, decided_at TEXT);
CREATE TABLE IF NOT EXISTS kb_chunks (id TEXT PRIMARY KEY, article_id TEXT, title TEXT, section TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS eval_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, set_name TEXT, metric TEXT, value REAL, created_at TEXT);
"""


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def normalised_edit_distance(a: str, b: str) -> float:
    n = max(len(a), len(b), 1)
    return round(levenshtein(a, b) / n, 4)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(_SCHEMA)

    # ---- tickets / results ------------------------------------------------
    def save_ticket(self, t: Ticket, redacted_text: str = "") -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO tickets(id, raw_text, redacted_text, source, created_at, status, ticket_json) VALUES (?,?,?,?,?,?,?)",
                (t.id, t.text, redacted_text, t.source, t.created or _now(), t.status or "open", t.model_dump_json()))
            self._db.commit()

    def save_result(self, r: TriageResult) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO results(ticket_id, work_type, service, team, assignee, priority, urgency, impact, resolution, confidence,"
                " flags_json, result_json, latency_ms, cost_usd, mode, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r.ticket_id, r.work_type, r.service, r.team, r.assignee, r.priority, r.urgency, r.impact, r.resolution, r.confidence,
                 r.flags.model_dump_json(), r.model_dump_json(), r.latency_ms, r.cost_usd, r.mode, _now()))
            self._db.commit()

    def get_result(self, ticket_id: str) -> TriageResult | None:
        with self._lock:
            row = self._db.execute("SELECT result_json FROM results WHERE ticket_id=?", (ticket_id,)).fetchone()
        return TriageResult.model_validate_json(row["result_json"]) if row else None

    def get_redacted(self, ticket_id: str) -> str:
        with self._lock:
            row = self._db.execute("SELECT redacted_text FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        return (row["redacted_text"] if row else "") or ""

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        with self._lock:
            row = self._db.execute("SELECT ticket_json FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        return Ticket.model_validate_json(row["ticket_json"]) if row else None

    _PRIO_RANK = {"highest": 0, "high": 1, "medium": 2, "low": 3, "lowest": 4}

    def queue(self, limit: int = 200) -> list[dict]:
        """Priority-sorted list with badges (unclear, mismatch, duplicate, injection, low-confidence) and decision state."""
        with self._lock:
            rows = self._db.execute(
                "SELECT t.id, t.source, t.created_at, t.ticket_json, r.priority, r.service, r.team, r.work_type, r.confidence, r.flags_json, r.resolution, r.assignee,"
                " (SELECT action FROM decisions d WHERE d.ticket_id=t.id ORDER BY d.id DESC LIMIT 1) AS decision"
                " FROM tickets t LEFT JOIN results r ON r.ticket_id=t.id").fetchall()
        out = []
        for r in rows:
            tj = json.loads(r["ticket_json"])
            flags = json.loads(r["flags_json"]) if r["flags_json"] else {}
            out.append({"id": r["id"], "summary": tj.get("summary", ""), "priority": r["priority"], "service": r["service"], "team": r["team"],
                        "work_type": r["work_type"], "confidence": r["confidence"], "flags": [k for k, v in flags.items() if v],
                        "resolution": r["resolution"], "assignee": r["assignee"], "decision": r["decision"], "source": r["source"],
                        "created": tj.get("created") or r["created_at"]})
        out.sort(key=lambda x: (x["decision"] is not None, self._PRIO_RANK.get(x["priority"] or "lowest", 5), -(x["confidence"] or 0)))
        return out[:limit]

    def open_load(self) -> dict[str, int]:
        with self._lock:
            rows = self._db.execute(
                "SELECT r.assignee, COUNT(*) n FROM results r WHERE r.assignee IS NOT NULL AND NOT EXISTS "
                "(SELECT 1 FROM decisions d WHERE d.ticket_id=r.ticket_id) GROUP BY r.assignee").fetchall()
        return {r["assignee"]: r["n"] for r in rows}

    # ---- decisions / feedback loop ---------------------------------------
    def save_decision(self, ticket_id: str, action: str, edited_text: str | None = None, reason: str | None = None,
                      original_text: str | None = None, dwell_ms: int | None = None) -> dict:
        if action not in ("approve", "edit", "reject"):
            raise ValueError("action must be approve | edit | reject")
        dist = normalised_edit_distance(original_text or "", edited_text or "") if action == "edit" and original_text is not None else 0.0
        with self._lock:
            self._db.execute("INSERT INTO decisions(ticket_id, action, edited_text, reason, edit_distance, dwell_ms, decided_at) VALUES (?,?,?,?,?,?,?)",
                             (ticket_id, action, edited_text, reason, dist, dwell_ms, _now()))
            self._db.commit()
        return {"ticket_id": ticket_id, "action": action, "edit_distance": dist}

    def approved_examples(self, service: str, work_type: str, limit: int = 2) -> list[str]:
        """Accepted (approved as-is or edited) draft texts for the same service + work type, newest first."""
        with self._lock:
            rows = self._db.execute(
                "SELECT d.action, d.edited_text, r.result_json FROM decisions d JOIN results r ON r.ticket_id=d.ticket_id "
                "WHERE d.action IN ('approve','edit') AND r.service=? AND r.work_type=? ORDER BY d.id DESC LIMIT 20", (service, work_type)).fetchall()
        out = []
        for row in rows:
            if row["action"] == "edit" and row["edited_text"]:
                out.append(row["edited_text"])
            else:
                res = json.loads(row["result_json"])
                txt = ((res.get("draft") or {}).get("text") or "").strip()
                if txt and txt != "INSUFFICIENT_EVIDENCE":
                    out.append(txt)
            if len(out) >= limit:
                break
        return out

    # ---- metrics ----------------------------------------------------------
    def metrics(self) -> dict:
        with self._lock:
            dec = self._db.execute("SELECT action, edit_distance, dwell_ms FROM decisions").fetchall()
            res = self._db.execute("SELECT latency_ms, cost_usd, confidence, mode, flags_json, priority FROM results").fetchall()
        n_dec = len(dec)
        acc = sum(1 for d in dec if d["action"] == "approve")
        edited = [d["edit_distance"] for d in dec if d["action"] == "edit"]
        lat = sorted(r["latency_ms"] for r in res if r["latency_ms"] is not None)

        def pct(p):
            return round(lat[min(len(lat) - 1, int(p * len(lat)))], 1) if lat else None
        flags = {"unclear": 0, "mismatch": 0, "duplicate": 0, "injection": 0, "low_confidence": 0}
        for r in res:
            f = json.loads(r["flags_json"] or "{}")
            for k in flags:
                flags[k] += 1 if f.get(k) else 0
        return {
            "tickets_triaged": len(res),
            "decisions": n_dec,
            "acceptance_rate": round(acc / n_dec, 3) if n_dec else None,
            "accepted_as_is": acc, "edited": len(edited), "rejected": sum(1 for d in dec if d["action"] == "reject"),
            "mean_edit_distance": round(statistics.mean(edited), 3) if edited else None,
            "latency_ms_p50": pct(0.5), "latency_ms_p95": pct(0.95),
            "mean_cost_usd": round(statistics.mean(r["cost_usd"] or 0 for r in res), 6) if res else None,
            "mean_confidence": round(statistics.mean(r["confidence"] or 0 for r in res), 3) if res else None,
            "mean_dwell_ms": round(statistics.mean(d["dwell_ms"] for d in dec if d["dwell_ms"]), 0) if any(d["dwell_ms"] for d in dec) else None,
            "flags": flags,
            "modes": {m: sum(1 for r in res if r["mode"] == m) for m in {r["mode"] for r in res}},
        }

    # ---- eval runs / kb ---------------------------------------------------
    def save_eval(self, run_id: str, set_name: str, metrics: dict[str, float]) -> None:
        with self._lock:
            for k, v in metrics.items():
                if isinstance(v, (int, float)):
                    self._db.execute("INSERT INTO eval_runs(run_id, set_name, metric, value, created_at) VALUES (?,?,?,?,?)", (run_id, set_name, k, float(v), _now()))
            self._db.commit()

    def index_kb(self, docs) -> None:
        with self._lock:
            for d in docs:
                self._db.execute("INSERT OR REPLACE INTO kb_chunks(id, article_id, title, section, text) VALUES (?,?,?,?,?)",
                                 (d.id, d.meta.get("article"), d.title, d.meta.get("section"), d.text))
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()
