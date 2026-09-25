from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from app.intake import enrich_intake
from app.main import app


def sample():
    return {'assistId': 'preview-1', 'draft': {'summary': 'Orders blocked', 'description': 'Order gateway returned 503',
        'workType': 'Incident', 'service': 'Order Management', 'team': 'Trading Support',
        'assignee': 'quinn.anderson@intcom.com', 'urgency': 'high', 'impact': 'low', 'priority': 'medium'},
        'selfService': {'possible': True, 'answer': 'Sign out and sign back in.'},
        'clarifyingQuestion': '', 'matches': [{'id': 'past-1', 'service': 'Order Management',
        'resolution': 'Restarted the order gateway and verified order entry.'}]}


def test_bridge_preserves_client_expert_and_training_resolution_vocabulary():
    llm = Mock()
    llm.complete_json.return_value = {'resolution': 'cannot reproduce', 'resolution_text': 'Checked the same order; no error reproduced.'}
    with patch('app.intake.assist', return_value=sample()) as assist, patch('app.intake.get_llm', return_value=llm):
        result = enrich_intake(object(), 'Order gateway returned 503', {'urgency': 'high', 'resolutionComment': 'NOT EVIDENCE'})
    assert 'NOT EVIDENCE' not in assist.call_args.args[1]
    assert 'high' in assist.call_args.args[1]
    assert result['resolutionStatus'] == 'cannot reproduce'
    assert result['clientResolution']['text'] == 'Sign out and sign back in.'
    assert result['expertResolution']['similarPast'][0]['id'] == 'past-1'
    assert result['engine'] == 'shared-backend'


def test_bridge_no_self_service_does_not_fabricate_client_fix():
    response = sample()
    response['selfService'] = {'possible': False, 'answer': ''}
    llm = Mock()
    llm.complete_json.side_effect = lambda *args, **kwargs: kwargs['fallback']()
    with patch('app.intake.assist', return_value=response), patch('app.intake.get_llm', return_value=llm):
        result = enrich_intake(object(), 'Order gateway returned 503', {})
    assert result['clientResolution'] is None
    assert result['resolutionStatus'] == 'done'


def test_intake_route_validates_and_forwards_partial_draft():
    with patch('app.main.store', object(), create=True), patch('app.main.enrich_intake', return_value={'engine': 'shared-backend'}) as enrich:
        client = TestClient(app)
        assert client.post('/api/intake/enrich', json={'description': 'Order failed', 'details': {'urgency': 'high'}}).json() == {'engine': 'shared-backend'}
        assert enrich.call_args.args[1:] == ('Order failed', {'urgency': 'high'})
        assert client.post('/api/intake/enrich', json={'description': ''}).status_code == 422
