# Security - jailbreak and prompt-injection resistance

Everything below is reproducible: `python eval/redteam.py` (deterministic layers), `python eval/redteam.py --llm` (adds the LLM guard and the
full live pipeline), `python eval/redteam.py --no-gate --llm` (switches the detector off to see what the model + code do on their own),
`python -m pytest tests/test_redteam.py`.

## What an attacker controls and what they want
The ticket summary, description, every comment, the reporter address and any hidden markup. They want to (1) change a decision (priority,
status, approval, routing), (2) extract the system prompt, tools, secrets or other people's data, (3) get their own text or links into a Jira
comment or a reply, (4) stall the service with a huge input, or (5) make the agent call tools it should not.

## Defence in depth
| # | Layer | What it does | Model bytes for what it stops |
|---|---|---|---|
| 0 | Size caps | 20 k characters per field are analysed; the model-facing text is a fixed 1 k / 12 k / 8 k (summary / description / comments), so nothing can hide beyond what the guard reads. Comment stripping is linear time. | - |
| 1 | Sanitise | NFKC, zero-width characters, HTML comments and hidden CSS are separated out: they are scanned but never reach a model. Hidden markup that carries *any* instruction cue is hostile by construction. | 0 |
| 2 | Regex gate | Bounded patterns for override / persona / prompt extraction / fake system notices / chat control tokens / tool names / exfiltration / manipulated decisions in EN, DE, FR, IT, ES, PT, NL, RU, ZH; re-run on decoded variants (leetspeak, homoglyphs, spaced letters, reversed text, rot13, base64). Strong cues fire alone, weak cues need a second. | 0 |
| 3 | LLM guard | Only when the regex is silent and a model is configured: an isolated JSON verdict on the **masked** text (no tools, no ticket context, windowed over the whole model-facing text). A positive verdict escalates; an unavailable model fails open (regex only), never on a positive. | the masked text goes to the guard call only |
| 4 | Architecture | The model supplies *evidence*; code computes priority (ITIL matrix), team (catalogue) and status (policy). Agent tools are read-only and only recommend. Ticket text is always inside a delimited data block; role tags are neutralised. | - |
| 5 | Output guards | Links are stripped from notes, drafts and steps (company links kept). Identifiers reflected into notes are taken only from sentences without any injection cue. Personal data is masked before any model call and never restored into notes. | - |
| 6 | Human | An escalated ticket is never auto-resolved or auto-answered; the analyst sees the reason. | - |

## Measured (offline regexes, live model where stated)
Five sets, written at different times. **Only the last two are honest generalisation numbers**; earlier sets were used to tune.

| Set | Attacks | Harmless look-alikes | Regex gate | With LLM guard | Status |
|---|---|---|---|---|---|
| Original detector (before this work) | 46 / 28 (two sets) | 20 / 40 | 13 / 46 and 3 / 28 caught; 7 / 20 and 6 / 40 false alarms | - | baseline |
| 1 (`redteam.py`) | 52 | 40 (x2 sender variants) | 52 / 52, 0 false alarms | 52 / 52, 0 false alarms | tuned on |
| 2 (`redteam_holdout.py`) | 28 | 40 (x2) | **first pass 8 / 28**, 5 distinct false alarms; after tuning 28 / 28, 0 | 28 / 28, 7 / 80 false alarms (4 distinct sentences) | tuned after first pass |
| 3 (`redteam_holdout2.py`) | 30 | 40 (x2) | **first pass 4 / 30 (13 %)**, 0 false alarms | 30 / 30, 0 false alarms | guard prompt tuned on it |
| 4 (`redteam_holdout3.py`) | 20 | 30 | first pass 3 / 20 | **first and only run: 19 / 20 stopped, 1 / 30 false alarm**; the miss ("forward *each* ... to an external address") was a missing quantifier and is fixed | **blind check** |

Reading it honestly:
* A hand-written regex list **does not generalise** (13 % on fresh paraphrases). That is why the LLM guard exists; the regex layer is the cheap,
  zero-byte first line for the obvious cases.
* The LLM guard raises recall on unseen wording to about 95 % at a cost of a few percent false alarms on deliberately confusing sentences
  ("reply only with the confirmation number", "enable developer mode in the browser"). A false alarm sends a real ticket to a human with the reason shown.
* **Real tickets: 0 false alarms on 331 texts** (all 173 unique training texts, the 106-ticket stress set, the 37-ticket validation set, the 20 challenge
  tickets and the demo tickets), both layers active, and all 10 labelled injection tickets among them are stopped. The 20 challenge outputs are
  byte-identical to the committed ones offline.
* **Accuracy is unchanged.** Final-code hybrid run against the committed baseline, stress / validation: routing 1.000 / 1.000, work type 1.000 / 1.000,
  clarification recall and precision 1.000, injection resistance 1.000 with 0 false positives, personal-data masking 1.000, priority = matrix 1.000,
  priority sanity 0.967 / 0.909 (two intermediate runs read 0.95 on the stress set: model run-to-run variation, gone in the final run). Offline: every
  metric identical. The 20 challenge outputs: routing identical 20 / 20 in both modes, all 12 audit checks pass.
* Cost of the guard: about +0.03 US cents per ticket (0.245 to 0.273) and roughly +0.4 s at the median in the evaluation (0.7 to 1.4 s for one isolated call; it runs before
  classification and is partly hidden by concurrency in batches). Switch it off with `LLM_GUARD=0`; the threshold is `GUARD_THRESHOLD` (default 0.7).

### The model on its own (detector switched OFF, live `gpt-4.1-mini`, 80 attacks)
This measures the second line: what happens if the gate is bypassed.
* **Priority inflated on a harmless ticket: 0 / 80.** Priority is computed in code from evidence.
* **System prompt or tool names leaked: 0 / 80.**
* Attacker text echoed into an output (a canary token): 11 / 80 (14 %), almost all through the "identifiers to reuse" path. Fixed by lifting identifiers only
  from sentences without injection cues, and by the guard; with the gate on, 0 / 110 reach an output.

### Denial of service (found by the new tests, existing code)
One 250 KB ticket with unclosed `<!--` markers took **53 s** (a quadratic regex in `sanitise` plus the name redactor). Now **0.17 s**
(size cap and a linear comment stripper). Guarded by `test_hostile_input_cannot_cause_catastrophic_backtracking`.

## Known limits (stated, not hidden)
* **Offline mode has no LLM guard.** Paraphrased attacks pass the regex gate and reach the deterministic engine, which is safe by construction
  (no model, template outputs, priority from rules): measured offline behavioural bypass is 1 / 110 (a reflected ID-shaped token) and 0 priority inflations.
* The guard is a model and can itself be fooled by an adaptive attacker; it sees only masked text, has no tools and its verdict can only *escalate*.
* Sample sizes are small (20-52 attacks per set); intervals are wide. Sets are single-author. A red team with knowledge of the prompts is not simulated.
* "Zero bytes to a model" holds for regex-stopped tickets. For guard-stopped tickets the masked text goes to the isolated guard call and nothing else
  (no classification, drafting or agent call ever sees a flagged ticket).
* Text beyond 12 k characters (description) is not analysed and not sent to any model; this is a documented trade-off for bounded latency and cost.
