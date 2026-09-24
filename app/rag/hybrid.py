"""Hybrid retrieval: 0.6 dense cosine + 0.4 BM25 over deduped resolution patterns.

Input:  a query (redacted ticket text) and optionally a service to filter by.
Output: Hit objects carrying score, the citation id (an exemplar JIRA ticket id) and a
        snippet — top 20 raw, service-filtered, deduped by signature, down to top 5.
Dense half is Chroma + sentence-transformers (kept from the scaffold); BM25 is rank_bm25.
A score floor reports low confidence instead of returning a bad match.
Failure mode it prevents: five copies of one sentence presented as five sources, and
confident answers built on retrieval that matched nothing.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi

from app.rag.patterns import Pattern, build_patterns
from app.rag.store import embed

SCORE_FLOOR = 0.35  # below this, retrieval reports "nothing reliable found"
DENSE_W, BM25_W = 0.6, 0.4


def tokenize(text: str) -> list[str]:
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(t) > 1]


@dataclass
class Hit:
    pattern: Pattern
    score: float
    dense: float
    bm25: float

    @property
    def citation_id(self) -> str:
        return self.pattern.best_ticket_id or self.pattern.key[:24]

    @property
    def snippet(self) -> str:
        return self.pattern.text[:300]


class HybridIndex:
    """Built once at startup over ~200 deduped patterns, so it is cheap to rebuild."""

    def __init__(self, patterns: list[Pattern]):
        self.patterns = patterns
        self._bm25 = BM25Okapi([tokenize(p.text) for p in patterns]) if patterns else None
        self._vectors = np.array(embed([p.text for p in patterns])) if patterns else np.zeros((0, 1))

    @classmethod
    def from_store(cls, con: sqlite3.Connection, limit: int | None = None) -> "HybridIndex":
        return cls(build_patterns(con, limit))

    def search(self, query: str, service: str | None = None, k: int = 5, top_n: int = 20) -> list[Hit]:
        if not self.patterns:
            return []
        q_vec = np.array(embed([query])[0])
        dense = self._vectors @ q_vec  # vectors are normalised, so this is cosine
        raw_bm25 = np.array(self._bm25.get_scores(tokenize(query)))
        top = raw_bm25.max() or 1.0
        bm25 = raw_bm25 / top  # scale to 0-1 so the 0.6/0.4 blend is meaningful

        scored = [
            Hit(p, float(DENSE_W * d + BM25_W * b), float(d), float(b))
            for p, d, b in zip(self.patterns, dense, bm25)
        ]
        scored.sort(key=lambda h: -h.score)
        pool = scored[:top_n]

        if service:
            filtered = [h for h in pool if h.pattern.service == service]
            pool = filtered or pool  # keep something rather than nothing; caller sees the score

        seen: set[str] = set()
        out: list[Hit] = []
        for h in pool:
            if h.pattern.signature in seen:  # dedupe by TEMPLATE, not exact string
                continue
            seen.add(h.pattern.signature)
            out.append(h)
            if len(out) == k:
                break
        return out


def retrieval_confidence(hits: list[Hit]) -> float:
    """0-1 confidence in the retrieval itself: best score, tempered by how many distinct
    patterns cleared the floor. Feeds the 0.4 retrieval term of the overall confidence."""
    if not hits:
        return 0.0
    best = hits[0].score
    if best < SCORE_FLOOR:
        return round(max(best, 0.0) * 0.5, 3)
    clear = sum(1 for h in hits if h.score >= SCORE_FLOOR)
    return round(min(best * (0.8 + 0.2 * math.log1p(clear)), 1.0), 3)
