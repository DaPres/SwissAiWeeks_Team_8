"""Load-balanced assignee policy (app/assign.py)."""
from app.assign import Assigner


def ticket(agent: str, status: str = "done", service: str = "Trade Matching") -> dict:
    return {"Assignee": agent, "Status": status, "Affected Business or IT Services": [service]}


def test_batch_is_spread_over_the_whole_pool():
    a = Assigner.from_training([ticket(x) for x in ("ann", "bob", "cid")]).session()
    picked = [a.pick("Trade Matching", f"ticket {n}")[0] for n in range(6)]
    assert sorted(picked) == ["ann", "ann", "bob", "bob", "cid", "cid"]


def test_smallest_open_backlog_first_then_familiarity():
    history = [ticket("ann", "open"), ticket("ann", "in progress"), ticket("bob", "open"), ticket("cid", "open"),
               ticket("cid"), ticket("cid"), ticket("bob", service="NAV Calculation")]
    a = Assigner.from_training(history).session()
    # bob and cid tie on backlog (1 each); cid resolved more Trade Matching tickets
    assert a.pick("Trade Matching", "x")[0] == "cid"
    assert a.pick("Trade Matching", "y")[0] == "bob"
    assert a.pick("Trade Matching", "z")[0] == "ann"  # largest backlog comes last


def test_deterministic_and_sessions_are_independent():
    history = [ticket(x) for x in ("ann", "bob", "cid", "dan")]
    base = Assigner.from_training(history)
    first = [base.session().pick("Trade Matching", "same ticket")[0] for _ in range(3)]
    assert len(set(first)) == 1  # each session starts empty; the hash tie-break is stable
    s = base.session()
    s.pick("Trade Matching", "same ticket")
    assert base.session_load == {}  # batches don't leak into the shared history


def test_empty_pool():
    assert Assigner.from_training([]).session().pick("Trade Matching", "x") == (None, "no assignee pool available")
