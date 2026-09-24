"""Nodes 2-4 - Quality gate, classifier and router (Sec. 6.2-6.4). Deterministic *rules* implementation.

This is both the offline fallback and the "advisory ranking" handed to the LLM (LLM classification lives in
``llm_tasks.py``; ``pipeline.py`` arbitrates between the two).

How the service is inferred (never trusting the value shown in the ticket at face value, never ignoring it either):
  evidence = domain-ontology term hits            (summary x2, description x1, comments x0.7)
           + resolution-playbook votes            (similar historical resolutions vote for their service)
           + a small prior for the service already selected in the ticket
  with two text-understanding guards that a keyword matcher usually lacks:
    * contrast suppression  - "...rather than regulatory submissions" removes what follows the contrast marker
    * completed-context     - "trades are already matched", "matching ... completed" are context, not the problem
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .catalogue import CHANNEL_SERVICE, SERVICES, SERVICE_NAMES, UNKNOWN, find_terms, team_for
from .models import Classification, Evidence, ServiceCandidate, Ticket

# ------------------------------------------------------------------ segmentation and suppression
_SENT = re.compile(r"(?<=[.!?])\s+|\n+")
_CONTRAST = re.compile(r"\b(?:rather\s+than|instead\s+of|as\s+opposed\s+to|and\s+not|but\s+not|unrelated\s+to|not\s+(?:about|for|the)|"
                       r"nicht\s+(?:für|um)|plutôt\s+que|statt)\b", re.I)
_CLAUSE_SPLIT = re.compile(r"\s*(?:,\s*(?:but|however|while|although|yet)\b|;|\bbut\b|\bhowever\b|\bwhile\b|\balthough\b)\s*", re.I)
_DONE_CONTEXT = re.compile(r"\b(?:already|completed|succeeded|successful(?:ly)?|correctly|unaffected|not\s+affected|works?\s+(?:fine|normally)|"
                           r"is\s+fine|are\s+fine|no\s+issues?\s+(?:with|on)|bereits|déjà)\b", re.I)


def _clauses(sentence: str) -> list[str]:
    return [c for c in _CLAUSE_SPLIT.split(sentence) if c and c.strip()]


def _effective_segments(text: str) -> list[str]:
    """Split into clauses and drop the clauses/spans that are context rather than the problem."""
    out: list[str] = []
    for sent in _SENT.split(text or ""):
        sent = sent.strip()
        if not sent:
            continue
        m = _CONTRAST.search(sent)
        if m:
            sent = sent[: m.start()]                       # what follows "rather than" is the *rejected* alternative
        for cl in _clauses(sent):
            if _DONE_CONTEXT.search(cl):
                continue
            out.append(cl)
    return out


# ------------------------------------------------------------------ service scoring
STRONG_W, WEAK_W = 3.0, 0.8
SEG_W = {"summary": 2.0, "description": 1.0, "comment": 0.7, "comment_bot": 0.3}
PRIOR_GIVEN = 1.5
PLAYBOOK_W = 5.0
PLAYBOOK_MIN = 0.28
_BOT = re.compile(r"(?:monitoring|service[._-]?desk|sa_|noreply|bot|^SYSTEM$)", re.I)


def _score_segment(seg: str, svc_name: str, weight: float, evid: list[Evidence], seen: set) -> float:
    s = SERVICES[svc_name]
    total = 0.0
    for t in find_terms(seg, s.strong):
        key = (svc_name, t)
        decay = 0.5 if key in seen else 1.0
        seen.add(key)
        w = STRONG_W * weight * decay
        total += w
        evid.append(Evidence(signal="strong", detail=t, weight=round(w, 2)))
    for t in find_terms(seg, s.weak):
        key = (svc_name, t)
        decay = 0.5 if key in seen else 1.0
        seen.add(key)
        w = WEAK_W * weight * decay
        total += w
        evid.append(Evidence(signal="weak", detail=t, weight=round(w, 2)))
    return total


def score_services(summary: str, description: str, comments: list[tuple[str, str]], given: str | None,
                   playbook_votes: dict[str, float] | None = None) -> list[ServiceCandidate]:
    parts: list[tuple[str, float]] = []
    for seg in _effective_segments(summary):
        parts.append((seg, SEG_W["summary"]))
    for seg in _effective_segments(description):
        parts.append((seg, SEG_W["description"]))
    for author, body in comments:
        w = SEG_W["comment_bot"] if _BOT.search(author or "") else SEG_W["comment"]
        for seg in _effective_segments(body):
            parts.append((seg, w))

    cands: list[ServiceCandidate] = []
    for name in SERVICE_NAMES:
        if name == CHANNEL_SERVICE:
            continue
        evid: list[Evidence] = []
        seen: set = set()
        total = 0.0
        for seg, w in parts:
            total += _score_segment(seg, name, w, evid, seen)
        if given == name:
            total += PRIOR_GIVEN
            evid.append(Evidence(signal="prior", detail="service selected in the ticket", weight=PRIOR_GIVEN))
        if playbook_votes and playbook_votes.get(name, 0) >= PLAYBOOK_MIN:
            w = PLAYBOOK_W * playbook_votes[name]
            total += w
            evid.append(Evidence(signal="playbook", detail=f"similar historical resolution (sim {playbook_votes[name]:.2f})", weight=round(w, 2)))
        cands.append(ServiceCandidate(service=name, score=round(total, 3), evidence=evid))
    cands.sort(key=lambda c: -c.score)
    return cands


def service_confidence(cands: list[ServiceCandidate]) -> float:
    """Softmax share of the top candidate (temperature 2.5) blended with its absolute evidence strength."""
    if not cands or cands[0].score <= 0:
        return 0.0
    scores = [c.score for c in cands[:6]]
    mx = max(scores)
    exps = [math.exp((s - mx) / 2.5) for s in scores]
    share = exps[0] / sum(exps)
    strength = min(1.0, cands[0].score / 8.0)
    return round(0.6 * share + 0.4 * strength, 3)


# ------------------------------------------------------------------ work type
_REQ_TITLE = re.compile(r"^(?:new\s+licen[sc]e|access\s+(?:requested|request|removal)|request(?:ed)?\b|need(?:s|ed)?\s+access|"
                        r"please\s+(?:add|create|grant|remove|provide|set\s*up)|general\s+request|zugriff\s+(?:angefordert|entfernen)|"
                        r"demande\s+d.acc[eè]s|lizenz\s+f[üu]r)|\brequested\b|\bfor\s+a\s+new\b|\bneed(?:s)?\s+(?:access|a\s+(?:new\s+)?(?:licen[sc]e|mailbox))",
                        re.I)
_INC_TITLE = re.compile(r"\b(?:fail(?:ed|ure|s)?|reject(?:ed|s)?|delay(?:ed|s)?|down|outage|error|stopp?ed|breach(?:ed)?|backlog|not\s+working|"
                        r"blank|missing|stale|cannot|can'?t|unable|alert|incorrect|timeout|timed\s+out|late|degraded|slow|"
                        r"unavailable|pending|stuck|ausgefallen|fehler|panne|erreur|critical\s+incident)\b", re.I)
_INC_BODY = re.compile(r"\b(?:fail(?:ed|ure|s|ing)?|reject(?:ed|s|ion)?|delay(?:ed|s)?|blocked|stopp?ed|not\s+(?:been\s+)?arriving|breach(?:ed)?|backlog|not\s+posted|not\s+(?:been\s+)?(?:sent|received|generated|produced|created)|"
                       r"error|timeout|timed\s+out|stale|missing|incomplete|blank|no\s+longer|outage|unavailable|degraded|threshold|"
                       r"cannot|can'?t|unable|dropped|not\s+(?:been\s+)?(?:published|delivered|synchroni[sz]ed|updating|receiving|working|calculated|booked)|"
                       r"remain(?:s)?\s+in|regressed|slow|(?:is|are|been|has\s+been|was)\s+down|down\s+since|not\s+working|does(?:n'?t|\s+not)\s+work|"
                       r"nobody\s+can|none\s+of|frozen|freezes|crash(?:ed)?|aborted|deadlock|bounced|off\s+by|differs?|break\s+of|wrong|zero|"
                       r"not\s+(?:reachable|available)|nicht\s+(?:erreichbar|veröffentlicht|gematcht)|gescheitert|fehlgeschlagen|abgelehnt|abgebrochen|"
                       r"veraltet|fehlt|indisponible|échoué|échoue|rejeté|n'a\s+pas\s+été\s+publi\w+|en\s+retard|vide)\b", re.I)
_REQ_BODY = re.compile(r"\b(?:needs?\s+(?:\w+\s+){0,3}?(?:access|licen[sc]e|mailbox|account|role|permissions?)|requires?\s+(?:\w+\s+){0,3}?(?:access|licen[sc]e)|requests?|requested|requesting|asking\s+for|approved|standard\s+(?:access|role|licen[sc]e|processing|sales)|"
                       r"new\s+(?:\w+\s+)?(?:user|joiner|colleague|analyst|manager|starter|hire)|joining|provision(?:ing|ed)?|remov(?:e|ed|al)\s+(?:all\s+)?(?:access|permissions?|rights)|"
                       r"access\s+(?:removed|removal|to|for)|offboard\w*|deactivat\w+|disable|(?:create|creation|new|set\s*up|provision\w*|need\w*)\s+(?:\w+\s+){0,3}(?:shared\s+mailbox|distribution\s+list)|role-based|role\s+profile|"
                       r"please\s+(?:create|add|remove|grant|set|assign|arrange|provide)|would\s+like|kindly|licen[sc]e\s+(?:for|to)|assign\w*|"
                       r"bitte\s+\w*\s*(?:einrichten|entfernen|anlegen|erstellen)|benötigen\s+eine|zugriff\s+auf|berechtigungen\s+\w*\s*entfernen|"
                       r"demande\s+d.acc[eè]s|merci\s+de\s+(?:supprimer|cr[ée]er)|nouvelle?\s+(?:collaboratri|gestionnaire)\w*|nouveau\s+collaborateur|collaborateur\s+parti)\b", re.I)
# explicit statements about the title/type mismatch (LLM-written tickets often spell the trap out)
_META_TO_REQUEST = [
    re.compile(r"\btitle\b[^.]{0,80}\b(?:sounds?|reads?|looks?|suggests?|implies|reads\s+like)\b[^.]{0,100}\b(?:incident|outage|urgent|failure|emergency)\b"
               r"[^.]{0,140}\b(?:but|however|although|actually|in\s+fact)\b", re.I),
    re.compile(r"\b(?:is|are)\s+(?:actually|really|in\s+fact)\s+(?:asking|requesting|a\s+request|a\s+standard\s+request|a\s+regular\s+service)", re.I),
    re.compile(r"\bstandard\s+service\s+request\b|\bregular\s+service\s+inquiry\b|\broutine\s+(?:identity|access|cleanup|clean-up|provisioning)\b|"
               r"\b(?:normal|standard|routine)\s+(?:provisioning|service)\s+request\b|\bnothing\s+is\s+broken\b", re.I),
    re.compile(r"\bno\s+(?:actual|real)\s+(?:outage|disruption|incident)\b|\bno\s+disruption\s+(?:was\s+)?reported\b|\bnot\s+an?\s+(?:incident|outage)\b", re.I),
]
_META_TO_INCIDENT = [
    re.compile(r"\btitle\b[^.]{0,80}\b(?:sounds?|reads?|looks?|suggests?|implies)\b[^.]{0,60}\b(?:service\s+)?request\b[^.]{0,140}\b(?:but|however|although|instead|actually)\b", re.I),
    re.compile(r"\b(?:is|are)\s+(?:actually|really|in\s+fact)\s+(?:an?\s+)?(?:incident|outage|failure)\b|\btrue\s+incident\b|"
               r"\bthis\s+is\s+an?\s+(?:incident|outage|failure)\b|\btreat\s+(?:it|this)\s+as\s+an?\s+(?:incident|outage)\b|"
               r"\b(?:is|this\s+is)\s+not\s+an?\s+(?:access\s+|service\s+)?request\b|\btitle\s+is\s+wrong\b|"
               r"\btitle\s+says\b[^.]{0,80}\bbut\b[^.]{0,100}\b(?:outage|incident|down|failure|failed)\b", re.I),
]
REQUEST_TYPE_PRIOR = {  # log-odds towards Incident (+) or Service Request (-). Deliberately modest: the intake label can be wrong.
    "machine created alert": 1.2, "human created incident": 1.2, "nonsense / unclear input": 0.6,
    "email / 3rd party warning": 0.4, "new license": -1.2, "new licence": -1.2, "access to a service": -1.2,
    "access removal": -1.2, "general request": -1.0, "misclassified incident title": -1.0,
    "misclassified service request title": 0.0,
}
W_TITLE, W_BODY, W_GIVEN = 0.7, 1.5, 0.6


def _distinct(rx: re.Pattern, text: str, cap: int) -> int:
    return min(cap, len({re.sub(r"\s+", " ", m.group(0).lower()) for m in rx.finditer(text or "")}))


def decide_work_type(summary: str, description: str, given: str | None, request_type: str | None,
                     comments_text: str = "") -> tuple[str, float, bool, list[str]]:
    """Description-primary (Sec. 6.3): z = given prior + request-type prior + 0.7*title + 1.5*description.
    Returns (work_type, confidence, title_mismatch, reasons). z > 0 -> Incident."""
    reasons: list[str] = []
    z = 0.0
    if given in ("Incident", "Service Request"):
        z += W_GIVEN if given == "Incident" else -W_GIVEN
    rt = (request_type or "").strip().lower()
    if rt in REQUEST_TYPE_PRIOR and REQUEST_TYPE_PRIOR[rt]:
        z += REQUEST_TYPE_PRIOR[rt]
        reasons.append(f"intake request type “{request_type}” leans {'Incident' if REQUEST_TYPE_PRIOR[rt] > 0 else 'Service Request'}")

    title_z = (1.0 if _INC_TITLE.search(summary) else 0.0) - (1.0 if _REQ_TITLE.search(summary) else 0.0)
    inc_n, req_n = _distinct(_INC_BODY, description, 4), _distinct(_REQ_BODY, description, 4)
    body_z = float(inc_n - req_n)
    body_z += 0.3 * (_distinct(_INC_BODY, comments_text, 2) - _distinct(_REQ_BODY, comments_text, 2))
    meta_req = any(rx.search(description) for rx in _META_TO_REQUEST)
    meta_inc = any(rx.search(description) for rx in _META_TO_INCIDENT)
    if _UNCLEAR_META.search(description) and not (meta_req or meta_inc):
        body_z = 0.0
    if meta_req:
        body_z -= 3.0
        reasons.append("description states the request is routine / the title is misleading (no real disruption)")
    if meta_inc:
        body_z += 3.0
        reasons.append("description states the underlying problem is a true incident despite the request-like title")

    z += W_TITLE * title_z + W_BODY * body_z
    desc_implies = "Incident" if body_z > 0 else ("Service Request" if body_z < 0 else None)
    title_implies = "Incident" if title_z > 0 else ("Service Request" if title_z < 0 else None)
    mismatch = bool(desc_implies and title_implies and desc_implies != title_implies) or meta_req or meta_inc

    wt = "Incident" if z > 0 else "Service Request" if z < 0 else (given if given in ("Incident", "Service Request") else "Incident")
    conf = round(1 / (1 + math.exp(-abs(z) / 1.6)), 3)
    if title_implies and desc_implies:
        reasons.append(f"summary suggests {title_implies}, description suggests {desc_implies}")
    return wt, conf, mismatch, reasons


# ------------------------------------------------------------------ unclear / quality gate
_UNCLEAR_META = re.compile(r"\b(?:unclear|not\s+clear|vague|malformed|garbled|incomplete\s+(?:message|note|text)|misrouted|accidental|poor(?:ly)?\s+(?:worded|written|phrased)|"
                           r"short\s+and\s+unclear|cannot\s+tell|does\s+not\s+(?:describe|contain)|clarify\s+the\s+exact|needs?\s+clarification|"
                           r"nonsense|unusable|no\s+usable)\b", re.I)


def content_tokens(text: str) -> int:
    from .retrieve import tokens
    return len(tokens(text))


def decide_unclear(summary: str, description: str, request_type: str | None, top_service_score: float) -> tuple[bool, list[str]]:
    score = 0.0
    reasons: list[str] = []
    rt = (request_type or "").lower()
    if "unclear" in rt or "nonsense" in rt:
        score += 2.5
        reasons.append(f"intake request type “{request_type}”")
    if _UNCLEAR_META.search(description) or _UNCLEAR_META.search(summary):
        m = _UNCLEAR_META.search(description) or _UNCLEAR_META.search(summary)
        score += 1.5
        reasons.append(f"text itself says the input is unclear: “{m.group(0)}”")
    n = content_tokens(description)
    if n < 10:
        score += 1.0
        reasons.append(f"description carries only {n} informative tokens")
    if top_service_score < 2.0:
        score += 1.0
        reasons.append("no service can be identified from the text")
    return score >= 2.0, reasons


# ------------------------------------------------------------------ entity
_ENT = {"Luxembourg": r"luxembourg|luxemburg|lux\b", "Nordics": r"nordics?|nordic|sweden|norway|denmark|finland",
        "Switzerland": r"switzerland|swiss|schweiz|suisse", "Germany": r"germany|german\b|deutschland|allemagne",
        "France": r"france|french\b|frankreich"}


def detect_entity(text: str) -> str | None:
    found = [e for e, rx in _ENT.items() if re.search(rf"\b(?:{rx})", text, re.I)]
    return found[0] if len(found) == 1 else None


# ------------------------------------------------------------------ public entry point
def classify_rules(ticket: Ticket, masked_summary: str, masked_description: str, masked_comments: list[tuple[str, str]],
                   playbook_votes: dict[str, float] | None = None) -> Classification:
    given_service = ticket.service if ticket.service in SERVICES else None
    if given_service == CHANNEL_SERVICE:
        given_service = None                          # a channel is not evidence about the affected system
    cands = score_services(masked_summary, masked_description, masked_comments, given_service, playbook_votes)
    top = cands[0]
    conf_service = service_confidence(cands)
    reasons: list[str] = []

    strong_hit = any(e.signal in ("strong", "playbook") for e in top.evidence)
    if (top.score < 3.0 or not strong_hit) and not given_service:
        service = UNKNOWN if ticket.service in (None, CHANNEL_SERVICE) else ticket.service
        reasons.append("no reliable service evidence in the text")
    else:
        service = top.service
        ev = [f"{e.detail}" for e in top.evidence if e.signal in ("strong", "playbook")][:4]
        reasons.append(f"service {service}: " + (", ".join(f"“{d}”" for d in ev) if ev else "prior from the ticket"))

    comments_text = " ".join(b for _, b in masked_comments)
    wt, wt_conf, mismatch, wt_reasons = decide_work_type(masked_summary, masked_description, ticket.work_type,
                                                         ticket.request_type, comments_text)
    unclear, u_reasons = decide_unclear(masked_summary, masked_description, ticket.request_type, top.score)
    reasons += wt_reasons + u_reasons

    entity = ticket.entity or detect_entity(masked_summary + " " + masked_description)
    final_service = service
    given = ticket.service
    return Classification(
        work_type=wt,
        service=final_service,
        team=team_for(final_service) if final_service != UNKNOWN else team_for(CHANNEL_SERVICE),
        entity=entity,
        unclear=unclear,
        title_mismatch=mismatch,
        confidence=round(min(conf_service, 0.4 + 0.6 * wt_conf) if conf_service else 0.2, 3),
        reasons=reasons,
        candidates=cands[:4],
        source="rules",
        service_changed=bool(given and final_service != given),
        work_type_changed=bool(ticket.work_type and wt != ticket.work_type),
    )
