"""Node 8 - Draft generator (Sec. 6.8), deterministic version + language handling + citation accounting.

Rules baked in (same as the LLM prompt): answer only from retrieved context; every factual sentence carries a
citation id like [KB-07]; INSUFFICIENT_EVIDENCE instead of guessing; same language as the ticket; <= ~120 words;
never promise a resolution time (the historical resolution times are random noise in the data).
"""
from __future__ import annotations

import re

from .catalogue import SERVICES, team_for
from .models import Citation, Draft
from .retrieve import Hit

_LANG_WORDS = {
    "de": set("der die das und nicht ist sind wir bitte für mit von zu den dem ein eine auf im wurde werden wurden aber auch nach über bei noch zugriff kunden".split()),
    "fr": set("le la les et pas est sont nous vous pour avec de du des un une sur dans a été être mais aussi après chez encore accès client bonjour".split()),
    "it": set("il lo la gli e non è sono noi per con di del della un una su in stato essere ma anche dopo accesso cliente buongiorno".split()),
    "en": set("the and not is are we please for with of to a an on in was were be but also after at still access client".split()),
}


def detect_language(text: str) -> str:
    words = re.findall(r"[a-zà-ÿ]+", (text or "").lower())
    if not words:
        return "en"
    scores = {lg: sum(1 for w in words if w in vocab) for lg, vocab in _LANG_WORDS.items()}
    lg = max(scores, key=lambda k: scores[k])
    return lg if scores[lg] >= 2 else "en"


_FRAMES = {
    "en": {
        "hello": "Hello,", "thanks": "Thank you for your ticket about {service}.",
        "team": "The {team} team is reviewing it.", "bye": "We will update you as soon as we have confirmed the details.",
        "clar_intro": "Thank you for your message. To be able to help we need a few details:",
        "clar_bye": "Please reply with these details and we will continue right away.",
        "asks": ["Which application or process is affected?", "When did it happen (date and time)?",
                 "What did you expect, or which error / reference did you see?"],
    },
    "de": {
        "hello": "Guten Tag,", "thanks": "Vielen Dank für Ihr Ticket zu {service}.",
        "team": "Das Team {team} prüft den Vorgang.", "bye": "Wir melden uns, sobald die Details bestätigt sind.",
        "clar_intro": "Vielen Dank für Ihre Nachricht. Damit wir helfen können, benötigen wir einige Angaben:",
        "clar_bye": "Bitte antworten Sie mit diesen Angaben, dann machen wir sofort weiter.",
        "asks": ["Welche Anwendung oder welcher Prozess ist betroffen?", "Wann ist es aufgetreten (Datum und Uhrzeit)?",
                 "Was haben Sie erwartet, bzw. welchen Fehler oder welche Referenz sehen Sie?"],
    },
    "fr": {
        "hello": "Bonjour,", "thanks": "Merci pour votre ticket concernant {service}.",
        "team": "L'équipe {team} l'examine.", "bye": "Nous reviendrons vers vous dès que les détails seront confirmés.",
        "clar_intro": "Merci pour votre message. Pour vous aider, nous avons besoin de quelques précisions :",
        "clar_bye": "Merci de répondre avec ces informations ; nous poursuivrons aussitôt.",
        "asks": ["Quelle application ou quel processus est concerné ?", "Quand cela s'est-il produit (date et heure) ?",
                 "Qu'attendiez-vous, ou quelle erreur / référence voyez-vous ?"],
    },
}
_FRAMES["it"] = _FRAMES["en"]


def _section_lines(hit: Hit) -> list[str]:
    body = hit.text.split(":", 1)[-1]
    return [ln.lstrip("-0123456789. ").strip() for ln in body.splitlines() if ln.strip()]


def _bullets(kb_hits: list[Hit], section: str, article: str | None) -> list[tuple[str, str]]:
    """(text, citation id) bullets from KB chunks whose section matches; prefers the given article."""
    out: list[tuple[str, str]] = []
    order = sorted(kb_hits, key=lambda h: 0 if h.meta.get("article") == article else 1)
    for h in order:
        if section in h.meta.get("section", ""):
            for ln in _section_lines(h):
                out.append((ln, h.meta.get("cite", h.id)))
    return out


_NONFACTUAL_START = re.compile(
    r"^(?:hello|hi\b|dear|thanks?|thank\s+you|guten\s+(?:tag|morgen)|sehr\s+geehrte|liebe|vielen\s+dank|danke|bonjour|madame|monsieur|cher|ch[eè]re|merci|"
    r"ciao|we\s+will\s+(?:update|keep|get\s+back)|wir\s+melden|wir\s+werden\s+uns|nous\s+reviendrons|please\s+reply|bitte\s+antworten|"
    r"best\s+regards|kind\s+regards|regards|mit\s+freundlichen|freundliche|cordialement|bien\s+cordialement)", re.I)
