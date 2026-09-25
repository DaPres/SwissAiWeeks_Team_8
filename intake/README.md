# Intake

React (JavaScript/JSX), Base UI, Tailwind CSS, and Vite on the frontend, with a Python standard-library HTTP server. Jev evaluates drafts as they are edited; the shared backend processes completed incidents and returns an optional client fix and expert proposal.

## Run with Aspire

From the repository root, run `aspire start` (or `aspire run`). Intake is available at http://127.0.0.1:8080; the existing explorer remains on port 5173.

Aspire manages three connected resources: `intake` (React/Vite), `intake-backend` (Python), and the shared `backend` (FastAPI). Vite forwards `/api` to Intake's discovered Python endpoint. Intake calls the shared backend's `/api/intake/enrich` for knowledge retrieval, routing and client/expert resolution proposals. There is no Main2 import or dependency. Repeated identical previews are cached for five minutes; the legacy `/api/triagemate-demo` endpoint uses this same shared backend.

`backend/.env` is the canonical local environment. Aspire injects provider credentials only into server resources, never the frontend. Intake also reads this file for standalone development; `intake/.env` is a fallback for missing values. Requires Node.js 22.12+ (or 24+), Python 3.13+, uv and Aspire.

For standalone development with an already running shared backend:

```sh
cd intake
uv sync
TRIAGE_BACKEND_URL=http://localhost:<shared-backend-port> uv run python server.py --port 8081
# In another terminal:
npm ci
npm run dev
```

Vite defaults to port 8080 and proxies to Intake's Python API on port 8081. `BACKEND_URL` overrides that target; `TRIAGE_BACKEND_URL` identifies the separate shared triage API. Aspire supplies both automatically.

## Progressive incident intake

The page starts with one description input. Every edit triggers Jev after a 450 ms pause. Requests contain exactly `worktype`, `urgency`, `impact`, `priority`, and `service_teams`; the former service/entity inference and five quality questions are not sent.

The five chips are Work Type, Urgency, Impact, Priority, and Service Teams, matching the example in `Jev.http`. Their dropdowns stay in a vertically aligned column below the input before and after selection. Filled chips show the field title and value with a plain checkmark in dark green, and remain editable. Unfilled chips trace a staggered animated outline while Jev reloads; reduced-motion preferences disable the animation. Impact uses the descriptive labels from the example. Each automatic value, including Priority, uses the largest number in its answer’s `probabilities`, independently of `choice` and `confidence`. An unclear/unknown winner, a tie with unclear, or missing/invalid probabilities leaves the chip empty. Priority’s manual popover still uses the urgency/impact matrix, and final engine processing ensures the saved priority is consistent. No chips are rendered inside the input.

Every description or manual field edit triggers Jev after a 450 ms pause. The highest-probability valid option populates each chip; unclear or unknown winners remain unfilled. Description quality and confidence are advisory, not submission requirements. The first chips appear after that pause, then remain visible across edits. Manual values override Jev inference and survive description edits and clearing the description; they reset only when starting a new incident. After submission, the neural engine may correct any submitted classification, including manual choices. The persisted enrichment stores submittedFields and fieldCorrections (before/after); My Incidents marks changed fields with an info tooltip. New enrichment and unchanged fields are not marked. Priority is recomputed from the reviewed urgency and impact. Existing incidents without correction history remain readable. The header navigation and chip labels use the same 16px text and 22px radius.

The submit button appears once the description contains non-whitespace text. Submission requires only a nonempty description and the five selected chips. Suggestions, low quality scores, pending or failed Jev checks, and expired evaluations do not block submission. `POST /api/incident-process` validates the current description, chip options, manual choices, directly before calling the shared backend. It does not require an evaluation token.

The processing dialog cannot be dismissed while the engine runs. If the shared backend proposes a `clientResolution`, the client can mark it resolved or ask for help; otherwise the dialog immediately confirms the team handover. A client fix awaiting a decision can be reopened from My Incidents. Incidents and their enriched JSON are saved locally to SQLite (`data/incidents.db`, ignored by Git). `GET /api/incidents?account=...` loads the grid, and `POST /api/incidents/{id}/decision` records the client's choice. Department accounts in the header are local demo views of routed incidents, not authentication or Jira integration. The detail view shows the saved fields and `expertResolution` when one exists. Resolution is the proposed triage outcome; the client acceptance/handover flow continues to govern workflow Status. The resolution note is stored in All Comments with the assigned agent prefix. The engine can correct submitted fields, and final Priority is recomputed if the engine changes Urgency or Impact.

