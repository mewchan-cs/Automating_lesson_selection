import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / 'backend'))
from analyzer import analyze_transcript, chart_for
from visual_summary import summarize_visual, load_knowledge, DATA


def sample(courses=None):
    return {'schema_version':'1.0','student':{'student_id':'DEMO-ONLY'},
            'semesters':[{'academic_year_start':1403,'term':1,'courses':courses or []}]}


def row(code,chart='1401-1402',grade=17):
    c = chart_for(chart).by_code[code][0]
    return {'course_code':code,'course_name':c['course_name'],'credits':c['credits'],'grade':grade}


POLICY = {'passing':{'minimum_grade':10,'zero_is_final':False,'source':'TEST ONLY — NOT UNIVERSITY POLICY'}}


def summary(chart='1401-1402',courses=None,policy=None):
    t = sample(courses)
    report = analyze_transcript(t,chart)
    return summarize_visual(report,t,chart_for(chart),policy=policy or {})


def all_options(group):
    return group['ready']+group['needs_review']+group['waiting']


class VisualSummaryTests(unittest.TestCase):
    def test_each_image_is_preserved_and_year_bound(self):
        for name,image in [('1395-1400','image-3.png'),('1401-1402','image-1.png'),('1403-plus','image-2.png')]:
            source,_ = load_knowledge(name)
            self.assertEqual(source['image'],image)
            self.assertEqual(hashlib.sha256((DATA/image).read_bytes()).hexdigest(),source['sha256'])

    def test_chart_and_base_analyzer_not_mutated(self):
        c = chart_for('1401-1402')
        before = json.dumps(c.data,ensure_ascii=False,sort_keys=True)
        summary()
        self.assertEqual(json.dumps(c.data,ensure_ascii=False,sort_keys=True),before)

    def test_direct_visual_courses_are_not_a_flat_legacy_list(self):
        r = summary()
        codes = {c['course_code'] for c in r['not_taken']}
        self.assertIn('30004',codes)
        self.assertNotIn('30100',codes)  # Graphic course is an option, not named in image 1.
        self.assertIn('30100',{c['course_code'] for g in r['option_groups'] for c in all_options(g)})

    def test_failed_attempt_excluded_from_never_taken(self):
        r = summary(courses=[row('30100',grade=0),row('30004',grade=8)])
        self.assertNotIn('30004',{c['course_code'] for c in r['not_taken']})
        self.assertNotIn('30100',{c['course_code'] for g in r['option_groups'] for c in all_options(g)})

    def test_optional_membership_not_mixed_with_ordinary_courses(self):
        group = next(g for g in summary()['option_groups'] if g['key']=='elective')
        self.assertIn('30100',{c['course_code'] for c in all_options(group)})
        self.assertNotIn('2101',{c['course_code'] for c in all_options(group)})

    def test_1403_specialty_and_elective_have_distinct_pools(self):
        r = summary('1403-plus')
        specialty = next(g for g in r['option_groups'] if g['key']=='specialty')
        elective = next(g for g in r['option_groups'] if g['key']=='elective')
        self.assertIn('CSE-201',{c['course_code'] for c in all_options(specialty)})
        self.assertIn('CSE-301',{c['course_code'] for c in all_options(elective)})
        self.assertNotIn('CSE-301',{c['course_code'] for c in all_options(specialty)})

    def test_focus_tracks_kept_separate(self):
        groups = [g for g in summary('1395-1400')['option_groups'] if g['key'].startswith('focus:')]
        self.assertGreater(len(groups),3)
        self.assertTrue(any('امنیت رایانه' in g['title'] for g in groups))
        for g in groups:
            ids = [c['course_id'] for c in all_options(g)]
            self.assertEqual(len(ids),len(set(ids)))

    def test_duplicate_package_rows_do_not_duplicate_options(self):
        for g in summary()['option_groups']:
            ids = [c['course_id'] for c in all_options(g)]
            self.assertEqual(len(ids),len(set(ids)))

    def test_missing_grade_policy_never_assumes_pass(self):
        r = summary(courses=[row('30001')])
        english2 = next(c for c in r['not_taken'] if c['course_code']=='30002')
        self.assertEqual(english2['availability']['status'],'UNKNOWN')
        r = summary(courses=[row('30001')],policy=POLICY)
        english2 = next(c for c in r['not_taken'] if c['course_code']=='30002')
        self.assertEqual(english2['availability']['status'],'READY')

    def test_zero_grade_not_final_by_default(self):
        r = summary(courses=[row('30001',grade=0)],policy=POLICY)
        self.assertEqual(next(c for c in r['not_taken'] if c['course_code']=='30002')['availability']['status'],'UNKNOWN')

    def test_known_missing_pre_is_waiting_not_available(self):
        c = next(c for c in summary()['not_taken'] if c['course_code']=='30002')
        self.assertEqual(c['availability']['status'],'WAITING')

    def test_corequisite_bundle(self):
        r = summary()
        nodes = {c['course_code']:c for c in r['not_taken']}
        for code in ('30004','30005'):
            self.assertEqual(nodes[code]['availability']['status'],'READY')
        self.assertIn(nodes['30005']['course_id'],nodes['30004']['availability']['concurrent_ids'])

    def test_corequisite_pending_taken_partner_not_recommended(self):
        r = summary(courses=[row('30004',grade=None)])
        c = next(c for c in r['not_taken'] if c['course_code']=='30005')
        self.assertNotEqual(c['availability']['status'],'READY')

    def test_visual_code_conflict_never_merged_with_legacy_code(self):
        r = summary(courses=[row('30045')])
        self.assertNotIn('30128',{c['course_code'] for c in r['not_taken']})
        self.assertIn('30128',{c['course_code'] for c in r['uncertain_visual_courses']})

    def test_unknown_unrelated_course_does_not_hide_all_remaining(self):
        r = summary(courses=[{'course_code':'OFF-CHART','course_name':'درس نامرتبط نمونه','credits':2,'grade':15}])
        self.assertTrue(r['not_taken'])
        self.assertEqual(len(r['needs_matching']),1)

    def test_exact_name_with_unknown_code_withheld_not_equated(self):
        c = row('30004');c['course_code']='UNKNOWN'
        r = summary(courses=[c])
        self.assertNotIn('30004',{x['course_code'] for x in r['not_taken']})
        self.assertIn('30004',{x['course_code'] for x in r['uncertain_visual_courses']})

    def test_missing_code_is_preserved_without_aborting(self):
        c = row('30004');c['course_code']=None
        r = analyze_transcript(sample([c]),'1401-1402')
        self.assertEqual(len(r['course_attempts']),1)
        self.assertTrue(r['visual_summary']['needs_matching'])

    def test_1403_codes_not_invented_for_project_or_general(self):
        r = summary('1403-plus')
        self.assertTrue(r['code_notice'])
        self.assertTrue(any(c['course_name']=='پروژه کارشناسی' and c['course_code'] is None for c in r['not_taken']))
        self.assertTrue(any(c['course_name']=='زبان انگلیسی' and c['course_code'] is None for c in r['not_taken']))

    def test_no_quota_or_group_satisfaction_inferred(self):
        r = summary(courses=[row('30100')])
        group = next(g for g in r['option_groups'] if g['key']=='elective')
        self.assertEqual(group['previously_taken_count'],1)
        self.assertIsNone(group['required_slots_remaining'])

    def test_policy_requires_official_source(self):
        bad = copy.deepcopy(POLICY);bad['passing']['source']=''
        with self.assertRaises(ValueError): summary(policy=bad)

    def test_student_results_not_cached(self):
        first = summary(courses=[row('1107')])
        second = summary()
        self.assertNotIn('1107',{c['course_code'] for c in first['not_taken']})
        self.assertIn('1107',{c['course_code'] for c in second['not_taken']})


if __name__=='__main__': unittest.main()
