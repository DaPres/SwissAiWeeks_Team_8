# TriageMate

A **triage co-pilot** for Swiss Life's operational service desks, built for the **Swiss {ai} Weeks Zurich Hackathon** (24–25 Sep 2026).

Not a chatbot. Measured on the challenge dataset, only **17%** of the ticket queue is a normal
ticket wanting a written answer: **37%** is automated alerts, **27%** external emails and
**19%** deliberate traps. The value is in filtering, routing and prioritising — not in prose.
See [docs/dataset_findings.md](docs/dataset_findings.md) for the evidence and
[CLAUDE.md](CLAUDE.md) for the architecture and working rules.

> **Provenance:** commit `1c0140a` is the last pre-event scaffold (generic boilerplate —
> model layer, RAG skeleton, FastAPI, Streamlit, tests). Everything after it was built during
> the hackathon. The organisers confirmed disclosed pre-built boilerplate is fine.

## Model layer

Every component reaches a provider through `app/agent/llm_client.py` and nothing else, with automatic fallback:

1. **Swisscom Apertus** (`swiss-ai/Apertus-v1.5-70B`): primary. If the ~60-min bearer token expires, the client re-reads `.env` and retries once on HTTP 401.
2. **OpenAI** (`gpt-4o-mini`)
3. **Public AI via the Hugging Face router** (`:publicai` model suffix)
4. **Local Ollama** (`llama3.2:3b`): catches any cloud failure by default, so a stage demo degrades to a slow local answer instead of an error (`OLLAMA_FALLBACK_MODE=offline_only` restricts it to offline runs)

## The result contract

Every stage codes against `app/schemas.py`. `TriageResult` carries the **7 graded fields**
(`GradedFields`: work type, service, team, assignee, priority, resolution, resolution comment)
kept deliberately separate from our internals (flags, citations, confidence, trace), so
`result.submission()` emits exactly the challenge's required output and nothing else.

```
app/agent   LLM client + fallback logic
app/rag     Chroma + sentence-transformers ingest/retrieve
app/api     FastAPI  POST /chat
app/ui      Streamlit demo chat
data/sample_docs   placeholder FAQ docs
tests       offline unit tests
```

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env        # then paste your keys into .env
uv run python test_providers.py
uv run python -m app.rag.ingest
```

## Run the demo (two terminals)

```bash
uv run uvicorn app.api.main:app --reload --port 8000
uv run streamlit run app/ui/streamlit_app.py
```

To call the API directly:

```bash
curl -X POST localhost:8000/chat -H "Content-Type: application/json" -d '{"message":"How do I reset my password?"}'
```

The response includes `answer`, `provider` (which LLM served it), `sources`, and `failed_providers`.

## Tests

```bash
uv run pytest
```

## Routing and assignee

`data/catalogue.yaml` is **generated** from the training data by
`uv run python scripts/build_catalogue.py`, which refuses to write a lookup table if
service→team is not 1:1. Service→team and criticality are therefore never model decisions:
the mapping is verified (20 services, 11 teams, 0 exceptions) and the Critical/Non-Critical
ratings come verbatim from the organisers' list. An unrecognised service routes to
**Service Desk** rather than being guessed.

**Assignee is unlearnable from this data** — all 30 assignees appear under all 11 teams, so
historical assignment is random. Copying it would reproduce noise. Instead we route to the
correct team, then suggest the **least-loaded** member of that team (fewest open or
in-progress tickets), breaking ties alphabetically so the result is reproducible. This is
**our operational heuristic, not a Swiss Life rule**, and the UI labels it as a suggestion.
If Swiss Life route by skill or rota, this is a one-function change.

## Storage and the related-ticket window

`app/store.py` keeps tickets, triage results, analyst decisions and eval runs in SQLite
(`data/triagemate.db`, git-ignored). Agent tools only ever read from it.

`RELATED_WINDOW_HOURS` (default **4**) defines duplicate/alert correlation: same service,
not done, created within ±4 h. **This is our parameter, not an organiser rule**, and the
default is chosen from the data: the median gap between consecutive alerts on the same
service is **10.20 h**, only **6.2%** land within 1 h, a 4 h window catches **24.1%**, and
24 h would sweep in **79.9%** — genuine bursts without over-merging. To be swept on the
stress set (1 h / 4 h / 24 h) once it exists.

## Dataset analysis

```bash
uv run python analyze_data.py
```

Verifies the claims TriageMate is built on: template counts, service→team cardinality,
whether priority is learnable, and a leakage check. Findings in
[docs/dataset_findings.md](docs/dataset_findings.md); the challenge brief is mirrored at
[docs/challenge.md](docs/challenge.md). `data/jira.json` (23.8 MB) is git-ignored — download it with:

```bash
curl -sL -o data/jira.json https://raw.githubusercontent.com/Swiss-ai-Weeks/SwissLife-2026/main/jira_first_20000_requested_fields_synthetic.json
```

## License

MIT
