import copy
import unittest
from test_backend import SAMPLE, ROOT
from analyzer import analyze_transcript, chart_for


class RegulatoryTests(unittest.TestCase):
    def setUp(self):
        self.t = copy.deepcopy(SAMPLE)
        self.rules = {'passing': {'minimum_grade': 10, 'zero_is_final': False, 'source': 'TEST ONLY'},
                      'relationships': {'source': 'TEST ONLY', 'exceptions_resolved': True},
                      'student_id': 'TEST-0001', 'history_complete': True}

    def report(self):
        return analyze_transcript(self.t, '1401-1402', self.rules)

    def relation_fixture(self):
        c = chart_for('1401-1402')
        r = next(r for r in c.relations if r['relation_type'] == 'PRE' and r['link_status'] == 'OK')
        row = c.by_id[r['course_id']][0]
        self.t['semesters'] = [{'academic_year_start': 1402, 'term': 1,
                               'courses': [{'course_code': row['course_code'], 'course_name': row['course_name'], 'credits': row['credits'], 'grade': 15, 'enrollment_status': 'ENROLLED'}]}]
        return r

    def test_unknown_rules_never_violate_or_claim_exact_total(self):
        r = analyze_transcript(self.t, '1401-1402')
        self.assertIsNone(r['remaining']['exact_remaining_credits'])
        self.assertFalse(any(i['status'] == 'VIOLATION' for i in r['audit']))

    def test_zero_is_unknown_until_explicit_policy(self):
        self.t['semesters'][0]['courses'][0]['grade'] = 0
        self.assertEqual(self.report()['course_attempts'][0]['completion'], 'UNKNOWN')
        self.rules['passing']['zero_is_final'] = True
        self.assertEqual(self.report()['course_attempts'][0]['completion'], 'FAILED')

    def test_repeat_counts_completed_course_once(self):
        r = self.report()
        self.assertNotIn('2101', [c['course_code'] for c in r['remaining']['courses']])
        self.assertEqual(len(r['repeated_courses']), 1)

    def test_missing_code_is_preserved(self):
        self.t['semesters'][0]['courses'][0]['course_code'] = None
        r = self.report()
        self.assertEqual(len(r['course_attempts']), 4)
        self.assertIsNone(r['course_attempts'][0]['course_id'])

    def test_pre_missing_requires_complete_history_and_rule(self):
        self.relation_fixture()
        self.assertTrue(any(i['status'] == 'VIOLATION' for i in self.report()['audit']))
        self.rules['history_complete'] = False
        self.assertFalse(any(i['status'] == 'VIOLATION' for i in self.report()['audit']))

    def test_future_pass_does_not_satisfy_earlier_pre(self):
        r = self.relation_fixture()
        c = chart_for('1401-1402').by_id[r['related_course_id']][0]
        self.t['semesters'].append({'academic_year_start': 1402, 'term': 2,
                                   'courses': [{'course_code': c['course_code'], 'course_name': c['course_name'], 'credits': c['credits'], 'grade': 18}]})
        self.assertTrue(any(i['kind'] == 'PRE' and i['status'] == 'VIOLATION' for i in self.report()['audit']))
        self.t['semesters'][1]['academic_year_start'] = 1401
        self.assertTrue(any(i['kind'] == 'PRE' and i['status'] == 'CONFIRMED' for i in self.report()['audit']))

    def test_student_binding_prevents_cross_student_state(self):
        self.relation_fixture()
        self.rules['student_id'] = 'OTHER'
        self.assertFalse(any(i['status'] == 'VIOLATION' for i in self.report()['audit']))

    def test_summer_does_not_inherit_normal_limit(self):
        self.relation_fixture()
        self.t['semesters'][0]['term'] = 3
        self.t['semesters'][0]['courses'][0]['enrollment_status'] = 'ENROLLED'
        self.rules['term_states'] = {'1402-3': {'state': 'normal', 'source': 'TEST'}}
        self.rules['credit_limits'] = {'normal': {'min': 0, 'max': 1, 'source': 'TEST'}}
        item = next(i for i in self.report()['audit'] if i['kind'] == 'credit_load')
        self.assertEqual(item['status'], 'UNKNOWN')

    def test_all_academic_states_with_evidence(self):
        self.relation_fixture()
        self.t['semesters'][0]['courses'][0]['enrollment_status'] = 'ENROLLED'
        for state in ('normal', 'probation', 'honors', 'final'):
            self.rules['term_states'] = {'1402-1': {'state': state, 'source': 'TEST'}}
            self.rules['credit_limits'] = {state: {'min': 0, 'max': 30, 'source': 'TEST'}}
            item = next(i for i in self.report()['audit'] if i['kind'] == 'credit_load')
            self.assertEqual(item['status'], 'CONFIRMED')

    def test_elective_overlap_rejected(self):
        self.rules['requirements'] = {'source': 'TEST', 'mandatory_ids': ['a'], 'groups': [{'course_ids': ['a'], 'credits': 3}]}
        with self.assertRaises(ValueError): self.report()

    def test_all_three_charts_load(self):
        for name in ('1395-1400', '1401-1402', '1403-plus'):
            self.assertTrue(analyze_transcript(self.t, name)['remaining']['courses'])

    def test_duplicate_semester_never_creates_violation(self):
        self.relation_fixture()
        self.t['semesters'] *= 2
        self.assertFalse(any(i['status'] == 'VIOLATION' for i in self.report()['audit']))

    def test_elective_balance_counts_unique_passes(self):
        self.relation_fixture()
        c = chart_for('1401-1402').by_code[self.t['semesters'][0]['courses'][0]['course_code']][0]
        self.rules['requirements'] = {'source': 'TEST', 'mandatory_ids': [], 'groups': [{'name': 'TEST', 'course_ids': [c['course_id']], 'credits': c['credits'] + 2}]}
        r = self.report()['remaining']
        self.assertEqual(r['exact_remaining_credits'], 2)
        self.rules['history_complete'] = False
        self.assertIsNone(self.report()['remaining']['exact_remaining_credits'])

    def test_credit_mismatch_not_counted_as_pass(self):
        self.relation_fixture()
        self.t['semesters'][0]['courses'][0]['credits'] = 29
        self.assertEqual(self.report()['course_attempts'][0]['completion'], 'UNKNOWN')

    def test_co_requires_enrollment_evidence(self):
        chart = chart_for('1401-1402')
        rel = next(r for r in chart.relations if r['relation_type'] == 'CO' and r['link_status'] == 'OK' and chart.by_id[r['course_id']][0]['validation_status'] == 'OK')
        self.t['semesters'] = [{'academic_year_start': 1402, 'term': 1, 'courses': []}]
        for cid in (rel['course_id'], rel['related_course_id']):
            c = chart.by_id[cid][0]
            self.t['semesters'][0]['courses'].append({'course_code': c['course_code'], 'course_name': c['course_name'], 'credits': c['credits'], 'grade': None})
        get = lambda: next(i for i in self.report()['audit'] if i['kind'] == 'CO' and i['course_id'] == rel['course_id'])
        self.assertEqual(get()['status'], 'UNKNOWN')
        self.t['semesters'][0]['courses'][1]['enrollment_status'] = 'ENROLLED'
        self.assertEqual(get()['status'], 'CONFIRMED')


if __name__ == '__main__': unittest.main()
