# Provider capabilities — measured

Probed 2026-09-24 12:45 with `uv run python scripts/probe_providers.py`. JSON: 20 attempts each; tools: 5. Raw data in `provider_capabilities.json`.

| Capability | apertus | openai | publicai | ollama |
|---|---|---|---|---|
| 1 plain chat | pass | fail | fail | fail |
| chat latency (median ms) | 1242 | - | - | - |
| 2 strict JSON | pass | - | - | - |
| JSON first-try / repaired / failed | 20 / 0 / 0 | - | - | - |
| JSON latency (median ms) | 2162 | - | - | - |
| 3 tool calling | pass | - | - | - |
| tool calls well-formed | 5/5 | - | - | - |
| 4 German usable | pass | - | - | - |
| 4 French usable | pass | - | - | - |
| 5 ~4k context needle | pass | - | - | - |
| long-context latency (ms) | 1831 | - | - | - |
| 6 probe cost | n/a (hackathon access) | $0.00000 for 0+0 tok | $0.00000 for 0+0 tok | n/a (hackathon access) |
| error | - | AuthenticationError: Error code: 401 - {'error': {'message': 'Incorrect API key provided: https://************************************************************************************9KG9. You can find your API key at http | AuthenticationError: Error code: 401 - {'error': 'Invalid username or password.'} | NotFoundError: Error code: 404 - {'error': {'message': "model 'llama3.2:3b' not found", 'type': 'not_found_error', 'param': None, 'code': None}} |

## Language samples

### apertus (`swiss-ai/Apertus-v1.5-70B`)

**DE:** Wir haben Ihre Meldung erhalten und nehmen das Problem mit der fehlgeschlagenen NAV-Berechnung sowie dem nicht abgeschlossenen nächtlichen Preislauf sehr ernst. Unser Team arbeitet bereits daran, die Ursache zu identifizieren und eine Lösung zu finden, um die Berichte für Ihre Kunden zeitnah bereitzustellen. Wir halten Sie über den Fortschritt auf dem Laufenden.

**FR:** Nous prenons note de l'incident concernant l'échec du calcul de la VNI ce matin et de l'interruption du traitement nocturne des prix. Notre équipe technique est immédiatement mobilisée pour résoudre ce problème et nous vous tiendrons informés de l'avancement dès que possible.


## Long-context answers

- **apertus**: The definitive fix was to restart the pricing scheduler and re-run the batch, and it is recorded in ticket JIRA-04242.


## Routing decision (from these measurements)

| Task | Setting | Provider | Why |
|---|---|---|---|
| classify | `TASK_CLASSIFY_PROVIDER` | swisscom-apertus | 20/20 strict JSON first-try, median 2.2 s |
| extract | `TASK_EXTRACT_PROVIDER` | swisscom-apertus | same call shape as classify |
| agent loop | `TASK_AGENT_PROVIDER` | swisscom-apertus | 5/5 well-formed tool calls |
| draft | `TASK_DRAFT_PROVIDER` | swisscom-apertus | fluent, professional German and French |

**This is currently an all-Swiss deployment, by measurement rather than preference:** Apertus
is the only provider whose credentials work today. It passed every capability outright, so
even with the other two restored it is a legitimate default rather than a fallback.

The original assumption (OpenAI for classify/extract/agent, Apertus for drafting) **could not
be tested** — see blockers below. Re-run the probe once the keys are fixed; changing routing
is four `.env` values, and the fallback chain is unchanged either way.

## Blockers (credentials, not code)

| Provider | Diagnosis | Fix |
|---|---|---|
| **OpenAI** | `OPENAI_API_KEY` holds a **URL** (`https://platform…`), not a key — the Keymaker redemption link was pasted instead of the key it issues | Open that link, redeem, paste the `sk-…` key |
| **Public AI** | `HF_TOKEN` holds a **`zpka_…`** value — that is a Zuplo gateway key, not a Hugging Face token (they start with `hf_`). Verified it is not an Apertus key either (401 against Swisscom) | Create a token at huggingface.co/settings/tokens with *"Make calls to Inference Providers"* |

The model id `swiss-ai/Apertus-70B-Instruct-2509:publicai` **is correct** — confirmed live on
the HF router with tools and structured output at $0.82/$2.92 per M tokens. The earlier guess
was right, so a Public AI failure in this probe is a credential problem, not a naming one.

## Apertus operational notes

- **Rate limit:** three rapid calls produced `429 EXPIRED_QUOTA`. This reads like an outage
  but is throttling; the client now backs off exponentially (`RATE_LIMIT_ATTEMPTS`) before
  falling through to the next provider.
- **Token expiry (~hourly):** the client re-reads `.env` and retries once on 401.
  `tests/test_batch_resilience.py` proves this works **mid-batch**, including two expiries
  inside one 20-ticket run, and that a genuinely dead token degrades to the next provider
  instead of killing the batch.
