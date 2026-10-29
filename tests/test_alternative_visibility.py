import unittest
from test_academic_review import sample,row,CHART
from analyzer import analyze_transcript


class AlternativeVisibilityTests(unittest.TestCase):
    def summary(self,courses=None):return analyze_transcript(sample(courses=courses),CHART)['visual_summary']

    def test_1402_revolution_is_visible_in_main_as_one_of_two(self):
        r=self.summary()
        group=next(g for g in r['main_alternatives'] if g['key']=='revolution')
        self.assertEqual(group['required_slots_remaining'],1)
        self.assertEqual({c['course_code'] for c in group['ready']},{'272481','272459'})
        self.assertEqual(group['completion_status'],'OPEN')

    def test_passing_political_thought_completes_same_visual_group(self):
        r=self.summary([row('272459',grade=10)])
        self.assertNotIn('revolution',{g['key'] for g in r['main_alternatives']})
        group=next(g for g in r['option_groups'] if g['key']=='revolution')
        self.assertEqual(group['required_slots_remaining'],0)

    def test_failing_revolution_does_not_complete_group(self):
        r=self.summary([row('272481',grade=9)])
        group=next(g for g in r['main_alternatives'] if g['key']=='revolution')
        self.assertEqual(group['completion_status'],'OPEN')
        self.assertEqual(group['retake_options'][0]['course_code'],'272481')
        self.assertIn('272459',{c['course_code'] for c in group['ready']})

    def test_ungraded_choice_is_not_silently_treated_as_passed(self):
        r=self.summary([row('272481',grade=None)])
        group=next(g for g in r['main_alternatives'] if g['key']=='revolution')
        self.assertEqual(group['completion_status'],'UNKNOWN')

    def test_same_fix_applies_to_history_alternative(self):
        r=self.summary()
        self.assertIn('history',{g['key'] for g in r['main_alternatives']})
        r=self.summary([row('272461',grade=17)])
        self.assertNotIn('history',{g['key'] for g in r['main_alternatives']})


if __name__=='__main__':unittest.main()
