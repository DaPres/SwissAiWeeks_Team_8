"""Shared fixtures. Tests run OFFLINE by default (no key, no network); LLM behaviour is tested against a mock
OpenAI-compatible transport so the plumbing is verified without spending a cent."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("TRIAGE_OFFLINE", "1")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "")
os.environ.setdefault("DECISION_CACHE", "0")

_TEST_DB = Path(__file__).resolve().parent.parent / "outputs" / "test_triagemate.db"
os.environ["DB_PATH"] = str(_TEST_DB)
for _f in (_TEST_DB, Path(str(_TEST_DB) + "-journal")):
    try:
        _f.unlink()
    except FileNotFoundError:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx
import pytest

from triagemate import llm as llm_mod
from triagemate.config import Settings
from triagemate.data import load_training, ticket_from_record
from triagemate.retrieve import get_retriever


@pytest.fixture(scope="session")
def training():
    return load_training()


@pytest.fixture(scope="session")
def retriever():
    return get_retriever()


def make_ticket(summary, description, service=None, work_type="Incident", reporter="maia.berg@intcom.com", **kw):
    rec = {"Summary": summary, "Description": description, "Work type": work_type, "Reporter": reporter,
           "Affected Business or IT Services": [service] if service else [], "Business Entity": [kw.pop("entity", "Luxembourg")],
           "Created date": kw.pop("created", "2026-09-10 10:00"), "Status": "open", "All Comments": kw.pop("comments", []),
           "Request type": kw.pop("request_type", None)}
    t = ticket_from_record(rec, 0, "T", "jira")
    return t.model_copy(update={"id": kw.pop("tid", "T-1")})


@pytest.fixture
def mk():
    return make_ticket


# ---------------------------------------------------------------- mock OpenAI-compatible server
class MockLLM:
    """Records every request; answers according to which prompt it recognises."""

    def __init__(self):
        self.requests: list[dict] = []
        self.fail_times = 0
        self.classification = None      # override dict
        self.reject_json_mode = False
        self.tool_script = ["search_kb", "find_open_related"]

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"url": str(request.url), "body": body, "headers": dict(request.headers)})
        if self.fail_times > 0:
            self.fail_times -= 1
            return httpx.Response(503, json={"error": "overloaded"})
        if str(request.url).endswith("/embeddings"):
            return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]} for _ in body["input"]]})
        if self.reject_json_mode and "response_format" in body:
            return httpx.Response(400, json={"error": "response_format unsupported"})
        msgs = body["messages"]
        system = msgs[0]["content"]
        usage = {"prompt_tokens": 500, "completion_tokens": 60}

        def reply(content=None, tool_calls=None):
            m = {"role": "assistant", "content": content}
            if tool_calls:
                m["tool_calls"] = tool_calls
            return httpx.Response(200, json={"choices": [{"message": m}], "usage": usage})

        if body.get("tools"):
            done = sum(1 for m in msgs if m.get("role") == "tool")
            if done < len(self.tool_script):
                name = self.tool_script[done]
                args = {"query": "ticket"} if name in ("search_kb", "find_similar_tickets") else {}
                return reply(None, [{"id": f"call{done}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}])
            return reply("done")
        if "triage classifier" in system:
            c = self.classification or {"summary_implies": "Incident", "description_implies": "Incident", "work_type": "Incident",
                                        "title_mismatch": False, "service": "Trading Platform", "service_confidence": 0.9,
                                        "unclear": False, "unclear_reason": "", "reasons": ["mock reason"]}
            return reply(json.dumps(c))
        if "Rate the ticket on two independent" in system:
            return reply(json.dumps({"urgency": "high", "impact": "significant", "urgency_evidence": "mock", "impact_evidence": "mock"}))
        if "resolution comment" in system:
            return reply("Resolution: Mock resolution generated from the playbook and confirmed with the requester.")
        if "Draft a reply" in system:
            return reply(json.dumps({"reply": "Hello,\nThe team is checking the service. [KB-01]\nWe will update you as soon as we have confirmed the details.",
                                     "next_steps": ["Confirm business impact with the desk head. [KB-01]", "Correlate with open incidents. [KB-01]"]}))
        if "cannot be actioned as written" in system:
            return reply("Hello,\n1. Which system?\n2. When?\nPlease reply with these details.")
        return reply("ok")


@pytest.fixture
def mock_llm():
    """Install an LLM client wired to the mock transport; restore the offline client afterwards."""
    m = MockLLM()
    settings = Settings(llm_provider="openai", llm_api_key="sk-test", llm_base_url="https://mock.local/v1", llm_model="mock-model",
                        triage_offline=False, llm_max_retries=1)
    client = llm_mod.LLMClient(settings, transport=httpx.MockTransport(m.handler))
    prev = llm_mod._OVERRIDE
    llm_mod.set_client(client)
    yield m
    llm_mod.set_client(prev)
