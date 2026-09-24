import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from quality import CRITERIA, QualityError, parse_answers, remember_evaluation, normalize_details
from incidents import create_ready_incident


def record(probability, details=None):
    evaluation = parse_answers({'answers': {key: {'noul': probability} for key in CRITERIA}})
    return remember_evaluation('Report', evaluation, details)


class ReadinessTests(unittest.TestCase):
    def test_below_threshold_and_stale_drafts_cannot_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'db.sqlite'
            for score in [0, .79, .7999]:
                item = record(score)
                with self.assertRaises(QualityError):
                    create_ready_incident({'description': 'Report', 'evaluationId': item['evaluationId']}, path)
            item = record(.95)
            for data in [{'description': 'Changed'}, {'description': 'Report', 'details': {'impact': 'Changed'}}]:
                with self.assertRaises(QualityError):
                    create_ready_incident({**data, 'evaluationId': item['evaluationId']}, path)
            self.assertFalse(path.exists())

    def test_exactly_eighty_can_submit_with_description_only(self):
        with tempfile.TemporaryDirectory() as directory:
            item = record(.8)
            saved = create_ready_incident({'description': 'Report', 'evaluationId': item['evaluationId']}, Path(directory) / 'db')
            self.assertEqual(saved['incident']['Description'], 'Report')
            self.assertNotIn('Reporter', saved['incident'])
            self.assertNotIn('Priority', saved['incident'])
            self.assertEqual(saved['incident']['Status'], 'open')

    def test_optional_details_are_preserved_and_compared(self):
        details = {'service': 'NAV', 'impact': 'Five funds blocked'}
        item = record(.9, details)
        with tempfile.TemporaryDirectory() as directory:
            saved = create_ready_incident({'description': 'Report', 'details': details, 'evaluationId': item['evaluationId']}, Path(directory) / 'db')
            self.assertIn('Impact: Five funds blocked', saved['incident']['All Comments'])

    def test_manual_fields_override_inference_and_priority_is_derived(self):
        details = {'department': 'Service Desk', 'summary': 'VPN unavailable', 'impact': 'high'}
        evaluation = {**parse_answers({'answers': {key: {'noul': .95} for key in CRITERIA}}),
                      'inferred': {'department': 'Trading Support', 'service': 'NAV Calculation', 'urgency': 'high', 'impact': 'low'}}
        item = remember_evaluation('Report', evaluation, details)
        with tempfile.TemporaryDirectory() as directory:
            saved = create_ready_incident({'description': 'Report', 'details': details, 'evaluationId': item['evaluationId']}, Path(directory) / 'db')['incident']
            self.assertEqual(saved['Service Team(s)'], ['Service Desk'])
            self.assertEqual(saved['Affected Business or IT Services'], ['NAV Calculation'])
            self.assertEqual(saved['Summary'], 'VPN unavailable')
            self.assertEqual(saved['Impact'], 'high')
            self.assertEqual(saved['Priority'], 'high')

    def test_expired_evaluation_cannot_submit(self):
        item = record(.9)
        with patch('quality.monotonic', return_value=float('inf')), self.assertRaises(QualityError):
            create_ready_incident({'description': 'Report', 'evaluationId': item['evaluationId']})

    def test_details_are_validated(self):
        for details in [None, {'unknown': 'x'}, {'impact': 5}, {'evidence': 'x' * 2001}]:
            with self.assertRaises(ValueError):
                normalize_details(details)
