"""Persistent visual-chart knowledge, never-taken courses and typed option pools.

This module adds a small report to the 0.3 analyzer without changing its matching
or academic verdicts. Readiness is a prospective chart check, not enrollment permission.
"""
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re

DATA = Path(__file__).resolve().parent / 'visual_data'
DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def normalized(value):
    return re.sub(r'\s+', ' ', str(value or '').translate(DIGITS).replace('ي','ی').replace('ك','ک').replace('\u200c',' ')).strip()


def load_knowledge(chart_name):
    catalog = json.loads((DATA / 'charts.json').read_text(encoding='utf-8'))
    source = next(c for c in catalog['charts'] if c['chart'] == chart_name)
    if hashlib.sha256((DATA / source['image']).read_bytes()).hexdigest() != source['sha256']:
        raise ValueError('تصویر و داده پایه چارت یکسان نیستند؛ داده چارت باید بازبینی شود.')
    options = json.loads((DATA / 'options.json').read_text(encoding='utf-8'))[chart_name]
    return source, options


def validate_policy(policy):
    if not isinstance(policy, dict): raise ValueError('تنظیمات چارت باید شیء JSON باشد.')
    passing = policy.get('passing')
    if passing is None: return None
    if not isinstance(passing, dict): raise ValueError('قاعده قبولی نامعتبر است.')
    grade = passing.get('minimum_grade')
    if type(grade) not in (int,float) or not math.isfinite(grade) or not 0 <= grade <= 20:
        raise ValueError('حد نمره قبولی نامعتبر است.')
    if type(passing.get('zero_is_final')) is not bool or not isinstance(passing.get('source'),str) or not passing['source'].strip():
        raise ValueError('قاعده قبولی نیازمند منبع و تعیین معنای صفر است.')
    return passing


