"""Tests for the four dry-run fixes:
2 priority calibration prompt, 3 citation enforcement, 4 duplicate gating,
1 retrieval-before-clarification ordering."""

import json

import pytest

from app import store
from app.agent.tools import ToolContext, run_tool
from app.draft import enforce_citation
import re

from app.pipeline import EXTRACT_SYSTEM
from app.rag.hybrid import HybridIndex
from app.rag.tickets import find_duplicates, text_similarity
from app.resolution import decide
from app.schemas import Citation, Flags, Resolution

ALERT = "NAV Calculation generated an automated monitoring alert indicating an operational problem."
OTHER = "A user needs access to Tax Reporting to complete their daily tasks."
RICH = ["a@x.com: We validated the issue against NAV Calculation and checked the overnight pricing run.",
        "b@x.com: Impact assessment confirmed the issue affected the operational workflow."]


# --- fix 2: the organisers' definitions are present verbatim ------------------------


@pytest.mark.parametrize("phrase", [
    "full unavailability to critical IT services supporting key operations (> 2 hrs downtime)",
    "partial unavailability of critical IT services, 1+ business",
    "full unavailability of non-critical IT services, or up to",
    "partial unavailability of non-critical IT services, or",
    "no direct operational impact",
    "immediate action required",
    "rapid resolution needed within hours",
    "Easy workaround available",
    "handled in normal workflow without urgent escalation",
    "routine/informational with no effect on operations",
])
def test_extract_prompt_carries_the_organiser_definitions(phrase):
    # the prompt wraps lines, so compare on whitespace-normalised text
    flat = re.sub(r"\s+", " ", EXTRACT_SYSTEM)
    assert phrase in flat


def test_extract_prompt_blocks_critical_service_inflation():
    assert "raises the CEILING" in EXTRACT_SYSTEM
    assert "It is NOT Major." in EXTRACT_SYSTEM


# --- fix 3: citation enforcement is mechanical --------------------------------------


def test_missing_citation_is_appended():
    out = enforce_citation("Determined a failed pricing run.", [Citation(id="JIRA-00042")])
    assert out.endswith("[JIRA-00042]")


def test_existing_citation_is_left_alone():
    text = "Followed the pattern in [JIRA-00099]."
    assert enforce_citation(text, [Citation(id="JIRA-00042")]) == text


def test_no_evidence_is_stated_not_faked():
    out = enforce_citation("Nothing matched this ticket.", [])
    assert "no supporting ticket found" in out and "JIRA" not in out


def test_bare_brackets_do_not_count_as_a_citation():
    out = enforce_citation("Checked the log [see attachment].", [Citation(id="JIRA-00042")])
    assert out.endswith("[JIRA-00042]")


# --- fix 4: duplicates need similarity too ------------------------------------------


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("fixes")
    rows = []
    for i, (desc, status) in enumerate([(ALERT, "open"), (ALERT, "open"), (OTHER, "open")], 1):
        rows.append({"Work type": "Incident", "Summary": f"T{i}", "Description": desc,
                     "Affected Business or IT Services": ["NAV Calculation" if desc == ALERT else "Tax Reporting"],
                     "Business Entity": ["Nordics"], "Service Team(s)": ["Valuation & Pricing"],
                     "Reporter": "r@x.com", "Assignee": "a@x.com", "Priority": "low", "Urgency": "low",
                     "Impact": "low", "Created date": "2026-03-03 10:00", "Status": status,
                     "Resolution": None, "Resolution date": None, "All Comments": RICH})
    src = tmp / "jira.json"
    src.write_text(json.dumps(rows), encoding="utf-8")
    con = store.connect(tmp / "t.db")
    store.load_corpus(con, src)
    return con, HybridIndex.from_store(con)


def test_text_similarity_separates_clones_from_neighbours():
    assert text_similarity(ALERT, ALERT) == 1.0
    assert text_similarity(ALERT, OTHER) < 0.3


