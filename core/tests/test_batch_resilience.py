"""Batch resilience: the Apertus bearer token expires roughly hourly, so the 401 refresh
must work MID-BATCH, not just on a first call. A 20-ticket run dying halfway through on
Friday morning would cost the submission.

Also covers per-task provider routing (TASK_*_PROVIDER).
"""

import httpx
import openai
import pytest

from app.agent.llm_client import LLMClient, Provider, providers_for_task


def _auth_error():
    req = httpx.Request("POST", "http://x/v1/chat/completions")
    return openai.AuthenticationError("token expired", response=httpx.Response(401, request=req), body=None)


@pytest.fixture
def apertus_like(monkeypatch):
    monkeypatch.setenv("K_AP", "token")
    monkeypatch.setenv("K_OA", "token")
    return [
        Provider("apertus", None, "apertus-70b", "K_AP", refresh_on_401=True),
        Provider("openai", None, "gpt", "K_OA"),
    ]


def test_401_mid_batch_recovers_and_the_batch_completes(apertus_like, monkeypatch):
    """Token expires at ticket 10 of 20; the client reloads .env and retries once."""
    client = LLMClient(providers=apertus_like)
    state = {"n": 0, "expired_at": 10, "reloads": 0}
    monkeypatch.setattr("app.agent.llm_client.load_env", lambda override=False: state.__setitem__("reloads", state["reloads"] + 1))

    def fake_call(p, messages, **kw):
        state["n"] += 1
        # one 401 exactly when the hourly token dies, then the refreshed token works
        if state["n"] == state["expired_at"] and not state.get("refreshed"):
            state["refreshed"] = True
            raise _auth_error()
        return f"ok-{state['n']}"

    monkeypatch.setattr(client, "_call", fake_call)

    results = [client.chat([{"role": "user", "content": f"ticket {i}"}]) for i in range(20)]
    assert len(results) == 20, "batch must complete"
    assert all(r.provider == "apertus" for r in results), "must stay on the primary, not silently degrade"
    assert state["reloads"] >= 1, ".env must be re-read so a freshly pasted token is used"


def test_repeated_expiries_across_a_long_batch(apertus_like, monkeypatch):
    """Two expiries in one run (a >1h batch) must both recover."""
    client = LLMClient(providers=apertus_like)
    state = {"n": 0, "fired": set()}
    monkeypatch.setattr("app.agent.llm_client.load_env", lambda override=False: None)

    def fake_call(p, messages, **kw):
        state["n"] += 1
        for boundary in (5, 15):
            if state["n"] == boundary and boundary not in state["fired"]:
                state["fired"].add(boundary)
                raise _auth_error()
        return "ok"

    monkeypatch.setattr(client, "_call", fake_call)
    results = [client.chat([{"role": "user", "content": "t"}]) for _ in range(20)]
    assert len(results) == 20 and state["fired"] == {5, 15}


def test_persistent_401_falls_through_to_the_next_provider(apertus_like, monkeypatch):
    """If the token is genuinely dead, the batch continues on the fallback rather than dying."""
    client = LLMClient(providers=apertus_like)
    monkeypatch.setattr("app.agent.llm_client.load_env", lambda override=False: None)

    def fake_call(p, messages, **kw):
        if p.name == "apertus":
            raise _auth_error()
        return "from fallback"

    monkeypatch.setattr(client, "_call", fake_call)
    r = client.chat([{"role": "user", "content": "t"}])
    assert r.provider == "openai" and "401" in r.errors["apertus"]


# --- per-task routing ---------------------------------------------------------------


def test_task_routing_puts_the_named_provider_first(monkeypatch):
    monkeypatch.setenv("TASK_DRAFT_PROVIDER", "swisscom-apertus")
    names = [p.name for p in providers_for_task("draft")]
    assert names[0] == "swisscom-apertus"
    assert len(names) == len({*names}) == 4, "fallbacks must be kept, not dropped"


def test_task_routing_keeps_the_safety_net(monkeypatch):
    monkeypatch.setenv("TASK_CLASSIFY_PROVIDER", "openai")
    names = [p.name for p in providers_for_task("classify")]
    assert names[0] == "openai" and "ollama-local" in names


def test_unknown_provider_name_falls_back_to_default_order(monkeypatch):
    monkeypatch.setenv("TASK_AGENT_PROVIDER", "not-a-provider")
    assert [p.name for p in providers_for_task("agent")] == [p.name for p in providers_for_task(None)]


def test_all_swiss_deployment_is_one_setting(monkeypatch):
    for task in ("classify", "extract", "agent", "draft"):
        monkeypatch.setenv(f"TASK_{task.upper()}_PROVIDER", "swisscom-apertus")
        assert providers_for_task(task)[0].name == "swisscom-apertus"
