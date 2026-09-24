"""FastAPI app: user assist (deflection), ticket creation, agent resolution with learning."""
import base64
import asyncio
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import catalog
from .config import settings
from .curation import publish, run_curation, training_tickets
from .eval_runs import EvalRuns
from .evaluate import EvalConfig, challenge_files
from .knowledge import ensure_ready, learn_from_ticket, ticket_text
from .llm import default_provider, get_llm, providers
from .store import Store
from .triage import assist, draft_resolution

logging.basicConfig(level=logging.INFO)
store: Store
evals: EvalRuns


@asynccontextmanager
async def lifespan(_: FastAPI):
    global store, evals
    store = Store(settings.db_path)
    await run_in_threadpool(ensure_ready, store)
    evals = EvalRuns(store, settings.db_path.parent / "evals")
    yield


app = FastAPI(title="Triage Assistant", lifespan=lifespan)

Level = Literal["highest", "high", "medium", "low", "lowest"]
DATA_URL = re.compile(r"^data:image/(png|jpeg|jpg|gif|webp);base64,")


class AssistIn(BaseModel):
    text: str = Field("", max_length=8000)
    images: list[str] = Field(default_factory=list, description="data:image/...;base64 URLs")
    reporter: str | None = None
    debug: bool = False
    llm: str | None = Field(None, description="provider id from /api/llms; default when omitted")


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


def _provider(name: str | None) -> str | None:
    if name and name not in providers():
        raise HTTPException(400, f"LLM {name!r} is not enabled")
    return name


def _service(name: str) -> str:
    if name not in catalog.SERVICES:
        raise HTTPException(400, f"Unknown service {name!r}")
    return name


@app.get("/api/health")
def health():
    return {"mode": get_llm().mode, "embeddingModel": get_llm().embedding_model, "knowledge": store.knowledge_stats()}


@app.get("/api/llms")
def llms():
    """Enabled chat providers, for the model picker."""
    return {
        "default": default_provider(),
        "providers": [
            {"id": p.mode, "label": p.label, "model": p.chat_model, "vision": bool(getattr(p, "vision_model", None))}
            for p in providers().values()
        ],
        "embeddingModel": get_llm().embedding_model,
    }


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
    return await run_in_threadpool(assist, store, body.text, body.images, body.reporter,
                                   None, False, _provider(body.llm))


@app.post("/api/assist/stream")
async def post_assist_stream(body: AssistIn):
    if not body.text.strip() and not body.images:
        raise HTTPException(400, "Describe the problem or paste a screenshot")
    _validate_images(body.images)
    provider = _provider(body.llm)

    async def events():
        loop = asyncio.get_running_loop()
        output: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

        def report(event: dict) -> None:
            loop.call_soon_threadsafe(output.put_nowait, ("progress", event))

        async def run_assist() -> None:
            try:
                result = await run_in_threadpool(assist, store, body.text, body.images,
                                                 body.reporter, report, body.debug, provider)
                await output.put(("result", result))
            except Exception:
                logging.exception("streamed assist failed")
                await output.put(("error", {"message": "Analysis failed. Please try again."}))
            finally:
                await output.put(None)

        asyncio.create_task(run_assist())
        while True:
            try:
                item = await asyncio.wait_for(output.get(), timeout=15)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if item is None:
                break
            name, payload = item
            yield f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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


def _sse(name: str, payload: object) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _challenge(name: str | None):
    files = challenge_files()
    if not files:
        raise HTTPException(404, "No challenge file found (jira_hackathon_blind_eval_challenge_*.json)")
    if not name:
        return files[0]
    match = next((f for f in files if f.name == name), None)
    if not match:
        raise HTTPException(400, f"Unknown challenge file {name!r}")
    return match


class EvalConfigIn(BaseModel):
    llm: str | None = None
    top_k: int | None = Field(None, ge=1, le=30)
    min_score: float = Field(0.0, ge=0.0, le=0.95)
    label: str | None = Field(None, max_length=80)


class EvalStartIn(BaseModel):
    configs: list[EvalConfigIn] = Field(min_length=1, max_length=8)
    challenge: str | None = None
    limit: int | None = Field(None, ge=1)
    workers: int = Field(4, ge=1, le=16)


@app.get("/api/eval/options")
def eval_options():
    """What the Evaluation tab can configure, plus the challenge tickets as submitted (the input column)."""
    files = challenge_files()
    challenge = json.loads(files[0].read_text()) if files else {"records": []}
    return {
        "challenges": [f.name for f in files],
        "defaults": {"topK": settings.top_k, "minScore": 0.0, "assistMinScore": settings.min_knowledge_score, "workers": 4},
        "records": [{k: r.get(k) for k in ("Summary", "Description", "Work type", "Request type",
                                             "Affected Business or IT Services", "Urgency", "Impact", "Priority")}
                    for r in challenge["records"]],
    }


@app.get("/api/eval/runs")
def eval_runs():
    return evals.summaries()


@app.post("/api/eval/runs")
def start_eval_runs(body: EvalStartIn):
    path = _challenge(body.challenge)
    batch = uuid.uuid4().hex[:8]
    return [evals.start(EvalConfig(llm=_provider(c.llm), top_k=c.top_k, min_score=c.min_score,
                                   workers=body.workers, limit=body.limit), path, c.label, batch)
            for c in body.configs]


@app.get("/api/eval/runs/{run_id}")
def get_eval_run(run_id: str):
    run = evals.get(run_id)
    if not run:
        raise HTTPException(404)
    return run


@app.post("/api/eval/runs/{run_id}/cancel")
def cancel_eval_run(run_id: str):
    return {"cancelling": evals.cancel(run_id)}


@app.delete("/api/eval/runs/{run_id}")
def delete_eval_run(run_id: str):
    if not evals.delete(run_id):
        raise HTTPException(404)
    return {"ok": True}


@app.get("/api/eval/runs/{run_id}/results.json")
def eval_results_file(run_id: str):
    run = evals.get(run_id)
    if not run:
        raise HTTPException(404)
    results = evals.results_file(run_id, _challenge(run["source"]))
    name = f"{run['challengeRunId'] or 'eval'}.{run_id}.results.json"
    return Response(json.dumps(results, indent=2, ensure_ascii=False), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/eval/stream")
async def eval_stream():
    """Server-sent events for every eval run: `snapshot` (all run summaries) on connect, then `run` (status /
    progress), `ticket` (one finished ticket: {runId, index, ticket}) and `deleted` as they happen."""
    queue = evals.subscribe()

    async def events():
        try:
            yield _sse("snapshot", evals.summaries())
            while True:
                try:
                    name, payload = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(name, payload)
        finally:
            evals.unsubscribe(queue)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# Container image: the built frontend is served from the same origin (SPA fallback to index.html).
if settings.static_dir and (settings.static_dir / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=settings.static_dir / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        file = (settings.static_dir / path).resolve()
        if path and file.is_file() and file.is_relative_to(settings.static_dir.resolve()):
            return FileResponse(file)
        return FileResponse(settings.static_dir / "index.html")
