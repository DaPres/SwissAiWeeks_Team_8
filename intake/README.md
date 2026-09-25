# Intake

React (JavaScript/JSX), Base UI, Tailwind CSS, and Vite on the frontend, with a Python standard-library HTTP server. Incident creation works locally. Optional live description checks use Jev by TypeSafe AI; an offline demo can call the sibling TriageMate core.

## Run locally

Requires Node.js 22.12+ (or 24+) and Python 3.10+. From this folder:

```sh
npm ci
npm run build
python3 server.py
```

Open http://127.0.0.1:8080. Python serves the compiled frontend from `dist/` and the `GET /api/health` endpoint. Run `npm run build` again after frontend changes.

The **Run TriageMate Demo** button needs the sibling `Main2` dependencies installed in the Python environment that runs this server. For example, from the repository root:

```sh
uv venv Main2/.venv
uv pip install --python Main2/.venv/bin/python -r Main2/requirements.txt
cd intake && ../Main2/.venv/bin/python server.py
```

The demo passes the description and visible chip values to `Main2/triagemate` using its offline preview path (`use_llm=False`, `commit_assign=False`) and displays the returned JSON below the form. Service, entity, urgency, impact, summary, and reporter map to native TriageMate inputs; selected team, assignee, context, and evidence go in labeled comments. The first call can take longer while the local retrieval index is built.

## Frontend development

Keep `python3 server.py` running in one terminal, then start Vite in another:

```sh
npm run dev
```

Open http://127.0.0.1:5174 for live updates. Vite proxies `/api` to Python on port 8080. Port 5174 avoids the original project's frontend on 5173.

For another backend port, run `python3 server.py --port 8081` and `BACKEND_URL=http://127.0.0.1:8081 npm run dev`.

## Progressive incident intake

The page starts with one description input. Every edit to a nonempty description or optional detail triggers Jev after a 450 ms pause. Five markers assess whether the report identifies the responsible department, affected service and symptoms, business impact, timing/context, and diagnostic evidence. Readiness is the floored average of their probabilities as a percentage; it is an actionability signal, not a guarantee of resolution.

Unfilled chips for service, team, entity, urgency, and impact sit below the input. Selecting a value moves it into a smaller chip in the input's bottom row; clicking that chip clears the value and returns the field below. The selected row scrolls horizontally, with edge fades that track its scroll position. Summary, reporter, assignee, context, and evidence stay hidden with empty draft values. Jev selects the chip fields from configured options, populating chips only at confidence 0.8 or higher. Option popovers show a scrollable list with search at the bottom; selecting an option saves it immediately. Manual values take precedence, including an explicit clear that suppresses a previous AI inference. The interface uses a locally bundled Geist font and a persistent light/dark toggle. While typing, a glowing outline traces the input. Chips and the matching right panel (below on small screens) first appear after a 450 ms pause, then remain visible through further edits; the panel refreshes only when typing stops again. It animates while checking, requests one OpenAI suggestion after a low-readiness evaluation or when Jev finds evidence insufficient, and otherwise shows a short ready message. Evidence is assessed from the description, and OpenAI prioritizes a concrete evidence request when needed. Editing invalidates the old submit gate while the previous advice stays visible until the next pause.

The submit button appears at the right of the input row once the description contains non-whitespace text. An early click gives feedback; submission proceeds only when the current readiness score reaches 80%. `POST /api/incidents` independently verifies the server-held evaluation, threshold, exact description, and optional details. Evaluations expire after ten minutes. Editing invalidates the previous evaluation while a new check runs. Failed checks provide a visible retry action; browser requests time out after twelve seconds.

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
