"""User-facing assist pipeline: describe images -> retrieve knowledge -> LLM decides -> deterministic routing."""
import collections
import logging
import re
import time
import uuid
from collections.abc import Callable

from . import catalog
from .config import settings
from .knowledge import ticket_text
from .llm import get_llm
from .store import Hit, Store

log = logging.getLogger(__name__)
SERVICE_NAMES = list(catalog.SERVICES)
ProgressCallback = Callable[[dict], None]


def _progress(callback: ProgressCallback | None, debug: bool, step: str, status: str,
              title: str, tool: str | None = None, started: float | None = None,
              detail: str | None = None, data: dict | None = None) -> None:
    if callback is None:
        return
    event = {"step": step, "status": status, "title": title}
    if debug:
        event.update({"tool": tool, "detail": detail, "data": data,
                      "durationMs": round((time.perf_counter() - started) * 1000) if started else None})
    callback(event)

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
        "rationale": {"type": "string", "description": "Why this service and work type, and which urgency and impact definitions apply."},
    },
}

def _definitions(defs: dict[str, str]) -> str:
    return "\n".join(f"    {level}: {text}" for level, text in defs.items())


def _indent(text: str, n: int) -> str:
    return "\n".join(" " * n + line for line in text.splitlines())


SYSTEM_PROMPT = f"""You are the L2 triage assistant of a pan-European asset manager's IT service desk.
A user describes a problem (text, plus descriptions of any screenshots). Decide what it really is and where it goes.

Rules:
- Route by the business process stage that is actually failing, not by the channel or the user's guess
  (a vendor e-mail about a late benchmark file is Rimes Data Feed, an LEI file rejected by a regulator gateway is
  Regulatory Reporting, custodian settlement-status delays are Securities Settlement).
- Work type comes from the substance, not the wording: requests for access, licences, mailboxes, removals or
  clean-ups are Service Requests even when phrased as an outage; something broken or degraded is an Incident.
- Access, licence and access-removal requests for a named business application belong to that application's
  service (e.g. Portfolio Accounting access -> Portfolio Accounting), not Identity & Access Management. Use Identity
  & Access Management only for identity-level work: joiner/mover/leaver accounts, deactivated-user clean-ups,
  role provisioning not tied to one application.
- Urgency and impact follow the Incident Priority Calculation Matrix (below). Assess each one on its own from the
  problem content against these definitions. The historic tickets' urgency/impact are random: never copy them.
  Impact = how much of the business is affected:
{_definitions(catalog.IMPACT_DEFINITIONS)}
  Urgency = how fast it must be fixed:
{_definitions(catalog.URGENCY_DEFINITIONS)}
- How to assess:
  * Impact: decide critical vs non-critical service and full vs partial unavailability first, then the scope:
    highest = a critical service fully down for key operations (or all funds/clients affected);
    high = a critical service partially unavailable or degraded (a failed job, feed, queue or workflow; blocked,
    stale or wrong output), or financial counterparts (brokers, custodians, clients) affected - even when only one
    business entity is affected ("1+ business entities" includes one);
    medium = a non-critical service fully unavailable, or a problem limited to one business entity or team that does
    not degrade a critical service; low = a non-critical service partially unavailable, or individuals affected.
  * Urgency: deadlines (cut-offs, NAV/publication times, regulatory filings), whether a workaround exists and how
    painful it is, and any regulatory breach or security compromise (a suspected compromise is highest urgency and
    at least high impact on a critical service).
  * Critical services: {[s for s in SERVICE_NAMES if catalog.is_critical(s)]}. The same failure on a critical
    service justifies higher urgency/impact than on a non-critical one.
  * Service requests with no service degradation (access, licences, new lists) are usually low or lowest impact;
    raise urgency only for a real deadline (e.g. a joiner starting tomorrow who cannot work).
  * Judge the facts, not the tone: don't escalate shouty wording, don't downplay calm reports of big outages.
- Priority is computed for you from urgency x impact with this matrix; pick the pair that reflects the facts:
{_indent(catalog.matrix_table(), 4)}
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


def build_prompt(text: str, image_descriptions: list[str], hits: list[Hit], duplicates: list[Hit] = ()) -> str:
    return (
        f"Service catalog (service -> owning team):\n"
        + "\n".join(f"- {s}: {catalog.team_for(s)}{' [critical]' if catalog.is_critical(s) else ''}" for s in SERVICE_NAMES)
        + f"\n\nUser problem:\n{text or '(no text)'}\n"
        + ("\nScreenshots (described):\n" + "\n".join(f"{i + 1}. {d}" for i, d in enumerate(image_descriptions)) if image_descriptions else "")
        + f"\n\nKnowledge base matches:\n{_format_hits(hits)}"
        + ("\n\nSimilar OPEN tickets already reported:\n" + "\n".join(f"- #{d.row['id']} {d.row['summary']} (similarity {d.score:.2f})" for d in duplicates) if duplicates else "")
    )


def _level(value: object, field: str) -> str:
    """Models without strict schemas answer "Medium" or " high"; only fall back to low for real garbage."""
    level = str(value or "").strip().lower()
    if level in catalog.LEVELS:
        return level
    log.warning("model returned invalid %s %r; using 'low'", field, value)
    return "low"


def route(decision: dict, hits: list[Hit]) -> dict:
    """Deterministic post-processing: never trust the model with lookups or arithmetic."""
    service = decision["service"] if decision.get("service") in catalog.SERVICES else (hits[0].row["service"] if hits else SERVICE_NAMES[0])
    urgency = _level(decision.get("urgency"), "urgency")
    impact = _level(decision.get("impact"), "impact")
    assignee, assignee_reason = pick_assignee(service, hits)
    return {
        "workType": decision.get("work_type") if decision.get("work_type") in ("Incident", "Service Request") else "Incident",
        "service": service,
        "team": catalog.team_for(service),
        "critical": catalog.is_critical(service),
        "assignee": assignee,
        "assigneeReason": assignee_reason,
        "urgency": urgency,
        "impact": impact,
        "priority": catalog.priority(urgency, impact),
    }


def triage(text: str, image_descriptions: list[str], hits: list[Hit], duplicates: list[Hit] = (),
           progress: ProgressCallback | None = None, debug: bool = False,
           provider: str | None = None) -> tuple[dict, dict]:
    """LLM decision over the retrieved knowledge, then deterministic routing. Returns (decision, routing)."""
    query = "\n".join([text, *(f"Screenshot: {d}" for d in image_descriptions)])
    llm = get_llm(provider)
    started = time.perf_counter()
    tool = "llm.complete_json" if llm.mode != "mock" else "heuristic_decision"
    _progress(progress, debug, "decision", "started", "Analysing the issue", tool,
              detail="Comparing your description with the retrieved precedents")
    decision = llm.complete_json(SYSTEM_PROMPT, build_prompt(text, image_descriptions, hits, duplicates),
                                 DECISION_SCHEMA, "triage_decision",
                                 fallback=lambda: _heuristic_decision(query, hits))
    _progress(progress, debug, "decision", "completed", "Issue analysed", tool, started,
              detail="Generated a support recommendation from the retrieved evidence",
              data={"mode": llm.mode, "model": llm.chat_model,
                    "service": decision.get("service"), "workType": decision.get("work_type"),
                    "usedKnowledgeIds": decision.get("used_knowledge_ids", [])})

    started = time.perf_counter()
    _progress(progress, debug, "routing", "started", "Checking routing and priority", "catalog.route")
    routing = route(decision, hits)
    _progress(progress, debug, "routing", "completed", "Routing and priority ready", "catalog.route", started,
              detail="Applied the service owner and urgency × impact priority matrix",
              data={"service": routing["service"], "team": routing["team"], "priority": routing["priority"],
                    "urgency": routing["urgency"], "impact": routing["impact"],
                    "assignee": routing["assignee"], "assigneeReason": routing["assigneeReason"]})
    return decision, routing


def assist(store: Store, text: str, images: list[str], reporter: str | None = None,
           progress: ProgressCallback | None = None, debug: bool = False, provider: str | None = None) -> dict:
    total_started = time.perf_counter()
    llm = get_llm(provider)
    image_descriptions = []
    if images:
        started = time.perf_counter()
        _progress(progress, debug, "vision", "started", "Reading screenshots", "llm.describe_image",
                  detail=f"Describing {min(len(images), settings.max_images)} attached screenshot(s)")
        for image in images[: settings.max_images]:
            image_descriptions.append(llm.describe_image(image, text))
        _progress(progress, debug, "vision", "completed", "Screenshots understood", "llm.describe_image", started,
                  data={"count": len(image_descriptions), "mode": llm.mode})

    query = "\n".join([text, *(f"Screenshot: {d}" for d in image_descriptions)])
    started = time.perf_counter()
    _progress(progress, debug, "embedding", "started", "Preparing a knowledge search", "llm.embed",
              detail="Turning the problem into a search vector")
    qv = llm.embed([query])[0]
    _progress(progress, debug, "embedding", "completed", "Search vector ready", "llm.embed", started,
              data={"model": llm.embedding_model, "dimensions": int(qv.shape[0])})

    started = time.perf_counter()
    _progress(progress, debug, "knowledge", "started", "Searching relevant knowledge", "store.search_knowledge",
              detail="Looking for the closest curated, catalog, and learned solutions")
    hits = [h for h in store.search_knowledge(qv, settings.top_k) if h.score > settings.min_knowledge_score]
    _progress(progress, debug, "knowledge", "completed", f"Found {len(hits)} knowledge matches",
              "store.search_knowledge", started,
              data={"topK": settings.top_k, "minScore": settings.min_knowledge_score, "matches": [
                  {"id": h.row["id"], "title": h.row["title"], "source": h.row["source"],
                   "service": h.row["service"], "score": round(h.score, 3)} for h in hits]})

    started = time.perf_counter()
    _progress(progress, debug, "duplicates", "started", "Checking open tickets", "store.search_open_tickets",
              detail="Comparing the problem with current open cases")
    duplicates = [h for h in store.search_open_tickets(qv, 3) if h.score >= settings.duplicate_threshold]
    _progress(progress, debug, "duplicates", "completed", f"Found {len(duplicates)} possible duplicates",
              "store.search_open_tickets", started,
              data={"threshold": settings.duplicate_threshold, "matches": [
                  {"id": h.row["id"], "summary": h.row["summary"], "score": round(h.score, 3)} for h in duplicates]})
    decision, routing = triage(text, image_descriptions, hits, duplicates, progress, debug, llm.mode)

    assist_id = uuid.uuid4().hex[:12]
    result = {
        "assistId": assist_id,
        "mode": llm.mode,
        "model": llm.chat_model,
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
            **routing,
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
    _progress(progress, debug, "complete", "completed", "Analysis complete", "assist.pipeline",
              total_started, detail="Saved the result after retrieval, analysis, and routing",
              data={"assistId": assist_id, "mode": llm.mode})
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
