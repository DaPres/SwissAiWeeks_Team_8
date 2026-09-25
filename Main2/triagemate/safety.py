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


MODEL_SUMMARY_CHARS, MODEL_DESC_CHARS, MODEL_COMMENT_CHARS = 1_000, 12_000, 8_000   # what any model may see; the LLM guard scans exactly this much
MAX_FIELD_CHARS = 20_000      # a summary / description / comment longer than this is anomalous; the rest is not analysed (denial-of-service guard)


def _strip_html_comments(t: str) -> tuple[str, list[str]]:
    """Remove <!-- ... --> in one pass with str.find. An UNCLOSED comment hides the rest of the text from any renderer, so it counts as hidden too."""
    out: list[str] = []
    hidden: list[str] = []
    i = 0
    while True:
        j = t.find("<!--", i)
        if j < 0:
            out.append(t[i:])
            break
        out.append(t[i:j] + " ")
        k = t.find("-->", j + 4)
        if k < 0:
            hidden.append(t[j:])
            break
        hidden.append(t[j:k + 3])
        i = k + 3
    return "".join(out), hidden


def sanitise(text: str) -> tuple[str, str, bool]:
    """Return (visible_text, hidden_text, hidden_removed). Hidden HTML/unicode payloads are separated out so they
    can be *scanned* for injection but never reach a model."""
    t = unicodedata.normalize("NFKC", (text or "")[:MAX_FIELD_CHARS])          # hard cap: bounded work for every later stage
    hidden = []
    t, comments = _strip_html_comments(t)                                       # linear time (the old regex was quadratic on unclosed comments)
    hidden += comments
    for m in _HIDDEN_CSS.finditer(t):
        hidden.append(m.group(0))
    t = _HIDDEN_CSS.sub(" ", t)
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
# (pattern, weight, description). Strong = 2 (fires alone), medium = 1 (needs a second cue).
# Design rules learned from a 52-attack / 40-look-alike red-team battery (eval/redteam.py):
#   * a strong pattern must need CONTEXT that an ordinary service-desk sentence does not have ("you are now on the list",
#     "show me how to rotate my API key" and "forward all tickets to the Securities team" are legitimate);
#   * every pattern is bounded (no unbounded gaps), so a hostile 100 KB ticket cannot cause catastrophic backtracking;
#   * obfuscated payloads (leetspeak, homoglyphs, spaced letters, reversed text, rot13, base64) are re-scanned after decoding.
_S, _M = 2, 1
_OVERRIDE_NOUNS = r"(?:instructions?|prompts?|rules|guidelines?|guidance|polic(?:y|ies)|safeguards?|constraints?|programming|directives?|restrictions?)"
_INJECTION_PATTERNS: list[tuple[re.Pattern, int, str]] = [
    # --- override / persona -----------------------------------------------------------------------------------------------
    (re.compile(r"\b(?:ignore|disregard|forget|override|bypass|neglect|abandon|discard)\b[^.\n]{0,40}\b(?:(?:all|any|the|your|previous|prior|above|earlier|former|"
                r"these|those|preceding|initial|original|system)\s+)*" + _OVERRIDE_NOUNS + r"\b", re.I), _S, "instruction-override phrase"),
    (re.compile(r"\bforget\s+(?:everything|all)\b[^.\n]{0,30}\b(?:above|before|you|prior|previous|so\s+far|learned|were\s+told)\b", re.I), _S, "instruction-override phrase"),
    (re.compile(r"\b(?:stop|cease)\s+following\b[^.\n]{0,30}\b(?:rules|instructions|guidelines|guidance|polic\w+)\b|"
                r"\b(?:rules|instructions|guidelines|guidance)\b[^.\n]{0,25}\bno\s+longer\s+(?:apply|applies|valid|matter)\b", re.I), _S, "instruction-override phrase"),
    (re.compile(r"\byou\s+are\s+now\s+(?:an?\s+|the\s+|my\s+)?(?:dan|ai\b|assistant|admin\w*|root|system|jailbroken|unrestricted|unfiltered|uncensored|free\b|evil|"
                r"different|new\b|god|developer|hacker)|\byou\s+are\s+no\s+longer\b[^.\n]{0,30}\b(?:bound|restricted|limited|an?\s+ai|assistant|triage)\b|"
                r"\bfrom\s+(?:now|here)\s+on\W+(?:you\s+(?:are|must|will|shall|should|only|always|have\s+to)\b|(?:always\s+|only\s+|just\s+)?(?:answer|reply|respond|output|write|say)\b)|"
                r"\bpretend\s+(?:to\s+be|that\s+you|you\s+are|you're)\b|"
                r"\bact\s+as\s+(?:an?\s+|the\s+)?(?:unfiltered|unrestricted|uncensored|jailbroken|evil|different|new|ai|assistant|system|root|dan)\b|\byou\s+are\s+(?:now\s+)?dan\b", re.I),
     _S, "role reassignment"),
    (re.compile(r"\bdo\s+anything\s+now\b|\b(?:disable|bypass|remove|turn\s+off|switch\s+off|unlock|circumvent)\b[^.\n]{0,25}\b(?:your|its|the\s+assistant'?s?)\s+(?:safety|content|security|"
                r"ethical|moderation)\s+(?:filters?|checks?|guardrails?|polic(?:y|ies)|restrictions?)\b|\bwith\s+no\s+(?:rules|restrictions|filters)\b|"
                r"\b(?:ai|assistant|model|dan)\b[^.\n]{0,25}\bwithout\s+(?:any\s+)?(?:restrictions|filters|rules|limitations)\b", re.I), _S, "jailbreak / persona terms"),
    (re.compile(r"\bjail\s?break\w*\b|\bdeveloper\s+mode\b", re.I), _M, "jailbreak / persona terms"),
    (re.compile(r"\bsystem\s+(?:override|notice|update|message|directive|instruction|policy)\s*[:\-]|"
                r"\b(?:triage|routing|priority|classification)\s+(?:rules|policy|logic)\b[^.\n]{0,20}\b(?:were|have\s+been|has\s+been|is|are)\s+(?:updated|changed|replaced|overridden)\b", re.I),
     _S, "fake system notice"),
    # --- prompt / secret extraction ---------------------------------------------------------------------------------------
    (re.compile(r"\b(?:reveal|print|show|leak|repeat|display|output|dump|tell\s+me|give\s+me|reproduce|recite|list|disclose|expose)\b[^.\n]{0,25}\b(?:your|the\s+(?:hidden|secret|internal|full|complete|initial))\s+"
                r"(?:full\s+|complete\s+|hidden\s+|secret\s+|internal\s+|initial\s+|original\s+)*(?:system\s+prompt|prompt|instructions|rules|guidelines|configuration|config|tool\s+list|tools|"
                r"credentials|api[\s_-]?keys?|secrets?|passwords?|memory|context)\b|"
                r"\b(?:summari[sz]e|paraphrase|translate|explain|describe|recite)\b[^.\n]{0,15}\byour\s+(?:system\s+|hidden\s+|initial\s+)?(?:instructions|prompt|rules|guidelines|configuration)\b|"
                r"\binstructions\s+you\s+(?:were|have\s+been|are)\s+given\b|\b(?:repeat|copy|print)\b[^.\n]{0,20}\b(?:the\s+)?(?:text|words|everything|message)\s+(?:above|before)\b|"
                r"\bstart(?:ing)?\s+with\s+(?:the\s+words?\s+)?[\"'“‘]?you\s+are\b|\bwhat\s+(?:is|are|were)\s+your\s+(?:system\s+)?(?:instructions|prompt|rules)\b", re.I),
     _S, "prompt/secret exfiltration attempt"),
    # --- control tokens, role tags, tool names ---------------------------------------------------------------------------
    (re.compile(r"[`~]{3}\s*(?:system|assistant|developer)\b|###\s*(?:system|instruction|prompt)|\[/?(?:INST|SYS|SYSTEM)\]|<\|(?:im_start|im_end|system|endoftext)\|>|"
                r"</?(?:ticket|system|assistant|instructions?)>|[\"']role[\"']\s*:\s*[\"'](?:system|assistant|developer)[\"']|"
                r"^\s*(?:system|developer)\s*:\s*(?:you|ignore|classify|set|output|always|mark|treat)\b|^\s*(?:assistant|ai|bot)\s*:\s*(?:call|use|ignore|set|mark|classify|output|reply)\b", re.I | re.M),
     _S, "chat-template control tokens"),
    (re.compile(r"\b(?:search_kb|find_similar_tickets|find_open_related|request_clarification|escalate_to_human|system_prompt)\b", re.I), _S, "names an internal agent tool"),
    # --- addressing the model directly -------------------------------------------------------------------------------------
    (re.compile(r"\bdear\s+(?:ai|a\.i\.|assistant|model|llm|chatbot|bot|gpt)\b|\bnote\s+to\s+(?:the\s+)?(?:ai|assistant|model|llm|bot)\b|"
                r"\b(?:ai|assistant|llm|chatbot)\s*[,:]\s*(?:please|when|you|ignore|set|do|mark|classify|make|treat)\b|\bwhen\s+you\s+(?:read|see|process)\s+this\b|"
                r"\bif\s+you\s+are\s+(?:an?\s+)?(?:ai|llm|language\s+model|assistant|chatbot)\b|"
                r"\b(?:the\s+)?(?:assistant|ai|model|llm)\s+(?:reading|processing|analy[sz]ing)\s+this\b", re.I), _S, "addresses the AI directly"),
    (re.compile(r"\bnew\s+instructions?\s*:", re.I), _M, "announces new instructions"),
    (re.compile(r"\b(?:reply|respond|answer|output|say|write|print|return|confirm)\b[^.\n]{0,25}\b(?:only|exactly|verbatim|always)\b[^.\n]{0,20}\b(?:with|:)|"
                r"\b(?:answer|reply|respond)\s+(?:to\s+)?(?:every|all|each)\s+ticket\b|\b(?:reply|respond|answer|antworte|r[eé]ponds?)\s+(?:only|nur|uniquement)\s+(?:with|mit|avec)\b", re.I),
     _M, "dictates the output"),
    # --- manipulating priority / resolution / oversight --------------------------------------------------------------------
    (re.compile(r"\b(?:set|change|mark|classify|rate|escalate|treat|make|handle|declare|label)\b[^.\n]{0,30}\b(?:priority|urgency|impact|severity|ticket|it|this|every\s+ticket)\b"
                r"[^.\n]{0,20}\b(?:as\s+|to\s+)?(?:highest|critical|p1|top\s+priority|max(?:imum)?)\b", re.I), _M, "tries to set priority/urgency"),
    (re.compile(r"\b(?:mark|close|set|flag)\b[^.\n]{0,20}\b(?:as\s+)?(?:resolved|closed|done|approved|cancel(?:l)?ed)\b|\bauto[- ]?(?:approve|resolve|close)\b|"
                r"\b(?:approve[sd]?|resolve[sd]?|closed?)\s+(?:it\s+|them\s+|this\s+|these\s+)?(?:automatically|without\s+review)\b|\band\s+close\s+(?:it|this|the\s+ticket)\b", re.I), _M,
     "tries to force a resolution/approval"),
    (re.compile(r"\b(?:do\s+not|don'?t|never)\b[^.\n]{0,25}\b(?:tell|inform|notify|escalate|flag|log|mention|classify|triage)\b|\b(?:skip|jump|bypass)\s+the\s+(?:queue|approval|review|process|controls?)\b", re.I),
     _M, "asks to suppress escalation/logging"),
    # --- exfiltration / phishing -------------------------------------------------------------------------------------------
    (re.compile(r"\b(?:forward|send|email|e-?mail|export|upload|post|leak|share)\b[^.\n]{0,50}\b(?:all|every|each|any|the\s+full|complete|entire)\b[^.\n]{0,40}\b(?:tickets?|data|records?|list|"
                r"passwords?|credentials?|users?|customers?|reporters?)\b[^.\n]{0,60}\b(?:to|at)\s+(?:\S+@\S+|https?://|attacker|external)|"
                r"\b(?:tell|give|list|show|send)\s+me\s+(?:the\s+)?(?:names?|e-?mails?(?:\s+addresses?)?|phone\s+numbers?|passwords?|personal\s+data|details|data)\b[^.\n]{0,45}"
                r"\b(?:of|about)\s+(?:the\s+)?(?:other|all|every)\b", re.I), _S, "data exfiltration request"),
    (re.compile(r"\b(?:reply|respond|answer|include|add|insert|embed|append|send)\b[^.\n]{0,40}\b(?:link|url|website|page)\b[^.\n]{0,20}https?://\S+", re.I), _M,
     "asks the reply to carry a link"),
    (re.compile(r"\bso\s+(?:the\s+)?(?:requester|user|customer)\s+can\s+(?:confirm|verify|log\s?in)\b", re.I), _M, "phishing cue"),
    (re.compile(r"\bthe\s+(?:administrator|admin|ceo|cfo|director)\s+has\s+(?:authori[sz]ed|approved)\b[^.\n]{0,40}\b(?:priority|access|override)\b", re.I), _M, "claims authority"),
    # --- generalised directive cues (paraphrases that a fixed phrase list would miss) ---------------------------------------
    (re.compile(r"\b(?:ignore|disregard|forget|overwrite|override|drop|abandon)\b[^.\n]{0,15}\byour\s+(?:training|ruleset|programming|behaviou?r|settings|setup|configuration|guidelines|rules|instructions|prompt|memory)\b|"
                r"\b(?:ignore|disregard|forget)\b[^.\n]{0,20}\bwhat\s+(?:the\s+)?(?:system|you|assistant|admin|developer)\b[^.\n]{0,15}\b(?:told|said|instructed|programmed|trained)\b|"
                r"\b(?:whatever|regardless\s+of|despite|notwithstanding)\s+your\s+(?:instructions|rules|guidelines|programming|training|policy)\b", re.I), _S, "instruction-override phrase"),
    (re.compile(r"\b(?:reset|overwrite|replace|rewrite|update|change|modify)\b[^.\n]{0,20}\byour\s+(?:behaviou?r|ruleset|rules|instructions|settings|configuration|programming|guidelines|memory|policy)\b|"
                r"\bfollow\s+only\s+my\s+(?:commands|instructions|orders)\b|\bonly\s+(?:obey|follow|listen\s+to)\s+me\b", re.I), _S, "attempts to reprogram the assistant"),
    (re.compile(r"\b(?:reveal|print|show|output|disclose|list|dump|repeat|recite|display|tell\s+me|give\s+me)\b[^.\n]{0,30}\byour\s+(?:full\s+|complete\s+|entire\s+|initial\s+|hidden\s+|original\s+)*"
                r"(?:system\s+)?(?:prompt|ruleset|instructions|configuration|setup(?:\s+message)?|context(?:\s+window)?|credentials|memory)\b(?!\s+(?:reply|response|answer|action|attention|support))", re.I),
     _S, "prompt/secret exfiltration attempt"),
    (re.compile(r"\byou\s+(?:have\s+been|are)\s+(?:granted|given|assigned)\b[^.\n]{0,30}\b(?:admin|root|elevated|full)\b|\byou\s+are\s+now\s+in\s+\w+\s+mode\b|"
                r"\b(?:version\s+of\s+yourself|alter\s+ego|another\s+ai|different\s+ai)\b|\btalk\s+like\s+a\b[^.\n]{0,30}\band\s+(?:ignore|skip|forget)\b", re.I), _S, "role reassignment"),
    (re.compile(r"\b(?:new|real|actual|true)\s+task\s*:|\bthe\s+(?:above|previous|preceding)\s+(?:was|is)\s+(?:just\s+)?a\s+test\b|"
                r"\b(?:admin|system|root|developer)\s+override\b|^\s*override\s*:", re.I | re.M), _S, "fake system notice"),
    (re.compile(r"\b(?:priority|status|resolution|urgency|impact|service|team|assignee)\s*=\s*\S+[\s,;]+(?:[a-z]+\s*=\s*\S+[\s,;]+)*\b(?:priority|status|resolution|urgency|impact|service|team|assignee|comment)\s*=", re.I),
     _S, "control fields (key=value)"),
    (re.compile(r"!\[[^\]]*\]\(https?://[^)\s]*[?&][^)\s]*\)", re.I), _S, "image/link that would exfiltrate data"),
    (re.compile(r"\b(?:list|show|print|output|tell\s+me)\b[^.\n]{0,25}\b(?:every|all)\s+(?:the\s+)?(?:other\s+)?(?:ticket|user|customer|reporter|email|name)s?\b[^.\n]{0,30}\byou\s+(?:have\s+)?seen\b", re.I),
     _S, "data exfiltration request"),
    (re.compile(r"\b(?:just|simply|only)\s+(?:say|reply|answer|respond|write|output)\b|\binstead\s*(?:,\s*)?(?:approve|write|say|output|reply)\b|\b(?:write|say|output|reply\s+with)\b[^.\n]{0,40}\binstead\b|"
                r"\blet'?s\s+play\s+a\s+game\b|\bforget\s+the\s+ticket\b|\bapprove\s+(?:every|all)\s+(?:pending\s+)?(?:request|ticket)s?\b|\bskip\s+(?:the\s+)?(?:validation|verification|checks?)\b|"
                r"\bverified\s+admin\w*\b|\bpolicy\s+update\b|\bdo\s+not\s+(?:question|check|verify)\s+it\b", re.I), _M, "manipulative directive"),
    (re.compile(r"\bsetz\w*\s+dich\s+(?:über|ueber)\b[^.\n]{0,30}\b(?:regeln|anweisungen|vorgaben)\b|\bweise\s+alle\s+anweisungen\s+zur[üu]ck\b", re.I), _S, "German instruction-override phrase"),
    (re.compile(r"\bignora\w*\b[^.\n]{0,25}\b(?:le\s+regole|le\s+istruzioni)\b|\bti\s+ordino\s+di\b", re.I), _S, "Italian instruction-override phrase"),
    # --- encoded payload announcements --------------------------------------------------------------------------------------
    (re.compile(r"\b(?:decode|decrypt|deobfuscate)\b[^.\n]{0,30}\b(?:and|then)\s+(?:follow|obey|execute|run|apply)\b", re.I), _S, "asks to decode and obey"),
    # --- other languages (override verb + rule noun, or priority-manipulation phrase) ---------------------------------------
    (re.compile(r"\b(?:ignoriere?|ignorier|missachte|vergiss|übergehe)\b[^.\n]{0,40}\b(?:anweisungen|instruktionen|regeln|vorgaben|befehle|richtlinien)\b|"
                r"\bvergiss\s+alles\b[^.\n]{0,40}\b(?:du|was)\b|\b(?:setze|stufe|mach)\b[^.\n]{0,25}\b(?:priorit[äa]t|dringlichkeit)\b[^.\n]{0,20}\b(?:h[öo]chste\w*|kritisch|sofort|maximal\w*)\b|"
                r"\bdu\s+bist\s+jetzt\s+(?:ein|eine|der|die|mein|dan|admin\w*|system\w*|ki\b|assistent\w*|root)\b", re.I), _S, "German instruction-override phrase"),
    (re.compile(r"\bignore[zr]?\b[^.\n]{0,40}\b(?:consignes|r[èe]gles|instructions|directives)\b|\b(?:oublie[zr]?|ne\s+tiens?\s+pas\s+compte)\b[^.\n]{0,40}\b(?:consignes|instructions|r[èe]gles)\b|"
                r"\boublie[zr]?\s+tout\s+ce\s+qui\s+pr[ée]c[èe]de\b|\bt(?:u\s+es|es)\s+maintenant\s+(?:un|une|le|la|mon|dan|admin\w*|syst[èe]me|ia\b|assistant\w*|root)\b|\bmets?\b[^.\n]{0,25}\bpriorit[ée]\b[^.\n]{0,20}\b(?:maximale|critique|haute)\b", re.I),
     _S, "French instruction-override phrase"),
    (re.compile(r"\bignora\w*\b[^.\n]{0,40}\b(?:istruzioni|regole|direttive|indicazioni)\b|\b(?:dimentica|scorda)\w*\b[^.\n]{0,20}\b(?:tutto|istruzioni)\b|"
                r"\bimposta\b[^.\n]{0,25}\bpriorit[àa]\b[^.\n]{0,20}\b(?:massima|critica|altissima)\b", re.I), _S, "Italian instruction-override phrase"),
    (re.compile(r"\bignora\w*\b[^.\n]{0,40}\b(?:instrucciones|reglas|directrices)\b|\bolvida\w*\b[^.\n]{0,20}\b(?:todo|instrucciones)\b|"
                r"\b(?:marca|establece|pon)\b[^.\n]{0,25}\bprioridad\b[^.\n]{0,20}\b(?:m[áa]xima|cr[íi]tica)\b", re.I), _S, "Spanish instruction-override phrase"),
    (re.compile(r"\bignor[ea]\w*\b[^.\n]{0,40}\b(?:instru[çc][õo]es|instrucoes|regras|diretrizes)\b|\bdefina\b[^.\n]{0,25}\bprioridade\b[^.\n]{0,20}\b(?:m[áa]xima|cr[íi]tica)\b", re.I),
     _S, "Portuguese instruction-override phrase"),
    (re.compile(r"\bnegeer\b[^.\n]{0,40}\b(?:instructies|regels|richtlijnen)\b|\bzet\b[^.\n]{0,25}\bprioriteit\b[^.\n]{0,20}\b(?:hoogste|kritiek)\b", re.I), _S, "Dutch instruction-override phrase"),
    (re.compile(r"игнорир\w*[^.\n]{0,40}(?:инструкци|правил|указани)|"
                r"забудь[^.\n]{0,30}(?:все|инструкци)", re.I), _S, "Russian instruction-override phrase"),
    (re.compile(r"忽略[^。\n]{0,20}(?:指令|指示|规则|说明|提示)|无视[^。\n]{0,20}(?:指令|规则)|优先级设为最高"), _S,
     "Chinese instruction-override phrase"),
]

