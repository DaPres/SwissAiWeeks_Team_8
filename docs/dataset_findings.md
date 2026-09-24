# Dataset findings — verified, not assumed

Source: `data/jira.json` (20,000 synthetic tickets, Swiss-ai-Weeks/SwissLife-2026).
Reproduce with `uv run python analyze_data.py`. Challenge README saved at [docs/challenge.md](challenge.md).
Verified 2026-09-24.

**Verdict: every claim in the pivot brief holds. The ticket-mix numbers are confirmed to the percentage point.**

## 1. Text variety — the data is 11 templates, not 20,000 tickets

| Metric | Value |
|---|---|
| Records | 20,000 |
| Unique `Summary` | **173** (0.86%) |
| Unique `Description` | **173** (0.86%) |
| Unique (Summary + Description) pairs | 173 |
| Description templates after masking service/entity/numbers | **11** |

The 173 unique texts are 11 templates × ~20 services. Every ticket is boilerplate with a
service name slotted in. **Implication: nothing here is a realistic writing sample, and any
"semantic" retrieval over it is retrieving the same sentence back.**

| Count | Share | Class | Template (truncated) |
|---:|---:|---|---|
| 7,385 | 36.93% | automated alert | `<SERVICE> generated an automated monitoring alert…` |
| 4,212 | 21.06% | external email | `A third party sent a warning regarding <SERVICE>…` |
| 1,490 | 7.45% | normal | `A user reported an operational disruption in <SERVICE>…` |
| 1,485 | 7.42% | **trap** | `The incident note for <SERVICE> is not aligned with the expected service context…` |
| 1,428 | 7.14% | **trap** | `…raised against <SERVICE>, but the title suggests a service request instead…` |
| 1,211 | 6.05% | external email | `An external party sent an email warning related to <SERVICE>…` |
| 814 | 4.07% | normal | `A new user requires a license for <SERVICE>…` |
| 757 | 3.79% | normal | `A user needs access to <SERVICE>…` |
| 413 | 2.07% | normal | `The request is to remove access to <SERVICE>…` |
| 412 | 2.06% | **trap** | `The ticket text for <SERVICE> is unclear and not aligned…` |
| 393 | 1.97% | **trap** | `The submitted title suggests an incident…but the actual request is regulatory…` |

### Ticket mix vs. the pitch

| Class | Claimed | **Measured** |
|---|---:|---:|
| Automated alerts | 37% | **36.93%** |
| External emails | 27% | **27.12%** |
| Unclear / contradictory traps | 18% | **18.59%** |
| Normal actionable tickets | 17% | **17.37%** |

Confirmed. **83% of the queue does not want a written answer.** The pitch is sound: the
product is a filter, not a writer.

## 2. Routing — service → team is strictly 1:1, so it must be a lookup table

- 20 services, 11 teams, **0 services map to more than one team**. 6 teams own several services (many-to-one, fine).
- A model must never decide the team. Classify the *service*, then look the team up. The full table is printed by `analyze_data.py` and becomes `data/catalogue.yaml`.
- Business entities are evenly spread: Nordics 4,015 / Luxembourg 4,113 / Switzerland 3,976 / Germany 3,965 / France 3,931.

### ⚠️ Assignee is pure noise
All **30 assignees appear under all 11 teams** (300 cross-team overlaps). Assignee is
randomly drawn and **cannot be learned** — see open question Q3.

## 3. Priority — unlearnable in training, deterministic in the challenge set

- 173 distinct Descriptions; **104 carry all five priority values**, and **all 173 carry more than one**. Identical text, every priority.
- 25 (Urgency, Impact) pairs; **0 map to a single Priority**. E.g. `(lowest, lowest)` n=5,099 → lowest 2,569 / low 1,532 / medium 505 / high 391 / highest 102.
- Median days-to-resolve is **flat**: lowest 11.00, low 10.79, medium 10.91, high 10.55, highest 11.27. Priority doesn't even drive handling time.

