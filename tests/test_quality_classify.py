"""Quality-gate and classifier tests, built from the dataset's REAL trap templates
(18.59% of the queue). Fake LLM throughout: these must hold with every provider down."""

import pytest

from app.classify import classify
from app.llm.validated import ValidatedLLM
from app.quality import assess
from app.schemas import Ticket, WorkType
from tests.test_validated_llm import FakeClient

# Verbatim template openings from data/jira.json (service slot filled in).
TRAP_UNCLEAR = "The ticket text for Tax Reporting is unclear and not aligned with the expected service request pattern."
TRAP_MISMATCH_BODY = "This issue was raised against NAV Calculation, but the title suggests a service request instead of an incident."
TRAP_MISALIGNED = "The incident note for Fund Pricing is not aligned with the expected service context and contains mixed details."
NORMAL_INCIDENT = "A user reported an operational disruption in Fund Pricing. The issue description includes business context and the impact on daily operations."
ALERT = "Trading Platform generated an automated monitoring alert indicating an operational problem. The log shows repeated execution errors."


def t(desc, summary="", service=None, tid="T-1") -> Ticket:
    return Ticket(id=tid, summary=summary, description=desc, claimed_service=service)


# --- quality gate -------------------------------------------------------------------


def test_unclear_trap_is_flagged():
    q = assess(t(TRAP_UNCLEAR, "Request for Tax Reporting"))
    assert q.unclear and q.evidence


def test_misaligned_note_is_flagged():
    assert assess(t(TRAP_MISALIGNED, "Incident for Fund Pricing")).unclear


def test_explicit_title_mismatch_is_flagged():
    q = assess(t(TRAP_MISMATCH_BODY, "Incident: NAV Calculation down"))
    assert q.title_mismatch


def test_implicit_title_body_contradiction_is_flagged():
    q = assess(t("A user needs access to Tax Reporting to complete their daily tasks.",
                 "Outage: Tax Reporting is broken and failed"))
    assert q.title_mismatch and q.notes["body_work_type"] == "Service Request"


def test_empty_ticket_is_not_actionable():
    q = assess(t("", "Help"))
    assert q.unclear and not q.actionable


def test_gibberish_is_not_actionable():
    assert not assess(t("!!!! ???? ---- 12345 ....... @@@@@")).actionable


@pytest.mark.parametrize("desc,summary", [(NORMAL_INCIDENT, "Fund Pricing disruption"), (ALERT, "Automated alert triggered for Trading Platform")])
def test_normal_tickets_pass_the_gate(desc, summary):
    q = assess(t(desc, summary))
    assert q.actionable and not q.unclear and not q.title_mismatch


# --- classifier ---------------------------------------------------------------------


def fake_llm(*replies) -> ValidatedLLM:
    return ValidatedLLM(client=FakeClient(*replies))


def test_classifier_uses_model_answer_when_valid():
    llm = fake_llm('{"work_type":"Incident","service":"Fund Pricing","entity":"Nordics","reason":"pricing run failed"}')
    r = classify(t(NORMAL_INCIDENT, "Fund Pricing disruption"), NORMAL_INCIDENT, assess(t(NORMAL_INCIDENT)), llm)
    assert r.value.service == "Fund Pricing" and r.source == "ok"


def test_off_catalogue_service_is_snapped_back():
    llm = fake_llm('{"work_type":"Incident","service":"Made Up System","reason":"invented"}')
    r = classify(t(ALERT, "alert"), ALERT, assess(t(ALERT)), llm)
    assert r.value.service in __import__("app.routing", fromlist=["x"]).services()
    assert r.value.service == "Trading Platform"


def test_case_variant_service_is_canonicalised():
    llm = fake_llm('{"work_type":"Incident","service":"trading platform","reason":"x"}')
    r = classify(t(ALERT, "alert"), ALERT, assess(t(ALERT)), llm)
    assert r.value.service == "Trading Platform"


def test_deterministic_fallback_still_finds_the_service_with_no_model():
    llm = fake_llm("total garbage", "still garbage")
    r = classify(t(ALERT, "alert"), ALERT, assess(t(ALERT)), llm)
    assert r.source == "fallback" and r.value.service == "Trading Platform"


def test_wrong_claimed_service_is_reported_as_disagreement():
    llm = fake_llm('{"work_type":"Incident","service":"Fund Pricing","reason":"pricing"}')
    ticket = t(NORMAL_INCIDENT, "something", service="Outlook & Email")
    r = classify(ticket, NORMAL_INCIDENT, assess(ticket), llm)
    assert r.service_disagreement and r.claimed_service == "Outlook & Email"


def test_fallback_prefers_the_body_work_type_over_the_title():
    body = "A user needs access to Tax Reporting to complete their daily tasks."
    ticket = t(body, "Outage: everything failed and is broken")
    r = classify(ticket, body, assess(ticket), fake_llm("garbage", "garbage"))
    assert r.value.work_type == WorkType.SERVICE_REQUEST and r.value.service == "Tax Reporting"
