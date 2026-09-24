"""Resolution status derived from OUR triage flags — never learned from the data.

Input:  the triage flags, confidence, loop signals and retrieved evidence.
Output: a Resolution status and the rule that produced it.
Resolution in the training data is random (measured: 25.5/25.0/24.9/24.6% across every
template, and `Status: done` carries all four), so it cannot be learned. The rules below are
ours, applied in priority order, and are documented in the README.
Failure mode it prevents: imitating a random label, and claiming `done` for a fix we cannot
support with a citation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas import Flags, Resolution

CONFIDENCE_FLOOR = 0.6

# Order matters: the first matching rule wins.
RULES = [
    ("injection_detected", "injection detected - not actioned", Resolution.CANCELLED),
    ("duplicate_of_open", "near-identical to an open ticket on the same service (parent named in the comment)", Resolution.CANCELLED),
    ("spam", "spam / not a service request", Resolution.CANCELLED),
    ("precedent_found", "a documented resolution pattern from a similar past ticket applies", Resolution.DONE),
    ("unclear_or_missing_info", "unclear or missing information, and no usable precedent", Resolution.CLARIFICATION),
    ("uncorroborated_alert", "alert with no corroborating evidence and nothing reproducible", Resolution.CANNOT_REPRODUCE),
    ("below_confidence_floor", f"confidence below {CONFIDENCE_FLOOR} - ask rather than guess", Resolution.CLARIFICATION),
    ("actionable_with_procedure", "actionable, with a matching resolution pattern", Resolution.DONE),
    ("no_matching_procedure", "actionable but no matching procedure found", Resolution.CLARIFICATION),
]


@dataclass
class ResolutionDecision:
    status: Resolution
    rule: str
    explanation: str


def decide(
    flags: Flags, confidence: float, *, is_alert: bool, has_citation: bool,
    escalated: bool = False, clarification_requested: bool = False,
    has_usable_precedent: bool = False,
) -> ResolutionDecision:
    """has_usable_precedent: retrieval found a relevant, substantively documented past ticket.

    The organisers' brief says that when a ticket lacks detail we should look for a similar
    historical ticket and follow its resolution pattern - so a precedent outranks `unclear`.
    We do NOT copy the precedent's own Resolution value: that field is random in this data.
    """
    def out(rule_id: str) -> ResolutionDecision:
        rule, explanation, status = next(r for r in RULES if r[0] == rule_id)
        return ResolutionDecision(status=status, rule=rule, explanation=explanation)

    if flags.injection:
        return out("injection_detected")
    # related_open alone is NOT a duplicate: sharing a service and a 4h window is common and
    # cancelled 25% of a dry run. flags.duplicate additionally requires near-identical text.
    if flags.duplicate:
        return out("duplicate_of_open")
    if flags.spam:
        return out("spam")
    if has_usable_precedent and not escalated:
        return out("precedent_found")
    if flags.unclear or clarification_requested:
        return out("unclear_or_missing_info")
    if is_alert and not has_citation:
        return out("uncorroborated_alert")
    if confidence < CONFIDENCE_FLOOR or escalated:
        return out("below_confidence_floor")
    if has_citation:
        return out("actionable_with_procedure")
    return out("no_matching_procedure")


def confidence_score(classifier: float, retrieval: float, self_report: float) -> float:
    """0.4 classifier + 0.4 retrieval + 0.2 the model's own confidence."""
    return round(min(max(0.4 * classifier + 0.4 * retrieval + 0.2 * self_report, 0.0), 1.0), 3)
