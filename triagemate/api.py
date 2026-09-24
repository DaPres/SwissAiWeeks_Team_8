"""REST API (FastAPI) + the analyst UI. Run:  python -m triagemate.cli serve   ->  http://127.0.0.1:8000

Endpoints
  GET  /health                       provider / index status
  POST /api/triage                   one ticket (Jira record, simple fields, or a pasted e-mail)  -> TriageResult
  POST /api/triage/batch             a list of tickets or a full challenge envelope                 -> results
  POST /api/challenge/predict        challenge envelope in, submission-format predictions out
  POST /api/demo/load                load the 5 demo tickets (+ optionally the challenge file) into the queue
  GET  /api/queue                    priority-sorted queue with badges
  GET  /api/tickets/{id}             ticket + AI result + decisions
  POST /api/tickets/{id}/decision    approve | edit | reject  (captures edit distance and dwell time)
  GET  /api/metrics                  acceptance rate, latency percentiles, cost per ticket, flags
  GET  /api/matrix                   the Urgency x Impact matrix
  GET  /api/kb/search?q=&service=    knowledge-base search with citation ids
  GET  /api/eval                     latest eval/results.json
Safety: every model-bound string is redacted first; the API never sends, deletes or changes anything outside this app (Sec. 4.10).
"""
from __future__ import annotations

import json
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .assign import Assigner
from .challenge import apply_result
from .config import ROOT, get_settings
from .data import find_challenge_file, read_records, ticket_from_record
from .llm import get_client
from .models import Ticket
from .pipeline import Triage
from .priority import matrix_table
from .retrieve import get_retriever
from .store import Store

MAX_CHARS = 20000
_state: dict[str, Any] = {}
_lock = threading.RLock()


def _init() -> None:
    s = get_settings()
    ret = get_retriever()
    store = Store(s.db_file)
    store.index_kb(ret.kb_docs)
    assigner = Assigner.from_training(ret.training)
    for agent, n in store.open_load().items():
        assigner.session_load[agent] += n
    _state.update(ret=ret, store=store, tri=Triage(retriever=ret, assigner=assigner, store=store))


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init()
    yield
    if "store" in _state:
        _state["store"].close()


