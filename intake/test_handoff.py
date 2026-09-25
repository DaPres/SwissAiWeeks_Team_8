import tempfile
import unittest
from pathlib import Path

from incidents import (IncidentError, decide_incident, list_incidents, save_processed_incident,
                       validate_handoff)
from quality import CRITERIA, QualityError, parse_answers, remember_evaluation
from engine_client import prepare_incident
from incident_fields import ASSIGNEES, LEVELS, calculate_priority


DESCRIPTION = 'The Order Management screen shows error 503 for everyone since 09:00.'
SELECTED = {'workType': 'Incident', 'department': 'Trading Support', 'priority': 'high',
            'urgency': 'high', 'impact': 'high'}


def request():
    evaluation = {**parse_answers({'answers': {key: {'noul': .95} for key in CRITERIA}}),
                  'inferred': dict(SELECTED)}
    token = remember_evaluation(DESCRIPTION, evaluation)
    return {'description': DESCRIPTION, 'details': {}, 'selected': dict(SELECTED),
            'account': 'client', 'evaluationId': token['evaluationId']}


def enrichment(identifier, client_fix=True):
    return {'id': identifier, 'summary': 'Order Management is unavailable', 'description': DESCRIPTION,
            'workType': 'Incident', 'service': 'Order Management', 'team': 'Trading Support',
            'entity': 'Switzerland', 'assignee': ASSIGNEES[0], 'resolutionStatus': 'done', 'urgency': 'high',
            'impact': 'high', 'priority': 'high',
            'clientResolution': {'title': 'Refresh the session', 'steps': ['Sign in again']} if client_fix else None,
            'expertResolution': {'note': 'Investigate the upstream gateway.'}}


