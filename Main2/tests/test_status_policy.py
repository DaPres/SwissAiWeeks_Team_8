"""Resolution-status policy: ask rather than guess when the system is not confident."""
from __future__ import annotations

from types import SimpleNamespace

from triagemate import resolutions as R


def _flags(**kw):
    base = dict(injection=False, unclear=False, title_mismatch=False, duplicate=False, low_confidence=False)
    base.update(kw)
    return SimpleNamespace(**base)


def _cls(service="Trading Platform", unclear=False):
    return SimpleNamespace(service=service, unclear=unclear)


def test_low_confidence_without_a_comparable_resolution_asks_for_clarification():
    status, why = R.decide_status(_cls(), _flags(low_confidence=True), "where are my trades i cannot see", False, None)
    assert status == "clarification" and "ask rather than guess" in why


def test_low_confidence_with_a_matching_playbook_still_resolves():
    assert R.decide_status(_cls(), _flags(low_confidence=True), "mailbox is full", True, None)[0] == "done"


def test_confident_actionable_ticket_is_done_and_duplicates_are_still_cancelled():
    assert R.decide_status(_cls(), _flags(), "orders are stuck in pending approval", False, None)[0] == "done"
    assert R.decide_status(_cls(), _flags(low_confidence=True), "orders are stuck", False, "INC-1")[0] == "cancelled"
