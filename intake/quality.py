"""Server-side Jev description evaluation; credentials never reach the browser."""
import json
import math
import os
from collections import OrderedDict
from threading import Lock
from time import monotonic
from uuid import uuid4
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from jev_prompt import REFERENCE_FIELDS, inference_questions, normalized_choice

# Aspire injects settings; standalone runs share the main backend environment.
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / 'backend' / '.env')
load_dotenv(Path(__file__).parent / '.env')

CRITERIA = {
    'department': 'Is there enough concrete information to confidently identify the responsible functional department or support team (for example valuation, securities operations, trading support, enterprise applications), without guessing?',
    'service': 'Is there enough concrete information to identify the affected business or IT service and understand what is failing versus the expected behavior?',
    'impact': 'Is there enough information to assess operational impact, affected users or entities, and urgency?',
    'context': 'Is there enough timing or triggering context to begin investigation, such as when it started, frequency, environment, or reproduction steps?',
    'evidence': 'Is there actionable diagnostic evidence for a specialist to start resolving the issue, such as a specific symptom, error, failed job, or troubleshooting result?',
}
CATALOG = json.loads((Path(__file__).parent / 'src' / 'catalog.json').read_text())
ENRICHMENT_OPTIONS = {
    'department': CATALOG['Service Team(s)'], 'service': CATALOG['Affected Business or IT Services'],
    'entity': CATALOG['Business Entity'], 'urgency': ['lowest', 'low', 'medium', 'high', 'highest'],
    'impact': ['lowest', 'low', 'medium', 'high', 'highest'],
    'priority': ['lowest', 'low', 'medium', 'high', 'highest'], 'workType': ['Incident', 'Service Request'],
}
DETAIL_FIELDS = {'summary', 'reporter', 'assignee', 'entity', 'urgency', 'service', 'department', 'impact', 'context', 'evidence', 'priority', 'workType', 'resolution', 'resolutionComment'}


def highest_probability_choice(answer):
    if not isinstance(answer, dict):
        return None
    probabilities = answer.get('probabilities')
    if not isinstance(probabilities, dict) or not probabilities:
        return None
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not math.isfinite(value) or not 0 <= value <= 1 for value in probabilities.values()):
        return None
    maximum = max(probabilities.values())
    if maximum <= 0:
        return None
    winners = [choice for choice, probability in probabilities.items() if probability == maximum]
    # An unclear winner (including a tie) must never turn into an invented selection.
    if any(choice.lower() in ('unclear', 'unknown') for choice in winners):
        return None
    return winners[0]


def parse_enrichment(response):
    inferred = {}
    answers = response.get('answers', {}) if isinstance(response, dict) else {}
    if not isinstance(answers, dict):
        return inferred
    for field, name in REFERENCE_FIELDS.items():
        choice = normalized_choice(field, highest_probability_choice(answers.get(name)))
        if choice in ENRICHMENT_OPTIONS[field]:
            inferred[field] = choice
    return inferred


def normalize_details(details):
    if not isinstance(details, dict) or set(details) - DETAIL_FIELDS:
        raise ValueError('Additional details must use the supported fields.')
    cleaned = {}
    for key, value in details.items():
        if not isinstance(value, str) or len(value) > 2000:
            raise ValueError('Each additional detail must be text of at most 2000 characters.')
        if value.strip():
            cleaned[key] = value.strip()
    return cleaned



class QualityError(Exception):
    def __init__(self, message, status=502, debug=None):
        super().__init__(message)
        self.status = status
        self.debug = debug


def build_jev_payload(description, details):
    model, questions = inference_questions()
    return {
        'model': os.getenv('JEV_MODEL', model),
        'state': {'description': description.strip(), **({'additional_details': details} if details else {})},
        'questions': questions,
    }


def parse_answers(response):
    try:
        answers = response['answers']
        results = []
        for key in CRITERIA:
            value = answers.get('quality_' + key, answers.get(key, {}))['noul']
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('Invalid probability')
            results.append({'id': key, 'probability': value,
                            'status': 'met' if value >= 0.7 else 'missing' if value <= 0.3 else 'uncertain'})
        return {'criteria': results, 'met': sum(item['status'] == 'met' for item in results), 'total': 5,
                'readiness': math.floor(sum(item['probability'] for item in results) / len(results) * 100)}
    except (KeyError, TypeError, ValueError, AttributeError):
        raise QualityError('Jev returned an incomplete evaluation. Please try again.') from None


