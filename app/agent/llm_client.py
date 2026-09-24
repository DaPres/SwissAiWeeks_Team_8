"""Multi-provider LLM client with ordered fallback.

Order: Swisscom Apertus -> OpenAI -> Public AI (HF router) -> local Ollama (offline only).
Every provider speaks the OpenAI chat-completions protocol, so one SDK covers all four.
"""

from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass, field

import openai
from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import load_env

log = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful IT/operations service-desk assistant. Answer using the provided "
    "context when it is relevant. If the context does not contain the answer, say so and "
    "suggest opening a ticket. Be concise."
)


class ProviderUnavailable(Exception):
    """Provider is not configured (missing key) or deliberately skipped."""


class AllProvidersFailed(Exception):
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("All LLM providers failed: " + "; ".join(f"{k}: {v}" for k, v in errors.items()))


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    errors: dict[str, str] = field(default_factory=dict)  # providers that failed before this one


@dataclass
class Provider:
    name: str
    base_url: str | None
    model: str
    key_env: str | None  # None = no key needed (Ollama)
    refresh_on_401: bool = False  # re-read .env and retry once on 401 (Apertus bearer expiry)
    offline_only: bool = False

    def api_key(self) -> str:
        if self.key_env is None:
            return "ollama"  # Ollama ignores the key, but the SDK requires a value
        key = os.getenv(self.key_env, "").strip()
        if not key:
            raise ProviderUnavailable(f"{self.key_env} is not set in .env")
        return key


def default_providers() -> list[Provider]:
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    return [
        Provider(
            name="swisscom-apertus",
            base_url=os.getenv(
                "APERTUS_BASE_URL",
                "https://api.swisscom.com/products/swiss-ai-weeks/apertus-1.5-70b/v1",
            ),
            model=os.getenv("APERTUS_MODEL", "swiss-ai/Apertus-v1.5-70B"),
            key_env="SWISSCOM_APERTUS_API_KEY",
            refresh_on_401=True,
        ),
        Provider(
            name="openai",
            base_url=None,
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            key_env="OPENAI_API_KEY",
        ),
        Provider(
            name="publicai-hf",
            base_url="https://router.huggingface.co/v1",
            model=os.getenv("PUBLICAI_MODEL", "swiss-ai/Apertus-70B-Instruct-2509:publicai"),
            key_env="HF_TOKEN",
        ),
        Provider(
            name="ollama-local",
            base_url=f"{ollama_base}/v1",
            model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            key_env=None,
            # Default "always": on stage, a slow local answer beats a 503. Set
            # OLLAMA_FALLBACK_MODE=offline_only to restrict it to genuinely offline runs.
            offline_only=os.getenv("OLLAMA_FALLBACK_MODE", "always") == "offline_only",
        ),
    ]


def providers_for_task(task: str | None) -> list[Provider]:
    """Per-task routing from .env: TASK_CLASSIFY_PROVIDER, TASK_EXTRACT_PROVIDER,
    TASK_AGENT_PROVIDER, TASK_DRAFT_PROVIDER.

    The named provider goes first; the rest stay in their default order as fallbacks, so a
    routing choice never removes the safety net. Setting every TASK_* to `swisscom-apertus`
    gives an all-Swiss deployment.
    """
    providers = default_providers()
    if not task:
        return providers
    preferred = os.getenv(f"TASK_{task.upper()}_PROVIDER", "").strip()
    if not preferred:
        return providers
    chosen = [p for p in providers if p.name == preferred]
    if not chosen:
        log.warning("TASK_%s_PROVIDER=%r is not a known provider; using default order", task.upper(), preferred)
        return providers
    return chosen + [p for p in providers if p.name != preferred]


def has_internet(host: str = "1.1.1.1", port: int = 53, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class LLMClient:
    def __init__(self, providers: list[Provider] | None = None, timeout: float | None = None, task: str | None = None):
        load_env()
        self.task = task
        self.providers = providers if providers is not None else providers_for_task(task)
        self.timeout = timeout or float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

    def _make_client(self, p: Provider) -> OpenAI:
        # max_retries=0: fallback to the next provider is our retry strategy.
        return OpenAI(api_key=p.api_key(), base_url=p.base_url, timeout=self.timeout, max_retries=0)

    def _call(self, p: Provider, messages: list[dict], **kwargs) -> str:
        resp = self._make_client(p).chat.completions.create(model=p.model, messages=messages, **kwargs)
        return resp.choices[0].message.content or ""

    def _call_with_token_refresh(self, p: Provider, messages: list[dict], **kwargs) -> str:
        """Retry once on 401: the Apertus bearer token expires after ~60 min.

        Before the retry we re-read .env (override=True) so a freshly pasted token is used
        without restarting the server.
        """

        def _reload(_state) -> None:
            log.warning("%s returned 401; reloading .env and retrying once", p.name)
            load_env(override=True)

        @retry(
            retry=retry_if_exception_type(openai.AuthenticationError),
            stop=stop_after_attempt(2),
            before_sleep=_reload,
            reraise=True,
        )
        def _go() -> str:
            return self._call(p, messages, **kwargs)

        return _go()

    def call_provider(self, p: Provider, messages: list[dict], **kwargs) -> str:
        p.api_key()  # raises ProviderUnavailable up front if the key is missing

        # Apertus returns 429 EXPIRED_QUOTA on rapid consecutive calls (measured in the
        # provider probe). Back off briefly before giving up on the primary provider.
        @retry(
            retry=retry_if_exception_type(openai.RateLimitError),
            stop=stop_after_attempt(int(os.getenv("RATE_LIMIT_ATTEMPTS", "3"))),
            wait=wait_exponential(multiplier=float(os.getenv("RATE_LIMIT_BASE_SECONDS", "2")), max=30),
            reraise=True,
        )
        def _go() -> str:
            if p.refresh_on_401:
                return self._call_with_token_refresh(p, messages, **kwargs)
            return self._call(p, messages, **kwargs)

        return _go()

    def chat(self, messages: list[dict], **kwargs) -> LLMResponse:
        errors: dict[str, str] = {}
        for p in self.providers:
            if p.offline_only and has_internet():
                errors[p.name] = "skipped (internet is up; Ollama is offline-only)"
                continue
            try:
                text = self.call_provider(p, messages, **kwargs)
                return LLMResponse(text=text, provider=p.name, model=p.model, errors=errors)
            except ProviderUnavailable as e:
                errors[p.name] = f"not configured: {e}"
            except openai.APIStatusError as e:  # 401/403/404/429/5xx
                errors[p.name] = f"HTTP {e.status_code}: {_short(e)}"
            except (openai.APITimeoutError, openai.APIConnectionError) as e:
                errors[p.name] = f"{type(e).__name__}: {_short(e)}"
            except Exception as e:  # never let one provider's bug kill the fallback chain
                errors[p.name] = f"{type(e).__name__}: {_short(e)}"
            log.warning("provider %s failed: %s", p.name, errors[p.name])
        raise AllProvidersFailed(errors)

    def ask(self, question: str, context: str = "", system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> LLMResponse:
        user = f"Context:\n{context}\n\nQuestion: {question}" if context else question
        return self.chat([{"role": "system", "content": system_prompt}, {"role": "user", "content": user}])


def _short(e: Exception, n: int = 200) -> str:
    s = str(e).replace("\n", " ")
    return s if len(s) <= n else s[:n] + "..."
