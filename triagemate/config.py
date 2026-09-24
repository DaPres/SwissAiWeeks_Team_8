"""Runtime configuration. Everything is overridable through environment variables / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    # --- LLM provider (OpenAI-compatible; the provider is a config value, never a code path) ---
    llm_provider: str = "none"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4.1-mini"
    llm_model_classify: str = ""
    llm_model_draft: str = ""
    llm_timeout: float = 45.0
    llm_max_retries: int = 2

    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str = ""

    embed_base_url: str = ""
    embed_api_key: str = ""
    embed_model: str = "text-embedding-3-small"

    price_in_per_1m: float = 0.40
    price_out_per_1m: float = 1.60

    triage_offline: bool = False
    confidence_floor: float = Field(default=0.60, ge=0.0, le=1.0)
    db_path: str = "outputs/triagemate.db"
    enable_business_overrides: bool = False   # PDF Sec. 6.5 examples, pending expert confirmation; README definitions win
    arbitration: str = "llm_first"          # llm_first | rules_first

    # --- paths ---
    data_dir: Path = ROOT / "data"
    kb_dir: Path = ROOT / "kb"
    prompts_dir: Path = ROOT / "prompts"
    outputs_dir: Path = ROOT / "outputs"

    @property
    def llm_enabled(self) -> bool:
        if self.triage_offline or self.llm_provider.lower() == "none":
            return False
        if self.llm_provider.lower() == "local":
            return bool(self.llm_base_url)
        return bool(self.llm_api_key)

    @property
    def classify_model(self) -> str:
        return self.llm_model_classify or self.llm_model

    @property
    def draft_model(self) -> str:
        return self.llm_model_draft or self.llm_model

    @property
    def db_file(self) -> Path:
        p = Path(self.db_path)
        return p if p.is_absolute() else ROOT / p


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    """Test helper: drop the cached settings so a changed environment is re-read."""
    get_settings.cache_clear()
