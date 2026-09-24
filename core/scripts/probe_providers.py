"""Probe the three cloud providers on the six capabilities that decide per-task routing.

Input:  keys from .env (Apertus, OpenAI, HF/Public AI). Ollama is the known last tier and
        is probed only for the plain-chat baseline.
Output: docs/provider_capabilities.md — capability x provider table with latencies, plus a
        JSON dump of raw results next to it.
Tests: 1 plain chat, 2 strict JSON x20, 3 tool calling x5, 4 German/French tickets,
       5 ~4k-token context with a needle, 6 tokens/cost and Apertus token behaviour.
Run: uv run python scripts/probe_providers.py
Failure mode it prevents: choosing the drafting or agent provider by assumption, and
discovering on Friday that one of them cannot emit a tool call.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openai
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT_MD = ROOT / "docs" / "provider_capabilities.md"
OUT_JSON = ROOT / "docs" / "provider_capabilities.json"
load_dotenv(ROOT / ".env")

JSON_ATTEMPTS = int(os.getenv("PROBE_JSON_ATTEMPTS", "20"))
TOOL_ATTEMPTS = int(os.getenv("PROBE_TOOL_ATTEMPTS", "5"))

# Per-1M-token prices. OpenAI: public list price. Public AI: from the HF router listing.
# Apertus via Swisscom: hackathon access, no published per-token price -> reported as n/a.
PRICING = {"openai": (0.15, 0.60), "publicai": (0.82, 2.92), "apertus": (None, None)}


@dataclass
class ProviderCfg:
    name: str
    base_url: str | None
    model: str
    key_env: str


PROVIDERS = [
    ProviderCfg("apertus", "https://api.swisscom.com/products/swiss-ai-weeks/apertus-1.5-70b/v1",
                "swiss-ai/Apertus-v1.5-70B", "SWISSCOM_APERTUS_API_KEY"),
    ProviderCfg("openai", None, os.getenv("OPENAI_MODEL", "gpt-4o-mini"), "OPENAI_API_KEY"),
    ProviderCfg("publicai", "https://router.huggingface.co/v1",
                os.getenv("PUBLICAI_MODEL", "swiss-ai/Apertus-70B-Instruct-2509:publicai"), "HF_TOKEN"),
    ProviderCfg("ollama", "http://localhost:11434/v1", os.getenv("OLLAMA_MODEL", "llama3.2:3b"), ""),
]

TICKET = ("NAV Calculation generated an automated monitoring alert indicating an operational problem. "
          "The log shows repeated execution errors and the overnight pricing run did not complete.")

SCHEMA_PROMPT = (
    'Reply with ONE JSON object and nothing else, exactly: '
    '{"work_type": "Incident" or "Service Request", "service": string, "urgency": one of '
    '["lowest","low","medium","high","highest"], "quote": a sentence copied from the ticket}'
)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "search_kb",
        "description": "Search the knowledge base of past tickets for a resolution pattern.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "search text"},
                "service": {"type": "string", "description": "service to filter by"},
            },
            "required": ["query"],
        },
    },
}]

DE_TICKET = ("Die NAV-Berechnung ist heute Morgen fehlgeschlagen. Der naechtliche Preislauf wurde nicht "
             "abgeschlossen und die Kunden warten auf die Berichte. Bitte um Rueckmeldung.")
FR_TICKET = ("Le calcul de la VNI a echoue ce matin. Le traitement nocturne des prix ne s'est pas termine "
             "et les clients attendent leurs rapports. Merci de nous tenir informes.")


@dataclass
class Result:
    provider: str
    model: str
    chat_ok: bool = False
    chat_latency_ms: list[float] = field(default_factory=list)
    json_first_try: int = 0
    json_repaired: int = 0
    json_failed: int = 0
    json_latency_ms: list[float] = field(default_factory=list)
    tools_ok: int = 0
    tools_attempts: int = 0
    tools_wellformed: list[str] = field(default_factory=list)
    de_output: str = ""
    fr_output: str = ""
    long_ok: bool = False
    long_answer: str = ""
    long_latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    notes: list[str] = field(default_factory=list)
    error: str | None = None


def client_for(cfg: ProviderCfg) -> openai.OpenAI | None:
    key = os.getenv(cfg.key_env, "").strip() if cfg.key_env else "ollama"
    if not key:
        return None
    return openai.OpenAI(api_key=key, base_url=cfg.base_url, timeout=90, max_retries=0)


PACE_SECONDS = float(os.getenv("PROBE_PACE_SECONDS", "1.0"))


def _chat(cli, cfg, messages, _retries: int = 4, **kw):
    """Paced + backed-off: Apertus rate-limits hard (429 EXPIRED_QUOTA) on rapid calls,
    which would otherwise read as an outage in the probe."""
    delay = 4.0
    for attempt in range(_retries):
        t0 = time.perf_counter()
        try:
            r = cli.chat.completions.create(model=cfg.model, messages=messages, **kw)
            time.sleep(PACE_SECONDS)
            return r, (time.perf_counter() - t0) * 1000
        except openai.RateLimitError:
            if attempt == _retries - 1:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def probe(cfg: ProviderCfg) -> Result:
    res = Result(cfg.name, cfg.model)
    cli = client_for(cfg)
    if cli is None:
        res.error = f"{cfg.key_env} not set"
        return res

    # 1 - plain chat, 3 runs
    try:
        for _ in range(3):
            r, ms = _chat(cli, cfg, [{"role": "user", "content": "Reply with exactly: pong"}], max_tokens=10, temperature=0)
            res.chat_latency_ms.append(round(ms))
            res.chat_ok = bool(r.choices[0].message.content)
        _usage(res, r)
    except Exception as e:
        res.error = f"{type(e).__name__}: {str(e)[:200]}"
        return res

    # 2 - strict JSON
    for _ in range(JSON_ATTEMPTS):
        try:
            r, ms = _chat(cli, cfg, [{"role": "system", "content": SCHEMA_PROMPT},
                                     {"role": "user", "content": TICKET}], max_tokens=200, temperature=0)
            res.json_latency_ms.append(round(ms))
            txt = (r.choices[0].message.content or "").strip()
            if _parses(txt):
                res.json_first_try += 1
                continue
            r2, _ = _chat(cli, cfg, [{"role": "system", "content": SCHEMA_PROMPT},
                                     {"role": "user", "content": TICKET},
                                     {"role": "assistant", "content": txt[:800]},
                                     {"role": "user", "content": "Not valid JSON for the schema. Reply with ONLY the corrected JSON object."}],
                          max_tokens=200, temperature=0)
            res.json_repaired += 1 if _parses((r2.choices[0].message.content or "").strip()) else 0
            res.json_failed += 0 if _parses((r2.choices[0].message.content or "").strip()) else 1
        except Exception as e:
            res.json_failed += 1
            res.notes.append(f"json error: {type(e).__name__}: {str(e)[:90]}")

    # 3 - tool calling
    for _ in range(TOOL_ATTEMPTS):
        res.tools_attempts += 1
        try:
            r, _ = _chat(cli, cfg, [
                {"role": "system", "content": "Use the search_kb tool to look up how this issue was resolved before. Call the tool."},
                {"role": "user", "content": TICKET}], tools=TOOLS, max_tokens=200, temperature=0)
            calls = r.choices[0].message.tool_calls or []
            if calls and calls[0].function.name == "search_kb":
                args = json.loads(calls[0].function.arguments or "{}")
                if "query" in args:
                    res.tools_ok += 1
                    res.tools_wellformed.append(json.dumps(args)[:120])
        except Exception as e:
            res.notes.append(f"tools error: {type(e).__name__}: {str(e)[:90]}")

    # 4 - German / French
    for lang, text, attr in (("German", DE_TICKET, "de_output"), ("French", FR_TICKET, "fr_output")):
        try:
            r, _ = _chat(cli, cfg, [
                {"role": "system", "content": f"You are a service-desk agent. Reply in {lang}, 2 sentences, professional."},
                {"role": "user", "content": text}], max_tokens=220, temperature=0.3)
            setattr(res, attr, (r.choices[0].message.content or "").strip()[:400])
        except Exception as e:
            res.notes.append(f"{lang} error: {str(e)[:90]}")

    # 5 - ~4k tokens with a needle in the middle
    filler = ("Initial triage assigned to Valuation & Pricing and reviewed against the service catalogue. "
              "We validated the issue against NAV Calculation and checked the operating conditions. ")
    needle = "The definitive fix recorded in ticket JIRA-04242 was to restart the pricing scheduler and re-run the batch. "
    chunks = filler * 26 + needle + filler * 26
    try:
        r, ms = _chat(cli, cfg, [
            {"role": "system", "content": "Answer using ONLY the context. Cite the ticket id you used."},
            {"role": "user", "content": f"Context:\n{chunks}\n\nTicket:\n{TICKET}\n\nWhat was the definitive fix, and which ticket id records it?"}],
            max_tokens=200, temperature=0)
        res.long_latency_ms = round(ms)
        res.long_answer = (r.choices[0].message.content or "").strip()[:300]
        res.long_ok = "JIRA-04242" in res.long_answer and "schedul" in res.long_answer.lower()
        _usage(res, r)
    except Exception as e:
        res.notes.append(f"long-context error: {type(e).__name__}: {str(e)[:120]}")

    return res


def _parses(txt: str) -> bool:
    txt = txt.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        d = json.loads(txt)
    except Exception:
        return False
    return isinstance(d, dict) and {"work_type", "service", "urgency", "quote"} <= set(d) and d["urgency"] in {
        "lowest", "low", "medium", "high", "highest"}


def _usage(res: Result, r) -> None:
    u = getattr(r, "usage", None)
    if u:
        res.prompt_tokens += getattr(u, "prompt_tokens", 0) or 0
        res.completion_tokens += getattr(u, "completion_tokens", 0) or 0


def med(xs: list[float]) -> str:
    return f"{statistics.median(xs):.0f}" if xs else "-"


def cost(res: Result) -> str:
    inp, outp = PRICING.get(res.provider, (None, None))
    if inp is None:
        return "n/a (hackathon access)"
    c = res.prompt_tokens / 1e6 * inp + res.completion_tokens / 1e6 * outp
    return f"${c:.5f} for {res.prompt_tokens}+{res.completion_tokens} tok"


def verdict(ok: int, n: int) -> str:
    if n == 0:
        return "not tested"
    if ok == n:
        return "pass"
    return "flaky" if ok else "fail"


def main() -> None:
    results = [probe(p) for p in PROVIDERS]
    OUT_JSON.write_text(json.dumps([r.__dict__ for r in results], indent=1, ensure_ascii=False), encoding="utf-8")

    L = []
    L.append("# Provider capabilities — measured\n")
    L.append(f"Probed {time.strftime('%Y-%m-%d %H:%M')} with `uv run python scripts/probe_providers.py`. "
             f"JSON: {JSON_ATTEMPTS} attempts each; tools: {TOOL_ATTEMPTS}. Raw data in `provider_capabilities.json`.\n")
    L.append("| Capability | " + " | ".join(r.provider for r in results) + " |")
    L.append("|---|" + "---|" * len(results))

    def row(label, fn):
        L.append(f"| {label} | " + " | ".join(fn(r) for r in results) + " |")

    row("1 plain chat", lambda r: "fail" if r.error else ("pass" if r.chat_ok else "fail"))
    row("chat latency (median ms)", lambda r: med(r.chat_latency_ms))
    row("2 strict JSON", lambda r: "-" if r.error else
        verdict(r.json_first_try + r.json_repaired, JSON_ATTEMPTS))
    row("JSON first-try / repaired / failed", lambda r: "-" if r.error else
        f"{r.json_first_try} / {r.json_repaired} / {r.json_failed}")
    row("JSON latency (median ms)", lambda r: med(r.json_latency_ms))
    row("3 tool calling", lambda r: "-" if r.error else verdict(r.tools_ok, r.tools_attempts))
    row("tool calls well-formed", lambda r: "-" if r.error else f"{r.tools_ok}/{r.tools_attempts}")
    row("4 German usable", lambda r: "-" if not r.de_output else ("pass" if len(r.de_output) > 40 else "thin"))
    row("4 French usable", lambda r: "-" if not r.fr_output else ("pass" if len(r.fr_output) > 40 else "thin"))
    row("5 ~4k context needle", lambda r: "-" if r.error else ("pass" if r.long_ok else "fail"))
    row("long-context latency (ms)", lambda r: f"{r.long_latency_ms:.0f}" if r.long_latency_ms else "-")
    row("6 probe cost", cost)
    row("error", lambda r: r.error or "-")

    L.append("\n## Language samples\n")
    for r in results:
        if r.de_output or r.fr_output:
            L.append(f"### {r.provider} (`{r.model}`)\n")
            if r.de_output:
                L.append(f"**DE:** {r.de_output}\n")
            if r.fr_output:
                L.append(f"**FR:** {r.fr_output}\n")

    L.append("\n## Long-context answers\n")
    for r in results:
        if r.long_answer:
            L.append(f"- **{r.provider}**: {r.long_answer}\n")

    notes = [f"- **{r.provider}**: {n}" for r in results for n in r.notes]
    if notes:
        L.append("\n## Notes\n")
        L.extend(notes)

    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:22]))
    print(f"\nwrote {OUT_MD}")


if __name__ == "__main__":
    main()
