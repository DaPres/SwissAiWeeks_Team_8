# Intake

React (JavaScript/JSX), Base UI, Tailwind CSS, and Vite on the frontend, with a Python standard-library backend. Incident creation works locally. Optional live description checks use Jev by TypeSafe AI.

## Run locally

Requires Node.js 22.12+ (or 24+) and Python 3.10+. From this folder:

```sh
npm ci
npm run build
python3 server.py
```

Open http://127.0.0.1:8080. Python serves the compiled frontend from `dist/` and the `GET /api/health` endpoint. Run `npm run build` again after frontend changes.

## Frontend development

Keep `python3 server.py` running in one terminal, then start Vite in another:

```sh
npm run dev
```

Open http://127.0.0.1:5174 for live updates. Vite proxies `/api` to Python on port 8080. Port 5174 avoids the original project's frontend on 5173.

For another backend port, run `python3 server.py --port 8081` and `BACKEND_URL=http://127.0.0.1:8081 npm run dev`.

## Progressive incident intake

The page starts with one description input. Every edit to a nonempty description or optional detail triggers Jev after a 450 ms pause. Five markers assess whether the report identifies the responsible department, affected service and symptoms, business impact, timing/context, and diagnostic evidence. Readiness is the floored average of their probabilities as a percentage; it is an actionability signal, not a guarantee of resolution.

Editable chips sit below the input. Jev additionally selects team, service, entity, urgency, and impact from configured options, populating chips only at confidence 0.8 or higher. Chips bounce when their values change and open anchored Base UI popovers for manual edits. Option popovers show a scrollable list with search at the bottom; selecting an option saves it immediately. Manual values take precedence. The interface uses a locally bundled Geist font and a persistent light/dark toggle. While typing, a glowing outline traces the input. Chips and the matching right panel (below on small screens) first appear after a 450 ms pause, then remain visible through further edits; the panel refreshes only when typing stops again. It animates while checking, automatically requests one OpenAI suggestion after a low-readiness evaluation and a further 500 ms pause, or shows No Issues Found with a submit button when ready. Editing invalidates the old submit gate while the previous advice stays visible until the next pause.

The submit button appears in the right panel only when the current readiness score reaches 80%. `POST /api/incidents` independently verifies the server-held evaluation, threshold, exact description, and optional details. Evaluations expire after ten minutes. Editing invalidates the previous evaluation while a new check runs. Failed checks provide a visible retry action; browser requests time out after twelve seconds.

Incidents are saved locally to SQLite (`data/incidents.db`, ignored by Git). The response is `{ id, incident }`. Records contain the description, incident work type, open status, creation date, and null resolution fields. Optional context is preserved in All Comments. Inferred and manually entered fields are persisted; priority is derived when urgency and impact are known. Unknown fields remain absent. There is no Jira integration.

## AI configuration

Set `JEV_API_KEY` and `OPENAI_API_KEY` in `intake/.env` (see `.env.example`) and restart Python. The environment file is ignored by Git; process environment variables take precedence. Credentials stay on the backend.

`JEV_MODEL` defaults to `jev-latest`. `POST /api/description-quality` sends the description and supplied details to the [Jev API](https://docs.typesafe.ai/introduction/quickstart). Pending browser requests are cancelled on edits; upstream requests already received may still finish.

`OPENAI_MODEL` defaults to `gpt-4.1-mini`. `POST /api/description-suggestion` sends the server-verified draft and Jev markers to the OpenAI Responses API with `store: false`, requesting structured guidance. Evaluations are held in bounded memory (128 entries), cleared on restart.

Run backend checks with `python3 -m unittest discover -p 'test_*.py'` and build the frontend with `npm run build`.

## Files

- `server.py` — local Python development server and health API.
- `index.html` — React page entry point.
- `src/main.jsx` — React root and global CSS import.
- `src/App.jsx` — progressive incident composer and creation receipt.
- `src/styles.css` — Tailwind entry point.
- `vite.config.js` — React, Tailwind, and API proxy configuration.
- `dist/` — generated frontend build (not committed).

Restart Python after backend changes. The Python server binds to localhost and is intended for local development.
