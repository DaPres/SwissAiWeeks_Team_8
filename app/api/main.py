"""FastAPI backend for TriageMate.

Endpoints: POST /triage (ticket in, result contract out), POST /decision (analyst
approve/edit/reject with reason, edit distance and dwell), GET /metrics (dashboard feed),
GET /queue + /ticket/{id} for the console, and POST /chat kept as a secondary
"ask about this ticket" feature.
The index and store are built once at startup so the first demo request is not slow.
Failure mode it prevents: the console reaching into the pipeline's internals, and a single
bad ticket taking down the demo (every triage is wrapped).

Run: uv run uvicorn app.api.main:app --port 8000
"""

from __future__ import annotations

import difflib
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import store
from app.agent import AllProvidersFailed, LLMClient
from app.pipeline import triage
from app.rag.hybrid import HybridIndex
from app.rag.retrieve import format_context, retrieve
from app.safety import screen
from app.schemas import Ticket, TriageResult

STATE: dict = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    con = store.connect()
    if store.ticket_count(con) == 0:
        store.load_corpus(con)
    STATE["con"] = con
    STATE["index"] = HybridIndex.from_store(con)  # also warms the embedding model
    yield


app = FastAPI(title="TriageMate", lifespan=lifespan)


class TriageRequest(BaseModel):
    """Either an existing ticket id, or a pasted ticket/email."""

    ticket_id: str | None = None
    summary: str = ""
    description: str = ""
    claimed_service: str | None = None
    entity: str | None = None
    reporter: str | None = None
    created: str | None = None
    force: bool = False  # re-triage even if a stored result exists


class DecisionRequest(BaseModel):
    ticket_id: str
    decision: str = Field(pattern="^(approve|edit|reject)$")
    reason: str = ""
    dwell_seconds: float = 0.0
    edited_text: str = ""


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "tickets": store.ticket_count(STATE["con"])}


@app.post("/triage", response_model=TriageResult)
def triage_endpoint(req: TriageRequest) -> TriageResult:
    con, index = STATE["con"], STATE["index"]

    if req.ticket_id and not (req.description or req.summary):
        if not req.force and (stored := store.get_result(con, req.ticket_id)):
            return stored
        ticket = store.get_ticket(con, req.ticket_id)
        if ticket is None:
            raise HTTPException(404, f"unknown ticket {req.ticket_id}")
    else:
        ticket = Ticket(
            id=req.ticket_id or f"PASTED-{abs(hash(req.description)) % 10**6:06d}",
            summary=req.summary, description=req.description,
            claimed_service=req.claimed_service, entity=req.entity,
            reporter=req.reporter, created=req.created,
        )

    try:
        result = triage(ticket, con, index)
    except Exception as e:  # the demo must never 500 on one ticket
        raise HTTPException(503, f"triage failed: {type(e).__name__}: {e}")
    store.save_result(con, result)
    return result


@app.post("/decision")
def decision_endpoint(req: DecisionRequest) -> dict:
    con = STATE["con"]
    result = store.get_result(con, req.ticket_id)
    if result is None:
        raise HTTPException(404, f"no triage result for {req.ticket_id}")

    original = result.graded.resolution_comment
    distance = _edit_distance(original, req.edited_text) if req.decision == "edit" else 0
    row_id = store.save_decision(con, req.ticket_id, req.decision, req.reason, distance,
                                 req.dwell_seconds, req.edited_text)
    if req.decision == "edit" and req.edited_text:
        result.graded.resolution_comment = req.edited_text
        store.save_result(con, result)
    return {"id": row_id, "decision": req.decision, "edit_distance": distance}


@app.get("/metrics")
def metrics_endpoint() -> dict:
    con = STATE["con"]
    m = store.decision_metrics(con)
    rows = con.execute("SELECT payload FROM results").fetchall()
    results = [TriageResult.model_validate_json(r["payload"]) for r in rows]
    if results:
        m["triaged"] = len(results)
        m["by_resolution"] = _count(r.graded.resolution.value for r in results)
        m["by_priority"] = _count(r.graded.priority.value for r in results)
        m["by_team"] = _count(r.graded.team for r in results)
        m["mean_confidence"] = round(sum(r.confidence for r in results) / len(results), 3)
        m["below_floor"] = sum(1 for r in results if r.confidence < 0.6)
        m["flagged"] = _count(f for r in results for f in r.flags.badges())
        m["citation_coverage"] = round(
            sum(1 for r in results if "[" in r.graded.resolution_comment) / len(results), 3)
        m["mean_comment_chars"] = round(
            sum(len(r.graded.resolution_comment) for r in results) / len(results), 1)
    else:
        m["triaged"] = 0
    return m


@app.get("/queue")
def queue_endpoint(limit: int = 50) -> list[dict]:
    """Triaged tickets, highest priority first — what the analyst works down."""
    con = STATE["con"]
    order = {"highest": 0, "high": 1, "medium": 2, "low": 3, "lowest": 4}
    rows = con.execute("SELECT payload FROM results LIMIT ?", (limit,)).fetchall()
    items = []
    for row in rows:
        r = TriageResult.model_validate_json(row["payload"])
        decided = con.execute("SELECT decision FROM decisions WHERE ticket_id = ? ORDER BY id DESC LIMIT 1",
                              (r.ticket_id,)).fetchone()
        items.append({
            "ticket_id": r.ticket_id, "priority": r.graded.priority.value,
            "service": r.graded.service, "team": r.graded.team,
            "work_type": r.graded.work_type.value, "resolution": r.graded.resolution.value,
            "confidence": r.confidence, "badges": r.flags.badges(),
            "decision": decided["decision"] if decided else None,
        })
    return sorted(items, key=lambda i: (order.get(i["priority"], 9), -i["confidence"]))


@app.get("/ticket/{ticket_id}")
def ticket_endpoint(ticket_id: str) -> dict:
    con = STATE["con"]
    ticket = store.get_ticket(con, ticket_id)
    result = store.get_result(con, ticket_id)
    if ticket is None and result is None:
        raise HTTPException(404, f"unknown ticket {ticket_id}")
    payload: dict = {"result": result.model_dump(mode="json") if result else None}
    if ticket:
        report = screen(ticket.text(), names=[ticket.reporter or ""])
        payload["ticket"] = {
            "id": ticket.id, "summary": ticket.summary, "description": ticket.description,
            "claimed_service": ticket.claimed_service, "entity": ticket.entity,
            "created": ticket.created, "status": ticket.status, "comments": ticket.comments,
            "redacted_text": report.redacted_text, "redactions": report.redactions,
        }
    return payload


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=0, le=10)


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    """Secondary feature: ask a free-text question about the knowledge base."""
    chunks = retrieve(req.message, k=req.top_k) if req.top_k else []
    try:
        resp = LLMClient().ask(req.message, context=format_context(chunks))
    except AllProvidersFailed as e:
        raise HTTPException(503, {"error": "all LLM providers failed", "providers": e.errors})
    return {"answer": resp.text, "provider": resp.provider, "model": resp.model,
            "sources": [{"source": c.source, "score": round(c.score, 3)} for c in chunks]}


def _edit_distance(a: str, b: str) -> int:
    """Characters changed between the draft and what the analyst sent — a quality signal."""
    sm = difflib.SequenceMatcher(None, a or "", b or "")
    return sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")


def _count(values) -> dict:
    out: dict = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
