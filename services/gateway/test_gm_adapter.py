import json,threading,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from gm_adapter import GmAdapter,GmError
class GmTests(unittest.TestCase):
 def setUp(self):
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_GET(self):
    if self.headers.get('Cookie')!='dfo_gm_session=fixture':self.send_response(401);self.end_headers();return
    body={'accounts':[{'accountId':7,'name':'10000001','cera':0,'characterCount':0,'internalSecret':'must-not-proxy'}]} if self.path=='/api/accounts' else {'characters':[{'accountId':8,'characterId':1,'name':'mismatched'}]}
    raw=json.dumps(body).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
   def do_POST(self):
    if self.path!='/api/auth/login':self.send_response(405);self.end_headers();return
    body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));ok=body.get('password')=='fixture';raw=json.dumps({'success':ok}).encode();self.send_response(200)
    if ok:self.send_header('Set-Cookie','dfo_gm_session=fixture; Path=/')
    self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
  self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.url='http://127.0.0.1:'+str(self.server.server_port)
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join()
 def test_auth_cookie_and_field_allowlist(self):
  adapter=GmAdapter(self.url,'fixture');result=adapter.accounts();self.assertEqual(result['accounts'][0]['name'],'10000001');self.assertNotIn('internalSecret',result['accounts'][0])
  with self.assertRaises(GmError):adapter.characters(7)
 def test_bad_auth_and_external_url(self):
  with self.assertRaises(GmError):GmAdapter(self.url,'wrong').accounts()
  with self.assertRaises(ValueError):GmAdapter('http://example.com:5051')
