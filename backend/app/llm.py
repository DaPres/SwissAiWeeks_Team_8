"""LLM access through Azure AI Foundry (OpenAI v1-compatible endpoint).

`MockLLM` keeps the whole system runnable offline (dev, tests, demos without keys):
hashed bag-of-words embeddings and caller-supplied heuristic fallbacks instead of chat calls.
"""
import hashlib
import json
import logging
import math
import re
from collections.abc import Callable
from typing import Any, Protocol

import numpy as np

from .config import settings

log = logging.getLogger(__name__)

IMAGE_PROMPT = (
    "You help an IT service desk at a pan-European asset manager. Describe this screenshot/photo so a support "
    "agent can triage it without seeing it. Include: the application or screen shown, any error messages and codes "
    "verbatim, job/host/queue/file identifiers, timestamps, amounts, and what looks wrong. Be factual and concise; "
    "do not guess beyond what is visible."
)


class LLM(Protocol):
    mode: str
    embedding_model: str

    def embed(self, texts: list[str]) -> np.ndarray: ...
    def describe_image(self, data_url: str, context: str = "") -> str: ...
    def complete_json(self, system: str, user: str, schema: dict, name: str,
                      fallback: Callable[[], dict]) -> dict: ...
    def complete_text(self, system: str, user: str, fallback: Callable[[], str]) -> str: ...


def _normalise(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return (m / norms).astype(np.float32)


class FoundryLLM:
    mode = "azure"

    def __init__(self) -> None:
        from openai import OpenAI

        if settings.foundry_api_key:
            api_key: Any = settings.foundry_api_key
        else:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            api_key = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
        self.client = OpenAI(base_url=settings.foundry_endpoint, api_key=api_key)
        self.embedding_model = f"azure:{settings.embedding_deployment}"

    def embed(self, texts: list[str]) -> np.ndarray:
        out: list[list[float]] = []
        for i in range(0, len(texts), 64):
            resp = self.client.embeddings.create(model=settings.embedding_deployment, input=texts[i:i + 64])
            out.extend(d.embedding for d in resp.data)
        return _normalise(np.array(out, dtype=np.float32))

    def describe_image(self, data_url: str, context: str = "") -> str:
        prompt = IMAGE_PROMPT + (f"\n\nThe user wrote: {context[:1500]}" if context else "")
        resp = self.client.chat.completions.create(
            model=settings.vision_deployment,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}],
        )
        return (resp.choices[0].message.content or "").strip()

    def complete_json(self, system: str, user: str, schema: dict, name: str,
                      fallback: Callable[[], dict]) -> dict:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            resp = self.client.chat.completions.create(
                model=settings.chat_deployment,
                messages=messages,
                response_format={"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}},
            )
        except Exception as e:  # some Foundry models only support json_object
            log.warning("json_schema not accepted (%s); retrying with json_object", e)
            messages[0]["content"] += "\n\nReply with a single JSON object matching this schema:\n" + json.dumps(schema)
            resp = self.client.chat.completions.create(
                model=settings.chat_deployment, messages=messages, response_format={"type": "json_object"},
            )
        return json.loads(resp.choices[0].message.content or "{}")

    def complete_text(self, system: str, user: str, fallback: Callable[[], str]) -> str:
        resp = self.client.chat.completions.create(
            model=settings.chat_deployment,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return (resp.choices[0].message.content or "").strip()


class MockLLM:
    """Deterministic offline stand-in. Retrieval quality ~ keyword search."""

    mode = "mock"
    embedding_model = "mock:hash-1024"
    DIM = 1024
    _token = re.compile(r"[a-z0-9_]+")
    _stop = set("the a an and or of to for in on is are was were be by with from that this it as at its not but has have".split())

    def embed(self, texts: list[str]) -> np.ndarray:
        m = np.zeros((len(texts), self.DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            toks = [w for w in self._token.findall(t.lower()) if w not in self._stop and len(w) > 2]
            for w in toks + [a + "_" + b for a, b in zip(toks, toks[1:])]:
                h = int(hashlib.md5(w.encode()).hexdigest(), 16)
                m[i, h % self.DIM] += 1.0 if (h >> 64) & 1 else -1.0
            m[i] = np.sign(m[i]) * np.log1p(np.abs(m[i]))
        return _normalise(m)

    def describe_image(self, data_url: str, context: str = "") -> str:
        size_kb = math.ceil(len(data_url) * 3 / 4 / 1024)
        return f"[mock mode] Attached image (~{size_kb} KB) not analysed; configure AZURE_FOUNDRY_ENDPOINT for vision."

    def complete_json(self, system: str, user: str, schema: dict, name: str,
                      fallback: Callable[[], dict]) -> dict:
        return fallback()

    def complete_text(self, system: str, user: str, fallback: Callable[[], str]) -> str:
        return fallback()


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = FoundryLLM() if settings.llm_mode == "azure" else MockLLM()
        log.info("LLM mode: %s (%s)", _llm.mode, _llm.embedding_model)
    return _llm
