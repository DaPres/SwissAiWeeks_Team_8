# Intake core handoff (for the UI/UX team)

Two things the backend gives you, as **Python functions**, **REST endpoints** and a **WebSocket**:

| | What it does | Call it |
|---|---|---|
| **Enrich** | `description` (only field required) in -> fully enriched incident out, with optional `clientResolution` / `expertResolution` | when the user submits |
| **Typing assist** | the backend "talks back" while the user is still typing: likely issue statements, word completion, missing-fact questions, and **sometimes** a quick self-service fix | on every (debounced) keystroke |

Everything runs **offline with no key** (rules + knowledge base). With an LLM key in `.env` the same calls get smarter (better classification, resolution notes, drafts in the user's language, optional `smart` suggestions).

## 1. Start it

```bash
pip install -r requirements.txt
python -m triagemate.cli serve --port 8765          # REST + WebSocket + analyst UI, CORS open for development
# reference implementation of the typing experience:  http://127.0.0.1:8765/static/intake_demo.html
```

Interactive API docs: `http://127.0.0.1:8765/docs`. Enriched incidents are stored, so they also appear in the analyst queue at `/`.

## 2. Python (if you call the backend in-process)

```python
from triagemate.intake import enrich_incident, enrich_many, assist

e = enrich_incident("Hi, my order is stuck in pending approval since 09:00")   # a string is enough
e.service, e.priority, e.client_resolution, e.expert_resolution                # typed attributes
payload = e.to_json()                                                          # camelCase dict for the browser

# optional hints - used as hints, never trusted blindly (Jira-style or camelCase keys both work)
e = enrich_incident({"description": "...", "service": "Order Management", "entity": "Germany", "reporter": "a@b.ch", "workType": "Incident"})

enrich_incident("...", use_llm=False)        # force the deterministic engine
enrich_incident("...", commit_assign=False)  # preview: does not consume agent capacity
enrich_many([...])                           # batch; alert storms (same service, similar text, < 4 h) are linked as duplicates

r = assist("Hi i am facing a transaction")   # typing assist, ~5 ms
```

CLI: `python -m triagemate.cli intake --text "..."` and `python -m triagemate.cli assist --text "..."`.

## 3. REST

| Method + path | Body / query | Returns |
|---|---|---|
| `POST /api/intake/enrich` | `{"description": "..."}` (+ optional fields). `?preview=true`, `?useLlm=false` | the enriched incident |
| `POST /api/intake/enrich/batch` | `{"incidents": [ ... ]}` or a plain list | `{"count", "incidents": [...]}` |
| `POST /api/intake/assist` | `{"text": "...", "mode": "fast"\|"smart"}` | typing-assist response |
| `GET  /api/intake/starters` | - | common openers for an empty input box |
| `GET  /api/intake/schema` | - | JSON Schemas of all contracts (`docs/intake_schema.json`) |

Errors: `422` with a readable message (missing/too short `description`, wrong body shape).

```js
const r = await fetch("/api/intake/enrich", {method: "POST", headers: {"Content-Type": "application/json"},
                       body: JSON.stringify({description: text})});
const incident = await r.json();
```

Generate TypeScript types: `npx json-schema-to-typescript docs/intake_schema.json > intake.d.ts` (re-create the schema with `python -m triagemate.cli schema`).

## 4. WebSocket - typing assist

`ws://host/ws/intake/assist`. Send `{"text": "<everything typed so far>", "mode": "fast"}` on each debounced keystroke (~120 ms); every message gets one response back (the same JSON as the REST call).
**Ignore stale answers**: every response echoes `text`; only render it if `response.text === input.value` (see `ui/intake_demo.html`, which also falls back to REST if the socket is unavailable).

## 5. The enriched incident (what you render)

```jsonc
{
  "id": "INC-0273296875",             // yours if you sent one
  "summary": "My mailbox is full and I cannot receive new emails.",     // derived from the description if not given
  "description": "...", "language": "en",                                // en | de | fr (draft/clarification follow it)
  "workType": "Incident",             // Incident | Service Request - decided from the text, the given value is only a hint
  "service": "Outlook & Email",       // null when it cannot be identified (then serviceIdentified=false and team="Service Desk")
  "serviceIdentified": true, "team": "Enterprise Applications", "businessCritical": false, "entity": null,
  "assignee": "irina.sokolov@intcom.com", "assigneeReason": "...",
  "urgency": "low", "impact": "low", "priority": "low", "priorityLabel": "Low",   // priority = matrix(urgency, impact), always consistent
  "priorityReason": {"urgency": "...", "impact": "...", "overrides": []},
  "resolutionStatus": "done",         // done | clarification | cancelled | cannot reproduce
  "confidence": 0.87,                 // heuristic 0..1, not a calibrated probability
  "flags": {"unclear": false, "mismatch": false, "duplicate": false, "injection": false, "lowConfidence": false, "containsPersonalData": false},
  "reasons": ["..."],                 // why it was classified this way (show under an "Why?" toggle)
  "corrections": [{"field": "service", "provided": "Outlook & Email", "final": "NAV Calculation"}],   // where the input hints were wrong
  "clarification": null,              // {"questions": [<=3], "message": "..."} when the text is too unclear to act on
  "clientResolution": {               // OPTIONAL - what the REQUESTER can try/prepare right now
    "title": "...", "text": "Here is what you can try right away:\n1. ... [KB-18]\n...", "steps": ["...", "..."],
    "confidence": 0.9, "language": "en", "escalation": "If this does not help, the Enterprise Applications team will pick up your ticket.",
    "citations": [{"id": "KB-18", "title": "..."}], "source": "kb-self-service"
  },
  "expertResolution": {               // OPTIONAL - what the TEAM should do / did
    "note": "Resolution: ...", "jiraComment": "agent@intcom.com: Resolution: ...", "steps": ["analyst next step [KB-18]"],
    "source": "playbook:HIST-07 | template:... | llm", "assignee": "...", "team": "...",
    "similarPast": [{"id": "HIST-07", "service": "...", "text": "...", "score": 0.4}], "citations": [...]
  },
  "escalation": null,                 // {"required": true, "message": "..."} when the text contained instruction-like content
  "draftReply": {"kind": "reply|clarification|escalation", "language": "en", "text": "...", "nextSteps": ["..."], "citationCoverage": 1.0},
  "relatedIncidents": [],             // earlier open incidents on the same service that look like the same event
  "provided": {},                     // echo of the optional fields you sent
  "meta": {"mode": "offline|hybrid|llm", "latencyMs": 26, "costUsd": 0, "tokensIn": 0, "tokensOut": 0, "promptVersions": {}, "notes": [], "trace": [/* agent tool calls */]}
}
```

### When do `clientResolution` / `expertResolution` appear?

| Situation | clientResolution | expertResolution | Also |
|---|---|---|---|
| Self-service fixable (mailbox full, locked out, portal login, order pending approval ...) | yes - only the steps of the matching scenario | yes | |
| Access / licence request | yes - the "what to prepare" checklist | yes - a request-fulfilment note | |
| Real, high-priority incident on a **critical** service (outage, all users) | **no** (never tell a trader to clear a cache during an outage) | yes | priority highest/high |
| Unclear text ("help") | no | no | `clarification` with <= 3 questions |
| Instruction-like text (prompt injection) | no | no | `escalation.required = true`; the text never reaches a model |
| Duplicate of an open incident | no | yes (links to the parent) | `flags.duplicate`, `relatedIncidents` |

Either can be `null`; render only what is present. `expertResolution.jiraComment` is ready to paste into Jira in the assigned agent's voice.

## 6. Typing-assist response

```jsonc
{
  "text": "Hi i am facing a transaction issue, my order is stuck in pending approval",   // echo - use it to drop stale answers
  "stage": "empty | typing | ready",           // ready = the service is clear and there is enough text to submit
  "wordCompletion": "x",                        // rest of the word being typed ("mailbo" -> "x"); null otherwise
  "suggestions": [{"text": "My order stays in pending approval and does not reach the broker.", "service": "Order Management",
                   "team": "Trading Support", "kind": "incident|request|ai", "score": 0.84, "hasQuickSolution": true}],
  "likelyService": {"name": "Order Management", "team": "Trading Support", "confidence": 0.7, "critical": true},   // null while ambiguous
  "quickSolution": {"title": "...", "service": "...", "steps": ["...", "..."], "confidence": 0.91,
                    "citations": [{"id": "KB-02", "title": "..."}], "escalation": "If this does not help, the Trading Support team will pick up your ticket."},
  "followUpQuestions": ["Can you share one example order reference and the broker account used?", "When did it start (date and time)?"],
  "language": "en", "mode": "fast", "blocked": false, "notes": [], "latencyMs": 8
}
```

Behaviour to design for:

* **Ambiguous words fan out.** "Hi i am facing a transaction" -> suggestions from settlement, allocations, reporting ...; `likelyService = null`; **no** `quickSolution`.
* **`quickSolution` only appears sometimes** - when the service is clear, a matching self-service article exists and it is safe. Never during an outage of a critical service, never for instruction-like text (`blocked: true`, no suggestions at all).
* **Empty box** (`stage: "empty"`): `suggestions` are common ways to begin - use them as starter chips.
* **`mode: "smart"`** adds LLM-written suggestions (`kind: "ai"`, masked text only, 1.6 s budget, silent fallback). Use it after a longer pause (e.g. 600 ms), not on every keystroke. Offline `fast` mode is ~5-10 ms.
* Suggestions are English statements; `language` reports the detected language (the enrich output and drafts follow German/French).

## 7. Notes and limits

* **Safety:** personal data is masked before any model call; injected text is escalated, never obeyed; nothing here writes to Jira or sends anything - it returns proposals for a human.
* The knowledge base, the client self-service texts and the issue phrasings are **synthetic** (no real Swiss Life documentation was provided); replace `kb/` (or edit `scripts/generate_kb.py` and run `python scripts/generate_kb.py`) with real articles.
* With no service given, the backend guesses one from the wording (a soft hint the text can override). Confidence values are heuristics.
* Tests: `python -m pytest tests/test_intake.py -q`.
