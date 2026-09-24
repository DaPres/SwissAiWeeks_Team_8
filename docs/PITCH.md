# Pitch, demo runbook and Q&A

Quote **measured** facts only; every estimate is labelled as an assumption. Numbers below come from `eval/RESULTS_*.md` and `eval/dataset_analysis.json`.

## Expert jury - 60 seconds

> "Swiss Life's desks lose time on triage, and the same ticket gets a different answer depending on who picks it up. We checked the data: identical texts carry
> every priority from lowest to highest - the labels are noise - and a classifier trained on them does no better than always saying 'lowest'. So we did not learn from history: we built consistency.
>
> [demo 1] A German alert on the Trading Platform: personal data masked, routed through the service catalogue, priority computed from urgency and impact **with the reason shown**,
> draft written from the knowledge base with citations - one click to approve.
>
> [demo 2] This external e-mail tells the AI to escalate itself. It is **flagged, not obeyed**, and no model ever saw the text.
>
> On our stress and validation sets - paraphrased, German, French, misleading titles, injections - routing is [X] and [Y]; priority is always consistent with your matrix because the model supplies evidence and code applies the policy.
> It runs on Swisscom's Apertus in Switzerland or on your Azure OpenAI, with one config line."

## Demo - five tickets, ~40 s (all in `data/demo_tickets.json`, button "Load demo tickets")

| # | Ticket | What to point at |
|---|---|---|
| 1 | German alert, Trading Platform | masked text toggle, service -> team, priority with reason + live matrix, cited draft, **Approve** |
| 2 | "help pls" | quality gate: **clarification request**, no invented answer |
| 3 | "Access requested for Trading Platform" but the body describes an outage | badge "corrected from Service Request", reasons quote the description |
| 4 | External vendor mail with "ignore all previous instructions..." | badge *injection*, escalation, priority **not** raised, agent trace shows `escalate_to_human` first |
| 5 | Dashboard | acceptance rate, edit distance, p50/p95 latency, cost per ticket, flags |

Tickets 3-4 double as Q&A material. The "Demo box" tab runs any pasted e-mail live. Backup: `outputs/challenge_predictions_llm.*` and a screen recording (record before 12:00).

## Main stage - 2 minutes

Same spine, plus: (1) **impact arithmetic - assumption, not data**: the file holds ~2,500 tickets a month; every minute of reading/classifying saved per ticket is ~40 analyst-hours a month - the real number needs
their average triage time (expert question 6); (2) integration: REST API behind Jira Service Management, or the same tools inside Semantic Kernel / Azure; (3) pilot: one team, real KB, measure against their current triage time and draft acceptance.

## Slides (max six)

1 Problem + data findings - 2 What it does - 3 Live demo - 4 Architecture + agent trace - 5 Results table (with the awkward cells) - 6 Impact and next steps.

## Q&A bank

| Question | Answer |
|---|---|
| Why is accuracy on the file ~100%? | Only 173 unique texts exist and every test text is also in training; a plain TF-IDF model scores 100%. That is why we built separate stress and post-freeze validation sets and report the leakage as such. |
| Why not learn priority from history? | 104 of 173 texts carry all five priorities; priority equals the matrix of urgency x impact only 39% of the time (chance). A trained classifier equals the majority baseline (~50%). We use your ITIL matrix and let the model supply evidence. |
| Can the model change the priority? | No. It supplies urgency and impact with a quoted sentence each; the matrix computes the priority in code. It is always consistent with the matrix (measured 1.000). Borderline ratings can differ between runs (we measured raw model agreement, see results); identical text is cached so re-triage is idempotent. |
| Why not fine-tune? | It would memorise 173 templates, needs GPU time, and no insurer wants to maintain a fine-tuned triage model. |
| Where does the data go? | Masked before any model call (e-mails, phones, IBANs, policy numbers, names). It can run entirely on Swiss-hosted Apertus or your Azure tenant; offline rules work with no model at all. Tested: no raw personal data reaches the provider. |
| What if it is wrong? | Confidence threshold, escalation instead of a confident draft, a human approves every reply, full audit log (edit distance, dwell time, reasons). Confidence is a heuristic composite, not a calibrated probability - we say so. |
| Prompt injection? | Ticket text is delimited data; instruction-like content is detected (EN/DE/FR, hidden HTML, zero-width) **before** any model runs; tools are read-only; the worst case is a suggestion a human rejects. 8/8 stress injections and 1/1 validation injection escalated, 0 false positives on look-alike tickets. |
| How does it integrate? | REST API (`/api/triage`, `/api/challenge/predict`), behind Jira Service Management, or the same tools in Semantic Kernel. |
| Why not Copilot Studio? | It could sit behind it; our contribution is the triage logic, the consistency guarantee and the evaluation. |
| Cost per ticket? | Measured from token usage: about 0.2-0.4 US cents with `gpt-4.1-mini` (dashboard shows the live number); free offline. |
| French and Italian? | German/French have ontology terms and localised drafts; the LLM path generalises further (Italian works in the validation set). Multilingual embeddings via OpenAI when configured. |
| Does it learn? | Accepted edits become the base for drafts of the same service/work-type pattern; the dashboard tracks acceptance and edit distance over the session. Demonstrated, not claimed as a trained model. |
| What about the assignee? | In the data the assignee is independent of service, team, entity, work type and priority (Cramer's V ~ 0.04), so nobody can predict the historical one. We assign by policy (spread, lowest backlog) and say so. |
| Where did the resolution notes come from? | 21 human-written notes hide in the training comments; a data-driven filter (long, repeated, bound to one service) finds them. They are the "resolution pattern" the brief mentions, and also evidence for the service. |
| What would you do next? | Ingest the real KB, pilot with one team, calibrate impact rules with your priority policy, collect analyst judgements to calibrate confidence. |

## Questions for the Swiss Life experts (Thursday)

1. Will real knowledge articles be provided?  2. Are there multilingual or messier real samples?  3. What is your actual priority policy - an ITIL matrix? What counts as high impact (market hours, regulatory deadlines)?
4. What makes a draft acceptable - tone, length, mandatory fields?  5. Which ticketing system, and where would this plug in?  6. What is today's average triage time per ticket (needed for an honest impact figure)?

## Facts to quote - and to avoid

Quote: 20,000 tickets - 20 services - 11 teams - 173 unique texts - priority consistent with the matrix 39% (chance) - service->team 1:1 - 21 mined resolution notes - measured cost/latency.
Avoid: resolution outcome rates, resolution times, time-of-day patterns, assignee workloads (randomly generated).
