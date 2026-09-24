"""FastAPI app: user assist (deflection), ticket creation, agent resolution with learning."""
import base64
import logging
import re
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import catalog
from .config import settings
from .curation import publish, run_curation, training_tickets
from .knowledge import ensure_ready, learn_from_ticket, ticket_text
from .llm import get_llm
from .store import Store
from .triage import assist, draft_resolution

logging.basicConfig(level=logging.INFO)
store: Store


@asynccontextmanager
async def lifespan(_: FastAPI):
    global store
    store = Store(settings.db_path)
    await run_in_threadpool(ensure_ready, store)
    yield


app = FastAPI(title="Triage Assistant", lifespan=lifespan)

Level = Literal["highest", "high", "medium", "low", "lowest"]
DATA_URL = re.compile(r"^data:image/(png|jpeg|jpg|gif|webp);base64,")


class AssistIn(BaseModel):
    text: str = Field("", max_length=8000)
    images: list[str] = Field(default_factory=list, description="data:image/...;base64 URLs")
    reporter: str | None = None


class FeedbackIn(BaseModel):
    helpful: bool


class TicketIn(BaseModel):
    assist_id: str
    summary: str
    description: str
    work_type: Literal["Incident", "Service Request"]
    service: str
    urgency: Level
    impact: Level
    reporter: str | None = None


class ResolveIn(BaseModel):
    resolution: Literal["done", "cancelled", "clarification", "cannot reproduce"]
    resolution_text: str = Field(min_length=10)
    assignee: str
    # Agents can correct the AI's routing at close; the corrected values are what the system learns.
    service: str | None = None
    work_type: Literal["Incident", "Service Request"] | None = None
    urgency: Level | None = None
    impact: Level | None = None


def _validate_images(images: list[str]) -> None:
    if len(images) > settings.max_images:
        raise HTTPException(400, f"At most {settings.max_images} images")
    for img in images:
        if not DATA_URL.match(img):
            raise HTTPException(400, "Images must be base64 data URLs (png, jpeg, gif, webp)")
        if len(base64.b64decode(img.split(",", 1)[1], validate=False)) > settings.max_image_bytes:
            raise HTTPException(413, f"Image larger than {settings.max_image_bytes // 1024 // 1024} MB")


def _service(name: str) -> str:
    if name not in catalog.SERVICES:
        raise HTTPException(400, f"Unknown service {name!r}")
    return name


@app.get("/api/health")
def health():
    return {"mode": get_llm().mode, "embeddingModel": get_llm().embedding_model, "knowledge": store.knowledge_stats()}


@app.get("/api/catalog")
def get_catalog():
    return {
        "services": [{"name": s, "team": t, "critical": c} for s, (t, c, _) in catalog.SERVICES.items()],
        "levels": catalog.LEVELS,
        "matrix": catalog.MATRIX,
    }


@app.post("/api/assist")
async def post_assist(body: AssistIn):
    if not body.text.strip() and not body.images:
        raise HTTPException(400, "Describe the problem or paste a screenshot")
    _validate_images(body.images)
    return await run_in_threadpool(assist, store, body.text, body.images, body.reporter)


@app.post("/api/assist/{assist_id}/feedback")
def assist_feedback(assist_id: str, body: FeedbackIn):
    a = store.get_assist(assist_id)
    if not a:
        raise HTTPException(404)
    store.update_assist(assist_id, feedback="helpful" if body.helpful else "not_helpful")
    if body.helpful:
        # Deflection confirmed: reinforce the knowledge that answered it.
        store.mark_helpful(a["result"]["usedKnowledgeIds"])
    return {"ok": True}


@app.post("/api/tickets")
async def create_ticket(body: TicketIn):
    a = store.get_assist(body.assist_id)
    if not a:
        raise HTTPException(404, "Unknown assist session")
    service = _service(body.service)
    draft = a["result"]["draft"]
    t = {
        "reporter": body.reporter,
        "user_text": a["user_text"],
        "image_descriptions": a["image_descriptions"],
        "summary": body.summary,
        "description": body.description,
        "work_type": body.work_type,
        "service": service,
        "team": catalog.team_for(service),
        "assignee": draft["assignee"] if service == draft["service"] else None,
        "urgency": body.urgency,
        "impact": body.impact,
        "priority": catalog.priority(body.urgency, body.impact),
        "ai_triage": draft,
        "assist_id": body.assist_id,
    }
    vec = (await run_in_threadpool(get_llm().embed, [ticket_text(t)]))[0]
    ticket_id = store.create_ticket(t, vec)
    store.update_assist(body.assist_id, ticket_id=ticket_id, feedback=a["feedback"] or "escalated")
    return store.get_ticket(ticket_id)


