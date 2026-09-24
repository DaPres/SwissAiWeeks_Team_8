"""LLM-backed tasks. Every function: masked input only, typed output, raises on failure so the caller can use the
deterministic fallback (``LLMError`` / ``LLMUnavailable``).  Prompts live in ``prompts/*.txt`` (versioned in git)."""
from __future__ import annotations

import difflib
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .catalogue import CRITICALITY, SERVICE_NAMES, SERVICES, UNKNOWN, team_for
from .llm import LLMError, get_client, load_prompt
from .models import Classification, PriorityResult, ServiceCandidate
from .priority import finalize
from .safety import wrap_data

_SVC_LOOKUP = {s.lower(): s for s in SERVICE_NAMES}
_ALIASES = {"oms": "Order Management", "nav": "NAV Calculation", "simcorp": "SimCorp Dimension", "iam": "Identity & Access Management",
            "sharepoint": "SharePoint & File Storage", "outlook": "Outlook & Email", "crm": "CRM & Client Portal", "rimes": "Rimes Data Feed"}


def normalise_service(v: str) -> str:
    s = (v or "").strip()
    if s.upper() == UNKNOWN or not s:
        return UNKNOWN
    if s.lower() in _SVC_LOOKUP:
        return _SVC_LOOKUP[s.lower()]
    if s.lower() in _ALIASES:
        return _ALIASES[s.lower()]
    m = difflib.get_close_matches(s.lower(), list(_SVC_LOOKUP), n=1, cutoff=0.86)
    if m:
        return _SVC_LOOKUP[m[0]]
    raise ValueError(f"service {v!r} is not in the catalogue")


# ------------------------------------------------------------------ 7.1 classification + quality gate
class LLMClassification(BaseModel):
    summary_implies: Literal["Incident", "Service Request", "unknown"] = "unknown"
    description_implies: Literal["Incident", "Service Request", "unknown"] = "unknown"
    work_type: Literal["Incident", "Service Request"]
    title_mismatch: bool = False
    service: str
    service_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    unclear: bool = False
    unclear_reason: str = ""
    reasons: list[str] = Field(default_factory=list)

    @field_validator("service")
    @classmethod
    def _svc(cls, v: str) -> str:
        return normalise_service(v)

    @field_validator("work_type", "summary_implies", "description_implies", mode="before")
    @classmethod
    def _wt(cls, v):
        s = str(v or "").strip().lower()
        if s in ("incident", "inc"):
            return "Incident"
        if s in ("service request", "request", "service_request", "sr"):
            return "Service Request"
        return "unknown" if s in ("", "unknown", "none", "n/a", "unclear") else v


def catalogue_block() -> str:
    lines = []
    for s in SERVICES.values():
        lines.append(f"- {s.name} | {s.description} | team: {s.team} | {CRITICALITY[s.name]}")
    return "\n".join(lines)


def llm_classify(masked_summary: str, masked_description: str, masked_comments: str, *, selected_service: str | None,
                 request_type: str | None, entity: str | None, given_work_type: str | None,
                 advisory: list[ServiceCandidate], team_fn=team_for) -> tuple[Classification, str]:
    p = load_prompt("classify.v1")
    system = p.render(catalogue=catalogue_block())
    hints = "; ".join(f"{c.service} ({c.score:.1f}: " + ", ".join(e.detail for e in c.evidence if e.signal in ("strong", "playbook"))[:80] + ")"
                      for c in advisory[:3])
    ticket = f"SUMMARY: {masked_summary}\nDESCRIPTION: {masked_description}"
    if masked_comments:
        ticket += f"\nCOMMENTS: {masked_comments}"
    meta = (f"selected_service: {selected_service or 'none'}\nrequest_type: {request_type or 'none'}\n"
            f"business_entity: {entity or 'none'}\nrecorded_work_type: {given_work_type or 'none'}")
    user = f"{wrap_data(ticket, 'ticket')}\n{wrap_data(meta, 'intake_metadata')}\n{wrap_data(hints or 'none', 'advisory_ranking')}"
    out = get_client().chat_json(system, user, LLMClassification, model=None, max_tokens=350, name="classify")
    cls = Classification(
        work_type=out.work_type, service=out.service, team=team_fn(out.service) if out.service != UNKNOWN else team_fn("Emailed Support Tickets"),
        entity=entity, unclear=out.unclear, title_mismatch=out.title_mismatch, confidence=round(out.service_confidence, 3),
        reasons=out.reasons[:4] + ([f"unclear: {out.unclear_reason}"] if out.unclear and out.unclear_reason else []),
        source="llm", candidates=advisory[:3],
        service_changed=bool(selected_service and out.service != selected_service),
        work_type_changed=bool(given_work_type and out.work_type != given_work_type),
    )
    return cls, p.version


