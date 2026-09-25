"""Intake adapter over the shared retrieval, routing and resolution pipeline."""
import json

from .evaluate import RESOLUTIONS, RESOLUTION_OUTCOME_RULES, RESOLUTION_SCHEMA
from .llm import get_llm
from .triage import RESOLUTION_SYSTEM, assist


def enrich_intake(store, description: str, details: dict[str, str]) -> dict:
    # Proposed resolution text is not evidence that an action has already happened.
    hints = {key: value for key, value in details.items()
             if value and key not in ('resolution', 'resolutionComment')}
    text = description + ("\n\nCurrent intake fields (correct them if inconsistent with the description):\n"
                          + json.dumps(hints, ensure_ascii=False) if hints else "")
    result = assist(store, text, [], details.get('reporter'))
    draft = result['draft']
    precedents = [match for match in result['matches']
                  if match.get('resolution') and match['service'] == draft['service']]
    question = result.get('clarifyingQuestion') or ''
    fallback = {'resolution': 'clarification' if question or not precedents else 'done',
                'resolution_text': question or (precedents[0]['resolution'] if precedents else
                    'Requested diagnostic evidence and reproduction steps before proposing a fix.')}
    prompt = (f"Assigned agent: {draft.get('assignee') or draft['team']}\n"
              f"Incident: {json.dumps(draft, ensure_ascii=False)}\n"
              f"Precedent resolutions: {json.dumps(precedents, ensure_ascii=False)}")
    outcome = get_llm().complete_json(RESOLUTION_SYSTEM + RESOLUTION_OUTCOME_RULES,
                                     prompt, RESOLUTION_SCHEMA, 'resolution', fallback=lambda: fallback)
    status = outcome.get('resolution')
    if status not in RESOLUTIONS:
        status = fallback['resolution']
    note = (outcome.get('resolution_text') or fallback['resolution_text']).strip()[:2000]
    sources = [{'id': match['id'], 'text': match['resolution']} for match in precedents[:3]]
    client = result.get('selfService') or {}
    return {
        **draft, 'description': draft.get('description') or description,
        'entity': details.get('entity'), 'resolutionStatus': status,
        'clientResolution': {'title': 'Try this first', 'text': client['answer']}
            if client.get('possible') and client.get('answer') else None,
        'expertResolution': {'note': note, 'assignee': draft.get('assignee'),
                             'team': draft['team'], 'similarPast': sources},
        'clarification': {'message': question} if question else None,
        'assistId': result['assistId'], 'engine': 'shared-backend',
    }
