"""LLM access through OpenAI-compatible endpoints: Azure AI Foundry, OpenAI and Swisscom Apertus.

`MockLLM` keeps the whole system runnable offline (dev, tests, demos without keys):
hashed bag-of-words embeddings and caller-supplied heuristic fallbacks instead of chat calls.
"""
import hashlib
import json
import logging
import math
import random
import re
import threading
import time
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
    mode: str  # provider id: "foundry", "openai", "apertus" or "mock"
    label: str
    chat_model: str
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


class Embedder(Protocol):
    embedding_model: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


class OpenAIEmbedder:
    """Embeddings through an OpenAI-compatible endpoint (Foundry or OpenAI)."""

    def __init__(self, client: Any, model: str, prefix: str) -> None:
        self.client = client
        self.model = model
        self.embedding_model = f"{prefix}:{model}"

    def embed(self, texts: list[str]) -> np.ndarray:
        out: list[list[float]] = []
        for i in range(0, len(texts), 64):
            resp = self.client.embeddings.create(model=self.model, input=texts[i:i + 64])
            out.extend(d.embedding for d in resp.data)
        return _normalise(np.array(out, dtype=np.float32))


def _retry_after(e: Exception) -> float | None:
    """Seconds from a 429's Retry-After header, if the server sent a usable one."""
    headers = getattr(getattr(e, "response", None), "headers", None) or {}
    try:
        value = float(headers.get("retry-after", ""))
    except ValueError:
        return None
    return value if 0 < value <= 120 else None