# ------------------------------------------------------------------ 7.2 urgency / impact extraction
_U_ALIAS = {"highest": "critical", "urgent": "critical", "very high": "critical", "normal": "medium", "informational": "lowest", "minimal": "lowest"}
_I_ALIAS = {"highest": "major", "widespread": "major", "major / widespread": "major", "major/widespread": "major", "high": "significant",
            "large": "significant", "significant / large": "significant", "significant/large": "significant", "medium": "moderate",
            "limited": "moderate", "moderate / limited": "moderate", "moderate/limited": "moderate", "low": "minor", "localized": "minor",
            "minor / localized": "minor", "minor/localized": "minor", "lowest": "none", "no direct impact": "none", "information": "none",
            "no impact": "none", "no direct impact / information": "none"}


class LLMUrgencyImpact(BaseModel):
    urgency: Literal["critical", "high", "medium", "low", "lowest"]
    impact: Literal["major", "significant", "moderate", "minor", "none"]
    urgency_evidence: str = ""
    impact_evidence: str = ""

    @field_validator("urgency", mode="before")
    @classmethod
    def _u(cls, v):
        s = str(v or "").strip().lower()
        return _U_ALIAS.get(s, s)

    @field_validator("impact", mode="before")
    @classmethod
    def _i(cls, v):
        s = str(v or "").strip().lower()
        return _I_ALIAS.get(s, s)


_U = {"critical": "highest", "high": "high", "medium": "medium", "low": "low", "lowest": "lowest"}
_I = {"major": "highest", "significant": "high", "moderate": "medium", "minor": "low", "none": "lowest"}


def llm_urgency_impact(masked_text: str, service: str, work_type: str) -> tuple[PriorityResult, str]:
    p = load_prompt("urgency_impact.v1")
    system = p.render(service=service, criticality=CRITICALITY.get(service, "Non-Critical"), work_type=work_type)
    out = get_client().chat_json(system, wrap_data(masked_text, "ticket"), LLMUrgencyImpact, max_tokens=250, name="urgency_impact")
    return finalize(_U[out.urgency], _I[out.impact], urgency_reason=out.urgency_evidence, impact_reason=out.impact_evidence,
                    source="llm"), p.version


# ------------------------------------------------------------------ resolution note
def llm_resolution_note(masked_text: str, service: str, work_type: str, playbook: list[str], kb: list[str], refs: list[str],
                        status: str) -> tuple[str, str]:
    p = load_prompt("resolution.v1")
    ctx = (f"{wrap_data(masked_text, 'ticket')}\n{wrap_data(chr(10).join(f'{i+1}. {t}' for i, t in enumerate(playbook)) or 'none', 'playbook')}\n"
           f"{wrap_data(chr(10).join(kb) or 'none', 'kb')}\nservice: {service}\nwork_type: {work_type}\nresolution_status: {status}\n"
           f"identifiers_to_reuse: {', '.join(refs) or 'none'}")
    res = get_client("draft").chat([{"role": "system", "content": p.text}, {"role": "user", "content": ctx}],
                            temperature=0.2, max_tokens=220, name="resolution_note")
    text = re.sub(r"\s+", " ", (res["content"] or "").strip())
    if not text:
        raise LLMError("empty resolution note")
    if not text.lower().startswith("resolution:"):
        text = "Resolution: " + text
    return text, p.version


# ------------------------------------------------------------------ 7.3 draft / 7.4 clarification
class LLMDraft(BaseModel):
    reply: str
    next_steps: list[str] = Field(default_factory=list)


def llm_draft(masked_text: str, context_blocks: list[str], language: str, service: str) -> tuple[str, list[str], str]:
    """Reply + internal next steps as typed JSON. If sentences lack citations, ONE repair pass names them (Sec. 6.8: no
    citation, no claim); the pipeline still validates coverage and falls back to the deterministic draft."""
    from .draft import citation_coverage, uncited_sentences
    p = load_prompt("draft.v1")
    ctx = f"{wrap_data(masked_text, 'ticket')}\n{wrap_data(chr(10).join(context_blocks) or 'none', 'context')}\nreply_language: {language}\nservice: {service}"
    client = get_client("draft")
    out = client.chat_json(p.text, ctx, LLMDraft, max_tokens=600, temperature=0.3, name="draft")
    text = out.reply.strip()
    if not text:
        raise LLMError("empty draft")
    if text != "INSUFFICIENT_EVIDENCE":
        missing = uncited_sentences(text) + uncited_sentences("\n".join(out.next_steps))
        if missing:
            fix = ctx + "\n\nYour previous answer had factual sentences without a citation id at their end:\n" + "\n".join(f"- {m[:140]}" for m in missing[:6]) \
                  + "\nRewrite the JSON so that EVERY factual sentence ends with a citation id."
            out = client.chat_json(p.text, fix, LLMDraft, max_tokens=600, temperature=0.2, name="draft_repair")
            text = out.reply.strip() or text
    return text, [s.strip() for s in out.next_steps if s.strip()], p.version


def llm_clarification(masked_text: str, language: str) -> tuple[str, str]:
    p = load_prompt("clarification.v1")
    res = get_client("draft").chat([{"role": "system", "content": p.text},
                             {"role": "user", "content": f"{wrap_data(masked_text, 'ticket')}\nreply_language: {language}"}],
                            temperature=0.2, max_tokens=250, name="clarification")
    text = (res["content"] or "").strip()
    if not text:
        raise LLMError("empty clarification")
    return text, p.version
