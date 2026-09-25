# Triage Assistant backend

FastAPI service that learns from resolved tickets and triages new problems before they become tickets.

```
user text + screenshots
  └─ vision LLM describes each image
  └─ embed → search knowledge (training history · service catalog · live resolutions) + open tickets
  └─ LLM decides: self-service answer? work type, service, urgency, impact, ticket draft
  └─ code: team lookup, assignee = resolver of most similar fixes, priority = urgency × impact matrix
agent resolves ticket (can correct routing)  →  embedded as `live` knowledge  →  next user finds it
user confirms "that solved it"               →  cited knowledge gets a helpful vote (ranks higher)
```

## Setup

Easiest: `aspire run` from the repo root (starts backend + frontend). Standalone:

```bash
cp .env.example .env        # paste the shared Foundry API key into AZURE_FOUNDRY_API_KEY
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

On first start the knowledge base is built from `../jira_first_20000_requested_fields_synthetic.json` into
`data/knowledge.db`: the history is curated first (see below), then gold clusters + 19 service catalog cards are embedded.

## Data curation (`app/curation.py`)

Every ticket gets a 0–100 quality score — resolution evidence 50 · closed 15 · real service 15 · clear input 10 ·
triage trail 10, minus 5 when the label contradicts a documented fix — plus findings that explain the deductions.
Tickets are clustered per service on a resolution-weighted embedding; each cluster is scored
(0.9 × mean ticket score + coherence bonus) and levelled:

| Level | Score | Meaning |
|---|---|---|
| gold | ≥ 80 | root cause documented — teaches routing and the fix |
| silver | ≥ 60 | closed with a short outcome — good for routing |
| bronze | ≥ 40 | closed without detail |
| reject | < 40 | open, generic intake bucket, or no usable signal — never published |

Run it from the command line (stores results in the DB; optional publish and flat-file export):

```bash
uv run python -m app.curate                              # analyse + store + print report
uv run python -m app.curate --publish silver             # also feed silver+ clusters to knowledge
uv run python -m app.curate --export out/curation        # summary.json, clusters.json, tickets.csv (one row per ticket)
uv run python -m app.curate --threshold 0.9 --db /tmp/x.db
```

Or browse it in the **Data curation** tab, pick the lowest level to learn, and publish (one knowledge item per cluster).
Changing the embedding deployment triggers an automatic re-embed on next start.

### LLM providers

Every provider whose credentials are in `.env` is enabled and offered in the **Get help** model picker (`GET /api/llms`):

| Provider | Enabled by | Chat | Vision | Embeddings |
| --- | --- | --- | --- | --- |
| `foundry` | `AZURE_FOUNDRY_ENDPOINT` (+ key or Entra ID) | `CHAT_DEPLOYMENT` | `VISION_DEPLOYMENT` | `EMBEDDING_DEPLOYMENT` |
| `openai` | `OPENAI_API_KEY` | `OPENAI_CHAT_MODEL` | `OPENAI_VISION_MODEL` | `OPENAI_EMBEDDING_MODEL` (if no Foundry) |
| `apertus` | `APERTUS_API_KEY` | `APERTUS_MODEL` | via Foundry/OpenAI | — |

Embeddings come from one model for all providers (Foundry, else OpenAI, else offline), so switching the chat model
never invalidates the knowledge base.
Rate limits: on HTTP 429 every provider backs off and retries (`LLM_RATE_LIMIT_RETRIES`, default 6; 2s doubling to
60s, or the server's `Retry-After`), and Apertus is capped at `APERTUS_MAX_CONCURRENCY` (default 2) calls in flight
across the whole app, so parallel eval runs queue instead of tripping its quota. `LLM_MODE` picks the default provider; `--llm` does the same for `app.evaluate`.
With nothing configured (or `LLM_MODE=mock`) everything runs offline with keyword embeddings and heuristic triage.

```bash
uv run pytest                         # end-to-end learning loop, mock mode
uv run python -m app.knowledge --level gold   # re-curate history and publish ≥ level
```

## Blind eval (`app/evaluate.py`)

Runs the same triage pipeline over the challenge file and fills in the 7 answer fields from the root README:
work type, service, team, assignee, urgency/impact → priority (matrix), resolution status and a resolution comment
(appended to `All Comments` as `<assignee>: Resolution: ...`, like the training data). Pre-filled service/priority
values in the challenge are treated as unverified hints.

```bash
uv run python -m app.evaluate                          # picks up jira_hackathon_blind_eval_challenge_*.json from the repo root
uv run python -m app.evaluate --input ../x.json --limit 3 --workers 1
uv run python -m app.evaluate --llm apertus            # compare chat providers
uv run python -m app.evaluate --top-k 8 --min-score 0.4   # retrieval settings (min-score 0 = keep every match)
uv run python -m app.evaluate --assignee precedent        # previous assignee policy (resolver of similar fixes)
LLM_MODE=mock uv run python -m app.evaluate --db /tmp/eval.db   # offline smoke run
```

Writes to `out/eval/`: `<runId>.results.json` (challenge format — the submission), `<runId>.trace.json`
(rationale, knowledge matches, fields changed vs input) and `<runId>.report.md` (summary table + consistency checks:
priority matches the matrix, team matches the catalog, assignee present).

**Assignee** (`app/assign.py`, the policy of `Main2/triagemate/assign.py`): the training `Assignee` is independent of the
ticket (all 30 agents appear under every service, ~1/30 each), so it is not predicted. The batch is load-balanced over
the agent pool instead — fewest assignments in this run, then smallest open/in-progress backlog in the history, then most
resolved tickets on the service, then a stable hash of the ticket text — so every ticket gets an agent, repeated runs
give the same answer, and the resolution comment is written in that agent's voice. `--assignee precedent` (or
`"assignee": "precedent"` in an Evaluation-tab config) restores the previous policy: the author of the most similar
documented fixes, which exists for only 10 services and leaves the rest in the team queue. The assistant flow
(`/api/assist`) keeps the precedent resolver, so a newly resolved problem is still routed to the agent who solved it.

### From the UI (Evaluation tab)

The **Evaluation** tab runs the same engine (`evaluate()`) from the browser: add one or more configurations
(model, top K knowledge items, minimum RAG similarity), start them together and watch every ticket land live over
server-sent events. Selected runs are compared side by side — per-field agreement with a baseline run, priority
distribution, re-routing and consistency issues, and a per-ticket grid that highlights disagreements and expands to
the resolution notes, rationale and knowledge used. Each run's `results.json` (submission format) can be downloaded.
Runs are stored in `data/evals/` next to the knowledge base.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/assist` | `{text, images: [dataURL]}` → understanding, self-service answer, triaged ticket draft, matches, duplicates |
| POST | `/api/assist/{id}/feedback` | `{helpful}` — deflection confirmed → reinforce cited knowledge |
| POST | `/api/tickets` | create ticket from an assist session |
| GET | `/api/tickets` | agent queue |
| POST | `/api/tickets/{id}/draft-resolution` | LLM drafts the resolution note from similar precedents |
| POST | `/api/tickets/{id}/resolve` | close; `done` resolutions are learned as knowledge |
| GET | `/api/curation` | run summary, all clusters, published level |
| GET | `/api/curation/clusters/{id}` | cluster detail + highest-scoring sample tickets |
| POST | `/api/curation/run` | `{threshold?}` re-analyse the history (re-publishes at the current level) |
| POST | `/api/curation/publish` | `{min_level: gold\|silver\|bronze}` replace history knowledge with clusters ≥ level |
| GET | `/api/eval/options` | challenge files, defaults, challenge tickets as reported |
| POST | `/api/eval/runs` | `{configs: [{llm, top_k, min_score, assignee, label}], limit?, workers?, challenge?}` → one run per config |
| GET | `/api/eval/runs`, `/api/eval/runs/{id}` | run summaries / one run with per-ticket results |
| GET | `/api/eval/stream` | SSE: `snapshot`, then `run` (progress), `ticket` (`{runId, index, ticket}`), `deleted` |
| POST / DELETE | `/api/eval/runs/{id}/cancel`, `/api/eval/runs/{id}` | stop / delete a run |
| GET | `/api/eval/runs/{id}/results.json` | download in the challenge submission format |
| GET | `/api/stats`, `/api/health`, `/api/catalog` | |
