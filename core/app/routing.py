"""Deterministic routing: service -> team, service -> criticality, team -> assignee.

Input:  a service name (from the classifier) and, for assignee, the open-ticket load.
Output: team (exact catalogue lookup), criticality (organisers' list), assignee (ours).
A model never decides any of this — service->team is 1:1 in the data, so it is a table.
Failure mode it prevents: hallucinated team names, and assignee picked by imitating the
dataset's random historical assignment.
"""

from __future__ import annotations

import difflib
from functools import lru_cache
from pathlib import Path

import yaml

CATALOGUE = Path(__file__).resolve().parent.parent / "data" / "catalogue.yaml"
UNKNOWN_TEAM = "Service Desk"  # safe landing zone: the team that owns Emailed Support Tickets


@lru_cache(maxsize=1)
def catalogue() -> dict:
    return yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))


def services() -> list[str]:
    return sorted(catalogue()["services"])


def teams() -> list[str]:
    return list(catalogue()["teams"])


def assignees() -> list[str]:
    return list(catalogue()["assignees"])


def canonical_service(name: str | None) -> str | None:
    """Map free text to a catalogue service. Exact, then case-insensitive, then close match.
    Returns None rather than guessing wildly — the caller flags that as unclear."""
    if not name:
        return None
    svc = catalogue()["services"]
    if name in svc:
        return name
    lower = {s.lower(): s for s in svc}
    if name.strip().lower() in lower:
        return lower[name.strip().lower()]
    match = difflib.get_close_matches(name.strip().lower(), list(lower), n=1, cutoff=0.85)
    return lower[match[0]] if match else None


def team_for(service: str | None) -> str:
    entry = catalogue()["services"].get(canonical_service(service) or "")
    return entry["team"] if entry else UNKNOWN_TEAM


def is_critical(service: str | None) -> bool:
    entry = catalogue()["services"].get(canonical_service(service) or "")
    return bool(entry) and entry["criticality"] == "critical"


def team_members(team: str) -> list[str]:
    """The dataset gives no real team membership (all 30 assignees appear under all 11
    teams), so we partition the global roster deterministically by team. This is OUR
    heuristic, disclosed in the README — swap it for the real rota when Swiss Life gives one."""
    roster = assignees()
    if not roster:
        return []
    all_teams = teams()
    if team not in all_teams:
        return roster
    i = all_teams.index(team)
    members = [a for n, a in enumerate(roster) if n % len(all_teams) == i]
    return members or roster


def pick_assignee(team: str, open_load: dict[str, int] | None = None) -> str | None:
    """Least-loaded member of the routed team; ties broken by name so it is reproducible.

    OUR heuristic, not an organiser rule: historical assignment in this data is random,
    so we optimise for balanced load instead of imitating noise.
    """
    members = team_members(team)
    if not members:
        return None
    load = open_load or {}
    return min(members, key=lambda a: (load.get(a, 0), a))
