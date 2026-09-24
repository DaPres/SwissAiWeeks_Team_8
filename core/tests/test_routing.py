"""Routing tests: every service in the dataset resolves to its known team, and the
assignee heuristic is load-balancing and reproducible."""

import json
from collections import defaultdict
from pathlib import Path

import pytest

from app import routing

DATA = Path(__file__).resolve().parent.parent / "data" / "jira.json"


def test_every_dataset_service_maps_to_its_known_team():
    if not DATA.exists():
        pytest.skip("data/jira.json not downloaded")
    pairs = defaultdict(set)
    for r in json.loads(DATA.read_text(encoding="utf-8")):
        pairs[r["Affected Business or IT Services"][0]].add(r["Service Team(s)"][0])
    assert len(pairs) == 20
    for service, teams in pairs.items():
        assert len(teams) == 1, f"{service} is not 1:1"
        assert routing.team_for(service) == next(iter(teams))


def test_catalogue_shape():
    assert len(routing.services()) == 20
    assert len(routing.teams()) == 11
    assert len(routing.assignees()) == 30


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("NAV Calculation", "NAV Calculation"),
        ("nav calculation", "NAV Calculation"),
        ("  Trading Platform ", "Trading Platform"),
        ("Trading Platfrom", "Trading Platform"),  # typo, close match
        ("Nonsense Service", None),
        (None, None),
    ],
)
def test_canonical_service(raw, expected):
    assert routing.canonical_service(raw) == expected


def test_unknown_service_lands_on_service_desk_not_a_guess():
    assert routing.team_for("Nonsense Service") == routing.UNKNOWN_TEAM


def test_criticality_comes_from_the_organiser_list():
    assert routing.is_critical("NAV Calculation")
    assert routing.is_critical("Trading Platform")
    assert not routing.is_critical("Tax Reporting")
    assert not routing.is_critical("Outlook & Email")


def test_pick_assignee_is_least_loaded_then_alphabetical():
    team = routing.teams()[0]
    members = routing.team_members(team)
    assert members, "team must have members"
    # all idle -> alphabetically first
    assert routing.pick_assignee(team, {}) == sorted(members)[0]
    # loaded first member -> someone else
    load = {sorted(members)[0]: 5}
    assert routing.pick_assignee(team, load) != sorted(members)[0]
    # deterministic across calls
    assert routing.pick_assignee(team, load) == routing.pick_assignee(team, load)


def test_assignee_is_always_in_the_routed_team():
    for team in routing.teams():
        assert routing.pick_assignee(team) in routing.team_members(team)
