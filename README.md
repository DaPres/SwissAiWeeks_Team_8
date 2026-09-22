# Swiss Life Support Agent

An AI support agent for operational service desks, built for the **Swiss {ai} Weeks Zurich Hackathon** (24–25 Sep 2026), Swiss Life challenge.

It uses RAG over knowledge-base docs and a multi-provider LLM client with automatic fallback:

1. **Swisscom Apertus** (`swiss-ai/Apertus-v1.5-70B`): primary. If the ~60-min bearer token expires, the client re-reads `.env` and retries once on HTTP 401.
2. **OpenAI** (`gpt-4o-mini`)
3. **Public AI via the Hugging Face router** (`:publicai` model suffix)
4. **Local Ollama** (`llama3.2:3b`): only used when there's no internet (set `OLLAMA_FALLBACK_MODE=always` to change this)

```
app/agent   LLM client + fallback logic
app/rag     Chroma + sentence-transformers ingest/retrieve
app/api     FastAPI  POST /chat
app/ui      Streamlit demo chat
data/sample_docs   placeholder FAQ docs
tests       offline unit tests
```

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env        # then paste your keys into .env
uv run python test_providers.py
uv run python -m app.rag.ingest
```

## Run the demo (two terminals)

```bash
uv run uvicorn app.api.main:app --reload --port 8000
uv run streamlit run app/ui/streamlit_app.py
```

To call the API directly:

```bash
curl -X POST localhost:8000/chat -H "Content-Type: application/json" -d '{"message":"How do I reset my password?"}'
```

The response includes `answer`, `provider` (which LLM served it), `sources`, and `failed_providers`.

## Tests

```bash
uv run pytest
```

## License

MIT
