"""Priority tests. The grid below is re-transcribed from docs/challenge.md INDEPENDENTLY of
app/priority.py, so a typo in either table fails the build. All 25 cells are walked, plus
determinism, the label mapping, and our one override."""

import pytest

from app.priority import IMPACT_LABEL, URGENCY_LABEL, compute, matrix_lookup
from app.schemas import Level

# Rows: urgency Critical->Lowest. Cols: impact Major, Significant, Moderate, Minor, None.
# Transcribed by hand from the organisers' table in docs/challenge.md.
ORGANISER_GRID = """
Critical | Highest | Highest | High   | Medium | Medium
High     | Highest | High    | High   | Medium | Low
Medium   | High    | High    | Medium | Low    | Low
Low      | Medium  | Medium  | Low    | Low    | Lowest
Lowest   | Medium  | Low     | Low    | Lowest | Lowest
"""

# matrix label -> dataset level, written out again here on purpose
URGENCY_FROM_LABEL = {"Critical": Level.HIGHEST, "High": Level.HIGH, "Medium": Level.MEDIUM,
                      "Low": Level.LOW, "Lowest": Level.LOWEST}
IMPACT_COLS = [Level.HIGHEST, Level.HIGH, Level.MEDIUM, Level.LOW, Level.LOWEST]
PRIORITY_FROM_LABEL = {"Highest": Level.HIGHEST, "High": Level.HIGH, "Medium": Level.MEDIUM,
                       "Low": Level.LOW, "Lowest": Level.LOWEST}


def cells():
    for line in ORGANISER_GRID.strip().splitlines():
        label, *vals = [c.strip() for c in line.split("|")]
        for impact, want in zip(IMPACT_COLS, vals):
            yield URGENCY_FROM_LABEL[label], impact, PRIORITY_FROM_LABEL[want]


@pytest.mark.parametrize("urgency,impact,expected", list(cells()))
def test_all_25_cells_match_the_organiser_matrix(urgency, impact, expected):
    assert matrix_lookup(urgency, impact) is expected


def test_grid_really_has_25_cells():
    assert len(list(cells())) == 25


def test_label_mapping_is_a_bijection():
    assert set(URGENCY_LABEL.values()) == {"Critical", "High", "Medium", "Low", "Lowest"}
    assert set(IMPACT_LABEL.values()) == {"Major", "Significant", "Moderate", "Minor", "None"}
    assert len(set(URGENCY_LABEL)) == len(set(IMPACT_LABEL)) == 5


def test_same_ticket_same_priority():
    args = (Level.HIGH, Level.MEDIUM, "NAV Calculation", "The service is down for everyone.")
    assert compute(*args) == compute(*args)


def test_critical_service_full_outage_raises_impact():
    priority, impact, reason, overrides = compute(
        Level.MEDIUM, Level.LOW, "Trading Platform", "Trading Platform is down for all traders."
    )
    assert impact is Level.HIGH  # 'Significant'
    assert overrides and overrides[0].ours is True
    assert priority is matrix_lookup(Level.MEDIUM, Level.HIGH)
    assert "override" in reason


def test_override_never_applies_to_non_critical_service():
    _, impact, _, overrides = compute(Level.MEDIUM, Level.LOW, "Tax Reporting", "Tax Reporting is down.")
    assert impact is Level.LOW and overrides == []


def test_override_never_lowers_impact():
    _, impact, _, overrides = compute(
        Level.MEDIUM, Level.HIGHEST, "Trading Platform", "Trading Platform is down."
    )
    assert impact is Level.HIGHEST and overrides == []


def test_no_override_without_outage_language():
    _, impact, _, overrides = compute(
        Level.MEDIUM, Level.LOW, "Trading Platform", "A user asks about a report layout."
    )
    assert impact is Level.LOW and overrides == []


def test_every_override_is_marked_as_ours():
    _, _, _, overrides = compute(Level.LOW, Level.LOWEST, "NAV Calculation", "NAV Calculation is down.")
    assert all(o.ours for o in overrides)