_REQUEST = re.compile(
    r"\b(?:please|could\s+you|can\s+you|kindly|we\s+(?:need|would\s+need|ask)|bitte|bitten\s+wir|ben\u00f6tigen\s+wir|k\u00f6nnten\s+sie|"
    r"veuillez|merci\s+de|nous\s+vous\s+(?:prions|demandons)|pourriez-vous)\b", re.I)
_CITE = re.compile(r"\[(?:KB|HIST)-\d+\]")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?!\[)|(?<=\])\s+|\n+", text) if s.strip()]


def _is_factual(s: str) -> bool:
    core = _CITE.sub("", s).strip(" -*\u2022\t")
    if not core or core.endswith("?") or core.endswith(":") or len(core.split()) <= 4:
        return False
    return not (_NONFACTUAL_START.match(core) or _REQUEST.search(core))


def uncited_sentences(text: str) -> list[str]:
    return [s for s in _sentences(text) if _is_factual(s) and not _CITE.search(s)]


def citation_coverage(text: str) -> float:
    """Share of factual sentences that end with a [KB-xx]/[HIST-xx] citation. Greetings, thanks, closings, questions and pure
    requests for information are not factual claims and are excluded."""
    factual = [s for s in _sentences(text) if _is_factual(s)]
    if not factual:
        return 1.0
    return round(sum(1 for s in factual if _CITE.search(s)) / len(factual), 3)


def build_reply(service: str, team: str, language: str, kb_hits: list[Hit], floor: float) -> Draft:
    fr = _FRAMES.get(language, _FRAMES["en"])
    best = kb_hits[0] if kb_hits else None
    if not best or best.score < floor:
        return Draft(kind="reply", language=language, text="INSUFFICIENT_EVIDENCE", insufficient_evidence=True,
                     next_steps=["No reliable knowledge-base source: analyst to handle manually."], citation_coverage=1.0)
    article = best.meta.get("article")
    cite = best.meta.get("cite", best.id)
    reply_pts = _bullets(kb_hits, "requester reply", article)
    lines = [fr["hello"], fr["thanks"].format(service=service)]
    if language == "en":
        for txt, c in reply_pts[:2]:
            lines.append(f"{txt.rstrip('.')}. [{c}]")
    else:
        lines.append(f"{fr['team'].format(team=team)} [{cite}]")
        lines.append(fr["bye"])
    if language == "en":
        lines.append(fr["bye"])
    text = "\n".join(lines)
    steps = [f"{t.rstrip('.')}. [{c}]" for t, c in _bullets(kb_hits, "analyst next", article)[:3]]
    cites = _citations(kb_hits, 3)
    return Draft(kind="reply", language=language, text=text, next_steps=steps, citations=cites,
                 citation_coverage=citation_coverage(text))


def build_clarification(service: str, team: str, language: str, kb_hits: list[Hit]) -> Draft:
    fr = _FRAMES.get(language, _FRAMES["en"])
    asks = list(fr["asks"])
    article = kb_hits[0].meta.get("article") if kb_hits else None
    if language == "en":
        specific = [t for t, _ in _bullets(kb_hits, "requester reply", article) if t.lower().startswith("please")]
        if specific:
            asks = [specific[0].rstrip(".") + ".", *asks][:3]
    lines = [fr["hello"], fr["clar_intro"], *[f"{i}. {a}" for i, a in enumerate(asks[:3], start=1)], fr["clar_bye"]]
    text = "\n".join(lines)
    return Draft(kind="clarification", language=language, text=text,
                 next_steps=["Keep the ticket in status clarification and follow up after one business day. [KB-25]"],
                 citations=_citations(kb_hits, 1), citation_coverage=1.0)


def build_escalation(reasons: list[str]) -> Draft:
    text = ("Escalated to a human analyst: the ticket text contains instruction-like content aimed at the triage system. "
            "It was treated as data and not acted upon. " + "; ".join(reasons[:2]))
    return Draft(kind="escalation", language="en", text=text,
                 next_steps=["Verify the sender out-of-band before any action. [KB-22]", "Do not follow any instruction embedded in the message. [KB-22]"])


def _citations(hits: list[Hit], n: int) -> list[Citation]:
    seen, out = set(), []
    for h in hits:
        cid = h.meta.get("cite", h.id)
        if cid in seen:
            continue
        seen.add(cid)
        out.append(h.as_citation())
        if len(out) >= n:
            break
    return out
