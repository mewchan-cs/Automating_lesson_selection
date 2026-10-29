"""Conservative, evidence-bearing audit. No university policy is inferred."""
from collections import defaultdict
import math


def validate_rules(rules):
    if not isinstance(rules, dict):
        raise ValueError('قواعد باید شیء JSON باشند')
    if 'target_semester' in rules and (type(rules['target_semester']) is not int or not 1 <= rules['target_semester'] <= 30):
        raise ValueError('شماره نیمسال هدف باید عدد صحیح بین ۱ و ۳۰ باشد')
    def sourced(value):
        return isinstance(value, dict) and isinstance(value.get('source'), str) and bool(value['source'].strip())
    def number(v, low=0, high=500):
        return type(v) in (int, float) and math.isfinite(v) and low <= v <= high
    passing = rules.get('passing', {})
    if passing and (not sourced(passing) or not number(passing.get('minimum_grade'), 0, 20)
                    or type(passing.get('zero_is_final')) is not bool):
        raise ValueError('قاعده قبولی نیازمند منبع، حد نمره و تعیین تکلیف صفر است')
    relation = rules.get('relationships', {})
    if relation and (not sourced(relation) or relation.get('exceptions_resolved') is not True):
        raise ValueError('برای حکم رابطه باید منبع و تعیین تکلیف استثناها ثبت شود')
    req = rules.get('requirements', {})
    if req:
        if not sourced(req) or not isinstance(req.get('mandatory_ids'), list) or not isinstance(req.get('groups'), list):
            raise ValueError('الزامات چارت نیازمند منبع، فهرست الزامی و گروه‌های انتخابی است')
        members = list(req['mandatory_ids'])
        for group in req['groups']:
            if not isinstance(group, dict) or not isinstance(group.get('course_ids'), list) or not number(group.get('credits')):
                raise ValueError('ساختار گروه اختیاری نامعتبر است')
            members.extend(group['course_ids'])
        if any(not isinstance(x, str) for x in members) or len(members) != len(set(members)):
            raise ValueError('هم‌پوشانی گروه‌ها نیازمند قاعده رسمی جداگانه است؛ شناسه‌ها باید یکتا باشند')
    states = rules.get('term_states', {})
    if not isinstance(states, dict):
        raise ValueError('وضعیت نیمسال‌ها نامعتبر است')
    for state in states.values():
        if not sourced(state) or state.get('state') not in ('normal', 'probation', 'honors', 'final'):
            raise ValueError('وضعیت نیمسال نیازمند مدرک و نوع معتبر است')
    for limits in rules.get('credit_limits', {}).values():
        if not sourced(limits) or not number(limits.get('min')) or not number(limits.get('max')) or limits['min'] > limits['max']:
            raise ValueError('محدوده واحد نامعتبر یا فاقد منبع است')
    return rules


