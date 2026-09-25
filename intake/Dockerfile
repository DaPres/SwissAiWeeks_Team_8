# Build from the repository root: docker build -f intake/Dockerfile -t team8-intake .
FROM node:22-alpine AS frontend
WORKDIR /src
COPY intake/package.json intake/package-lock.json ./
RUN npm ci
COPY intake/src ./src
COPY intake/index.html intake/vite.config.js ./
RUN npm run build

FROM python:3.13-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8080
WORKDIR /app/intake
COPY intake/pyproject.toml intake/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY intake/*.py ./
COPY intake/Jev.http intake/service-teams.json ./
COPY intake/src/catalog.json intake/src/assignees.json intake/src/priority-matrix.json ./src/
COPY --from=frontend /src/dist ./dist
RUN useradd --uid 10001 app && mkdir -p data && chown app data
USER app
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['PORT'] + '/api/health', timeout=2)"
CMD ["python", "server.py"]