def summarize_visual(report, transcript, chart, policy=None):
    source, option_specs = load_knowledge(chart.chart)
    if policy is None:
        policy = json.loads((DATA / 'policy.json').read_text(encoding='utf-8'))
    passing = validate_policy(policy)
    attempts = report['course_attempts']
    visual = {n['course_id']:dict(n) for n in source['nodes']}
    catalog = {}
    for cid, rows in chart.by_id.items():
        row = rows[0]
        catalog[cid] = dict(row, aliases=list({normalized(r['course_name']) for r in rows}),
                            category_rows=rows, visual=False,
                            identity_uncertain=len({(r.get('course_code'),r.get('credits')) for r in rows}) != 1)
    for cid, node in visual.items():
        base = catalog.get(cid, {})
        aliases = set(base.get('aliases', [])) | {normalized(node['course_name'])}
        catalog[cid] = dict(base, **{k:node[k] for k in ('course_id','course_code','course_name','credits')},
                            aliases=list(aliases), visual=True, node=node, identity_uncertain=False)
    # A visual code is authoritative within this cohort. Legacy code differences
    # are kept as uncertain matches, never silently treated as equivalences.
    by_code = defaultdict(set)
    for cid, c in catalog.items():
        if c.get('course_code'): by_code[normalized(c['course_code'])].add(cid)
    history = defaultdict(list)
    uncertain_ids = set()
    uncertain_attempts = []
    matched_attempts = set()
    for idx, attempt in enumerate(attempts):
        ids = by_code.get(normalized(attempt['course_code']), set())
        if len(ids) == 1:
            cid = next(iter(ids))
            if not catalog[cid].get('identity_uncertain'):
                history[cid].append(attempt)
                matched_attempts.add(idx)
                continue
        possible = set(ids)
        if attempt.get('course_id') in catalog: possible.add(attempt['course_id'])
        possible.update(cid for cid,c in catalog.items() if normalized(attempt['course_name']) in c['aliases'])
        uncertain_ids.update(possible)
        uncertain_attempts.append({'course_code':attempt['course_code'],'course_name':attempt['course_name'],
                                   'possible_course_ids':sorted(possible)})

    def completed(cid):
        if cid in uncertain_ids or not passing: return False
        return any(a['grade'] is not None and (a['grade'] != 0 or passing['zero_is_final'])
                   and a['grade'] >= passing['minimum_grade']
                   and a['credits'] == catalog[cid]['credits'] for a in history.get(cid, []))

    passed = {cid for cid in catalog if completed(cid)}
    active = set()
    for term in transcript['semesters']:
        for c in term['courses']:
            if c.get('enrollment_status') == 'ENROLLED' and c.get('grade') is None:
                ids = by_code.get(normalized(c.get('course_code')),set())
                if len(ids) == 1 and not (ids & uncertain_ids): active.update(ids)
    never_taken = set(catalog) - set(history) - uncertain_ids
    relations = defaultdict(list)
    constraints_unknown = set()
    base_to_visual = {n['base_course_code']:n['course_id'] for n in visual.values()}
    def resolve(code):
        if code in base_to_visual: return base_to_visual[code]
        ids = by_code.get(normalized(code),set())
        return next(iter(ids)) if len(ids) == 1 else None
    for cid, c in catalog.items():
        if c.get('visual'):
            n = c['node']
            if not n.get('relationship_reviewed') or n.get('requires_unresolved_reference') or not n.get('relationships_complete'):
                constraints_unknown.add(cid)
            if n.get('minimum_semester') or n.get('unresolved_credit_condition') or n.get('minimum_passed_credits'):
                # No inferred current semester or interpretation of "اخذ واحد".
                constraints_unknown.add(cid)
            for kind,key in (('PRE','prerequisites'),('CO','corequisites')):
                relations[cid].extend((kind,resolve(code)) for code in n[key])
        else:
            rows = c.get('category_rows',[])
            if c.get('identity_uncertain') or any(r.get('validation_status') != 'OK' for r in rows):
                constraints_unknown.add(cid)
            for rel in chart.relations:
                if rel.get('course_id') == cid:
                    relations[cid].append((rel.get('relation_type'),rel.get('related_course_id')))
                    if rel.get('link_status') != 'OK': constraints_unknown.add(cid)
        if any(cond.get('course_id') == cid for cond in chart.data['credit_conditions']): constraints_unknown.add(cid)

    readiness = {}
    for cid in never_taken:
        reasons = []
        unknown = cid in constraints_unknown or not catalog[cid].get('course_code')
        if unknown: reasons.append('کد یا شرط چارت نیازمند بررسی')
        blocked = False
        for kind,target in relations[cid]:
            if target not in catalog or kind not in ('PRE','CO'):
                unknown = True; reasons.append('رابطه نامشخص'); continue
            if kind == 'PRE' and target not in passed:
                if target not in history and target not in uncertain_ids:
                    blocked = True; reasons.append('پیش‌نیاز در کارنامه موجود نیست')
                elif not passing or target in uncertain_ids:
                    unknown = True; reasons.append('قبولی پیش‌نیاز نیازمند احراز')
                else:
                    # Missing/zero/mismatched grades are uncertain, not final failures.
                    grades = history[target]
                    if any(a['grade'] is None or (a['grade'] == 0 and not passing['zero_is_final']) or a['credits'] != catalog[target]['credits'] for a in grades):
                        unknown = True; reasons.append('نتیجه پیش‌نیاز نامشخص')
                    else: blocked = True; reasons.append('قبولی پیش‌نیاز احراز نشد')
        readiness[cid] = {'status':'WAITING' if blocked else 'UNKNOWN' if unknown else 'READY',
                          'reasons':list(dict.fromkeys(reasons)), 'concurrent_ids':[]}
    # CO cycles are allowed only when all their members are otherwise ready.
    while True:
        changes = {}
        for cid, state in readiness.items():
            if state['status'] != 'READY': continue
            partners = {target for kind,target in relations[cid] if kind == 'CO'} - passed - active
            bad = [target for target in partners if target not in readiness or readiness[target]['status'] != 'READY']
            if bad:
                unknown = any(target in uncertain_ids or (target in history and not passing) or readiness.get(target,{}).get('status') == 'UNKNOWN' for target in bad)
                changes[cid] = {'status':'UNKNOWN' if unknown else 'WAITING','reasons':['هم‌نیاز هم‌زمان نیازمند بررسی یا انتخاب مجدد است'],'concurrent_ids':[]}
            else: state['concurrent_ids'] = sorted(partners)
        if not changes: break
        readiness.update(changes)
    def item(cid):
        c = catalog[cid]
        return {'course_id':cid,'course_name':c['course_name'],'course_code':c.get('course_code'),
                'code_source':c['node']['code_source'] if c.get('visual') else 'existing_json',
                'suggested_semester':c['node']['suggested_semester'] if c.get('visual') else None,
                'availability':readiness[cid], 'source_image':source['image'] if c.get('visual') else None}
    def ordered(ids):
        return [item(cid) for cid in sorted(ids, key=lambda i:(catalog[i].get('node',{}).get('suggested_semester',999),catalog[i]['course_name']))]
    groups = []
    for spec in option_specs:
        membership = defaultdict(set)
        for cid,c in catalog.items():
            rows = c.get('category_rows',[])
            for row in rows:
                matches = row.get('course_type') in spec.get('types',[]) or row.get('course_code') in spec.get('codes',[]) or cid in spec.get('ids',[])
                if matches:
                    key = row.get('course_group') or 'گروه نامشخص' if spec.get('split_by_group') else ''
                    membership[key].add(cid)
        for subgroup, ids in membership.items():
            remaining = ids & never_taken
            candidates = ordered(remaining)
            explicit_choice=spec.get('choice_rule')=='one_passed_course'
            choice_state=None
            if explicit_choice:
                pending=bool(ids & uncertain_ids) or (not passing and bool(ids & set(history))) or any(a['grade'] is None or a['grade']==0 and (not passing or not passing['zero_is_final']) for cid in ids for a in history.get(cid,[]))
                choice_state='COMPLETE' if ids & passed else 'UNKNOWN' if pending else 'OPEN'
            retake_options=[{'course_id':cid,'course_name':catalog[cid]['course_name'],'course_code':catalog[cid].get('course_code'),
                             'availability':{'status':'UNKNOWN','reasons':['قبلاً اخذ شده ولی قبولی احراز نشده است'],'concurrent_ids':[]}}
                            for cid in sorted(ids & set(history)-passed)] if explicit_choice and choice_state!='COMPLETE' else []
            groups.append({'key':spec['key']+(':'+subgroup if subgroup else ''),
                           'title':spec['title']+(' — '+subgroup if subgroup else ''),
                           'semesters':spec['semesters'], 'note':spec.get('note'),
                           'previously_taken_count':len(ids & set(history)),
                           'ready':[c for c in candidates if c['availability']['status']=='READY'],
                           'needs_review':[c for c in candidates if c['availability']['status']=='UNKNOWN'],
                           'waiting':[c for c in candidates if c['availability']['status']=='WAITING'],
                           'remaining_option_count':len(candidates),
                           'required_slots_remaining':(0 if choice_state=='COMPLETE' else 1) if explicit_choice else None,
                           'show_in_main':spec.get('show_in_main') is True,
                           'completion_status':choice_state,'choice_rule':spec.get('choice_rule'),
                           'retake_options':retake_options})
    # Named general courses without codes in image 2 remain visible; no code is invented.
    code_less_named = []
    for slot in source['slots']:
        if slot['kind'] != 'missing_code': continue
        matches = {cid for cid,c in catalog.items() if normalized(slot['name']) in c['aliases']}
        if matches & (set(history)|uncertain_ids): continue
        if len(matches) == 1:
            cid = next(iter(matches))
            if cid in never_taken:
                row = item(cid); row['suggested_semester'] = slot['suggested_semester']; row['source_image'] = source['image']; code_less_named.append(row)
        else:
            code_less_named.append({'course_id':None,'course_name':slot['name'],'course_code':None,
              'suggested_semester':slot['suggested_semester'],'source_image':source['image'],
              'availability':{'status':'UNKNOWN','reasons':['کد در تصویر مشخص نیست'],'concurrent_ids':[]}})
    named = ordered(set(visual) & never_taken) + code_less_named
    named.sort(key=lambda c:(c['suggested_semester'],c['course_name']))
    return {'schema_version':'1.0','chart':chart.chart,'source_image':source['image'],'source_sha256':source['sha256'],
            'not_taken':named, 'option_groups':groups,
            'main_alternatives':[g for g in groups if g['show_in_main'] and g['completion_status']!='COMPLETE'],
            'needs_matching':uncertain_attempts,
            'uncertain_visual_courses':[{'course_id':cid,'course_name':catalog[cid]['course_name'],'course_code':catalog[cid].get('course_code')} for cid in sorted(set(visual)&uncertain_ids)],
            'unresolved_slots':[s for s in source['slots'] if s['kind']=='unresolved_option'],
            'selection_notes':chart.data['rules'],
            'code_notice':'تصویر ۱۴۰۳ کد ندارد؛ کدهای نمایش‌داده‌شده از داده قبلی‌اند و با تصویر تأیید نشده‌اند.' if chart.chart=='1403-plus' else None,
            'notice':'اخذنشده‌ها بر اساس کارنامه موجودند؛ گزینه‌های آماده فقط از نظر شروط ثبت‌شده چارت بررسی شده‌اند. هم‌نیازهای پیشنهادی باید با هم اخذ شوند؛ ارائه، سهم اختیاری و سقف واحد جداگانه بررسی شود.'}
