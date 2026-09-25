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

The five chips are Work Type, Urgency, Impact, Priority, and Service Teams, matching the example in `Jev.http`. Their dropdowns stay below the input before and after selection. Filled chips show their value and a checked-square icon in dark green, and remain editable. Unfilled chips trace a staggered animated outline while Jev reloads; reduced-motion preferences disable the animation. Impact uses the descriptive labels from the example. Each automatic value, including Priority, uses the largest number in its answer’s `probabilities`, independently of `choice` and `confidence`. An unclear/unknown winner, a tie with unclear, or missing/invalid probabilities leaves the chip empty. Priority’s manual popover still uses the urgency/impact matrix, and final engine processing ensures the saved priority is consistent. No chips are rendered inside the input.

Every description or manual field edit triggers Jev after a 450 ms pause. The highest-probability valid option populates each chip; unclear or unknown winners remain unfilled. Description quality and confidence are advisory, not submission requirements. The first chips appear after that pause, then remain visible across edits. Manual values override inference and survive description edits, clearing the description, and final backend processing; they reset only when starting a new incident. The sidebar and chip labels use the same 16px text and 22px radius.

The submit button appears once the description contains non-whitespace text. Submission requires only a nonempty description and the five selected chips. Suggestions, low quality scores, pending or failed Jev checks, and expired evaluations do not block submission. `POST /api/incident-process` validates the current description, chip options, manual choices, directly before calling the shared backend. It does not require an evaluation token.

The processing dialog cannot be dismissed while the engine runs. If the shared backend proposes a `clientResolution`, the client can mark it resolved or ask for help; otherwise the dialog immediately confirms the team handover. A client fix awaiting a decision can be reopened from My Incidents. Incidents and their enriched JSON are saved locally to SQLite (`data/incidents.db`, ignored by Git). `GET /api/incidents?account=...` loads the grid, and `POST /api/incidents/{id}/decision` records the client's choice. Department accounts in the header are local demo views of routed incidents, not authentication or Jira integration. The detail view shows the saved fields and `expertResolution` when one exists. Resolution is the proposed triage outcome; the client acceptance/handover flow continues to govern workflow Status. The resolution note is stored in All Comments with the assigned agent prefix. Manual assignee, resolution, and comment edits are preserved, and final Priority is recomputed if the engine changes Urgency or Impact.

## AI configuration

Set `JEV_API_KEY` and `OPENAI_API_KEY` in `backend/.env` (see `backend/.env.example`) and restart Aspire. Existing `intake/.env` values are only used when absent from the shared environment. The environment file is ignored by Git; process environment variables take precedence. Credentials stay on the backend.

`JEV_MODEL` defaults to `jev-latest`. The five question definitions come from `Jev.http`; its sample state is replaced by the live description and manual selections. The API returns inferred fields and unresolved fields without a fabricated description-quality score. Manual values always take precedence. No auxiliary classification or quality questions are sent. The shared backend supplies service, assignee, and resolutions after submission.

OpenAI sidebar suggestions now assess the description and current field selections directly. They do not depend on the removed Jev quality markers, and remain advisory.

`service-teams.json` supplies routing context to Jev and mirrors the ownership mapping in `backend/app/catalog.py`. Keep these catalogues in sync when ownership changes; users can describe the affected service without knowing the owning department.

The collapsible **Jev Debug** pane on Create Incident shows the actual last request, Jev response, and elapsed time. It distinguishes the previous exchange while a new check is pending, and includes sanitized errors when a check fails. Authentication is always redacted. The backend allows 15 seconds for Jev and the browser allows 20 seconds for the API round trip. Pending browser requests are cancelled on edits; upstream requests already received may still finish. Submit validation hints fade out after five seconds, or after interaction with the description or a dropdown chip. Only one general hint appears at a time, appearing to the left of Submit Incident until it fades; another invalid attempt restarts the timer.

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