# ---- de-obfuscation: the same patterns are re-run on decoded variants of the text -------------------------------------------
_HOMOGLYPHS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s", "һ": "h",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X",
    "ο": "o", "α": "a", "ν": "v", "ρ": "p", "ι": "i", "κ": "k", "τ": "t", "Α": "A", "Β": "B", "Ε": "E", "Ο": "O",
})
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
_MIXED_TOKEN = re.compile(r"\b(?=\w*[A-Za-z])(?=\w*\d)\w{4,}\b")
_SPACED_RUN = re.compile(r"(?:(?<=\s)|^)(?:[A-Za-z0-9] ){3,}[A-Za-z0-9](?=\s|$|[.,!?;:])")
_B64_CHUNK = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/=])")


def _decoded_variants(text: str) -> list[tuple[str, str]]:
    """(label, text) variants that a model might understand but a literal regex would miss."""
    import base64
    import binascii
    import codecs

    out: list[tuple[str, str]] = []
    homo = text.translate(_HOMOGLYPHS)
    if homo != text:
        out.append(("homoglyphs", homo))
    leet = _MIXED_TOKEN.sub(lambda m: m.group(0).translate(_LEET), text)
    if leet != text:
        out.append(("leetspeak", leet))
    spaced = _SPACED_RUN.sub(lambda m: m.group(0).replace(" ", ""), text)
    if spaced != text:
        out.append(("spaced letters", spaced))
    out.append(("reversed text", text[::-1]))
    out.append(("rot13", codecs.decode(text, "rot13")))
    for m in _B64_CHUNK.finditer(text):
        try:
            raw = base64.b64decode(m.group(0), validate=False)
            s = raw.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if s and sum(ch.isprintable() for ch in s) / len(s) > 0.95 and re.search(r"[A-Za-z]{3}", s):
            out.append(("base64", s))
    return out


