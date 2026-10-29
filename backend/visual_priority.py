"""Image-backed curriculum overlay and conservative course suggestions."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'visual_charts'


def apply_visual(chart):
    payload = json.loads((ROOT / 'catalog.json').read_text(encoding='utf-8'))
    source = next(c for c in payload['charts'] if c['chart'] == chart.chart)
    if hashlib.sha256((ROOT / source['image']).read_bytes()).hexdigest() != source['sha256']:
        raise ValueError('تصویر چارت با داده ثبت‌شده تطابق ندارد؛ نیازمند بازبینی')
    conflicts = []
    # These links are explicit in catalog.json, never inferred by fuzzy names.
    for node in source['nodes']:
        rows = chart.by_id.get(node['course_id'], [])
        if not rows:
            row = {'entry_year_from':source['entry_year_from'], 'entry_year_to':source['entry_year_to'],
                   'source_category':'چارت تصویری', 'source_row':None, 'course_group':None}
            chart.courses.append(row)
            rows = [row]
        for row in rows:
            before = {k:row.get(k) for k in ('course_code','credits','prerequisites','corequisites')}
            row.update({k:node.get(k) for k in ('course_id','course_code','course_name','credits','course_type')})
            row.update(visual_source=source['image'], suggested_semester=node['suggested_semester'],
                       validation_status='OK' if node['relationships_complete'] and not node.get('requires_unresolved_reference') else 'REVIEW_RELATION')
            row['prerequisites'] = ', '.join(node['prerequisites']) or None
            row['corequisites'] = ', '.join(node['corequisites']) or None
            after = {k:row.get(k) for k in before}
            if before != after and before['course_code'] is not None:
                conflicts.append({'course_id':node['course_id'], 'before':before, 'visual':after,
                                  'image':source['image'], 'semester':node['suggested_semester']})
    chart.by_code = defaultdict(list)
    chart.by_id = defaultdict(list)
    for row in chart.courses:
        if row.get('course_code'):
            chart.by_code[str(row['course_code'])].append(row)
        if row.get('course_id'):
            chart.by_id[str(row['course_id'])].append(row)
    by_visual_code = {n['base_course_code']:n for n in source['nodes']}
    visual_ids = {n['course_id'] for n in source['nodes']}
    chart.relations[:] = [r for r in chart.relations if r.get('course_id') not in visual_ids]
    for node in source['nodes']:
        for kind, key in (('PRE','prerequisites'),('CO','corequisites')):
            for code in node[key]:
                target = by_visual_code.get(code)
                target_rows = chart.by_code.get(code, [])
                target_id = target['course_id'] if target else target_rows[0]['course_id'] if len({r['course_id'] for r in target_rows}) == 1 else None
                official = target['course_code'] if target else code
                chart.relations.append({'course_id':node['course_id'], 'course_code':node['course_code'],
                    'related_course_id':target_id, 'related_course_code':official, 'relation_type':kind,
                    'link_status':'OK' if target_id else 'UNRESOLVED', 'source_row':None,
                    'source_text':f"{source['image']} — نیمسال {node['suggested_semester']} — {kind}",
                    'visual_source':source['image']})
    return dict(source, conflicts=conflicts)


def recommend(report, transcript, chart, rules):
    source = chart.visual
    attempts = report['course_attempts']
    # The user asked for courses never taken, so failed attempts are excluded too.
    taken_ids = {a['course_id'] for a in attempts if a['course_id']}
    taken_codes = {a['course_code'] for a in attempts if a['course_code']}
    passed = {a['course_id'] for a in attempts if a.get('completion') == 'PASSED'}
    active = {a['course_id'] for a in attempts if a.get('enrollment_status') == 'ENROLLED' and a.get('grade') is None}
    nodes = {n['course_id']:n for n in source['nodes']}
    known = {}
    for cid, rows in chart.by_id.items():
        # Identical duplicate package rows are a single course; conflicting rows are withheld.
        unique = {(r.get('course_code'),r.get('credits'),r.get('validation_status')) for r in rows}
        if len(unique) == 1 and rows[0].get('course_code'):
            known[cid] = rows[0]
    available = {}
    withheld = []
    student_bound = rules.get('student_id') == report['student']['student_id'] and bool(rules.get('student_id'))
    target_semester = rules.get('target_semester') if student_bound else None
    for cid, row in known.items():
        if cid in taken_ids or row['course_code'] in taken_codes:
            continue
        node = nodes.get(cid)
        relations = [r for r in chart.relations if r.get('course_id') == cid]
        missing = []
        if row.get('validation_status') != 'OK': missing.append('رابطه نیازمند بازبینی')
        if node and (not node['relationships_complete'] or node.get('requires_unresolved_reference')):
            missing.append(node.get('review_reason') or node.get('requires_unresolved_reference') or 'رابطه تصویری نامشخص')
        if node and node.get('minimum_semester') and (type(target_semester) is not int or target_semester < node['minimum_semester']):
            missing.append('شرط نیمسال')
        if node and node.get('unresolved_credit_condition'): missing.append(node['unresolved_credit_condition'])
        if any(c.get('course_id') == cid for c in chart.data['credit_conditions']): missing.append('شرط واحد نیازمند احراز')
        for rel in relations:
            if rel.get('link_status') != 'OK' or not rel.get('related_course_id'):
                missing.append('رابطه حل‌نشده')
            elif rel['relation_type'] == 'PRE' and rel['related_course_id'] not in passed:
                missing.append('پیش‌نیاز احراز نشده')
            elif rel['relation_type'] not in ('PRE','CO'): missing.append('نوع رابطه نامشخص')
        if missing:
            withheld.append({'course_id':cid,'course_code':row['course_code'],'reasons':list(dict.fromkeys(missing))})
            continue
        available[cid] = {'course_id':cid,'course_name':row['course_name'],'course_code':row['course_code'],
                          'suggested_semester':node['suggested_semester'] if node else None,
                          'source_image':source['image'] if node else None,
                          'code_source':node.get('code_source') if node else 'existing_json',
                          'concurrent_course_ids':[], 'scope':'CHART_CONDITIONS_ONLY'}
    # Greatest fixed point: corequisite bundles remain only when every member can be taken.
    changed = True
    while changed:
        changed = False
        for cid in list(available):
            coreqs = {r['related_course_id'] for r in chart.relations if r.get('course_id') == cid and r.get('relation_type') == 'CO'}
            unresolved = coreqs - passed - active - set(available)
            if unresolved:
                withheld.append({'course_id':cid,'course_code':available[cid]['course_code'],'reasons':['هم‌نیاز قابل اخذ یا گذرانده‌شده احراز نشد']})
                del available[cid]
                changed = True
            else:
                available[cid]['concurrent_course_ids'] = sorted(coreqs - passed - active)
    ordered = sorted(available.values(), key=lambda c:(c['suggested_semester'] or 999,c['course_name'],c['course_code']))
    unresolved_transcript = any(not a['course_id'] for a in attempts)
    if unresolved_transcript:
        # An unmapped portal code could be a previously taken visual course.
        # Do not present the whole chart as "never taken" on a code-system mismatch.
        withheld.extend({'course_id':c['course_id'],'course_code':c['course_code'],'reasons':['تطبیق کدهای کارنامه کامل نیست']} for c in ordered)
        ordered = []
    first = min((c['suggested_semester'] for c in ordered if c['suggested_semester'] is not None), default=None)
    priority = [c for c in ordered if first is not None and c['suggested_semester'] == first]
    other = [c for c in ordered if c not in priority]
    return {'priority':priority,'other':other,'withheld':withheld,
            'source_image':source['image'], 'source_sha256':source['sha256'],
            'selection_rule':'ابتدا قدیمی‌ترین نیمسال دارای درس قابل پیشنهاد در چارت تصویری؛ سپس سایر گزینه‌ها',
            'notice':'برای پیشنهاد دقیق، کدهای نامنطبق یا مفقود کارنامه باید تعیین تکلیف شوند.' if unresolved_transcript else 'بر اساس کارنامه موجود و شرایط چارت؛ هم‌نیازها باید با هم انتخاب شوند. ارائه، ظرفیت و سقف واحد نیازمند بررسی‌اند.',
            'code_notice':'تصویر ۱۴۰۳ کد ندارد؛ کدهای این ورودی از داده قبلی‌اند و با تصویر تأیید نشده‌اند.' if chart.chart == '1403-plus' else None,
            'visual_slots':source['slots'], 'visual_conflicts':source['conflicts']}
