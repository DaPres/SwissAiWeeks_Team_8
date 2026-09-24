"""Provider smoke test:  python -m triagemate.cli smoke

Checks, per role (classify / draft) and for embeddings, with the keys in .env (never printed):
  1 chat            - a plain completion
  2 json            - schema-constrained JSON (the classifier contract)
  3 tools           - OpenAI-style tool calling (the agent loop); if weak, the agent degrades to its deterministic policy
  4 embeddings      - multilingual retrieval (optional)
  5 end-to-end      - one full ticket through the hybrid pipeline (cost, latency, prompt versions)
"""
from __future__ import annotations

import sys
import time

from pydantic import BaseModel

from triagemate.config import get_settings
from triagemate.llm import LLMClient, LLMError, LLMUnavailable, get_client, track


class _Ping(BaseModel):
    ok: bool
    word: str


def _mask(k: str) -> str:
    return f"…{k[-4:]}" if k and len(k) > 8 else ("(none)" if not k else "(short)")


def _row(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name:<12} {detail}")
    return ok


def check_role(role: str) -> dict[str, bool]:
    c: LLMClient = get_client(role)
    print(f"\n== role '{role}': provider={c.provider} model={c.default_model or '-'} key={_mask(c.cfg.api_key)} enabled={c.enabled}")
    if not c.enabled:
        print("  (not configured - skipped; the system runs its deterministic engine for this role)")
        return {}
    res: dict[str, bool] = {}
    t0 = time.perf_counter()
    try:
        with track() as u:
            out = c.chat([{"role": "user", "content": "Reply with exactly one word: pong"}], max_tokens=20, name="smoke_chat")
        res["chat"] = _row("chat", bool(out["content"]), f"{(out['content'] or '').strip()[:30]!r}  {int((time.perf_counter() - t0) * 1000)} ms  {u.tokens_in}+{u.tokens_out} tokens")
    except (LLMError, LLMUnavailable) as e:
        res["chat"] = _row("chat", False, str(e)[:160])
        print("  -> fix the key / base URL / model in .env and re-run; skipping the remaining checks for this role")
        return res
    try:
        out = c.chat_json("You are a test. Reply with JSON.", 'Return {"ok": true, "word": "pong"}', _Ping, max_tokens=60, name="smoke_json")
        res["json"] = _row("json", out.ok is True, f"{out.model_dump()}")
    except (LLMError, LLMUnavailable) as e:
        res["json"] = _row("json", False, str(e)[:160])
    try:
        tools = [{"type": "function", "function": {"name": "search_kb", "description": "Search the knowledge base.",
                                                   "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}]
        out = c.chat([{"role": "system", "content": "You must call the search_kb tool to answer."},
                      {"role": "user", "content": "How do I fix rejected trade allocations?"}], tools=tools, max_tokens=80, name="smoke_tools")
        res["tools"] = _row("tools", bool(out["tool_calls"]), f"called {[t['name'] for t in out['tool_calls']]}" if out["tool_calls"] else "no tool call -> agent will use its deterministic policy")
    except (LLMError, LLMUnavailable) as e:
        res["tools"] = _row("tools", False, str(e)[:160])
    return res


def main() -> int:
    s = get_settings()
    print(f"default provider: {s.llm_provider} | classify: {s.role_provider('classify')} | draft: {s.role_provider('draft')} | offline switch: {s.triage_offline}")
    results = {r: check_role(r) for r in dict.fromkeys(("classify", "draft"))}

    print("\n== embeddings")
    ep = s.embed_profile()
    if ep is None:
        print("  (no embedding provider configured - a local TF-IDF/LSA model is used)")
    else:
        try:
            v = get_client("classify").embed(["Trading platform is down", "Die Handelsplattform ist nicht erreichbar"])
            import numpy as np
            a, b = np.array(v[0]), np.array(v[1])
            cos = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
            _row("embeddings", len(v) == 2, f"{ep.provider}:{ep.model} dim={len(v[0])} EN-DE cosine={cos:.2f} (multilingual if > 0.5)")
        except (LLMError, LLMUnavailable, Exception) as e:  # noqa: BLE001
            _row("embeddings", False, str(e)[:160])

    print("\n== end-to-end (one German ticket, hybrid mode)")
    ok_e2e = False
    if any(r.get("chat") for r in results.values()):
        from triagemate.models import Ticket
        from triagemate.pipeline import Triage
        t = Ticket(id="SMOKE-1", summary="Handelsplattform: Kurse werden nicht aktualisiert",
                   description="Seit 08:05 werden in der Handelsplattform keine Kurse mehr aktualisiert. Die Händler von Anna Keller (anna.keller@intcom.com) können nicht sicher handeln.",
                   services=["Trading Platform"], work_type="Incident", reporter="anna.keller@intcom.com", created="2026-09-24 09:12", source="paste")
        r = Triage().run_ticket(t)
        ok_e2e = _row("pipeline", r.classification.source in ("ensemble", "llm"),
                      f"{r.work_type} | {r.service} | {r.priority} (U={r.urgency}/I={r.impact}) | {r.latency_ms:.0f} ms | {r.tokens_in}+{r.tokens_out} tokens | ${r.cost_usd:.5f}")
        print(f"     prompts: {r.prompt_versions}")
        print(f"     resolution note ({r.resolution_source}): {r.resolution_note[:140]}")
        print(f"     draft language={r.draft.language} coverage={r.draft.citation_coverage}; notes: {[n for n in r.notes if 'unavailable' in n or 'overrode' in n or 'rejected' in n]}")
    else:
        print("  (skipped - no working chat provider)")

    hard_ok = all(v.get("chat") and v.get("json") for v in results.values() if v)
    print("\nRESULT:", "READY - hybrid mode works" if (hard_ok and ok_e2e) else "not ready - see FAIL lines (offline mode still works)")
    return 0 if (hard_ok and ok_e2e) or not any(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
