"""Template signatures and resolution quality — the two things that make this corpus usable.

Input:  tickets from the store (20,000 rows that are really 173 texts / 11 templates).
Output: Pattern groups (one per template+service) and a 0-1 quality score per ticket's
        resolution comments.
Dedupe is by SIGNATURE (service/entity/number masked), not exact string, so k results are
k genuinely different resolution patterns. Quality ranking pushes "Problem fixed." (5,851
occurrences; 20.6% of tickets are filler-only) below substantive notes.
Failure mode it prevents: retrieval returning five copies of one sentence, and grounding a
resolution comment in filler.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from functools import lru_cache

from app import routing

FILLER = {
    "problem fixed.",
    "resolution recorded: access updated.",
    "resolution recorded: service restored.",
}
# A comment is substantive if it says WHAT was done, not just that something was done.
SPECIFIC_CUES = ("validated", "checked", "confirmed", "assessment", "catalogue", "restored", "workflow", "escalat", "reviewed")


@lru_cache(maxsize=1)
def _masks() -> tuple[list[str], list[str]]:
    services = sorted(routing.services(), key=len, reverse=True)
    entities = ["Switzerland", "France", "Luxembourg", "Germany", "Nordics"]
    return services, sorted(entities, key=len, reverse=True)


def signature(text: str) -> str:
    """Mask service names, entities and numbers so boilerplate collapses to one key."""
    services, entities = _masks()
    for s in services:
        text = text.replace(s, "<SERVICE>")
    for e in entities:
        text = text.replace(e, "<ENTITY>")
    text = re.sub(r"\d+", "<N>", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def strip_author(comment: str) -> str:
    """Comments are stored as 'someone@intcom.com: text' — the address is PII."""
    return comment.split(": ", 1)[-1].strip() if ": " in comment[:60] else comment.strip()


def resolution_quality(comments: list[str]) -> float:
    """0-1. Filler-only scores ~0; long, specific, multi-step trails score high."""
    bodies = [strip_author(c) for c in comments if c.strip()]
    if not bodies:
        return 0.0
    substantive = [b for b in bodies if b.lower() not in FILLER]
    if not substantive:
        return 0.05
    longest = max(len(b) for b in substantive)
    cues = sum(1 for b in substantive for cue in SPECIFIC_CUES if cue in b.lower())
    score = (
        0.45 * min(len(substantive) / 3, 1.0)        # a real investigation trail
        + 0.35 * min(longest / 120, 1.0)             # detail, capped at the median length
        + 0.20 * min(cues / 3, 1.0)                  # says what was actually checked
    )
    return round(min(score, 1.0), 3)


@dataclass
class Pattern:
    """One resolution pattern: a template signature for a given service."""

    key: str
    signature: str
    service: str | None
    work_type: str | None
    text: str                       # representative text, for BM25 and embedding
    ticket_ids: list[str] = field(default_factory=list)
    best_ticket_id: str | None = None
    best_comment: str = ""
    best_quality: float = 0.0
    resolutions: dict[str, int] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.ticket_ids)


def build_patterns(con: sqlite3.Connection, limit: int | None = None) -> list[Pattern]:
    """Group the corpus into (signature, service, work_type) patterns, keeping the
    highest-quality resolved exemplar of each as the citation target."""
    q = "SELECT id, summary, description, service, work_type, resolution, comments FROM tickets"
    if limit:
        q += f" LIMIT {int(limit)}"
    import json as _json

    groups: dict[str, Pattern] = {}
    for r in con.execute(q):
        sig = signature(f"{r['description']} {r['summary']}")
        key = f"{sig}|{r['service']}|{r['work_type']}"
        p = groups.get(key)
        if p is None:
            p = groups[key] = Pattern(
                key=key, signature=sig, service=r["service"], work_type=r["work_type"],
                text=f"{r['summary']}. {r['description']}",
            )
        p.ticket_ids.append(r["id"])
        if r["resolution"]:
            p.resolutions[r["resolution"]] = p.resolutions.get(r["resolution"], 0) + 1
        comments = _json.loads(r["comments"] or "[]")
        quality = resolution_quality(comments)
        # Prefer a resolved ticket with a substantive trail as the pattern's exemplar.
        rank = (quality + (0.15 if r["resolution"] == "done" else 0.0), len(comments))
        best_rank = (p.best_quality + (0.15 if p.best_comment and "done" in p.resolutions else 0.0), 0)
        if p.best_ticket_id is None or rank > best_rank:
            p.best_ticket_id = r["id"]
            p.best_quality = quality
            p.best_comment = " ".join(strip_author(c) for c in comments)[:600]
    return list(groups.values())
