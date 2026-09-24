"""Provider-agnostic LLM layer (Sec. 4.11 design rule): every provider speaks the OpenAI-compatible API, so the
provider is a *config value*. No provider quirk leaks into business logic.

Providers (LLM_PROVIDER, or per role with CLASSIFY_PROVIDER / DRAFT_PROVIDER):
   openai | apertus (Swisscom Swiss AI Platform) | local (Ollama / LM Studio) | azure   -> OpenAI-style /chat/completions
   anthropic                                                                              -> official SDK, see llm_anthropic.py
Guarantees:
  * every call is timed, token-counted and priced (per-ticket ``track()`` context) -> real cost-per-ticket metric
  * structured output: JSON mode when the provider supports it, tolerant extraction otherwise, Pydantic validation,
    one repair retry with the validation error appended (Sec. 4.2)
  * client-side throttle (Apertus allows 5 requests/s), Retry-After honoured, retries with backoff on 429/5xx, and a circuit
    breaker so a dead provider never stalls the demo: callers catch ``LLMUnavailable`` and use their deterministic fallback.
"""
from __future__ import annotations

import atexit
import contextvars
import hashlib
import json
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import Settings, get_settings

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    """Provider not configured, breaker open, or all retries failed -> use the deterministic fallback."""


# ------------------------------------------------------------------ usage / cost accounting
@dataclass
class Usage:
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    log: list[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def add(self, name: str, tin: int, tout: int, ms: float, cost: float, model: str) -> None:
        with self._lock:
            self.calls += 1
            self.tokens_in += tin
            self.tokens_out += tout
            self.latency_ms += ms
            self.cost_usd += cost
            self.log.append({"call": name, "model": model, "in": tin, "out": tout, "ms": round(ms, 1), "usd": round(cost, 6)})


_current: contextvars.ContextVar[Optional[Usage]] = contextvars.ContextVar("triage_usage", default=None)


@contextmanager
def track():
    u = Usage()
    tok = _current.set(u)
    try:
        yield u
    finally:
        _current.reset(tok)


# ------------------------------------------------------------------ helpers
def extract_json(text: str) -> Any:
    """Tolerant JSON extraction: plain JSON, ```json fences, or the first balanced {...} in prose."""
    if text is None:
        raise ValueError("empty response")
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.I)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    start = s.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(s)):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(s[start:i + 1])
                    except json.JSONDecodeError:
                        break
        start = s.find("{", start + 1)
    raise ValueError(f"no JSON object found in: {s[:120]!r}")


class _Breaker:
    def __init__(self, threshold: int = 3, cooldown: float = 45.0):
        self.threshold, self.cooldown = threshold, cooldown
        self.fails = 0
        self.open_until = 0.0
        self.lock = threading.Lock()

    def allow(self) -> bool:
        return time.monotonic() >= self.open_until

    def ok(self) -> None:
        with self.lock:
            self.fails = 0

    def fail(self) -> None:
        with self.lock:
            self.fails += 1
            if self.fails >= self.threshold:
                self.open_until = time.monotonic() + self.cooldown
                self.fails = 0


class _Throttle:
    """Minimum spacing between requests (e.g. 4 rps for Swisscom's 5 req/s limit). Thread-safe."""

    def __init__(self, rps: float):
        self.interval = 1.0 / rps if rps and rps > 0 else 0.0
        self.next_at = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        if not self.interval:
            return
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_at - now)
            self.next_at = max(now, self.next_at) + self.interval
        if delay:
            time.sleep(delay)



def _placeholder(ann: Any) -> Any:
    from typing import Literal, get_args, get_origin
    origin, args = get_origin(ann), get_args(ann)
    if ann is bool:
        return True
    if ann is int:
        return 0
    if ann is float:
        return 0.5
    if ann is str:
        return "<string>"
    if origin is Literal:
        return " | ".join(str(a) for a in args)          # e.g. "critical | high | medium | low | lowest": pick exactly one
    if origin in (list, set, tuple):
        return [_placeholder(args[0]) if args else "<string>"]
    if origin is not None and type(None) in args:         # Optional[X]
        return _placeholder(next(a for a in args if a is not type(None)))
    return "<value>"


