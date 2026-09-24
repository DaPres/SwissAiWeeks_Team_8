"""Intake core handoff - the function the UI team calls.

    from triagemate.intake import enrich_incident, assist

    enriched = enrich_incident({"description": "My order stays in pending approval since 09:00"})   # only `description` is required
    enriched.to_json()          # camelCase dict, ready to send to the browser

Input  : ``IncidentIn`` - only ``description`` is required. Any other field the caller already knows (summary, service, workType,
         entity, reporter, priority, urgency, impact, created, comments ...) can be passed and is used as a *hint*, never trusted blindly.
         Jira-style keys ("Affected Business or IT Services", "Work type", ...) and camelCase keys are both accepted.
Output : ``EnrichedIncident`` - everything the triage pipeline decided, in one object:
         workType, service, team, entity, assignee, urgency/impact/priority (+ the reason), resolutionStatus, confidence, flags,
         corrections (what was changed versus what the caller provided), a clarification request when the text is too unclear,
         and - only when they apply -

           clientResolution  what the *requester* can try or prepare right now (self-service steps from the knowledge base; never
                             offered for injected/unclear text, duplicates, or high-priority incidents on critical services)
           expertResolution  what the *team* should do / did: the resolution note in Jira-comment form, next steps for the analyst,
                             and the most similar past resolutions

Also here: ``assist(text)`` - suggestions while the user is still typing (see ``triagemate/assist.py``).
Nothing in this module sends, deletes or changes anything outside the local store.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Optional, Union

from pydantic import ConfigDict, Field
from pydantic.alias_generators import to_camel

from .assist import AssistResponse, Suggestion, assist, get_assistant, starters  # noqa: F401  (re-exported for the UI team)
from .catalogue import CHANNEL_SERVICE, ENTITIES, SERVICES, UNKNOWN, is_critical, team_for
from .draft import detect_language
from .models import CamelModel, Ticket, TriageResult
from .pipeline import Triage
from .retrieve import get_retriever
from .safety import analyse_ticket, names_from_emails

__all__ = ["IncidentIn", "EnrichedIncident", "enrich_incident", "enrich_many", "normalise_incident", "assist", "starters",
           "set_default_triage", "get_default_triage", "json_schemas"]


# ------------------------------------------------------------------ input
class IncidentIn(CamelModel):
    """Only ``description`` is required. Everything else is an optional hint."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    description: str = Field(min_length=3, max_length=20000, description="what the user wrote (the only required field)")
    id: Optional[str] = None
    summary: Optional[str] = Field(default=None, description="title; derived from the description when missing")
    work_type: Optional[str] = Field(default=None, description="Incident | Service Request (a hint - the text decides)")
    request_type: Optional[str] = None
    service: Optional[str] = Field(default=None, description="affected service as selected by the user (a hint - the text decides)")
    entity: Optional[str] = Field(default=None, description="Luxembourg | Nordics | Switzerland | Germany | France")
    reporter: Optional[str] = None
    priority: Optional[str] = None
    urgency: Optional[str] = None
    impact: Optional[str] = None
    created: Optional[str] = Field(default=None, description="YYYY-MM-DD HH:MM; defaults to now")
    comments: list[str] = Field(default_factory=list)
    linked_issues: list[str] = Field(default_factory=list)


_KEYMAP = {
    "description": "description", "desc": "description", "text": "description", "body": "description", "message": "description", "incident": "description",
    "summary": "summary", "title": "summary", "subject": "summary",
    "worktype": "work_type", "type": "work_type", "issuetype": "work_type", "requesttype": "request_type",
    "service": "service", "affectedservice": "service", "affectedbusinessoritservices": "service", "affectedbusinessoritservice": "service",
    "entity": "entity", "businessentity": "entity", "reporter": "reporter", "reportedby": "reporter",
    "priority": "priority", "urgency": "urgency", "impact": "impact", "created": "created", "createddate": "created",
    "comments": "comments", "allcomments": "comments", "linkedissues": "linked_issues",
    "id": "id", "key": "id", "ticketid": "id", "incidentid": "id",
}


