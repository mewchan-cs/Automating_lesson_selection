"""Reconcile the pictured reference plan and allocate options without double counting.

This certifies completion of the supplied plan, not an external graduation decree.
"""
import json
from pathlib import Path

DATA=Path(__file__).resolve().parent/'visual_data'


def allocate(groups,passed,courses):
    """Assign each whole course to at most one option group (bounded DP)."""
    caps=tuple(g['credits'] for g in groups)
    pools=[set(g['ids']) for g in groups]
    ids=sorted(set(passed)&set().union(*pools)) if pools else []
    states={tuple(0 for _ in groups):()}
    for cid in ids:
        units=courses[cid]['credits']
        additions={}
        for state,assignments in states.items():
            for index,pool in enumerate(pools):
                if cid not in pool or state[index]+units>caps[index]: continue
                next_state=state[:index]+(state[index]+units,)+state[index+1:]
                if next_state not in states and next_state not in additions:
                    additions[next_state]=assignments+((cid,index),)
        states.update(additions)
    best=max(states,key=lambda s:(sum(s),s))
    assignments=states[best]
    return [{'name':g['name'],'category':g.get('category'),'required':g['credits'],'confirmed':best[i],
             'remaining':g['credits']-best[i], 'assigned_course_ids':[cid for cid,index in assignments if index==i],
             'candidate_course_ids':sorted(set(g['ids'])-set(passed)) if best[i]<g['credits'] else []}
            for i,g in enumerate(groups)]


def check_plan(chart,source,courses,passed,ledger,audit,history_complete,*,verify_enrollment=True):
    """Read reviewed plan requirements; fail closed on source inconsistencies."""
    plans=json.loads((DATA/'plans.json').read_text(encoding='utf-8'))
    plan=plans[chart.chart]
    result={'basis':'supplied_visual_reference_plan','source_image':source['image'],
            'plan_total':plan.get('total_credits'),'source_issues':plan.get('issues',[]),
            'status':'UNKNOWN','label':'نامشخص','reason':'منبع چارت باید تکمیل یا رفع اختلاف شود.',
            'counted_credits':None,'remaining_credits':None,'missing_required':[], 'groups':[],
            'balance_verified':False,'curriculum_complete':False}
    if not plan.get('verified'): return result
    required=set(plan['required_ids'])
    if any(cid not in courses for cid in required): raise ValueError('درس الزامی برنامه تصویری در داده پایه موجود نیست.')
    variants=plan.get('variants') or [{'name':'برنامه تصویر','groups':plan['groups']}]
    best=None
    for variant in variants:
        groups=variant['groups']
        for group in groups:
            if any(cid not in courses for cid in group['ids']): raise ValueError('گزینه برنامه تصویری در داده پایه موجود نیست.')
            if required & set(group['ids']): raise ValueError('درس الزامی نباید دوباره در سهم انتخابی شمرده شود.')
        allocated=sum(courses[cid]['credits'] for cid in required)+sum(g['credits'] for g in groups)
        if allocated!=plan['total_credits']: raise ValueError('جمع اجزای برنامه تصویری با مجموع بازبینی‌شده نمی‌خواند.')
        coverage=allocate(groups,passed,courses)
        earned=sum(g['confirmed'] for g in coverage)
        if best is None or earned>best[0]: best=(earned,variant['name'],coverage)
    missing=required-set(passed)
    counted=sum(courses[cid]['credits'] for cid in required & set(passed))+best[0]
    remaining=plan['total_credits']-counted
    result.update(counted_credits=counted,missing_required=[dict(course_id=cid,course_name=courses[cid]['course_name'],course_code=courses[cid].get('course_code')) for cid in sorted(missing)],
                  groups=best[2],selected_path=best[1],required_course_ids=sorted(required),remaining_to_confirm=remaining)
    focus_groups=[g for variant in variants for g in variant['groups'] if g.get('role')=='focus']
    if focus_groups:
        union=set().union(*(set(g['ids']) for g in focus_groups))
        completed_mixed=sum(courses[cid]['credits'] for cid in union & set(passed))
        focus_coverage=[g for g in best[2] if g['name'].startswith('چهار درس از تمرکز ')]
        if focus_coverage and focus_coverage[0]['remaining']>0 and completed_mixed>=focus_coverage[0]['required']:
            result['reason']='دروس تمرکز بین چند مسیر پخش شده‌اند؛ مجاز بودن اختلاط مسیرها در تصویر مشخص نیست.'
            result['source_issues'].append(result['reason'])
            return result
    # Unknown old attempts cannot add/remove credits when a later exact pass is known.
    known_balance=all(a['review_course_id'] and a['credits_ok'] and
                      (a['outcome']!='UNKNOWN' or a['review_course_id'] in passed) for a in ledger)
    if not verify_enrollment:
        result['remaining_credits']=remaining if history_complete and known_balance else None
        result['balance_verified']=True
        if remaining==0:
            result.update(status='COMPLETE',label='دروس و سهم واحدهای چارت تکمیل شده',curriculum_complete=True,
                          remaining_credits=0,reason='تمام الزامی‌ها و سهم گروه‌ها با قبولی حداقل ۱۰ و بدون شمارش دوباره تکمیل شده‌اند.')
        else:
            result.update(status='INCOMPLETE',label='در کارنامه موجود، الزامات چارت کامل نیست',
                          reason=f'{remaining:g} واحد از الزامات چارت هنوز با قبولی قابل تطبیق احراز نشده است.')
        return result
    if not history_complete or not known_balance:
        result['reason']='کامل بودن کارنامه یا تطبیق و قبولی یک یا چند درس، روی نتیجه اثر می‌گذارد.'
        return result
    result['remaining_credits']=remaining
    result['balance_verified']=all(a['status']=='CONFIRMED' for a in audit)
    if remaining>0:
        result.update(status='INCOMPLETE',label='برنامه درسی هنوز کامل نشده',reason=f'{remaining:g} واحد از برنامه تصویری باقی مانده است.')
    elif result['balance_verified']:
        result.update(status='COMPLETE',label='دروس لازمِ چارت تکمیل شده',curriculum_complete=True,
                      reason='همه درس‌های مشخص و سهم گزینه‌های برنامه تصویری، بدون شمارش تکراری احراز شده‌اند.')
    else: result['reason']='واحدهای برنامه تکمیل‌اند؛ یک ایراد واقعی در سابقه اخذ هنوز تعیین تکلیف نشده است.'
    return result
