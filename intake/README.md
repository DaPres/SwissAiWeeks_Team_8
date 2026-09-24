# Intake

A standalone vanilla JavaScript and Python starter. Tailwind CSS is compiled with the [Tailwind CLI](https://tailwindcss.com/docs/installation/tailwind-cli). The Python backend has no external dependencies or API keys.

## Run

Requires Python 3.10 or newer. The compiled CSS is committed, so running the app needs only Python. From this folder:

```sh
python3 server.py
```

Open http://127.0.0.1:8080. To use another port, run `python3 server.py --port 8081`.

## Frontend development

Install Node.js 20+ and run:

```sh
npm ci
npm run watch:css
```

Keep the CSS watcher and Python server running in separate terminals. Before committing style changes, run `npm run build:css` and include the regenerated `public/styles.css`.

## Files

- `server.py` — local development server and `GET /api/health` endpoint.
- `public/index.html` — page markup.
- `src/styles.css` — Tailwind entry point; utilities are scanned from `public/`.
- `public/styles.css` — generated CSS.
- `public/app.js` — browser logic and API requests.

Frontend changes appear on refresh. Restart the server after Python changes.
Only the `public` directory is served as static content. The server binds to localhost and is intended for local development.
