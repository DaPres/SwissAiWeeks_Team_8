import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from quality import QualityError, evaluate_description, parse_enrichment, build_jev_payload
from jev_prompt import reference_prompt


def answers():
    choices = {'worktype': 'incident', 'service_teams': 'Risk & Controls', 'urgency': 'High',
               'impact': 'Moderate / Limited', 'priority': 'High'}
    return {'answers': {key: {'type': 'choice', 'choice': value, 'confidence': .1,
                             'probabilities': {value: .6, 'unclear': .4}} for key, value in choices.items()}}


class QualityTests(unittest.TestCase):
    def test_highest_probability_wins_over_choice_and_confidence(self):
        response = answers()
        response['answers']['worktype'].update({'choice': 'service_request', 'confidence': 1})
        response['answers']['priority'].update({'choice': 'Lowest', 'confidence': 1})
        self.assertEqual(parse_enrichment(response), {'workType': 'Incident', 'department': 'Risk & Controls',
            'urgency': 'high', 'impact': 'medium', 'priority': 'high'})

    def test_unclear_unknown_or_tied_unclear_winner_stays_empty(self):
        for name in ('unclear', 'Unclear', 'Unknown'):
            for probability in (.7, .5):
                response = answers()
                response['answers']['worktype']['probabilities'] = {'incident': 1 - probability, name: probability}
                self.assertNotIn('workType', parse_enrichment(response))

    def test_invalid_or_missing_probabilities_do_not_fall_back_to_choice(self):
        for probabilities in (None, {}, {'incident': 0}, {'incident': True}, {'incident': float('nan')},
                              {'incident': float('inf')}, {'incident': -1}, {'incident': 2}, {'incident': '0.9'}):
            response = answers()
            response['answers']['worktype']['probabilities'] = probabilities
            self.assertNotIn('workType', parse_enrichment(response))

    @patch.dict('os.environ', {'JEV_API_KEY': 'test-secret'})
    @patch('quality.urlopen')
    def test_five_answers_are_sufficient_without_removed_quality_questions(self, request):
        request.return_value = io.BytesIO(json.dumps(answers()).encode())
        result = evaluate_description({'description': 'Regulatory Reporting execution error.'})
        self.assertEqual(len(result['inferred']), 5)
        self.assertEqual(result['unresolvedFields'], [])
        self.assertNotIn('readiness', result)
        self.assertNotIn('criteria', result)

    @patch.dict('os.environ', {'JEV_API_KEY': 'test-secret'})
    @patch('quality.urlopen')
    def test_unclear_priority_is_not_replaced_by_matrix_autofill(self, request):
        response = answers()
        response['answers']['priority']['probabilities'] = {'High': .2, 'Unclear': .8}
        request.return_value = io.BytesIO(json.dumps(response).encode())
        result = evaluate_description({'description': 'Report fails.'})
        self.assertNotIn('priority', result['inferred'])
        self.assertEqual(result['unresolvedFields'], ['priority'])

    @patch.dict('os.environ', {'JEV_API_KEY': 'test-secret'})
    @patch('quality.urlopen')
    def test_manual_values_take_precedence_over_unclear_inference(self, request):
        response = answers()
        response['answers']['worktype']['probabilities'] = {'incident': .1, 'unclear': .9}
        request.return_value = io.BytesIO(json.dumps(response).encode())
        result = evaluate_description({'description': 'Report fails.', 'details': {'workType': 'Service Request'}})
        self.assertNotIn('workType', result['inferred'])
        self.assertNotIn('workType', result['unresolvedFields'])

    @patch('quality.urlopen')
    def test_invalid_input_does_not_call_provider(self, request):
        for data in [None, {}, {'description': 4}, {'description': '   '}, {'description': 'a' * 10001}]:
            with self.subTest(data_type=type(data).__name__), self.assertRaises(ValueError):
                evaluate_description(data)
        request.assert_not_called()

    @patch.dict('os.environ', {'JEV_API_KEY': 'test-secret'})
    @patch('quality.urlopen')
    def test_only_description_is_sent_and_credential_is_server_side(self, request):
        request.return_value = io.BytesIO(json.dumps(answers()).encode())
        result = evaluate_description({'description': 'The reporting service returns error 503.', 'reporter': 'private@example.com'})
        sent = request.call_args.args[0]
        payload = json.loads(sent.data)
        self.assertEqual(sent.full_url, 'https://api.typesafe.ai/v1/systemone')
        self.assertEqual(payload['state'], {'description': 'The reporting service returns error 503.'})
        self.assertEqual(set(payload['questions']), {'worktype', 'service_teams', 'urgency', 'impact', 'priority'})
        self.assertEqual(result['debug']['request']['body'], payload)
        self.assertEqual(result['debug']['response']['body'], answers())
        self.assertGreaterEqual(result['debug']['durationMs'], 0)
        self.assertNotIn('test-secret', json.dumps(result))
        self.assertNotIn('private@example.com', json.dumps(payload))

    @patch.dict('os.environ', {'JEV_API_KEY': 'test-secret'})
    @patch('quality.urlopen')
    def test_uses_reference_prompts_but_ui_state(self, request):
        request.return_value = io.BytesIO(json.dumps(answers()).encode())
        evaluate_description({'description': '  A different report from the UI.  ',
                              'details': {'department': 'Trading Support', 'entity': ' Switzerland ', 'summary': ''}})
        payload = json.loads(request.call_args.args[0].data)
        self.assertEqual(payload['state'], {'description': 'A different report from the UI.',
                         'additional_details': {'department': 'Trading Support', 'entity': 'Switzerland'}})
        for field, reference in (('workType', 'worktype'), ('urgency', 'urgency'), ('impact', 'impact'),
                                 ('priority', 'priority'), ('department', 'service_teams')):
            expected = reference_prompt()['questions'][reference]
            actual = payload['questions'][reference]
            self.assertIn(expected['instructions'], actual['instructions'])
            self.assertEqual(actual['criteria'], expected['criteria'])
        for key in ('service_teams',):
            self.assertIn('"Trading Platform": "Investment Operations"', payload['questions'][key]['instructions'])

    @patch.dict('os.environ', {'JEV_API_KEY': 'test-secret'})
    @patch('quality.urlopen')
    def test_invalid_answers_still_include_redacted_exchange(self, request):
        request.return_value = io.BytesIO(json.dumps({'answers': {}, 'diagnostic': 'test-secret'}).encode())
        with self.assertRaises(QualityError) as caught:
            evaluate_description({'description': 'An incomplete upstream answer.'})
        self.assertEqual(caught.exception.debug['response']['body']['answers'], {})
        self.assertNotIn('test-secret', json.dumps(caught.exception.debug))

    @patch.dict('os.environ', {'JEV_API_KEY': 'test-secret'})
    @patch('quality.urlopen')
    def test_provider_errors_are_sanitized(self, request):
        request.side_effect = HTTPError('https://api.typesafe.ai/v1/systemone', 401, 'test-secret', {}, None)
        with self.assertRaises(QualityError) as caught:
            evaluate_description({'description': 'The reporting service returns error 503.'})
        self.assertEqual(caught.exception.status, 503)
        self.assertNotIn('test-secret', str(caught.exception))
        self.assertNotIn('test-secret', json.dumps(caught.exception.debug))
        self.assertEqual(caught.exception.debug['response']['status'], 401)


if __name__ == '__main__':
    unittest.main()
