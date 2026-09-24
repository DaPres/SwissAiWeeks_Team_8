"""End-to-end learning loop in mock mode (no Azure calls)."""
import os
import tempfile
import json

os.environ["LLM_MODE"] = "mock"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["MIN_KNOWLEDGE_SCORE"] = "0"  # mock hash embeddings score far below real ones

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PIXEL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def test_initial_knowledge_is_ingested():
    with TestClient(app) as c:
        k = c.get("/api/health").json()["knowledge"]
        assert k["bySource"]["training"] >= 20  # gold clusters only by default
        assert k["bySource"]["catalog"] == 19
        assert k["minLevel"] == "gold"


def test_curation_levels_and_publish():
    with TestClient(app) as c:
        cur = c.get("/api/curation").json()
        s = cur["summary"]
        assert s["tickets"] == 20000
        assert sum(s["ticketLevels"].values()) == 20000
        gold = [cl for cl in cur["clusters"] if cl["level"] == "gold"]
        assert gold and all(cl["resolutionKind"] == "rich" for cl in gold)
        # the generic intake bucket never reaches the knowledge base
        assert all(cl["level"] == "reject" for cl in cur["clusters"] if cl["service"] == "Emailed Support Tickets")

        detail = c.get(f"/api/curation/clusters/{gold[0]['id']}").json()
        assert detail["samples"] and detail["samples"][0]["Summary"]

        silver = c.post("/api/curation/publish", json={"min_level": "silver"}).json()
        assert silver["published"] > len(gold)
        back = c.post("/api/curation/publish", json={"min_level": "gold"}).json()
        assert back["published"] == len(gold) and back["knowledge"]["minLevel"] == "gold"


def test_assist_routes_to_precedent_expert():
    with TestClient(app) as c:
        r = c.post("/api/assist", json={
            "text": "Trade matching adapter TMA-402 rejected 16 allocations from broker JPM, confirmations blocked",
            "images": [PIXEL],
        }).json()
        assert r["draft"]["service"] == "Trade Matching"
        assert r["draft"]["team"] == "Investment Operations"
        assert r["draft"]["assignee"] == "quinn.anderson@intcom.com"
        assert r["draft"]["priority"] == "high"  # high x high from the matrix
        assert len(r["imageDescriptions"]) == 1


def test_streamed_assist_reports_real_steps_and_debug_details():
    def read_events(response):
        events = []
        kind = None
        for line in response.iter_lines():
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                events.append((kind, json.loads(line[6:])))
        return events

    with TestClient(app) as c:
        request = {"text": "Trade matching adapter TMA-402 rejected 16 allocations", "debug": True}
        with c.stream("POST", "/api/assist/stream", json=request) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            events = read_events(response)

        progress = [data for kind, data in events if kind == "progress"]
        assert [step["step"] for step in progress if step["status"] == "completed"] == [
            "embedding", "knowledge", "duplicates", "decision", "routing", "complete",
        ]
        retrieval = next(step for step in progress if step["step"] == "knowledge" and step["status"] == "completed")
        assert retrieval["tool"] == "store.search_knowledge"
        assert retrieval["data"]["matches"]
        assert retrieval["data"]["matches"][0]["score"] >= 0
        assert retrieval["durationMs"] >= 0
        assert events[-1][0] == "result"
        assert events[-1][1]["draft"]["service"] == "Trade Matching"

        with c.stream("POST", "/api/assist/stream", json={**request, "debug": False}) as response:
            brief = read_events(response)
        assert brief[-1][0] == "result"
        assert all("tool" not in data and "data" not in data for kind, data in brief if kind == "progress")


def test_resolve_teaches_the_next_user():
    with TestClient(app) as c:
        problem = "Bloomberg terminal launcher shows error BBG-7731 license token expired on trading desk PC"
        a = c.post("/api/assist", json={"text": problem}).json()
        before = c.get("/api/health").json()["knowledge"]["bySource"].get("live", 0)

        t = c.post("/api/tickets", json={
            "assist_id": a["assistId"], "summary": problem, "description": problem,
            "work_type": "Incident", "service": "Trading Platform", "urgency": "medium", "impact": "low",
        }).json()
        assert t["priority"] == "low" and t["team"] == "Investment Operations"

        # Same problem again while open -> flagged as duplicate
        again = c.post("/api/assist", json={"text": problem}).json()
        assert again["duplicates"] and again["duplicates"][0]["id"] == t["id"]

        res = c.post(f"/api/tickets/{t['id']}/resolve", json={
            "resolution": "done", "assignee": "vicky.chen@intcom.com",
            "resolution_text": "Re-issued the BBG-7731 licence token via the Bloomberg admin console and restarted the launcher.",
        }).json()
        assert res["learnedKnowledgeId"] == f"live-{t['id']}"
        assert res["knowledge"]["bySource"]["live"] == before + 1

        # Next user with the same problem is routed to the agent who solved it
        nxt = c.post("/api/assist", json={"text": "BBG-7731 license token expired error on Bloomberg launcher"}).json()
        assert nxt["matches"][0]["id"] == f"live-{t['id']}"
        assert nxt["draft"]["assignee"] == "vicky.chen@intcom.com"

        # User confirms the answer helped -> knowledge reinforced -> offered as self-service next time
        c.post(f"/api/assist/{nxt['assistId']}/feedback", json={"helpful": True})
        third = c.post("/api/assist", json={"text": "Bloomberg launcher BBG-7731 token expired"}).json()
        assert third["selfService"]["possible"]


def test_eval_runs_from_the_api():
    import time

    with TestClient(app) as c:
        opts = c.get("/api/eval/options").json()
        assert opts["challenges"] and len(opts["records"]) == 20
        started = c.post("/api/eval/runs", json={"limit": 3, "workers": 2, "configs": [
            {"min_score": 0.0}, {"min_score": 0.9, "top_k": 2, "label": "strict"}]}).json()
        assert [r["total"] for r in started] == [3, 3] and started[1]["label"] == "strict"

        for _ in range(200):
            runs = {r["id"]: r for r in c.get("/api/eval/runs").json()}
            if all(runs[s["id"]]["status"] == "done" for s in started):
                break
            time.sleep(0.05)
        run = c.get(f"/api/eval/runs/{started[0]['id']}").json()
        assert run["status"] == "done" and run["completed"] == 3
        t = run["tickets"][0]
        assert t["record"]["Priority"] and t["record"]["Service Team(s)"] and t["trace"]["resolutionText"]
        # a 0.9 similarity floor filters out every mock-embedding match
        strict = c.get(f"/api/eval/runs/{started[1]['id']}").json()
        assert all(not tk["trace"]["matches"] for tk in strict["tickets"])

        results = c.get(f"/api/eval/runs/{run['id']}/results.json").json()
        assert len(results["records"]) == 3 and results["triage"]["minScore"] == 0.0
        assert c.delete(f"/api/eval/runs/{run['id']}").json()["ok"]
        assert c.get(f"/api/eval/runs/{run['id']}").status_code == 404
