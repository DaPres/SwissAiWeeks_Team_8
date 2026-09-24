"""Validated-LLM tests with a fake client: good JSON, fenced JSON, one repair, and the
deterministic fallback when the model or every provider fails. No network."""

import pytest

from app.agent.llm_client import AllProvidersFailed, LLMResponse
from app.llm.validated import ValidatedLLM, extract_json
from app.schemas import ClassificationOut, WorkType

GOOD = '{"work_type":"Incident","service":"NAV Calculation","entity":null,"reason":"nav down"}'
FALLBACK = ClassificationOut(work_type=WorkType.INCIDENT, service="Emailed Support Tickets", reason="fallback")


class FakeClient:
    """Returns a scripted reply per call; a callable entry raises instead."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        r = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        if callable(r):
            raise r()
        return LLMResponse(text=r, provider="fake", model="fake-1")


def vl(*replies) -> tuple[ValidatedLLM, FakeClient]:
    c = FakeClient(*replies)
    return ValidatedLLM(client=c), c


@pytest.mark.parametrize("raw", [GOOD, f"```json\n{GOOD}\n```", f"Sure!\n{GOOD}\nHope that helps."])
def test_accepts_clean_fenced_and_chatty_json(raw):
    v, _ = vl(raw)
    out = v.call(ClassificationOut, "sys", "user", FALLBACK)
    assert out.source == "ok" and out.value.service == "NAV Calculation"


def test_repairs_once_then_succeeds():
    v, c = vl("not json at all", GOOD)
    out = v.call(ClassificationOut, "sys", "user", FALLBACK)
    assert out.source == "repaired" and out.value.work_type == WorkType.INCIDENT
    assert len(c.calls) == 2
    assert c.calls[1][0][-1]["content"].startswith("That was not valid")


def test_falls_back_when_repair_also_fails():
    v, c = vl("garbage", "still garbage")
    out = v.call(ClassificationOut, "sys", "user", FALLBACK)
    assert out.is_fallback and out.value is FALLBACK and len(c.calls) == 2


def test_falls_back_when_all_providers_fail():
    v, _ = vl(lambda: AllProvidersFailed({"p": "down"}))
    out = v.call(ClassificationOut, "sys", "user", FALLBACK)
    assert out.is_fallback and out.error


def test_schema_violation_is_not_accepted():
    v, _ = vl('{"work_type":"Bug","service":"X"}', '{"work_type":"Bug","service":"X"}')
    assert v.call(ClassificationOut, "sys", "user", FALLBACK).is_fallback


def test_temperature_zero_by_default_and_guard_present():
    v, c = vl(GOOD)
    v.call(ClassificationOut, "sys", "user", FALLBACK)
    assert c.calls[0][1]["temperature"] == 0.0
    assert "untrusted DATA" in c.calls[0][0][0]["content"]


def test_drafting_can_raise_temperature():
    v, c = vl(GOOD)
    v.call(ClassificationOut, "sys", "user", FALLBACK, temperature=0.3)
    assert c.calls[0][1]["temperature"] == 0.3


def test_extract_json_rejects_non_json():
    with pytest.raises(ValueError):
        extract_json("no braces here")