def _parse_json(content: str) -> dict:
    """Models without structured output sometimes wrap the object in prose or a ```json fence."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(content[start:end + 1])


class ChatLLM:
    """Chat/vision through an OpenAI-compatible endpoint. Embeddings are delegated to the shared
    embedder so the knowledge base vectors stay comparable whichever chat provider is selected."""

    def __init__(self, mode: str, label: str, client: Any, chat_model: str, vision_model: str | None,
                 embedder: Embedder, vision_fallback: "LLM | None" = None, max_concurrency: int = 0) -> None:
        self.mode = mode
        self.label = label
        self.client = client
        self.chat_model = chat_model
        self.vision_model = vision_model
        self.embedder = embedder
        self.vision_fallback = vision_fallback
        # Caps in-flight calls across all threads (eval workers, parallel runs, users); 0 = unlimited.
        self.slots = threading.BoundedSemaphore(max_concurrency) if max_concurrency > 0 else None

    def _chat(self, **kwargs: Any) -> Any:
        """chat.completions.create with rate-limit handling: the SDK's own two quick retries are not enough for
        per-minute quotas (Apertus answers 429 "rate_limit_reached_error"), so back off honouring Retry-After."""
        from openai import RateLimitError

        for attempt in range(settings.rate_limit_retries + 1):
            if self.slots:
                self.slots.acquire()
            try:
                return self.client.chat.completions.create(**kwargs)
            except RateLimitError as e:
                if attempt == settings.rate_limit_retries:
                    raise
                delay = _retry_after(e) or min(60.0, 2.0 * 2 ** attempt) * random.uniform(0.8, 1.2)
                log.warning("%s: rate limited (attempt %d/%d); retrying in %.1fs", self.mode, attempt + 1,
                            settings.rate_limit_retries, delay)
                # keep the slot while waiting so other threads queue up instead of hammering the endpoint
                time.sleep(delay)
            finally:
                if self.slots:
                    self.slots.release()
        raise AssertionError("unreachable")

    @property
    def embedding_model(self) -> str:
        return self.embedder.embedding_model

    def embed(self, texts: list[str]) -> np.ndarray:
        return self.embedder.embed(texts)

    def describe_image(self, data_url: str, context: str = "") -> str:
        if not self.vision_model:  # text-only model: borrow another provider's vision
            if self.vision_fallback:
                return self.vision_fallback.describe_image(data_url, context)
            return MockLLM().describe_image(data_url, context)
        prompt = IMAGE_PROMPT + (f"\n\nThe user wrote: {context[:1500]}" if context else "")
        resp = self._chat(
            model=self.vision_model,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}],
        )
        return (resp.choices[0].message.content or "").strip()

    def complete_json(self, system: str, user: str, schema: dict, name: str,
                      fallback: Callable[[], dict]) -> dict:
        from openai import BadRequestError, UnprocessableEntityError

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            resp = self._chat(
                model=self.chat_model,
                messages=messages,
                response_format={"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}},
            )
            return _parse_json(resp.choices[0].message.content or "{}")
        except (BadRequestError, UnprocessableEntityError) as e:  # some models only support json_object, or no response_format at all
            log.warning("%s: json_schema not accepted (%s); retrying with json_object", self.mode, e)
        messages[0]["content"] += "\n\nReply with a single JSON object matching this schema:\n" + json.dumps(schema)
        try:
            resp = self._chat(
                model=self.chat_model, messages=messages, response_format={"type": "json_object"},
            )
        except (BadRequestError, UnprocessableEntityError) as e:
            log.warning("%s: json_object not accepted (%s); retrying without response_format", self.mode, e)
            resp = self._chat(model=self.chat_model, messages=messages)
        return _parse_json(resp.choices[0].message.content or "{}")

    def complete_text(self, system: str, user: str, fallback: Callable[[], str]) -> str:
        resp = self._chat(
            model=self.chat_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return (resp.choices[0].message.content or "").strip()


class MockLLM:
    """Deterministic offline stand-in. Retrieval quality ~ keyword search."""

    mode = "mock"
    label = "Offline (mock)"
    chat_model = "heuristic fallback"
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
        return f"[mock mode] Attached image (~{size_kb} KB) not analysed; configure a vision-capable provider (Foundry or OpenAI)."

    def complete_json(self, system: str, user: str, schema: dict, name: str,
                      fallback: Callable[[], dict]) -> dict:
        return fallback()

    def complete_text(self, system: str, user: str, fallback: Callable[[], str]) -> str:
        return fallback()


_providers: dict[str, LLM] | None = None
_default: str = "mock"


def _build_providers() -> dict[str, LLM]:
    """All configured chat providers, in preference order. Empty when nothing is configured or LLM_MODE=mock."""
    from openai import OpenAI

    if settings.llm_mode == "mock":
        return {}
    foundry = openai = None
    if settings.foundry_endpoint:
        if settings.foundry_api_key:
            api_key: Any = settings.foundry_api_key
        else:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            api_key = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
        foundry = OpenAI(base_url=settings.foundry_endpoint, api_key=api_key)
    if settings.openai_api_key:
        openai = OpenAI(base_url=settings.openai_base_url, api_key=settings.openai_api_key)

    # One embedder for everything: knowledge vectors must come from a single model.
    embedder: Embedder = (OpenAIEmbedder(foundry, settings.embedding_deployment, "azure") if foundry
                          else OpenAIEmbedder(openai, settings.openai_embedding_model, "openai") if openai
                          else MockLLM())

    providers: dict[str, LLM] = {}
    if foundry:
        providers["foundry"] = ChatLLM("foundry", "Azure AI Foundry", foundry, settings.chat_deployment,
                                       settings.vision_deployment, embedder)
    if openai:
        providers["openai"] = ChatLLM("openai", "OpenAI", openai, settings.openai_chat_model,
                                      settings.openai_vision_model, embedder)
    if settings.apertus_api_key:
        vision = providers.get("foundry") or providers.get("openai")
        providers["apertus"] = ChatLLM("apertus", "Apertus (Swisscom)",
                                       OpenAI(base_url=settings.apertus_base_url, api_key=settings.apertus_api_key),
                                       settings.apertus_model, None, embedder, vision_fallback=vision,
                                       max_concurrency=settings.apertus_max_concurrency)
    return providers


def providers() -> dict[str, LLM]:
    global _providers, _default
    if _providers is None:
        _providers = _build_providers()
        wanted = {"azure": "foundry"}.get(settings.llm_mode, settings.llm_mode)
        _default = wanted if wanted in _providers else next(iter(_providers), "mock")
        if settings.llm_mode and settings.llm_mode != "mock" and wanted not in _providers:
            log.warning("LLM_MODE=%s is not configured; using %s", settings.llm_mode, _default)
        log.info("LLM providers: %s (default %s)", ", ".join(_providers) or "none", _default)
    return _providers


def default_provider() -> str:
    providers()
    return _default


def get_llm(provider: str | None = None) -> LLM:
    """The chat provider by id (see `providers()`), or the default one. Falls back to the offline mock."""
    available = providers()
    return available.get(provider or _default) or MockLLM()
