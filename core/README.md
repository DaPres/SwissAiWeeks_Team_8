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
historical assignment is random. We route the **team** exactly, and suggest an assignee by
polling the most similar historical pattern (modal assignee, ties by name), which samples
the same distribution the reference answers were drawn from. Measured over 200 held-out
tickets (`uv run python scripts/eval_assignee.py`):

| Method | Hit rate |
|---|---:|
| uniform random (1/30) | 3.3% |
| modal per service | 4.0% |
| modal per service + work type | 5.0% |
| **similar-pattern modal (ours)** | **5.0%** |
| similar-ticket single exemplar | 1.5% |

No approach beats ~5%, because there is nothing to learn. (The single-exemplar variant is
*worse* than random: one exemplar concentrates on one person, while polling the pattern
spreads across the real distribution.) We say this plainly rather than implying skill, and
the UI labels the assignee a suggestion. A rota or skill-based rule from Swiss Life would
replace one function.

## The deterministic spine

The stages that must never be wrong are code, not model output.

**Safety gate (`app/safety.py`).** Redacts emails, IBANs, phone numbers, card numbers and
person names (derived from the ticket's own reporter/assignee) before any text reaches a
provider — the model layer only ever sees redacted text. Injection is detected on the
*original* text, so redaction cannot mask an attack, and each of the 8 rules reports *why*
it fired. Measured on all 20,000 real tickets: **0 false-positive injection flags**.

**Priority (`app/priority.py`).** The LLM extracts urgency and impact with a quoted sentence
each; the 5×5 matrix in code turns them into a priority. Two vocabularies meet here — the
organisers' matrix labels (`Critical…Lowest` × `Major…None`) and the dataset's lowercase
`lowest…highest` — and `URGENCY_LABEL`/`IMPACT_LABEL` are the single place they are mapped.
`tests/test_priority.py` re-transcribes the organisers' grid independently and walks **all
25 cells**, so a typo in either table fails the build.

*Overrides are ours, not Swiss Life's.* One rule only, grounded in the organisers'
critical-service list: **a Critical service in full outage cannot be below `Significant`
impact.** It lives in a single labelled table (`OUR_OVERRIDES`), never lowers an impact,
and every applied override is marked `ours=True` so the UI can show it as our heuristic.
(The market-hours and regulatory-deadline rules were considered and **dropped** — they were
not in any organiser document.)

**Quality gate and classifier (`app/quality.py`, `app/classify.py`).** Deterministic cues
catch the dataset's trap templates; the description always outranks the summary; the model's
service answer is snapped back to the catalogue, and with every provider down the fallback
still finds the service in the text.

Measured over all 20,000 tickets (`uv run python scripts/eval_spine.py`):

| Class | N | unclear | mismatch | injection FP |
|---|---:|---:|---:|---:|
| automated alert | 7,385 | 0.0% | 0.0% | 0 |
| external email | 5,423 | 0.0% | 0.0% | 0 |
| **trap** | 3,718 | **51.0%** | **49.0%** | 0 |
| normal | 3,474 | 0.0% | 0.0% | 0 |

The gates flag **3,718 tickets = 18.6%**, which is exactly the trap population, with **zero
false positives** on the other 16,282. Every trap is caught by one gate or the other.
(The fallback classifier's 100% service accuracy in that script is *not* a skill claim — the
training text names its own service. The honest test is the challenge set, where it is wrong
on purpose.)

## Retrieval

There is no knowledge base in this challenge — the corpus is past tickets and their
comments — so a **citation is a ticket id**. Two measured properties shape the design:

- **20,000 tickets are 173 texts.** Nearest-neighbour would return five copies of one
  sentence, so tickets are grouped into **patterns** by template signature (service, entity
  and numbers masked) and results are deduped by signature: *k* results are *k* genuinely
  different resolution patterns.
- **Resolution quality varies wildly.** "Problem fixed." appears **5,851 times**, there are
  only **79 unique comment strings**, and **20.6% of tickets are filler-only**. Each pattern
  therefore exposes its best-documented resolved member as the citation target, so we never
  ground an answer in filler.

Scoring is hybrid — **0.6 dense cosine (Chroma + sentence-transformers) + 0.4 BM25** — taking
the top 20, filtering by service, deduping, down to the top 5. Below a **0.35 score floor**
retrieval reports low confidence instead of returning a bad match.

## The agent loop, resolution and drafting

**Bounded loop (`app/agent/loop.py`).** At most **5 tool calls** over five read-only tools —
`search_kb`, `find_similar_tickets`, `find_open_related`, `request_clarification`,
`escalate_to_human`. Tool arguments are validated and clamped before any database access;
the last two are terminal signals that end the loop. Every step is traced with its own
latency, and the trace is shown in the UI.

**Resolution status (`app/resolution.py`) is derived from our own flags, never learned.**
Resolution in the training data is random — measured at 25.5 / 25.0 / 24.9 / 24.6% across
*every* template, with `Status: done` carrying all four values — so imitating it is
impossible by construction. Our rules, in priority order:

| Condition | Status |
|---|---|
| injection detected | `cancelled` |
| duplicate of an open ticket on the same service | `cancelled` |
| spam / not a service request | `cancelled` |
| unclear or missing information | `clarification` |
| alert with no corroborating evidence, nothing reproducible | `cannot reproduce` |
| confidence below 0.6 | `clarification` (ask rather than guess) |
| actionable, with a matching resolution pattern | `done` |
| actionable but no matching procedure found | `clarification` |

**Drafting (`app/draft.py`)** runs at temperature 0.3 — everything else is 0. Every factual
sentence carries a **citation id**, and citations are kept in a structured field as well as
inline, so the UI can show provenance and the submission can strip them. A `clarification`
is never a thin note: it must state exactly what is missing and why it blocks resolution.
If retrieval supports nothing, the comment says so rather than inventing a fix.

**Confidence** = `0.4 × classifier + 0.4 × retrieval + 0.2 × self-report`. If any stage fell
back to deterministic output, confidence is **capped at 0.5** — below the floor — because a
result we did not get a model judgement for must never look confident.

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
