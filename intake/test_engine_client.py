import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import URLError

from engine_client import EngineError, _cache, complete_draft_fields, preview_incident
from incident_fields import ASSIGNEES


class EngineClientTests(unittest.TestCase):
    def setUp(self):
        _cache.clear()
        self.env = patch.dict(os.environ, {'TRIAGE_BACKEND_URL': 'http://shared-backend:8000'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.result = {'service': 'Order Management', 'team': 'Trading Support', 'workType': 'Incident',
                       'assignee': ASSIGNEES[0], 'urgency': 'high', 'impact': 'low',
                       'resolutionStatus': 'done', 'expertResolution': {'note': 'Replayed the failed order.',
                       'similarPast': [{'id': 'past-1', 'text': 'Replayed the failed order.'}]}}

    def test_shared_api_receives_live_fields_without_resolution_claims_and_caches_preview(self):
        with patch('engine_client.urlopen', return_value=io.BytesIO(json.dumps(self.result).encode())) as call:
            draft = {'description': 'Order screen returns 503', 'details': {'service': 'Order Management',
                     'workType': 'Service Request', 'resolutionComment': 'Proposed fix'}}
            first = preview_incident(draft, 'INC-FIRST')
            second = preview_incident(draft, 'INC-SECOND')
        self.assertEqual(call.call_count, 1)
        req = call.call_args.args[0]
        self.assertEqual(req.full_url, 'http://shared-backend:8000/api/intake/enrich')
        self.assertEqual(json.loads(req.data)['details'], {'service': 'Order Management', 'workType': 'Service Request'})
        self.assertEqual(first['id'], 'INC-FIRST')
        self.assertEqual(second['id'], 'INC-SECOND')

    def test_completion_uses_shared_backend_fields_and_sources(self):
        with patch('engine_client.preview_incident', return_value=self.result):
            completed = complete_draft_fields('Order failed', {})
        self.assertEqual(completed['fields']['priority'], 'medium')
        self.assertEqual(completed['fields']['department'], 'Trading Support')
        self.assertEqual(completed['fields']['resolution'], 'done')
        self.assertEqual(completed['sources'][0]['id'], 'past-1')

    def test_unavailable_backend_is_actionable_and_not_cached(self):
        with patch('engine_client.urlopen', side_effect=URLError('offline')):
            with self.assertRaisesRegex(EngineError, 'Check Aspire'):
                preview_incident({'description': 'Order failed'})
        self.assertFalse(_cache)
