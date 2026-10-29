"""Integration checks using the actual saved policy, without test policy injection."""
import unittest
from test_academic_review import sample,row,CHART
from analyzer import analyze_transcript,chart_for


class SavedPassingPolicyTests(unittest.TestCase):
    def test_ten_passes_and_below_ten_does_not_for_every_cohort(self):
        for chart,code in [('1395-1400','1107'),('1401-1402','1107'),('1403-plus','SCI-101')]:
            c=chart_for(chart).by_code[code][0]
            for grade,expected in [(10,c['credits']),(9.99,0),(None,0)]:
                with self.subTest(chart=chart,grade=grade):
                    t=sample(courses=[{'course_code':code,'course_name':c['course_name'],'credits':c['credits'],'grade':grade}])
                    r=analyze_transcript(t,chart,academic_review=True)
                    self.assertEqual(r['academic_review']['graduation']['confirmed_passed_chart_credits'],expected)

    def test_saved_threshold_unlocks_prerequisite_at_ten(self):
        for grade,expected in [(10,'READY'),(9.99,'WAITING'),(None,'UNKNOWN'),(0,'UNKNOWN')]:
            with self.subTest(grade=grade):
                r=analyze_transcript(sample(courses=[row('30001',grade=grade)]),CHART)
                english2=next(c for c in r['visual_summary']['not_taken'] if c['course_code']=='30002')
                self.assertEqual(english2['availability']['status'],expected)


if __name__=='__main__': unittest.main()
