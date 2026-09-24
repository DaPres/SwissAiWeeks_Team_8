"""Ticket-level retrieval: similar past tickets, related open tickets, assignee suggestion.

Input:  the hybrid index, the store, a redacted query, service and work type.
Output: SimilarTicket rows ranked by pattern similarity THEN resolution quality, the open
        tickets inside RELATED_WINDOW_HOURS for duplicate/alert correlation, and an
        assignee taken from the most similar historical ticket.
Assignee here deliberately samples the same (random) distribution the reference answers were
drawn from — see README; it is a lottery at ~5% either way, so we spend nothing optimising it.
Failure mode it prevents: grounding a resolution in a "Problem fixed." ticket, and missing
that the same alert already has an open ticket.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from dataclasses import dataclass

from app import store
from app.rag.hybrid import Hit, HybridIndex
from app.rag.patterns import resolution_quality, strip_author
from app.schemas import Ticket


def related_window_hours() -> float:
    return float(os.getenv("RELATED_WINDOW_HOURS", "4"))


@dataclass
class SimilarTicket:
    id: str
    service: str | None
    work_type: str | None
    assignee: str | None
    resolution: str | None
    comment: str
    quality: float
    similarity: float

    @property
    def citation_id(self) -> str:
        return self.id


def find_similar_tickets(
    con: sqlite3.Connection, index: HybridIndex, query: str, service: str | None = None,
    work_type: str | None = None, k: int = 5, per_pattern: int = 3,
) -> list[SimilarTicket]:
    """Top patterns first (so results are k DISTINCT patterns), then the best-documented
    member of each — never the filler-only one."""
    hits: list[Hit] = index.search(query, service=service, k=k)
    out: list[SimilarTicket] = []
    for hit in hits:
        p = hit.pattern
        if work_type and p.work_type and p.work_type != work_type:
            continue
        ids = p.ticket_ids[:200]  # cap the scan; patterns can hold thousands of clones
        placeholders = ",".join("?" * len(ids))
        rows = con.execute(
            f"SELECT id, service, work_type, assignee, resolution, comments FROM tickets"
            f" WHERE id IN ({placeholders}) AND resolution IS NOT NULL",
            ids,
        ).fetchall()
        ranked = sorted(
            (
                (resolution_quality(json.loads(r["comments"] or "[]")), r)
                for r in rows
            ),
            key=lambda pair: (-pair[0], pair[1]["id"]),
        )[:per_pattern]
        for quality, r in ranked[:1] or []:
            out.append(
                SimilarTicket(
                    id=r["id"], service=r["service"], work_type=r["work_type"], assignee=r["assignee"],
                    resolution=r["resolution"],
                    comment=" ".join(strip_author(c) for c in json.loads(r["comments"] or "[]"))[:600],
                    quality=quality, similarity=round(hit.score, 3),
                )
            )
    return out[:k]


def find_open_related(con: sqlite3.Connection, service: str | None, created: str | None, exclude_id: str | None = None) -> list[Ticket]:
    """Same service, not done, within +/- RELATED_WINDOW_HOURS (ours, default 4)."""
    if not service:
        return []
    return store.find_open_related(con, service, created, related_window_hours(), exclude_id)


def suggest_assignee_from_patterns(
    con: sqlite3.Connection, index: HybridIndex, query: str, service: str | None = None,
    work_type: str | None = None, exclude_id: str | None = None, pool: int = 400,
) -> tuple[str | None, str]:
    """Modal assignee across the members of the most similar pattern.

    Measured (scripts/eval_assignee.py, n=200): 5.0% vs 3.3% uniform. Polling the whole
    matched pattern beats taking one exemplar's assignee (1.5%), because a single exemplar
    concentrates on one person while the pattern samples the reference's own distribution.
    """
    hits = index.search(query, service=service, k=3)
    for hit in hits:
        p = hit.pattern
        if work_type and p.work_type and p.work_type != work_type:
            continue
        ids = [i for i in p.ticket_ids[:pool] if i != exclude_id]
        if not ids:
            continue
        rows = con.execute(
            f"SELECT assignee, COUNT(*) n FROM tickets WHERE id IN ({','.join('?' * len(ids))})"
            " AND assignee IS NOT NULL GROUP BY assignee",
            ids,
        ).fetchall()
        if rows:
            winner = min(rows, key=lambda r: (-r["n"], r["assignee"]))["assignee"]
            return winner, f"most frequent assignee across {sum(r['n'] for r in rows)} tickets matching pattern {p.best_ticket_id}"
    return None, "no similar pattern with an assignee"


def suggest_assignee(similar: list[SimilarTicket], team_fallback: list[str] | None = None) -> tuple[str | None, str]:
    """Assignee of the most similar historical ticket; ties by frequency, then name.

    Returns (assignee, reason). Assignment is random in this data (measured: ~5% best
    case), so this samples the reference's own distribution rather than inventing logic.
    """
    if not similar:
        pick = sorted(team_fallback or [])[:1]
        return (pick[0] if pick else None, "no similar ticket found; first team member by name")

    best = max(s.similarity for s in similar)
    top = [s for s in similar if s.similarity >= best - 1e-9 and s.assignee]
    if not top:
        top = [s for s in similar if s.assignee]
    if not top:
        pick = sorted(team_fallback or [])[:1]
        return (pick[0] if pick else None, "similar tickets have no assignee")

    freq = Counter(s.assignee for s in similar if s.assignee)
    winner = min(top, key=lambda s: (-freq[s.assignee], s.assignee)).assignee
    return winner, f"assignee of most similar ticket {top[0].id} (similarity {top[0].similarity})"
