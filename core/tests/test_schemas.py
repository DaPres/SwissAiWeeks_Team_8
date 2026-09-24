"""Contract tests: the result contract round-trips, rejects malformed LLM output, and can
emit the graded fields alone in the challenge's field names."""

import pytest
from pydantic import ValidationError

from app.schemas import (
    ClassificationOut,
    Evidence,
    Flags,
    GradedFields,
    Level,
    Resolution,
    Ticket,
    TriageResult,
    UrgencyImpactOut,
    WorkType,
)


def _result(**kw) -> TriageResult:
    base = dict(
        graded=GradedFields(
            work_type=WorkType.INCIDENT,
            service="NAV Calculation",
            team="Valuation & Pricing",
            assignee="a@intcom.com",
            priority=Level.HIGH,
            resolution=Resolution.DONE,
            resolution_comment="Checked feed [T-1].",
        ),
        urgency=Evidence(value=Level.HIGH, quote="NAV cannot be published."),
        impact=Evidence(value=Level.MEDIUM, quote="One entity affected."),
    )
    return TriageResult(**(base | kw))


def test_round_trip():
    r = _result()
    assert TriageResult.model_validate_json(r.model_dump_json()) == r


def test_submission_has_only_graded_fields_and_challenge_names():
    s = _result().submission()
    assert s["Work type"] == "Incident"
    assert s["Affected Business or IT Services"] == ["NAV Calculation"]
    assert s["Service Team(s)"] == ["Valuation & Pricing"]
    assert s["Priority"] == "high" and s["Resolution"] == "done"
    # internals must never leak into a submission
    for leaked in ("confidence", "trace", "flags", "citations", "draft_reply"):
        assert leaked not in s


def test_description_outranks_summary_in_text():
    t = Ticket(id="T-1", summary="Password reset", description="Trading platform is down.")
    assert t.text().index("Trading platform") < t.text().index("Password reset")


@pytest.mark.parametrize(
    "payload",
    [
        {"work_type": "Bug", "service": "X"},  # not in the vocabulary
        {"service": "X"},  # missing work_type
        {"work_type": "Incident"},  # missing service
    ],
)
def test_malformed_classification_is_rejected(payload):
    with pytest.raises(ValidationError):
        ClassificationOut.model_validate(payload)


def test_malformed_urgency_impact_is_rejected():
    with pytest.raises(ValidationError):
        UrgencyImpactOut.model_validate({"urgency": {"value": "severe"}, "impact": {"value": "low"}})


def test_confidence_is_bounded():
    with pytest.raises(ValidationError):
        _result(confidence=1.4)


def test_flags_badges():
    f = Flags(injection=True, unclear=True, related_open=["T-9"])
    assert "injection" in f.badges() and "duplicate_of:T-9" in f.badges()
