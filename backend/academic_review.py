"""Evidence-bearing academic status, graduation and prospective credit limits.

No implicit university regulation. A policy must explicitly confirm applicability.
"""
import json
import math
from collections import defaultdict
from pathlib import Path

from visual_summary import load_knowledge, normalized, validate_policy, DATA

ROOT = Path(__file__).resolve().parent


def number(value, low=0, high=10000):
    return type(value) in (int,float) and math.isfinite(value) and low <= value <= high


def validate_config(config):
    if not isinstance(config,dict): raise ValueError('آیین‌نامه باید شیء JSON باشد.')
    status = config.get('status_rules')
    if status:
        if not isinstance(status,dict) or not number(status.get('probation_below'),0,20) or not number(status.get('honors_at_least'),0,20) or status['probation_below'] >= status['honors_at_least']:
            raise ValueError('آستانه وضعیت آموزشی نامعتبر است.')
        if (status.get('summer_affects_status') is not None and type(status.get('summer_affects_status')) is not bool) or not number(status.get('minimum_effective_credits')):
            raise ValueError('قاعده تابستان و حداقل واحد مؤثر باید صریح باشد.')
    limits = config.get('credit_limits')
    if limits:
        if not isinstance(limits,dict): raise ValueError('ساختار محدوده واحد نامعتبر است.')
        for name,rule in limits.items():
            if not isinstance(rule,dict) or not number(rule.get('min')) or not number(rule.get('max')) or rule['min'] > rule['max'] or type(rule.get('approval_required')) is not bool:
                raise ValueError('کف و سقف واحد و شرط تأیید باید صریح باشند.')
            if 'legal_minimum' in rule and (not number(rule['legal_minimum']) or rule['legal_minimum']>rule['max']):
                raise ValueError('کف قانونی واحد نامعتبر است.')
            if name in ('final','final_summer') and not number(rule.get('remaining_at_most')):
                raise ValueError('شرط واحد باقی‌مانده ترم آخر باید مشخص باشد.')
            if name in ('final','final_summer') and rule['remaining_at_most']>rule['max']:
                raise ValueError('مانده مجاز ترم آخر نمی‌تواند بیشتر از سقف همان ترم باشد.')
    graduation = config.get('graduation',{})
    if not isinstance(graduation,dict): raise ValueError('الزامات فارغ‌التحصیلی نامعتبر است.')
    for req in graduation.values():
        if not isinstance(req,dict) or not isinstance(req.get('required_ids'),list) or not isinstance(req.get('groups'),list) or not number(req.get('total_credits')) or req['total_credits']<=0 or not number(req.get('minimum_cumulative_gpa'),0,20):
            raise ValueError('جدول کامل الزامات و معدل فارغ‌التحصیلی باید ثبت شود.')
        ids = list(req['required_ids'])
        for group in req['groups']:
            if not isinstance(group,dict) or not isinstance(group.get('ids'),list) or not number(group.get('credits')):
                raise ValueError('گروه انتخابی فارغ‌التحصیلی نامعتبر است.')
            ids.extend(group['ids'])
        if any(not isinstance(cid,str) for cid in ids) or len(ids) != len(set(ids)):
            raise ValueError('شناسه تکراری یا هم‌پوشان در الزامات فارغ‌التحصیلی مجاز نیست.')
    return config


