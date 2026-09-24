"""Repo hygiene (plan Sec. 15.3): `.env` absent from git, `.env.example` present and empty, no key-shaped strings in tracked files."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY_SHAPES = re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}|sk-ant-[A-Za-z0-9_\-]{20,}|AKIA[0-9A-Z]{16}")


def _candidate_files() -> list[Path]:
    """Every file git would commit: tracked + untracked-but-not-ignored."""
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, timeout=30)
        names = [n for n in out.stdout.splitlines() if n.strip()]
    except Exception:
        names = []
    return [ROOT / n for n in names if (ROOT / n).is_file() and (ROOT / n).stat().st_size < 5_000_000]


def test_dotenv_is_git_ignored():
    files = {str(p.relative_to(ROOT)).replace("\\", "/") for p in _candidate_files()}
    assert ".env" not in files, ".env must never be committed"


def test_env_example_exists_and_has_no_secret_values():
    ex = ROOT / ".env.example"
    assert ex.exists()
    for line in ex.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Z_]*(?:API_KEY|TOKEN|SECRET))=(.*)$", line.strip())
        if m:
            assert m.group(2).strip() == "", f"{m.group(1)} in .env.example must be empty"


def test_no_key_shaped_strings_or_real_env_values_in_committable_files():
    real_values = []
    env = ROOT / ".env"
    if env.exists():
        real_values = [m.group(1).strip() for m in re.finditer(r"(?m)^[A-Z_]*(?:API_KEY|TOKEN|SECRET)=(.+)$", env.read_text(encoding="utf-8")) if len(m.group(1).strip()) >= 8]
    for f in _candidate_files():
        if f.suffix.lower() in (".json", ".md", ".py", ".txt", ".html", ".example", ".yml", ".yaml", ".csv", "") or f.name == "Makefile":
            text = f.read_text(encoding="utf-8", errors="ignore")
            assert not KEY_SHAPES.search(text), f"key-shaped string in {f.relative_to(ROOT)}"
            for v in real_values:
                assert v not in text, f"a real secret from .env appears in {f.relative_to(ROOT)}"