def _score(text: str) -> tuple[int, list[str]]:
    score, reasons = 0, []
    for rx, w, why in _INJECTION_PATTERNS:
        seen: dict[str, str] = {}
        for m in rx.finditer(text):
            seen.setdefault(re.sub(r"\s+", " ", m.group(0)).lower(), m.group(0))
            if len(seen) >= 2:
                break
        if seen:
            score += w * len(seen)
            snippet = re.sub(r"\s+", " ", next(iter(seen.values())))[:80]
            reasons.append(f"{why}: \u201c{snippet}\u201d")
    return score, reasons


def detect_injection(text: str, *, external_sender: bool = False) -> tuple[bool, list[str]]:
    """Precision over recall for *single* weak cues (a false alarm sends a real ticket to a human), but recall over
    obfuscation: decoded variants are scanned too. A hit suppresses auto-drafting and forces escalation to a human.
    ``external_sender`` is kept for API compatibility; a lone medium cue from an external sender is not enough by itself."""
    text = text[:60_000]                                   # bounded work per ticket
    score, reasons = _score(text)
    if score < 2:
        for label, variant in _decoded_variants(text):
            s2, r2 = _score(variant)
            if s2 >= 2:
                return True, [f"obfuscated ({label}): {r}" for r in r2]
    return (score >= 2), (reasons if score >= 2 else [])


