"""Blind-eval runs started from the UI: each run is one configuration (model, top-k, min similarity) over the
challenge file, executed on a background thread with the same engine as `python -m app.evaluate`.

Progress is pushed to every subscriber (the SSE endpoint) as it happens; finished runs are kept as JSON files next
to the knowledge base so they can be compared later.
"""
import asyncio
import json
import logging
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from .evaluate import EvalConfig, evaluate, run_meta
from .llm import get_llm
from .store import Store

log = logging.getLogger(__name__)


def summary(run: dict) -> dict:
    """A run without its per-ticket results."""
    return {k: v for k, v in run.items() if k != "tickets"}


class EvalRuns:
    def __init__(self, store: Store, directory: Path) -> None:
        self.store = store
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.runs: dict[str, dict] = {}
        self.stop: dict[str, threading.Event] = {}
        self.subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()
        for f in sorted(self.dir.glob("*.json")):
            try:
                run = json.loads(f.read_text())
            except (OSError, json.JSONDecodeError):
                log.warning("skipping unreadable eval run %s", f)
                continue
            if run["status"] in ("queued", "running"):  # the server stopped while it ran
                run["status"] = "interrupted"
            self.runs[run["id"]] = run

    # ---------------------------------------------------------------- pub/sub
    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        with self.lock:
            self.subscribers.add((asyncio.get_running_loop(), queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self.lock:
            self.subscribers = {s for s in self.subscribers if s[1] is not queue}

    def _emit(self, name: str, payload: dict) -> None:
        with self.lock:
            subscribers = list(self.subscribers)
        for loop, queue in subscribers:
            loop.call_soon_threadsafe(queue.put_nowait, (name, payload))

    # ---------------------------------------------------------------- runs
    def summaries(self) -> list[dict]:
        with self.lock:
            return sorted((summary(r) for r in self.runs.values()), key=lambda r: -r["createdAt"])

    def get(self, run_id: str) -> dict | None:
        with self.lock:
            run = self.runs.get(run_id)
            return json.loads(json.dumps(run)) if run else None

    def delete(self, run_id: str) -> bool:
        with self.lock:
            if run_id not in self.runs:
                return False
            if run_id in self.stop:
                self.stop[run_id].set()
            del self.runs[run_id]
        (self.dir / f"{run_id}.json").unlink(missing_ok=True)
        self._emit("deleted", {"id": run_id})
        return True

    def cancel(self, run_id: str) -> bool:
        with self.lock:
            event = self.stop.get(run_id)
        if event:
            event.set()
        return event is not None

    def start(self, config: EvalConfig, challenge_path: Path, label: str | None = None, batch: str | None = None) -> dict:
        challenge = json.loads(challenge_path.read_text())
        records = challenge["records"][: config.limit] if config.limit else challenge["records"]
        llm = get_llm(config.llm)
        run_id = uuid.uuid4().hex[:10]
        run = {
            "id": run_id,
            "batch": batch,
            "label": label or f"{llm.label} · k={config.top_k or '-'} · min {config.min_score:g}",
            "config": {**asdict(config), "llm": llm.mode},
            "model": llm.chat_model,
            "source": challenge_path.name,
            "challengeRunId": challenge.get("runId"),
            "status": "queued",
            "total": len(records),
            "completed": 0,
            "problems": 0,
            "createdAt": time.time(),
            "startedAt": None,
            "finishedAt": None,
            "error": None,
            "meta": None,
            "tickets": [None] * len(records),
        }
        with self.lock:
            self.runs[run_id] = run
            self.stop[run_id] = threading.Event()
        self._emit("run", summary(run))
        threading.Thread(target=self._execute, args=(run_id, config, records), daemon=True,
                         name=f"eval-{run_id}").start()
        return summary(run)

    def _update(self, run_id: str, **fields) -> dict | None:
        with self.lock:
            run = self.runs.get(run_id)
            if run is None:  # deleted meanwhile
                return None
            run.update(fields)
            snapshot = summary(run)
        self._emit("run", snapshot)
        return snapshot

    def _execute(self, run_id: str, config: EvalConfig, records: list[dict]) -> None:
        stop = self.stop[run_id]
        self._update(run_id, status="running", startedAt=time.time())

        def on_ticket(i: int, result: dict) -> None:
            with self.lock:
                run = self.runs.get(run_id)
                if run is None:
                    return
                run["tickets"][i] = result
                run["completed"] += 1
                run["problems"] += len(result["problems"])
            self._emit("ticket", {"runId": run_id, "index": i, "ticket": result})
            self._update(run_id)

        try:
            meta = run_meta(self.store, config, self.runs[run_id]["source"])
            evaluate(self.store, records, config, on_ticket, stop.is_set)
            status = "cancelled" if stop.is_set() else "done"
            self._update(run_id, status=status, finishedAt=time.time(), meta=meta)
        except Exception as e:
            log.exception("eval run %s failed", run_id)
            self._update(run_id, status="failed", finishedAt=time.time(), error=str(e))
        finally:
            with self.lock:
                self.stop.pop(run_id, None)
                run = self.runs.get(run_id)
                if run is not None:
                    (self.dir / f"{run_id}.json").write_text(json.dumps(run, ensure_ascii=False))

    def results_file(self, run_id: str, challenge_path: Path) -> dict | None:
        """The run in the challenge submission format (unfinished tickets are left as in the input)."""
        run = self.get(run_id)
        if not run:
            return None
        challenge = json.loads(challenge_path.read_text())
        records = challenge["records"]
        for i, t in enumerate(run["tickets"]):
            if t:
                records[i] = t["record"]
        return {**challenge, "records": records[: run["total"]], "triage": run["meta"]}
