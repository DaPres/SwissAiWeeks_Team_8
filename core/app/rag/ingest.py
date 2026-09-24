"""Chunk + embed every .md/.txt file in data/sample_docs into the local Chroma store.

Run:  uv run python -m app.rag.ingest
Re-running is safe: the collection is rebuilt from scratch each time.
"""

import re
from pathlib import Path

from app.config import DOCS_DIR
from app.rag.store import COLLECTION, embed, get_client, get_collection


def chunk_text(text: str, max_chars: int = 800, overlap: int = 100) -> list[str]:
    """Split on blank lines (paragraphs), then pack paragraphs into ~max_chars chunks."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for para in paras:
        while len(para) > max_chars:  # hard-split giant paragraphs
            chunks.append(para[:max_chars])
            para = para[max_chars - overlap :]
        if cur and len(cur) + len(para) + 2 > max_chars:
            chunks.append(cur)
            cur = cur[-overlap:] + "\n\n" + para if overlap else para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        chunks.append(cur)
    return chunks


def ingest(docs_dir: Path = DOCS_DIR) -> int:
    files = sorted(p for p in docs_dir.rglob("*") if p.suffix.lower() in {".md", ".txt"})
    ids, docs, metas = [], [], []
    for f in files:
        for i, chunk in enumerate(chunk_text(f.read_text(encoding="utf-8"))):
            ids.append(f"{f.relative_to(docs_dir).as_posix()}::{i}")
            docs.append(chunk)
            metas.append({"source": f.name, "chunk": i})

    client = get_client()
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass  # didn't exist yet
    col = get_collection()
    if docs:
        col.add(ids=ids, documents=docs, metadatas=metas, embeddings=embed(docs))
    print(f"Ingested {len(docs)} chunks from {len(files)} files in {docs_dir}")
    return len(docs)


if __name__ == "__main__":
    ingest()
