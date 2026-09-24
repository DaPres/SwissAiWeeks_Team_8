"""The result contract every TriageMate stage codes against.

Input:  a raw Jira-shaped ticket (Ticket), possibly with wrong/missing fields on purpose.
Output: TriageResult — the 7 graded fields (GradedFields) plus our internals (flags,
        citations, confidence, trace). `result.graded` alone emits the exact submission format.
Also holds the small schemas the LLM must fill (ClassificationOut, UrgencyImpactOut,
DraftOut): each is validated, repaired once, then replaced by a deterministic fallback.
Failure mode it prevents: stages inventing their own dict shapes, and un-validated model
output reaching the UI or the submission file.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

# --- vocabularies -------------------------------------------------------------------
# Lowercase everywhere, matching the dataset. The organisers' matrix uses different
# labels for the same 5 points; app/priority.py owns that mapping explicitly.


class WorkType(StrEnum):
    INCIDENT = "Incident"
    SERVICE_REQUEST = "Service Request"


class Level(StrEnum):
    """The shared 5-point scale for urgency, impact and priority."""

    LOWEST = "lowest"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    HIGHEST = "highest"


class Resolution(StrEnum):
    DONE = "done"
    CANCELLED = "cancelled"
    CLARIFICATION = "clarification"
    CANNOT_REPRODUCE = "cannot reproduce"


# --- input --------------------------------------------------------------------------


class Ticket(BaseModel):
    """A ticket as received. Every field is untrusted: the service may be wrong, the
    title may contradict the body, the text may contain instructions aimed at the model."""

    id: str
    summary: str = ""
    description: str = ""
    claimed_service: str | None = None  # 'Affected Business or IT Services' as submitted
    entity: str | None = None
    reporter: str | None = None
    created: str | None = None
    status: str | None = None
    comments: list[str] = Field(default_factory=list)

    def text(self) -> str:
        """Description first: 7.14% of tickets carry a title that contradicts the body."""
        return f"{self.description}\n\n[title] {self.summary}".strip()


# --- LLM-filled sub-schemas ---------------------------------------------------------


class Evidence(BaseModel):
    """A judgement plus the one sentence from the ticket that justifies it."""

    value: Level
    quote: str = Field(default="", max_length=400)


class ClassificationOut(BaseModel):
    work_type: WorkType
    service: str
    entity: str | None = None
    reason: str = ""


class UrgencyImpactOut(BaseModel):
    urgency: Evidence
    impact: Evidence


class DraftOut(BaseModel):
    reply: str = ""
    next_steps: list[str] = Field(default_factory=list)
    self_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


# --- internals ----------------------------------------------------------------------


class Flags(BaseModel):
    unclear: bool = False
    title_mismatch: bool = False
    injection: bool = False
    spam: bool = False
    duplicate: bool = False
    low_confidence: bool = False
    related_open: list[str] = Field(default_factory=list)

    def badges(self) -> list[str]:
        on = [k for k, v in self.model_dump().items() if v is True]
        return on + ([f"duplicate_of:{self.related_open[0]}"] if self.related_open else [])


class Citation(BaseModel):
    id: str  # ticket id or KB article id — never a bare quote
    snippet: str = ""
    score: float | None = None


class TraceStep(BaseModel):
    step: str
    detail: str = ""
    latency_ms: float = 0.0
    tool: str | None = None


class Override(BaseModel):
    """A priority adjustment we applied. `ours=True` means OUR heuristic, not an
    organiser rule — the UI must show this distinction."""

    rule: str
    effect: str
    ours: bool = True


# --- output -------------------------------------------------------------------------


class GradedFields(BaseModel):
    """Exactly the 7 fields the challenge scores. Nothing else belongs here."""

    work_type: WorkType
    service: str
    team: str
    assignee: str | None = None
    priority: Level
    resolution: Resolution
    resolution_comment: str = ""


class TriageResult(BaseModel):
    graded: GradedFields
    urgency: Evidence
    impact: Evidence
    priority_reason: str = ""
    overrides: list[Override] = Field(default_factory=list)
    flags: Flags = Field(default_factory=Flags)
    draft_reply: str = ""
    next_steps: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    trace: list[TraceStep] = Field(default_factory=list)
    ticket_id: str | None = None

    def submission(self) -> dict:
        """The submission payload: graded fields only, in the challenge's own field names."""
        g = self.graded
        return {
            "Work type": g.work_type.value,
            "Affected Business or IT Services": [g.service],
            "Service Team(s)": [g.team],
            "Assignee": g.assignee,
            "Priority": g.priority.value,
            "Urgency": self.urgency.value.value,
            "Impact": self.impact.value.value,
            "Resolution": g.resolution.value,
            "Resolution text": g.resolution_comment,
        }