def normalise_incident(raw: Union[str, dict, IncidentIn]) -> IncidentIn:
    """Accepts a bare string, a camelCase dict, a snake_case dict or a Jira-export record."""
    if isinstance(raw, IncidentIn):
        return raw
    if isinstance(raw, str):
        return IncidentIn(description=raw)
    if not isinstance(raw, dict):
        raise TypeError("incident must be a string, a dict or an IncidentIn")
    out: dict[str, Any] = {}
    for k, v in raw.items():
        key = _KEYMAP.get(re.sub(r"[^a-z0-9]", "", str(k).lower()))
        if not key or v in (None, "", []):
            continue
        if key in ("service", "entity", "work_type") and isinstance(v, (list, tuple)):
            v = v[0] if v else None
        if key in ("comments", "linked_issues"):
            v = [str(x) for x in (v if isinstance(v, (list, tuple)) else [v])]
        out.setdefault(key, v)
    return IncidentIn(**out)


_GREETING = re.compile(r"^\s*(?:hi|hello|hey|dear|good\s+(?:morning|afternoon)|hallo|guten\s+(?:tag|morgen)|bonjour|salut)\b[^\n,.!:;]{0,40}[,.!:;\n]\s*", re.I)


def derive_summary(description: str, limit: int = 90) -> str:
    text = _GREETING.sub("", description.strip(), count=1) or description.strip()
    first = re.split(r"(?<=[.!?])\s+|\n+", text, maxsplit=1)[0].strip()
    first = re.sub(r"\s+", " ", first)
    first = first[:1].upper() + first[1:]
    return first if len(first) <= limit else first[: limit - 1].rsplit(" ", 1)[0] + "…"


