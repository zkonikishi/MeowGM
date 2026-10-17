import json
import os
from unittest.mock import patch
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from server import Gateway, Store


class PvfApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=self.root/'Script.pvf'
        self.source.write_bytes(b'fixture data, not a validated PVF'+b'X'*1048576)
        store=Store(self.root/'qa.db');store.initialize('pvf-fixture-password')
        self.server=Gateway(('127.0.0.1',0),store)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
        self.cookie=''
        self.request('/api/admin/login',{'username':'admin','password':'pvf-fixture-password'})

    def request(self,path,body=None,authenticated=True,origin=True):
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=self.origin
        if authenticated:headers['Cookie']=self.cookie
        req=urllib.request.Request(self.origin+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:r=urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:r=e
        cookie=r.headers.get('Set-Cookie')
        if cookie:self.cookie=cookie.split(';')[0]
        return r.status,json.loads(r.read())

    def test_missing_provider_reports_unavailable_and_preserves_file(self):
        code,info=self.request('/api/admin/pvf/inspect',{'path':str(self.source)})
        self.assertEqual(code,200);self.assertFalse(info['headerValidated'])
        self.assertFalse(info['capabilities']['huazhiGameEncryption'])
        code,key=self.request('/api/admin/pvf/key',{})
        self.assertEqual(code,400)
        self.assertIn('尚未提供',key['error'])
        self.assertFalse((self.root/'pvf-keys').exists())

    def test_authorization_origin_and_unknown_mode(self):
        self.assertEqual(self.request('/api/admin/pvf/key',{},authenticated=False)[0],401)
        self.assertEqual(self.request('/api/admin/pvf/key',{},origin=False)[0],403)
        code,result=self.request('/api/admin/pvf/protect',{'path':str(self.source),'mode':'huazhi','keyPath':'unused'})
        self.assertEqual(code,400);self.assertIn('尚未提供',result['error'])
    @patch.dict(os.environ,{"MEOW_MANAGER_TEST_MODE":"1"})
    def test_simulated_catalog_api_requires_admin_and_reports_conflict(self):
        self.assertEqual(self.request('/api/admin/meowpay/catalog',authenticated=False)[0],401)
        code,r=self.request('/api/admin/meowpay/catalog');self.assertEqual(code,200);self.assertTrue(r['simulation']);self.assertFalse(r['productionEntitlementImplemented'])
        body={'revision':r['catalog']['revision'],'pointsPerMinor':10,'monthlyMinor':1000,'yearlyMinor':9900,'blackDiamondEnabled':True}
        self.assertEqual(self.request('/api/admin/meowpay/catalog',body,origin=False)[0],403)
        self.assertEqual(self.request('/api/admin/meowpay/catalog',body)[0],200)
        self.assertEqual(self.request('/api/admin/meowpay/catalog',body)[0],409)
        self.assertEqual(self.request('/api/admin/meowpay/catalog',{**body,'actor':'forged'})[0],400)


if __name__=='__main__':unittest.main()
