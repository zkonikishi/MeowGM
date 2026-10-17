import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from admission import AdmissionServer, AdmissionStore

class AdmissionHttpTests(unittest.TestCase):
    def test_authenticated_health_and_prepare_claim_over_http(self):
        with tempfile.TemporaryDirectory() as directory:
            calls=[]
            def consume(ticket,rid):
                calls.append(rid)
                return {'ok':True,'uid':'10000001','realm_id':'hk','game_account_id':7,'game_login_name':'10000001','admission_id':rid}
            server=AdmissionServer(('127.0.0.1',0),AdmissionStore(Path(directory)/'admission.db',consume),'k'*32)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(path,body=None,key='k'*32):
                headers={'X-OO-Game-Key':key,'Content-Type':'application/json'}
                req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/internal/v1/admissions/{path}',data=None if body is None else json.dumps(body).encode(),headers=headers)
                try:response=urllib.request.urlopen(req,timeout=3)
                except urllib.error.HTTPError as e:response=e
                with response:return response.status,json.loads(response.read())
            try:
                self.assertEqual(request('health',key='wrong')[0],403)
                status,health=request('health');self.assertEqual(status,200);self.assertFalse(health['platform_checked']);self.assertEqual(calls,[])
                cid=str(uuid.uuid4())
                status,result=request('prepare',{'connection_id':cid,'uid':'10000001','ticket':'a'*64});self.assertEqual(status,200)
                body={'connection_id':cid,'admission_id':result['admission_id']}
                self.assertEqual(request('claim',body)[0],200)
                self.assertEqual(request('claim',body)[0],409)
                self.assertEqual(request('close',{'connection_id':cid})[0],200)
                self.assertEqual(len(calls),1)
            finally:server.shutdown();thread.join();server.server_close()
