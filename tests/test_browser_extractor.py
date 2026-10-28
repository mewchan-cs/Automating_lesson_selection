"""Browser extraction with previously anonymized sample. Requires playwright + Chromium.
Optional test: python tests/test_browser_extractor.py
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    page = browser.new_page()
    page.set_content((ROOT / 'tests/fixture_transcript_anonymous.html').read_text(encoding='utf-8'))
    result = page.evaluate((ROOT / 'extension/extractor.js').read_text(encoding='utf-8'))
    assert result['found']
    report = result['transcript']
    assert report['extraction']['semester_count'] == 8
    assert report['extraction']['attempt_count'] == 48
    assert report['extraction']['latest_reported_summary']['cumulative_attempted_credits'] == 107
    assert report['extraction']['latest_reported_summary']['cumulative_passed_credits'] == 97
    assert all(c['status'] == 'UNDETERMINED' for s in report['semesters'] for c in s['courses'])
    print('PASS: 8 semesters, 48 attempts, credits 107 / passed 97 as reported by portal')
    browser.close()
