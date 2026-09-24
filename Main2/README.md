# TriageMate - AI triage co-pilot for operational service desks

**Swiss {ai} Weeks - Zurich Hackathon 2026 - Swiss Life challenge "AI Support Agent for Operational Service Desks"**

TriageMate ingests a Jira ticket (or a pasted e-mail), makes the text safe, decides what it really is and which system it concerns,
routes it through the service catalogue, computes the priority from evidence with the ITIL matrix, researches the knowledge base and
similar/related tickets with a bounded agent, drafts a cited reply and a concrete resolution note, and hands everything to a human
who approves, edits or rejects. Every decision is logged, and accepted edits feed back into future drafts.

> **In one sentence for the jury:** the training data is a decoy (only 173 unique texts; priority, assignee and outcomes are random noise),
> so we built what the data cannot fake - consistent, explainable behaviour on hard cases - and we report the awkward numbers too.

## Quick start (fresh clone, no key needed)

```bash
pip install -r requirements.txt
python -m triagemate.cli analyze          # reproduces every data finding quoted below     -> eval/dataset_analysis.json
python -m triagemate.cli run-challenge    # triage the challenge file                        -> outputs/challenge_predictions.{json,csv}
python -m triagemate.cli eval --offline   # stress + post-freeze validation + holdout        -> eval/results_offline.json
python -m triagemate.cli serve --port 8765   # analyst UI + REST API                        -> http://127.0.0.1:8765
python -m pytest tests -q                 # 100+ tests, no network
```

Windows: run the same commands in PowerShell (no `make` needed). Linux/macOS: `make check` runs the whole gate.

### Adding an LLM (optional - everything has a deterministic fallback)

Copy `.env.example` to `.env` and paste keys next to the provider names; `LLM_PROVIDER` picks the default. You can keep all keys at once
and use different providers per role (`CLASSIFY_PROVIDER=openai`, `DRAFT_PROVIDER=apertus`).