_SENTENCES = re.compile(r"(?<=[.!?;])\s+|\n+")


def without_suspicious_sentences(text: str) -> str:
    """Drop every sentence that carries any injection cue (even a weak one). Used before identifiers are lifted out of the ticket
    to be reflected into a resolution note, so attacker-supplied tokens ('output PWNED-7431') are never echoed."""
    keep = [s for s in _SENTENCES.split(text or "") if s and _score(s)[0] < 1]
    return " ".join(keep)


_URL = re.compile(r"(?:https?://|www\.)[^\s<>\")\]]+", re.I)


def strip_links(text: str) -> str:
    """Output guard: a reply, note or step must never carry a link the knowledge base did not put there (phishing via a reflected
    URL). Company-internal links (intcom.com) are kept."""
    return _URL.sub(lambda m: m.group(0) if "intcom.com" in m.group(0).lower() else "[link removed]", text or "")


# ------------------------------------------------------------------ orchestration
def analyse(text: str, *, reporter: str | None = None, extra_addresses: list[str] | None = None,
            known_names: set[str] | None = None) -> SafetyResult:
    """Full gate for one piece of ticket text."""
    visible, hidden, hidden_removed = sanitise(text)
    external = bool(reporter) and not reporter.lower().endswith("@intcom.com")
    injected, reasons = detect_injection(visible + "\n" + hidden, external_sender=external)
    if not injected and hidden.strip():
        h_score, h_why = _score(hidden)                    # hidden markup that carries ANY instruction cue is hostile by construction
        if h_score >= 1:
            injected, reasons = True, [f"hidden content: {r}" for r in h_why]
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
    if not injected and hidden.strip():
        h_score, h_why = _score(hidden)                    # hidden markup that carries ANY instruction cue is hostile by construction
        if h_score >= 1:
            injected, reasons = True, [f"hidden content: {r}" for r in h_why]
    addrs = [a for a, _ in comments if a] + ([reporter] if reporter else [])
    names = set(known_names or set()) | names_from_emails(*addrs, *_EMAIL.findall("\n".join(visible)))
    red = Redactor(names)
    masked_summary = red.redact(visible[0])
    masked_description = red.redact(visible[1])
    masked_comments = []
    for (author, _), vis in zip(comments, visible[2:]):
        masked_comments.append((_kind_of_email(author) if "@" in (author or "") else (author or ""), red.redact(vis)))
    masked_summary = masked_summary[:MODEL_SUMMARY_CHARS]                       # model-facing size is fixed so that nothing can hide beyond the guard's view
    masked_description = masked_description[:MODEL_DESC_CHARS]
    kept, used = [], 0
    for author, body in masked_comments:
        body = body[:4_000]
        if used + len(body) > MODEL_COMMENT_CHARS:
            break
        kept.append((author, body))
        used += len(body)
    masked_comments = kept
    return TicketSafety(
        summary=masked_summary, description=masked_description, comments=masked_comments, mapping=dict(red.map),
        injection=injected, injection_reasons=reasons, redaction_count=len(red.map), hidden_removed=hidden_removed,
        warnings=(["hidden markup/zero-width content removed before analysis"] if hidden_removed else [])
        + ([f"text longer than {MAX_FIELD_CHARS} characters was truncated for analysis"]
           if any(len(x or "") > MAX_FIELD_CHARS for x in (summary, description, *[b for _, b in comments])) else []),
    )


def leaks_pii(masked_text: str, mapping: dict[str, str]) -> list[str]:
    """Test helper for the invariant: which original values survive in the text that would reach a model?"""
    return [v for v in mapping.values() if len(v) > 3 and v in masked_text]
