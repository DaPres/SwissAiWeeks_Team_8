"""Offline tests: fallback order + 401 refresh logic, with fake providers (no network, no keys)."""

import httpx
import openai
import pytest

from app.agent.llm_client import AllProvidersFailed, LLMClient, Provider
from app.rag.ingest import chunk_text


def _status_error(cls, code: int):
    req = httpx.Request("POST", "http://x/v1/chat/completions")
    return cls("boom", response=httpx.Response(code, request=req), body=None)


def _providers(monkeypatch):
    monkeypatch.setenv("K1", "a")
    monkeypatch.setenv("K2", "b")
    monkeypatch.delenv("K_MISSING", raising=False)
    return [
        Provider("p1", None, "m1", "K1", refresh_on_401=True),
        Provider("missing", None, "m", "K_MISSING"),
        Provider("p2", None, "m2", "K2"),
    ]


def test_falls_back_to_next_provider(monkeypatch):
    client = LLMClient(providers=_providers(monkeypatch))

    def fake_call(p, messages, **kw):
        if p.name == "p1":
            raise _status_error(openai.RateLimitError, 429)
        return f"hi from {p.name}"

    monkeypatch.setattr(client, "_call", fake_call)
    r = client.chat([{"role": "user", "content": "x"}])
    assert r.provider == "p2" and r.text == "hi from p2"
    assert "429" in r.errors["p1"] and "not configured" in r.errors["missing"]


def test_401_retries_once_then_succeeds(monkeypatch):
    client = LLMClient(providers=_providers(monkeypatch)[:1])
    calls = {"n": 0}

    def fake_call(p, messages, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _status_error(openai.AuthenticationError, 401)
        return "ok"

    monkeypatch.setattr(client, "_call", fake_call)
    assert client.chat([{"role": "user", "content": "x"}]).text == "ok"
    assert calls["n"] == 2


def test_all_fail_raises(monkeypatch):
    client = LLMClient(providers=_providers(monkeypatch))
    monkeypatch.setattr(client, "_call", lambda *a, **k: (_ for _ in ()).throw(openai.APIConnectionError(request=httpx.Request("GET", "http://x"))))
    with pytest.raises(AllProvidersFailed) as ei:
        client.chat([{"role": "user", "content": "x"}])
    assert set(ei.value.errors) == {"p1", "missing", "p2"}


def test_chunk_text_respects_size():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(20))
    chunks = chunk_text(text, max_chars=500, overlap=50)
    assert len(chunks) > 1 and all(len(c) <= 500 + 50 + 2 for c in chunks)
