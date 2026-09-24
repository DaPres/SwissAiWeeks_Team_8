"""Node 1 - Safety gate (Sec. 4.10 / 6.1): PII redaction, injection detection, data delimiting.

Invariant stated in the pitch: *no unmasked text ever reaches a model*.

Layers (no single layer is sufficient):
  1. Separation   - ticket text is only ever sent inside a delimited ``<ticket>`` data block.
  2. Detection    - precision-first pattern set for instructions aimed at a model / triage system.
  3. Least priv.  - agent tools are read-only (see agent.py); the worst case is a bad *suggestion*.
  4. Redaction    - e-mails, phones, IBANs, policy numbers and person names become tokens before any model call
                    and are restored only in the final analyst-facing draft.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .catalogue import ENTITIES, SERVICE_NAMES, TEAMS

# ------------------------------------------------------------------ redaction
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,4})?\b")
_PHONE = re.compile(r"(?<![\w/])(?:\+|00)\d{1,3}[\s.\-]?(?:\(?\d{1,4}\)?[\s.\-]?){2,5}\d{2,4}(?!\w)")
_PHONE_LOCAL = re.compile(r"(?<![\w/.\-])0\d{2}[\s.\-]\d{3}[\s.\-]\d{2}[\s.\-]\d{2}(?![\w\-]|\.\d)")
_POLICY = re.compile(r"\b(?:policy|pol|contract|vertrag|police|contrat|account|konto|compte)\s*(?:no\.?|nr\.?|number|#|:)?\s*"
                     r"([A-Z]{0,3}[-/]?\d{6,14})\b", re.IGNORECASE)
_SSN_CH = re.compile(r"\b756[.\s]?\d{4}[.\s]?\d{4}[.\s]?\d{2}\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")

_HONORIFIC = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof|Herr|Frau|Monsieur|Madame|Mme|M\.|Signor|Signora)\.?\s+"
                        r"([A-ZÀ-Ý][\wà-ÿ'\-]+(?:\s+[A-ZÀ-Ý][\wà-ÿ'\-]+)?)")
_GREETING = re.compile(r"\b(?:Hi|Hello|Dear|Hallo|Guten\s+(?:Tag|Morgen)|Liebe[rn]?|Bonjour|Cher|Chère|Ciao)\s+"
                       r"([A-ZÀ-Ý][\wà-ÿ'\-]+(?:\s+[A-ZÀ-Ý][\wà-ÿ'\-]+)?)\b")
_SIGNOFF = re.compile(r"(?:(?:Best|Kind|Warm|Kindest)\s+regards|Regards|Thanks|Thank\s+you|Cheers|Sincerely|"
                      r"Mit\s+freundlichen\s+Gr[üu](?:ß|ss)en|Freundliche\s+Gr[üu](?:ß|ss)e|Cordialement|Bien\s+cordialement)"
                      r"[,\s]*\n?\s*([A-ZÀ-Ý][\wà-ÿ'\-]+(?:\s+[A-ZÀ-Ý][\wà-ÿ'\-]+)?)")

_PROTECTED = {w.lower() for w in (*SERVICE_NAMES, *TEAMS, *ENTITIES)}
_STOP_NAMES = {"team", "support", "service", "desk", "all", "everyone", "colleagues", "there", "and", "the", "regards",
               "thanks", "please", "monitoring", "operations", "sir", "madam", "compliance", "risk", "trading"}

_FIRST_NAMES = {'adam', 'alexander', 'alexandra', 'ali', 'alice', 'amelia', 'anders', 'andre', 'andrea', 'andreas', 'anna', 'anne', 'antoine', 'antonio', 'beat', 'beatrice', 'benjamin', 'bernard', 'bernhard', 'birgit', 'björn', 'carla', 'carlos', 'carmen', 'caroline', 'cecilia', 'charles', 'charlotte', 'chiara', 'christian', 'christine', 'christoph', 'claire', 'clara', 'claude', 'claudia', 'clemens', 'cora', 'daniel', 'daniela', 'david', 'denis', 'diana', 'dieter', 'dominique', 'dorothea', 'eduard', 'elena', 'elisabeth', 'elise', 'emil', 'emilie', 'emma', 'eric', 'erik', 'erika', 'ernst', 'eva', 'fabian', 'fabio', 'felix', 'filip', 'florian', 'francesca', 'francois', 'frank', 'franz', 'frederic', 'friedrich', 'gabriel', 'gabriele', 'georg', 'gerard', 'gina', 'giovanni', 'giulia', 'gregor', 'gustav', 'hanna', 'hannah', 'hans', 'harald', 'heidi', 'heinrich', 'helen', 'helena', 'helene', 'henri', 'henry', 'hugo', 'ines', 'ingrid', 'irina', 'isabel', 'isabelle', 'jacques', 'jan', 'jana', 'jean', 'jens', 'jessica', 'joachim', 'johan', 'johann', 'johanna', 'jonas', 'josef', 'joseph', 'julia', 'julien', 'jurg', 'karen', 'karin', 'karl', 'katharina', 'katrin', 'kevin', 'klaus', 'konrad', 'kurt', 'lars', 'laura', 'lea', 'lena', 'leo', 'leon', 'lisa', 'lorenz', 'louis', 'louise', 'luca', 'lucas', 'lucia', 'ludwig', 'luis', 'lukas', 'luke', 'maia', 'manuel', 'marc', 'marco', 'marcus', 'margaret', 'maria', 'marie', 'marina', 'mario', 'mark', 'markus', 'marta', 'martin', 'martina', 'mathias', 'matthias', 'maurice', 'max', 'maya', 'melanie', 'michael', 'michel', 'michelle', 'miriam', 'monika', 'monique', 'nadia', 'nadine', 'natalie', 'nico', 'nicolas', 'nicole', 'nina', 'nora', 'oliver', 'olivia', 'oscar', 'otto', 'pascal', 'patrick', 'paul', 'paula', 'peter', 'petra', 'philipp', 'philippe', 'pierre', 'rachel', 'rafael', 'ralf', 'raphael', 'regula', 'reto', 'richard', 'robert', 'roger', 'roland', 'rolf', 'rosa', 'ruth', 'sabine', 'sabrina', 'samuel', 'sandra', 'sara', 'sarah', 'sebastian', 'sebastien', 'silvia', 'simon', 'simone', 'sofia', 'sophie', 'stefan', 'stefanie', 'stephan', 'stephanie', 'susanne', 'sven', 'tamara', 'tania', 'theo', 'thomas', 'tim', 'tobias', 'ulrich', 'ursula', 'valentin', 'vera', 'veronika', 'vicky', 'victor', 'viktor', 'vincent', 'walter', 'wendy', 'werner', 'wilhelm', 'william', 'xavier', 'xena', 'yannick', 'yasmine', 'yves', 'zoe'}
_NAME_PAIR = re.compile(r"(?=\b([A-ZÀ-Ý][a-zà-ÿ]+)\s+([A-ZÀ-Ý][a-zà-ÿ'\-]{2,})\b)")     # lookahead: overlapping pairs ("Contact Marc Dupont")

_BOT_LOCAL = re.compile(r"^(?:sa[_\-]|svc[_\-]|monitoring|service[._-]?desk|noreply|no-reply|alerts?|bot|system|info$)", re.I)


def _kind_of_email(addr: str) -> str:
    local, _, domain = addr.lower().partition("@")
    if _BOT_LOCAL.match(local):
        return "SYSTEM" if domain.endswith("intcom.com") else "EXTERNAL"
    if domain.endswith("intcom.com"):
        return "USER"
    return "EXTERNAL"


@dataclass
class SafetyResult:
    text: str                                   # masked, delimiter-neutralised, safe to send to a model
    mapping: dict[str, str] = field(default_factory=dict)   # token -> original
    injection: bool = False
    injection_reasons: list[str] = field(default_factory=list)
    redaction_count: int = 0
    hidden_removed: bool = False
    pii_found: bool = False
    warnings: list[str] = field(default_factory=list)

    def restore(self, text: str) -> str:
        return restore(text, self.mapping)


class Redactor:
    """Stateful per-ticket redactor: the same value always maps to the same token."""

    def __init__(self, known_names: set[str] | None = None):
        self.map: dict[str, str] = {}
        self._rev: dict[str, str] = {}
        self._counters: dict[str, int] = {}
        self.known_names = {n for n in (known_names or set()) if n}

    def _token(self, kind: str, value: str) -> str:
        key = f"{kind}:{value.lower()}"
        if key in self._rev:
            return self._rev[key]
        n = self._counters.get(kind, 0) + 1
        self._counters[kind] = n
        tok = f"[{kind}_{n}]"
        self.map[tok] = value
        self._rev[key] = tok
        return tok

    def _sub(self, rx: re.Pattern, kind: str, text: str, group: int = 0, kind_fn=None) -> str:
        def repl(m: re.Match) -> str:
            val = m.group(group)
            k = kind_fn(val) if kind_fn else kind
            tok = self._token(k, val)
            if group:
                s, e = m.span(group)
                whole = m.group(0)
                off = m.start(0)
                return whole[: s - off] + tok + whole[e - off:]
            return tok
        return rx.sub(repl, text)

    def redact(self, text: str) -> str:
        t = text
        t = self._sub(_EMAIL, "EMAIL", t, kind_fn=lambda a: f"EMAIL_{_kind_of_email(a)}")
        t = self._sub(_IBAN, "IBAN", t)
        t = self._sub(_SSN_CH, "ID", t)
        t = self._sub(_POLICY, "POLICY", t, group=1)
        t = self._sub(_PHONE, "PHONE", t)
        t = self._sub(_PHONE_LOCAL, "PHONE", t)
        # person names ------------------------------------------------------------
        for rx in (_HONORIFIC, _GREETING, _SIGNOFF):
            t = self._sub_names(rx, t)
        t = self._gazetteer_names(t)
        for name in sorted(self.known_names, key=len, reverse=True):
            if name.lower() in _PROTECTED:
                continue
            t = re.sub(rf"(?<![\w\[]){re.escape(name)}(?![\w\]])", lambda m: self._token("PERSON", m.group(0)), t,
                       flags=re.IGNORECASE)
        return t

    def _gazetteer_names(self, text: str) -> str:
        """First-name gazetteer + a capitalised surname: catches "Marc Dupont" with no honorific or greeting."""
        spans: list[tuple[int, int]] = []
        last_end = -1
        for m in _NAME_PAIR.finditer(text):
            first, last = m.group(1), m.group(2)
            start, end = m.start(1), m.end(2)
            if start < last_end or first.lower() not in _FIRST_NAMES:
                continue
            whole = text[start:end].lower()
            if last.lower() in _STOP_NAMES or last.lower() in _PROTECTED or any(p in whole for p in _PROTECTED):
                continue
            spans.append((start, end))
            last_end = end
        for start, end in reversed(spans):
            text = text[:start] + self._token("PERSON", text[start:end]) + text[end:]
        return text

    def _sub_names(self, rx: re.Pattern, text: str) -> str:
        def repl(m: re.Match) -> str:
            name = m.group(1)
            words = name.split()
            if any(w.lower() in _STOP_NAMES or w.lower() in _PROTECTED for w in words):
                return m.group(0)
            if name.lower() in _PROTECTED or any(p in name.lower() for p in _PROTECTED):
                return m.group(0)
            s, e = m.span(1)
            off = m.start(0)
            whole = m.group(0)
            return whole[: s - off] + self._token("PERSON", name) + whole[e - off:]
        return rx.sub(repl, text)


def restore(text: str, mapping: dict[str, str]) -> str:
    out = text
    for tok, val in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        out = out.replace(tok, val)
    return out


def names_from_emails(*addresses: str | None) -> set[str]:
    """`amelia.marcus@intcom.com` -> {"Amelia Marcus"}: the reporter/assignee gazetteer for the NER-lite pass."""
    names: set[str] = set()
    for a in addresses:
        if not a or "@" not in a:
            continue
        local = a.split("@", 1)[0]
        if _BOT_LOCAL.match(local) or not re.search(r"[._-]", local):
            continue
        parts = [p for p in re.split(r"[._-]+", local) if p.isalpha()]
        if 2 <= len(parts) <= 3:
            names.add(" ".join(p.capitalize() for p in parts))
    return names


# ------------------------------------------------------------------ sanitising
_ZW = dict.fromkeys(map(ord, "​‌‍⁠﻿‪‫‬‭‮"), None)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_HIDDEN_CSS = re.compile(r"<[^>]+style\s*=\s*[\"'][^\"']*(?:display\s*:\s*none|font-size\s*:\s*0|visibility\s*:\s*hidden)"
                         r"[^\"']*[\"'][^>]*>.*?</[^>]+>", re.S | re.I)
_TAGS = re.compile(r"</?(?:ticket|context|system|assistant|user|instructions?)\b[^>]*>", re.I)


def sanitise(text: str) -> tuple[str, str, bool]:
    """Return (visible_text, hidden_text, hidden_removed). Hidden HTML/unicode payloads are separated out so they
    can be *scanned* for injection but never reach a model."""
    t = unicodedata.normalize("NFKC", text or "")
    hidden = []
    for rx in (_HTML_COMMENT, _HIDDEN_CSS):
        for m in rx.finditer(t):
            hidden.append(m.group(0))
        t = rx.sub(" ", t)
    stripped = t.translate(_ZW)
    hidden_removed = bool(hidden) or stripped != t
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", stripped)
    return t, "\n".join(hidden), hidden_removed


def neutralise_delimiters(text: str) -> str:
    """Stop ticket text from closing our data block or impersonating a role tag."""
    return _TAGS.sub(lambda m: m.group(0).replace("<", "[").replace(">", "]"), text)


def wrap_data(text: str, tag: str = "ticket") -> str:
    return f"<{tag}>\n{neutralise_delimiters(text)}\n</{tag}>"


# ------------------------------------------------------------------ injection detection
# (pattern, weight, description). Strong = 2 (fires alone), medium = 1 (needs a second cue or an external sender).
_INJECTION_PATTERNS: list[tuple[re.Pattern, int, str]] = [
    (re.compile(r"\b(?:ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b(?:all\s+|any\s+|the\s+|your\s+|previous\s+|prior\s+|above\s+|earlier\s+|these\s+)*"
                r"(?:instructions?|prompts?|rules?|guidelines?|polic(?:y|ies)|safeguards?|constraints?)\b", re.I), 2,
     "instruction-override phrase"),
    (re.compile(r"\byou\s+are\s+(?:now|no\s+longer)\b|\bfrom\s+now\s+on\s+you\b|\bact\s+as\s+(?:an?\s+)?(?:ai|assistant|system|admin|root|different)\b", re.I), 2,
     "role reassignment"),
    (re.compile(r"\bnew\s+instructions?\s*:|\byour\s+(?:system\s+)?(?:instructions|programming)\b|"
                r"\b(?:reveal|print|show|leak|repeat|display)\b[^.\n]{0,30}\b(?:system\s+prompt|your\s+prompt|instructions|secrets?|api[\s_-]?key|credentials?)\b", re.I), 2,
     "prompt/secret exfiltration attempt"),
    (re.compile(r"\b(?:as\s+an?\s+ai|language\s+model|large\s+language|chatgpt|openai|assistant\s*:)\b", re.I), 1,
     "addresses the AI directly"),
    (re.compile(r"\b(?:set|change|mark|classify|rate|escalate|treat|make)\b[^.\n]{0,25}\b(?:priority|urgency|impact|severity)\b[^.\n]{0,20}"
                r"\b(?:to\s+|as\s+)?(?:highest|critical|p1|urgent|max(?:imum)?|top)\b", re.I), 1,
     "tries to set priority/urgency"),
    (re.compile(r"\b(?:mark|close|set|flag)\b[^.\n]{0,20}\b(?:as\s+)?(?:resolved|closed|done|approved|cancel(?:l)?ed)\b|"
                r"\bauto[- ]?(?:approve|resolve|close)\b", re.I), 1, "tries to force a resolution/approval"),
    (re.compile(r"\b(?:do\s+not|don'?t|never)\b[^.\n]{0,25}\b(?:tell|inform|notify|escalate|flag|log|mention)\b", re.I), 1,
     "asks to suppress escalation/logging"),
    (re.compile(r"\b(?:forward|send|email|export)\b[^.\n]{0,40}\b(?:all|every|the\s+full|complete|entire)\b[^.\n]{0,30}"
                r"\b(?:tickets?|data|records?|list|passwords?|credentials?)\b[^.\n]{0,30}\b(?:to|at)\b", re.I), 2,
     "data exfiltration request"),
    (re.compile(r"\bignoriere\b[^.\n]{0,40}\b(?:anweisungen|instruktionen|regeln|vorgaben)\b|\b(?:setze|stufe)\b[^.\n]{0,25}"
                r"\b(?:priorit[äa]t|dringlichkeit)\b[^.\n]{0,20}\b(?:h[öo]chste|kritisch|sofort)\b|\bdu\s+bist\s+jetzt\b", re.I), 2,
     "German instruction-override phrase"),
    (re.compile(r"\bignore[zr]\b[^.\n]{0,40}\b(?:consignes|règles|instructions\s+pr[ée]c[ée]dentes)\b|\b(?:oublie[zr]?|ne\s+tiens\s+pas\s+compte)\b[^.\n]{0,40}"
                r"\b(?:consignes|instructions|règles|précédent\w*)\b|\bt(?:u\s+es|es)\s+maintenant\b|\bmets?\b[^.\n]{0,25}\bpriorité\b"
                r"[^.\n]{0,20}\b(?:maximale|critique|haute)\b", re.I), 2,
     "French instruction-override phrase"),
    (re.compile(r"[`~]{3}\s*(?:system|assistant)|###\s*(?:system|instruction)|\[/?(?:INST|SYS)\]|<\|(?:im_start|system)\|>", re.I), 2,
     "chat-template control tokens"),
]


def detect_injection(text: str, *, external_sender: bool = False) -> tuple[bool, list[str]]:
    """Precision over recall: a hit suppresses auto-drafting and forces escalation to a human."""
    score = 0
    reasons: list[str] = []
    for rx, w, why in _INJECTION_PATTERNS:
        m = rx.search(text)
        if m:
            score += w
            snippet = re.sub(r"\s+", " ", m.group(0))[:80]
            reasons.append(f"{why}: “{snippet}”")
    threshold = 1 if external_sender else 2
    return score >= threshold and bool(reasons), reasons if score >= threshold else []


# ------------------------------------------------------------------ orchestration
def analyse(text: str, *, reporter: str | None = None, extra_addresses: list[str] | None = None,
            known_names: set[str] | None = None) -> SafetyResult:
    """Full gate for one piece of ticket text."""
    visible, hidden, hidden_removed = sanitise(text)
    external = bool(reporter) and not reporter.lower().endswith("@intcom.com")
    injected, reasons = detect_injection(visible + "\n" + hidden, external_sender=external)
    names = set(known_names or set()) | names_from_emails(reporter, *(extra_addresses or []),
                                                          *_EMAIL.findall(visible))
    red = Redactor(names)
    masked = red.redact(visible)
    return SafetyResult(
        text=masked,
        mapping=dict(red.map),
        injection=injected,
        injection_reasons=reasons,
        redaction_count=len(red.map),
        hidden_removed=hidden_removed,
        pii_found=bool(red.map),
        warnings=["hidden markup/zero-width content removed before analysis"] if hidden_removed else [],
    )


@dataclass
class TicketSafety:
    """Masked view of a whole ticket: one shared redactor so the same person/address gets the same token everywhere."""
    summary: str
    description: str
    comments: list[tuple[str, str]]          # (author kind/role token, masked body)
    mapping: dict[str, str]
    injection: bool
    injection_reasons: list[str]
    redaction_count: int
    hidden_removed: bool
    warnings: list[str]

    @property
    def text(self) -> str:
        return f"{self.summary}\n{self.description}".strip()

    def restore(self, text: str) -> str:
        return restore(text, self.mapping)


def analyse_ticket(summary: str, description: str, comments: list[tuple[str, str]] | None = None, *,
                   reporter: str | None = None, known_names: set[str] | None = None) -> TicketSafety:
    comments = comments or []
    parts = [sanitise(summary), sanitise(description), *[sanitise(b) for _, b in comments]]
    visible = [p[0] for p in parts]
    hidden = "\n".join(p[1] for p in parts if p[1])
    hidden_removed = any(p[2] for p in parts)
    external = bool(reporter) and not reporter.lower().endswith("@intcom.com")
    # scan title+description+hidden payloads for injection; comment bodies too (a comment is untrusted input as well)
    injected, reasons = detect_injection("\n".join(visible) + "\n" + hidden, external_sender=external)
    addrs = [a for a, _ in comments if a] + ([reporter] if reporter else [])
    names = set(known_names or set()) | names_from_emails(*addrs, *_EMAIL.findall("\n".join(visible)))
    red = Redactor(names)
    masked_summary = red.redact(visible[0])
    masked_description = red.redact(visible[1])
    masked_comments = []
    for (author, _), vis in zip(comments, visible[2:]):
        masked_comments.append((_kind_of_email(author) if "@" in (author or "") else (author or ""), red.redact(vis)))
    return TicketSafety(
        summary=masked_summary, description=masked_description, comments=masked_comments, mapping=dict(red.map),
        injection=injected, injection_reasons=reasons, redaction_count=len(red.map), hidden_removed=hidden_removed,
        warnings=["hidden markup/zero-width content removed before analysis"] if hidden_removed else [],
    )


def leaks_pii(masked_text: str, mapping: dict[str, str]) -> list[str]:
    """Test helper for the invariant: which original values survive in the text that would reach a model?"""
    return [v for v in mapping.values() if len(v) > 3 and v in masked_text]
