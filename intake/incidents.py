"""Validate sample-compatible incidents and persist them locally."""
from contextlib import closing
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from incident_fields import ASSIGNEES, CHIP_OPTIONS, LEVELS, MATRIX, RESOLUTIONS, calculate_priority

CATALOG = json.loads((Path(__file__).parent / 'src' / 'catalog.json').read_text())
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


REQUIRED_CHIPS = CHIP_OPTIONS
HANDOFF_OPTIONS = REQUIRED_CHIPS


class IncidentError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def validate_handoff(data):
    """Validate the submitted draft independently of advisory Jev evaluations."""
    from quality import QualityError, normalize_details

    if not isinstance(data, dict):
        raise ValueError('An incident draft is required.')
    description = data.get('description')
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 10000:
        raise QualityError('Provide a description of at most 10000 characters.', 422)
    details = normalize_details(data.get('details', {}))
    selected = data.get('selected')
    if not isinstance(selected, dict) or set(selected) != set(HANDOFF_OPTIONS):
        raise ValueError('The five selected incident fields are required.')
    for key, (label, choices) in HANDOFF_OPTIONS.items():
        value = selected[key]
        if not isinstance(value, str) or value not in choices:
            raise QualityError('Please complete the incident details.', 422)
        if key in details and value != details[key]:
            raise QualityError('The selected fields must match your manual choices.', 422)

    account = data.get('account', 'client')
    if account != 'client' and account not in CATALOG['Service Team(s)']:
        raise ValueError('Choose a valid demo account.')
    return {'description': description.strip(), 'fields': {**details, **selected},
            'manual': details, 'account': account}


def new_incident_id():
    return f'INC-{uuid4().hex[:12].upper()}'


def save_processed_incident(draft, enriched, identifier, db_path=DB_PATH):
    """Persist the core's corrected fields and both optional resolution proposals."""
    if not isinstance(enriched, dict) or enriched.get('id') != identifier:
        raise ValueError('The neural engine returned an invalid incident.')
    fields = draft['fields']
    account = draft['account']
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    manual = draft['manual']
    work_type = manual.get('workType') or enriched.get('workType') or fields.get('workType') or 'Incident'
    service = manual.get('service') or enriched.get('service') or fields.get('service')
    if service not in CATALOG['Affected Business or IT Services']:
        raise ValueError('The neural engine returned an invalid service.')
    team = manual.get('department') or enriched.get('team') or fields['department']
    entity = manual.get('entity') or enriched.get('entity') or fields.get('entity')
    assignee = manual.get('assignee') or enriched.get('assignee') or fields.get('assignee', '')
    if assignee not in ASSIGNEES:
        assignee = fields.get('assignee', '')
    urgency = manual.get('urgency') or enriched.get('urgency') or fields['urgency']
    impact = manual.get('impact') or enriched.get('impact') or fields['impact']
    priority = calculate_priority(urgency, impact)
    if not priority:
        raise ValueError('The neural engine returned invalid priority inputs.')
    resolution = manual.get('resolution') or enriched.get('resolutionStatus') or fields.get('resolution', 'clarification')
    if resolution not in RESOLUTIONS:
        raise ValueError('The neural engine returned an invalid resolution.')
    expert = enriched.get('expertResolution') or {}
    note = manual.get('resolutionComment') or expert.get('note') or fields.get('resolutionComment', '')
    author = assignee or team
    comment = note if note.startswith(author + ':') else f'{author}: {note}'
    enriched = {**enriched, 'workType': work_type, 'service': service, 'team': team, 'entity': entity, 'assignee': assignee, 'urgency': urgency, 'impact': impact,
                'priority': priority, 'resolutionStatus': resolution}
    if expert:
        enriched['expertResolution'] = {**expert, 'note': note, 'jiraComment': comment, 'assignee': assignee, 'team': team}
    reporter = fields.get('reporter') or (f"{re.sub(r'[^a-z0-9]+', '.', account.lower()).strip('.')}@intake.local")
    incident = {
        'Work type': work_type,
        'Summary': enriched.get('summary') or draft['description'][:90],
        'Description': enriched.get('description') or draft['description'],
        'Affected Business or IT Services': [service],
        'Service Team(s)': [team],
        'Business Entity': [entity] if entity else [],
        'Reporter': reporter,
        'Assignee': assignee,
        'Urgency': urgency,
        'Impact': impact,
        'Priority': priority,
        'Status': 'awaiting client' if enriched.get('clientResolution') else 'open',
        'Created date': now,
        'Resolution': resolution,
        'Resolution date': None,
        'All Comments': [f'{key.title()}: {value}' for key, value in draft['manual'].items()
                         if key in ('context', 'evidence')] + ([comment] if note else []),
        'Submitted account': account,
    }
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS incident_enrichment (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        db.execute('INSERT INTO incidents (id, payload) VALUES (?, ?)', (identifier, json.dumps(incident)))
        db.execute('INSERT INTO incident_enrichment (id, payload) VALUES (?, ?)', (identifier, json.dumps(enriched)))
    return {'id': identifier, 'incident': incident, 'enriched': enriched}


def list_incidents(account='client', db_path=DB_PATH):
    if account != 'client' and account not in CATALOG['Service Team(s)']:
        raise ValueError('Choose a valid demo account.')
    if not db_path.exists():
        return []
    with closing(sqlite3.connect(db_path)) as db:
        has_enrichment = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='incident_enrichment'").fetchone()
        if has_enrichment:
            rows = db.execute('SELECT i.id, i.payload, e.payload FROM incidents i LEFT JOIN incident_enrichment e ON e.id=i.id ORDER BY i.rowid DESC').fetchall()
        else:
            rows = [(identifier, payload, None) for identifier, payload in
                    db.execute('SELECT id, payload FROM incidents ORDER BY rowid DESC').fetchall()]
    records = [{'id': identifier, 'incident': json.loads(payload),
                'enriched': json.loads(enrichment) if enrichment else None}
               for identifier, payload, enrichment in rows]
    if account == 'client':
        return [record for record in records if record['incident'].get('Submitted account', 'client') == 'client']
    return [record for record in records if account in record['incident'].get('Service Team(s)', [])
            and record['incident'].get('Status') != 'awaiting client']


def decide_incident(identifier, decision, account, db_path=DB_PATH):
    if not re.fullmatch(r'INC-[A-Z0-9]{12}', identifier):
        raise ValueError('Invalid incident ID.')
    if decision not in ('resolved', 'handoff'):
        raise ValueError('Choose resolved or handoff.')
    if not db_path.exists():
        raise IncidentError('Incident not found.', 404)
    with closing(sqlite3.connect(db_path)) as db, db:
        row = db.execute('SELECT payload FROM incidents WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise IncidentError('Incident not found.', 404)
        incident = json.loads(row[0])
        if incident.get('Submitted account') != account:
            raise IncidentError('This incident belongs to another demo account.', 403)
        if incident.get('Status') != 'awaiting client':
            raise IncidentError('This incident has already been decided.', 409)
        if decision == 'resolved':
            incident.update({'Status': 'done', 'Resolution': 'done',
                             'Resolution date': datetime.now().strftime('%Y-%m-%d %H:%M')})
        else:
            incident['Status'] = 'open'
        db.execute('UPDATE incidents SET payload=? WHERE id=?', (json.dumps(incident), identifier))
        row = db.execute('SELECT payload FROM incident_enrichment WHERE id=?', (identifier,)).fetchone()
    return {'id': identifier, 'incident': incident, 'enriched': json.loads(row[0]) if row else None}