@app.get("/api/tickets")
def list_tickets(status: Literal["open", "resolved"] | None = None):
    return store.list_tickets(status)


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: int):
    t = store.get_ticket(ticket_id)
    if not t:
        raise HTTPException(404)
    return t


@app.post("/api/tickets/{ticket_id}/draft-resolution")
async def post_draft_resolution(ticket_id: int):
    t = get_ticket(ticket_id)
    return await run_in_threadpool(draft_resolution, store, t)


@app.post("/api/tickets/{ticket_id}/resolve")
async def resolve_ticket(ticket_id: int, body: ResolveIn):
    t = get_ticket(ticket_id)
    if t["status"] != "open":
        raise HTTPException(409, "Ticket already resolved")
    service = _service(body.service or t["service"])
    urgency, impact = body.urgency or t["urgency"], body.impact or t["impact"]
    fields = {
        "status": "resolved",
        "resolution": body.resolution,
        "resolution_text": body.resolution_text,
        "assignee": body.assignee,
        "service": service,
        "team": catalog.team_for(service),
        "work_type": body.work_type or t["work_type"],
        "urgency": urgency,
        "impact": impact,
        "priority": catalog.priority(urgency, impact),
        "resolved_at": time.time(),
    }
    store.update_ticket(ticket_id, fields)
    resolved = store.get_ticket(ticket_id)
    learned = None
    # Only real fixes teach anything; cancelled / unclear tickets would pollute the knowledge base.
    if body.resolution == "done":
        learned = await run_in_threadpool(learn_from_ticket, store, resolved)
    return {"ticket": resolved, "learnedKnowledgeId": learned, "knowledge": store.knowledge_stats()}


class CurationRunIn(BaseModel):
    threshold: float | None = Field(None, ge=0.3, le=0.99, description="cosine similarity to merge into a cluster")


class PublishIn(BaseModel):
    min_level: Literal["gold", "silver", "bronze"]


@app.get("/api/curation")
def get_curation():
    summary = store.curation_summary()
    if not summary:
        raise HTTPException(404, "No curation run yet")
    clusters = [{k: v for k, v in c.items() if k != "problem"} for c in store.curation_clusters()]
    return {"summary": summary, "clusters": clusters, "knowledge": store.knowledge_stats()}


@app.get("/api/curation/clusters/{cluster_id}")
def get_curation_cluster(cluster_id: int, limit: int = 12):
    cluster = store.curation_cluster(cluster_id)
    if not cluster:
        raise HTTPException(404)
    history = training_tickets()
    samples = []
    for t in store.curation_cluster_tickets(cluster_id, limit):
        src = history[t["idx"]]
        samples.append({**t, **{k: src.get(k) for k in (
            "Work type", "Summary", "Description", "Affected Business or IT Services", "Assignee",
            "Status", "Resolution", "Created date", "All Comments")}})
    return {"cluster": cluster, "samples": samples}


@app.post("/api/curation/run")
async def post_curation_run(body: CurationRunIn):
    summary = await run_in_threadpool(run_curation, store, body.threshold)
    # Cluster ids change on every run, so re-publish at the current level to keep knowledge in sync.
    level = store.get_meta("knowledge_min_level") or "gold"
    published = await run_in_threadpool(publish, store, level)
    return {"summary": summary, "published": published}


@app.post("/api/curation/publish")
async def post_curation_publish(body: PublishIn):
    return await run_in_threadpool(publish, store, body.min_level)


@app.get("/api/stats")
def stats():
    tickets = store.list_tickets()
    return {
        "knowledge": store.knowledge_stats(),
        "assists": store.assist_stats(),
        "tickets": {
            "open": sum(t["status"] == "open" for t in tickets),
            "resolved": sum(t["status"] == "resolved" for t in tickets),
        },
    }
