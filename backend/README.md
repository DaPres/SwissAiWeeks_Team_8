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

Without an endpoint (or with `LLM_MODE=mock`) everything runs offline with keyword embeddings and heuristic triage.

```bash
uv run pytest                         # end-to-end learning loop, mock mode
uv run python -m app.knowledge --level gold   # re-curate history and publish ≥ level
```

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
| GET | `/api/stats`, `/api/health`, `/api/catalog` | |
