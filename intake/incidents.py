"""Validate sample-compatible incidents and persist them locally."""
from contextlib import closing
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

CATALOG = json.loads((Path(__file__).parent / 'src' / 'catalog.json').read_text())
LEVELS = ['highest', 'high', 'medium', 'low', 'lowest']
MATRIX = [
    ['highest', 'highest', 'high', 'medium', 'medium'],
    ['highest', 'high', 'high', 'medium', 'low'],
    ['high', 'high', 'medium', 'low', 'low'],
    ['medium', 'medium', 'low', 'low', 'lowest'],
    ['medium', 'low', 'low', 'lowest', 'lowest'],
]
DB_PATH = Path(__file__).parent / 'data' / 'incidents.db'


def validate_incident(data):
    if not isinstance(data, dict):
        raise ValueError('An incident must be a JSON object.')
    incident = {'Work type': 'Incident'}
    if data.get('Work type') != 'Incident':
        raise ValueError('Work type must be Incident.')
    for key, limit in [('Summary', 200), ('Description', 10000), ('Reporter', 254), ('Assignee', 254)]:
        value = data.get(key, '')
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f'{key} must be text of at most {limit} characters.')
        value = value.strip()
        if key != 'Assignee' and not value:
            raise ValueError(f'{key} is required.')
        if key in ('Reporter', 'Assignee') and value and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError(f'{key} must be a valid email address.')
        incident[key] = value
    for key, options in CATALOG.items():
        values = data.get(key, [])
        if not isinstance(values, list) or any(not isinstance(v, str) or v not in options for v in values):
            raise ValueError(f'Select valid values for {key}.')
        if key != 'Service Team(s)' and not values:
            raise ValueError(f'{key} is required.')
        incident[key] = list(dict.fromkeys(values))
    for key in ('Urgency', 'Impact'):
        if data.get(key) not in LEVELS:
            raise ValueError(f'{key} must be a valid level.')
        incident[key] = data[key]
    incident['Priority'] = MATRIX[LEVELS.index(incident['Urgency'])][LEVELS.index(incident['Impact'])]
    comments = data.get('All Comments', [])
    if not isinstance(comments, list) or len(comments) > 50 or any(not isinstance(c, str) or len(c) > 5300 for c in comments):
        raise ValueError('Comments must be an array of text entries (maximum 50).')
    incident.update({'Status': 'open', 'Created date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                     'Resolution': None, 'Resolution date': None, 'All Comments': comments})
    return incident


def create_incident(data, db_path=DB_PATH):
    incident = validate_incident(data)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    identifier = f'INC-{uuid4().hex[:12].upper()}'
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        db.execute('INSERT INTO incidents (id, payload) VALUES (?, ?)', (identifier, json.dumps(incident)))
    return {'id': identifier, 'incident': incident}


def create_ready_incident(data, db_path=DB_PATH):
    """Save only the exact draft approved by the current Jev evaluation."""
    from quality import QualityError, normalize_details, suggestion_context
    if not isinstance(data, dict) or not isinstance(data.get('evaluationId'), str):
        raise ValueError('A current readiness evaluation is required.')
    context = suggestion_context(data['evaluationId'])
    description = data.get('description')
    details = normalize_details(data.get('details', {}))
    if not isinstance(description, str) or description.strip() != context['description'] or details != context['details']:
        raise QualityError('The draft changed. Wait for a fresh readiness check.', 409)
    if context['evaluation'].get('readiness', 0) < 80:
        raise QualityError('Reach 80% readiness before submitting.', 422)
    # Unknown fields stay absent: an actionable description need not have manual routing labels.
    incident = {'Work type': 'Incident', 'Description': description.strip(), 'Status': 'open',
                'Created date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'Resolution': None, 'Resolution date': None, 'All Comments': []}
    if details:
        labels = {'department': 'Responsible team', 'service': 'Affected service', 'impact': 'Impact',
                  'context': 'Timing and context', 'evidence': 'Diagnostic evidence'}
        incident['All Comments'] = [f'{labels.get(key, key.title())}: {value}' for key, value in details.items()]
    fields = {**context['evaluation'].get('inferred', {}), **details}
    for key, target in {'summary': 'Summary', 'reporter': 'Reporter', 'assignee': 'Assignee', 'urgency': 'Urgency', 'impact': 'Impact'}.items():
        if fields.get(key) and (key not in ('urgency', 'impact') or fields[key] in LEVELS):
            incident[target] = fields[key]
    for key, target in {'department': 'Service Team(s)', 'service': 'Affected Business or IT Services', 'entity': 'Business Entity'}.items():
        if fields.get(key):
            incident[target] = [fields[key]]
    if fields.get('impact') in LEVELS and fields.get('urgency') in LEVELS:
        incident['Priority'] = MATRIX[LEVELS.index(fields['urgency'])][LEVELS.index(fields['impact'])]
    identifier = f'INC-{uuid4().hex[:12].upper()}'
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        db.execute('INSERT INTO incidents (id, payload) VALUES (?, ?)', (identifier, json.dumps(incident)))
    return {'id': identifier, 'incident': incident}
