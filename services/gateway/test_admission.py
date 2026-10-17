import json
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from admission import AdmissionStore,Fault,PlatformConsumer

class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'admission.db';self.calls=[]
        def consume(ticket,rid):
            self.calls.append(rid)
            return {'ok':True,'uid':'10000001','realm_id':'hk','game_account_id':7,'game_login_name':'10000001','admission_id':rid}
        self.consume=consume;self.store=AdmissionStore(self.path,consume);self.cid=str(uuid.uuid4());self.ticket='a'*64
    def tearDown(self):self.tmp.cleanup()
    def prepare(self,cid=None,ticket=None):return self.store.prepare(cid or self.cid,'10000001',ticket or self.ticket)
    def test_replay_claim_and_no_plaintext_storage(self):
        first=self.prepare();self.assertEqual(self.prepare(),first);self.assertEqual(len(self.calls),1)
        with self.assertRaises(Fault):self.prepare(str(uuid.uuid4()))
        claimed=self.store.claim(self.cid,first['admission_id']);self.assertEqual(claimed,first)
        with self.assertRaises(Fault):self.store.claim(self.cid,first['admission_id'])
        with self.assertRaises(Fault):self.prepare()
        self.assertNotIn(self.ticket.encode(),self.path.read_bytes())
    def test_uncertain_retry_same_request_id(self):
        count=0
        def flaky(ticket,rid):
            nonlocal count
            result=self.consume(ticket,rid);count+=1
            if count==1:raise Fault('platform_unavailable',503)
            return result
        self.store.consume=flaky
        with self.assertRaises(Fault):self.prepare()
        self.prepare();self.assertEqual(self.calls[0],self.calls[1])
    def test_restart_old_and_new_connection_denied(self):
        self.prepare();self.store=AdmissionStore(self.path,self.consume)
        with self.assertRaises(Fault):self.prepare()
        with self.assertRaises(Fault):self.prepare(str(uuid.uuid4()))
    def test_parallel_claim_exactly_once(self):
        admission=self.prepare()['admission_id']
        def claim(_):
            try:self.store.claim(self.cid,admission);return True
            except Fault:return False
        with ThreadPoolExecutor(max_workers=8) as pool:self.assertEqual(sum(pool.map(claim,range(8))),1)
    def test_leading_zero_uid_preserved(self):
        self.store.consume=lambda ticket,rid:{'ok':True,'uid':'00000001','realm_id':'hk','game_account_id':7,'game_login_name':'00000001','admission_id':rid}
        result=self.store.prepare(self.cid,'00000001',self.ticket)
        self.assertEqual(result['uid'],'00000001')
        with self.assertRaises(Fault):self.store.prepare(str(uuid.uuid4()),'00000000','b'*64)
    def test_disconnect_during_consume_does_not_revive(self):
        entered=threading.Event();release=threading.Event()
        def slow(ticket,rid):entered.set();release.wait(3);return self.consume(ticket,rid)
        self.store.consume=slow
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(self.prepare);self.assertTrue(entered.wait(2));self.store.close(self.cid);release.set()
            with self.assertRaises(Fault):future.result()
        with self.assertRaises(Fault):self.prepare()
    def test_binding_mismatch_never_ready(self):
        def mismatch(ticket,rid):return {**self.consume(ticket,rid),'uid':'10000002'}
        self.store.consume=mismatch
        with self.assertRaises(Fault):self.prepare()
        with self.assertRaises(Fault):self.store.claim(self.cid,str(uuid.uuid4()))
    def test_expiry_and_same_connection_new_ticket(self):
        ready=self.prepare()
        with self.assertRaises(Fault):self.prepare(ticket='b'*64)
        with self.store.db() as db:db.execute('UPDATE admissions SET created=0')
        with self.assertRaises(Fault):self.store.claim(self.cid,ready['admission_id'])
    def test_upstream_tls_required(self):
        with self.assertRaises(ValueError):PlatformConsumer('http://example.com','a'*32)
        with self.assertRaises(ValueError):PlatformConsumer('https://user:password@example.com','a'*32)

if __name__=='__main__':unittest.main()
