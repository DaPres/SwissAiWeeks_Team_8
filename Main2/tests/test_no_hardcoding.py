"""Challenge rule: 'Do not hardcode answers to the 20 specific challenge tickets'.

The distinctive identifiers and opening phrases of every bundled challenge ticket are derived at run time and must not
appear anywhere in the shipped code, prompts, knowledge base, UI or tests. The eval sets are checked too: they must not
contain copies of the challenge tickets (they are written by hand as independent material).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from triagemate.data import find_challenge_file, read_records

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["triagemate", "prompts", "kb", "scripts", "ui", "tests", "docs", "eval"]
SCAN_SUFFIXES = {".py", ".txt", ".md", ".html", ".js", ".css", ".yaml", ".yml", ".toml", ".json"}
SKIP_NAMES = {"test_no_hardcoding.py", "results.json", "results_offline.json", "results_hybrid.json",
              "validation_first_run_offline.json", "validation_first_run_hybrid.json", "dataset_analysis.json"}


def _needles() -> set[str]:
    f = find_challenge_file()
    if f is None:
        pytest.skip("no bundled challenge file")
    recs, _ = read_records(f)
    needles: set[str] = set()
    for r in recs:
        text = f"{r.get('Summary', '')} {r.get('Description', '')}"
        needles |= set(re.findall(r"\b[A-Z][A-Z0-9_]*[-_][A-Z0-9_]*\d[A-Z0-9_.]*\b", text))     # job / queue / adapter ids
        needles |= {m for m in re.findall(r"\b[\w]+\.(?:txt|csv|xml|json)\b", text)}              # file names
        needles.add(" ".join(str(r.get("Summary", "")).lower().split()))                           # whole title
        needles.add(" ".join(str(r.get("Description", "")).lower().split()[:10]))                  # opening of the description
    return {n for n in needles if len(n) > 8}


def test_no_challenge_ticket_text_in_shipped_files():
    needles = {n.lower() for n in _needles()}
    assert len(needles) >= 20, "needle extraction failed"
    offenders = []
    for d in SCAN_DIRS:
        for p in (ROOT / d).rglob("*"):
            if not p.is_file() or p.suffix not in SCAN_SUFFIXES or p.name in SKIP_NAMES or "__pycache__" in p.parts:
                continue
            text = " ".join(p.read_text(encoding="utf-8", errors="ignore").lower().split())
            offenders += [(str(p.relative_to(ROOT)), n) for n in needles if n in text]
    assert not offenders, f"challenge-ticket text found in shipped files: {offenders[:5]}"


def test_eval_sets_are_independent_of_challenge_tickets():
    needles = {n.lower() for n in _needles()}
    for name in ("stress_set.json", "validation_set.json"):
        text = " ".join(json.dumps(json.loads((ROOT / "eval" / name).read_text(encoding="utf-8")), ensure_ascii=False).lower().split())
        assert not [n for n in needles if n in text], f"{name} contains challenge-ticket text"
