"""Course/credit completion only: no GPA status, enrollment caps or PRE/CO gate."""
import math
from visual_summary import normalized


def valid_number(n):
    return type(n) in (int,float) and math.isfinite(n) and 0<=n<=10000


def build_report(report,chart,source,courses,passed,ledger,plan,history_complete):
    reported=report['overview'].get('latest_reported_passed_credits')
    reported=reported if valid_number(reported) else None
    verified=sum(courses[cid]['credits'] for cid in passed)
    total=plan.get('plan_total') if plan else None
    counted=plan.get('counted_credits') if plan else None
    result={'mode':'graduation','chart':chart.chart,'basis':'supplied_visual_reference_plan',
            'scope':'passed_courses_and_category_credits_only','status':'SOURCE_INCOMPLETE',
            'title':'منبع لازم برای مقایسهٔ واحدها کامل نیست',
            'reason':(plan.get('source_issues') or [plan.get('reason')])[0] if plan else 'جدول الزامات قابل اجرا در دسترس نیست.',
            'required_credits':total,'counted_passed_credits':counted,'verified_chart_passed_credits':verified,
            'reported_passed_credits':reported,'remaining_to_confirm':None,'exact_remaining_credits':None,
            'minimum_total_shortage':max(0,total-reported) if total is not None and reported is not None else None,
            'categories':[],'missing_courses':[],'groups':plan.get('groups',[]) if plan else [],
            'unresolved_rows':[],'passed_not_allocated':[],
            'note':'قبولی نمرهٔ ۱۰ و بالاتر است؛ هر درس فقط یک‌بار در سهم واحدها شمرده می‌شود. مقایسه بر پایهٔ برنامهٔ مرجع چارت انتخابی است.'}
    for a in ledger:
        if not a['review_course_id'] or not a['credits_ok'] or a['outcome']=='UNKNOWN' and a['review_course_id'] not in passed:
            result['unresolved_rows'].append({'course_name':a['course_name'],'course_code':a['course_code'],
                'credits':a['credits'],'grade':a['grade'],'reason':'کد قابل تطبیق نیست' if not a['review_course_id'] else 'واحد با چارت اختلاف دارد' if not a['credits_ok'] else 'نمره قطعی قابل قبول در دسترس نیست'})
    if total is None or counted is None:return result
    required_ids=set(plan.get('required_course_ids',[]))
    visual={n['course_id']:n for n in source['nodes']}
    labels={'O':'عمومی','OE':'عمومی','OEK':'عمومی','P':'پایه','A':'اصلی','TE':'تخصصی الزامی',
            'T':'تخصصی','TEE':'تخصصی','TEK':'اختیاری','EK':'اختیاری','TR':'تمرکز','MEP':'مهارتی'}
    categories={}
    def category(key,required,confirmed):
        c=categories.setdefault(key,{'name':key,'required':0,'confirmed':0,'remaining_to_confirm':0})
        c['required']+=required;c['confirmed']+=confirmed;c['remaining_to_confirm']=max(0,c['required']-c['confirmed'])
    allocated_ids=set(required_ids & set(passed))
    for cid in required_ids:
        c=courses[cid];kind=c.get('course_type') or visual.get(cid,{}).get('course_type')
        category(labels.get(kind,'سایر الزامی‌های چارت'),c['credits'],c['credits'] if cid in passed else 0)
    for g in result['groups']:
        category(g.get('category') or 'انتخابی',g['required'],g['confirmed'])
        allocated_ids.update(g.get('assigned_course_ids',[]))
        g['choices']=[{'course_id':cid,'course_name':courses[cid]['course_name'],'course_code':courses[cid].get('course_code'),'credits':courses[cid]['credits']} for cid in g.get('candidate_course_ids',[])]
    result['categories']=list(categories.values())
    for c in plan['missing_required']:
        attempts=[a for a in ledger if a['review_course_id']==c['course_id']]
        possible=[a for a in ledger if not a['review_course_id'] and (a.get('course_id')==c['course_id'] or normalized(a['course_name'])==normalized(c['course_name']))]
        status='MATCH_REQUIRED' if possible else 'GRADE_PENDING' if any(a['outcome']=='UNKNOWN' for a in attempts) else 'FAILED' if attempts else 'NOT_TAKEN'
        result['missing_courses'].append(dict(c,credits=courses[c['course_id']]['credits'],completion_status=status))
    result['passed_not_allocated']=[{'course_id':cid,'course_name':courses[cid]['course_name'],'course_code':courses[cid].get('course_code'),'credits':courses[cid]['credits']} for cid in sorted(set(passed)-allocated_ids)]
    remaining=max(0,total-counted)
    result['remaining_to_confirm']=remaining
    if plan.get('remaining_credits') is not None:result['exact_remaining_credits']=plan['remaining_credits']
    if sum(c['required'] for c in result['categories'])!=total:
        result.update(status='SOURCE_INCONSISTENT',title='جمع دسته‌های چارت نیازمند اصلاح است',reason='جمع واحد گروه‌ها با کل برنامه یکسان نیست.')
        return result
    if remaining==0:
        if reported is not None and reported<counted:
            result.update(status='TOTALS_CONFLICT',title='بین جمع سامانه و دروس اختلاف وجود دارد',reason='واحدهای قبول‌شدهٔ ردیف‌ها بیشتر از جمع قبولی اعلام‌شدهٔ سامانه است؛ تأیید تکمیل متوقف شد.')
        else:
            result.update(status='COMPLETE',title='دروس و واحدهای لازمِ چارت تکمیل شده‌اند',reason='تمام الزامی‌ها و سهم گروه‌ها با قبولی حداقل ۱۰، بدون شمارش تکراری، تکمیل‌اند.',exact_remaining_credits=0)
    elif reported is not None and reported<total:
        result.update(status='NOT_COMPLETE',title='واحدهای لازم برای فارغ‌التحصیلی تکمیل نیست',
                      reason=f'طبق جمع قبولی سامانه، حداقل {total-reported:g} واحد تا مجموع {total:g} واحدِ برنامه کم است؛ کسری هر دسته در جدول آمده است.')
    elif history_complete and not result['unresolved_rows']:
        result.update(status='NOT_COMPLETE',title='دروس یا سهم گروه‌های چارت تکمیل نیست',
                      reason=f'{remaining:g} واحد از الزامات مشخصِ این برنامه هنوز تکمیل نشده است.',exact_remaining_credits=remaining)
    else:
        result.update(status='NOT_CONFIRMED',title='در کارنامهٔ موجود، تکمیل الزامات احراز نشد',
                      reason=f'{remaining:g} واحد از سهم برنامه هنوز با قبولی قابل تطبیق احراز نشده؛ موارد مؤثر در نتیجه در فهرست پایین مشخص‌اند.')
    if plan.get('source_issues') and remaining>0 and not (reported is not None and reported<total):
        result.update(status='ALLOCATION_REVIEW',title='تخصیص درس‌ها به گروه نیازمند تعیین تکلیف است',reason=plan['source_issues'][0],exact_remaining_credits=None)
    return result
