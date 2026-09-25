"""Read-only, offline preview of an Intake draft through the sibling TriageMate core."""

from functools import lru_cache
from pathlib import Path
import sys

from quality import normalize_details


CORE_DIR = Path(__file__).resolve().parent.parent / 'Main2'
if not CORE_DIR.is_dir():
    CORE_DIR = Path(__file__).resolve().parent.parent / 'main2'


def prepare_incident(data):
    if not isinstance(data, dict):
        raise ValueError('An incident draft is required.')
    description = data.get('description')
    if not isinstance(description, str) or not 3 <= len(description.strip()) <= 10000:
        raise ValueError('Description must contain between 3 and 10000 characters.')
    details = normalize_details(data.get('details', {}))
    incident = {'description': description.strip()}
    for field in ('summary', 'service', 'entity', 'reporter', 'urgency', 'impact'):
        if field in details:
            incident[field] = details[field]
    comments = [f'{label}: {details[field]}' for field, label in (
        ('department', 'Selected team'), ('assignee', 'Selected assignee'),
        ('context', 'Context'), ('evidence', 'Evidence')) if field in details]
    if comments:
        incident['comments'] = comments
    return incident


@lru_cache(maxsize=1)
def offline_triage():
    if not CORE_DIR.is_dir():
        raise FileNotFoundError('The Main2 TriageMate folder is missing.')
    if str(CORE_DIR) not in sys.path:
        sys.path.insert(0, str(CORE_DIR))
    from triagemate.data import load_training
    from triagemate.pipeline import Triage
    from triagemate.retrieve import LsaEmbedder, Retriever

    return Triage(retriever=Retriever(load_training(), embedder=LsaEmbedder()), use_llm=False)


def preview_incident(data):
    incident = prepare_incident(data)
    triage = offline_triage()
    from triagemate.intake import enrich_incident

    return enrich_incident(incident, use_llm=False, commit_assign=False, triage=triage).to_json()
