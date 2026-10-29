"""Exercise the real HTTP handler over byte streams; no socket/network access."""
import io
import json
from types import SimpleNamespace
import unittest
from test_backend import SAMPLE
from server import Handler


class Connection:
    def __init__(self,data): self.input=io.BytesIO(data);self.output=bytearray()
    def makefile(self,*args,**kwargs): return self.input
    def sendall(self,data): self.output.extend(data)


class InMemoryApiTests(unittest.TestCase):
    def post(self,review=True,token='test',origin='chrome-extension://'+'a'*32,target='regular',mode='academic'):
        body=json.dumps({'chart':'1401-1402','transcript':SAMPLE,'academic_review':review,'target_term':target,'review_mode':mode}).encode()
        headers=f'POST /analyze HTTP/1.0\r\nOrigin: {origin}\r\nX-Local-Token: {token}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n'.encode()
        conn=Connection(headers+body)
        Handler(conn,('127.0.0.1',0),SimpleNamespace(pairing_token='test'))
        raw=bytes(conn.output);head,payload=raw.split(b'\r\n\r\n',1)
        return int(head.split()[1]),json.loads(payload)

    def test_opt_in_response_contains_new_review(self):
        status,body=self.post()
        self.assertEqual(status,200)
        self.assertIn('academic_review',body)
        self.assertIsNone(body['academic_review']['credit_limit']['maximum'])
        self.assertIsNone(body['academic_review']['last_term']['gpa'])  # cumulative GPA is not term GPA

    def test_default_flow_unchanged(self):
        status,body=self.post(review=False)
        self.assertEqual(status,200)
        self.assertNotIn('academic_review',body)
        self.assertIn('visual_summary',body)

    def test_invalid_option_rejected(self):
        self.assertEqual(self.post(review='yes')[0],422)
        self.assertEqual(self.post(target='invalid')[0],422)

    def test_token_and_origin_still_enforced(self):
        self.assertEqual(self.post(token='wrong')[0],401)
        self.assertEqual(self.post(origin='https://example.com')[0],403)

    def test_graduation_mode_has_no_status_or_credit_cap(self):
        status,body=self.post(mode='graduation')
        self.assertEqual(status,200)
        data=body['academic_review']
        self.assertEqual(data['mode'],'graduation')
        self.assertNotIn('academic_status',data)
        self.assertNotIn('credit_limit',data)
        self.assertTrue(data['categories'])

    def test_invalid_review_mode_is_rejected(self):
        self.assertEqual(self.post(mode='invalid')[0],422)


if __name__=='__main__': unittest.main()
