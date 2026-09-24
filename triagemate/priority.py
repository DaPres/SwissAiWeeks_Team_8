"""Node 5 - Priority engine (Sec. 6.5).

The model (or the rules below) supplies *evidence* -> Urgency and Impact. The **policy** - the README's
Urgency x Impact matrix - decides the Priority, in code, so Priority is always internally consistent.

Matrix orientation was verified against the challenge file: all 20 given priorities equal
M[urgency row][impact column] (rows: Critical..Lowest urgency; columns: Major..No-direct-impact impact).
Ticket vocabulary ``highest/high/medium/low/lowest`` maps to the matrix labels as:
  Urgency: highest=Critical  high=High  medium=Medium  low=Low  lowest=Lowest
  Impact : highest=Major/Widespread  high=Significant/Large  medium=Moderate/Limited
           low=Minor/Localized  lowest=No direct impact/Information
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .catalogue import SERVICES, is_critical
from .models import LEVELS, PriorityResult

# rows = urgency, columns = impact  (both ordered highest -> lowest)
_ORDER = ("highest", "high", "medium", "low", "lowest")
_MATRIX_ROWS = {
    #            Major      Signif.   Moderate  Minor     None
    "highest": ("highest", "highest", "high",   "medium", "medium"),   # Critical
    "high":    ("highest", "high",    "high",   "medium", "low"),
    "medium":  ("high",    "high",    "medium", "low",    "low"),
    "low":     ("medium",  "medium",  "low",    "low",    "lowest"),
    "lowest":  ("medium",  "low",     "low",    "lowest", "lowest"),
}
URGENCY_LABEL = {"highest": "Critical", "high": "High", "medium": "Medium", "low": "Low", "lowest": "Lowest"}
IMPACT_LABEL = {"highest": "Major / Widespread", "high": "Significant / Large", "medium": "Moderate / Limited",
                "low": "Minor / Localized", "lowest": "No direct impact / Information"}


def matrix_priority(urgency: str, impact: str) -> str:
    u, i = urgency.lower(), impact.lower()
    return _MATRIX_ROWS[u][_ORDER.index(i)]


def is_consistent(priority: str, urgency: str, impact: str) -> bool:
    return matrix_priority(urgency, impact) == (priority or "").lower()


def _shift(level: str, delta: int) -> str:
    """delta>0 -> more severe."""
    idx = LEVELS.index(level) + delta
    return LEVELS[max(0, min(len(LEVELS) - 1, idx))]


# ------------------------------------------------------------------ cue extraction
def _rx(*alts: str) -> re.Pattern:
    return re.compile(r"(?<![\w])(?:" + "|".join(alts) + r")(?![\w])", re.I)


CUES: dict[str, re.Pattern] = {
    "full_outage": _rx(r"(?:is|are|went|gone)\s+down", r"outage", r"unavailable", r"not\s+available", r"completely\s+(?:down|unavailable|blocked)",
                       r"cannot\s+(?:log\s*in|access|open|start|be\s+used)", r"no\s+access\s+for\s+(?:all|any)", r"all\s+users",
                       r"platform\s+(?:is\s+)?down", r"total(?:ly)?\s+(?:failure|unavailable)", r"crash(?:ed)?", r"komplett\s+ausgefallen",
                       r"ausfall", r"panne\s+(?:totale|complète)", r"hors\s+service", r"nicht\s+erreichbar", r"non\s+disponible"),
    "blocked": _rx(r"blocked", r"cannot\s+(?:process|proceed|publish|be\s+processed)", r"unable\s+to\s+(?:process|publish|proceed|submit)",
                   r"did\s+not\s+publish", r"not\s+published", r"stuck", r"halted", r"stopped", r"never\s+leave", r"do\s+not\s+progress",
                   r"not\s+arriving", r"failed", r"rejected", r"not\s+(?:been\s+)?(?:delivered|posted|synchroni[sz]ed)",
                   r"blockiert", r"bloqué", r"bloquee?s?", r"abgelehnt", r"rejeté",
                   r"nicht\s+(?:mehr\s+)?(?:aktualisiert|verfügbar|erreichbar|möglich|veröffentlicht|zugestellt|gebucht)",
                   r"keine?\s+\w+\s+mehr", r"fehlgeschlagen", r"abgebrochen", r"gescheitert", r"unterbrochen",
                   r"ne\s+(?:fonctionne|répond)\s+(?:plus|pas)", r"n'est\s+pas\s+(?:disponible|mis\s+à\s+jour|publié)", r"échoué", r"interrompu"),
    "partial": _rx(r"delay(?:ed|s)?", r"late", r"some", r"several", r"partial(?:ly)?", r"intermittent(?:ly)?", r"slow", r"degraded", r"incomplete",
                   r"missing", r"blank", r"wrong", r"stale", r"backlog", r"mismatch(?:es)?", r"only\s+(?:some|a\s+few|one)", r"verzögert", r"retard",
                   r"unvollständig", r"incomplet"),
    "workaround": _rx(r"work[\s-]?around", r"manual(?:ly)?", r"can\s+still", r"still\s+(?:able|possible|open)", r"in\s+the\s+meantime",
                      r"alternative\s+(?:way|route)", r"opening\s+each"),
    "no_workaround": _rx(r"no\s+work[\s-]?around", r"cannot\s+proceed", r"no\s+way\s+to", r"not\s+possible\s+to", r"nothing\s+works"),
    "individual": _rx(r"one\s+(?:additional\s+)?user", r"single\s+user", r"a\s+(?:new\s+)?(?:colleague|joiner|employee|analyst|contractor|user|manager)",
                      r"the\s+(?:employee|user|contractor|colleague)", r"new\s+(?:joiner|starter|hire)", r"one\s+(?:additional\s+)?licen[sc]e",
                      r"individual", r"(?:this|that)\s+user", r"relationship\s+manager", r"my\s+(?:account|access)"),
    "mass": _rx(r"all\s+(?:the\s+)?(?:deactivated|inactive|users|accounts|contractors|members)", r"batch\s+of\s+users", r"(?:several|many|multiple)\s+users",
                r"whole\s+team", r"entire\s+team", r"team\s+of", r"everyone", r"all\s+staff"),
    "info": _rx(r"for\s+(?:your\s+)?(?:information|awareness)", r"fyi", r"no\s+(?:actual\s+|real\s+)?(?:disruption|outage|impact|degradation)",
                r"not\s+an?\s+(?:outage|incident)", r"informational", r"advance\s+notice", r"planned\s+maintenance", r"no\s+disruption\s+(?:was\s+)?reported",
                r"vendor\s+(?:update|eta)\s+expected", r"eta\s+(?:later|today)", r"corrected\s+\w+\s+eta"),
    "regulatory": _rx(r"regulator\w*", r"regulatory", r"filing", r"submission", r"deadline", r"finma", r"cssf", r"bafin", r"esma", r"mifid\w*",
                      r"emir", r"sftr", r"aifmd", r"lei", r"aufsicht\w*", r"réglementaire", r"sanction\w*", r"breach(?:es)?\s+of\s+(?:limit|regulat)"),
    "security": _rx(r"security\s+(?:incident|breach|compromise)", r"compromis\w+", r"unauthori[sz]ed", r"malware", r"phishing", r"data\s+leak",
                    r"leaver", r"offboard\w*", r"contract(?:or)?\s+(?:ended|left)", r"left\s+the\s+organi[sz]ation", r"must\s+not\s+retain\s+access",
                    r"inactive\s+accounts?", r"deactivat\w+", r"terminated"),
    "time_critical": _rx(r"seit\s+\d{1,2}[:.]\d{2}", r"depuis\s+\d{1,2}\s*h", r"today", r"asap", r"immediately", r"urgent(?:ly)?", r"right\s+away", r"end\s+of\s+(?:the\s+)?day", r"eod", r"within\s+(?:the\s+)?hour",
                         r"this\s+morning", r"before\s+(?:the\s+)?(?:cut-?off|close|open\w*|market|next\s+(?:accounting\s+)?cycle|start\s+of)", r"cut-?off",
                         r"at\s+risk", r"quickly", r"heute", r"sofort", r"dringend", r"aujourd'hui", r"immédiatement", r"urgent"),
    "relaxed": _rx(r"next\s+week", r"before\s+next\s+week", r"no\s+rush", r"whenever", r"when\s+possible", r"low\s+priority", r"by\s+the\s+end\s+of\s+the\s+month",
                   r"not\s+urgent", r"nächste\s+woche", r"semaine\s+prochaine"),
    "counterpart": _rx(r"brokers?", r"custodians?", r"counterpart(?:y|ies)", r"clients?", r"investors?", r"vendors?", r"regulators?", r"banks?", r"third[\s-]party",
                       r"kunden?", r"broker", r"contrepartie\w*"),
    "presentation": _rx(r"dashboards?", r"overview\s+screen", r"display(?:s|ed)?", r"summary\s+(?:screen|view|page)", r"shows?\s+(?:stale|old|yesterday)",
                        r"cosmetic", r"label", r"wording", r"layout"),
    "market_hours": _rx(r"market\s+(?:hours|open|close|opening)", r"during\s+(?:the\s+)?(?:trading|market)\s+(?:day|hours)", r"intraday", r"pre-?open",
                        r"before\s+(?:the\s+)?open"),
    "valuation_day": _rx(r"valuation\s+day", r"nav\s+(?:date|day|cut-?off)", r"next\s+accounting\s+cycle", r"end-of-day\s+valuation", r"eod\s+valuation"),
    "everyone_entities": _rx(r"all\s+(?:business\s+)?entities", r"group[\s-]wide", r"multiple\s+entities", r"across\s+(?:all\s+)?entities", r"every\s+entity"),
}


def cue_hits(text: str) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for name, rx in CUES.items():
        found = [re.sub(r"\s+", " ", m.group(0)) for m in rx.finditer(text)]
        if found:
            hits[name] = found
    return hits


_ENTITY_RX = {e: re.compile(rf"\b{e}\b", re.I) for e in ("Luxembourg", "Nordics", "Switzerland", "Germany", "France")}


def entities_mentioned(text: str) -> list[str]:
    return [e for e, rx in _ENTITY_RX.items() if rx.search(text)]


def _quote(hits: dict[str, list[str]], *names: str, limit: int = 3) -> str:
    seen: list[str] = []
    for n in names:
        for h in hits.get(n, []):
            if h.lower() not in [s.lower() for s in seen]:
                seen.append(h)
    return ", ".join(f"“{s}”" for s in seen[:limit])


# ------------------------------------------------------------------ rule-based assessment
@dataclass
class AssessInput:
    text: str
    service: str
    work_type: str = "Incident"
    request_type: str | None = None
    entities: list[str] = field(default_factory=list)
    unclear: bool = False


def rule_assess(a: AssessInput, overrides_enabled: bool = False) -> PriorityResult:
    """Deterministic Urgency/Impact extraction anchored on the README definitions and the critical-service list."""
    hits = cue_hits(a.text)
    crit = is_critical(a.service)
    is_request = a.work_type == "Service Request"
    ents = set(a.entities) | set(entities_mentioned(a.text))
    multi_entity = len(ents) >= 2 or "everyone_entities" in hits

    full = "full_outage" in hits
    blocked = "blocked" in hits
    partial = "partial" in hits
    workaround = "workaround" in hits and "no_workaround" not in hits
    info = "info" in hits
    reasons_i: list[str] = []
    reasons_u: list[str] = []
    overrides: list[str] = []

    # ------------------------------------------------------------- IMPACT
    if is_request:
        impact = "low"
        reasons_i.append("service request affecting an individual / a small team (Minor / Localized)")
        if "mass" in hits:
            impact = "medium"
            reasons_i = [f"request covers many users/accounts {_quote(hits, 'mass')} (Moderate / Limited)"]
        if info and not blocked:
            impact = "lowest"
            reasons_i = [f"no operational disruption reported {_quote(hits, 'info')} (No direct impact)"]
        if "security" in hits and "mass" in hits:
            impact = "medium"
    else:
        if info and not (full or blocked):
            impact = "lowest" if not crit else "low"
            reasons_i.append(f"informational notice {_quote(hits, 'info')}; no confirmed degradation")
        elif crit and full:
            impact = "highest"
            reasons_i.append(f"critical service {a.service} fully unavailable {_quote(hits, 'full_outage')} (Major / Widespread)")
        elif crit and (blocked or partial):
            impact = "high"
            reasons_i.append(f"partial unavailability of critical service {a.service} {_quote(hits, 'blocked', 'partial')} (Significant / Large)")
            if "presentation" in hits and workaround and not blocked:
                impact = "medium"
                reasons_i = [f"presentation-only degradation of {a.service} with a workaround {_quote(hits, 'presentation', 'workaround')} (Moderate / Limited)"]
        elif crit:
            impact = "medium"
            reasons_i.append(f"critical service {a.service} mentioned without a confirmed failure (Moderate / Limited)")
        elif full:
            impact = "medium"
            reasons_i.append(f"non-critical service {a.service} fully unavailable {_quote(hits, 'full_outage')} (Moderate / Limited)")
        elif blocked or partial:
            impact = "low"
            reasons_i.append(f"partial unavailability of non-critical service {a.service} (Minor / Localized)")
        else:
            impact = "low"
            reasons_i.append("no clear service degradation described (Minor / Localized)")

        if multi_entity and impact not in ("highest", "lowest"):
            impact = _shift(impact, +1)
            reasons_i.append(f"multiple business entities affected ({', '.join(sorted(ents))})")
        elif crit and "counterpart" in hits and impact == "medium" and (blocked or partial):
            impact = "high"
            reasons_i.append(f"financial counterparts affected {_quote(hits, 'counterpart')}")

    # non-critical services cannot be "Major" (README: Major = full unavailability of *critical* services)
    if not crit and impact == "highest":
        impact = "high"
        reasons_i.append("clamped: Major / Widespread is reserved for critical services")

    # ------------------------------------------------------------- URGENCY
    if is_request:
        urgency = "low"
        reasons_u.append("standard request handled in the normal workflow (Low)")
        if "relaxed" in hits:
            urgency = "lowest" if info else "low"
            reasons_u = [f"no time pressure {_quote(hits, 'relaxed')}"]
        if "time_critical" in hits:
            urgency = "medium"
            reasons_u = [f"requester states a same-day need {_quote(hits, 'time_critical')} (Medium)"]
        if "security" in hits:
            urgency = "high" if "time_critical" in hits else "medium"
            reasons_u = [f"access-control / leaver hygiene {_quote(hits, 'security')}"
                         + (f" with deadline {_quote(hits, 'time_critical')}" if "time_critical" in hits else "") + f" (→ {urgency})"]
        if info and "time_critical" not in hits and "security" not in hits:
            urgency = "lowest"
            reasons_u = [f"routine / informational request {_quote(hits, 'info')} (Lowest)"]
    else:
        if info and not (full or blocked):
            urgency = "lowest" if not crit else "low"
            reasons_u.append(f"informational, no deadline pressure {_quote(hits, 'info')}")
        elif "no_workaround" in hits or (full and crit):
            urgency = "highest"
            reasons_u.append(f"no workaround / major outage {_quote(hits, 'no_workaround', 'full_outage')} - immediate action (Critical)")
        elif "regulatory" in hits and ("time_critical" in hits or "blocked" in hits) and crit:
            urgency = "highest" if ("time_critical" in hits and blocked) else "high"
            reasons_u.append(f"regulatory exposure {_quote(hits, 'regulatory')} with time pressure {_quote(hits, 'time_critical', 'blocked')}")
        elif crit and (blocked or "time_critical" in hits):
            urgency = "high"
            reasons_u.append(f"time-critical failure of a critical service {_quote(hits, 'time_critical', 'blocked')} (High)")
        elif crit and partial:
            urgency = "medium"
            reasons_u.append(f"degradation with downstream tolerance {_quote(hits, 'partial')} (Medium)")
        elif blocked or "time_critical" in hits:
            urgency = "medium"
            reasons_u.append(f"non-critical service issue needing prompt attention {_quote(hits, 'time_critical', 'blocked')} (Medium)")
        else:
            urgency = "low"
            reasons_u.append("handled in the normal workflow (Low)")
        if workaround and urgency in ("highest", "high"):
            urgency = _shift(urgency, -1)
            reasons_u.append(f"workaround available {_quote(hits, 'workaround')} → one level lower")
        elif workaround and urgency == "medium" and "presentation" in hits:
            urgency = "medium"
        if "relaxed" in hits:
            urgency = _shift(urgency, -1)
            reasons_u.append(f"requester allows more time {_quote(hits, 'relaxed')}")
        # machine-created alerts without confirmed impact are less urgent than a human-reported outage
        if (a.request_type or "").lower().startswith("machine created") and urgency == "highest" and not full:
            urgency = "high"
            reasons_u.append("automated alert without confirmed outage: capped at High until validated")

    # ------------------------------------------------------------- business overrides (logged, evidence-triggered, opt-in)
    if overrides_enabled:
        urgency, impact = _apply_overrides(a, hits, urgency, impact, full, blocked, workaround, is_request, overrides)

    if a.unclear:
        reasons_u.append("input is unclear: rating is provisional and the ticket is routed for clarification")

    return PriorityResult(
        urgency=urgency, impact=impact, priority=matrix_priority(urgency, impact),
        urgency_reason="; ".join(reasons_u), impact_reason="; ".join(reasons_i), overrides=overrides, source="rules",
    )


def _apply_overrides(a, hits, urgency, impact, full, blocked, workaround, is_request, overrides):
    """PDF Sec. 6.5 example overrides. Off by default: the README's Urgency/Impact definitions are the authority and the
    overrides are 'to confirm with the experts'."""
    if not is_request and a.service in ("Trading Platform", "Order Management", "Trade Matching", "Securities Settlement")             and "market_hours" in hits and (full or blocked):
        impact = _shift(impact, +1)
        overrides.append("Impact +1: settlement/trading outage during market hours")
    if a.service == "Regulatory Reporting" and "regulatory" in hits and "time_critical" in hits and urgency != "highest":
        urgency = _shift(urgency, +1)
        overrides.append("Urgency +1: regulatory reporting with a stated deadline")
    if a.service == "NAV Calculation" and "valuation_day" in hits and (full or blocked) and impact != "highest":
        impact = _shift(impact, +1)
        overrides.append("Impact +1: NAV failure on a valuation day")
    if "individual" in hits and workaround and not is_request and urgency != "lowest":
        urgency = _shift(urgency, -1)
        overrides.append("Urgency -1: single user with a workaround")
    return urgency, impact


def finalize(urgency: str, impact: str, *, urgency_reason: str = "", impact_reason: str = "",
             overrides: list[str] | None = None, source: str = "llm") -> PriorityResult:
    """Model-supplied U/I -> policy-computed Priority (the model never outputs a priority)."""
    u = urgency.lower() if urgency and urgency.lower() in _ORDER else "medium"
    i = impact.lower() if impact and impact.lower() in _ORDER else "medium"
    return PriorityResult(urgency=u, impact=i, priority=matrix_priority(u, i), urgency_reason=urgency_reason,
                          impact_reason=impact_reason, overrides=overrides or [], source=source)


def sanity_clamp(result: PriorityResult, service: str, work_type: str) -> PriorityResult:
    """Guard-rails applied to model-supplied ratings so an over-eager model cannot contradict the README definitions."""
    u, i = result.urgency, result.impact
    notes = list(result.overrides)
    if not is_critical(service) and i == "highest":
        i = "high"
        notes.append("clamped impact: Major/Widespread is reserved for critical services")
    if work_type == "Service Request" and i in ("highest", "high"):
        i = "medium"
        notes.append("clamped impact: a single service request cannot exceed Moderate/Limited")
    if work_type == "Service Request" and u == "highest":
        u = "high"
        notes.append("clamped urgency: a service request cannot be Critical")
    if (u, i) == (result.urgency, result.impact):
        return result
    return PriorityResult(urgency=u, impact=i, priority=matrix_priority(u, i), urgency_reason=result.urgency_reason,
                          impact_reason=result.impact_reason, overrides=notes, source=result.source)


def matrix_table() -> list[dict]:
    """Serialisable matrix for the UI / docs."""
    rows = []
    for u in _ORDER:
        rows.append({"urgency": u, "label": URGENCY_LABEL[u], "cells": [
            {"impact": i, "label": IMPACT_LABEL[i], "priority": matrix_priority(u, i)} for i in _ORDER]})
    return rows
