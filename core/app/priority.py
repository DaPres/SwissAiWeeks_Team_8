"""Priority computed in code from the organisers' 5x5 matrix. The model never decides it.

Input:  urgency + impact as dataset levels (lowest..highest), plus the service (for overrides).
Output: a Priority level, the reason, and any overrides applied.
Two vocabularies meet here: the organisers' matrix labels (Critical..Lowest urgency x
Major..None impact) and the dataset's lowercase lowest..highest. MATRIX below is the
organisers' table verbatim; URGENCY_LABEL/IMPACT_LABEL are the only place the two are
mapped, and test_priority.py walks all 25 cells against the README table.
Failure mode it prevents: a silent mis-map that is invisible on stage and wrong on every
ticket, and priority drifting between runs of the same ticket.
"""

from __future__ import annotations

from app.routing import is_critical
from app.schemas import Level, Override

# --- the organisers' matrix, transcribed verbatim from docs/challenge.md -------------
# Rows = Urgency (Critical, High, Medium, Low, Lowest)
# Cols = Impact  (Major/Widespread, Significant/Large, Moderate/Limited, Minor/Localized, No direct impact)
MATRIX: dict[str, dict[str, str]] = {
    "Critical": {"Major": "Highest", "Significant": "Highest", "Moderate": "High", "Minor": "Medium", "None": "Medium"},
    "High":     {"Major": "Highest", "Significant": "High",    "Moderate": "High", "Minor": "Medium", "None": "Low"},
    "Medium":   {"Major": "High",    "Significant": "High",    "Moderate": "Medium", "Minor": "Low",  "None": "Low"},
    "Low":      {"Major": "Medium",  "Significant": "Medium",  "Moderate": "Low",  "Minor": "Low",    "None": "Lowest"},
    "Lowest":   {"Major": "Medium",  "Significant": "Low",     "Moderate": "Low",  "Minor": "Lowest", "None": "Lowest"},
}

# --- the label mapping: dataset level <-> organiser matrix label ---------------------
# The dataset stores urgency, impact AND priority on one lowercase 5-point scale.
# The matrix names the same 5 points differently per axis. This is the single mapping point.
URGENCY_LABEL: dict[Level, str] = {
    Level.HIGHEST: "Critical",
    Level.HIGH: "High",
    Level.MEDIUM: "Medium",
    Level.LOW: "Low",
    Level.LOWEST: "Lowest",
}
IMPACT_LABEL: dict[Level, str] = {
    Level.HIGHEST: "Major",        # Major / Widespread
    Level.HIGH: "Significant",     # Significant / Large
    Level.MEDIUM: "Moderate",      # Moderate / Limited
    Level.LOW: "Minor",            # Minor / Localized
    Level.LOWEST: "None",          # No direct impact / Information
}
PRIORITY_FROM_LABEL: dict[str, Level] = {
    "Highest": Level.HIGHEST,
    "High": Level.HIGH,
    "Medium": Level.MEDIUM,
    "Low": Level.LOW,
    "Lowest": Level.LOWEST,
}

# --- OUR overrides ------------------------------------------------------------------
# NOT organiser rules. Grounded only in the organisers' critical-service list.
# Kept as one small table so they are trivial to swap when Swiss Life give us the real ones.
OUR_OVERRIDES = [
    {
        "id": "critical_service_full_outage",
        "description": "Critical service with a full outage raises Impact to at least Significant",
        "min_impact": Level.HIGH,  # 'Significant' on the impact axis
    }
]
FULL_OUTAGE_CUES = ("full outage", "completely unavailable", "total outage", "is down", "unavailable to all", "cannot be used by anyone")


def _rank(level: Level) -> int:
    return [Level.LOWEST, Level.LOW, Level.MEDIUM, Level.HIGH, Level.HIGHEST].index(level)


def matrix_lookup(urgency: Level, impact: Level) -> Level:
    """The pure matrix: no overrides, no service context. Deterministic."""
    return PRIORITY_FROM_LABEL[MATRIX[URGENCY_LABEL[urgency]][IMPACT_LABEL[impact]]]


def apply_overrides(
    impact: Level, service: str | None, text: str = ""
) -> tuple[Level, list[Override]]:
    """Our only override: a Critical service in full outage cannot be below Significant impact."""
    applied: list[Override] = []
    low = text.lower()
    if is_critical(service) and any(cue in low for cue in FULL_OUTAGE_CUES):
        rule = OUR_OVERRIDES[0]
        if _rank(impact) < _rank(rule["min_impact"]):
            applied.append(
                Override(
                    rule=rule["id"],
                    effect=f"impact {impact.value} -> {rule['min_impact'].value} ({service} is a Critical service in full outage)",
                    ours=True,
                )
            )
            impact = rule["min_impact"]
    return impact, applied


def compute(
    urgency: Level, impact: Level, service: str | None = None, text: str = ""
) -> tuple[Level, Level, str, list[Override]]:
    """Returns (priority, effective_impact, reason, overrides). Same input -> same output."""
    effective_impact, overrides = apply_overrides(impact, service, text)
    priority = matrix_lookup(urgency, effective_impact)
    reason = (
        f"ITIL 5x5 matrix: urgency={URGENCY_LABEL[urgency]} x impact={IMPACT_LABEL[effective_impact]} "
        f"-> {priority.value}"
    )
    if overrides:
        reason += " (after our override: " + "; ".join(o.rule for o in overrides) + ")"
    return priority, effective_impact, reason, overrides