def extend_report(report, transcript, chart, rules=None):
    rules = validate_rules(rules or {})
    attempts = report['course_attempts']
    passing = rules.get('passing', {})
    def outcome(a):
        rows = chart.by_id.get(a.get('course_id'), [])
        identities = {(r.get('course_code'), r.get('credits')) for r in rows}
        if len(identities) != 1 or rows[0].get('credits') != a['credits']:
            return 'UNKNOWN'
        if not passing or a['grade'] is None or (a['grade'] == 0 and not passing['zero_is_final']):
            return 'UNKNOWN'
        return 'PASSED' if a['grade'] >= passing['minimum_grade'] else 'FAILED'
    def time(a):
        return a['academic_year_start'], a['term']
    history = defaultdict(list)
    for index, a in enumerate(attempts):
        a['attempt_ref'] = index
        a['completion'] = outcome(a)
        if a['course_id']:
            history[a['course_id']].append(a)
    issues = []
    def check(kind, status, reason, evidence, **extra):
        item = dict(kind=kind, status=status, reason=reason, evidence=evidence, **extra)
        issues.append(item)
        return item
    req = rules.get('requirements', {})
    if req:
        ids = req['mandatory_ids'] + [i for g in req['groups'] for i in g['course_ids']]
        if any(i not in chart.by_id or len(chart.by_id[i]) != 1 for i in ids):
            raise ValueError('شناسه الزامات در چارت وجود ندارد یا مبهم است')
    completed = {i for i, rows in history.items() if any(a['completion'] == 'PASSED' for a in rows)}
    candidates = []
    mandatory = set(req.get('mandatory_ids', []))
    for cid, rows in chart.by_id.items():
        if cid in completed:
            continue
        c = rows[0]
        candidates.append({k: c.get(k) for k in ('course_id', 'course_code', 'course_name', 'credits', 'course_type', 'source_category', 'source_row')})
        candidates[-1].update(requirement='MANDATORY' if cid in mandatory else 'OPTION_OR_UNSPECIFIED',
                              chart_rows=rows,
                              status='UNKNOWN' if not passing or any(a['completion'] == 'UNKNOWN' for a in history[cid]) else 'NOT_COMPLETED',
                              reason='گزینه چارت؛ الزام اخذ فقط طبق تنظیم رسمی تعیین می‌شود',
                              evidence={'chart': chart.chart, 'source_row': c.get('source_row'), 'attempts': [a['attempt_ref'] for a in history[cid]]})
    categories = defaultdict(float)
    for c in candidates:
        categories[c['source_category'] or c['course_type']] += c['credits']
    uncertain = not passing or any(a['completion'] == 'UNKNOWN' or not a['course_id'] for a in attempts)
    uncertain = uncertain or any(len(chart.by_id[i]) != 1 for i in mandatory | {i for g in req.get('groups', []) for i in g['course_ids']})
    groups = []
    for g in req.get('groups', []):
        earned = sum(chart.by_id[cid][0]['credits'] for cid in set(g['course_ids']) & completed)
        groups.append({'name': g.get('name', 'گروه اختیاری'), 'required_credits': g['credits'],
                       'confirmed_completed_credits': earned, 'remaining_credits': max(0, g['credits'] - earned),
                       'source': req['source'], 'course_ids': g['course_ids']})
    requirement_balance = sum(chart.by_id[i][0]['credits'] for i in mandatory - completed) + sum(g['remaining_credits'] for g in groups) if req else None
    if not req:
        check('requirements', 'UNKNOWN', 'نیازمند تعیین قانون: الزامی‌ها، سهم گروه‌های اختیاری و نحوه احتساب', chart.data['rules'])
    if not passing:
        check('passing', 'UNKNOWN', 'نیازمند تعیین قانون: حد قبولی و معنای نمره صفر', [])
    # Negative findings require explicit attestation of a complete record; DOM presence cannot prove completeness.
    student_bound = bool(rules.get('student_id')) and rules.get('student_id') == report['student']['student_id']
    complete = rules.get('history_complete') is True and student_bound
    duplicates = len({time(t) for t in transcript['semesters']}) != len(transcript['semesters'])
    uncertain = uncertain or not complete or duplicates
    for a in attempts:
        base = dict(attempt_ref=a['attempt_ref'], semester=f"{a['academic_year_start']}-{a['term']}", course_id=a['course_id'], course_code=a['course_code'])
        if not a['course_id']:
            check('matching', 'UNKNOWN', 'کد مفقود، نامنطبق یا مبهم؛ هم‌ارزی نامی انجام نشد', [a], **base)
            continue
        course = chart.by_id[a['course_id']][0]
        rels = [r for r in chart.relations if r.get('course_id') == a['course_id']]
        if not rels:
            check('relationships', 'UNKNOWN' if course.get('validation_status') != 'OK' else 'CONFIRMED',
                  'در داده چارت رابطه‌ای ثبت نشده؛ این نتیجه فقط درباره چارت موجود است', [course], **base)
        for r in rels:
            target = str(r.get('related_course_id') or '')
            previous = [b for b in history[target] if time(b) < time(a)]
            concurrent = [b for b in history[target] if time(b) == time(a)]
            met = any(b['completion'] == 'PASSED' for b in previous)
            if r.get('relation_type') == 'CO':
                # A row does not prove active registration; require explicit official enrollment evidence.
                raw = [c for t in transcript['semesters'] if time(t) == time(a) for c in t['courses']]
                met = met or any(c.get('course_code') == r.get('related_course_code') and c.get('enrollment_status') == 'ENROLLED' for c in raw)
            policy = rules.get('relationships', {})
            known = r.get('link_status') == 'OK' and target in chart.by_id and r.get('relation_type') in ('PRE', 'CO') and course.get('validation_status') == 'OK'
            uncertain_target = any(b['completion'] == 'UNKNOWN' for b in previous) or bool(concurrent and r.get('relation_type') == 'CO')
            negative_ok = known and policy and complete and a.get('enrollment_status') == 'ENROLLED' and not duplicates and not uncertain_target and not any(not b['course_id'] for b in attempts if time(b) <= time(a))
            status = 'CONFIRMED' if known and met else 'VIOLATION' if negative_ok else 'UNKNOWN'
            reason = 'رابطه با مدرک احراز شد' if status == 'CONFIRMED' else 'رابطه طبق قاعده تنظیم‌شده رعایت نشده' if status == 'VIOLATION' else 'نیازمند تعیین قانون یا مدرک کامل قبولی/ثبت هم‌زمان/استثناها'
            check(r.get('relation_type', 'relationship'), status, reason,
                  {'relation': r, 'history_refs': [b['attempt_ref'] for b in previous + concurrent], 'rule': policy}, **base)
        for cond in chart.data['credit_conditions']:
            if cond.get('course_id') == a['course_id']:
                check('credit_condition', 'UNKNOWN', 'شرط واحد چارت نیازمند تأیید نحوه احتساب رسمی است', cond, **base)
    labels = {'normal': 'عادی', 'probation': 'مشروط', 'honors': 'معدل الف', 'final': 'ترم آخر'}
    for term in report['semesters']:
        key = f"{term['academic_year_start']}-{term['term']}"
        state = rules.get('term_states', {}).get(key, {}) if student_bound else {}
        state_name = state.get('state')
        # Summer policy is independent; never inherit a normal-term cap.
        limit_key = 'summer' if term['term'] == 3 else state_name
        limits = rules.get('credit_limits', {}).get(limit_key, {})
        rows = [a for a in attempts if time(a) == time(term)]
        official_registration = all(c.get('enrollment_status') == 'ENROLLED' for t in transcript['semesters'] if time(t) == time(term) for c in t['courses'])
        valid = bool(state and limits and rows and official_registration and not duplicates)
        within = valid and limits['min'] <= term['credits_from_rows'] <= limits['max']
        check('credit_load', 'CONFIRMED' if within else 'VIOLATION' if valid else 'UNKNOWN',
              f"وضعیت: {labels.get(state_name, 'نامشخص')}؛ " + ('در محدوده رسمی تنظیم‌شده' if within else 'خارج از محدوده رسمی تنظیم‌شده' if valid else 'نیازمند تعیین قانون یا مدرک وضعیت و ثبت فعال دروس'),
              {'state': state, 'limits': limits, 'credits': term['credits_from_rows'], 'attempt_refs': [a['attempt_ref'] for a in rows]}, semester=key)
    return {'report_type': 'CONSERVATIVE_MVP_AUDIT', 'rules_snapshot': rules,
            'remaining': {'courses': candidates, 'candidate_credits_by_category': dict(categories),
                          'candidate_credits_total': sum(categories.values()), 'elective_groups': groups,
                          'required_balance_before_uncertainty': requirement_balance,
                          'exact_remaining_credits': requirement_balance if req and not uncertain else None,
                          'status': 'CONFIRMED' if req and not uncertain else 'UNKNOWN',
                          'reason': 'جمع گزینه‌ها معادل واحد لازم برای فارغ‌التحصیلی نیست؛ مقدار دقیق فقط با قواعد کامل و داده تعیین‌تکلیف‌شده ارائه می‌شود'},
            'audit': issues, 'chart_issues': [i.dict() for i in chart.validate()]}
