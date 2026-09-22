"""FastAPI backend.

Run:  uv run uvicorn app.api.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.agent import AllProvidersFailed, LLMClient
from app.rag.retrieve import format_context, retrieve

llm = LLMClient()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load the embedding model at boot so the first demo question isn't slow.
    retrieve("warm up", k=1)
    yield


app = FastAPI(title="Swiss Life Support Agent", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=0, le=10)


class Source(BaseModel):
    source: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    provider: str
    model: str
    sources: list[Source]
    failed_providers: dict[str, str]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    chunks = retrieve(req.message, k=req.top_k) if req.top_k else []
    try:
        resp = llm.ask(req.message, context=format_context(chunks))
    except AllProvidersFailed as e:
        raise HTTPException(status_code=503, detail={"error": "all LLM providers failed", "providers": e.errors})
    return ChatResponse(
        answer=resp.text,
        provider=resp.provider,
        model=resp.model,
        sources=[Source(source=c.source, score=round(c.score, 3)) for c in chunks],
        failed_providers=resp.errors,
    )