def _example(model_cls: Type[BaseModel]) -> dict:
    """An example *instance* (not a JSON schema) - models imitate schema keywords ("title", "type") if you show them one."""
    return {name: _placeholder(f.annotation) for name, f in model_cls.model_fields.items()}


# ------------------------------------------------------------------ client
class LLMClient:
    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None,
                 provider: str | None = None, role: str = "classify"):
        self.s = settings or get_settings()
        self.role = role
        self.provider = (provider or self.s.role_provider(role)).lower()
        self.cfg = self.s.profile(self.provider)
        self.transport = transport
        self.breaker = _Breaker()
        self.throttle = _Throttle(self.cfg.rps)
        self._http: httpx.Client | None = None
        self._anth = None
        self._json_mode_ok = True
        self._embed_cache: dict[str, list[float]] = {}
        self._cache_file = self.s.outputs_dir / "cache" / "embeddings.json"
        self._cache_dirty = 0
        self._last_flush = time.monotonic()
        atexit.register(self._flush_cache, True)

    # ---- config ---------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return (not self.s.triage_offline) and self.cfg.enabled

    @property
    def default_model(self) -> str:
        return self.s.model_for(self.role) if self.provider == self.s.role_provider(self.role) else self.cfg.model

    def _client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=self.s.llm_timeout, transport=self.transport)
        return self._http

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.provider == "azure":
            h["api-key"] = self.cfg.api_key
        elif self.cfg.api_key:
            h["Authorization"] = f"Bearer {self.cfg.api_key}"
        return h

    def _chat_url(self) -> str:
        if self.provider == "azure":
            ep = self.cfg.azure_endpoint.rstrip("/")
            dep = self.cfg.azure_deployment or self.cfg.model
            return f"{ep}/openai/deployments/{dep}/chat/completions?api-version={self.cfg.azure_api_version}"
        return self.cfg.base_url.rstrip("/") + "/chat/completions"

    # ---- pricing --------------------------------------------------------
    def _cost(self, tin: int, tout: int) -> float:
        return tin / 1e6 * self.s.price_in_per_1m + tout / 1e6 * self.s.price_out_per_1m

    # ---- raw request with throttle / retries ----------------------------
    def _post(self, url: str, payload: dict, name: str, headers: dict | None = None) -> dict:
        if not self.enabled:
            raise LLMUnavailable("no LLM configured")
        if not self.breaker.allow():
            raise LLMUnavailable("circuit breaker open (provider recently failing)")
        last: Exception | None = None
        client_error = False
        for attempt in range(self.s.llm_max_retries + 1):
            try:
                self.throttle.wait()
                r = self._client().post(url, headers=headers or self._headers(), json=payload)
                if r.status_code in (429, 500, 502, 503, 504):
                    ra = r.headers.get("retry-after")
                    if ra and ra.replace(".", "", 1).isdigit():
                        time.sleep(min(float(ra), 5.0))
                    raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
                if r.status_code >= 400:
                    # 4xx is a request/config problem (bad key, bad model): do not retry blindly, do not trip the breaker
                    client_error = True
                    raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
                self.breaker.ok()
                return r.json()
            except (httpx.HTTPError, LLMError) as e:
                last = e
                if client_error:
                    break
                time.sleep(min(0.4 * (2 ** attempt), 3.0))
        if not client_error:
            self.breaker.fail()
        raise LLMUnavailable(f"{name}: {last}")

    # ---- chat (OpenAI-style, or Claude via the official SDK) ---------------
    def chat(self, messages: list[dict], *, model: str | None = None, temperature: float = 0.0, max_tokens: int = 400,
             json_mode: bool = False, tools: list[dict] | None = None, tool_choice: str | None = None,
             name: str = "chat") -> dict:
        """Returns {"content": str|None, "tool_calls": [{"id","name","arguments"(dict)}], "usage": (in, out), "raw_message"}."""
        model = model or self.default_model
        if self.provider == "anthropic":
            return self._chat_anthropic(messages, model, max_tokens, tools, name)
        payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if self.provider == "azure":
            payload.pop("model", None)
        if self.provider in ("openai", "azure") and temperature == 0:
            payload["seed"] = 7                       # best-effort determinism for the repeated-run consistency metric
        if json_mode and self._json_mode_ok:
            payload["response_format"] = {"type": "json_object"}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
        t0 = time.perf_counter()
        try:
            data = self._post(self._chat_url(), payload, name)
        except LLMUnavailable as e:
            if json_mode and "response_format" in payload and "HTTP 400" in str(e):
                self._json_mode_ok = False            # provider rejects JSON mode: fall back to prompt-only JSON
                payload.pop("response_format")
                data = self._post(self._chat_url(), payload, name)
            elif "max_tokens" in str(e) and "HTTP 400" in str(e) and "max_completion_tokens" in str(e):
                payload["max_completion_tokens"] = payload.pop("max_tokens")   # newer OpenAI models
                data = self._post(self._chat_url(), payload, name)
            else:
                raise
        ms = (time.perf_counter() - t0) * 1000
        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            raise LLMError(f"malformed response: {str(data)[:200]}") from e
        usage = data.get("usage") or {}
        tin, tout = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        u = _current.get()
        if u is not None:
            u.add(name, tin, tout, ms, self._cost(tin, tout), model)
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_raw": fn.get("arguments")}
            calls.append({"id": tc.get("id"), "name": fn.get("name"), "arguments": args})
        return {"content": msg.get("content"), "tool_calls": calls, "usage": (tin, tout), "raw_message": msg}

    def _chat_anthropic(self, messages, model, max_tokens, tools, name) -> dict:
        if not self.enabled:
            raise LLMUnavailable("no LLM configured")
        if not self.breaker.allow():
            raise LLMUnavailable("circuit breaker open (provider recently failing)")
        from .llm_anthropic import AnthropicChat
        if self._anth is None:
            self._anth = AnthropicChat(self.cfg.api_key, self.cfg.base_url, self.s.llm_timeout, self.s.llm_max_retries, self.transport)
        t0 = time.perf_counter()
        try:
            res = self._anth.chat(messages, model=model, max_tokens=max_tokens, tools=tools, name=name)
        except LLMUnavailable:
            self.breaker.fail()
            raise
        self.breaker.ok()
        u = _current.get()
        if u is not None:
            tin, tout = res["usage"]
            u.add(name, tin, tout, (time.perf_counter() - t0) * 1000, self._cost(tin, tout), model)
        return res

    # ---- structured output ----------------------------------------------
    def chat_json(self, system: str, user: str, model_cls: Type[T], *, model: str | None = None, max_tokens: int = 350,
                  temperature: float = 0.0, name: str = "task") -> T:
        """Typed contract: JSON -> validate -> one repair retry with the error appended -> raise (caller falls back)."""
        sys_full = (f"{system}\n\nReturn ONLY one JSON object shaped exactly like this example - replace every placeholder with a real value "
                    f"(no schema keywords, no extra fields, no prose):\n{json.dumps(_example(model_cls), ensure_ascii=False)}")
        messages = [{"role": "system", "content": sys_full}, {"role": "user", "content": user}]
        err_note = ""
        for _ in range(2):
            if err_note:
                messages = messages + [{"role": "user", "content": f"Your previous answer was invalid ({err_note}). "
                                                                     f"Reply again with ONLY the corrected JSON object."}]
            res = self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens, json_mode=True, name=name)
            try:
                return model_cls.model_validate(extract_json(res["content"] or ""))
            except (ValueError, ValidationError) as e:
                err_note = str(e)[:300].replace("\n", " ")
                messages = messages[:2] + [{"role": "assistant", "content": res["content"] or ""}]
        raise LLMError(f"{name}: no valid JSON after repair retry ({err_note})")

    # ---- embeddings -------------------------------------------------------
    def _load_cache(self) -> None:
        if self._embed_cache or not self._cache_file.exists():
            return
        try:
            self._embed_cache = json.loads(self._cache_file.read_text(encoding="utf-8"))
        except Exception:
            self._embed_cache = {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        ep = self.s.embed_profile()
        if ep is None:
            raise LLMUnavailable("no embedding provider configured")
        self._load_cache()
        model = ep.model or self.s.embed_model
        keyf = lambda t: hashlib.sha1(f"{ep.provider}␟{model}␟{t}".encode()).hexdigest()
        missing = [t for t in texts if keyf(t) not in self._embed_cache]
        for i in range(0, len(missing), 64):
            batch = missing[i:i + 64]
            if ep.provider == "azure":
                url = f"{ep.azure_endpoint.rstrip('/')}/openai/deployments/{model}/embeddings?api-version={ep.azure_api_version}"
                headers = {"api-key": ep.api_key, "Content-Type": "application/json"}
            else:
                url = f"{ep.base_url.rstrip('/')}/embeddings"
                headers = {"Authorization": f"Bearer {ep.api_key}", "Content-Type": "application/json"}
            self.throttle.wait()
            r = self._client().post(url, headers=headers, json={"model": model, "input": batch})
            if r.status_code >= 400:
                raise LLMUnavailable(f"embeddings HTTP {r.status_code}")
            for t, item in zip(batch, r.json()["data"]):
                self._embed_cache[keyf(t)] = item["embedding"]
                self._cache_dirty += 1
        self._flush_cache()
        return [self._embed_cache[keyf(t)] for t in texts]

    def _flush_cache(self, force: bool = False) -> None:
        """Write the embedding cache at most every 20 s (it is several MB) and once more at exit."""
        if not self._cache_dirty or (not force and time.monotonic() - self._last_flush < 20):
            return
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(json.dumps(self._embed_cache), encoding="utf-8")
            self._cache_dirty = 0
            self._last_flush = time.monotonic()
        except OSError:
            pass


# ------------------------------------------------------------------ client registry
_CLIENTS: dict[tuple[str, str], LLMClient] = {}
_OVERRIDE: LLMClient | None = None


def get_client(role: str = "classify", force: bool = False) -> LLMClient:
    """One client per (provider, role): 'classify' covers classification / extraction / agent steps, 'draft' covers drafts,
    clarifications and resolution notes. Lets you run e.g. OpenAI for classification and Apertus for drafting."""
    if _OVERRIDE is not None:
        return _OVERRIDE
    s = get_settings()
    key = (s.role_provider(role), role)
    if force or key not in _CLIENTS:
        _CLIENTS[key] = LLMClient(s, role=role)
    return _CLIENTS[key]


def set_client(client: LLMClient | None) -> None:
    """Tests / eval can inject a client (e.g. wired to a mock transport) for every role."""
    global _OVERRIDE
    _OVERRIDE = client
    _CLIENTS.clear()


def any_llm_enabled() -> bool:
    return get_client("classify").enabled or get_client("draft").enabled


# ------------------------------------------------------------------ prompt loading (versioned in git)
@dataclass
class Prompt:
    name: str
    version: str
    text: str

    def render(self, **kw) -> str:
        out = self.text
        for k, v in kw.items():
            out = out.replace("{{" + k + "}}", str(v))
        return out


_PROMPTS: dict[str, Prompt] = {}


def load_prompt(name: str) -> Prompt:
    if name in _PROMPTS:
        return _PROMPTS[name]
    p = get_settings().prompts_dir / f"{name}.txt"
    raw = p.read_text(encoding="utf-8")
    m = re.match(r"#\s*version:\s*(\S+)\s*\n", raw)
    version = m.group(1) if m else "v0"
    text = raw[m.end():] if m else raw
    pr = Prompt(name, f"{version}+{hashlib.sha1(text.encode()).hexdigest()[:7]}", text.strip())
    _PROMPTS[name] = pr
    return pr
