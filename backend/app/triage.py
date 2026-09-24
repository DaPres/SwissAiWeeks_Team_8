"""User-facing assist pipeline: describe images -> retrieve knowledge -> LLM decides -> deterministic routing."""
import collections
import re
import uuid

from . import catalog
from .config import settings
from .knowledge import ticket_text
from .llm import get_llm
from .store import Hit, Store

SERVICE_NAMES = list(catalog.SERVICES)

DECISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "understanding", "work_type", "service", "urgency", "impact", "self_service_possible",
        "self_service_answer", "needs_ticket", "clarifying_question", "ticket_summary",
        "ticket_description", "used_knowledge_ids", "rationale",
    ],
    "properties": {
        "understanding": {"type": "string", "description": "One or two sentences restating the user's actual problem."},
        "work_type": {"type": "string", "enum": ["Incident", "Service Request"]},
        "service": {"type": "string", "enum": SERVICE_NAMES},
        "urgency": {"type": "string", "enum": catalog.LEVELS},
        "impact": {"type": "string", "enum": catalog.LEVELS},
        "self_service_possible": {"type": "boolean"},
        "self_service_answer": {"type": "string", "description": "Steps the user can take themselves, or empty."},
        "needs_ticket": {"type": "boolean"},
        "clarifying_question": {"type": "string", "description": "Only if essential information is missing, else empty."},
        "ticket_summary": {"type": "string"},
        "ticket_description": {"type": "string"},
        "used_knowledge_ids": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string", "description": "Why this service, work type, urgency and impact."},
    },
}

SYSTEM_PROMPT = f"""You are the L2 triage assistant of a pan-European asset manager's IT service desk.
A user describes a problem (text, plus descriptions of any screenshots). Decide what it really is and where it goes.

Rules:
- Route by the business process stage that is actually failing, not by the channel or the user's guess
  (a vendor e-mail about a late benchmark file is Rimes Data Feed, an LEI file rejected by a regulator gateway is
  Regulatory Reporting, custodian settlement-status delays are Securities Settlement).
- Work type comes from the substance, not the wording: requests for access, licences, mailboxes, removals or
  clean-ups are Service Requests even when phrased as an outage; something broken or degraded is an Incident.
- Urgency definitions: {catalog.URGENCY_DEFINITIONS}
- Impact definitions: {catalog.IMPACT_DEFINITIONS}
- Critical services: {[s for s in SERVICE_NAMES if catalog.is_critical(s)]}. Failures there justify higher
  urgency/impact than the same failure on a non-critical service. Don't over-escalate shouty wording; single-user
  service requests are usually low/low.
- Self-service: only offer it when the user can realistically fix or bypass the problem themselves, or when the
  knowledge base shows it is a known issue with a documented user-side answer. Never promise actions only support
  staff can perform. Access, licence and provisioning requests always need a ticket.
- Use the knowledge base items as precedent; cite the ids you relied on.
- Write ticket_summary/ticket_description as a clear, specific ticket an agent can act on (include identifiers)."""


def _format_hits(hits: list[Hit]) -> str:
    lines = []
    for h in hits:
        r = h.row
        lines.append(
            f"- id={r['id']} source={r['source']} service={r['service']} similarity={h.score:.2f}"
            + (f" resolver={r['resolver']}" if r.get("resolver") else "")
            + f"\n  problem: {r['problem'][:600]}"
            + (f"\n  resolution: {r['resolution']}" if r.get("resolution") else "")
        )
    return "\n".join(lines) or "(no matches)"


def _heuristic_decision(text: str, hits: list[Hit]) -> dict:
    """Mock-mode stand-in for the LLM decision, driven purely by retrieval."""
    low = text.lower()
    service = hits[0].row["service"] if hits else "Outlook & Email"
    sr = re.search(r"\b(access|licen[cs]e|mailbox|distribution list|remove|removal|onboard|offboard|new joiner|permission)", low)
    work_type = "Service Request" if sr else "Incident"
    crit = catalog.is_critical(service)
    if work_type == "Service Request":
        urgency, impact = "low", "low"
    else:
        blocked = re.search(r"\b(blocked|down|outage|cannot|can't|failed|stopped|missing|rejected)\b", low)
        urgency = "high" if crit and blocked else "medium" if crit else "low"
        impact = "high" if crit and blocked else "medium" if crit else "low"
    helpful = next((h for h in hits if h.row["helpful"] > 0 and h.row.get("resolution")), None)
    first_line = text.strip().splitlines()[0] if text.strip() else "Problem reported via assistant"
    return {
        "understanding": first_line[:200],
        "work_type": work_type,
        "service": service,
        "urgency": urgency,
        "impact": impact,
        "self_service_possible": helpful is not None,
        "self_service_answer": helpful.row["resolution"] if helpful else "",
        "needs_ticket": helpful is None,
        "clarifying_question": "",
        "ticket_summary": first_line[:120],
        "ticket_description": text.strip(),
        "used_knowledge_ids": [h.row["id"] for h in hits[:3]],
        "rationale": f"[mock mode] Nearest knowledge item belongs to {service}.",
    }


def pick_assignee(service: str, hits: list[Hit]) -> tuple[str | None, str]:
    """The expert who resolved the most similar past problems in this service (training shows the recorded
    Assignee is noise, while resolution authors are consistent per problem class)."""
    votes: collections.Counter = collections.Counter()
    for h in hits:
        r = h.row
        if r["service"] == service and r.get("resolver"):
            votes[r["resolver"]] += h.score * (1 + 0.1 * r["helpful"])
    if votes:
        return votes.most_common(1)[0][0], "resolver of the most similar resolved tickets"
    return None, f"no precedent resolver - route to {catalog.team_for(service)} queue"


