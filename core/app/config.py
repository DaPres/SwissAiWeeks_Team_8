"""Central place for paths and .env loading. Nothing secret is hardcoded here."""

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
DOCS_DIR = PROJECT_ROOT / "data" / "sample_docs"
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"


def load_env(override: bool = False) -> None:
    """Load .env from the project root. override=True re-reads freshly pasted keys."""
    load_dotenv(ENV_FILE, override=override)
