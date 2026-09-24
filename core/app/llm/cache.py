"""On-disk cache for model results, keyed by ticket id + task (+ model + prompt hash).

Input:  ticket id, task name, model/prompt fingerprint.
Output: the stored JSON payload, or None. Writes are atomic-ish (write then replace).
Re-running a batch must not re-call a provider for tickets already processed: this is the
Friday-morning protection when 200 people hit the same endpoints, and it makes the demo
reproducible with the network unplugged.
Failure mode it prevents: burning rate limit and money re-deriving identical answers, and a
demo that cannot run twice.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = Path(os.getenv("LLM_CACHE_DIR", str(ROOT / "data" / "llm_cache")))


def enabled() -> bool:
    return os.getenv("LLM_CACHE", "1") not in {"0", "false", "no"}


def key(ticket_id: str, task: str, fingerprint: str = "") -> str:
    digest = hashlib.sha256(f"{ticket_id}|{task}|{fingerprint}".encode()).hexdigest()[:24]
    safe_ticket = "".join(c for c in ticket_id if c.isalnum() or c in "-_")[:40] or "no-id"
    return f"{safe_ticket}.{task}.{digest}"


def path_for(cache_key: str) -> Path:
    return CACHE_DIR / f"{cache_key}.json"


def get(cache_key: str) -> dict | None:
    if not enabled():
        return None
    p = path_for(cache_key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None  # a corrupt cache entry must never break a run


def put(cache_key: str, payload: dict) -> None:
    if not enabled():
        return
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path_for(cache_key).with_suffix(".tmp")
        tmp.write_text(json.dumps({**payload, "cached_at": time.time()}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path_for(cache_key))
    except OSError:
        pass  # caching is an optimisation, never a hard dependency


def clear() -> int:
    if not CACHE_DIR.exists():
        return 0
    n = 0
    for f in CACHE_DIR.glob("*.json"):
        f.unlink(missing_ok=True)
        n += 1
    return n
