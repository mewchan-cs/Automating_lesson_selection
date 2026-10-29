import json
import unittest
from test_academic_review import BASE,PASS,CHART,ROOT,sample,row
from analyzer import analyze_transcript,chart_for
from academic_review import review_academics
from visual_summary import load_knowledge
from visual_plan import allocate,check_plan


def completed_plan(omit_project=False):
    source,_=load_knowledge(CHART)
    plan=json.loads((ROOT/'backend/visual_data/plans.json').read_text(encoding='utf-8'))[CHART]
    required=set(plan['required_ids'])
    terms={(1401+(i-1)//2,1+(i-1)%2):{'academic_year_start':1401+(i-1)//2,'term':1+(i-1)%2,'courses':[],
          'reported_summary':{'term_gpa':15,'cumulative_gpa':15}} for i in range(1,9)}
    for node in source['nodes']:
        if node['course_id'] not in required or omit_project and node['base_course_code']=='30028':continue
        n=node['suggested_semester'];key=(1401+(n-1)//2,1+(n-1)%2)
        if node['base_course_code']=='30027':
            key=(1403,3);terms[key]={'academic_year_start':1403,'term':3,'courses':[],'reported_summary':{'term_gpa':15,'cumulative_gpa':15}}
        terms[key]['courses'].append({'course_code':node['course_code'],'course_name':node['course_name'],'credits':node['credits'],'grade':17})
    for code,n in [('272481',5),('272461',6),('30115',7),('30109',8),('30111',7),('30107',8),('30114',8)]:
        terms[(1401+(n-1)//2,1+(n-1)%2)]['courses'].append(row(code))
    return {'schema_version':'1.0','student':{'student_id':'FULL-PLAN-DEMO'},'semesters':list(terms.values()),'extraction':{'history_complete':True}}


class VisualPlanTests(unittest.TestCase):
    def test_overlapping_options_not_double_counted(self):
        groups=[{'name':'A','ids':['x'],'credits':3},{'name':'B','ids':['x'],'credits':3}]
        coverage=allocate(groups,{'x'},{'x':{'credits':3}})
        self.assertEqual(sum(g['confirmed'] for g in coverage),3)

    def test_allocation_finds_global_solution_instead_of_greedy_choice(self):
        groups=[{'name':'A','ids':['x','y'],'credits':3},{'name':'B','ids':['x'],'credits':3}]
        coverage=allocate(groups,{'x','y'},{'x':{'credits':3},'y':{'credits':3}})
        self.assertEqual(sum(g['confirmed'] for g in coverage),6)
        ids=[cid for g in coverage for cid in g['assigned_course_ids']]
        self.assertEqual(len(ids),len(set(ids)))

    def test_same_term_final_grade_is_evidence_of_corequisite_registration(self):
        t=sample(courses=[row('30004'),row('30005')])
        r=analyze_transcript(t,CHART,academic_review=True)['academic_review']
        checks=[c for a in r['course_audit'] for c in a['checks'] if c['kind']=='CO']
        self.assertTrue(checks)
        self.assertTrue(all(c['status']=='CONFIRMED' for c in checks))

    def test_portal_totals_can_verify_loaded_history_automatically(self):
        t=sample();t['extraction']={};t['semesters'][0]['reported_summary'].update(cumulative_attempted_credits=3,cumulative_passed_credits=3)
        r=analyze_transcript(t,CHART,academic_review=True)['academic_review']
        self.assertEqual(r['history_verification']['source'],'portal_totals_reconciled')
        self.assertEqual(r['graduation']['exact_remaining_credits'],139)

    def test_inconsistent_portal_totals_do_not_verify_history(self):
        t=sample();t['extraction']={};t['semesters'][0]['reported_summary'].update(cumulative_attempted_credits=30,cumulative_passed_credits=3)
        r=analyze_transcript(t,CHART,academic_review=True)['academic_review']
        self.assertFalse(r['history_verification']['complete'])

    def test_conflicting_1403_diagram_does_not_get_false_graduation(self):
        c=chart_for('1403-plus').by_code['SCI-101'][0]
        t=sample(courses=[{'course_code':c['course_code'],'course_name':c['course_name'],'credits':c['credits'],'grade':17}])
        r=analyze_transcript(t,'1403-plus',academic_review=True)['academic_review']
        self.assertEqual(r['decision']['code'],'NORMAL')
        self.assertEqual(r['credit_limit']['maximum'],20)
        self.assertIsNone(r['graduation']['exact_remaining_credits'])
        self.assertIn('تیتر',r['decision']['detail'])

    def test_full_reference_plan_can_be_confirmed_without_user_marking_courses(self):
        r=analyze_transcript(completed_plan(),CHART,academic_review=True)['academic_review']
        self.assertEqual(r['graduation']['exact_remaining_credits'],0)
        self.assertEqual(r['decision']['code'],'GRADUATED_ACADEMICALLY',
                         [(a['course_code'],a['checks']) for a in r['course_audit'] if a['status']!='CONFIRMED'])

    def test_last_project_produces_final_term_and_waiver_automatically(self):
        r=analyze_transcript(completed_plan(omit_project=True),CHART,academic_review=True)['academic_review']
        self.assertEqual(r['graduation']['exact_remaining_credits'],3)
        self.assertEqual(r['decision']['code'],'FINAL_TERM')
        self.assertTrue(r['credit_limit']['waive_pre_corequisites'])

    def test_older_plan_counts_summer_internship_and_keeps_focus_coherent(self):
        source,_=load_knowledge('1395-1400')
        plan=json.loads((ROOT/'backend/visual_data/plans.json').read_text(encoding='utf-8'))['1395-1400']
        chart=chart_for('1395-1400')
        courses={cid:dict(rows[0]) for cid,rows in chart.by_id.items()}
        for n in source['nodes']:courses[n['course_id']]=n
        passed=set(plan['required_ids'])
        for group in plan['variants'][0]['groups']:
            units=0
            for cid in group['ids']:
                if cid in passed:continue
                passed.add(cid);units+=courses[cid]['credits']
                if units>=group['credits']:break
        result=check_plan(chart,source,courses,passed,[],[],True)
        self.assertEqual(result['plan_total'],141)
        self.assertEqual(result['remaining_credits'],0)

    def test_mixed_focus_is_not_automatically_certified(self):
        source,_=load_knowledge('1395-1400')
        plan=json.loads((ROOT/'backend/visual_data/plans.json').read_text(encoding='utf-8'))['1395-1400']
        chart=chart_for('1395-1400');courses={cid:dict(rows[0]) for cid,rows in chart.by_id.items()}
        for n in source['nodes']:courses[n['course_id']]=n
        ai=next(v for v in plan['variants'] if v['name']=='هوش مصنوعی')
        software=next(v for v in plan['variants'] if 'سیستم' in v['name'] and 'نرم' in v['name'])
        mixed=set(ai['groups'][-1]['ids'][:2]+software['groups'][-1]['ids'][:2])
        result=check_plan(chart,source,courses,set(plan['required_ids'])|mixed,[],[],True)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertIsNone(result['remaining_credits'])
        self.assertIn('چند مسیر',result['reason'])


if __name__=='__main__':unittest.main()
