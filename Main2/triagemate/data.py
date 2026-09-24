"""Loading and normalising tickets from either schema.

Schema A (training):  a JSON list of flat dicts (16 fields, lower-case severity values).
Schema B (Jira export / blind eval): ``{"records": [...], ...}`` with extra fields
(Request type, Business Critical for Entity, Severity, Linked issues, Due date) and Title-Case values.
Both are normalised to :class:`triagemate.models.Ticket`; the original dict is kept in ``raw``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

from .config import get_settings
from .models import Ticket

DATASET_NAME = "jira_first_20000_requested_fields_synthetic.json"


def _as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if x not in (None, "")]
    return [str(v)] if str(v) else []


def _lower(v: Optional[str]) -> Optional[str]:
    return v.strip().lower() if isinstance(v, str) and v.strip() else None


def ticket_from_record(rec: dict, idx: int, prefix: str, source: str) -> Ticket:
    tid = rec.get("Key") or rec.get("Issue key") or rec.get("id") or f"{prefix}-{idx + 1:05d}"
    return Ticket(
        id=str(tid),
        work_type=rec.get("Work type"),
        request_type=rec.get("Request type"),
        summary=rec.get("Summary") or "",
        description=rec.get("Description") or "",
        services=_as_list(rec.get("Affected Business or IT Services")),
        entities=_as_list(rec.get("Business Entity")),
        teams=_as_list(rec.get("Service Team(s)")),
        reporter=rec.get("Reporter"),
        assignee=rec.get("Assignee"),
        priority=_lower(rec.get("Priority")),
        urgency=_lower(rec.get("Urgency")),
        impact=_lower(rec.get("Impact")),
        severity=_lower(rec.get("Severity")),
        created=rec.get("Created date"),
        status=rec.get("Status"),
        resolution=_lower(rec.get("Resolution")),
        resolution_date=rec.get("Resolution date"),
        due_date=rec.get("Due date"),
        linked_issues=_as_list(rec.get("Linked issues")),
        comments=_as_list(rec.get("All Comments")),
        source=source,
        raw=rec,
    )


def read_records(path: str | Path) -> tuple[list[dict], dict]:
    """Return (records, envelope-metadata). Accepts a list, an envelope with ``records``, or JSONL."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()], {}
    data = json.loads(text)
    if isinstance(data, list):
        return data, {}
    if isinstance(data, dict):
        for key in ("records", "issues", "tickets", "data"):
            if isinstance(data.get(key), list):
                meta = {k: v for k, v in data.items() if k != key}
                return data[key], meta
        return [data], {}
    raise ValueError(f"Unsupported ticket file layout: {p}")


def is_envelope(path: str | Path) -> bool:
    """True when the file is an object wrapping the records (Jira export), False for a bare list / JSONL."""
    p = Path(path)
    if p.suffix.lower() == ".jsonl":
        return False
    return isinstance(json.loads(p.read_text(encoding="utf-8")), dict)


def load_tickets(path: str | Path, prefix: str = "T", source: str = "jira") -> list[Ticket]:
    recs, _ = read_records(path)
    return [ticket_from_record(r, i, prefix, source) for i, r in enumerate(recs)]


def load_training(path: str | Path | None = None) -> list[Ticket]:
    p = Path(path) if path else get_settings().data_dir / DATASET_NAME
    return load_tickets(p, prefix="TRN", source="training")


def find_challenge_file(data_dir: str | Path | None = None) -> Optional[Path]:
    """The README names ``jira_hackathon_20_new_tickets_challenge.json``; the repo ships a
    ``jira_hackathon_blind_eval_challenge_<ts>.json``. Accept either (newest wins)."""
    d = Path(data_dir) if data_dir else get_settings().data_dir
    cands = sorted(d.glob("jira_hackathon*challenge*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if cands else None


def iter_all_text(tickets: Iterable[Ticket]):
    for t in tickets:
        yield t.text
