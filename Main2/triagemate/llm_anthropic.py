"""Claude (Anthropic) chat backend behind the same interface as the OpenAI-compatible client in ``llm.py``.

Kept in its own module on purpose: ``llm.py`` stays provider-neutral (the plan's design rule), and everything Claude-specific
lives here, built on the official ``anthropic`` SDK. Selected with ``LLM_PROVIDER=anthropic`` (``pip install anthropic``).

Current-API rules applied (Claude Opus 5 / Sonnet 5 family):
  * ``temperature`` / ``top_p`` / ``top_k`` are removed on these models (400 if sent) -> omitted; determinism comes from the
    typed-JSON contract + the policy layer computing priority in code, exactly as in the OpenAI path.
  * thinking is adaptive by default; it is never disabled. Effort is set per task (``low`` for classification / extraction /
    tool routing, ``medium`` for drafting) and ``max_tokens`` leaves headroom for thinking.
  * ``stop_reason == "refusal"`` is surfaced as an error so the pipeline falls back to its deterministic path.
  * server-side ``fallbacks: "default"`` (beta ``server-side-fallback-2026-07-01``) is opted in for Opus 5 / Fable; if the API
    rejects the parameter the call is retried once without it.
  * assistant turns that used tools are echoed back with their original content blocks (thinking blocks unchanged).
"""
from __future__ import annotations

import json
from typing import Any

from .llm import LLMError, LLMUnavailable

_NO_SAMPLING = ("claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-5", "claude-fable", "claude-mythos")
_EFFORT_OK = ("claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-5", "claude-sonnet-4-6",
              "claude-fable", "claude-mythos")
_FALLBACK_OK = ("claude-opus-5", "claude-fable")
_EFFORT_BY_TASK = {"draft": "medium", "resolution_note": "medium"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _starts(model: str, prefixes: tuple[str, ...]) -> bool:
    return any(model.startswith(p) for p in prefixes)


class AnthropicChat:
    def __init__(self, api_key: str, base_url: str = "", timeout: float = 60.0, max_retries: int = 2, transport=None):
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover - exercised only without the optional dependency
            raise LLMUnavailable("LLM_PROVIDER=anthropic needs the official SDK: pip install anthropic") from e
        self._sdk = anthropic
        kw: dict[str, Any] = {"api_key": api_key, "timeout": timeout, "max_retries": max_retries}
        if base_url and "anthropic.com" not in base_url:
            kw["base_url"] = base_url
        if transport is not None:
            kw["http_client"] = anthropic.DefaultHttpxClient(transport=transport)
        self.client = anthropic.Anthropic(**kw)
        self._fallbacks_ok = True

    # ---- message conversion (internal OpenAI-style dicts -> Anthropic blocks) -------------------
    @staticmethod
    def _convert(messages: list[dict]) -> tuple[str, list[dict]]:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        conv: list[dict] = []
        for m in messages:
            role = m["role"]
            if role == "system":
                continue
            if role == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": str(m["content"])}
                if conv and conv[-1]["role"] == "user" and isinstance(conv[-1]["content"], list) \
                        and conv[-1]["content"] and conv[-1]["content"][0].get("type") == "tool_result":
                    conv[-1]["content"].append(block)            # all results of one turn go in ONE user message
                else:
                    conv.append({"role": "user", "content": [block]})
            elif role == "assistant" and m.get("_blocks"):
                conv.append({"role": "assistant", "content": m["_blocks"]})       # verbatim, incl. thinking blocks
            elif role == "assistant" and m.get("tool_calls"):
                blocks = ([{"type": "text", "text": m["content"]}] if m.get("content") else []) + [
                    {"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"], "input": json.loads(tc["function"]["arguments"] or "{}")}
                    for tc in m["tool_calls"]]
                conv.append({"role": "assistant", "content": blocks})
            else:
                conv.append({"role": role, "content": m["content"] or ""})
        return system, conv

    # ---- one call -----------------------------------------------------------------------------
    def chat(self, messages: list[dict], *, model: str, max_tokens: int, tools: list[dict] | None, name: str) -> dict:
        sdk = self._sdk
        system, conv = self._convert(messages)
        kw: dict[str, Any] = {"model": model, "max_tokens": max(max_tokens, 2048), "messages": conv}
        if system:
            kw["system"] = system
        if tools:
            kw["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                            "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}})} for t in tools]
        if _starts(model, _EFFORT_OK):
            kw["output_config"] = {"effort": _EFFORT_BY_TASK.get(name, "low")}
        try:
            resp = self._create(kw, model)
        except sdk.RateLimitError as e:
            raise LLMUnavailable(f"{name}: rate limited ({e})") from e
        except (sdk.APIConnectionError, sdk.InternalServerError) as e:
            raise LLMUnavailable(f"{name}: {e}") from e
        except sdk.APIStatusError as e:
            raise LLMUnavailable(f"{name}: HTTP {e.status_code} {getattr(e, 'message', '')[:160]}") from e

        if resp.stop_reason == "refusal":
            cat = getattr(getattr(resp, "stop_details", None), "category", None)
            raise LLMError(f"{name}: model refused (category={cat}); using the deterministic fallback")
        text, calls, blocks = "", [], []
        for b in resp.content:
            blocks.append(b.model_dump(exclude_none=True))
            if b.type == "text":
                text += b.text
            elif b.type == "tool_use":
                calls.append({"id": b.id, "name": b.name, "arguments": b.input or {}})
        if resp.stop_reason == "max_tokens" and not text and not calls:
            raise LLMError(f"{name}: response truncated before any output (raise max_tokens)")
        u = resp.usage
        tin = int(getattr(u, "input_tokens", 0) or 0) + int(getattr(u, "cache_read_input_tokens", 0) or 0)
        raw = {"role": "assistant", "content": text or None, "_blocks": blocks}
        if calls:
            raw["tool_calls"] = [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}} for c in calls]
        return {"content": text or None, "tool_calls": calls, "usage": (tin, int(getattr(u, "output_tokens", 0) or 0)), "raw_message": raw}

    def _create(self, kw: dict, model: str):
        sdk = self._sdk
        if self._fallbacks_ok and _starts(model, _FALLBACK_OK):
            try:
                return self.client.messages.create(**kw, extra_headers={"anthropic-beta": FALLBACK_BETA}, extra_body={"fallbacks": "default"})
            except sdk.BadRequestError as e:
                if "fallback" in str(e).lower() or "beta" in str(e).lower():
                    self._fallbacks_ok = False               # parameter not accepted for this org/model: stop sending it
                else:
                    raise
        return self.client.messages.create(**kw)
