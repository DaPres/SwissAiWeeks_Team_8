"""Ping every LLM provider with a trivial prompt and report which ones work.

Run after filling in .env:   uv run python test_providers.py
Ollama is always tested here (even when online) so you know the offline fallback is ready.
"""

import time

import openai

from app.agent.llm_client import LLMClient, ProviderUnavailable, default_providers

PROMPT = [{"role": "user", "content": "Reply with exactly the word: pong"}]


def main() -> None:
    client = LLMClient()
    ok = 0
    for p in default_providers():
        t0 = time.perf_counter()
        try:
            text = client.call_provider(p, PROMPT, max_tokens=10)
            status, detail = "OK  ", repr(text.strip())[:60]
            ok += 1
        except ProviderUnavailable as e:
            status, detail = "SKIP", str(e)
        except openai.APIStatusError as e:
            status, detail = "FAIL", f"HTTP {e.status_code}: {str(e)[:120]}"
        except Exception as e:
            status, detail = "FAIL", f"{type(e).__name__}: {str(e)[:120]}"
        ms = (time.perf_counter() - t0) * 1000
        print(f"[{status}] {p.name:<17} {p.model:<45} {ms:7.0f} ms  {detail}")
    print(f"\n{ok}/{len(default_providers())} providers reachable.")


if __name__ == "__main__":
    main()