The challenge README states this outright: *"Priority/Urgency/Impact are random here… drawn
independently of each other and of the ticket content."* **But for the 20 challenge tickets
Priority is fully determined by the official 5×5 Urgency × Impact matrix.**

**This is the single most important finding: never train on Priority. Extract Urgency and
Impact from text with the LLM, then compute Priority in code from the organisers' matrix.**
That is exactly the design in the brief, now evidence-backed.

## 4. Leakage check — TF-IDF + logistic regression, random 80/20

| Target | Accuracy | Majority baseline | Lift | Macro-F1 | Classes |
|---|---:|---:|---:|---:|---:|
| service | 1.000 | 0.270 | +0.730 | 1.000 | 20 |
| work type | 1.000 | 0.799 | +0.201 | 1.000 | 2 |
| priority | 0.504 | 0.501 | **+0.003** | 0.137 | 5 |

**100.00% of test texts (4,000/4,000) appear verbatim in training.** The split is dishonest
by construction, so the perfect service and work-type scores are memorisation, not skill —
the service name is literally in the sentence. Priority gets **+0.003 lift**: statistically
nothing, exactly as predicted.

Consequences:
1. **Do not ship a TF-IDF classifier.** It has learned "the string after 'alert for' is the service". The 20 challenge tickets are freshly written with *deliberately wrong* service fields, so this breaks on contact.
2. **Report no offline accuracy from a random split.** Any eval must split by template, or be a hand-built eval set.
3. Service and work type are genuinely easy *when the text is honest* — the difficulty is exactly the 18.59% of traps where it isn't.

## 5. Consequences for retrieval

There is **no knowledge base** in this challenge — only past tickets and their comments
(every ticket has 1–5 comments, median ~333 characters, and 3,031 have no Resolution).
So the retrieval corpus is past tickets, and a "citation" is a **ticket id**, not a KB article.
With 173 unique texts, dense similarity is near-useless (everything matches everything);
BM25 over ticket + comments, filtered by service, does the real work. Retrieval must
dedupe by template and report low confidence instead of returning 5 copies of one sentence.

## 6. Where the brief and the challenge README disagree

1. **Grading targets.** The README grades 7 fields per ticket: Work type, Service, **Team, Assignee**, Priority, **Resolution status** (`done` / `cancelled` / `clarification` / `cannot reproduce`) and **Resolution text**. The brief's pipeline produces a draft reply and next steps but no resolution status or assignee. The result contract must carry both, or we score zero on them. → Q1/Q3.
2. **The 5×5 matrix is given, with different labels than the data.** Matrix axes are Urgency `Critical/High/Medium/Low/Lowest` × Impact `Major/Significant/Moderate/Minor/No direct impact` → Priority `Highest/High/Medium/Low/Lowest`. The data uses lowercase `lowest…highest` for all three. We need an explicit label mapping in code, tested.
3. **The critical-service list is given** (14 Critical, 6 Non-Critical) and is grounded business input — use it to justify Urgency/Impact instead of inventing rules.
4. **The market-hours and regulatory-deadline overrides in the brief are not in any organiser document.** Under our own "never invent a Swiss Life business rule" rule, these need your sign-off. → Q2.

## Open questions (blocking design, not code)

- **Q1 — Resolution status + text.** These are graded. Add them to the result contract as a 6th stage, or deliberately skip and lose those points?
- **Q2 — Business overrides.** Market-hours trading outage → raise impact; regulatory deadline < 24h → raise urgency. Invented, or from a Swiss Life source? If invented, I propose grounding them in the organisers' critical-service list instead (Critical service + full outage → Impact ≥ Significant) and labelling them clearly as our assumption.
- **Q3 — Assignee.** Provably random in the data. Options: (a) omit, (b) pick the team's most frequent assignee, (c) round-robin within the owning team. I suggest (b), stated as a heuristic.
- **Q4 — "Related open tickets within 4h."** A reasonable default, but it's our number, not theirs. Confirm 4h, or make it configurable (proposed: same service, status ≠ done, created within 4h, default configurable).
