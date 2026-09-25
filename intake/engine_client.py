"""HTTP client for the shared triage backend discovered by Aspire."""
import copy
import json
import os
from collections import OrderedDict
from threading import Lock
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from quality import normalize_details
from incident_fields import ASSIGNEES, RESOLUTIONS, calculate_priority


class EngineError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


_cache = OrderedDict()
_cache_lock = Lock()


def prepare_incident(data):
    if not isinstance(data, dict):
        raise ValueError('An incident draft is required.')
    description = data.get('description')
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 10000:
        raise ValueError('Description must contain between 1 and 10000 characters.')
    details = normalize_details(data.get('details', {}))
    # Proposed resolutions must not become evidence in the next analysis.
    details = {key: value for key, value in details.items() if key not in ('resolution', 'resolutionComment')}
    return {'description': description.strip(), 'details': details}


def preview_incident(data, identifier=None):
    payload = prepare_incident(data)
    base = (os.environ.get('TRIAGE_BACKEND_URL') or os.environ.get('services__backend__http__0') or '').rstrip('/')
    if not base:
        raise EngineError('The shared backend is not configured. Start Intake through Aspire.')
    key = (base, json.dumps(payload, sort_keys=True))
    with _cache_lock:
        cached = _cache.get(key)
        result = copy.deepcopy(cached[1]) if cached and cached[0] > monotonic() else None
    if result is None:
        request = Request(base + '/api/intake/enrich', data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=90) as response:
                result = json.load(response)
        except HTTPError as error:
            raise EngineError('The shared backend could not finish the review. Please retry.', 502) from error
        except (URLError, TimeoutError, OSError) as error:
            raise EngineError('The shared backend is unavailable. Check Aspire and retry.') from error
        except (ValueError, UnicodeDecodeError) as error:
            raise EngineError('The shared backend returned an invalid response.', 502) from error
        if not isinstance(result, dict) or not result.get('service') or not result.get('team'):
            raise EngineError('The shared backend returned an incomplete response.', 502)
        with _cache_lock:
            _cache[key] = (monotonic() + 300, copy.deepcopy(result))
            while len(_cache) > 64:
                _cache.popitem(last=False)
    if identifier is not None:
        result['id'] = identifier
    return result


def complete_draft_fields(description, fields):
    preview = preview_incident({'description': description, 'details': fields})
    expert = preview.get('expertResolution') or {}
    completion = {}
    for key, source in [('workType', 'workType'), ('service', 'service'), ('department', 'team'),
                        ('urgency', 'urgency'), ('impact', 'impact')]:
        if preview.get(source):
            completion[key] = preview[source]
    assignee = fields.get('assignee') or preview.get('assignee')
    if assignee in ASSIGNEES:
        completion['assignee'] = assignee
    if preview.get('resolutionStatus') in RESOLUTIONS:
        completion['resolution'] = preview['resolutionStatus']
    note = expert.get('note') or (preview.get('clarification') or {}).get('message')
    if note:
        completion['resolutionComment'] = note[:2000]
    merged = {**completion, **fields}
    if priority := calculate_priority(merged.get('urgency'), merged.get('impact')):
        completion['priority'] = priority
    return {'fields': completion, 'sources': expert.get('similarPast', [])}
