"""Two hard rules, enforced by test:

1. No unredacted text can reach any provider — asserted by inspecting exactly what the
   client received, not by trusting callers.
2. Model results are cached on disk by ticket id + task, so re-running a batch does not
   re-call the provider.
"""

import pytest

from app.llm import cache
from app.llm.validated import RedactionError, ValidatedLLM, assert_redacted
from app.schemas import ClassificationOut, WorkType
from tests.test_validated_llm import FakeClient

GOOD = '{"work_type":"Incident","service":"NAV Calculation","entity":null,"reason":"x"}'
FALLBACK = ClassificationOut(work_type=WorkType.INCIDENT, service="Emailed Support Tickets", reason="fb")
DIRTY = ("Reporter luca.rinaldi@intcom.com called +41 44 123 45 67 about IBAN "
         "CH93 0076 2011 6238 5295 7 and card 4111 1111 1111 1111.")


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    yield


def sent_text(client: FakeClient) -> str:
    """Everything that actually left for the provider, in one string."""
    return "\n".join(m["content"] for call in client.calls for m in call[0])


# --- rule 1: redaction --------------------------------------------------------------


def test_no_unredacted_text_can_reach_a_provider():
    c = FakeClient(GOOD)
    ValidatedLLM(client=c).call(ClassificationOut, "sys", DIRTY, FALLBACK)
    payload = sent_text(c)
    for secret in ("luca.rinaldi@intcom.com", "+41 44 123 45 67", "CH93 0076 2011 6238 5295 7", "4111 1111 1111 1111"):
        assert secret not in payload, f"{secret!r} leaked to the provider"
    assert "@intcom.com" not in payload and "[EMAIL]" in payload


def test_leak_is_caught_on_the_repair_turn_too():
    c = FakeClient("not json", GOOD)  # forces the repair round-trip
    ValidatedLLM(client=c).call(ClassificationOut, "sys", DIRTY, FALLBACK)
    assert "luca.rinaldi@intcom.com" not in sent_text(c)
    assert len(c.calls) == 2


def test_strict_mode_raises_so_a_regression_fails_the_build(monkeypatch):
    monkeypatch.setenv("LLM_STRICT_REDACTION", "1")
    with pytest.raises(RedactionError):
        assert_redacted(DIRTY, where="test")


def test_already_redacted_text_passes_through_unchanged():
    clean = "NAV Calculation alert: pricing run did not complete."
    assert assert_redacted(clean) == clean


# --- rule 2: caching ----------------------------------------------------------------


def test_second_call_is_served_from_disk_without_calling_the_provider():
    c = FakeClient(GOOD)
    llm = ValidatedLLM(client=c)
    first = llm.call(ClassificationOut, "sys", "NAV alert", FALLBACK, ticket_id="JIRA-1", task="classify")
    assert first.source == "ok" and len(c.calls) == 1

    c2 = FakeClient(GOOD)
    second = ValidatedLLM(client=c2).call(ClassificationOut, "sys", "NAV alert", FALLBACK, ticket_id="JIRA-1", task="classify")
    assert second.source == "cached" and second.value == first.value
    assert c2.calls == [], "cache hit must not reach the provider"


def test_cache_is_scoped_by_ticket_and_task():
    llm = lambda c: ValidatedLLM(client=c)  # noqa: E731
    c1 = FakeClient(GOOD)
    llm(c1).call(ClassificationOut, "sys", "text", FALLBACK, ticket_id="JIRA-1", task="classify")
    c2 = FakeClient(GOOD)
    llm(c2).call(ClassificationOut, "sys", "text", FALLBACK, ticket_id="JIRA-2", task="classify")
    assert len(c2.calls) == 1, "a different ticket must not hit the cache"
    c3 = FakeClient(GOOD)
    llm(c3).call(ClassificationOut, "sys", "text", FALLBACK, ticket_id="JIRA-1", task="extract")
    assert len(c3.calls) == 1, "a different task must not hit the cache"


def test_fallbacks_are_never_cached():
    c = FakeClient("garbage", "garbage")
    out = ValidatedLLM(client=c).call(ClassificationOut, "sys", "text", FALLBACK, ticket_id="JIRA-9", task="classify")
    assert out.is_fallback
    c2 = FakeClient(GOOD)
    ValidatedLLM(client=c2).call(ClassificationOut, "sys", "text", FALLBACK, ticket_id="JIRA-9", task="classify")
    assert len(c2.calls) == 1, "a fallback must not poison the cache"


def test_uncached_when_no_ticket_id():
    c = FakeClient(GOOD)
    ValidatedLLM(client=c).call(ClassificationOut, "sys", "text", FALLBACK)
    c2 = FakeClient(GOOD)
    ValidatedLLM(client=c2).call(ClassificationOut, "sys", "text", FALLBACK)
    assert len(c2.calls) == 1


def test_corrupt_cache_entry_does_not_break_the_run(tmp_path):
    c = FakeClient(GOOD)
    llm = ValidatedLLM(client=c)
    llm.call(ClassificationOut, "sys", "text", FALLBACK, ticket_id="JIRA-3", task="classify")
    for f in cache.CACHE_DIR.glob("*.json"):
        f.write_text("{not json", encoding="utf-8")
    c2 = FakeClient(GOOD)
    out = ValidatedLLM(client=c2).call(ClassificationOut, "sys", "text", FALLBACK, ticket_id="JIRA-3", task="classify")
    assert out.source == "ok" and len(c2.calls) == 1