class HandoffTests(unittest.TestCase):
    def test_inferred_classification_reaches_core_as_hints(self):
        selected = {**SELECTED, 'workType': 'Service Request', 'urgency': 'highest', 'priority': 'highest'}
        evaluation = {**parse_answers({'answers': {key: {'noul': .95} for key in CRITERIA}}), 'inferred': selected}
        token = remember_evaluation(DESCRIPTION, evaluation)
        draft = validate_handoff({**request(), 'selected': selected, 'evaluationId': token['evaluationId']})
        core_input = prepare_incident({'description': draft['description'], 'details': draft['fields']})
        self.assertEqual(core_input['details']['workType'], 'Service Request')
        self.assertEqual(core_input['details']['priority'], 'highest')

    def test_requires_every_current_selected_field(self):
        valid = request()
        self.assertEqual(validate_handoff(valid)['fields']['department'], 'Trading Support')
        for change in ({'selected': {**SELECTED, 'workType': ''}},
                       {'selected': {**SELECTED, 'urgency': ''}},
                       {'selected': {**SELECTED, 'impact': 'invalid'}},
                       {'selected': {**SELECTED, 'priority': 'invalid'}},
                       {'details': {'department': 'Service Desk'}, 'selected': SELECTED},
                       {'selected': {**SELECTED, 'department': 'Unknown team'}}):
            with self.subTest(change=change), self.assertRaises(QualityError):
                validate_handoff({**valid, **change})

    def test_five_fields_are_enough_without_hidden_enrichment(self):
        draft = validate_handoff(request())
        self.assertEqual(set(draft['fields']), set(SELECTED))
        with tempfile.TemporaryDirectory() as directory:
            saved = save_processed_incident(draft, enrichment('INC-000000000001'),
                                            'INC-000000000001', Path(directory) / 'db')
        self.assertEqual(saved['incident']['Affected Business or IT Services'], ['Order Management'])
        self.assertEqual(saved['incident']['Assignee'], ASSIGNEES[0])

    def test_complete_chips_allow_submission_despite_low_quality(self):
        token = remember_evaluation(DESCRIPTION, {**parse_answers({'answers': {
            key: {'noul': .5} for key in CRITERIA}}), 'inferred': SELECTED})
        self.assertEqual(validate_handoff({**request(), 'evaluationId': token['evaluationId']})['fields'], SELECTED)

    def test_complete_chips_do_not_need_any_current_evaluation(self):
        for description, token in [('x', None), ('Latest text edited while checking', 'expired-token')]:
            data = {'description': description, 'details': {}, 'selected': SELECTED, 'account': 'client'}
            if token:
                data['evaluationId'] = token
            self.assertEqual(validate_handoff(data)['description'], description)
            self.assertEqual(prepare_incident(data)['description'], description)

    def test_empty_description_or_missing_chips_still_fail(self):
        for description in ['', '   ', None]:
            with self.assertRaises(QualityError):
                validate_handoff({**request(), 'description': description})
        with self.assertRaises(ValueError):
            validate_handoff({**request(), 'selected': {}})

    def test_predicted_priority_does_not_block_submission_before_engine_correction(self):
        draft = validate_handoff({**request(), 'selected': {**SELECTED, 'priority': 'lowest'}})
        with tempfile.TemporaryDirectory() as directory:
            saved = save_processed_incident(draft, enrichment('INC-000000000003'),
                                            'INC-000000000003', Path(directory) / 'db')
        self.assertEqual(saved['incident']['Priority'], 'high')

    def test_client_fix_requires_decision_before_team_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / 'incidents.db'
            saved = save_processed_incident(validate_handoff(request()), enrichment('INC-123456789ABC'),
                                            'INC-123456789ABC', db_path)
            self.assertEqual(saved['incident']['Status'], 'awaiting client')
            self.assertEqual(saved['incident']['Resolution'], 'done')
            self.assertTrue(saved['incident']['All Comments'][-1].startswith(saved['incident']['Assignee'] + ':'))
            self.assertEqual(len(list_incidents('client', db_path)), 1)
            self.assertEqual(list_incidents('Trading Support', db_path), [])
            decided = decide_incident(saved['id'], 'handoff', 'client', db_path)
            self.assertEqual(decided['incident']['Status'], 'open')
            self.assertEqual(decided['enriched']['expertResolution']['note'], 'Investigate the upstream gateway.')
            self.assertEqual(len(list_incidents('Trading Support', db_path)), 1)
            with self.assertRaises(IncidentError):
                decide_incident(saved['id'], 'resolved', 'client', db_path)

    def test_engine_can_correct_manual_chips_and_persists_the_audit(self):
        manual = dict(SELECTED)
        draft = validate_handoff({**request(), 'details': manual, 'selected': manual})
        result = enrichment('INC-000000000002', False)
        result.update({'workType': 'Service Request', 'team': 'Risk & Controls',
                       'urgency': 'low', 'impact': 'lowest', 'priority': 'highest'})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'db'
            saved = save_processed_incident(draft, result, result['id'], path)
            reloaded = list_incidents('client', path)[0]
            self.assertEqual(reloaded, saved)
            self.assertEqual(list_incidents('Trading Support', path), [])
            self.assertEqual(list_incidents('Risk & Controls', path), [saved])
        incident, enriched = saved['incident'], saved['enriched']
        self.assertEqual(incident['Work type'], 'Service Request')
        self.assertEqual(incident['Service Team(s)'], ['Risk & Controls'])
        self.assertEqual((incident['Urgency'], incident['Impact'], incident['Priority']), ('low', 'lowest', 'lowest'))
        self.assertEqual(enriched['expertResolution']['team'], 'Risk & Controls')
        self.assertEqual(enriched['fieldCorrections'], {
            'Work type': {'before': 'Incident', 'after': 'Service Request'},
            'Service Team(s)': {'before': ['Trading Support'], 'after': ['Risk & Controls']},
            'Urgency': {'before': 'high', 'after': 'low'},
            'Impact': {'before': 'high', 'after': 'lowest'},
            'Priority': {'before': 'high', 'after': 'lowest'},
        })
        self.assertEqual(enriched['submittedFields']['Urgency'], 'high')
        self.assertEqual(draft['manual'], manual)

    def test_unchanged_values_and_new_enrichment_are_not_marked_as_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            result = enrichment('INC-000000000004', False)
            saved = save_processed_incident(validate_handoff(request()), result, result['id'], Path(directory) / 'db')
        self.assertEqual(saved['enriched']['fieldCorrections'], {})
        self.assertNotIn('Assignee', saved['enriched']['submittedFields'])

    def test_engine_resolution_and_assignee_override_draft_hints(self):
        details = {'assignee': ASSIGNEES[-1], 'resolution': 'cannot reproduce',
                   'resolutionComment': 'An unverified draft note.'}
        draft = validate_handoff({**request(), 'details': details})
        with tempfile.TemporaryDirectory() as directory:
            result = enrichment('INC-000000000005', False)
            saved = save_processed_incident(draft, result, result['id'], Path(directory) / 'db')
        self.assertEqual(saved['incident']['Assignee'], ASSIGNEES[0])
        self.assertEqual(saved['incident']['Resolution'], 'done')
        self.assertEqual(saved['incident']['All Comments'][-1], ASSIGNEES[0] + ': Investigate the upstream gateway.')
        self.assertEqual(saved['enriched']['fieldCorrections']['Resolution'],
                         {'before': 'cannot reproduce', 'after': 'done'})

    def test_correction_audit_survives_client_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'db'
            result = enrichment('INC-000000000006')
            result['urgency'] = 'low'
            saved = save_processed_incident(validate_handoff(request()), result, result['id'], path)
            decided = decide_incident(result['id'], 'resolved', 'client', path)
            self.assertEqual(decided['enriched']['fieldCorrections'], saved['enriched']['fieldCorrections'])

    def test_all_priority_matrix_cells_match_challenge_policy(self):
        expected_rows = ['highest highest high medium medium', 'highest high high medium low',
                         'high high medium low low', 'medium medium low low lowest',
                         'medium low low lowest lowest']
        for urgency, row in zip(LEVELS, expected_rows):
            for impact, expected in zip(LEVELS, row.split()):
                self.assertEqual(calculate_priority(urgency, impact), expected)
        self.assertIsNone(calculate_priority('', 'high'))

    def test_accepting_client_fix_marks_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / 'incidents.db'
            save_processed_incident(validate_handoff(request()), enrichment('INC-ABCDEF123456'),
                                    'INC-ABCDEF123456', db_path)
            decided = decide_incident('INC-ABCDEF123456', 'resolved', 'client', db_path)
            self.assertEqual(decided['incident']['Status'], 'done')
            self.assertEqual(decided['incident']['Resolution'], 'done')
            self.assertIsNotNone(decided['incident']['Resolution date'])

    def test_no_client_fix_goes_directly_to_team(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / 'incidents.db'
            saved = save_processed_incident(validate_handoff(request()), enrichment('INC-987654321ABC', False),
                                            'INC-987654321ABC', db_path)
            self.assertEqual(saved['incident']['Status'], 'open')
            self.assertEqual(len(list_incidents('Trading Support', db_path)), 1)


if __name__ == '__main__':
    unittest.main()
