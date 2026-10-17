import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from plugins_api import Plugins,PluginError

class PluginTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.status={'serverId':'fixture','edition':'custom','serverVersion':'86s4a21','instanceId':'fixture-instance','defaultPluginReady':False,'supportedActions':['list'],'plugins':[{'id':'meowlink.custom','product':'MeowLink+','installed':True,'loaded':False,'state':'failed','error':'fixture health failed','required':True,'pluginVersion':'0.1.0','dependencies':[],'permissions':[],'configurationSchema':{}}]}
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.headers.get('Origin') or self.headers.get('X-Arad-Control-Key')!='F'*40:self.send_response(403);self.end_headers();return
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(owner.status).encode())
            def log_message(self,*args):pass
        self.http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=self.http.serve_forever,daemon=True).start();self.addCleanup(self.http.server_close);self.addCleanup(self.http.shutdown)
        self.api=Plugins(Path(self.temp.name)/'connection.json',protector=lambda b,decrypt=False:b)
    def connect(self):return self.api.save({'url':'http://127.0.0.1:'+str(self.http.server_port),'key':'F'*40})
    def test_unconfigured_is_not_loaded_and_secret_is_not_returned(self):
        r=self.api.status();self.assertFalse(r['connected']);self.assertEqual(r['plugins'],[])
        r=self.connect();self.assertTrue(r['keySet']);self.assertNotIn('key',r);self.assertNotIn('F'*40,json.dumps(r))
    def test_authenticated_host_status_preserves_health_failure(self):
        self.connect();r=self.api.status();self.assertTrue(r['connected']);self.assertFalse(r['plugins'][0]['loaded']);self.assertEqual(r['plugins'][0]['error'],'fixture health failed');self.assertEqual(r['supportedActions'],['list'])
    def test_edition_version_and_inconsistent_loaded_state_rejected(self):
        self.connect()
        for key,bad in [('edition','sponsored'),('serverVersion','95s5a9')]:
            old=self.status[key];self.status[key]=bad
            with self.assertRaises(PluginError):self.api.status()
            self.status[key]=old
        self.status['plugins'][0]['loaded']=True;self.status['plugins'][0]['installed']=False
        with self.assertRaises(PluginError):self.api.status()
    def test_cloud_http_and_embedded_credentials_rejected(self):
        for url in ['http://example.invalid','https://user@example.invalid','https://example.invalid/path','https://example.invalid/?key=x']:
            with self.assertRaises(PluginError):self.api.save({'url':url})
