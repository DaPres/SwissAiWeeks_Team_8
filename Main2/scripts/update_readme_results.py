"""Copies the latest evaluation tables into README.md between the RESULTS markers, so quoted numbers always come from eval/*.md.

    python scripts/update_readme_results.py                 # hybrid (if present) + offline
    python scripts/update_readme_results.py --offline-only
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


def _body(p: Path, heading: str) -> str:
    text = p.read_text(encoding="utf-8")
    text = re.sub(r"^# Results.*?\n", "", text, count=1)
    text = re.sub(r"(?m)^## ", "#### ", text)
    return f"### {heading}\n\n" + text.strip() + "\n"


def main() -> None:
    parts = []
    hyb, off = ROOT / "eval" / "RESULTS_hybrid.md", ROOT / "eval" / "RESULTS_offline.md"
    if hyb.exists() and "--offline-only" not in sys.argv:
        parts.append(_body(hyb, "With an LLM (hybrid mode: rules + model, arbitrated)"))
    if off.exists():
        parts.append(_body(off, "Offline (deterministic rules only, no key needed)"))
    if not parts:
        raise SystemExit("run `python -m triagemate.cli eval` first")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    new = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda m: START + "\n" + "\n".join(parts) + "\n" + END, readme, flags=re.S)
    (ROOT / "README.md").write_text(new, encoding="utf-8")
    print("README results updated from", [p.name for p in (hyb, off) if p.exists()])


if __name__ == "__main__":
    main()
