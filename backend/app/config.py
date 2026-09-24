"""Runtime settings, read from environment / backend/.env."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    # Azure AI Foundry (OpenAI v1-compatible endpoint), e.g. https://<resource>.openai.azure.com/openai/v1/
    foundry_endpoint: str = os.getenv("AZURE_FOUNDRY_ENDPOINT", "")
    # API key; when empty and an endpoint is set, Entra ID (DefaultAzureCredential) is used
    foundry_api_key: str = os.getenv("AZURE_FOUNDRY_API_KEY", "")
    chat_deployment: str = os.getenv("CHAT_DEPLOYMENT", "gpt-4.1")
    vision_deployment: str = os.getenv("VISION_DEPLOYMENT", "") or os.getenv("CHAT_DEPLOYMENT", "gpt-4.1")
    embedding_deployment: str = os.getenv("EMBEDDING_DEPLOYMENT", "text-embedding-3-large")

    # OpenAI API (platform.openai.com); enabled when OPENAI_API_KEY is set
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_chat_model: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-6-luna")
    openai_vision_model: str = os.getenv("OPENAI_VISION_MODEL", "") or os.getenv("OPENAI_CHAT_MODEL", "gpt-6-luna")
    openai_embedding_model: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    # Swisscom Apertus (OpenAI-compatible, text only, no embeddings); enabled when APERTUS_API_KEY is set
    apertus_api_key: str = os.getenv("APERTUS_API_KEY", "")
    apertus_base_url: str = os.getenv(
        "APERTUS_BASE_URL", "https://api.swisscom.com/products/swiss-ai-weeks/apertus-1.5-70b/v1")
    apertus_model: str = os.getenv("APERTUS_MODEL", "swiss-ai/Apertus-v1.5-70B")

    # Default chat provider: "foundry" (alias "azure"), "openai", "apertus" or "mock".
    # Empty = first configured of foundry, openai, apertus. "mock" disables every provider.
    llm_mode: str = os.getenv("LLM_MODE", "")

    db_path: Path = Path(os.getenv("DB_PATH", str(BACKEND_DIR / "data" / "knowledge.db")))
    training_file: Path = Path(os.getenv("TRAINING_FILE", str(REPO_DIR / "jira_first_20000_requested_fields_synthetic.json")))

    # built frontend (triage-explorer/dist) to serve from "/"; set in the container image
    static_dir: Path | None = Path(os.environ["STATIC_DIR"]) if os.getenv("STATIC_DIR") else None

    top_k: int = int(os.getenv("TOP_K", "6"))
    # cosine similarity a knowledge match must exceed to reach the assistant
    min_knowledge_score: float = float(os.getenv("MIN_KNOWLEDGE_SCORE", "0.4"))
    # cosine similarity above which an open ticket counts as "already reported"
    duplicate_threshold: float = float(os.getenv("DUPLICATE_THRESHOLD", "0.82"))
    max_images: int = int(os.getenv("MAX_IMAGES", "4"))
    max_image_bytes: int = int(os.getenv("MAX_IMAGE_BYTES", str(5 * 1024 * 1024)))


settings = Settings()