def evaluate_description(data):
    description = data.get('description') if isinstance(data, dict) else None
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 10000:
        raise ValueError('Description must contain between 1 and 10000 characters.')
    details = normalize_details(data.get('details', {}))
    api_key = os.getenv('JEV_API_KEY', '')
    if not api_key:
        raise QualityError('Description checking is not configured. Add JEV_API_KEY to the server environment.', 503)
    payload = build_jev_payload(description, details)
    url = 'https://api.typesafe.ai/v1/systemone'
    request = Request(url, data=json.dumps(payload).encode(),
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        method='POST',
    )
    debug = {'request': {'method': 'POST', 'url': url,
                         'headers': {'Content-Type': 'application/json', 'Authorization': 'Bearer [redacted]'},
                         'body': payload}, 'response': None}
    started = monotonic()

    def trace():
        debug['durationMs'] = round((monotonic() - started) * 1000)
        # Only the redacted exchange is returned to the browser, including on upstream failures.
        return json.loads(json.dumps(debug).replace(api_key, '[redacted]'))

    def fail(message, status=502, upstream_status=None):
        debug['response'] = {'status': upstream_status, 'body': {'error': message}}
        return QualityError(message, status, trace())

    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
            debug['response'] = {'status': getattr(response, 'status', 200), 'body': result}
    except HTTPError as error:
        if error.code in (401, 403):
            raise fail('Jev authentication failed. Check the server API key.', 503, error.code) from None
        if error.code == 429:
            raise fail('Jev is rate limited. Wait a moment and try again.', 429, error.code) from None
        raise fail('Jev is temporarily unavailable. Please try again.', upstream_status=error.code) from None
    except (URLError, TimeoutError, OSError):
        raise fail('Could not reach Jev. Please try again.') from None
    except (ValueError, UnicodeDecodeError):
        raise fail('Jev returned an invalid response. Please try again.') from None
    if not isinstance(result, dict) or not isinstance(result.get('answers'), dict) or any(
            name not in result['answers'] for name in REFERENCE_FIELDS.values()):
        raise QualityError('Jev returned an incomplete evaluation. Please try again.', debug=trace())
    inferred = parse_enrichment(result)
    fields = {**inferred, **details}
    evaluation = {'inferred': inferred, 'unresolvedFields': [field for field in REFERENCE_FIELDS if not fields.get(field)]}
    return {**remember_evaluation(description.strip(), evaluation, details), 'debug': trace()}


def complete_evaluation(data, complete_fields):
    identifier = data.get('evaluationId') if isinstance(data, dict) else None
    if not isinstance(identifier, str) or len(identifier) != 32:
        raise ValueError('A current evaluation is required for historical suggestions.')
    context = suggestion_context(identifier)
    fields = {**context['evaluation'].get('inferred', {}), **context['details']}
    if fields.get('service') not in CATALOG['Affected Business or IT Services']:
        raise ValueError('Choose an affected service before looking up resolutions.')
    completion = complete_fields(context['description'], fields)
    evaluation = {**context['evaluation'],
                  'inferred': {**context['evaluation'].get('inferred', {}), **completion['fields']},
                  'resolutionSources': completion.get('sources', [])}
    return remember_evaluation(context['description'], evaluation, context['details'])


_evaluations = OrderedDict()
_evaluations_lock = Lock()


def remember_evaluation(description, evaluation, details=None):
    identifier = uuid4().hex
    needs_suggestion = bool(evaluation.get('unresolvedFields'))
    with _evaluations_lock:
        now = monotonic()
        for key in list(_evaluations):
            if _evaluations[key]['expires'] < now:
                del _evaluations[key]
        _evaluations[identifier] = {'description': description, 'evaluation': evaluation,
                                    'eligible': needs_suggestion, 'details': normalize_details(details or {}), 'expires': now + 600}
        while len(_evaluations) > 128:
            _evaluations.popitem(last=False)
    return {**evaluation, 'evaluationId': identifier, 'needsSuggestion': needs_suggestion}


def suggestion_context(identifier):
    with _evaluations_lock:
        entry = _evaluations.get(identifier)
        if not entry or entry['expires'] < monotonic():
            raise QualityError('Description check expired. Edit the description to check again.', 409)
        return entry.copy()