## AI configuration

Set `JEV_API_KEY` and `OPENAI_API_KEY` in `backend/.env` (see `backend/.env.example`) and restart Aspire. Existing `intake/.env` values are only used when absent from the shared environment. The environment file is ignored by Git; process environment variables take precedence. Credentials stay on the backend.

`JEV_MODEL` defaults to `jev-latest`. The five question definitions come from `Jev.http`; its sample state is replaced by the live description and manual selections. The API returns inferred fields and unresolved fields without a fabricated description-quality score. Manual values take precedence during drafting; the final neural-engine review can correct them. No auxiliary classification or quality questions are sent. The shared backend supplies service, assignee, and resolutions after submission.

OpenAI sidebar suggestions assess the entire description and current field selections and ask at most one genuinely unanswered question. Concrete symptoms count as evidence, and explicit answers such as no troubleshooting performed or unknown timing are accepted. Once the symptom is clear, guidance favors missing business context such as a deadline or blocked work; actionable reports and simple information questions need no extra diagnostic checklist. Suggestions remain advisory. Opt-in live semantic regressions run with `RUN_LIVE_SUGGESTION_TESTS=1 uv run python -m unittest test_suggestion_behavior -v` from `intake/`.

`service-teams.json` supplies routing context to Jev and mirrors the ownership mapping in `backend/app/catalog.py`. Keep these catalogues in sync when ownership changes; users can describe the affected service without knowing the owning department.

The header contains the logo, Create Incident / My Incidents navigation, and named accounts with department labels and pixel avatars. Names come from the sample ticket data; account IDs and routing stay the same. Jev debug output is not displayed. The backend allows 15 seconds for Jev and the browser allows 20 seconds for the API round trip. Pending browser requests are cancelled on edits; upstream requests already received may still finish. Submit validation hints fade out after five seconds, or after interaction with the description or a dropdown chip. Only one general hint appears at a time, appearing to the left of Submit Incident until it fades; another invalid attempt restarts the timer.

`OPENAI_MODEL` defaults to `gpt-4.1-mini`. `POST /api/description-suggestion` sends the server-verified draft and field selections to the OpenAI Responses API with `store: false`, requesting structured guidance. Evaluations are held in bounded memory (128 entries), cleared on restart.

Run backend checks with `uv run python -m unittest discover -p 'test_*.py'` and build the frontend with `npm run build`.

## Files

- `server.py` — local Python development server and health API.
- `index.html` — React page entry point.
- `src/main.jsx` — React root and global CSS import.
- `src/App.jsx` — progressive incident composer and workspace navigation.
- `src/IncidentDialog.jsx` — processing, client fix, and handover dialog.
- `src/IncidentsView.jsx` — incident grid and detail view.
- `src/AccountSwitcher.jsx` — local demo accounts for the client and departments.
- `src/styles.css` — Tailwind entry point.
- `vite.config.js` — React, Tailwind, and API proxy configuration.
- `dist/` — generated frontend build (not committed).

Restart Python after backend changes. The Python server binds to localhost and is intended for local development.

## Container deployment

Intake has its own image, separate from the existing triage explorer/shared-backend image. Its Python server serves the compiled React frontend and `/api` from the same origin; Node/Vite are only used during the image build.

From the repository root, with provider credentials in `backend/.env`:

```sh
docker compose up --build -d
```

Open Intake at http://localhost:8082 and the triage explorer at http://localhost:8000. Override `INTAKE_PORT` or `TRIAGE_PORT` if needed. Intake calls `http://backend:8000` over the Compose network. Named volumes preserve both services' data; `docker compose down` retains them. Keys are loaded at runtime and excluded from image build contexts.

To build just Intake:

```sh
docker build -f intake/Dockerfile -t team8-intake .
```

For an independently hosted Intake container, configure `TRIAGE_BACKEND_URL` to the shared backend's reachable URL, plus `JEV_API_KEY` and `OPENAI_API_KEY` (optionally `JEV_MODEL` and `OPENAI_MODEL`). Expose port 8080 and mount persistent storage at `/app/intake/data`. `/api/health` identifies the service as `intake`. `HOST` defaults to loopback locally and `0.0.0.0` in the image.

Version-tag releases publish both `aiweeksteam8.azurecr.io/triage` and `aiweeksteam8.azurecr.io/intake`. The existing Azure deployment step still updates the triage Container App; the separate Intake image must be deployed as an additional app with the runtime settings above.
