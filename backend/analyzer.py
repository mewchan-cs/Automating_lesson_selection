"""Transcript matching plus optional completion of a supplied reference curriculum.

Passing uses the saved, user-confirmed threshold. Administrative graduation and
deferred enrollment rules are outside the graduation-only report.
"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
import math
from typing import Any

from curriculum_engine import CHARTS, Curriculum


class DataError(ValueError):
    pass


def _text(value: Any, name: str, max_length: int = 500) -> str:
    if value is None:
        return ''
    if not isinstance(value, str) or len(value) > max_length:
        raise DataError(f'فیلد {name} باید رشته کوتاه باشد.')
    return value.strip()


def _number(value: Any, name: str, *, minimum: float, maximum: float, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise DataError(f'مقدار عددی نامعتبر در {name}')
    if not minimum <= value <= maximum:
        raise DataError(f'عدد خارج از محدوده مجاز در {name}')
    return float(value)


@lru_cache(maxsize=3)
def chart_for(name: str) -> Curriculum:
    if name not in CHARTS:
        raise DataError('چارت انتخاب‌شده ناشناخته است.')
    return Curriculum(name)


def analyze_transcript(transcript: dict, chart_name: str, *, academic_review=False, target_term='regular',review_mode='academic') -> dict:
    if type(academic_review) is not bool:
        raise DataError('گزینه بررسی آموزشی باید روشن یا خاموش باشد.')
    if not isinstance(transcript, dict):
        raise DataError('کارنامه باید یک شیء JSON باشد.')
    if transcript.get('schema_version') != '1.0':
        raise DataError('نسخه ساختار کارنامه پشتیبانی نمی‌شود.')
    student = transcript.get('student')
    semesters = transcript.get('semesters')
    if not isinstance(student, dict) or not isinstance(semesters, list) or not 1 <= len(semesters) <= 100:
        raise DataError('مشخصات دانشجو یا فهرست نیمسال‌ها نامعتبر است.')
    chart = chart_for(chart_name)
    student_id = _text(student.get('student_id'), 'student_id', 60)
    full_name = _text(student.get('full_name'), 'full_name', 200)
    major = _text(student.get('major'), 'major', 200)
    warnings: list[str] = []
    extraction = transcript.get('extraction')
    if isinstance(extraction, dict):
        source_warnings = extraction.get('warnings')
        if isinstance(source_warnings, list):
            for warning in source_warnings[:100]:
                if isinstance(warning, str):
                    warnings.append(warning[:400])

    attempts: list[dict] = []
    unmatched: dict[str, dict] = {}
    ambiguous: dict[str, dict] = {}
    groups: dict[str, list[dict]] = defaultdict(list)
    terms: list[dict] = []
    matches = 0
    grade_ge_10 = grade_lt_10 = no_grade = 0
    sum_credits = 0.0
    total = 0
    years_seen = set()

    for term_index, semester in enumerate(semesters):
        if not isinstance(semester, dict):
            raise DataError('ساختار نیمسال نامعتبر است.')
        year = semester.get('academic_year_start')
        term = semester.get('term')
        courses = semester.get('courses')
        if isinstance(year, bool) or not isinstance(year, int) or not 1300 <= year <= 1500:
            raise DataError('سال تحصیلی نامعتبر است.')
        if isinstance(term, bool) or term not in (1, 2, 3):
            raise DataError('شماره نیمسال نامعتبر است.')
        if not isinstance(courses, list) or len(courses) > 200:
            raise DataError('فهرست دروس یک نیمسال نامعتبر است.')
        years_seen.add((year, term))
        term_credits = 0.0
        label = f'{year}-{term}'
        if total + len(courses) > 5000:
            raise DataError('تعداد رکوردهای کارنامه بیش از حد مجاز است.')
        for c in courses:
            if not isinstance(c, dict):
                raise DataError('اطلاعات یک درس نامعتبر است.')
            code = _text(c.get('course_code'), 'course_code', 60)
            name = _text(c.get('course_name'), 'course_name', 200)
            credits = _number(c.get('credits'), 'credits', minimum=0.01, maximum=30)
            grade = _number(c.get('grade'), 'grade', minimum=0, maximum=20, nullable=True)
            if not name:
                raise DataError('نام درس در کارنامه خالی است.')
            if not code:
                warnings.append(f'کد درس «{name}» در نیمسال {label} موجود نیست؛ تطبیق نیازمند بررسی است.')
            total += 1
            term_credits += credits
            sum_credits += credits
            if grade is None:
                no_grade += 1
            elif grade >= 10:
                grade_ge_10 += 1
            else:
                grade_lt_10 += 1
            matches_by_code = chart.by_code.get(code, [])
            ids = {str(row.get('course_id') or '') for row in matches_by_code}
            ids.discard('')
            if len(ids) == 1:
                mapped_id = next(iter(ids))
                matches += 1
                chart_course = matches_by_code[0]
                type_code = chart_course.get('course_type')
                chart_name_fa = chart_course.get('course_name')
                chart_credits = chart_course.get('credits')
                if isinstance(chart_credits, (int, float)) and abs(chart_credits - credits) > 0.001:
                    warnings.append(f'مغایرت تعداد واحد: {code} ({name})؛ کارنامه {credits:g}، چارت {chart_credits}')
                # Differing titles are kept verbatim, not assumed educationally equivalent.
            else:
                mapped_id = None
                type_code = None
                chart_name_fa = None
                if not matches_by_code:
                    unmatched.setdefault(code or f'MISSING:{total}', {'course_code': code, 'course_name': name, 'attempts': 0})['attempts'] += 1
                else:
                    ambiguous.setdefault(code, {'course_code': code, 'course_name': name, 'attempts': 0})['attempts'] += 1
            attempt = {
                'academic_year_start': year, 'term': term, 'course_code': code,
                'course_id': mapped_id, 'course_name': name, 'credits': credits,
                'grade': grade, 'course_type': type_code, 'chart_course_name': chart_name_fa,
                'matching': 'EXACT_CODE' if mapped_id else ('AMBIGUOUS_CODE' if matches_by_code else 'NOT_IN_CHART'),
            }
            attempts.append(attempt)
            groups[mapped_id or (f'OFFICIAL:{code}' if code else f'MISSING:{total}')].append(attempt)
        reported = semester.get('reported_summary')
        if reported is not None and not isinstance(reported, dict):
            raise DataError('خلاصه نیمسال نامعتبر است.')
        reported = reported or {}
        attempted = reported.get('term_attempted_credits')
        if attempted is not None:
            attempted = _number(attempted, 'term_attempted_credits', minimum=0, maximum=500)
            if abs(attempted - term_credits) > 0.001:
                warnings.append(f'مغایرت واحدهای اخذشده نیمسال {label}: دروس {term_credits:g}، سامانه {attempted:g}')
        term_gpa = reported.get('term_gpa')
        if term_gpa is not None:
            term_gpa = _number(term_gpa, 'term_gpa', minimum=0, maximum=20)
        terms.append({
            'academic_year_start': year, 'term': term,
            'attempt_count': len(courses), 'credits_from_rows': term_credits,
            'reported_attempted_credits': attempted,
            'reported_passed_credits': reported.get('term_passed_credits'),
            'reported_term_gpa': term_gpa,
            'reported_cumulative_gpa': reported.get('cumulative_gpa'),
            'reported_cumulative_passed_credits': reported.get('cumulative_passed_credits'),
        })

    if len(years_seen) < len(semesters):
        warnings.append('نیمسال تکراری در ورودی مشاهده شد؛ ممکن است داده تکرار شده باشد.')
    if isinstance(extraction, dict):
        for field, actual in (('semester_count', len(semesters)), ('attempt_count', total)):
            announced = extraction.get(field)
            if announced is not None and announced != actual:
                warnings.append(f'تعداد {field} با تعداد واقعی داده‌ها مطابقت ندارد.')
    repeats = []
    for key, items in groups.items():
        if len(items) > 1:
            repeats.append({
                'identity': key,
                'course_name': items[-1]['course_name'],
                'attempts': [
                    {'academic_year_start': a['academic_year_start'], 'term': a['term'],
                     'grade': a['grade'], 'course_code': a['course_code']} for a in items
                ]
            })
    repeats.sort(key=lambda item: (-len(item['attempts']), item['course_name']))
    if unmatched:
        warnings.append(f'{len(unmatched)} کد درس در چارت انتخاب‌شده پیدا نشد؛ تطبیق نامی خودکار انجام نشد.')
    if ambiguous:
        warnings.append(f'{len(ambiguous)} کد درس در چارت به چند شناسه اشاره دارد و نیازمند بازبینی است.')
    warnings.append('مقایسه بر پایه کارنامه موجود و چارت انتخابی انجام می‌شود؛ ثبت رسمی فارغ‌التحصیلی با آموزش است.')
    terms.sort(key=lambda t: (t['academic_year_start'], t['term']))
    last_reported = terms[-1] if terms else {}
    report = {
        'schema_version': '1.0', 'report_type': 'PRELIMINARY_TRANSCRIPT_ANALYSIS',
        'curriculum': chart_name,
        'student': {'student_id': student_id or None, 'full_name': full_name or None, 'major': major or None},
        'overview': {
            'semester_count': len(semesters), 'course_attempts': total,
            'attempted_credits_from_rows': sum_credits,
            'latest_reported_passed_credits': last_reported.get('reported_cumulative_passed_credits'),
            'latest_reported_gpa': last_reported.get('reported_cumulative_gpa'),
            'observed_grades_at_least_10': grade_ge_10,
            'observed_grades_below_10': grade_lt_10,
            'observed_missing_grades': no_grade,
            'matched_attempts': matches, 'unmatched_attempts': total - matches,
            'repeated_course_count': len(repeats),
        },
        'semesters': terms,
        'unmatched_courses': list(unmatched.values()),
        'ambiguous_courses': list(ambiguous.values()),
        'repeated_courses': repeats,
        'course_attempts': attempts,
        'warnings': warnings,
        'limitations': 'حد قبولی ثبت‌شده ۱۰ است؛ تطبیق کد، واحد و سهم گروه‌ها جداگانه بررسی می‌شود. صدور مدرک و مجوز اخذ درس موضوع این گزارش نیست.',
    }
    from visual_summary import summarize_visual
    report['visual_summary'] = summarize_visual(report, transcript, chart)
    if academic_review:
        from academic_review import review_academics, apply_final_waiver
        report['academic_review'] = review_academics(report, transcript, chart, target=target_term,mode=review_mode)
        if review_mode=='academic':apply_final_waiver(report['visual_summary'],report['academic_review'])
    return report