def _norm_service(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    from .llm_tasks import normalise_service
    try:
        s = normalise_service(v)
    except ValueError:
        return None
    return None if s == UNKNOWN else s


def _norm_worktype(v: Optional[str]) -> Optional[str]:
    s = (v or "").strip().lower()
    return "Incident" if s in ("incident", "inc") else "Service Request" if s in ("service request", "request", "sr") else None


def _norm_entity(v: Optional[str]) -> Optional[str]:
    return next((e for e in ENTITIES if v and e.lower() == v.strip().lower()), None)


def to_ticket(inc: IncidentIn) -> Ticket:
    svc = _norm_service(inc.service)
    ent = _norm_entity(inc.entity)
    return Ticket(
        id=inc.id or f"INC-{int(time.time() * 1000) % 10**10:010d}", work_type=_norm_worktype(inc.work_type), request_type=inc.request_type,
        summary=inc.summary or derive_summary(inc.description), description=inc.description, services=[svc] if svc else [],
        entities=[ent] if ent else [], reporter=inc.reporter, priority=(inc.priority or "").lower() or None, urgency=(inc.urgency or "").lower() or None,
        impact=(inc.impact or "").lower() or None, created=inc.created or time.strftime("%Y-%m-%d %H:%M"), status="open",
        comments=list(inc.comments), linked_issues=list(inc.linked_issues), source="intake")


def _with_service_hint(t: Ticket) -> Ticket:
    """Description-only intake: when the caller named no service, let the typing-assist vocabulary supply a soft first guess.
    It enters the pipeline exactly like a user-selected service (a small prior the text can override) and is *not* reported as provided."""
    if t.services:
        return t
    svc, conf = get_assistant().guess_service(t.description)
    return t.model_copy(update={"services": [svc]}) if svc and conf >= 0.5 else t


# ------------------------------------------------------------------ output
class Flags(CamelModel):
    unclear: bool = False
    mismatch: bool = False
    duplicate: bool = False
    injection: bool = False
    low_confidence: bool = False
    contains_personal_data: bool = False


class Citation(CamelModel):
    id: str
    title: str = ""
    snippet: str = ""


class Correction(CamelModel):
    field: str
    provided: Optional[str] = None
    final: Optional[str] = None


class PriorityReason(CamelModel):
    urgency: str = ""
    impact: str = ""
    overrides: list[str] = Field(default_factory=list)


class Clarification(CamelModel):
    questions: list[str]
    message: str


class ClientResolution(CamelModel):
    title: str
    text: str
    steps: list[str]
    confidence: float
    language: str
    escalation: str
    citations: list[Citation] = Field(default_factory=list)
    source: str = "kb-self-service"


class SimilarResolution(CamelModel):
    id: str
    service: str
    text: str
    score: float


class ExpertResolution(CamelModel):
    note: str
    jira_comment: str
    steps: list[str] = Field(default_factory=list)
    source: str
    assignee: Optional[str] = None
    team: str = ""
    similar_past: list[SimilarResolution] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class DraftReply(CamelModel):
    kind: str
    language: str
    text: str
    next_steps: list[str] = Field(default_factory=list)
    citation_coverage: float = 1.0


class TraceStepOut(CamelModel):
    step: int
    tool: str
    args: str = ""
    result: str = ""
    latency_ms: float = 0.0
    mode: str = ""


class Meta(CamelModel):
    mode: str
    latency_ms: float
    cost_usd: float
    tokens_in: int = 0
    tokens_out: int = 0
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    trace: list[TraceStepOut] = Field(default_factory=list)


class EnrichedIncident(CamelModel):
    id: str
    summary: str
    description: str
    language: str
    work_type: str
    service: Optional[str]
    service_identified: bool
    team: str
    business_critical: bool
    entity: Optional[str] = None
    assignee: Optional[str] = None
    assignee_reason: str = ""
    urgency: str
    impact: str
    priority: str
    priority_label: str
    priority_reason: PriorityReason
    resolution_status: str
    confidence: float
    flags: Flags
    reasons: list[str] = Field(default_factory=list)
    corrections: list[Correction] = Field(default_factory=list)
    clarification: Optional[Clarification] = None
    client_resolution: Optional[ClientResolution] = None
    expert_resolution: Optional[ExpertResolution] = None
    escalation: Optional[dict] = None
    draft_reply: Optional[DraftReply] = None
    related_incidents: list[str] = Field(default_factory=list)
    provided: dict[str, Any] = Field(default_factory=dict)
    meta: Meta


# ------------------------------------------------------------------ default pipeline
_DEFAULT: Triage | None = None
_LOCK = threading.RLock()


def set_default_triage(tri: Optional[Triage]) -> None:
    """The API injects its store-backed pipeline so enriched incidents also appear in the analyst queue."""
    global _DEFAULT
    _DEFAULT = tri


def get_default_triage() -> Triage:
    global _DEFAULT
    with _LOCK:
        if _DEFAULT is None:
            _DEFAULT = Triage()
        return _DEFAULT


def _triage_for(triage: Optional[Triage], use_llm: Optional[bool]) -> Triage:
    tri = triage or get_default_triage()
    if use_llm is not None and tri._use_llm != use_llm:
        return Triage(retriever=tri.ret, assigner=tri.assigner, store=tri.store, use_llm=use_llm)
    return tri


# ------------------------------------------------------------------ resolutions
_FRAMES = {
    "en": ("Here is what you can try right away:", "If this does not help, the {team} team will pick up your ticket."),
    "de": ("Das können Sie sofort versuchen:", "Falls das nicht hilft, übernimmt das Team {team} Ihr Ticket."),
    "fr": ("Voici ce que vous pouvez essayer tout de suite :", "Si cela ne suffit pas, l'équipe {team} prend votre ticket en charge."),
}


def _translate(steps: list[str], lang: str, tri: Triage) -> list[str]:
    """Steps are authored in English; when the ticket is German/French and an LLM is on, translate (fallback: English)."""
    if lang == "en" or not tri.llm_on:
        return steps
    try:
        from .llm import get_client
        c = get_client("draft")
        res = c.chat([{"role": "system", "content": f"Translate each numbered line into {'German' if lang == 'de' else 'French'}. Keep it short. "
                                                    "Return only the translated lines, one per line, same order, no numbering."},
                      {"role": "user", "content": "\n".join(steps)}], max_tokens=400, temperature=0.0, name="translate_steps")
        out = [ln.strip() for ln in (res["content"] or "").splitlines() if ln.strip()]
        return out if len(out) == len(steps) else steps
    except Exception:  # noqa: BLE001 - translation is a nicety, never a failure
        return steps


def _client_resolution(res: TriageResult, safe_text: str, lang: str, tri: Triage) -> Optional[ClientResolution]:
    """``safe_text`` is the masked DESCRIPTION only: a misleading title must not pick the solution."""
    f = res.flags
    if f.injection or f.unclear or f.duplicate or res.resolution == "clarification" or res.service == UNKNOWN:
        return None
    if res.work_type == "Incident" and is_critical(res.service) and res.priority in ("highest", "high"):
        return None                                            # a real, high-priority incident on a critical system is for the experts
    qs = get_assistant().quick_solution(safe_text, res.service, res.classification.confidence if res.classification else 0.5,
                                        allow_generic=(res.work_type == "Service Request"))
    if qs is None:
        return None
    steps = _translate(qs.steps, lang, tri)
    intro, outro = _FRAMES.get(lang, _FRAMES["en"])
    cite = qs.citations[0]["id"] if qs.citations else ""
    text = intro + "\n" + "\n".join(f"{i}. {s}" + (f" [{cite}]" if cite else "") for i, s in enumerate(steps, 1)) + "\n" + outro.format(team=res.team)
    return ClientResolution(title=qs.title, text=text, steps=steps, confidence=qs.confidence, language=lang,
                            escalation=outro.format(team=res.team), citations=[Citation(**c) for c in qs.citations])


def _expert_resolution(res: TriageResult, safe_text: str, tri: Triage) -> Optional[ExpertResolution]:
    if res.flags.injection or res.resolution == "clarification" or not res.resolution_note:
        return None
    hits = tri.ret.resolution_playbook(safe_text, service=res.service if res.service != UNKNOWN else None, k=3)
    similar = [SimilarResolution(id=h.meta.get("cite", h.id), service=(h.meta.get("services") or [""])[0], text=h.text, score=round(h.score, 3))
               for h in hits if h.score >= 0.2]
    dr = res.draft
    return ExpertResolution(
        note=res.resolution_note, jira_comment=f"{res.assignee}: {res.resolution_note}" if res.assignee else res.resolution_note,
        steps=list(dr.next_steps) if dr and dr.kind == "reply" else [], source=res.resolution_source, assignee=res.assignee, team=res.team,
        similar_past=similar, citations=[Citation(id=c.id, title=c.title, snippet=c.snippet) for c in (dr.citations if dr else [])])


def _clarification(res: TriageResult) -> Optional[Clarification]:
    if res.flags.injection or not (res.flags.unclear or res.resolution == "clarification"):
        return None
    dr = res.draft
    lines = [re.sub(r"^\s*\d+[.)]\s*", "", ln).strip() for ln in (dr.text if dr else "").splitlines() if re.match(r"^\s*\d+[.)]\s+", ln)]
    return Clarification(questions=lines[:3] or ["Which application or process is affected?", "When did it happen?", "What did you expect, or which error do you see?"],
                         message=dr.text if dr else "")


def _corrections(inc: IncidentIn, res: TriageResult) -> list[Correction]:
    out: list[Correction] = []
    wt = _norm_worktype(inc.work_type)
    if wt and wt != res.work_type:
        out.append(Correction(field="workType", provided=wt, final=res.work_type))
    sv = _norm_service(inc.service)
    if sv and sv != res.service:
        out.append(Correction(field="service", provided=sv, final=res.service if res.service != UNKNOWN else None))
    for name in ("urgency", "impact", "priority"):
        given = (getattr(inc, name) or "").strip().lower()
        final = getattr(res, name)
        if given and given != final:
            out.append(Correction(field=name, provided=given, final=final))
    return out


def build_enriched(inc: IncidentIn, t: Ticket, res: TriageResult, tri: Triage) -> EnrichedIncident:
    safe = analyse_ticket(t.summary, t.description, t.comment_bodies(), reporter=t.reporter, known_names=names_from_emails(t.reporter))
    lang = res.draft.language if res.draft else detect_language(t.text)
    c, f, p = res.classification, res.flags, res.priority_detail
    identified = res.service != UNKNOWN
    inj_msg = res.draft.text if (f.injection and res.draft) else ""
    return EnrichedIncident(
        id=t.id, summary=t.summary, description=t.description, language=lang, work_type=res.work_type,
        service=res.service if identified else None, service_identified=identified, team=res.team,
        business_critical=is_critical(res.service), entity=(c.entity if c else None) or t.entity, assignee=res.assignee,
        assignee_reason=res.assignee_reason, urgency=res.urgency, impact=res.impact, priority=res.priority,
        priority_label=res.priority.capitalize(),
        priority_reason=PriorityReason(urgency=p.urgency_reason if p else "", impact=p.impact_reason if p else "", overrides=list(p.overrides) if p else []),
        resolution_status=res.resolution, confidence=res.confidence,
        flags=Flags(unclear=f.unclear, mismatch=f.mismatch, duplicate=f.duplicate, injection=f.injection, low_confidence=f.low_confidence,
                    contains_personal_data=f.pii),
        reasons=list(c.reasons) if c else [], corrections=_corrections(inc, res), clarification=_clarification(res),
        client_resolution=_client_resolution(res, safe.description, lang, tri), expert_resolution=_expert_resolution(res, safe.text, tri),
        escalation={"required": True, "message": inj_msg} if f.injection else None,
        draft_reply=DraftReply(kind=res.draft.kind, language=res.draft.language, text=res.draft.text, next_steps=list(res.draft.next_steps),
                               citation_coverage=res.draft.citation_coverage) if res.draft else None,
        related_incidents=list(res.duplicates),
        provided={k: v for k, v in inc.to_json().items() if v not in (None, [], "") and k != "description"},
        meta=Meta(mode=res.mode, latency_ms=res.latency_ms, cost_usd=res.cost_usd, tokens_in=res.tokens_in, tokens_out=res.tokens_out,
                  prompt_versions=res.prompt_versions, notes=res.notes, trace=[TraceStepOut(**s.model_dump()) for s in res.trace]),
    )


# ------------------------------------------------------------------ public functions
def enrich_incident(incident: Union[str, dict, IncidentIn], *, use_llm: Optional[bool] = None, commit_assign: bool = True,
                    triage: Optional[Triage] = None) -> EnrichedIncident:
    """The handoff function. ``incident`` may be just the description string, or a dict with more fields.

    use_llm       None = use the configured LLM if there is one; False = deterministic rules only; True = require the LLM path
    commit_assign False = preview: the suggested assignee does not count towards agent load
    """
    inc = normalise_incident(incident)
    t = _with_service_hint(to_ticket(inc))
    tri = _triage_for(triage, use_llm)
    with _LOCK:
        res = tri.run_ticket(t, commit_assign=commit_assign)
    return build_enriched(inc, t, res, tri)


def enrich_many(incidents: list[Union[str, dict, IncidentIn]], *, use_llm: Optional[bool] = None, triage: Optional[Triage] = None) -> list[EnrichedIncident]:
    """Batch version: alert storms inside the list are correlated (same service, similar text, within four hours)."""
    incs = [normalise_incident(i) for i in incidents]
    tickets = [_with_service_hint(to_ticket(i)) for i in incs]
    tri = _triage_for(triage, use_llm)
    with _LOCK:
        results = tri.run_batch(tickets)
    return [build_enriched(i, t, r, tri) for i, t, r in zip(incs, tickets, results)]


def json_schemas() -> dict:
    """JSON Schemas for the request and response contracts (generate TypeScript types from these)."""
    return {"IncidentIn": IncidentIn.model_json_schema(by_alias=True), "EnrichedIncident": EnrichedIncident.model_json_schema(by_alias=True),
            "AssistResponse": AssistResponse.model_json_schema(by_alias=True)}
