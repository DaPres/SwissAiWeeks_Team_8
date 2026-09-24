"""Runtime configuration. Everything is overridable through environment variables / .env.

Provider model (Sec. 4.11): every provider is a *profile* (key, base URL, model). Keep all your keys in .env at once and pick
which one is used with LLM_PROVIDER; optionally use different providers per role (e.g. OpenAI for classification, Apertus for
drafting) with CLASSIFY_PROVIDER / DRAFT_PROVIDER.  Legacy LLM_API_KEY / LLM_BASE_URL / LLM_MODEL still work for the default provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent

PROVIDERS = ("openai", "apertus", "azure", "anthropic", "local")
_PLACEHOLDER_HINTS = ("PASTE", "your ", "YOUR_", "xxxx", "<")


def _real(v: str) -> str:
    """A key still holding placeholder text counts as 'not set' so the system quietly stays offline."""
    v = (v or "").strip()
    return "" if (not v or any(h in v for h in _PLACEHOLDER_HINTS)) else v


@dataclass(frozen=True)
class Profile:
    provider: str
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    rps: float = 0.0                 # client-side request throttle (0 = unlimited)
    azure_endpoint: str = ""
    azure_deployment: str = ""
    azure_api_version: str = ""

    @property
    def enabled(self) -> bool:
        if self.provider == "local":
            return bool(self.base_url)
        if self.provider == "azure":
            return bool(self.api_key and self.azure_endpoint)
        if self.provider in ("openai", "apertus", "anthropic"):
            return bool(self.api_key)
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    # --- which provider(s) ---
    llm_provider: str = "none"               # default: openai | apertus | azure | anthropic | local | none
    classify_provider: str = ""              # optional per-role override (blank = default)
    draft_provider: str = ""

    # --- legacy generic fields (apply to the default provider when the specific ones are empty) ---
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_model_classify: str = ""             # optional per-role model override
    llm_model_draft: str = ""
    llm_timeout: float = 45.0
    llm_max_retries: int = 2

    # --- per-provider profiles ---
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"

    apertus_api_key: str = ""
    apertus_base_url: str = "https://api.swisscom.com/products/swiss-ai-weeks/apertus-1.5-70b/v1"
    apertus_model: str = "swiss-ai/Apertus-v1.5-70B"
    apertus_rps: float = 4.0                 # Swisscom limit is 5 requests/s

    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-10-21"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"

    local_base_url: str = "http://localhost:11434/v1"
    local_model: str = ""

    # --- embeddings (optional; Apertus has no embeddings endpoint, so OpenAI is the usual choice) ---
    embed_provider: str = ""                 # blank = openai if its key is set, else the default provider when it can embed
    embed_base_url: str = ""
    embed_api_key: str = ""
    embed_model: str = "text-embedding-3-small"

    price_in_per_1m: float = 0.40
    price_out_per_1m: float = 1.60

    triage_offline: bool = False
    confidence_floor: float = Field(default=0.60, ge=0.0, le=1.0)
    db_path: str = "outputs/triagemate.db"
    enable_business_overrides: bool = False   # PDF Sec. 6.5 examples, pending expert confirmation; README definitions win
    arbitration: str = "llm_first"           # llm_first | rules_first
    agent_mode: str = "llm"                  # llm = model picks the tools; policy = deterministic plan (fastest)
    batch_workers: int = 4                   # tickets processed concurrently in a batch when an LLM is on
    urgency_samples: int = 1                 # optional self-consistency: N parallel urgency/impact ratings, per-dimension median
    decision_cache: bool = True              # content-addressed cache: same text+model+prompt => same urgency/impact (idempotent re-triage)

    # --- paths ---
    data_dir: Path = ROOT / "data"
    kb_dir: Path = ROOT / "kb"
    prompts_dir: Path = ROOT / "prompts"
    outputs_dir: Path = ROOT / "outputs"

    # ------------------------------------------------------------------ provider resolution
    def profile(self, provider: str | None = None) -> Profile:
        p = (provider or self.llm_provider or "none").lower()
        default = p == self.llm_provider.lower()

        def pick(specific: str, generic: str) -> str:
            g = _real(generic) if default else ""
            return g or _real(specific)

        if p == "openai":
            return Profile(p, pick(self.openai_api_key, self.llm_api_key), (self.llm_base_url if default and self.llm_base_url else self.openai_base_url),
                           (self.llm_model if default and self.llm_model else self.openai_model))
        if p == "apertus":
            return Profile(p, pick(self.apertus_api_key, self.llm_api_key), (self.llm_base_url if default and self.llm_base_url else self.apertus_base_url),
                           (self.llm_model if default and self.llm_model else self.apertus_model), rps=self.apertus_rps)
        if p == "azure":
            return Profile(p, pick(self.azure_openai_api_key, self.llm_api_key), "", (self.llm_model if default and self.llm_model else self.azure_openai_deployment),
                           azure_endpoint=self.azure_openai_endpoint, azure_deployment=self.azure_openai_deployment or (self.llm_model if default else ""),
                           azure_api_version=self.azure_openai_api_version)
        if p == "anthropic":
            return Profile(p, pick(self.anthropic_api_key, self.llm_api_key), self.llm_base_url if default else "",
                           (self.llm_model if default and self.llm_model else self.anthropic_model))
        if p == "local":
            return Profile(p, "", (self.llm_base_url if default and self.llm_base_url else self.local_base_url),
                           (self.llm_model if default and self.llm_model else self.local_model))
        return Profile("none")

    def role_provider(self, role: str) -> str:
        override = {"classify": self.classify_provider, "draft": self.draft_provider}.get(role, "")
        return (override or self.llm_provider or "none").lower()

    def model_for(self, role: str) -> str:
        override = {"classify": self.llm_model_classify, "draft": self.llm_model_draft}.get(role, "")
        return override or self.profile(self.role_provider(role)).model

    def embed_profile(self) -> Profile | None:
        """Where embeddings come from, or None (-> local TF-IDF/LSA model)."""
        if self.triage_offline:
            return None
        key = _real(self.embed_api_key)
        if self.embed_base_url and (key or _real(self.openai_api_key)):
            return Profile("openai", key or _real(self.openai_api_key), self.embed_base_url, self.embed_model)
        prov = (self.embed_provider or "").lower()
        if not prov:
            prov = "openai" if self.profile("openai").enabled else self.llm_provider.lower()
        if prov in ("openai", "azure", "local"):
            pf = self.profile(prov)
            if pf.enabled:
                return Profile(pf.provider, key or pf.api_key, pf.base_url, self.embed_model, azure_endpoint=pf.azure_endpoint,
                               azure_api_version=pf.azure_api_version)
        return None

    # ------------------------------------------------------------------ convenience
    @property
    def llm_enabled(self) -> bool:
        if self.triage_offline:
            return False
        return any(self.profile(self.role_provider(r)).enabled for r in ("classify", "draft"))

    @property
    def classify_model(self) -> str:
        return self.model_for("classify")

    @property
    def draft_model(self) -> str:
        return self.model_for("draft")

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
