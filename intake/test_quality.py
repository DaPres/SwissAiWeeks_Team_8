import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from quality import CRITERIA, QualityError, evaluate_description, parse_answers, parse_enrichment


def answers(value=0.9):
    return {'answers': {key: {'type': 'noul', 'noul': value} for key in CRITERIA}}


class QualityTests(unittest.TestCase):
    def test_enrichment_requires_valid_confident_catalog_value(self):
        for confidence, choice, expected in [(.91, 'NAV Calculation', {'service': 'NAV Calculation'}),
                                            (.79, 'NAV Calculation', {}), (.99, 'Unknown', {}),
                                            (.99, 'Invented service', {}), (True, 'NAV Calculation', {}),
                                            (float('nan'), 'NAV Calculation', {})]:
            self.assertEqual(parse_enrichment({'answers': {'infer_service': {'choice': choice, 'confidence': confidence}}}), expected)

    def test_probability_bands(self):
        for value, status, count in [(0.9, 'met', 5), (0.5, 'uncertain', 0), (0.1, 'missing', 0)]:
            result = parse_answers(answers(value))
            self.assertEqual(result['met'], count)
            self.assertTrue(all(item['status'] == status for item in result['criteria']))

    def test_incomplete_and_invalid_results_fail_closed(self):
        for value in [float('nan'), float('inf'), -1, 2, True, '0.9', None]:
            with self.subTest(value=value), self.assertRaises(QualityError):
                parse_answers(answers(value))
        with self.assertRaises(QualityError):
            parse_answers({'answers': {}})

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
        self.assertEqual(payload['state'], {'issue_description': 'The reporting service returns error 503.'})
        self.assertEqual(len(payload['questions']), 10)
        self.assertNotIn('test-secret', json.dumps(result))
        self.assertNotIn('private@example.com', json.dumps(payload))

    @patch.dict('os.environ', {'JEV_API_KEY': 'test-secret'})
    @patch('quality.urlopen')
    def test_provider_errors_are_sanitized(self, request):
        request.side_effect = HTTPError('https://api.typesafe.ai/v1/systemone', 401, 'test-secret', {}, None)
        with self.assertRaises(QualityError) as caught:
            evaluate_description({'description': 'The reporting service returns error 503.'})
        self.assertEqual(caught.exception.status, 503)
        self.assertNotIn('test-secret', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
