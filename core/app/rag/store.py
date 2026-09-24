"""Shared Chroma collection + sentence-transformers embedder (lazy, cached)."""

import os
from functools import lru_cache

import chromadb
from sentence_transformers import SentenceTransformer

from app.config import CHROMA_DIR, load_env

COLLECTION = "support_kb"


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    load_env()
    return SentenceTransformer(os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))


def embed(texts: list[str]) -> list[list[float]]:
    return get_embedder().encode(texts, normalize_embeddings=True).tolist()


@lru_cache(maxsize=1)
def get_client() -> chromadb.ClientAPI:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_collection():
    return get_client().get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
