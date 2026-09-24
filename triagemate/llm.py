"""Provider-agnostic LLM layer (Sec. 4.11 design rule): every provider speaks the OpenAI-compatible API, so the
provider is a *config value*. No provider quirk leaks into business logic.

Supported (via LLM_PROVIDER):  openai | apertus | local | azure   -> OpenAI-style /chat/completions
                               anthropic                          -> native Messages API (adapter below)
Guarantees:
  * every call is timed, token-counted and priced (per-ticket ``track()`` context) -> real cost-per-ticket metric
  * structured output: JSON mode when the provider supports it, tolerant extraction otherwise, Pydantic validation,
    one repair retry with the validation error appended (Sec. 4.2)
  * retries with backoff on 429/5xx, plus a circuit breaker so a dead provider never stalls the demo:
    callers catch ``LLMUnavailable`` and use their deterministic fallback.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
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

    def add(self, name: str, tin: int, tout: int, ms: float, cost: float, model: str) -> None:
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


# ------------------------------------------------------------------ client
class LLMClient:
    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None):
        self.s = settings or get_settings()
        self.transport = transport
        self.breaker = _Breaker()
        self._http: httpx.Client | None = None
        self._json_mode_ok = True
        self._embed_cache: dict[str, list[float]] = {}
        self._cache_file = self.s.outputs_dir / "cache" / "embeddings.json"
        self._cache_dirty = 0

    # ---- config ---------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self.s.llm_enabled

    @property
    def provider(self) -> str:
        return self.s.llm_provider.lower()

    def _client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=self.s.llm_timeout, transport=self.transport)
        return self._http

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.provider == "azure":
            h["api-key"] = self.s.llm_api_key
        elif self.provider == "anthropic":
            h["x-api-key"] = self.s.llm_api_key
            h["anthropic-version"] = "2023-06-01"
        elif self.s.llm_api_key:
            h["Authorization"] = f"Bearer {self.s.llm_api_key}"
        return h

    def _chat_url(self) -> str:
        if self.provider == "azure":
            ep = self.s.azure_openai_endpoint.rstrip("/")
            dep = self.s.azure_openai_deployment or self.s.llm_model
            return f"{ep}/openai/deployments/{dep}/chat/completions?api-version={self.s.azure_openai_api_version}"
        if self.provider == "anthropic":
            return (self.s.llm_base_url if "anthropic" in self.s.llm_base_url else "https://api.anthropic.com/v1").rstrip("/") + "/messages"
        return self.s.llm_base_url.rstrip("/") + "/chat/completions"

    # ---- pricing --------------------------------------------------------
    def _cost(self, tin: int, tout: int) -> float:
        return tin / 1e6 * self.s.price_in_per_1m + tout / 1e6 * self.s.price_out_per_1m

    # ---- raw request with retries ---------------------------------------
    def _post(self, url: str, payload: dict, name: str) -> dict:
        if not self.enabled:
            raise LLMUnavailable("no LLM configured")
        if not self.breaker.allow():
            raise LLMUnavailable("circuit breaker open (provider recently failing)")
        last: Exception | None = None
        client_error = False
        for attempt in range(self.s.llm_max_retries + 1):
            try:
                r = self._client().post(url, headers=self._headers(), json=payload)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
                if r.status_code >= 400:
                    # 4xx is a request/config problem, not transient - do not retry blindly and do not trip the breaker
                    client_error = True
                    raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
                self.breaker.ok()
                return r.json()
            except (httpx.HTTPError, LLMError) as e:  # network or transient
                last = e
                if client_error:
                    break
                time.sleep(min(0.4 * (2 ** attempt), 3.0))
        if not client_error:
            self.breaker.fail()
        raise LLMUnavailable(f"{name}: {last}")

    # ---- OpenAI-style chat ----------------------------------------------
    def chat(self, messages: list[dict], *, model: str | None = None, temperature: float = 0.0, max_tokens: int = 400,
             json_mode: bool = False, tools: list[dict] | None = None, tool_choice: str | None = None,
             name: str = "chat") -> dict:
        """Returns {"content": str|None, "tool_calls": [{"id","name","arguments"(dict)}], "usage": (in, out)}."""
        model = model or self.s.classify_model
        if self.provider == "anthropic":
            return self._chat_anthropic(messages, model=model, temperature=temperature, max_tokens=max_tokens,
                                        tools=tools, name=name)
        payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if self.provider == "azure":
            payload.pop("model", None)
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

    # ---- Anthropic Messages adapter (same return shape) -----------------
    def _chat_anthropic(self, messages: list[dict], *, model: str, temperature: float, max_tokens: int,
                        tools: list[dict] | None, name: str) -> dict:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        conv = []
        for m in messages:
            if m["role"] == "system":
                continue
            if m["role"] == "tool":
                conv.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": m["tool_call_id"],
                                                          "content": m["content"]}]})
            elif m["role"] == "assistant" and m.get("tool_calls"):
                blocks = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"],
                                   "input": json.loads(tc["function"]["arguments"] or "{}")})
                conv.append({"role": "assistant", "content": blocks})
            else:
                conv.append({"role": m["role"], "content": m["content"]})
        payload: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "messages": conv}
        if system:
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                                 "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}})} for t in tools]
        t0 = time.perf_counter()
        data = self._post(self._chat_url(), payload, name)
        ms = (time.perf_counter() - t0) * 1000
        text, calls = "", []
        for b in data.get("content", []):
            if b.get("type") == "text":
                text += b.get("text", "")
            elif b.get("type") == "tool_use":
                calls.append({"id": b["id"], "name": b["name"], "arguments": b.get("input", {})})
        usage = data.get("usage") or {}
        tin, tout = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
        u = _current.get()
        if u is not None:
            u.add(name, tin, tout, ms, self._cost(tin, tout), model)
        raw = {"role": "assistant", "content": text or None}
        if calls:
            raw["tool_calls"] = [{"id": c["id"], "type": "function",
                                  "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}} for c in calls]
        return {"content": text or None, "tool_calls": calls, "usage": (tin, tout), "raw_message": raw}

    # ---- structured output ----------------------------------------------
    def chat_json(self, system: str, user: str, model_cls: Type[T], *, model: str | None = None, max_tokens: int = 350,
                  temperature: float = 0.0, name: str = "task") -> T:
        """Typed contract: JSON -> validate -> one repair retry with the error appended -> raise (caller falls back)."""
        schema_hint = json.dumps(model_cls.model_json_schema().get("properties", {}), ensure_ascii=False)
        sys_full = f"{system}\n\nReturn ONLY a JSON object with these fields: {schema_hint}"
        messages = [{"role": "system", "content": sys_full}, {"role": "user", "content": user}]
        err_note = ""
        for attempt in range(2):
            if err_note:
                messages = messages + [{"role": "user", "content": f"Your previous answer was invalid ({err_note}). "
                                                                     f"Reply again with ONLY the corrected JSON object."}]
            res = self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens, json_mode=True, name=name)
            try:
                obj = extract_json(res["content"] or "")
                return model_cls.model_validate(obj)
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
        if not self.enabled:
            raise LLMUnavailable("no LLM configured")
        self._load_cache()
        model = self.s.embed_model
        keyf = lambda t: hashlib.sha1(f"{model}␟{t}".encode()).hexdigest()
        missing = [t for t in texts if keyf(t) not in self._embed_cache]
        base = (self.s.embed_base_url or self.s.llm_base_url).rstrip("/")
        key = self.s.embed_api_key or self.s.llm_api_key
        for i in range(0, len(missing), 64):
            batch = missing[i:i + 64]
            if self.provider == "azure":
                url = f"{self.s.azure_openai_endpoint.rstrip('/')}/openai/deployments/{model}/embeddings?api-version={self.s.azure_openai_api_version}"
                headers = {"api-key": key, "Content-Type": "application/json"}
            else:
                url = f"{base}/embeddings"
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            r = self._client().post(url, headers=headers, json={"model": model, "input": batch})
            if r.status_code >= 400:
                raise LLMUnavailable(f"embeddings HTTP {r.status_code}")
            for t, item in zip(batch, r.json()["data"]):
                self._embed_cache[keyf(t)] = item["embedding"]
                self._cache_dirty += 1
        if self._cache_dirty:
            try:
                self._cache_file.parent.mkdir(parents=True, exist_ok=True)
                self._cache_file.write_text(json.dumps(self._embed_cache), encoding="utf-8")
                self._cache_dirty = 0
            except OSError:
                pass
        return [self._embed_cache[keyf(t)] for t in texts]


_CLIENT: LLMClient | None = None


def get_client(force: bool = False) -> LLMClient:
    global _CLIENT
    if _CLIENT is None or force:
        _CLIENT = LLMClient()
    return _CLIENT


def set_client(client: LLMClient | None) -> None:
    """Tests / eval can inject a client wired to a mock transport."""
    global _CLIENT
    _CLIENT = client


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
