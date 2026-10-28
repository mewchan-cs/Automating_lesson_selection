"""Opt-in localhost bridge for the Chromium extension (Python 3.10+, stdlib only).

Security controls: loopback only, unpredictable token, strict Origin, bounded payload,
no persistent PII, no raw body logs. This is NOT a public service.
"""
from __future__ import annotations

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import secrets
from urllib.parse import urlsplit

from analyzer import analyze_transcript, DataError

HOST = '127.0.0.1'
PORT = 8765
MAX_BYTES = 2_000_000
EXTENSION_ORIGIN = re.compile(r'^chrome-extension://[a-p]{32}$')


class Handler(BaseHTTPRequestHandler):
    server_version = 'AcademicAdvisorLocal/0.1'

    def log_message(self, format, *args):
        # Suppress server access logging to avoid incidental personal-data leakage.
        pass

    def _origin(self):
        value = self.headers.get('Origin', '')
        return value if EXTENSION_ORIGIN.fullmatch(value) else None

    def _headers(self, status, *, cors=False):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if cors and self._origin():
            self.send_header('Access-Control-Allow-Origin', self._origin())
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Local-Token')
            self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
            self.send_header('Vary', 'Origin')
        self.end_headers()

    def _send(self, status, body, *, cors=True):
        serialized = json.dumps(body, ensure_ascii=False).encode('utf-8')
        # Response body follows response headers. No sensitive data written to disk.
        self._headers(status, cors=cors)
        self.wfile.write(serialized)

    def do_OPTIONS(self):
        if self.path != '/analyze' or not self._origin():
            return self._send(403, {'error': 'origin_not_allowed'}, cors=False)
        self._headers(204, cors=True)

    def do_GET(self):
        # Do not expose data or token via GET (including /health).
        return self._send(404, {'error': 'not_found'}, cors=False)

    def do_POST(self):
        if urlsplit(self.path).path != '/analyze' or not self._origin():
            return self._send(403, {'error': 'origin_not_allowed'}, cors=False)
        supplied = self.headers.get('X-Local-Token', '')
        if not supplied or not hmac.compare_digest(supplied, self.server.pairing_token):
            return self._send(401, {'error': 'invalid_pairing_token'})
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            return self._send(415, {'error': 'content_type_must_be_json'})
        try:
            length = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            length = -1
        if not 0 < length <= MAX_BYTES:
            return self._send(413, {'error': 'invalid_content_length'})
        try:
            req = json.loads(self.rfile.read(length))
            if not isinstance(req, dict):
                raise DataError('درخواست JSON نامعتبر است.')
            output = analyze_transcript(req.get('transcript'), req.get('chart'))
        except (UnicodeDecodeError, json.JSONDecodeError, DataError, ValueError, KeyError, TypeError) as exc:
            return self._send(422, {'error': 'invalid_transcript', 'message': str(exc)[:500]})
        except Exception:
            # Do not disclose sensitive internals in server responses.
            return self._send(500, {'error': 'internal_error', 'message': 'خطای غیرمنتظره در موتور تحلیل'})
        return self._send(200, output)


def start():
    token = os.environ.get('ADVISOR_LOCAL_TOKEN') or secrets.token_urlsafe(24)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.pairing_token = token
    print('\nموتور تحلیل محلی فعال شد.')
    print(f'نشانی: http://{HOST}:{PORT}')
    print('کد اتصال (فقط در افزونه مرورگر وارد شود):')
    print(token, flush=True)
    print('برای توقف: Ctrl+C | تا وقتی این پنجره باز است موتور فعال می‌ماند.\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    start()
