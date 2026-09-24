"""Typed contracts shared by every module (Sec. 4.2: an unreliable generator becomes a typed component)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Level = Literal["lowest", "low", "medium", "high", "highest"]
LEVELS: tuple[str, ...] = ("lowest", "low", "medium", "high", "highest")
WorkType = Literal["Incident", "Service Request"]


class CamelModel(BaseModel):
    """Base for the UI-facing contracts: Python field names are snake_case, JSON is camelCase (workType, clientResolution ...)."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    def to_json(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)


class Ticket(BaseModel):
    """A ticket in either schema (training export or Jira blind-eval export)."""

    id: str
    work_type: Optional[str] = None
    request_type: Optional[str] = None
    summary: str = ""
    description: str = ""
    services: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    teams: list[str] = Field(default_factory=list)
    reporter: Optional[str] = None
    assignee: Optional[str] = None
    priority: Optional[str] = None
    urgency: Optional[str] = None
    impact: Optional[str] = None
    severity: Optional[str] = None
    created: Optional[str] = None
    status: Optional[str] = None
    resolution: Optional[str] = None
    resolution_date: Optional[str] = None
    due_date: Optional[str] = None
    linked_issues: list[str] = Field(default_factory=list)
    comments: list[str] = Field(default_factory=list)
    source: str = "jira"          # jira | training | paste | email
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def service(self) -> Optional[str]:
        return self.services[0] if self.services else None

    @property
    def entity(self) -> Optional[str]:
        return self.entities[0] if self.entities else None

    @property
    def text(self) -> str:
        return f"{self.summary}\n{self.description}".strip()

    def comment_bodies(self) -> list[tuple[str, str]]:
        out = []
        for c in self.comments:
            if ": " in c:
                a, b = c.split(": ", 1)
                out.append((a.strip(), b.strip()))
            else:
                out.append(("", c.strip()))
        return out


class Evidence(BaseModel):
    signal: str
    detail: str
    weight: float = 0.0


class ServiceCandidate(BaseModel):
    service: str
    score: float
    evidence: list[Evidence] = Field(default_factory=list)


class Classification(BaseModel):
    work_type: str
    service: str                       # one of the catalogue names or UNKNOWN
    team: str
    entity: Optional[str] = None
    unclear: bool = False
    title_mismatch: bool = False
    confidence: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    candidates: list[ServiceCandidate] = Field(default_factory=list)
    source: str = "rules"              # rules | llm | ensemble
    service_changed: bool = False      # differs from the value shown in the ticket
    work_type_changed: bool = False


class PriorityResult(BaseModel):
    urgency: str
    impact: str
    priority: str
    urgency_reason: str = ""
    impact_reason: str = ""
    overrides: list[str] = Field(default_factory=list)
    source: str = "rules"


class Citation(BaseModel):
    id: str            # e.g. KB-07 or HIST-3
    title: str
    snippet: str = ""
    score: float = 0.0


class TraceStep(BaseModel):
    step: int
    tool: str
    args: str = ""
    result: str = ""
    latency_ms: float = 0.0
    mode: str = "policy"   # policy | llm


class Draft(BaseModel):
    kind: Literal["reply", "clarification", "escalation", "none"] = "reply"
    language: str = "en"
    text: str = ""
    next_steps: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    insufficient_evidence: bool = False
    citation_coverage: float = 1.0


class Flags(BaseModel):
    unclear: bool = False
    mismatch: bool = False
    duplicate: bool = False
    injection: bool = False
    low_confidence: bool = False
    pii: bool = False


class TriageResult(BaseModel):
    ticket_id: str
    work_type: str
    service: str
    team: str
    assignee: Optional[str] = None
    assignee_reason: str = ""
    urgency: str
    impact: str
    priority: str
    resolution: str
    resolution_note: str = ""
    resolution_source: str = ""
    confidence: float = 0.0
    flags: Flags = Field(default_factory=Flags)
    classification: Optional[Classification] = None
    priority_detail: Optional[PriorityResult] = None
    draft: Optional[Draft] = None
    duplicates: list[str] = Field(default_factory=list)
    similar: list[dict] = Field(default_factory=list)
    trace: list[TraceStep] = Field(default_factory=list)
    redaction_count: int = 0
    mode: str = "offline"              # offline | llm | hybrid
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    stage_ms: dict[str, float] = Field(default_factory=dict)
    llm_calls: list[dict] = Field(default_factory=list)