def test_duplicate_requires_near_identical_text(env):
    con, _ = env
    dupes = find_duplicates(con, ALERT, "NAV Calculation", "2026-03-03 10:00", exclude_id="JIRA-00001")
    assert [t.id for t, _ in dupes] == ["JIRA-00002"]
    # a different ticket on the same service in the same window is NOT a duplicate
    assert find_duplicates(con, OTHER, "NAV Calculation", "2026-03-03 10:00", exclude_id="JIRA-00001") == []


def test_related_open_alone_no_longer_cancels():
    d = decide(Flags(related_open=["JIRA-00002"]), 0.9, is_alert=False, has_citation=True)
    assert d.status is not Resolution.CANCELLED
    d2 = decide(Flags(duplicate=True, related_open=["JIRA-00002"]), 0.9, is_alert=False, has_citation=True)
    assert d2.status is Resolution.CANCELLED and "parent named" in d2.explanation


def test_tool_separates_related_from_duplicates(env):
    con, index = env
    ctx = ToolContext(con=con, index=index, ticket_id="JIRA-00001", created="2026-03-03 10:00",
                      default_service="NAV Calculation", ticket_text=ALERT)
    out = run_tool("find_open_related", {"service": "NAV Calculation"}, ctx)
    assert [d["id"] for d in out["duplicates"]] == ["JIRA-00002"]
    assert "related_open" in out and out["duplicates"][0]["similarity"] >= 0.75


# --- fix 1: retrieval before clarification ------------------------------------------


def test_clarification_rejected_before_any_retrieval(env):
    con, index = env
    ctx = ToolContext(con=con, index=index, ticket_text=ALERT, default_service="NAV Calculation")
    out = run_tool("request_clarification", {"missing": "the exact error code from the log"}, ctx)
    assert out["rejected"] and "Retrieval has not been attempted" in out["reason"]
    assert ctx.clarification is None


def test_clarification_rejected_when_a_precedent_exists(env):
    con, index = env
    ctx = ToolContext(con=con, index=index, ticket_text=ALERT, default_service="NAV Calculation")
    run_tool("search_kb", {"query": ALERT, "service": "NAV Calculation"}, ctx)
    assert ctx.usable_precedent, "a richly documented clone should register as a precedent"
    out = run_tool("request_clarification", {"missing": "the exact error code from the log"}, ctx)
    assert out["rejected"] and "usable precedent" in out["reason"]


def test_generic_clarification_is_rejected(env):
    con, index = env
    ctx = ToolContext(con=con, index=index, ticket_text=OTHER, default_service="Tax Reporting")
    ctx.retrieval_attempted = True
    for generic in ("more details", "more information please", "clarify the issue"):
        out = run_tool("request_clarification", {"missing": generic}, ctx)
        assert out["rejected"] and "SPECIFIC" in out["reason"]
    assert ctx.clarification is None


def test_specific_clarification_is_accepted_after_failed_retrieval(env):
    con, index = env
    ctx = ToolContext(con=con, index=index, ticket_text=OTHER, default_service="Tax Reporting")
    ctx.retrieval_attempted = True  # retrieval ran and found nothing usable
    out = run_tool("request_clarification",
                   {"missing": "the error code, the affected user count and the time the batch failed"}, ctx)
    assert out.get("accepted") and ctx.clarification


def test_precedent_outranks_unclear_in_the_resolution_rules():
    d = decide(Flags(unclear=True), 0.9, is_alert=False, has_citation=True, has_usable_precedent=True)
    assert d.status is Resolution.DONE and d.rule == "precedent_found"
    # without a precedent, unclear still asks
    d2 = decide(Flags(unclear=True), 0.9, is_alert=False, has_citation=True)
    assert d2.status is Resolution.CLARIFICATION


def test_injection_still_outranks_a_precedent():
    d = decide(Flags(injection=True), 0.9, is_alert=False, has_citation=True, has_usable_precedent=True)
    assert d.status is Resolution.CANCELLED
