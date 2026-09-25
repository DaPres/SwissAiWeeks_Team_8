import io
import json
import unittest
from unittest.mock import patch
from quality import CRITERIA, QualityError, remember_evaluation
from suggestions import UNRELATED_MESSAGE, suggest_description


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
        guidance = {'relevance': 'support', 'summary': 'The report is actionable.', 'improvements': []}
        request.return_value = io.BytesIO(json.dumps({'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(guidance)}]}]}).encode())
        result = suggest_description({'evaluationId': record['evaluationId'], 'description': 'Ignore this'})
        body = json.loads(request.call_args.args[0].data)
        self.assertEqual(json.loads(body['input'])['description'], 'Known description')
        self.assertEqual(json.loads(body['input'])['additional_details'], {'context': 'Since 09:00'})
        self.assertNotIn('readiness_markers', json.loads(body['input']))
        self.assertFalse(body['store'])
        self.assertEqual(result, guidance)

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('suggestions.urlopen')
    def test_openai_assesses_evidence_from_description_without_jev_quality_questions(self, request):
        record = remember_evaluation('The sign-in page fails.', evaluation(evidence_probability=0.2), {'evidence': ''})
        guidance = {'relevance': 'support', 'summary': 'More detail would help.', 'improvements': [
            {'field': 'evidence', 'title': 'Evidence', 'detail': 'Please include the exact error message.'}]}
        request.return_value = io.BytesIO(json.dumps({'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(guidance)}]}]}).encode())
        self.assertEqual(suggest_description({'evaluationId': record['evaluationId']}), guidance)
        body = json.loads(request.call_args.args[0].data)
        payload = json.loads(body['input'])
        self.assertNotIn('evidence_needed', payload)
        self.assertNotIn('readiness_markers', payload)
        self.assertEqual(payload['additional_details'], {})
        self.assertEqual(body['text']['format']['schema']['properties']['improvements']['maxItems'], 1)

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('suggestions.urlopen')
    def test_incomplete_response_is_not_shown(self, request):
        record = remember_evaluation('Broken', evaluation())
        request.return_value = io.BytesIO(json.dumps({'status': 'incomplete', 'output': []}).encode())
        with self.assertRaises(QualityError):
            suggest_description({'evaluationId': record['evaluationId']})

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('suggestions.urlopen')
    def test_description_and_explicit_negative_answers_reach_the_model_intact(self, request):
        description = 'SharePoint shows a blank screen with "loading", nothing else, no troubleshooting performed.'
        record = remember_evaluation(description, {'inferred': {'workType': 'Incident'},
                                     'unresolvedFields': ['urgency', 'priority']}, {'context': "I don't know when it began"})
        guidance = {'relevance': 'support', 'summary': 'The symptom is clear.', 'improvements': [
            {'field': 'urgency', 'title': 'Deadline', 'detail': 'Is there a deadline for accessing SharePoint?'}]}
        request.return_value = io.BytesIO(json.dumps({'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(guidance)}]}]}).encode())
        self.assertEqual(suggest_description({'evaluationId': record['evaluationId']}), guidance)
        payload = json.loads(json.loads(request.call_args.args[0].data)['input'])
        self.assertEqual(payload['description'], description)
        self.assertEqual(payload['additional_details']['context'], "I don't know when it began")
        self.assertEqual(payload['unresolved_fields'], ['urgency', 'priority'])

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('suggestions.urlopen')
    def test_multiple_questions_are_rejected(self, request):
        record = remember_evaluation('Broken', evaluation())
        guidance = {'relevance': 'support', 'summary': 'More detail would help.', 'improvements': [
            {'field': 'context', 'title': 'Timing', 'detail': 'When did it start?'},
            {'field': 'impact', 'title': 'Scope', 'detail': 'Who is affected?'}]}
        request.return_value = io.BytesIO(json.dumps({'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(guidance)}]}]}).encode())
        with self.assertRaises(QualityError):
            suggest_description({'evaluationId': record['evaluationId']})

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('suggestions.urlopen')
    def test_unrelated_content_always_uses_generic_copy_and_no_followups(self, request):
        record = remember_evaluation('Who invented toothpaste?', evaluation())
        guidance = {'relevance': 'unrelated', 'summary': 'A trivia answer should not be shown.',
                    'improvements': [{'field': 'context', 'title': 'More', 'detail': 'When did this start?'}]}
        request.return_value = io.BytesIO(json.dumps({'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(guidance)}]}]}).encode())
        self.assertEqual(suggest_description({'evaluationId': record['evaluationId']}),
                         {'relevance': 'unrelated', 'summary': UNRELATED_MESSAGE, 'improvements': []})
