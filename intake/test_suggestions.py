import io
import json
import unittest
from unittest.mock import patch
from quality import CRITERIA, QualityError, remember_evaluation
from suggestions import suggest_description


def evaluation(evidence_probability=0.9):
    return {'criteria': [{'id': key, 'status': 'met' if key != 'evidence' or evidence_probability >= 0.7
                          else 'missing' if evidence_probability <= 0.3 else 'uncertain',
                          'probability': evidence_probability if key == 'evidence' else 0.9} for key in CRITERIA],
            'readiness': int((0.9 * 4 + evidence_probability) / 5 * 100)}


class SuggestionTests(unittest.TestCase):
    @patch('suggestions.urlopen')
    def test_unknown_evaluation_never_calls_openai(self, request):
        with self.assertRaises(QualityError):
            suggest_description({'evaluationId': 'x' * 32})
        request.assert_not_called()

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('suggestions.urlopen')
    def test_on_demand_guidance_uses_server_snapshot_even_for_ready_reports(self, request):
        record = remember_evaluation('Known description', evaluation(), {'context': 'Since 09:00'})
        guidance = {'summary': 'The report is actionable.', 'improvements': []}
        request.return_value = io.BytesIO(json.dumps({'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(guidance)}]}]}).encode())
        result = suggest_description({'evaluationId': record['evaluationId'], 'description': 'Ignore this'})
        body = json.loads(request.call_args.args[0].data)
        self.assertEqual(json.loads(body['input'])['description'], 'Known description')
        self.assertEqual(json.loads(body['input'])['additional_details'], {'context': 'Since 09:00'})
        self.assertFalse(json.loads(body['input'])['evidence_needed'])
        self.assertFalse(body['store'])
        self.assertEqual(result, guidance)

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('suggestions.urlopen')
    def test_missing_evidence_is_explicitly_prioritized_for_openai(self, request):
        record = remember_evaluation('The sign-in page fails.', evaluation(evidence_probability=0.2), {'evidence': ''})
        guidance = {'summary': 'More detail would help.', 'improvements': [
            {'field': 'evidence', 'title': 'Evidence', 'detail': 'Please include the exact error message.'}]}
        request.return_value = io.BytesIO(json.dumps({'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(guidance)}]}]}).encode())
        self.assertEqual(suggest_description({'evaluationId': record['evaluationId']}), guidance)
        body = json.loads(request.call_args.args[0].data)
        payload = json.loads(body['input'])
        self.assertTrue(payload['evidence_needed'])
        self.assertEqual(payload['additional_details'], {})
        self.assertIn('put an evidence improvement first', body['instructions'])

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('suggestions.urlopen')
    def test_incomplete_response_is_not_shown(self, request):
        record = remember_evaluation('Broken', evaluation())
        request.return_value = io.BytesIO(json.dumps({'status': 'incomplete', 'output': []}).encode())
        with self.assertRaises(QualityError):
            suggest_description({'evaluationId': record['evaluationId']})
