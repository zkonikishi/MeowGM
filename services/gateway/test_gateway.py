import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from server import Store, Gateway

class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'test.db'
        self.store=Store(self.path)
        self.store.initialize('fixture-password-123')
        self.server=Gateway(('127.0.0.1',0),self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://'+self.server.authority
        self.cookie=''
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,body=None,origin=True):
        headers={'Cookie':self.cookie}
        if body is not None:
            headers['Content-Type']='application/json'
            if origin: headers['Origin']=self.base
        req=urllib.request.Request(self.base+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        try: response=urllib.request.urlopen(req)
        except urllib.error.HTTPError as e: response=e
        with response:
            cookie=response.headers.get('Set-Cookie')
            if cookie:self.cookie=cookie.split(';')[0]
            return response.status,json.loads(response.read())
    def login(self):self.assertEqual(self.request('/api/admin/login',{'password':'fixture-password-123'})[0],200)
    def test_auth_origin_logout(self):
        self.assertEqual(self.request('/api/admin/launcher/install',{})[0],401)
        self.assertEqual(self.request('/api/admin/deployment/start',{'action':'uninstall'})[0],401)
        self.assertEqual(self.request('/api/admin/deployment/status',{})[0],401)
        self.assertEqual(self.request('/api/admin/config')[0],401)
        self.assertEqual(self.request('/api/admin/login',{'password':'wrong'})[0],401)
        self.assertEqual(self.request('/api/admin/login',{'password':'fixture-password-123'},False)[0],403)
        self.login()
        self.assertEqual(self.request('/api/admin/launcher/install',{},False)[0],403)
        self.assertEqual(self.request('/api/admin/deployment/start',{'action':'uninstall'},False)[0],403)
        self.assertEqual(self.request('/api/admin/deployment/start',{'action':'uninstall'})[0],400)
        self.assertEqual(self.request('/api/admin/deployment/status',{})[1]['jobs'],[])
        self.assertEqual(self.request('/api/admin/config')[0],200)
        self.request('/api/admin/logout',{})
        self.assertEqual(self.request('/api/admin/config')[0],401)
    def test_publish_conflict_persistence_audit(self):
        self.login();config=self.request('/api/public/config')[1]
        config['announcements']=[{'title':'维护通知','body':'测试正文 <script>仅作为文本</script>'}]
        self.assertEqual(self.request('/api/admin/publish',config)[0],200)
        self.assertEqual(self.request('/api/admin/publish',config)[0],409)
        self.assertEqual(self.request('/api/public/config')[1]['revision'],1)
        self.assertEqual(Store(self.path).read()['announcements'],config['announcements'])
        self.assertEqual(len(self.request('/api/admin/audit')[1]),1)
    def test_invalid_config_no_write(self):
        self.login();config=self.store.read();config['maintenance']='true'
        self.assertEqual(self.request('/api/admin/publish',config)[0],400)
        self.assertEqual(self.store.read()['revision'],0)
        config=self.store.read();config['realm']='old-flower'
        self.assertEqual(self.request('/api/admin/publish',config)[0],400)
    def test_session_expires(self):
        self.login()
        with self.server.auth_lock:
            self.server.sessions={k:0 for k in self.server.sessions}
        self.assertEqual(self.request('/api/admin/config')[0],401)
    def test_connection_settings_auth_secrets_and_apply(self):
        self.assertEqual(self.request('/api/admin/connections')[0],401)
        self.login()
        payload={'gmUrl':'http://127.0.0.1:9','gmPassword':'fixture-secret','platformUrl':'https://platform.example','adminKey':'fixture-key-'+'k'*32,'caFile':''}
        self.assertEqual(self.request('/api/admin/connections',payload,False)[0],403)
        code,result=self.request('/api/admin/connections',payload)
        self.assertEqual(code,200);self.assertTrue(result['adminKeySet'])
        self.assertNotIn('fixture-secret',json.dumps(result));self.assertNotIn('adminKey',result)
        self.assertIsNotNone(self.server.gm);self.assertIsNotNone(self.server.operations.transport)
        self.assertEqual(self.request('/api/admin/connections',{'gmUrl':'http://external.example'})[0],400)
        self.assertEqual(self.server.gm.url,'http://127.0.0.1:9')

if __name__=='__main__':unittest.main()
