"""Run from project root: python -m unittest discover -s tests -v"""
import json
from pathlib import Path
import sys
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from analyzer import DataError, analyze_transcript
from server import Handler, ThreadingHTTPServer


SAMPLE = {
    'schema_version': '1.0',
    'student': {'student_id': 'TEST-0001', 'full_name': 'دانشجوی آزمایشی', 'major': 'مهندسی کامپیوتر'},
    'semesters': [
        {'academic_year_start': 1402, 'term': 1,
         'courses': [
             {'course_code': '2101', 'course_name': 'ریاضی 1', 'credits': 3, 'grade': 9.75},
             {'course_code': '30006', 'course_name': 'ریاضیات گسسته', 'credits': 3, 'grade': None},
             {'course_code': 'X-NOT-IN-CHART', 'course_name': 'درس آزمایشی', 'credits': 2, 'grade': 11.0},
         ], 'reported_summary': {'term_attempted_credits': 8, 'term_gpa': 11.0,
                                  'cumulative_passed_credits': 2, 'cumulative_gpa': 11.0}},
        {'academic_year_start': 1402, 'term': 2,
         'courses': [{'course_code': '2101', 'course_name': 'ریاضی ۱', 'credits': 3, 'grade': 17.5}],
         'reported_summary': {'term_attempted_credits': 3,
                              'cumulative_passed_credits': 5, 'cumulative_gpa': 15.0}}
    ],
    'extraction': {'semester_count': 2, 'attempt_count': 4, 'warnings': []}
}


class AnalyzerTests(unittest.TestCase):
    def test_analyzer_preserves_repeats_and_maps_official_codes(self):
        result = analyze_transcript(SAMPLE, '1401-1402')
        self.assertEqual(result['overview']['course_attempts'], 4)
        self.assertEqual(result['overview']['attempted_credits_from_rows'], 11)
        self.assertEqual(result['overview']['matched_attempts'], 3)
        self.assertEqual(result['overview']['observed_grades_below_10'], 1)
        self.assertEqual(result['overview']['observed_missing_grades'], 1)
        self.assertEqual(result['overview']['latest_reported_passed_credits'], 5)
        self.assertEqual(len(result['repeated_courses']), 1)
        self.assertEqual(result['repeated_courses'][0]['course_name'], 'ریاضی ۱')
        self.assertEqual(result['unmatched_courses'][0]['course_code'], 'X-NOT-IN-CHART')
        self.assertTrue(all('status' not in x for x in result['course_attempts']))

    def test_latest_summary_uses_chronology_not_source_order(self):
        example = json.loads(json.dumps(SAMPLE))
        example['semesters'].reverse()
        result = analyze_transcript(example, '1401-1402')
        self.assertEqual(result['overview']['latest_reported_gpa'], 15.0)
        self.assertEqual(result['overview']['latest_reported_passed_credits'], 5)
        self.assertEqual([t['term'] for t in result['semesters']], [1, 2])

    def test_rejects_invalid_grade(self):
        example = json.loads(json.dumps(SAMPLE))
        example['semesters'][0]['courses'][0]['grade'] = 25
        with self.assertRaises(DataError):
            analyze_transcript(example, '1401-1402')

    def test_rejects_invalid_chart(self):
        with self.assertRaises(DataError):
            analyze_transcript(SAMPLE, '../other')

    def test_warning_on_credits_mismatch(self):
        example = json.loads(json.dumps(SAMPLE))
        example['semesters'][0]['reported_summary']['term_attempted_credits'] = 9
        result = analyze_transcript(example, '1401-1402')
        self.assertTrue(any('مغایرت واحدهای اخذشده' in w for w in result['warnings']))


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.httpd.pairing_token = 'test-pairing-key'
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.address = f'http://127.0.0.1:{cls.httpd.server_port}/analyze'
        cls.origin = 'chrome-extension://' + 'a' * 32

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=4)

    def post(self, *, origin=True, token='test-pairing-key'):
        headers = {'Content-Type': 'application/json', 'X-Local-Token': token}
        if origin:
            headers['Origin'] = self.origin
        req = Request(self.address, json.dumps({'chart': '1401-1402', 'transcript': SAMPLE}).encode(),
                      headers=headers, method='POST')
        try:
            with urlopen(req, timeout=10) as resp:
                return resp.status, json.load(resp), dict(resp.headers)
        except HTTPError as exc:
            return exc.code, json.loads(exc.read()), dict(exc.headers)

    def test_pairing_and_origin_required(self):
        self.assertEqual(self.post(origin=False)[0], 403)
        self.assertEqual(self.post(token='bad')[0], 401)

    def test_analyze_over_http(self):
        status, report, headers = self.post()
        self.assertEqual(status, 200)
        self.assertEqual(report['overview']['matched_attempts'], 3)
        self.assertEqual(headers.get('Access-Control-Allow-Origin'), self.origin)

    def test_preflight(self):
        req = Request(self.address, method='OPTIONS', headers={
            'Origin': self.origin,
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type,x-local-token',
        })
        with urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 204)
            self.assertIn('X-Local-Token', resp.headers['Access-Control-Allow-Headers'])


if __name__ == '__main__':
    unittest.main()
