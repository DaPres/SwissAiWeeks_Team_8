"""SQLite persistence + in-memory cosine index.

Knowledge items are the vectorised memory of how problems get solved. Sources:
  training - curated clusters of the 20k history (see curation.py), filtered by quality level
  catalog  - one card per service, so services without history are still retrievable
  live     - tickets resolved in this system (the continuous-learning loop)

At hackathon scale (hundreds to low thousands of vectors) a numpy matrix is plenty;
swap `VectorIndex` for Azure AI Search when volumes grow.
"""
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS knowledge (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  service TEXT NOT NULL,
  team TEXT NOT NULL,
  work_type TEXT,
  resolver TEXT,
  title TEXT NOT NULL,
  problem TEXT NOT NULL,
  resolution TEXT,
  occurrences INTEGER NOT NULL DEFAULT 1,
  helpful INTEGER NOT NULL DEFAULT 0,
  ticket_id INTEGER,
  created_at REAL NOT NULL,
  embedding BLOB
);
CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  reporter TEXT,
  user_text TEXT NOT NULL,
  image_descriptions TEXT NOT NULL DEFAULT '[]',
  summary TEXT NOT NULL,
  description TEXT NOT NULL,
  work_type TEXT NOT NULL,
  service TEXT NOT NULL,
  team TEXT NOT NULL,
  assignee TEXT,
  urgency TEXT NOT NULL,
  impact TEXT NOT NULL,
  priority TEXT NOT NULL,
  ai_triage TEXT NOT NULL DEFAULT '{}',
  resolution TEXT,
  resolution_text TEXT,
  resolved_at REAL,
  assist_id TEXT,
  embedding BLOB
);
CREATE TABLE IF NOT EXISTS curation_run (id INTEGER PRIMARY KEY CHECK (id = 1), summary TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS curation_clusters (id INTEGER PRIMARY KEY, level TEXT NOT NULL, service TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS curation_tickets (
  idx INTEGER PRIMARY KEY, cluster_id INTEGER NOT NULL, score REAL NOT NULL, level TEXT NOT NULL, flags TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS curation_tickets_cluster ON curation_tickets(cluster_id);
CREATE TABLE IF NOT EXISTS assists (
  id TEXT PRIMARY KEY,
  created_at REAL NOT NULL,
  user_text TEXT NOT NULL,
  image_descriptions TEXT NOT NULL,
  result TEXT NOT NULL,
  feedback TEXT,
  ticket_id INTEGER
);
"""


@dataclass
class Hit:
    id: str | int
    score: float
    row: dict


class VectorIndex:
    def __init__(self) -> None:
        self.ids: list = []
        self.matrix = np.zeros((0, 0), dtype=np.float32)

    def build(self, rows: list[tuple]) -> None:
        self.ids = [r[0] for r in rows if r[1] is not None]
        vecs = [np.frombuffer(r[1], dtype=np.float32) for r in rows if r[1] is not None]
        self.matrix = np.vstack(vecs) if vecs else np.zeros((0, 0), dtype=np.float32)

    def search(self, q: np.ndarray, k: int) -> list[tuple]:
        if not self.ids or self.matrix.shape[1] != q.shape[0]:
            return []
        scores = self.matrix @ q
        top = np.argsort(-scores)[:k]
        return [(self.ids[i], float(scores[i])) for i in top]


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(knowledge)")}
        for col, typ in (("quality", "REAL"), ("level", "TEXT")):  # added with data curation
            if col not in cols:
                self.db.execute(f"ALTER TABLE knowledge ADD COLUMN {col} {typ}")
        self.lock = threading.RLock()
        self._knowledge_index: VectorIndex | None = None
        self._ticket_index: VectorIndex | None = None

    # ---------------------------------------------------------------- meta
    def get_meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))
            self.db.commit()

    # ---------------------------------------------------------------- knowledge
    def add_knowledge(self, items: list[dict], embeddings: np.ndarray) -> None:
        with self.lock:
            for item, vec in zip(items, embeddings):
                self.db.execute(
                    """INSERT OR REPLACE INTO knowledge
                       (id, source, service, team, work_type, resolver, title, problem, resolution,
                        occurrences, helpful, ticket_id, created_at, quality, level, embedding)
                       VALUES (:id,:source,:service,:team,:work_type,:resolver,:title,:problem,:resolution,
                               :occurrences,:helpful,:ticket_id,:created_at,:quality,:level,:embedding)""",
                    {
                        "id": item.get("id") or f"{item['source']}-{uuid.uuid4().hex[:10]}",
                        "work_type": None, "resolver": None, "resolution": None, "occurrences": 1,
                        "helpful": 0, "ticket_id": None, "created_at": time.time(), "quality": None, "level": None,
                        **item,
                        "embedding": vec.astype(np.float32).tobytes(),
                    },
                )
            self.db.commit()
            self._knowledge_index = None

    def knowledge_rows(self, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        q = f"SELECT * FROM knowledge WHERE id IN ({','.join('?' * len(ids))})"
        return {r["id"]: _row(r) for r in self.db.execute(q, ids)}

    def search_knowledge(self, q: np.ndarray, k: int) -> list[Hit]:
        with self.lock:
            if self._knowledge_index is None:
                self._knowledge_index = VectorIndex()
                self._knowledge_index.build(self.db.execute("SELECT id, embedding FROM knowledge").fetchall())
            raw = self._knowledge_index.search(q, k * 3)
        rows = self.knowledge_rows([i for i, _ in raw])
        hits = []
        for i, s in raw:
            r = rows[i]
            # Learned boost: confirmed-helpful answers and frequently recurring patterns rank slightly higher.
            boost = 1 + 0.04 * np.log1p(r["helpful"]) + 0.01 * np.log1p(r["occurrences"])
            hits.append(Hit(i, s * boost, r))
        hits.sort(key=lambda h: -h.score)
        return hits[:k]

    def mark_helpful(self, ids: list[str]) -> None:
        with self.lock:
            self.db.executemany("UPDATE knowledge SET helpful = helpful + 1 WHERE id=?", [(i,) for i in ids])
            self.db.commit()

    def knowledge_stats(self) -> dict:
        by_source = {r["source"]: r["n"] for r in self.db.execute("SELECT source, COUNT(*) n FROM knowledge GROUP BY source")}
        by_level = {r["level"]: r["n"] for r in self.db.execute("SELECT level, COUNT(*) n FROM knowledge WHERE level IS NOT NULL GROUP BY level")}
        helpful = self.db.execute("SELECT COALESCE(SUM(helpful),0) FROM knowledge").fetchone()[0]
        return {"bySource": by_source, "byLevel": by_level, "total": sum(by_source.values()), "helpfulVotes": helpful,
                "minLevel": self.get_meta("knowledge_min_level")}

    def all_knowledge_for_reembed(self) -> list[dict]:
        return [_row(r) for r in self.db.execute("SELECT * FROM knowledge")]

    def delete_knowledge_source(self, source: str) -> None:
        with self.lock:
            self.db.execute("DELETE FROM knowledge WHERE source=?", (source,))
            self.db.commit()
            self._knowledge_index = None

    # ---------------------------------------------------------------- curation
    def save_curation(self, summary: dict, clusters: list[dict], ticket_rows: list[tuple]) -> None:
        with self.lock:
            self.db.execute("DELETE FROM curation_run")
            self.db.execute("DELETE FROM curation_clusters")
            self.db.execute("DELETE FROM curation_tickets")
            self.db.execute("INSERT INTO curation_run VALUES (1, ?)", (json.dumps(summary),))
            self.db.executemany("INSERT INTO curation_clusters VALUES (?,?,?,?)",
                                [(c["id"], c["level"], c["service"], json.dumps(c)) for c in clusters])
            self.db.executemany("INSERT INTO curation_tickets VALUES (?,?,?,?,?)", ticket_rows)
            self.db.commit()

    def curation_summary(self) -> dict | None:
        row = self.db.execute("SELECT summary FROM curation_run WHERE id=1").fetchone()
        return json.loads(row["summary"]) if row else None

    def curation_clusters(self) -> list[dict]:
        return [json.loads(r["data"]) for r in self.db.execute("SELECT data FROM curation_clusters ORDER BY id")]

    def curation_cluster(self, cluster_id: int) -> dict | None:
        row = self.db.execute("SELECT data FROM curation_clusters WHERE id=?", (cluster_id,)).fetchone()
        return json.loads(row["data"]) if row else None

    def curation_ticket_rows(self) -> list[dict]:
        rows = self.db.execute("SELECT idx, cluster_id, score, level, flags FROM curation_tickets ORDER BY idx")
        return [{"idx": r["idx"], "cluster_id": r["cluster_id"], "score": r["score"], "level": r["level"],
                 "flags": json.loads(r["flags"])} for r in rows]

    def curation_cluster_tickets(self, cluster_id: int, limit: int) -> list[dict]:
        rows = self.db.execute(
            "SELECT idx, score, level, flags FROM curation_tickets WHERE cluster_id=? ORDER BY score DESC, idx LIMIT ?",
            (cluster_id, limit))
        return [{"idx": r["idx"], "score": r["score"], "level": r["level"], "flags": json.loads(r["flags"])} for r in rows]

    # ---------------------------------------------------------------- tickets
    def create_ticket(self, t: dict, embedding: np.ndarray) -> int:
        with self.lock:
            cur = self.db.execute(
                """INSERT INTO tickets (created_at, status, reporter, user_text, image_descriptions, summary, description,
                     work_type, service, team, assignee, urgency, impact, priority, ai_triage, assist_id, embedding)
                   VALUES (?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (time.time(), t.get("reporter"), t["user_text"], json.dumps(t.get("image_descriptions", [])),
                 t["summary"], t["description"], t["work_type"], t["service"], t["team"], t.get("assignee"),
                 t["urgency"], t["impact"], t["priority"], json.dumps(t.get("ai_triage", {})), t.get("assist_id"),
                 embedding.astype(np.float32).tobytes()),
            )
            self.db.commit()
            self._ticket_index = None
            return int(cur.lastrowid)

    def get_ticket(self, ticket_id: int) -> dict | None:
        r = self.db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        return _row(r) if r else None

    def list_tickets(self, status: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM tickets", ()
        if status:
            q, args = q + " WHERE status=?", (status,)
        return [_row(r) for r in self.db.execute(q + " ORDER BY id DESC", args)]

    def update_ticket(self, ticket_id: int, fields: dict) -> None:
        with self.lock:
            cols = ", ".join(f"{k}=?" for k in fields)
            self.db.execute(f"UPDATE tickets SET {cols} WHERE id=?", (*fields.values(), ticket_id))
            self.db.commit()
            self._ticket_index = None

    def search_open_tickets(self, q: np.ndarray, k: int) -> list[Hit]:
        with self.lock:
            if self._ticket_index is None:
                self._ticket_index = VectorIndex()
                self._ticket_index.build(self.db.execute("SELECT id, embedding FROM tickets WHERE status='open'").fetchall())
            raw = self._ticket_index.search(q, k)
        return [Hit(i, s, self.get_ticket(i)) for i, s in raw]

    # ---------------------------------------------------------------- assists
    def save_assist(self, assist_id: str, user_text: str, image_descriptions: list[str], result: dict) -> None:
        with self.lock:
            self.db.execute("INSERT INTO assists VALUES (?,?,?,?,?,NULL,NULL)",
                            (assist_id, time.time(), user_text, json.dumps(image_descriptions), json.dumps(result)))
            self.db.commit()

    def get_assist(self, assist_id: str) -> dict | None:
        r = self.db.execute("SELECT * FROM assists WHERE id=?", (assist_id,)).fetchone()
        return _row(r) if r else None

    def update_assist(self, assist_id: str, **fields) -> None:
        with self.lock:
            cols = ", ".join(f"{k}=?" for k in fields)
            self.db.execute(f"UPDATE assists SET {cols} WHERE id=?", (*fields.values(), assist_id))
            self.db.commit()

    def assist_stats(self) -> dict:
        rows = self.db.execute("SELECT feedback, COUNT(*) n FROM assists GROUP BY feedback").fetchall()
        return {(r["feedback"] or "none"): r["n"] for r in rows}


JSON_COLS = {"image_descriptions", "ai_triage", "result"}


def _row(r: sqlite3.Row) -> dict:
    d = {k: r[k] for k in r.keys() if k != "embedding"}
    for k in JSON_COLS & d.keys():
        d[k] = json.loads(d[k]) if d[k] else d[k]
    return d
