"""Classifier: work type, affected service and entity — description outranking summary.

Input:  a Ticket, its QualityReport, and REDACTED text; the LLM is asked for a judgement
        constrained to the catalogue's 20 services.
Output: ClassificationOut plus how it was reached (llm / repaired / fallback), and the
        claimed-vs-detected service disagreement that the UI shows the analyst.
The deterministic fallback reads the service straight out of the text (the dataset names it
in the sentence) so classification still works with every provider down.
Failure mode it prevents: trusting the submitted service field (wrong on purpose in the
challenge set) and inventing service names outside the catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass

from app import routing
from app.llm.validated import Validated, ValidatedLLM
from app.quality import QualityReport
from app.schemas import ClassificationOut, Ticket, WorkType

SYSTEM = """You classify IT service-desk tickets for an asset manager.

Rules:
- The DESCRIPTION outranks the SUMMARY. Titles are often wrong on purpose.
- The service field submitted with the ticket may be wrong; judge from the text.
- Choose `service` from this exact list, copying the name verbatim:
{services}
- `work_type` is "Incident" (something is broken/degraded) or "Service Request"
  (access, licence, onboarding, information).
- `reason`: one short sentence quoting the words that decided it.
"""


@dataclass
class ClassificationResult:
    value: ClassificationOut
    source: str
    claimed_service: str | None = None
    service_disagreement: bool = False
    latency_ms: float = 0.0


def _fallback(ticket: Ticket, quality: QualityReport) -> ClassificationOut:
    """No model: match a catalogue service name in the text, prefer the body's work type."""
    body = (ticket.description or "").lower()
    title = (ticket.summary or "").lower()
    found = next((s for s in routing.services() if s.lower() in body), None) or next(
        (s for s in routing.services() if s.lower() in title), None
    )
    service = found or routing.canonical_service(ticket.claimed_service) or "Emailed Support Tickets"
    wt = quality.notes.get("body_work_type")
    work_type = WorkType(wt) if wt else WorkType.INCIDENT
    return ClassificationOut(
        work_type=work_type,
        service=service,
        entity=ticket.entity,
        reason="deterministic fallback: catalogue name found in ticket text",
    )


def classify(ticket: Ticket, redacted_text: str, quality: QualityReport, llm: ValidatedLLM | None = None) -> ClassificationResult:
    llm = llm or ValidatedLLM()
    fallback = _fallback(ticket, quality)
    system = SYSTEM.format(services="\n".join(f"  - {s}" for s in routing.services()))
    user = (
        f"<ticket>\n{redacted_text}\n</ticket>\n\n"
        f"Submitted service (may be WRONG, treat as a hint only): {ticket.claimed_service or 'none'}\n"
        f"Quality flags: unclear={quality.unclear}, title_mismatch={quality.title_mismatch}"
    )
    out: Validated[ClassificationOut] = llm.call(ClassificationOut, system, user, fallback)

    value = out.value
    # The model may still answer off-catalogue; snap it back or fall back.
    canonical = routing.canonical_service(value.service)
    if canonical is None:
        value = value.model_copy(update={"service": fallback.service, "reason": f"{value.reason} [off-catalogue, snapped to fallback]"})
    elif canonical != value.service:
        value = value.model_copy(update={"service": canonical})

    claimed = routing.canonical_service(ticket.claimed_service)
    return ClassificationResult(
        value=value,
        source=out.source,
        claimed_service=claimed,
        service_disagreement=bool(claimed) and claimed != value.service,
        latency_ms=out.latency_ms,
    )
