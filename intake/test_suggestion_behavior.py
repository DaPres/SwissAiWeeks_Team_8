"""Opt-in semantic regressions against the configured OpenAI model.

RUN_LIVE_SUGGESTION_TESTS=1 uv run python -m unittest test_suggestion_behavior -v
These calls use the server's API key and incur normal API usage.
"""
import os
import unittest

from quality import remember_evaluation
from suggestions import suggest_description


@unittest.skipUnless(os.getenv('RUN_LIVE_SUGGESTION_TESTS') == '1', 'Live model checks are opt-in')
class SuggestionBehaviorTests(unittest.TestCase):
    def guidance(self, description, unresolved=None):
        record = remember_evaluation(description, {
            'inferred': {'workType': 'Incident', 'department': 'Enterprise Applications'},
            'unresolvedFields': unresolved or [],
        })
        result = suggest_description({'evaluationId': record['evaluationId']})
        print(f'\nGuidance: {result}', flush=True)
        return result

    def test_sharepoint_screenshot_does_not_repeat_evidence_or_troubleshooting(self):
        result = self.guidance(
            'My sharepoint doesn\'t work, it is just loading, empty white screen with "loading" message, '
            'nothing else, no troubleshooting performed', ['urgency', 'priority'])
        self.assertLessEqual(len(result['improvements']), 1)
        for item in result['improvements']:
            self.assertIn(item['field'], ('urgency', 'impact', 'context'))
            self.assertNotRegex(item['detail'].lower(), r'troubleshoot|error message|failed step|tried|attempted')

    def test_complete_symptom_without_troubleshooting_is_actionable(self):
        result = self.guidance(
            'Since 09:00 SharePoint stays on an empty white screen with only "loading". '
            'Only I am affected. No other error message. No troubleshooting performed. '
            'I can use local copies to continue work and have no deadline.')
        self.assertEqual(result['improvements'], [])

    def test_previous_attempts_and_unknown_timing_are_not_asked_again(self):
        result = self.guidance(
            'SharePoint stays blank with "loading". Reloading and a private browser window did not help. '
            'No error code. I do not know when this began. Only I am affected, '
            'I can keep working with local files, and there is no deadline.')
        self.assertEqual(result['improvements'], [])

    def test_simple_information_question_needs_no_diagnostic_evidence(self):
        self.assertEqual(self.guidance('Which mail program should I use for work email?')['improvements'], [])

    def test_vague_report_still_gets_a_specific_question(self):
        result = self.guidance('It does not work.')
        self.assertEqual(len(result['improvements']), 1)
        self.assertIn(result['improvements'][0]['field'], ('service', 'evidence'))
