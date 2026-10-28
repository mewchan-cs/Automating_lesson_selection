"""موتور تحلیل چارت - فاز اول: خواندن، اعتبارسنجی و تحلیل روابط.

کتابخانه استاندارد پایتون؛ بدون API یا وابستگی خارجی.
این موتور مجوز قطعی انتخاب واحد صادر نمی‌کند.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any

CHARTS = ('1395-1400', '1401-1402', '1403-plus')


def s(value: Any) -> str:
    """Official codes must always be treated as strings."""
    if value is None: return ''
    if isinstance(value, float) and value.is_integer(): return str(int(value))
    return str(value).strip()


def codes(value: Any) -> list[str]:
    if isinstance(value, list): return [s(x) for x in value if s(x)]
    return [x.strip() for x in s(value).replace('،', ',').split(',') if x.strip()]


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    source_row: int | None = None

    def dict(self) -> dict:
        return {'severity': self.severity, 'code': self.code,
                'message': self.message, 'source_row': self.source_row}


class Curriculum:
    def __init__(self, chart: str, root: Path | str | None = None):
        if chart not in CHARTS: raise ValueError(f'Unknown chart: {chart}')
        self.chart = chart
        if root is None: root = Path(__file__).resolve().parent / 'data'
        filepath = Path(root) / f'{chart}.json'
        payload = json.loads(filepath.read_text(encoding='utf-8'))
        self.data = payload['sheets']
        self.courses = self.data['courses']
        self.relations = self.data['relations']
        self.by_code: dict[str, list[dict]] = defaultdict(list)
        self.by_id: dict[str, list[dict]] = defaultdict(list)
        for item in self.courses:
            if s(item.get('course_code')): self.by_code[s(item['course_code'])].append(item)
            if s(item.get('course_id')): self.by_id[s(item['course_id'])].append(item)

    def lookup(self, code_or_id: str) -> list[dict]:
        key = s(code_or_id)
        return self.by_code.get(key, []) if key in self.by_code else self.by_id.get(key, [])

    def summary(self) -> dict:
        counts = Counter(s(c.get('course_type')) for c in self.courses)
        rels = Counter(s(r.get('relation_type')) for r in self.relations)
        return {
            'curriculum': self.chart,
            'course_rows': len(self.courses),
            'distinct_internal_ids': len(self.by_id),
            'courses_without_official_code': sum(not s(c.get('course_code')) for c in self.courses),
            'course_type_counts': dict(sorted(counts.items())),
            'relationship_counts': dict(sorted(rels.items())),
            'curriculum_rules_not_yet_executable': len(self.data['rules']),
            'manual_review_items': sum(s(r.get('review_status')) == 'OPEN' for r in self.data['review']),
        }

    def _source_row(self, course: dict) -> int | None:
        try: return int(course.get('source_row'))
        except (TypeError, ValueError): return None

    def _resolved_edges(self, kind: str) -> list[tuple[str, str]]:
        return [(s(r.get('course_id')), s(r.get('related_course_id')))
                for r in self.relations
                if s(r.get('relation_type')) == kind and s(r.get('link_status')) == 'OK'
                and s(r.get('course_id')) and s(r.get('related_course_id'))]

    def _cycles(self) -> list[list[str]]:
        # Directed edges: course -> prerequisite. Only confirmed references are traversed.
        graph: dict[str, set[str]] = defaultdict(set)
        for source, target in self._resolved_edges('PRE'):
            graph[source].add(target)
        color: dict[str, int] = {}
        path: list[str] = []
        cycles: set[tuple[str, ...]] = set()

        def dfs(node: str):
            color[node] = 1
            path.append(node)
            for nbr in sorted(graph[node]):
                if color.get(nbr, 0) == 0: dfs(nbr)
                elif color[nbr] == 1:
                    candidate = path[path.index(nbr):]
                    # canonical rotation removes duplicates
                    k = min(tuple(candidate[i:] + candidate[:i]) for i in range(len(candidate)))
                    cycles.add(k)
            path.pop()
            color[node] = 2

        for node in list(graph):
            if color.get(node, 0) == 0: dfs(node)
        return [list(x) for x in sorted(cycles)]

    def validate(self) -> list[Issue]:
        issues: list[Issue] = []
        for c in self.courses:
            row = self._source_row(c)
            name = s(c.get('course_name'))
            if not s(c.get('course_id')):
                issues.append(Issue('ERROR', 'missing_course_id', f'درس «{name}» شناسه ندارد', row))
            if not name:
                issues.append(Issue('ERROR', 'missing_course_name', 'نام درس خالی است', row))
            if not isinstance(c.get('credits'), (int, float)) or c.get('credits') < 0:
                issues.append(Issue('ERROR', 'bad_credits', f'واحد نامعتبر: {name}', row))
            if not s(c.get('course_type')):
                issues.append(Issue('ERROR', 'missing_course_type', f'نوع درس نامشخص: {name}', row))
            if not s(c.get('course_code')):
                issues.append(Issue('WARNING', 'missing_official_code', f'کد رسمی ثبت نشده: {name}', row))
            if s(c.get('validation_status')) == 'REVIEW_RELATION':
                issues.append(Issue('WARNING', 'unresolved_relationship', f'رابطه درس نیازمند بازبینی است: {name}', row))
            lo,hi=c.get('entry_year_from'),c.get('entry_year_to')
            if not isinstance(lo,int) or (hi is not None and (not isinstance(hi,int) or hi<lo)):
                issues.append(Issue('ERROR', 'bad_year_range', f'بازه ورودی نامعتبر: {name}',row))

        for code, rows in self.by_code.items():
            if len({s(x['course_id']) for x in rows}) > 1:
                issues.append(Issue('ERROR', 'ambiguous_official_code', f'کد رسمی {code} به چند شناسه متفاوت اشاره می‌کند'))
        for r in self.relations:
            code = s(r.get('course_code'))
            related = s(r.get('related_course_code'))
            if s(r.get('relation_type')) not in {'PRE','CO'}:
                issues.append(Issue('ERROR', 'invalid_relation_type', f'رابطه ناشناخته برای {code}: {r.get("relation_type")}'))
            st = s(r.get('link_status'))
            if st != 'OK':
                issues.append(Issue('WARNING', 'uncertain_relation_target', f'رابطه {code} ← {related}: {st}', r.get('source_row')))
            if code and code not in self.by_code:
                issues.append(Issue('ERROR', 'missing_relation_source', f'درس مبدا رابطه وجود ندارد: {code}',r.get('source_row')))
            if st == 'OK':
                targets = self.by_code.get(related, [])
                if not targets:
                    issues.append(Issue('ERROR','missing_relation_target',f'درس مقصد رابطه وجود ندارد: {related}', r.get('source_row')))
                elif s(r.get('related_course_id')) not in {s(c.get('course_id')) for c in targets}:
                    issues.append(Issue('ERROR', 'wrong_relation_id', f'شناسه مقصد با کد {related} سازگار نیست', r.get('source_row')))
                if s(r.get('course_id')) == s(r.get('related_course_id')):
                    issues.append(Issue('ERROR','self_dependency',f'درس {code} به خودش وابسته است', r.get('source_row')))
        for cycle in self._cycles():
            issues.append(Issue('ERROR', 'prerequisite_cycle', 'چرخه پیش‌نیازی: ' + ' -> '.join(cycle + [cycle[0]])))
        for item in self.data['review']:
            if s(item.get('review_status')) == 'OPEN':
                issues.append(Issue('REVIEW', s(item.get('issue_type')),
                                    f'بازبینی منبع: {s(item.get("course_name"))} | {s(item.get("source_or_reason"))}',item.get('source_row')))
        return issues

    def course_detail(self, ref: str) -> dict:
        found = self.lookup(ref)
        if not found: raise ValueError(f'درس با کد/شناسه {ref} یافت نشد')
        ids = {s(x.get('course_id')) for x in found}
        if len(ids)>1: raise ValueError('کد رسمی مبهم است؛ از شناسه داخلی استفاده کنید')
        cid = next(iter(ids))
        prereqs = [r for r in self.relations if s(r.get('course_id'))==cid and s(r.get('relation_type'))=='PRE']
        coreqs = [r for r in self.relations if s(r.get('course_id'))==cid and s(r.get('relation_type'))=='CO']
        return {'courses':found,'prerequisites':prereqs,'corequisites':coreqs,
                'credit_conditions':[r for r in self.data['credit_conditions'] if s(r.get('course_id'))==cid]}

    def check_course(self, ref: str, passed: list[str], concurrent: list[str] | None = None,
                     passed_credits: int | None = None) -> dict:
        """Preliminary constraint check only; not an official permission to enroll."""
        detail = self.course_detail(ref)
        courses = detail['courses']
        cid = s(courses[0].get('course_id'))
        passed_ids = self._resolve_refs(passed)
        concurrent_ids = self._resolve_refs(concurrent or [])
        blockers=[]; warnings=[]
        if cid in passed_ids: warnings.append('این درس قبلاً در مجموعه دروس گذرانده‌شده ثبت شده است')
        for rel in detail['prerequisites']:
            target_id=s(rel.get('related_course_id'))
            if s(rel.get('link_status'))!='OK' or not target_id:
                warnings.append('رابطه پیش‌نیازی نامشخص: '+s(rel.get('source_text')))
            elif target_id not in passed_ids:
                blockers.append('پیش‌نیاز گذرانده نشده: '+s(rel.get('related_course_code')))
        for rel in detail['corequisites']:
            target_id=s(rel.get('related_course_id'))
            if s(rel.get('link_status'))!='OK' or not target_id:
                warnings.append('رابطه هم‌نیازی نامشخص: '+s(rel.get('source_text')))
            elif target_id not in passed_ids | concurrent_ids:
                blockers.append('هم‌نیاز نه گذرانده شده و نه هم‌زمان انتخاب شده: '+s(rel.get('related_course_code')))
        for cond in detail['credit_conditions']:
            if s(cond.get('condition_type')) == 'minimum_passed_credits':
                minimum=int(cond['min_passed_credits'])
                if passed_credits is None:
                    warnings.append(f'بررسی شرط حداقل {minimum} واحد به تعداد واحد گذرانده‌شده نیاز دارد')
                elif passed_credits < minimum:
                    blockers.append(f'حداقل {minimum} واحد لازم است؛ مقدار اعلام‌شده: {passed_credits}')
        for course in courses:
            if s(course.get('validation_status')) == 'REVIEW_RELATION':
                warnings.append('متن پیش‌نیاز/هم‌نیاز این درس کاملاً تعیین تکلیف نشده است')
            if not s(course.get('course_code')):
                warnings.append('کد رسمی این درس در چارت ثبت نشده است')
        warnings.append('قوانین بسته‌های انتخابی، ترم ارائه، سقف واحد و استثناهای آموزشی هنوز در این مرحله اعمال نشده‌اند')
        return {'curriculum':self.chart,'course_id':cid,'course_name':s(courses[0].get('course_name')),
                'result':'BLOCKED' if blockers else ('NEEDS_REVIEW' if len(warnings)>1 else 'PRELIMINARY_PASS'),
                'blockers':blockers,'warnings':warnings}

    def _resolve_refs(self, refs: list[str]) -> set[str]:
        resolved=set()
        for ref in refs:
            if ref in self.by_id: resolved.add(ref);continue
            rows = self.by_code.get(ref,[])
            ids={s(x.get('course_id')) for x in rows}
            if len(ids)==1:resolved.add(next(iter(ids)))
            elif not ids: raise ValueError(f'درس گذرانده‌شده/هم‌زمان ناشناخته: {ref}')
            else: raise ValueError(f'کد مبهم در دروس گذرانده‌شده/هم‌زمان: {ref}')
        return resolved


def compare(left: Curriculum, right: Curriculum) -> dict:
    """Compare identities without automatically declaring similar names equivalent."""
    a=set(left.by_id);b=set(right.by_id)
    changes=[]
    for cid in sorted(a&b):
        x=left.by_id[cid][0]; y=right.by_id[cid][0]
        changed={}
        for key in ('course_code','credits','course_type'):
            if x.get(key)!=y.get(key): changed[key]={'before':x.get(key),'after':y.get(key)}
        if changed:changes.append({'course_id':cid,'course_name':s(y.get('course_name')),'changes':changed})
    return {'left':left.chart,'right':right.chart,
            'only_left':[{'course_id':cid,'name':s(left.by_id[cid][0].get('course_name'))} for cid in sorted(a-b)],
            'only_right':[{'course_id':cid,'name':s(right.by_id[cid][0].get('course_name'))} for cid in sorted(b-a)],
            'shared_id_count':len(a&b),'changed_shared_courses':changes,
            'caution':'شناسه‌های یکسان بر اساس تطبیق قبلی هستند؛ هم‌ارزی آموزشی تأییدنشده باید دستی بررسی شود.'}
