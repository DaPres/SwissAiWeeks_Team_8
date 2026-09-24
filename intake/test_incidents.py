from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from incidents import create_incident, validate_incident


def payload():
    return {'Work type': 'Incident', 'Summary': 'NAV job stopped', 'Description': 'Overnight run failed.',
            'Reporter': 'agent@example.com', 'Assignee': '', 'Affected Business or IT Services': ['NAV Calculation'],
            'Business Entity': ['Switzerland'], 'Service Team(s)': [], 'Urgency': 'highest', 'Impact': 'highest',
            'Priority': 'lowest', 'All Comments': []}


class IncidentTests(unittest.TestCase):
    def test_creation_derives_priority_and_lifecycle(self):
        data = payload() | {'Status': 'done', 'Resolution': 'done', 'Created date': 'invalid'}
        result = validate_incident(data)
        self.assertEqual(result['Priority'], 'highest')
        self.assertEqual(result['Status'], 'open')
        self.assertIsNone(result['Resolution'])
        self.assertIsNone(result['Resolution date'])
        self.assertRegex(result['Created date'], r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$')

    def test_invalid_payloads_are_rejected(self):
        for changes in [{'Summary': '  '}, {'Reporter': 'not-email'}, {'Business Entity': []},
                        {'Affected Business or IT Services': ['Imaginary']}, {'Urgency': 'Critical'},
                        {'All Comments': 'oops'}, {'Service Team(s)': [None]}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_incident(payload() | changes)

    def test_multiple_values_and_persistence(self):
        data = payload() | {'Business Entity': ['France', 'Germany'],
                            'Affected Business or IT Services': ['NAV Calculation', 'Fund Pricing'],
                            'All Comments': ['agent@example.com: Investigating.']}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'incidents.db'
            result = create_incident(data, path)
            with closing(sqlite3.connect(path)) as db:
                stored = json.loads(db.execute('SELECT payload FROM incidents WHERE id = ?', (result['id'],)).fetchone()[0])
            self.assertEqual(stored, result['incident'])
            self.assertEqual(stored['Business Entity'], ['France', 'Germany'])


if __name__ == '__main__':
    unittest.main()
