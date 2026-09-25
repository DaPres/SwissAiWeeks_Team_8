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


_UI_CACHE: dict[str, dict] = {}
_UI_LOADED = {"done": False, "dirty": 0}


def _ui_cache_file():
    from .config import get_settings
    return get_settings().outputs_dir / "cache" / "urgency_impact.json"


def _ui_cache_load() -> None:
    import json
    if _UI_LOADED["done"]:
        return
    _UI_LOADED["done"] = True
    try:
        _UI_CACHE.update(json.loads(_ui_cache_file().read_text(encoding="utf-8")))
    except Exception:
        pass


def _ui_cache_flush() -> None:
    import json
    if not _UI_LOADED["dirty"]:
        return
    try:
        f = _ui_cache_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(_UI_CACHE), encoding="utf-8")
        _UI_LOADED["dirty"] = 0
    except OSError:
        pass


import atexit as _atexit  # noqa: E402
_atexit.register(_ui_cache_flush)

_U_ORDER = ["lowest", "low", "medium", "high", "critical"]
_I_ORDER = ["none", "minor", "moderate", "significant", "major"]


def llm_urgency_impact(masked_text: str, service: str, work_type: str, samples: int | None = None) -> tuple[PriorityResult, str]:
    """Urgency/impact evidence from the model. Ratings on borderline cases flip between runs (high vs highest), which would break
    the 'priority consistency = 1.00' promise - so several samples are taken in parallel and the per-dimension **median** is used
    (self-consistency). The priority itself is still computed by the matrix, in code."""
    import concurrent.futures as cf
    import contextvars
    from .config import get_settings
    import hashlib
    cfg = get_settings()
    n = max(1, samples if samples is not None else cfg.urgency_samples)
    p = load_prompt("urgency_impact.v1")
    system = p.render(service=service, criticality=CRITICALITY.get(service, "Non-Critical"), work_type=work_type)
    client = get_client()
    user = wrap_data(masked_text, "ticket")
    key = hashlib.sha1(f"{client.provider}|{client.default_model}|{p.version}|{n}|{service}|{work_type}|{masked_text}".encode()).hexdigest()
    if cfg.decision_cache:
        _ui_cache_load()
        hit = _UI_CACHE.get(key)
        if hit:
            return finalize(hit["u"], hit["i"], urgency_reason=hit["ue"], impact_reason=hit["ie"], source="llm (cached)"), p.version

    def one() -> LLMUrgencyImpact:
        return client.chat_json(system, user, LLMUrgencyImpact, max_tokens=250, temperature=0.4 if n > 1 else 0.0, name="urgency_impact")

    outs: list[LLMUrgencyImpact] = []
    last: Exception | None = None
    if n == 1:
        outs = [one()]
    else:
        with cf.ThreadPoolExecutor(max_workers=n) as ex:
            futs = [ex.submit(contextvars.copy_context().run, one) for _ in range(n)]
            for f in futs:
                try:
                    outs.append(f.result())
                except LLMError as e:
                    last = e
    if not outs:
        raise last or LLMError("urgency_impact: no valid sample")
    ui = sorted(_U_ORDER.index(o.urgency) for o in outs)[(len(outs) - 1) // 2 + (len(outs) % 2 == 0)]
    ii = sorted(_I_ORDER.index(o.impact) for o in outs)[(len(outs) - 1) // 2 + (len(outs) % 2 == 0)]
    u, i = _U_ORDER[ui], _I_ORDER[ii]
    pick = next((o for o in outs if o.urgency == u), outs[0]), next((o for o in outs if o.impact == i), outs[0])
    res = finalize(_U[u], _I[i], urgency_reason=pick[0].urgency_evidence, impact_reason=pick[1].impact_evidence, source="llm")
    if cfg.decision_cache:
        _UI_CACHE[key] = {"u": res.urgency, "i": res.impact, "ue": res.urgency_reason, "ie": res.impact_reason}
        _UI_LOADED["dirty"] += 1
        if _UI_LOADED["dirty"] >= 25:
            _ui_cache_flush()
    return res, p.version


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


# ------------------------------------------------------------------ injection guard (second line behind the regex gate)
class LLMGuard(BaseModel):
    injection: bool = False
    confidence: float = 0.5
    reason: str = ""

    @field_validator("injection", mode="before")
    @classmethod
    def _b(cls, v):
        return str(v).strip().lower() in ("true", "yes", "1") if not isinstance(v, bool) else v

    @field_validator("confidence", mode="before")
    @classmethod
    def _c(cls, v):
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5


def llm_guard(masked_text: str) -> tuple[bool, float, str, str]:
    """Isolated yes/no verdict on the MASKED text: no tools, no ticket context, JSON only, output validated. Called only when the regex
    gate found nothing, because regexes cannot follow creative paraphrases (measured: 4/30 on a fresh attack set)."""
    p = load_prompt("guard.v1")
    client = get_client("classify")
    # the whole model-facing text is scanned, in overlapping windows, so a payload cannot hide behind padding
    size, step = 3_500, 3_000
    windows = [masked_text[i:i + size] for i in range(0, max(len(masked_text), 1), step)][:8]

    def one(w: str) -> LLMGuard:
        return client.chat_json(p.text, wrap_data(w, "ticket"), LLMGuard, max_tokens=80, temperature=0.0, name="guard")

    if len(windows) == 1:
        outs = [one(windows[0])]
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as ex:
            outs = list(ex.map(one, windows))
    hit = max((o for o in outs if o.injection), key=lambda o: o.confidence, default=None)
    top = hit or outs[0]
    return bool(hit), top.confidence, top.reason.strip()[:140], p.version


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
