import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from analyzer import analyze_transcript,chart_for,DataError
from academic_review import review_academics,apply_final_waiver

BASE=json.loads((ROOT/'backend/academic_policy.json').read_text(encoding='utf-8'))
PASS={'passing':{'minimum_grade':10,'zero_is_final':False,'source':'TEST ONLY'}}
CHART='1401-1402'


def row(code='1107',grade=17):
    c=chart_for(CHART).by_code[code][0]
    return {'course_code':code,'course_name':c['course_name'],'credits':c['credits'],'grade':grade}


def sample(gpa=15,courses=None):
    return {'schema_version':'1.0','student':{'student_id':'TEST-ACADEMIC'},
            'semesters':[{'academic_year_start':1402,'term':1,'courses':[row()] if courses is None else courses,
                          'reported_summary':{'term_gpa':gpa,'cumulative_gpa':15}}],
            'extraction':{'history_complete':True}}


def req_for(codes,groups=None):
    c=chart_for(CHART)
    ids=[c.by_code[code][0]['course_id'] for code in codes]
    groups=groups or []
    return {'required_ids':ids,'groups':groups,'total_credits':sum(c.by_id[i][0]['credits'] for i in ids)+sum(g['credits'] for g in groups),
            'minimum_cumulative_gpa':12,'all_requirements_defined':True,'other_conditions_resolved':True}


