import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from analyzer import analyze_transcript, chart_for


def transcript(courses=None):
    return {'schema_version':'1.0','student':{'student_id':'VISUAL-TEST'},
            'semesters':[{'academic_year_start':1403,'term':1,'courses':courses or []}]}


def course(code, grade=17, chart='1401-1402'):
    c = chart_for(chart).by_code[code][0]
    return {'course_code':code,'course_name':c['course_name'],'credits':c['credits'],'grade':grade}


POLICY = {'passing':{'minimum_grade':10,'zero_is_final':False,'source':'TEST ONLY'}}


class VisualPriorityTests(unittest.TestCase):
    def suggestions(self, chart='1401-1402', courses=None, rules=None):
        return analyze_transcript(transcript(courses), chart, rules or {})['recommendations']

    def test_images_preserved_and_bound(self):
        for name in ('1395-1400','1401-1402','1403-plus'):
            c = chart_for(name)
            data = (ROOT / 'backend/visual_charts' / c.visual['image']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), c.visual['sha256'])

    def test_1403_uses_second_image_per_user_confirmation(self):
        c = chart_for('1403-plus')
        self.assertEqual(c.visual['image'],'image-2.png')
        self.assertEqual(c.visual['year_source'],'user_confirmation_2026-10-28')

    def test_visual_relation_overrides_legacy(self):
        c = chart_for('1403-plus')
        row = c.by_code['CSE-121'][0]
        pre = [r['related_course_code'] for r in c.relations if r['course_id'] == row['course_id'] and r['relation_type'] == 'PRE']
        self.assertEqual(pre,['CSE-120'])

    def test_visual_credits_override_legacy_shape(self):
        self.assertEqual(chart_for('1403-plus').by_code['CSE-120'][0]['credits'],2)

    def test_visual_code_conflict_not_silently_aliased(self):
        for chart, visual, old in [('1401-1402','30128','30045'),('1395-1400','291478','291503')]:
            c = chart_for(chart)
            self.assertTrue(c.by_code[visual])
            self.assertFalse(c.by_code.get(old))
            r = self.suggestions(chart)
            self.assertNotIn(visual,{x['course_code'] for x in r['priority'] + r['other']})
            self.assertTrue(r['visual_conflicts'])

    def test_priority_is_earliest_available_visual_semester(self):
        r = self.suggestions()
        self.assertTrue(r['priority'])
        self.assertEqual({x['suggested_semester'] for x in r['priority']},{1})
        self.assertTrue(all(x['suggested_semester'] is None or x['suggested_semester'] > 1 for x in r['other']))

    def test_never_taken_excludes_failed_attempt_too(self):
        r = self.suggestions(courses=[course('1107',0)])
        self.assertNotIn('1107',{x['course_code'] for x in r['priority']+r['other']})

    def test_passed_prerequisite_unlocks_next_course(self):
        r = self.suggestions(courses=[course('30001')],rules=POLICY)
        self.assertIn('30002',{x['course_code'] for x in r['priority']+r['other']})
        r = self.suggestions(courses=[course('30001')])
        self.assertNotIn('30002',{x['course_code'] for x in r['priority']+r['other']})

    def test_zero_does_not_unlock_prerequisite(self):
        r = self.suggestions(courses=[course('30001',0)],rules=POLICY)
        self.assertNotIn('30002',{x['course_code'] for x in r['priority']+r['other']})

    def test_corequisite_bundle_is_retained(self):
        r = self.suggestions()
        rows = {x['course_code']:x for x in r['priority']+r['other']}
        self.assertIn('30004', rows)
        self.assertIn('30005', rows)
        self.assertIn(rows['30005']['course_id'], rows['30004']['concurrent_course_ids'])

    def test_unknown_attempt_blocks_partner_bundle(self):
        r = self.suggestions(courses=[course('30004',None)])
        self.assertNotIn('30005',{x['course_code'] for x in r['priority']+r['other']})

    def test_codes_missing_in_second_image_are_not_invented(self):
        r = self.suggestions('1403-plus')
        self.assertTrue(r['code_notice'])
        self.assertTrue(all(x['course_code'] for x in r['priority']+r['other']))
        self.assertFalse(any(x['course_name'] == 'پروژه کارشناسی' for x in r['priority']+r['other']))
        self.assertTrue(any(x['kind'] == 'missing_code' for x in r['visual_slots']))

    def test_unknown_credit_condition_withheld(self):
        r = self.suggestions('1395-1400')
        self.assertNotIn('291496',{x['course_code'] for x in r['priority']+r['other']})
        self.assertTrue(any(x['course_code']=='291496' for x in r['withheld']))

    def test_no_prerequisite_from_other_cohort(self):
        c = chart_for('1395-1400')
        physics = c.by_code['231480'][0]
        pre = [r['related_course_code'] for r in c.relations if r['course_id'] == physics['course_id']]
        self.assertEqual(pre,['271477'])

    def test_unpictured_existing_courses_follow_visual_courses(self):
        r = self.suggestions()
        visual = [x for x in r['other'] if x['source_image']]
        legacy = [x for x in r['other'] if not x['source_image']]
        self.assertTrue(legacy)
        self.assertEqual(r['other'], visual+legacy)

    def test_unmapped_portal_code_does_not_recommend_all_as_never_taken(self):
        r = self.suggestions('1403-plus', [{'course_code':'UNKNOWN-PORTAL','course_name':'نام نامطمئن','credits':3,'grade':18}])
        self.assertEqual(r['priority'],[])
        self.assertEqual(r['other'],[])
        self.assertIn('کدهای نامنطبق',r['notice'])


if __name__ == '__main__': unittest.main()
