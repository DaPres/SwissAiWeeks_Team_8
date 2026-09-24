"""Quality gate: is this ticket actionable, and does its title contradict its body?

Input:  a Ticket (already safety-screened).
Output: QualityReport — unclear / title_mismatch flags with the evidence that triggered them.
Deterministic cues first (they cover the dataset's trap templates and cost nothing); the
LLM is only consulted by the classifier afterwards, never to re-decide these flags.
Failure mode it prevents: writing a confident answer to a ticket that says nothing, and
trusting a title that disagrees with the body — 18.59% of the queue is exactly that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas import Ticket, WorkType

MIN_ACTIONABLE_CHARS = 40

# Cues lifted from the dataset's own trap templates, plus generic vagueness.
UNCLEAR_CUES = (
    "is unclear",
    "not aligned with the expected",
    "without clear",
    "no clear",
    "insufficient information",
    "cannot be determined",
    "does not contain enough",
    "missing details",
)
MISMATCH_CUES = (
    "but the title suggests",
    "the title suggests",
    "the submitted title suggests",
    "title does not match",
    "contrary to the title",
)

# Work-type language, used only to cross-check title vs body.
REQUEST_CUES = ("request", "please provide", "needs access", "requires a license", "onboarding", "remove access", "new user")
INCIDENT_CUES = ("outage", "failed", "error", "not working", "degraded", "alert", "broken", "unavailable", "crash")


@dataclass
class QualityReport:
    unclear: bool = False
    title_mismatch: bool = False
    actionable: bool = True
    evidence: list[str] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)


def _hits(text: str, cues: tuple[str, ...]) -> list[str]:
    low = text.lower()
    return [c for c in cues if c in low]


def _implied_work_type(text: str) -> WorkType | None:
    low = text.lower()
    req = sum(1 for c in REQUEST_CUES if c in low)
    inc = sum(1 for c in INCIDENT_CUES if c in low)
    if req > inc:
        return WorkType.SERVICE_REQUEST
    if inc > req:
        return WorkType.INCIDENT
    return None


def assess(ticket: Ticket) -> QualityReport:
    r = QualityReport()
    body, title = ticket.description or "", ticket.summary or ""
    combined = f"{body} {title}"

    if len(body.strip()) < MIN_ACTIONABLE_CHARS:
        r.unclear, r.actionable = True, False
        r.evidence.append(f"description is only {len(body.strip())} chars")
    if hits := _hits(combined, UNCLEAR_CUES):
        r.unclear = True
        r.evidence.append(f"unclear cue: {hits[0]!r}")
    if not re.search(r"[a-zA-Z]{3}", body):
        r.unclear, r.actionable = True, False
        r.evidence.append("description has no readable text")

    if hits := _hits(combined, MISMATCH_CUES):
        r.title_mismatch = True
        r.evidence.append(f"explicit mismatch cue: {hits[0]!r}")
    t_type, b_type = _implied_work_type(title), _implied_work_type(body)
    if t_type and b_type and t_type != b_type:
        r.title_mismatch = True
        r.evidence.append(f"title reads as {t_type.value}, body reads as {b_type.value}")
        r.notes["body_work_type"] = b_type.value  # the body wins downstream

    if r.unclear and not r.evidence:
        r.evidence.append("unclear")
    return r