app = FastAPI(title="TriageMate", version=__version__, lifespan=lifespan,
              description="AI triage co-pilot for Swiss Life service desks: classify, prioritise, route, retrieve, draft, human approves.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def tri() -> Triage:
    if "tri" not in _state:
        _init()
    return _state["tri"]


def store() -> Store:
    if "store" not in _state:
        _init()
    return _state["store"]


# ------------------------------------------------------------------ input parsing
class SimpleTicket(BaseModel):
    summary: str = Field(default="", max_length=2000)
    description: str = Field(default="", max_length=MAX_CHARS)
    service: Optional[str] = None
    work_type: Optional[str] = None
    request_type: Optional[str] = None
    reporter: Optional[str] = None
    entity: Optional[str] = None
    created: Optional[str] = None
    comments: list[str] = Field(default_factory=list)
    email: Optional[str] = Field(default=None, max_length=MAX_CHARS, description="raw pasted e-mail (Subject:/From: headers optional)")
    record: Optional[dict] = Field(default=None, description="a Jira-export record with the challenge field names")


_paste_counter = {"n": 0}


def _from_email(raw: str) -> dict:
    subject, sender, body = "", None, raw
    m = re.match(r"(?is)^((?:[A-Za-z\-]+:.*\n)+)\n?(.*)$", raw.strip())
    if m and re.search(r"(?im)^(subject|from):", m.group(1)):
        headers, body = m.group(1), m.group(2)
        sm = re.search(r"(?im)^subject:\s*(.*)$", headers)
        fm = re.search(r"(?im)^from:\s*.*?<?([\w.\-+]+@[\w.\-]+)>?\s*$", headers)
        subject = sm.group(1).strip() if sm else ""
        sender = fm.group(1) if fm else None
    else:
        first, _, rest = raw.strip().partition("\n")
        subject, body = first[:120], rest or first
    return {"Summary": subject or body[:80], "Description": body.strip(), "Reporter": sender or "info@extcom_00.com",
            "Affected Business or IT Services": ["Emailed Support Tickets"], "Work type": "Incident"}


def to_ticket(payload: SimpleTicket) -> Ticket:
    with _lock:
        _paste_counter["n"] += 1
        n = _paste_counter["n"]
    if payload.record:
        rec = dict(payload.record)
    elif payload.email:
        rec = _from_email(payload.email)
        rec["source"] = "email"
    else:
        rec = {"Summary": payload.summary, "Description": payload.description or payload.summary,
               "Affected Business or IT Services": [payload.service] if payload.service else [],
               "Work type": payload.work_type, "Request type": payload.request_type, "Reporter": payload.reporter,
               "Business Entity": [payload.entity] if payload.entity else [], "Created date": payload.created,
               "All Comments": payload.comments}
    if not (rec.get("Summary") or rec.get("Description")):
        raise HTTPException(422, "provide summary/description, an e-mail, or a Jira record")
    rec.setdefault("Status", "open")
    t = ticket_from_record(rec, n - 1, "PASTE", "paste" if not payload.record else "jira")
    return t.model_copy(update={"id": (rec.get("Key") or f"PASTE-{n:04d}")})


# ------------------------------------------------------------------ endpoints
@app.get("/health")
def health() -> dict:
    ret = _state.get("ret") or get_retriever()
    cc, dc = get_client("classify"), get_client("draft")
    on = cc.enabled or dc.enabled
    return {"status": "ok", "version": __version__, "mode": "llm" if on else "offline", "llm_enabled": on,
            "provider": cc.provider, "model": cc.default_model if cc.enabled else None,
            "draft_provider": dc.provider, "draft_model": dc.default_model if dc.enabled else None, "embedder": ret.embedder.name,
            "kb_chunks": len(ret.kb_docs), "kb_articles": len({d.meta["article"] for d in ret.kb_docs}), "playbook_entries": len(ret.playbook),
            "training_tickets": len(ret.training), "index_build_seconds": round(ret.build_seconds, 2)}


@app.post("/api/triage")
def triage_one(payload: SimpleTicket):
    t = to_ticket(payload)
    with _lock:
        res = tri().run_ticket(t)
    return {"ticket": t.model_dump(exclude={"raw"}), "result": res.model_dump()}


@app.post("/api/triage/batch")
def triage_batch(body: Any = Body(...)):
    if isinstance(body, dict) and "records" in body:
        recs = body["records"]
    elif isinstance(body, list):
        recs = body
    else:
        raise HTTPException(422, "expected a list of records or an envelope with 'records'")
    tickets = [ticket_from_record(r, i, "API", "jira") for i, r in enumerate(recs)]
    with _lock:
        results = tri().run_batch(tickets)
    return {"count": len(results), "results": [r.model_dump() for r in results]}


@app.post("/api/challenge/predict")
def challenge_predict(body: Any = Body(...)):
    """Submission-format output for a challenge envelope (same schema in, same schema out)."""
    recs = body["records"] if isinstance(body, dict) and "records" in body else body
    if not isinstance(recs, list):
        raise HTTPException(422, "expected a list of records or an envelope with 'records'")
    tickets = [ticket_from_record(r, i, "CH", "jira") for i, r in enumerate(recs)]
    with _lock:
        results = tri().run_batch(tickets)
    preds = [apply_result(r, res) for r, res in zip(recs, results)]
    return {**{k: v for k, v in body.items() if k != "records"}, "records": preds} if isinstance(body, dict) else preds


@app.post("/api/demo/load")
def demo_load(include_challenge: bool = Query(False)):
    tickets: list[Ticket] = []
    demo = json.loads((get_settings().data_dir / "demo_tickets.json").read_text(encoding="utf-8"))
    tickets += [ticket_from_record(r, i, "DEMO", "jira").model_copy(update={"id": f"DEMO-{i + 1}"}) for i, r in enumerate(demo)]
    if include_challenge:
        f = find_challenge_file()
        if f:
            recs, _ = read_records(f)
            tickets += [ticket_from_record(r, i, "CH", "jira") for i, r in enumerate(recs)]
    with _lock:
        results = tri().run_batch(tickets)
    return {"loaded": len(results), "ids": [r.ticket_id for r in results]}


@app.get("/api/queue")
def queue(limit: int = Query(200, le=1000)):
    return {"items": store().queue(limit)}


@app.get("/api/tickets/{ticket_id}")
def ticket_detail(ticket_id: str):
    t, r = store().get_ticket(ticket_id), store().get_result(ticket_id)
    if not t or not r:
        raise HTTPException(404, "unknown ticket")
    return {"ticket": t.model_dump(exclude={"raw"}), "result": r.model_dump()}


class Decision(BaseModel):
    action: str
    edited_text: Optional[str] = Field(default=None, max_length=MAX_CHARS)
    reason: Optional[str] = Field(default=None, max_length=1000)
    dwell_ms: Optional[int] = None


@app.post("/api/tickets/{ticket_id}/decision")
def decide(ticket_id: str, d: Decision):
    r = store().get_result(ticket_id)
    if not r:
        raise HTTPException(404, "unknown ticket")
    if d.action == "reject" and not (d.reason or "").strip():
        raise HTTPException(422, "a reason is required when rejecting")
    original = (r.draft.text if r.draft else "") or ""
    try:
        return store().save_decision(ticket_id, d.action, d.edited_text, d.reason, original_text=original, dwell_ms=d.dwell_ms)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/api/metrics")
def metrics():
    return store().metrics()


@app.get("/api/matrix")
def matrix():
    return {"rows": matrix_table()}


@app.get("/api/kb/search")
def kb_search(q: str = Query(..., min_length=2, max_length=500), service: Optional[str] = None, k: int = Query(5, le=10)):
    hits = (_state.get("ret") or get_retriever()).search_kb(q, service=service, k=k)
    return {"hits": [{"id": h.meta.get("cite"), "section": h.meta.get("section"), "title": h.title, "score": round(h.score, 3),
                      "text": h.text[:400]} for h in hits]}


@app.get("/api/playbook")
def playbook():
    ret = _state.get("ret") or get_retriever()
    return {"entries": [{"id": e.id, "service": e.service, "count": e.count, "top_share": e.top_share, "text": e.text} for e in ret.playbook]}


@app.get("/api/eval")
def eval_results():
    p = ROOT / "eval" / "results.json"
    if not p.exists():
        raise HTTPException(404, "run `python -m triagemate.cli eval` first")
    return JSONResponse(json.loads(p.read_text(encoding="utf-8")))


@app.get("/api/dataset-analysis")
def dataset_analysis():
    p = ROOT / "eval" / "dataset_analysis.json"
    if not p.exists():
        raise HTTPException(404, "run `python -m triagemate.cli analyze` first")
    return JSONResponse(json.loads(p.read_text(encoding="utf-8")))


# ------------------------------------------------------------------ UI
UI_DIR = ROOT / "ui"
if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(UI_DIR / "index.html")