def review_academics(report, transcript, chart, *, target='regular', config=None, passing_policy=None,mode='academic'):
    if mode not in ('academic','graduation'):raise ValueError('نوع بررسی نامعتبر است.')
    if target not in ('regular','summer'): raise ValueError('نوع ترم آینده نامعتبر است.')
    config = validate_config(config if config is not None else json.loads((ROOT/'academic_policy.json').read_text(encoding='utf-8')))
    source_ok = isinstance(config.get('source'),str) and bool(config['source'].strip())
    applicable = source_ok and config.get('scope_confirmed') is True and chart.chart in config.get('applicable_charts',[])
    passing = validate_policy(passing_policy if passing_policy is not None else json.loads((DATA/'policy.json').read_text(encoding='utf-8')))
    source,_ = load_knowledge(chart.chart)
    visual = {n['course_id']:n for n in source['nodes']}
    courses = {cid:dict(rows[0], identity_uncertain=len({(r.get('course_code'),r.get('credits')) for r in rows})!=1) for cid,rows in chart.by_id.items()}
    for cid,node in visual.items():
        courses[cid] = dict(courses.get(cid,{}),course_id=cid,course_code=node['course_code'],course_name=node['course_name'],credits=node['credits'],identity_uncertain=False)
    by_code = defaultdict(set)
    for cid,c in courses.items():
        if c.get('course_code'): by_code[normalized(c['course_code'])].add(cid)
    def time(a): return a['academic_year_start'],a['term']
    counts = defaultdict(int)
    for term in report['semesters']: counts[time(term)] += 1
    history = defaultdict(list)
    ledger = []
    for index,a in enumerate(report['course_attempts']):
        ids = by_code.get(normalized(a['course_code']),set())
        cid = next(iter(ids)) if len(ids)==1 else None
        exact = cid is not None and not courses[cid].get('identity_uncertain')
        credits_ok = exact and courses[cid]['credits'] == a['credits']
        outcome = 'UNKNOWN'
        if credits_ok and passing and a['grade'] is not None and (a['grade'] != 0 or passing['zero_is_final']):
            outcome = 'PASSED' if a['grade'] >= passing['minimum_grade'] else 'FAILED'
        item = dict(a,attempt_ref=index,review_course_id=cid if exact else None,
                    credits_ok=bool(credits_ok),outcome=outcome)
        ledger.append(item)
        if exact: history[cid].append(item)
    passed = {cid for cid,rows in history.items() if any(a['outcome']=='PASSED' for a in rows)}
    latest = max(report['semesters'],key=time)
    latest_raw = [t for t in transcript['semesters'] if time(t)==time(latest)]
    last_key = f"{latest['academic_year_start']}-{latest['term']}"
    raw_summary = latest_raw[0].get('reported_summary') or {} if len(latest_raw)==1 else {}
    extraction=transcript.get('extraction')
    explicit_complete=isinstance(extraction,dict) and extraction.get('history_complete') is True
    reported_attempted=raw_summary.get('cumulative_attempted_credits')
    reported_passed=raw_summary.get('cumulative_passed_credits')
    verified_passed=sum(courses[cid]['credits'] for cid in passed)
    reconciled=(number(reported_attempted) and number(reported_passed)
                and abs(reported_attempted-report['overview']['attempted_credits_from_rows'])<0.001
                and abs(reported_passed-verified_passed)<0.001
                and all(a['review_course_id'] and a['credits_ok'] for a in ledger)
                and all(n==1 for n in counts.values()))
    history_complete=explicit_complete or reconciled
    last_gpa = latest.get('reported_term_gpa')
    final_grades = all(a['grade'] is not None for a in ledger if time(a)==time(latest)) and bool(latest['attempt_count'])
    zero_uncertain = any(a['grade']==0 for a in ledger if time(a)==time(latest)) and (not passing or not passing['zero_is_final'])
    state = {'status':'UNKNOWN','state':None,'label':'نامشخص','gpa_band':None,'reason':'نیازمند آیین‌نامه قابل اعمال','semester':last_key,'reported_gpa':last_gpa}
    status_rule = config.get('status_rules') or {}
    if mode=='academic' and applicable and status_rule:
        if not number(last_gpa,0,20): state['reason']='معدل رسمی آخرین نیمسال موجود نیست؛ معدل ترم قدیمی جایگزین نشده است.'
        else:
            band = 'probation' if last_gpa < status_rule['probation_below'] else 'honors' if last_gpa >= status_rule['honors_at_least'] else 'normal'
            state['gpa_band']=band
            effective = raw_summary.get('term_effective_credits')
            minimum = status_rule['minimum_effective_credits']
            if counts[time(latest)] != 1: state['reason']='چند رکورد برای آخرین نیمسال وجود دارد.'
            elif latest['term']==3 and status_rule['summer_affects_status'] is not True: state['reason']='اثر معدل تابستان بر وضعیت تعیین نشده یا طبق قانون تنظیم‌شده مستثناست؛ وضعیت ترم قدیمی خودکار جایگزین نمی‌شود.'
            elif not final_grades or zero_uncertain: state['reason']='نمرات آخرین نیمسال هنوز قطعی یا تعیین تکلیف نشده‌اند.'
            elif minimum > 0 and (not number(effective) or effective < minimum): state['reason']='حداقل واحد مؤثر لازم برای احراز وضعیت تأیید نشده است.'
            else:
                state.update(status='CONFIRMED',state=band,label={'probation':'مشروط','honors':'الف','normal':'عادی'}[band],reason='طبق معدل رسمی آخرین نیمسال و قانون تنظیم‌شده')
    # Audit code/credits separately from historical enrollment eligibility.
    relations = defaultdict(list)
    node_codes = {n['base_course_code']:n['course_id'] for n in visual.values()}
    unresolved_relations = set()
    for cid,c in courses.items():
        if cid in visual:
            n=visual[cid]
            if not n.get('relationship_reviewed') or not n.get('relationships_complete') or n.get('requires_unresolved_reference'):
                unresolved_relations.add(cid)
            for kind,key in (('PRE','prerequisites'),('CO','corequisites')):
                for code in n[key]:
                    ids=by_code.get(normalized(code),set())
                    target_id=node_codes.get(code) or (next(iter(ids)) if len(ids)==1 else None)
                    relations[cid].append((kind,target_id,n['source_image']))
        else:
            if c.get('validation_status')!='OK': unresolved_relations.add(cid)
            for r in chart.relations:
                if r.get('course_id')==cid:
                    relations[cid].append((r['relation_type'],r.get('related_course_id'),r.get('source_text')))
                    if r.get('link_status')!='OK': unresolved_relations.add(cid)
    audit=[]
    for a in (ledger if mode=='academic' else []):
        cid=a['review_course_id']
        checks=[]
        def add(kind,status,reason,evidence): checks.append(dict(kind=kind,status=status,reason=reason,evidence=evidence))
        add('matching','CONFIRMED' if cid else 'UNKNOWN','تطبیق دقیق با کد چارت' if cid else 'کد مفقود، نامنطبق یا متعارض با تصویر',{'code':a['course_code'],'course_id':cid})
        add('credits','CONFIRMED' if a['credits_ok'] else 'UNKNOWN','واحد مطابق چارت' if a['credits_ok'] else 'واحد یا تطبیق درس نیازمند بررسی',{'transcript':a['credits'],'chart':courses[cid]['credits'] if cid else None})
        if cid:
            if cid in unresolved_relations: add('conditions','UNKNOWN','شرط یا رابطه چارت نیازمند بازبینی است',{'source':source['image']})
            if counts[time(a)]!=1: add('history','UNKNOWN','نیمسال تکراری؛ سوابق نیازمند بررسی است',{'semester':time(a)})
            if len([b for b in history[cid] if time(b)==time(a)])>1:
                add('repeat','UNKNOWN','چند اخذ از یک درس در یک نیمسال نیازمند بررسی است',{'attempt_ref':a['attempt_ref']})
            if any(b['outcome']=='PASSED' for b in history[cid] if time(b)<time(a)):
                add('repeat','UNKNOWN','اخذ دوباره پس از قبولی قبلی نیازمند مجوز یا قاعده رسمی است',{'attempt_ref':a['attempt_ref']})
            node=visual.get(cid,{})
            if node.get('minimum_semester'):
                before_terms={time(t) for t in report['semesters'] if time(t)<time(a) and t['term']!=3}
                met=history_complete and len(before_terms)+1>=node['minimum_semester']
                add('semester','CONFIRMED' if met else 'UNKNOWN','شرط نیمسال احراز شد' if met else 'شرط نیمسال از تاریخچه موجود احراز نشد',{'observed_ordinal':len(before_terms)+1,'minimum':node['minimum_semester']})
            conditions=[r for r in chart.data['credit_conditions'] if r.get('course_id')==cid]
            if node.get('unresolved_credit_condition') and not conditions:
                add('credit_condition','UNKNOWN','متن شرط واحد هنوز تفسیر یکتا ندارد',node['unresolved_credit_condition'])
            for condition in conditions:
                required=condition.get('min_passed_credits')
                prior_passed={b['review_course_id'] for b in ledger if time(b)<time(a) and b['outcome']=='PASSED'}
                prior_units=sum(courses[i]['credits'] for i in prior_passed)
                met=number(required) and prior_units>=required
                add('credit_condition','CONFIRMED' if met else 'UNKNOWN','حداقل واحد با قبولی‌های قبلی احراز شد' if met else 'حداقل واحد شرط درس احراز نشد',{'prior_confirmed_passed':prior_units,'required':required})
            for kind,needed,proof in relations[cid]:
                prior=[b for b in history.get(needed,[]) if time(b)<time(a)]
                met=any(b['outcome']=='PASSED' for b in prior)
                concurrent=[b for b in history.get(needed,[]) if time(b)==time(a)]
                # Official active-registration evidence is required for CO confirmation.
                raw_concurrent=[c for t in transcript['semesters'] if time(t)==time(a) for c in t['courses']]
                if kind=='CO' and needed in courses and courses[needed].get('course_code'):
                    met=met or any(normalized(c.get('course_code'))==normalized(courses[needed].get('course_code')) and c.get('enrollment_status')=='ENROLLED' for c in raw_concurrent)
                    # A final, nonzero grade on the same-term official transcript
                    # is affirmative evidence that the corequisite was registered.
                    met=met or any(b['credits_ok'] and b['grade'] is not None and
                                   (b['grade']>0 or passing and passing['zero_is_final']) for b in concurrent)
                add(kind,'CONFIRMED' if met and needed and cid not in unresolved_relations else 'UNKNOWN',
                    'شرط رابطه با مدرک احراز شد' if met else 'قبولی قبلی یا ثبت هم‌زمان از سوابق موجود احراز نشد؛ حکم تخلف صادر نمی‌شود',
                    {'needed_id':needed,'history_refs':[b['attempt_ref'] for b in prior+concurrent],'source':proof})
        audit.append({'attempt_ref':a['attempt_ref'],'course_code':a['course_code'],'course_name':a['course_name'],
                      'semester':f"{a['academic_year_start']}-{a['term']}",'status':'CONFIRMED' if all(c['status']=='CONFIRMED' for c in checks) else 'UNKNOWN','checks':checks})
    req = config.get('graduation',{}).get(chart.chart)
    graduation={'status':'UNKNOWN','label':'نیازمند تکمیل قانون یا مدارک','reason':'تعداد واحد اخذشده به‌تنهایی برای فارغ‌التحصیلی کافی نیست؛ جدول کامل الزامات لازم است.',
                'confirmed_passed_chart_credits':sum(courses[cid]['credits'] for cid in passed) if passing else None,
                'reported_passed_credits':report['overview'].get('latest_reported_passed_credits'),
                'required_total':req.get('total_credits') if req else None,'counted_credits':None,
                'exact_remaining_credits':None,'balance_verified':False,'missing_required':[],'groups':[]}
    missing_policy=[]
    if not passing: missing_policy.append('قاعده قبولی درس و معنای نمره صفر')
    if not req or req.get('all_requirements_defined') is not True: missing_policy.append('فهرست کامل الزامی‌ها، سهم گروه‌ها و کل واحد مصوب')
    if missing_policy: graduation['reason']='برای نتیجه قطعی باید تعیین شود: '+'؛ '.join(missing_policy)
    if applicable and req and req.get('all_requirements_defined') is True:
        req_ids=set(req['required_ids']) | {cid for g in req['groups'] for cid in g['ids']}
        if any(cid not in courses or courses[cid].get('identity_uncertain') for cid in req_ids): raise ValueError('شناسه الزامات فارغ‌التحصیلی در چارت وجود ندارد یا مبهم است.')
        if any(sum(courses[cid]['credits'] for cid in set(g['ids']))<g['credits'] for g in req['groups']):
            raise ValueError('ظرفیت واحد گروه از سهم موردنیاز کمتر است.')
        missing=set(req['required_ids'])-passed
        counted=sum(courses[cid]['credits'] for cid in set(req['required_ids'])&passed)
        remaining=sum(courses[cid]['credits'] for cid in missing)
        group_deficit=False
        for g in req['groups']:
            earned=sum(courses[cid]['credits'] for cid in set(g['ids'])&passed)
            deficit=max(0,g['credits']-earned)
            counted+=min(earned,g['credits']);remaining+=deficit
            group_deficit=group_deficit or deficit>0
            graduation['groups'].append({'name':g.get('name','گروه انتخابی'),'required':g['credits'],'confirmed':earned,'remaining':deficit,
                                          'candidate_course_ids':sorted(set(g['ids'])-passed) if deficit else []})
        graduation.update(counted_credits=counted,missing_required=[{'course_id':cid,'course_code':courses[cid].get('course_code'),'course_name':courses[cid]['course_name']} for cid in sorted(missing)])
        # A complete curriculum must reconcile mandatory and group credit requirements.
        allocated=sum(courses[cid]['credits'] for cid in req['required_ids'])+sum(g['credits'] for g in req['groups'])
        data_complete=history_complete
        all_resolved=bool(passing) and all(a['review_course_id'] and a['credits_ok'] and a['outcome']!='UNKNOWN' for a in ledger) and all(n==1 for n in counts.values())
        cgpa=latest.get('reported_cumulative_gpa')
        if allocated != req['total_credits']: graduation['reason']='جمع الزامی‌ها و سهم گروه‌ها با کل واحد مصوب تطبیق ندارد.'
        elif not data_complete or not all_resolved: graduation['reason']='کامل بودن کارنامه، قبولی‌ها یا تطبیق دروس هنوز تأیید نشده است.'
        else:
            graduation['exact_remaining_credits']=remaining
            manual_verified=(req.get('prior_enrollment_confirmed') is True
                             and bool(report['student'].get('student_id'))
                             and req.get('prior_enrollment_student_id')==report['student']['student_id']
                             and isinstance(req.get('prior_enrollment_source'),str) and bool(req['prior_enrollment_source'].strip()))
            graduation['balance_verified']=all(a['status']=='CONFIRMED' for a in audit) or manual_verified
            if missing or group_deficit or counted<req['total_credits']:
                graduation.update(status='NOT_READY',label='هنوز واجد شرایط نیست',reason='درس الزامی یا سهم واحد یک گروه باقی مانده است.')
            elif not number(cgpa,0,20): graduation['reason']='معدل کل رسمی در دسترس نیست.'
            elif cgpa<req['minimum_cumulative_gpa']: graduation.update(status='NOT_READY',label='شرط معدل کل احراز نشد',reason='معدل کل از حداقل قانون تنظیم‌شده کمتر است.')
            elif any(a['status']!='CONFIRMED' for a in audit) or req.get('other_conditions_resolved') is not True:
                graduation['reason']='درستی اخذ دروس یا سایر شروط فارغ‌التحصیلی نیازمند بررسی است.'
            else: graduation.update(status='CONFIRMED',label='شرایط آموزشی تنظیم‌شده احراز شد',reason='واحد، دروس الزامی، سهم گروه‌ها، معدل کل و درستی اخذ دروس احراز شده‌اند؛ صدور مدرک با آموزش است.')
    visual_plan=None
    if applicable and not req:
        from visual_plan import check_plan
        visual_plan=check_plan(chart,source,courses,passed,ledger,audit,history_complete,verify_enrollment=mode!='graduation')
        graduation.update(required_total=visual_plan['plan_total'],counted_credits=visual_plan['counted_credits'],
                          exact_remaining_credits=visual_plan['remaining_credits'],balance_verified=visual_plan['balance_verified'],
                          missing_required=visual_plan['missing_required'],groups=visual_plan['groups'],
                          reason=visual_plan['reason'],basis='supplied_visual_reference_plan')
        if visual_plan['status']=='INCOMPLETE': graduation.update(status='NOT_READY',label='برنامه تصویری هنوز تکمیل نشده')
        elif visual_plan['status']=='COMPLETE': graduation.update(status='CURRICULUM_COMPLETE',label='شرایط درسی فارغ‌التحصیلی طبق چارت احراز شد')
        elif visual_plan['source_issues']: graduation['reason']=visual_plan['source_issues'][0]
    limit={'status':'UNKNOWN','target':target,'minimum':None,'maximum':None,'conditional_maximum':None,'recommended_credits':None,'final_term_exception':False,'waive_pre_corequisites':False,'reason':'نیازمند قاعده و وضعیت آموزشی تأییدشده','source':config.get('source') if applicable else None}
    limits=config.get('credit_limits') or {}
    chosen=None
    if applicable and mode=='academic':
        if target=='summer': chosen=limits.get('summer')
        elif state['status']=='CONFIRMED': chosen=limits.get(state['state'])
        # Final-term exceptions require an exact academic balance, not a claim based on attempted credits.
        final=limits.get('final') if target=='regular' else limits.get('final_summer')
        if final and graduation['balance_verified'] and graduation['exact_remaining_credits'] is not None and 0<graduation['exact_remaining_credits']<=final.get('remaining_at_most',-1):
            gpa_min=final.get('minimum_cumulative_gpa')
            gpa_met=gpa_min is None or number(gpa_min,0,20) and number(latest.get('reported_cumulative_gpa'),0,20) and latest['reported_cumulative_gpa']>=gpa_min
            if gpa_met and final.get('overrides_status') is True:
                chosen=final
                limit.update(final_term_exception=True,waive_pre_corequisites=final.get('waive_pre_corequisites') is True,recommended_credits=graduation['exact_remaining_credits'])
        if chosen:
            if chosen['approval_required']:
                limit.update(status='CONDITIONAL',conditional_maximum=chosen['max'],reason='این سقف به تأیید گروه/آموزش نیاز دارد؛ مجوز قطعی صادر نشده است.')
                fallback=limits.get('normal') if state.get('state')=='honors' and target=='regular' else None
                if fallback and not fallback['approval_required']: limit.update(minimum=fallback['min'],maximum=fallback['max'])
            else: limit.update(status='CONFIRMED',minimum=chosen.get('legal_minimum'),maximum=chosen['max'],reason='سقف طبق قواعد اعلام‌شده و وضعیت احرازشده؛ کف قانونی تعیین نشده است.' if 'legal_minimum' not in chosen else 'محدوده واحد طبق قاعده تنظیم‌شده')
    remaining_ids={c['course_id'] for c in graduation['missing_required']} | {cid for g in graduation['groups'] for cid in g['candidate_course_ids']}
    waiver_ids=[]
    if limit['waive_pre_corequisites']:
        for cid in remaining_ids:
            n=visual.get(cid,{})
            if courses[cid].get('course_code') and not n.get('minimum_semester') and not n.get('unresolved_credit_condition') and not any(r.get('course_id')==cid for r in chart.data['credit_conditions']):
                waiver_ids.append(cid)
    decision={'code':'UNKNOWN','text':state['reason'],'detail':None,'scope':'configured_academic_rules'}
    if graduation['status'] in ('CONFIRMED','CURRICULUM_COMPLETE'):
        decision.update(code='GRADUATED_ACADEMICALLY',text=graduation['label'],detail='تأیید اداری و صدور مدرک با آموزش است.')
    elif limit['final_term_exception']:
        scope=' طبق چارت تصویری' if graduation.get('basis')=='supplied_visual_reference_plan' else ''
        decision.update(code='FINAL_TERM',text=f"ترم آخر{scope} — {limit['recommended_credits']:g} واحد باقی مانده؛ قابل اخذ تا سقف ۲۴ واحد بدون پیش‌نیاز و هم‌نیاز",detail=None)
    elif state['status']=='CONFIRMED' and limit['maximum'] is not None:
        decision.update(code=state['state'].upper(),text=f"{state['label']} — سقف انتخاب واحد {limit['maximum']:g} واحد",
                        detail=graduation['reason'] if graduation['status']=='UNKNOWN' else None)
    if mode=='graduation':
        if req and req.get('all_requirements_defined') is True:
            from visual_plan import allocate
            groups=allocate([dict(g,name=g.get('name','گروه انتخابی')) for g in req['groups']],passed,courses)
            for g,original in zip(groups,req['groups']):g['category']=original.get('category','انتخابی')
            required=set(req['required_ids'])
            counted=sum(courses[cid]['credits'] for cid in required & passed)+sum(g['confirmed'] for g in groups)
            visual_plan={'plan_total':req['total_credits'],'counted_credits':counted,'required_course_ids':sorted(required),
                         'source_issues':[],'groups':groups,'remaining_credits':None,
                         'missing_required':[dict(course_id=cid,course_name=courses[cid]['course_name'],course_code=courses[cid].get('course_code')) for cid in sorted(required-passed)]}
        from graduation_report import build_report
        return build_report(report,chart,source,courses,passed,ledger,visual_plan,history_complete)
    return {'policy_applicable':bool(applicable),'policy_source':config.get('source') if applicable else None,
            'last_term':{'semester':last_key,'gpa':last_gpa,'credits':latest['credits_from_rows']},
            'academic_status':state,'credit_limit':limit,'graduation':graduation,'course_audit':audit,
            'final_term_course_ids':sorted(waiver_ids), 'waiver_scope':'future_remaining_courses_only',
            'decision':decision,'visual_plan':visual_plan,'history_verification':{'complete':bool(history_complete),'source':'explicit_confirmation' if explicit_complete else 'portal_totals_reconciled' if reconciled else None},
            'audit_summary':{'confirmed':sum(a['status']=='CONFIRMED' for a in audit),'needs_review':sum(a['status']!='CONFIRMED' for a in audit)}}


def apply_final_waiver(summary,review):
    """Waive only PRE/CO for approved remaining requirements, never past audit."""
    ids=set(review['final_term_course_ids'])
    if not ids: return
    def update(course):
        if course['course_id'] in ids:
            course['availability']={'status':'READY','reasons':['معافیت پیش‌نیاز و هم‌نیاز ترم آخر طبق قاعده اعلام‌شده'],
                                    'concurrent_ids':[],'final_term_waiver':True}
    for course in summary['not_taken']: update(course)
    for group in summary['option_groups']:
        candidates=group['ready']+group['needs_review']+group['waiting']
        for course in candidates: update(course)
        group['ready']=[c for c in candidates if c['availability']['status']=='READY']
        group['needs_review']=[c for c in candidates if c['availability']['status']=='UNKNOWN']
        group['waiting']=[c for c in candidates if c['availability']['status']=='WAITING']
    summary['final_term_waiver']=True
    summary['notice']='برای دروس باقی‌ماندهٔ مصوب، معافیت پیش‌نیاز و هم‌نیاز ترم آخر طبق قاعده اعلام‌شده اعمال شده است؛ سهم گروه‌ها و سقف واحد همچنان باید رعایت شوند.'
