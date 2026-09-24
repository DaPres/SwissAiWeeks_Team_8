"""Top-k retrieval from the local Chroma store.

Run:  uv run python -m app.rag.retrieve "how do I reset my password"
"""

import sys
from dataclasses import dataclass

from app.rag.store import embed, get_collection


@dataclass
class Chunk:
    text: str
    source: str
    score: float  # cosine similarity, higher is better


def retrieve(query: str, k: int = 3) -> list[Chunk]:
    col = get_collection()
    if col.count() == 0:
        return []
    res = col.query(query_embeddings=embed([query]), n_results=min(k, col.count()))
    return [
        Chunk(text=doc, source=meta["source"], score=1 - dist)
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]


def format_context(chunks: list[Chunk]) -> str:
    return "\n\n---\n\n".join(f"[{c.source}]\n{c.text}" for c in chunks)


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "How do I reset my password?"
    for c in retrieve(q):
        print(f"--- {c.source} (score {c.score:.3f})\n{c.text}\n")