def assist(store: Store, text: str, images: list[str], reporter: str | None = None) -> dict:
    llm = get_llm()
    image_descriptions = [llm.describe_image(img, text) for img in images[: settings.max_images]]
    query = "\n".join([text, *(f"Screenshot: {d}" for d in image_descriptions)])
    qv = llm.embed([query])[0]

    hits = store.search_knowledge(qv, settings.top_k)
    duplicates = [h for h in store.search_open_tickets(qv, 3) if h.score >= settings.duplicate_threshold]

    user_prompt = (
        f"Service catalog (service -> owning team):\n"
        + "\n".join(f"- {s}: {catalog.team_for(s)}{' [critical]' if catalog.is_critical(s) else ''}" for s in SERVICE_NAMES)
        + f"\n\nUser problem:\n{text or '(no text)'}\n"
        + ("\nScreenshots (described):\n" + "\n".join(f"{i + 1}. {d}" for i, d in enumerate(image_descriptions)) if image_descriptions else "")
        + f"\n\nKnowledge base matches:\n{_format_hits(hits)}"
        + ("\n\nSimilar OPEN tickets already reported:\n" + "\n".join(f"- #{d.row['id']} {d.row['summary']} (similarity {d.score:.2f})" for d in duplicates) if duplicates else "")
    )
    decision = llm.complete_json(SYSTEM_PROMPT, user_prompt, DECISION_SCHEMA, "triage_decision",
                                 fallback=lambda: _heuristic_decision(query, hits))

    # Deterministic post-processing: never trust the model with lookups or arithmetic.
    service = decision["service"] if decision.get("service") in catalog.SERVICES else (hits[0].row["service"] if hits else SERVICE_NAMES[0])
    urgency = decision.get("urgency") if decision.get("urgency") in catalog.LEVELS else "low"
    impact = decision.get("impact") if decision.get("impact") in catalog.LEVELS else "low"
    assignee, assignee_reason = pick_assignee(service, hits)

    assist_id = uuid.uuid4().hex[:12]
    result = {
        "assistId": assist_id,
        "mode": llm.mode,
        "imageDescriptions": image_descriptions,
        "understanding": decision.get("understanding", ""),
        "selfService": {
            "possible": bool(decision.get("self_service_possible")),
            "answer": decision.get("self_service_answer", ""),
        },
        "needsTicket": bool(decision.get("needs_ticket", True)),
        "clarifyingQuestion": decision.get("clarifying_question", ""),
        "draft": {
            "summary": decision.get("ticket_summary") or text[:120],
            "description": decision.get("ticket_description") or text,
            "workType": decision.get("work_type", "Incident"),
            "service": service,
            "team": catalog.team_for(service),
            "critical": catalog.is_critical(service),
            "assignee": assignee,
            "assigneeReason": assignee_reason,
            "urgency": urgency,
            "impact": impact,
            "priority": catalog.priority(urgency, impact),
        },
        "rationale": decision.get("rationale", ""),
        "usedKnowledgeIds": decision.get("used_knowledge_ids", []),
        "matches": [
            {
                "id": h.row["id"], "source": h.row["source"], "service": h.row["service"], "title": h.row["title"],
                "resolver": h.row.get("resolver"), "resolution": h.row.get("resolution"),
                "helpful": h.row["helpful"], "score": round(h.score, 3),
            }
            for h in hits
        ],
        "duplicates": [
            {"id": d.row["id"], "summary": d.row["summary"], "service": d.row["service"], "score": round(d.score, 3)}
            for d in duplicates
        ],
    }
    store.save_assist(assist_id, text, image_descriptions, result)
    return result


RESOLUTION_SYSTEM = """You are the assigned L2 agent writing the resolution comment on a Jira service ticket at an asset
manager. Write 1-3 sentences in first-person-plural past tense, like: "Traced the rejection to ...; corrected ...,
reprocessed ... and confirmed ...". Be concrete: name the root cause, the corrective action and how it was verified,
reusing identifiers from the ticket. Base it on the precedent resolutions when they fit. No greetings, no filler."""


def draft_resolution(store: Store, ticket: dict) -> dict:
    llm = get_llm()
    qv = llm.embed([ticket_text(ticket)])[0]
    hits = [h for h in store.search_knowledge(qv, settings.top_k * 2) if h.row.get("resolution")][: settings.top_k]
    same_service = [h for h in hits if h.row["service"] == ticket["service"]] or hits
    user = (
        f"Ticket #{ticket['id']} [{ticket['work_type']}] service={ticket['service']}\n"
        f"Summary: {ticket['summary']}\nDescription: {ticket['description']}\n"
        + "".join(f"Screenshot: {d}\n" for d in ticket.get("image_descriptions") or [])
        + f"\nPrecedent resolutions:\n{_format_hits(same_service)}"
    )

    def fallback() -> str:
        return same_service[0].row["resolution"] if same_service else "Investigated the reported issue, applied the fix and confirmed with the requester."

    return {
        "text": llm.complete_text(RESOLUTION_SYSTEM, user, fallback),
        "precedents": [{"id": h.row["id"], "resolution": h.row["resolution"], "score": round(h.score, 3)} for h in same_service[:3]],
    }
