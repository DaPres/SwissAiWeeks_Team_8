"""Retrieval tests: template dedupe, service filtering, resolution-quality ranking, the
score floor, and the similar-ticket assignee. Small synthetic corpus, no network."""

import json

import pytest

from app import store
from app.rag.hybrid import SCORE_FLOOR, HybridIndex, retrieval_confidence
from app.rag.patterns import build_patterns, resolution_quality, signature
from app.rag.tickets import (
    find_open_related,
    find_similar_tickets,
    suggest_assignee,
    suggest_assignee_from_patterns,
)

ALERT = "{svc} generated an automated monitoring alert indicating an operational problem."
ACCESS = "A user needs access to {svc} to complete their daily tasks."

RICH = [
    "a@x.com: Initial triage assigned to Valuation & Pricing and reviewed against the service catalogue.",
    "b@x.com: We validated the issue against NAV Calculation and checked the overnight pricing run.",
    "c@x.com: Impact assessment confirmed the issue affected the operational workflow.",
]
FILLER = ["a@x.com: Problem fixed."]


def _row(i, desc, svc, team, wt="Incident", res="done", comments=None, status="done", assignee="a@x.com", created="2026-03-03 10:00"):
    return {
        "Work type": wt, "Summary": f"Ticket {i}", "Description": desc,
        "Affected Business or IT Services": [svc], "Business Entity": ["Nordics"],
        "Service Team(s)": [team], "Reporter": "r@x.com", "Assignee": assignee,
        "Priority": "low", "Urgency": "low", "Impact": "low", "Created date": created,
        "Status": status, "Resolution": res, "Resolution date": "2026-03-04 10:00",
        "All Comments": comments if comments is not None else FILLER,
    }


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("rag")
    rows = [
        _row(1, ALERT.format(svc="NAV Calculation"), "NAV Calculation", "Valuation & Pricing", comments=FILLER),
        _row(2, ALERT.format(svc="NAV Calculation"), "NAV Calculation", "Valuation & Pricing", comments=RICH, assignee="rich@x.com"),
        _row(3, ALERT.format(svc="NAV Calculation"), "NAV Calculation", "Valuation & Pricing", comments=FILLER),
        _row(4, ALERT.format(svc="Trading Platform"), "Trading Platform", "Investment Operations", comments=RICH),
        _row(5, ACCESS.format(svc="Tax Reporting"), "Tax Reporting", "Tax & Reporting", wt="Service Request", comments=RICH),
        _row(6, ALERT.format(svc="NAV Calculation"), "NAV Calculation", "Valuation & Pricing",
             res=None, status="open", created="2026-03-03 11:00", assignee="open@x.com"),
    ]
    src = tmp / "jira.json"
    src.write_text(json.dumps(rows), encoding="utf-8")
    c = store.connect(tmp / "t.db")
    store.load_corpus(c, src)
    return c


@pytest.fixture(scope="module")
def index(con):
    return HybridIndex.from_store(con)


# --- signatures and quality ---------------------------------------------------------


def test_signature_masks_service_so_clones_collapse():
    assert signature(ALERT.format(svc="NAV Calculation")) == signature(ALERT.format(svc="Trading Platform"))
    assert signature(ALERT.format(svc="NAV Calculation")) != signature(ACCESS.format(svc="NAV Calculation"))


def test_resolution_quality_ranks_substance_over_filler():
    assert resolution_quality(FILLER) < 0.1
    assert resolution_quality(RICH) > 0.7
    assert resolution_quality([]) == 0.0


def test_patterns_group_clones_and_keep_the_best_exemplar(con):
    pats = build_patterns(con)
    nav_alert = [p for p in pats if p.service == "NAV Calculation" and "alert" in p.text.lower()]
    assert len(nav_alert) == 1, "clones must collapse into one pattern"
    p = nav_alert[0]
    assert p.size == 4 and p.best_ticket_id == "JIRA-00002"  # the richly documented one
    assert p.best_quality > 0.7


# --- hybrid search ------------------------------------------------------------------


def test_search_returns_distinct_patterns_not_clones(index):
    hits = index.search("automated monitoring alert operational problem", k=5)
    sigs = [h.pattern.signature for h in hits]
    assert len(sigs) == len(set(sigs)), "results must be distinct templates"


def test_service_filter(index):
    hits = index.search("automated monitoring alert", service="Trading Platform", k=5)
    assert hits and all(h.pattern.service == "Trading Platform" for h in hits)


def test_citation_id_is_a_ticket_id(index):
    hits = index.search("automated monitoring alert", service="NAV Calculation")
    assert hits[0].citation_id.startswith("JIRA-")


def test_score_floor_reports_low_confidence_for_nonsense(index):
    hits = index.search("xylophone quantum gardening tournament")
    assert retrieval_confidence(hits) < 0.5
    assert retrieval_confidence([]) == 0.0


def test_confidence_is_higher_for_a_real_match(index):
    good = index.search("A user needs access to Tax Reporting to complete their daily tasks.")
    assert good and good[0].score > SCORE_FLOOR
    assert retrieval_confidence(good) > 0.5


# --- ticket-level -------------------------------------------------------------------


def test_similar_tickets_prefer_documented_resolutions(con, index):
    sims = find_similar_tickets(con, index, ALERT.format(svc="NAV Calculation"), service="NAV Calculation")
    assert sims and sims[0].id == "JIRA-00002"
    assert sims[0].quality > 0.7 and "validated" in sims[0].comment


def test_similar_tickets_respect_work_type(con, index):
    sims = find_similar_tickets(con, index, ACCESS.format(svc="Tax Reporting"), work_type="Service Request")
    assert all(s.work_type == "Service Request" for s in sims)


def test_open_related_finds_the_open_clone(con, monkeypatch):
    monkeypatch.setenv("RELATED_WINDOW_HOURS", "4")
    rel = find_open_related(con, "NAV Calculation", "2026-03-03 10:00", exclude_id="JIRA-00001")
    assert [t.id for t in rel] == ["JIRA-00006"]


def test_assignee_comes_from_the_most_similar_ticket(con, index):
    sims = find_similar_tickets(con, index, ALERT.format(svc="NAV Calculation"), service="NAV Calculation")
    who, reason = suggest_assignee(sims)
    assert who == "rich@x.com" and "most similar ticket" in reason


def test_pattern_modal_assignee_polls_the_whole_pattern(con, index):
    # JIRA-1/2/3 share a pattern: a@x.com twice, rich@x.com once -> modal is a@x.com,
    # unlike the exemplar method which would pick the best-documented ticket's assignee.
    who, reason = suggest_assignee_from_patterns(
        con, index, ALERT.format(svc="NAV Calculation"), service="NAV Calculation", work_type="Incident"
    )
    assert who == "a@x.com" and "most frequent" in reason


def test_pattern_modal_excludes_the_query_ticket(con, index):
    who, _ = suggest_assignee_from_patterns(
        con, index, ALERT.format(svc="Trading Platform"), service="Trading Platform", exclude_id="JIRA-00004"
    )
    assert who != "JIRA-00004"


def test_assignee_falls_back_to_team_when_nothing_similar():
    who, reason = suggest_assignee([], team_fallback=["z@x.com", "a@x.com"])
    assert who == "a@x.com" and "no similar ticket" in reason
