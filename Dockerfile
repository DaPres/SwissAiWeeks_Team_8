# Single image: the React frontend (triage-explorer) is built and served by the FastAPI backend from "/".

FROM node:22-alpine AS frontend
WORKDIR /src
COPY triage-explorer/package.json triage-explorer/package-lock.json ./
RUN npm ci
COPY triage-explorer/ ./
RUN npm run build

FROM python:3.13-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 STATIC_DIR=/app/static
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
# training data: the knowledge base is built from it on first start (TRAINING_FILE defaults to the repo root)
COPY jira_first_20000_requested_fields_synthetic.json /app/
# blind-eval challenge for the Evaluation tab (found by its jira_hackathon_blind_eval_challenge_*.json name)
COPY jira_hackathon_blind_eval_challenge_*.json /app/
COPY --from=frontend /src/dist /app/static

ARG VERSION=dev
ENV APP_VERSION=$VERSION
RUN useradd --uid 10001 app && mkdir -p /app/backend/data && chown app /app/backend/data
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
