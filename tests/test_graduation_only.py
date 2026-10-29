import copy
import unittest
from test_visual_plan import completed_plan
from test_academic_review import sample,row,CHART
from analyzer import analyze_transcript


def review(t):return analyze_transcript(t,CHART,academic_review=True,review_mode='graduation')['academic_review']


class GraduationOnlyTests(unittest.TestCase):
    def test_complete_plan_does_not_need_gpa_or_historical_preconditions(self):
        t=completed_plan()
        all_rows=[c for s in t['semesters'] for c in s['courses']]
        t['semesters']=[{'academic_year_start':1404,'term':3,'courses':all_rows,'reported_summary':{}}]
        t['extraction']={}
        r=review(t)
        self.assertEqual(r['status'],'COMPLETE')
        self.assertEqual(r['required_credits'],142)
        self.assertEqual(r['counted_passed_credits'],142)
        self.assertNotIn('academic_status',r)
        self.assertNotIn('credit_limit',r)
        self.assertNotIn('course_audit',r)

    def test_summer_missing_gpa_does_not_block_graduation_comparison(self):
        t=sample();t['semesters'][0]['term']=3;t['semesters'][0]['reported_summary']={'cumulative_passed_credits':3}
        r=review(t)
        self.assertEqual(r['status'],'NOT_COMPLETE')
        self.assertEqual(r['minimum_total_shortage'],139)

    def test_screenshot_like_90_matched_97_reported_is_not_globally_unknown(self):
        t=completed_plan();units=0
        for s in t['semesters']:
            keep=[]
            for c in s['courses']:
                if units+c['credits']<=90:keep.append(c);units+=c['credits']
            s['courses']=keep
        self.assertEqual(units,90)
        t['semesters'].append({'academic_year_start':1404,'term':3,
           'courses':[{'course_code':'UNMATCHED','course_name':'نمونه بدون تطبیق','credits':7,'grade':17}],
           'reported_summary':{'term_gpa':19.25,'cumulative_passed_credits':97}})
        r=review(t)
        self.assertEqual(r['verified_chart_passed_credits'],90)
        self.assertEqual(r['status'],'NOT_COMPLETE')
        self.assertEqual(r['minimum_total_shortage'],45)
        self.assertIsNone(r['exact_remaining_credits'])
        self.assertTrue(r['unresolved_rows'])

    def test_categories_reconcile_with_total_and_counted_credits(self):
        r=review(completed_plan(omit_project=True))
        self.assertEqual(sum(c['required'] for c in r['categories']),142)
        self.assertEqual(sum(c['confirmed'] for c in r['categories']),r['counted_passed_credits'])
        self.assertEqual(r['exact_remaining_credits'],3)
        self.assertIn('عمومی',{c['name'] for c in r['categories']})
        self.assertIn('تخصصی',{c['name'] for c in r['categories']})
        self.assertIn('اختیاری',{c['name'] for c in r['categories']})

    def test_total_enough_but_wrong_category_is_not_completion(self):
        t=completed_plan()
        for s in t['semesters']:s['courses']=[c for c in s['courses'] if c['course_code']!='2101']
        t['semesters'][-1]['courses'].append(row('30112'))
        t['semesters'][-1]['reported_summary']['cumulative_passed_credits']=142
        r=review(t)
        self.assertEqual(r['status'],'NOT_COMPLETE')
        self.assertTrue(any(c['course_code']=='2101' for c in r['missing_courses']))
        self.assertTrue(r['passed_not_allocated'])

    def test_failing_required_course_is_listed_and_not_counted(self):
        t=sample(courses=[row('1107',grade=9)])
        r=review(t)
        self.assertEqual(r['counted_passed_credits'],0)
        self.assertEqual(next(c for c in r['missing_courses'] if c['course_code']=='1107')['completion_status'],'FAILED')

    def test_repeat_pass_does_not_add_units(self):
        t=sample(courses=[row('1107')])
        t['semesters'].append({'academic_year_start':1402,'term':2,'courses':[row('1107')],'reported_summary':{}})
        self.assertEqual(review(t)['counted_passed_credits'],3)

    def test_partial_history_missing_rows_does_not_claim_exact_balance(self):
        t=sample();t['extraction']={}
        r=review(t)
        self.assertEqual(r['status'],'NOT_CONFIRMED')
        self.assertIsNone(r['exact_remaining_credits'])
        self.assertEqual(r['remaining_to_confirm'],139)

    def test_portal_total_conflict_prevents_false_complete(self):
        t=completed_plan()
        latest=max(t['semesters'],key=lambda s:(s['academic_year_start'],s['term']))
        latest['reported_summary']['cumulative_passed_credits']=90
        self.assertEqual(review(t)['status'],'TOTALS_CONFLICT')


if __name__=='__main__':unittest.main()