class AcademicReviewTests(unittest.TestCase):
    def review(self,t=None,config=None,passing=PASS,target='regular'):
        t=t or sample()
        report=analyze_transcript(t,CHART)
        return review_academics(report,t,chart_for(CHART),config=copy.deepcopy(config or BASE),passing_policy=passing,target=target)

    def test_boundaries_and_caps_exactly_as_user_requested(self):
        for gpa,state,cap in [(0,'probation',14),(11.99,'probation',14),(12,'normal',20),(16.99,'normal',20),(17,'honors',24),(20,'honors',24)]:
            with self.subTest(gpa=gpa):
                r=self.review(sample(gpa))
                self.assertEqual(r['academic_status']['state'],state)
                self.assertEqual(r['credit_limit']['maximum'],cap)
                self.assertIsNone(r['credit_limit']['minimum'])

    def test_all_three_cohorts_have_user_status_rules(self):
        for name in ('1395-1400','1401-1402','1403-plus'):
            t=sample(17)
            report=analyze_transcript(t,name)
            r=review_academics(report,t,chart_for(name),config=BASE,passing_policy=PASS)
            self.assertEqual(r['credit_limit']['maximum'],24)

    def test_optional_analysis_is_off_by_default(self):
        self.assertNotIn('academic_review',analyze_transcript(sample(),CHART))
        self.assertIn('academic_review',analyze_transcript(sample(),CHART,academic_review=True))
        with self.assertRaises(DataError): analyze_transcript(sample(),CHART,academic_review='yes')

    def test_latest_missing_gpa_not_replaced_with_earlier_gpa(self):
        t=sample(18)
        t['semesters'].append({'academic_year_start':1402,'term':2,'courses':[row('2101')],'reported_summary':{}})
        r=self.review(t)
        self.assertEqual(r['last_term']['semester'],'1402-2')
        self.assertIsNone(r['credit_limit']['maximum'])

    def test_order_of_source_terms_does_not_change_status(self):
        t=sample(18)
        t['semesters'].append({'academic_year_start':1402,'term':2,'courses':[row('2101')],'reported_summary':{'term_gpa':11}})
        t['semesters'].reverse()
        self.assertEqual(self.review(t)['academic_status']['state'],'probation')

    def test_ungraded_latest_term_does_not_produce_final_status(self):
        r=self.review(sample(18,[row(grade=None)]))
        self.assertEqual(r['academic_status']['status'],'UNKNOWN')
        self.assertIsNone(r['credit_limit']['maximum'])

    def test_zero_is_conservative_until_finality_configured(self):
        self.assertEqual(self.review(sample(11,[row(grade=0)]))['academic_status']['status'],'UNKNOWN')
        p=copy.deepcopy(PASS);p['passing']['zero_is_final']=True
        self.assertEqual(self.review(sample(11,[row(grade=0)]),passing=p)['academic_status']['state'],'probation')

    def test_summer_not_assigned_regular_cap(self):
        t=sample(18);t['semesters'][0]['term']=3
        self.assertIsNone(self.review(t)['credit_limit']['maximum'])
        self.assertIsNone(self.review(sample(18),target='summer')['credit_limit']['maximum'])

    def test_duplicate_term_is_unknown(self):
        t=sample(18);t['semesters']*=2
        self.assertEqual(self.review(t)['academic_status']['status'],'UNKNOWN')

    def test_complete_requirements_and_valid_courses_confirm_conditions(self):
        config=copy.deepcopy(BASE);config['graduation'][CHART]=req_for(['1107'])
        r=self.review(config=config)
        self.assertEqual(r['graduation']['status'],'CONFIRMED')
        self.assertEqual(r['graduation']['exact_remaining_credits'],0)
        self.assertFalse(r['credit_limit']['final_term_exception'])

    def test_total_credits_alone_not_graduation(self):
        config=copy.deepcopy(BASE);config['graduation'][CHART]=req_for(['2101'])
        r=self.review(config=config)
        self.assertEqual(r['graduation']['status'],'NOT_READY')
        self.assertEqual(r['graduation']['counted_credits'],0)
        self.assertTrue(r['graduation']['missing_required'])

    def test_passed_credit_not_attempted_credit(self):
        r=self.review(sample(courses=[row(grade=8)]))
        self.assertEqual(r['graduation']['confirmed_passed_chart_credits'],0)

    def test_repeat_failure_then_pass_counts_once(self):
        t=sample(15,[row(grade=8)])
        t['semesters'].append({'academic_year_start':1402,'term':2,'courses':[row(grade=17)],'reported_summary':{'term_gpa':17,'cumulative_gpa':15}})
        self.assertEqual(self.review(t)['graduation']['confirmed_passed_chart_credits'],3)

    def test_reviewed_visual_plan_supplies_requirements_without_manual_table(self):
        r=self.review()
        self.assertEqual(r['graduation']['status'],'NOT_READY')
        self.assertEqual(r['graduation']['required_total'],142)
        self.assertEqual(r['graduation']['exact_remaining_credits'],139)
        self.assertEqual(r['graduation']['basis'],'supplied_visual_reference_plan')

    def test_missing_passing_rule_does_not_report_zero_passed(self):
        self.assertIsNone(self.review(passing={})['graduation']['confirmed_passed_chart_credits'])

    def test_final_term_waiver_overrides_gpa_even_probation(self):
        config=copy.deepcopy(BASE);config['graduation'][CHART]=req_for(['1107','2101'])
        for gpa in (9,15,18):
            r=self.review(sample(gpa),config=config)
            self.assertTrue(r['credit_limit']['final_term_exception'])
            self.assertTrue(r['credit_limit']['waive_pre_corequisites'])
            self.assertEqual(r['credit_limit']['recommended_credits'],3)
            self.assertEqual(r['credit_limit']['maximum'],24)

    def test_24_remaining_qualifies_30_does_not(self):
        pool=['30006','30007','30011','30015','30017','30018','30019','30021','30023','30025']
        for amount,expected in ((24,True),(30,False)):
            ids=[chart_for(CHART).by_code[c][0]['course_id'] for c in pool[:amount//3]]
            config=copy.deepcopy(BASE);config['graduation'][CHART]=req_for(['1107'],[{'name':'TEST','ids':ids,'credits':amount}])
            r=self.review(sample(11),config=config)
            self.assertEqual(r['graduation']['exact_remaining_credits'],amount)
            self.assertEqual(r['credit_limit']['final_term_exception'],expected)
            self.assertEqual(r['credit_limit']['maximum'],24 if expected else 14)

    def test_incomplete_transcript_cannot_enable_final_exception(self):
        config=copy.deepcopy(BASE);config['graduation'][CHART]=req_for(['1107','2101'])
        t=sample();t['extraction']['history_complete']=False
        r=self.review(t,config=config)
        self.assertFalse(r['credit_limit']['final_term_exception'])
        self.assertIsNone(r['graduation']['exact_remaining_credits'])

    def test_credit_mismatch_prevents_graduation(self):
        config=copy.deepcopy(BASE);config['graduation'][CHART]=req_for(['1107'])
        t=sample();t['semesters'][0]['courses'][0]['credits']=2
        self.assertEqual(self.review(t,config=config)['graduation']['status'],'UNKNOWN')

    def test_wrong_code_not_accepted_by_name(self):
        t=sample();t['semesters'][0]['courses'][0]['course_code']='UNKNOWN'
        r=self.review(t)
        self.assertEqual(r['course_audit'][0]['status'],'UNKNOWN')
        self.assertEqual(r['graduation']['confirmed_passed_chart_credits'],0)

    def test_policy_overlap_rejected(self):
        config=copy.deepcopy(BASE);req=req_for(['1107']);req['groups']=[{'ids':req['required_ids'],'credits':3}];config['graduation'][CHART]=req
        with self.assertRaises(ValueError): self.review(config=config)

    def test_unrelated_source_scope_disables_limits(self):
        config=copy.deepcopy(BASE);config['scope_confirmed']=False
        self.assertIsNone(self.review(config=config)['credit_limit']['maximum'])

    def test_final_waiver_changes_only_needed_future_courses(self):
        config=copy.deepcopy(BASE);config['graduation'][CHART]=req_for(['1107','30007'])
        t=sample(11)
        report=analyze_transcript(t,CHART)
        review=review_academics(report,t,chart_for(CHART),config=config,passing_policy=PASS)
        audit_before=copy.deepcopy(review['course_audit'])
        apply_final_waiver(report['visual_summary'],review)
        advanced=next(c for c in report['visual_summary']['not_taken'] if c['course_code']=='30007')
        architecture=next(c for c in report['visual_summary']['not_taken'] if c['course_code']=='30015')
        self.assertTrue(advanced['availability']['final_term_waiver'])
        self.assertNotEqual(architecture['availability']['status'],'READY')
        self.assertEqual(review['course_audit'],audit_before)

    def test_unaudited_prior_enrollment_cannot_enable_final_exception(self):
        config=copy.deepcopy(BASE);config['graduation'][CHART]=req_for(['30007','2101'])
        r=self.review(sample(11,[row('30007')]),config=config)
        self.assertFalse(r['graduation']['balance_verified'])
        self.assertFalse(r['credit_limit']['final_term_exception'])

    def test_manual_prior_enrollment_confirmation_is_student_bound(self):
        config=copy.deepcopy(BASE);req=req_for(['30007','2101']);config['graduation'][CHART]=req
        req.update(prior_enrollment_confirmed=True,prior_enrollment_student_id='OTHER',prior_enrollment_source='TEST')
        t=sample(11,[row('30007')])
        self.assertFalse(self.review(t,config=config)['credit_limit']['final_term_exception'])
        req['prior_enrollment_student_id']='TEST-ACADEMIC'
        self.assertTrue(self.review(t,config=config)['credit_limit']['final_term_exception'])


if __name__=='__main__': unittest.main()
