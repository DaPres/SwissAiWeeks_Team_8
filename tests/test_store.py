"""Store tests: corpus load, open-ticket load for assignee balancing, the related-ticket
window, and durable results/decisions. Uses a temp DB and a synthetic corpus — no network."""

import json

import pytest

from app import store
from app.schemas import Evidence, GradedFields, Level, Resolution, TriageResult, WorkType


@pytest.fixture
def con(tmp_path):
    rows = [
        {  # 0: open, in window
            "Work type": "Incident", "Summary": "Alert A", "Description": "NAV alert",
            "Affected Business or IT Services": ["NAV Calculation"], "Business Entity": ["Nordics"],
            "Service Team(s)": ["Valuation & Pricing"], "Reporter": "r@x.com", "Assignee": "a@x.com",
            "Priority": "low", "Urgency": "low", "Impact": "low", "Created date": "2026-03-03 10:00",
            "Status": "open", "Resolution": None, "Resolution date": None, "All Comments": ["a@x.com: looked"],
        },
        {  # 1: open, same service, 2h later -> related
            "Work type": "Incident", "Summary": "Alert B", "Description": "NAV alert again",
            "Affected Business or IT Services": ["NAV Calculation"], "Business Entity": ["Nordics"],
            "Service Team(s)": ["Valuation & Pricing"], "Reporter": "r@x.com", "Assignee": "b@x.com",
            "Priority": "low", "Urgency": "low", "Impact": "low", "Created date": "2026-03-03 12:00",
            "Status": "in progress", "Resolution": None, "Resolution date": None, "All Comments": [],
        },
        {  # 2: done -> never related
            "Work type": "Incident", "Summary": "Alert C", "Description": "NAV alert closed",
            "Affected Business or IT Services": ["NAV Calculation"], "Business Entity": ["Nordics"],
            "Service Team(s)": ["Valuation & Pricing"], "Reporter": "r@x.com", "Assignee": "a@x.com",
            "Priority": "low", "Urgency": "low", "Impact": "low", "Created date": "2026-03-03 11:00",
            "Status": "done", "Resolution": "done", "Resolution date": "2026-03-04 11:00", "All Comments": [],
        },
        {  # 3: different service
            "Work type": "Service Request", "Summary": "Access", "Description": "Need access",
            "Affected Business or IT Services": ["Tax Reporting"], "Business Entity": ["Nordics"],
            "Service Team(s)": ["Tax & Reporting"], "Reporter": "r@x.com", "Assignee": "c@x.com",
            "Priority": "low", "Urgency": "low", "Impact": "low", "Created date": "2026-03-03 11:00",
            "Status": "open", "Resolution": None, "Resolution date": None, "All Comments": [],
        },
    ]
    src = tmp_path / "jira.json"
    src.write_text(json.dumps(rows), encoding="utf-8")
    c = store.connect(tmp_path / "t.db")
    store.load_corpus(c, src)
    return c


def test_corpus_loads_with_ids(con):
    assert store.ticket_count(con) == 4
    t = store.get_ticket(con, "JIRA-00001")
    assert t.claimed_service == "NAV Calculation" and t.comments == ["a@x.com: looked"]


def test_open_load_counts_only_open_and_in_progress(con):
    assert store.open_load(con) == {"a@x.com": 1, "b@x.com": 1, "c@x.com": 1}


def test_find_open_related_same_service_recent_not_done(con):
    rel = store.find_open_related(con, "NAV Calculation", "2026-03-03 10:00", 4, exclude_id="JIRA-00001")
    assert [t.id for t in rel] == ["JIRA-00002"]  # not the done one, not Tax Reporting


def test_related_window_is_configurable(con):
    assert store.find_open_related(con, "NAV Calculation", "2026-03-03 10:00", 1, "JIRA-00001") == []
    assert len(store.find_open_related(con, "NAV Calculation", "2026-03-03 10:00", 24, "JIRA-00001")) == 1


def test_bad_date_does_not_explode(con):
    assert store.find_open_related(con, "NAV Calculation", "not-a-date", 4) == []


def test_results_and_decisions_round_trip(con):
    r = TriageResult(
        ticket_id="JIRA-00001",
        graded=GradedFields(work_type=WorkType.INCIDENT, service="NAV Calculation",
                            team="Valuation & Pricing", priority=Level.HIGH, resolution=Resolution.DONE),
        urgency=Evidence(value=Level.HIGH), impact=Evidence(value=Level.MEDIUM),
    )
    store.save_result(con, r)
    assert store.get_result(con, "JIRA-00001").graded.service == "NAV Calculation"

    store.save_decision(con, "JIRA-00001", "approve", dwell_seconds=12.5)
    store.save_decision(con, "JIRA-00001", "edit", reason="tone", edit_distance=20, dwell_seconds=30)
    m = store.decision_metrics(con)
    assert m["total_decisions"] == 2 and m["approval_rate"] == 0.5
    assert m["by_decision"]["edit"]["avg_edit_distance"] == 20