| Provider | Variables |
|---|---|
| OpenAI | `OPENAI_API_KEY` (model `gpt-4.1-mini`) - also supplies multilingual embeddings |
| Swisscom **Apertus** (Swiss AI Platform) | `APERTUS_API_KEY` (base URL and model `swiss-ai/Apertus-v1.5-70B` preset; 5 req/s throttle built in) |
| Azure OpenAI | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` |
| Claude | `ANTHROPIC_API_KEY` (`pip install anthropic`; official SDK) |
| Local (Ollama / LM Studio) | `LOCAL_BASE_URL`, `LOCAL_MODEL` |

`python -m triagemate.cli smoke` checks chat, JSON output, tool calling, embeddings and one full ticket against the configured keys (keys are never printed).
`TRIAGE_OFFLINE=1` forces the rules engine. The privacy invariant is tested: **no unmasked text ever reaches a model** (see Safety).

## What the data really tests (all reproducible with `analyze`)

| Finding | Number | Consequence |
|---|---|---|
| Unique ticket texts | 173 of 20,000 (11 templates x services) | accuracy on the file is leakage; TF-IDF + logistic regression scores **100%** on service and work type |
| Priority vs urgency/impact | consistent with the README matrix only **39%** (chance); 104 of 173 texts carry all five priorities | priority is *computed from evidence*, never learned |
| Assignee vs service, team, entity, work type, resolution, priority | Cramer's V ~ 0.04, chi-square ~ degrees of freedom (independent) | no model can predict the historical assignee; we use a load-balancing policy and say so |
| Service -> team | strictly 1:1, asserted against all 20,000 tickets | routing is a lookup |
| Resolution outcome shares | ~25% each, independent of content | resolution *status* is a policy; never quoted as a business fact |
| **Hidden signal** | 21 human-written `Resolution: ...` notes across 10 services among 79 unique comment bodies | mined automatically; they drive the resolution note and act as evidence for the service |

Two more traps handled explicitly: `Emailed Support Tickets` is a **channel**, not a system (never chosen as the affected service; unknown -> Service Desk + clarification),
and raw ticket text contains personal data (masked before any model call).

## How each README requirement is met

| README task field | How | Where |
|---|---|---|
| Work type (title may lie) | description-primary scoring: explicit "the title sounds like an outage but..." statements, incident/request cues, intake prior; LLM arbitrated | `classify.py`, `llm_tasks.py` |
| Affected service (do not trust the selected one) | ontology of the 20 services (EN/DE/FR) + contrast suppression + resolution-playbook votes + LLM with advisory ranking; selected service is only a small prior | `catalogue.py`, `classify.py` |
| Service team | strict catalogue lookup | `catalogue.py` |
| Assignee | policy over the real 30-agent pool: spread a batch, lowest backlog, familiarity, stable hash (statistically the historical assignee is unpredictable) | `assign.py` |
| Priority consistent with the matrix | urgency/impact from evidence, **matrix computed in code**; 25 cells tested against the README table; never freehand | `priority.py` |
| Resolution status | policy over signals (`done`, `clarification` for unclear/injection, `cancelled` for duplicates, `cannot reproduce` for transient) | `resolutions.py` |
| Resolution comment (specific, in the agent's voice, reuse similar history) | best-matching mined human note adapted with ticket identifiers, or an LLM rewrite grounded in playbook + KB; written as `agent@intcom.com: Resolution: ...` and appended to `All Comments` | `resolutions.py`, `retrieve.py`, `challenge.py` |
| No hardcoded answers | the runner has no notion of ticket identity; `test_runner_is_ticket_agnostic_no_hardcoded_answers` triages a fresh synthetic ticket; lexicon contains generic domain terms only | `tests/` |

The challenge file in the repo is `jira_hackathon_blind_eval_challenge_*.json` (Jira-export envelope), not the README's `jira_hackathon_20_new_tickets_challenge.json`;
the loader accepts either name, an envelope, a bare list or JSONL, and the output keeps the input schema.

## Results

<!-- RESULTS:START -->
### With an LLM (hybrid mode: rules + model, arbitrated)

Mode: **hybrid** - stress set n=106, priority consistency over 2 runs.

| Metric | Holdout (text-only) | Stress set | Baseline |
|---|---|---|---|
| Service / team routing accuracy | 1.000 (leakage) | 1.000 | TF-IDF+LogReg 1.000 (leakage) |
| Work type, misleading subset | - | 1.000 | title keywords 0.960 |
| Work type, overall | 0.994 | 1.000 | majority 0.803 |
| Priority consistency (2 runs) | - | 0.991 | trained classifier 0.493 = majority 0.497 |
| Priority == matrix(urgency, impact) | - | 1.000 | training labels 0.390 (chance) |
| Clarification recall / F1 / F2 | - | 1.000 / 1.000 / 1.000 | - |
| Injection resistance (FPR) | - | 1.000 (0.000) | - |
| PII redaction recall | - | 1.000 | - |
| Citation coverage (EN replies) | - | 1.0 | target >= 0.9 |
| Duplicate linking P / R | - | 1.000 / 1.000 | - |
| Latency p50 / p95 (ms/ticket) | - | 7199.1 / 10912.3 | target p95 < 6000 |
| Cost per ticket (USD) | - | 0.002454 | - |

#### Post-freeze validation set (n=37, written after the rules were frozen; hybrid numbers are post prompt-fix, see first-run files)

| Metric | Value |
|---|---|
| Service / team routing accuracy | 1.000 / 1.000 |
| Work type accuracy (all / misleading-title subset) | 1.000 / 1.000 |
| Clarification recall / precision | 1.000 / 1.000 |
| Injection resistance (false-positive rate) | 1.000 (0.000) |
| Priority sanity / matrix-consistent | 0.909 / 1.000 |

#### Per category (stress set)

| Category | n | team acc | service acc | work-type acc |
|---|---|---|---|---|
| paraphrase | 20 | 1.000 | 1.000 | 1.000 |
| german | 20 | 1.000 | 1.000 | 1.000 |
| french | 12 | 1.000 | 1.000 | 1.000 |
| service_omitted | 8 | 1.000 | 1.000 | 1.000 |
| misleading_title | 10 | 1.000 | 1.000 | 1.000 |
| pii | 10 | 1.000 | 1.000 | 1.000 |
| injection | 8 | 1.000 | 1.000 | 1.000 |
| benign | 6 | 1.000 | 1.000 | 1.000 |
| alert_storm | 8 | 1.000 | 1.000 | 1.000 |
| unclear | 4 | 1.000 | 1.000 | 1.000 |

#### Honesty notes

- The holdout number is meaningless as a generalisation estimate: 100% of test texts also occur in the training data (only 173 unique texts).
- The stress set and the domain ontology share an author; expect an independent annotator to score lower.
- Assignee, resolution outcome and resolution time in the training data are statistically independent of everything else, so they are not evaluated as predictions.
- `Confidence` is a heuristic composite, not a calibrated probability.

### Offline (deterministic rules only, no key needed)

Mode: **offline** - stress set n=106, priority consistency over 5 runs.

| Metric | Holdout (text-only) | Stress set | Baseline |
|---|---|---|---|
| Service / team routing accuracy | 1.000 (leakage) | 1.000 | TF-IDF+LogReg 1.000 (leakage) |
| Work type, misleading subset | - | 1.000 | title keywords 0.960 |
| Work type, overall | 0.994 | 1.000 | majority 0.803 |
| Priority consistency (5 runs) | - | 1.000 | trained classifier 0.493 = majority 0.497 |
| Priority == matrix(urgency, impact) | - | 1.000 | training labels 0.390 (chance) |
| Clarification recall / F1 / F2 | - | 1.000 / 0.923 / 0.968 | - |
| Injection resistance (FPR) | - | 1.000 (0.000) | - |
| PII redaction recall | - | 1.000 | - |
| Citation coverage (EN replies) | - | 1.0 | target >= 0.9 |
| Duplicate linking P / R | - | 1.000 / 1.000 | - |
| Latency p50 / p95 (ms/ticket) | - | 47.1 / 67.9 | target p95 < 6000 |
| Cost per ticket (USD) | - | 0.0 | - |

#### Post-freeze validation set (n=37, written after the rules were frozen; hybrid numbers are post prompt-fix, see first-run files)

| Metric | Value |
|---|---|
| Service / team routing accuracy | 0.946 / 0.946 |
| Work type accuracy (all / misleading-title subset) | 0.946 / 0.750 |
| Clarification recall / precision | 1.000 / 1.000 |
| Injection resistance (false-positive rate) | 1.000 (0.000) |
| Priority sanity / matrix-consistent | 0.758 / 1.000 |

#### Per category (stress set)

| Category | n | team acc | service acc | work-type acc |
|---|---|---|---|---|
| paraphrase | 20 | 1.000 | 1.000 | 1.000 |
| german | 20 | 1.000 | 1.000 | 1.000 |
| french | 12 | 1.000 | 1.000 | 1.000 |
| service_omitted | 8 | 1.000 | 1.000 | 1.000 |
| misleading_title | 10 | 1.000 | 1.000 | 1.000 |
| pii | 10 | 1.000 | 1.000 | 1.000 |
| injection | 8 | 1.000 | 1.000 | 1.000 |
| benign | 6 | 1.000 | 1.000 | 1.000 |
| alert_storm | 8 | 1.000 | 1.000 | 1.000 |
| unclear | 4 | 1.000 | 1.000 | 1.000 |

#### Honesty notes

- The holdout number is meaningless as a generalisation estimate: 100% of test texts also occur in the training data (only 173 unique texts).
- The stress set and the domain ontology share an author; expect an independent annotator to score lower.
- Assignee, resolution outcome and resolution time in the training data are statistically independent of everything else, so they are not evaluated as predictions.
- `Confidence` is a heuristic composite, not a calibrated probability.

<!-- RESULTS:END -->

### Reading these numbers honestly

* **Holdout** is reported only because the plan asks for it: every test text is also in the training data (leakage).
* The **stress set** (106 tickets) and the ontology share an author and were used while developing - treat it as a regression suite, not an unbiased estimate.
* The **post-freeze validation set** (37 tickets, new phrasing, Italian, misleading titles) was written after the rules were frozen and run **once** before any change.
  First-run results are stored in `eval/validation_first_run_offline.json` (routing **0.946**) and `eval/validation_first_run_hybrid.json` (routing **0.892**, work type 1.000).
  The hybrid first run exposed a *prompt* gap: the LLM filed "give X access to <service>" requests under Identity & Access Management, whereas the training data files all 1,984
  access/removal/licence tickets under the service named in the title. Classification prompt v1.1 now states that convention. Because the validation set informed that fix,
  the hybrid validation numbers in the table below are **post-fix and no longer untouched**; the first-run numbers above are the ones to quote for generalisation. It is still single-author.
* `Confidence` is a heuristic composite (classifier, retrieval score, source agreement) - **not** a calibrated probability.
* Assignee accuracy is not measured: in the data it is independent of everything.

## Intake API - enrich an incident, and help while the user types

Built for a separate front-end (full contract and examples in [`docs/INTAKE_HANDOFF.md`](docs/INTAKE_HANDOFF.md), JSON Schemas in `docs/intake_schema.json`).

```python
from triagemate.intake import enrich_incident, assist
e = enrich_incident("Hi, my order is stuck in pending approval")   # only `description` is required; other Jira fields are used as hints
e.to_json()          # service, team, assignee, urgency/impact/priority, flags, optional clientResolution / expertResolution, draft reply ...
assist("Hi i am facing a transaction")                              # typing assist, ~5 ms, offline
```

* `POST /api/intake/enrich` (+ `/batch`) - fully enriched incident. `clientResolution` = what the requester can try or prepare right now (only when it is safe: never during an outage of a critical service);
  `expertResolution` = resolution note, ready-to-paste Jira comment, next steps and similar past tickets for the assigned team.
* `POST /api/intake/assist` and `WS /ws/intake/assist` - while the user types: likely issue statements, word completion, follow-up questions, and *sometimes* a cited quick fix.
  `mode: "smart"` adds LLM-written suggestions on masked text with a 1.6 s budget and silent fallback.
* Reference page: `/static/intake_demo.html`. CLI: `python -m triagemate.cli intake --text "..."`, `assist --text "..."`.

## Safety (Sec. 4.10 of the plan, all tested)

1. **Separation** - ticket text only inside delimited data blocks; role-tag lookalikes are neutralised.
2. **Detection** - precision-first injection patterns (EN/DE/FR, hidden HTML comments, zero-width characters); 0 false positives on the benign look-alike tickets.
3. **Least privilege** - agent tools are read-only; tools *recommend*, deterministic gates *decide*.
4. **Redaction** - e-mails, phones, IBANs, policy numbers and person names become tokens before any model call; restored only in the analyst-facing draft, never in resolution notes.

An injected ticket triggers escalation **before** any model runs: zero bytes of the attack text are sent to a provider (tested).

## Cost and latency (measured, not estimated)

Every model call is timed, token-counted and priced; the UI dashboard and `results_*.json` report p50/p95 latency and mean cost per ticket.
With `gpt-4.1-mini` a full ticket costs about **0.25 US cents** and takes p50 ~7 s / p95 ~11 s end to end from a laptop (independent calls run in parallel; a batch runs 4 tickets at once);
the offline engine takes well under 0.1 s. `AGENT_MODE=policy` skips the LLM tool loop for a faster path.

## Jury criteria -> where to look

| Criterion | Evidence |
|---|---|
| Technical functionality and AI | hybrid rules + LLM with arbitration, typed outputs, hybrid retrieval, mined playbook, 100+ tests, live-verified providers (OpenAI, Swisscom Apertus) |
| User experience | `ui/index.html`: priority queue with badges, redaction toggle, reasons on one screen, live ITIL matrix, cited draft, agent trace, one-click approve/edit/reject, paste-an-email demo box, dashboard |
| Agentic depth | bounded 5-call tool loop, LLM-chosen tools with deterministic guardrails and a policy fallback; full trace shown in the UI |
| Uniqueness and creativity | data forensics (leakage, independence tests), playbook mining, contrast suppression, examples-not-schemas JSON prompting, feedback loop |
| Potential and market impact | regulated-insurer design: masking, human approval, audit log; integrates behind Jira Service Management via the REST API; pilot plan below |

## Pre-built scaffolding disclosure (organiser rule)

The architecture, prompts and evaluation plan follow a pre-event planning document (`plan.pdf`, "TriageMate field textbook"). All code in this repository was written during the event
(24-25 Sep 2026) with Claude Code. The knowledge base (`kb/`, 26 short articles) is **synthetic** - no real Swiss Life documentation was provided - and every article is marked `synthetic: true`.
The stress and validation sets are hand-written for this event. No generic boilerplate or third-party template was reused beyond standard libraries (FastAPI, scikit-learn, pydantic, httpx).

## Limitations and next steps

* KB and ontology are synthetic / author-written; a real pilot ingests the real KB and calibrates the impact rules with Swiss Life's own priority policy (question list in `docs/PITCH.md`).
* Urgency/impact are judgement calls; the rules and the LLM disagree on about half of the challenge tickets (routing agrees on all 20). Priority is always matrix-consistent, but expert agreement is unmeasured.
* Offline German/French coverage relies on a hand-written ontology. The LLM improved work-type accuracy (validation 1.000 vs 0.946) and priority sanity (0.909 vs 0.758) but, before the prompt fix above, was *worse* at routing (0.892 vs 0.946) - hence the arbitration between rules and model instead of trusting either alone.
* Confidence is uncalibrated; calibration needs analyst judgements collected by the feedback loop.
* Not built: fine-tuning (would memorise 173 templates), cross-encoder reranking (unnecessary with ~26 articles), real Jira write-back (read-only demo by design).

## Repo map

```
triagemate/   safety, catalogue, classify, priority, retrieve, agent, draft, resolutions, assign, llm(+anthropic), llm_tasks, pipeline, intake, assist, store, api, cli, analyze, challenge
prompts/      versioned prompt files (recorded with every result)
kb/           26 synthetic knowledge-base articles          scripts/  generate_kb, smoke_llm, update_readme_results
eval/         stress_set, validation_set, run_eval, results_*.json, dataset_analysis.json
ui/           analyst UI + intake_demo.html (typing assist) docs/     ARCHITECTURE.md, PITCH.md, INTAKE_HANDOFF.md, intake_schema.json
tests/        catalogue, matrix, safety, classifier, retrieval, LLM plumbing, privacy invariant, API, challenge runner, intake + typing assist, repo hygiene
data/         the organiser's files + 5 demo tickets
```
