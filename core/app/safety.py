"""Safety gate: redact PII and detect prompt injection before any model sees the ticket.

Input:  raw ticket text (and the ticket's own reporter/assignee names, which are PII too).
Output: SafetyReport — redacted text, what was redacted, injection verdict + matched rules.
Redaction is reversible only in the UI (the analyst can toggle the original); the model
layer only ever receives the redacted text.
Failure mode it prevents: leaking customer emails/IBANs to a third-party provider, and a
ticket body talking the agent into ignoring its instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- PII patterns -------------------------------------------------------------------
# Order matters: IBAN before generic long numbers, email before name-from-email.
PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[ ]?(?:[A-Z0-9]{4}[ ]?){2,7}[A-Z0-9]{1,4}\b")),
    # CARD before PHONE: a 16-digit card also matches the looser phone shape.
    ("CARD", re.compile(r"\b(?:\d{4}[ -]?){3}\d{3,4}\b")),
    ("PHONE", re.compile(r"(?<![\w.])(?:\+\d{1,3}[ .-]?)?(?:\(\d{1,4}\)[ .-]?)?\d{2,4}(?:[ .-]\d{2,4}){2,4}(?![\w.])")),
]

# Injection cues. Each is a rule id + pattern so the UI can say WHY it flagged.
INJECTION_RULES: list[tuple[str, re.Pattern]] = [
    ("ignore_instructions", re.compile(r"\b(ignore|disregard|forget)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all)\b[^.\n]{0,20}\b(instruction|prompt|rule|context)", re.I)),
    ("reveal_prompt", re.compile(r"\b(reveal|show|print|repeat|output|tell me)\b[^.\n]{0,30}\b(system prompt|your (instructions|prompt|rules)|initial prompt)", re.I)),
    ("role_override", re.compile(r"\b(you are now|from now on you|act as|pretend to be|new persona|new role)\b", re.I)),
    ("authority_claim", re.compile(r"\b(as (an? )?(admin|administrator|developer|engineer)|i am (your|the) (admin|developer|creator)|on behalf of (anthropic|openai|the developer))\b", re.I)),
    ("exfiltration", re.compile(r"\b(send|post|forward|upload|email)\b[^.\n]{0,40}\b(to|at)\b[^.\n]{0,20}(https?://|[\w.+-]+@)", re.I)),
    ("tool_abuse", re.compile(r"\b(delete|drop|truncate|update|insert into|rm -rf|shutdown)\b[^.\n]{0,25}\b(table|database|ticket|all)\b", re.I)),
    ("override_priority", re.compile(r"\b(set|mark|make|escalate)\b[^.\n]{0,25}\b(priority|urgency|impact)\b[^.\n]{0,25}\b(highest|critical|p1)\b", re.I)),
    ("hidden_instruction", re.compile(r"(<!--|\[//\]:|​|```system)", re.I)),
]


@dataclass
class SafetyReport:
    redacted_text: str
    injection: bool = False
    matched_rules: list[str] = field(default_factory=list)
    redactions: dict[str, int] = field(default_factory=dict)

    @property
    def redaction_count(self) -> int:
        return sum(self.redactions.values())


def _name_patterns(names: list[str]) -> list[re.Pattern]:
    """Build patterns for real person names, including 'first.last@' style handles."""
    out = []
    for raw in filter(None, names):
        local = raw.split("@")[0]
        parts = [p for p in re.split(r"[._\s-]+", local) if len(p) > 2]
        for p in parts:
            out.append(re.compile(rf"\b{re.escape(p)}\b", re.I))
        if len(parts) >= 2:
            out.append(re.compile(rf"\b{re.escape(parts[0])}[ ._-]{re.escape(parts[-1])}\b", re.I))
    return out


def redact(text: str, names: list[str] | None = None) -> tuple[str, dict[str, int]]:
    """Replace PII with typed placeholders. Deterministic: same input, same output."""
    counts: dict[str, int] = {}
    for label, pattern in PII_PATTERNS:
        text, n = pattern.subn(f"[{label}]", text)
        if n:
            counts[label] = counts.get(label, 0) + n
    for pattern in _name_patterns(names or []):
        text, n = pattern.subn("[NAME]", text)
        if n:
            counts["NAME"] = counts.get("NAME", 0) + n
    return text, counts


def detect_injection(text: str) -> list[str]:
    return [rule for rule, pattern in INJECTION_RULES if pattern.search(text)]


def screen(text: str, names: list[str] | None = None) -> SafetyReport:
    """The one call a stage makes: redact, then flag injection on the ORIGINAL text.

    Injection is detected pre-redaction so that redaction cannot mask an attack.
    """
    rules = detect_injection(text)
    redacted, counts = redact(text, names)
    return SafetyReport(redacted_text=redacted, injection=bool(rules), matched_rules=rules, redactions=counts)
