import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from environment import Environment
from gm_bridge import GMBridge

class BridgeTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  storage=self.root/'server/work/dfo-lan/runtime/storage';storage.mkdir(parents=True)
  (self.root/'server/work/dfo-lan/go.mod').write_text('module dfolan\n')
  self.database=storage/'fixture.sqlite3'
  db=sqlite3.connect(self.database);db.executescript('CREATE TABLE accounts(id INTEGER,username TEXT);CREATE TABLE characters(id INTEGER,account_id INTEGER,name TEXT,profession INTEGER,state TEXT,deleted_at TEXT);INSERT INTO accounts VALUES(1,"fixture");');db.close()
  (storage/'local.json').write_text(json.dumps({'sqlite_path':str(self.database)}))
  self.client=self.root/'client';self.client.mkdir();(self.client/'Script.pvf').write_bytes(b'fixture, not a real PVF archive')
  self.environment=Environment(self.root/'environment.json');self.environment.save({'profile':'115us','mode':'local','root':str(self.root),'version':'fixture'})
  self.helper=self.root/'helper.py';self.helper.write_text("import json,sys,time\nprint(json.dumps({'version':1,'ready':True,'data_source':'pvf','pvf_checksum':'f'*64}),flush=True)\nfor line in sys.stdin:\n request=json.loads(line)\n if request.get('body',{}).get('sleep'):time.sleep(3)\n print(json.dumps({'ok':True,'echo':request}),flush=True)\n")
  self.bridge=GMBridge(self.environment,self.root/'manager',tool=[sys.executable,'-u',str(self.helper)],startup_timeout=3,request_timeout=.3);self.addCleanup(self.bridge.close)
  self.bridge.save({'clientDirectory':str(self.client)})
 def ready(self):
  self.bridge.connect({});deadline=time.monotonic()+5
  while time.monotonic()<deadline:
   state=self.bridge.status()
   if state['state']!='preparing':break
   time.sleep(.01)
  self.assertEqual(state['state'],'ready',state)
  return state
 def call(self,method='overview',**extra):
  return self.bridge.call({'connectionId':self.bridge.status()['connectionId'],'method':method,**extra})
 def test_save_never_connects_and_backup_precedes_pipe(self):
  self.assertIsNone(self.bridge.process);before=hashlib.sha256(self.database.read_bytes()).hexdigest()
  state=self.ready();self.assertTrue(Path(state['backup']).is_file());self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(),before)
  backup=sqlite3.connect(state['backup'])
  try:self.assertEqual(backup.execute('SELECT COUNT(*) FROM accounts').fetchone()[0],1)
  finally:backup.close()
  self.assertTrue(self.call()['ok']);self.assertIsNone(state['gameRunning'])
 def test_unknown_methods_and_wrong_connection_are_rejected(self):
  self.ready()
  with self.assertRaisesRegex(ValueError,'未开放'):self.call('patch.liveStart')
  with self.assertRaisesRegex(ValueError,'失效'):self.bridge.call({'connectionId':'wrong','method':'overview'})
  with self.assertRaisesRegex(ValueError,'格式'):self.call(query={'account':'1'})
 def test_environment_change_rejects_stale_pipe(self):
  self.ready();self.environment.save({'profile':'115us','mode':'local','root':str(self.root),'version':'changed'})
  with self.assertRaisesRegex(ValueError,'失效'):self.call()
  self.assertEqual(self.bridge.status()['state'],'stale')
 def test_timeout_closes_and_reports_unknown_result(self):
  self.ready()
  with self.assertRaisesRegex(ValueError,'结果未知'):self.call('grant',body={'id':'launcher-fixture-operation-1','sleep':True})
  self.assertIsNone(self.bridge.process)
 def test_request_keeps_idempotency_id_unchanged(self):
  self.ready();body={'id':'launcher-fixture-operation-123','gold':1}
  self.assertEqual(self.call('grant',body=body)['echo']['body'],body)
 def test_context_survives_reconnect_but_connection_capability_rotates(self):
  before=self.ready();self.bridge.close();after=self.ready()
  self.assertEqual(before['contextId'],after['contextId'])
  self.assertNotEqual(before['connectionId'],after['connectionId'])
  self.environment.save({'profile':'115us','mode':'local','root':str(self.root),'version':'other'})
  self.bridge.close();changed=self.ready()
  self.assertNotEqual(after['contextId'],changed['contextId'])
 def test_points_pending_persists_across_backend_restart_and_blocks_different_request(self):
  self.ready();body={'id':'launcher-fixture-points-0001','account':1,'character':1,'action':'sp','value':7,'reason':'fixture'}
  # Fake helper does not acknowledge a mutation: the request must stay pending.
  self.call('character.edit',body=body)
  self.assertEqual(self.bridge.pending()['body'],{**body,'account':'1','character':'1'})
  self.bridge.close()
  restarted=GMBridge(self.environment,self.root/'manager',tool=[sys.executable,'-u',str(self.helper)],startup_timeout=3,request_timeout=.3)
  self.addCleanup(restarted.close)
  self.assertEqual(restarted.status()['pending']['body'],{**body,'account':'1','character':'1'})
  self.bridge=restarted;self.ready()
  self.call('character.edit',body=body)
  with self.assertRaisesRegex(ValueError,'待核对'):self.call('character.edit',body={**body,'value':8})
 def test_points_pending_clears_only_after_matching_receipt(self):
  self.helper.write_text("import json,sys\nprint(json.dumps({'version':1,'ready':True,'data_source':'pvf','pvf_checksum':'f'*64}),flush=True)\nfor line in sys.stdin:\n r=json.loads(line)\n print(json.dumps({'ok':True,'grant_id':r['body']['id']}),flush=True)\n")
  self.ready();self.call('character.edit',body={'id':'launcher-fixture-points-0002','account':1,'character':1,'action':'tp','value':1,'reason':'fixture'})
  self.assertIsNone(self.bridge.pending())
 def test_resource_warning_is_not_lost_when_progress_ring_advances(self):
  self.helper.write_text("import json,sys\nsys.stderr.reconfigure(encoding='utf-8')\nprint('警告：缺少中文补译',file=sys.stderr,flush=True)\nfor i in range(30):print('progress '+str(i),file=sys.stderr,flush=True)\nprint(json.dumps({'version':1,'ready':True,'data_source':'pvf','pvf_checksum':'f'*64}),flush=True)\nfor line in sys.stdin:print('{}',flush=True)\n",encoding='utf-8')
  self.ready();deadline=time.monotonic()+2
  while time.monotonic()<deadline and not self.bridge.status()['resourceWarnings']:time.sleep(.01)
  self.assertTrue(any('中文补译' in x for x in self.bridge.status()['resourceWarnings']))
  self.bridge.close();self.assertFalse(self.bridge.status()['resourceWarnings'])
 def test_int64_request_pipe_and_pending_are_lossless_and_unsafe_numbers_rejected(self):
  self.ready();body={'id':'launcher-fixture-int64-0001','account':'9223372036854775807','character':'9007199254740993','action':'sp','value':1,'reason':'int64 fixture'}
  echo=self.call('character.edit',body=body)['echo']['body']
  self.assertEqual(echo['account'],9223372036854775807);self.assertEqual(echo['character'],9007199254740993)
  self.assertEqual(self.bridge.pending()['body'],body)
  before=self.bridge.pending_path.read_bytes()
  with self.assertRaises(ValueError):self.call('character.edit',body={**body,'account':9007199254740992})
  self.assertEqual(self.bridge.pending_path.read_bytes(),before)
  with self.assertRaises(ValueError):self.call('character',query={'id':['01']})
 def test_legacy_pending_safe_numeric_ids_are_exposed_as_strings_without_rewriting(self):
  body={'id':'launcher-fixture-legacy-0001','account':1,'character':2,'action':'sp','value':1,'reason':'fixture'}
  self.bridge.pending_path.write_text(json.dumps({'context':'fixture','checksum':'f'*64,'body':body}))
  before=self.bridge.pending_path.read_bytes()
  self.assertEqual(self.bridge.pending()['body'],{**body,'account':'1','character':'2'})
  self.assertEqual(self.bridge.pending_path.read_bytes(),before)
 def test_identity_edits_are_not_available_through_native_gm_or_points(self):
  self.ready();process=self.bridge.process
  for method in ('identity.login_id.set','identity.uid.set','account.rename'):
   with self.assertRaisesRegex(ValueError,'未开放'):self.call(method)
  edit={'id':'launcher-no-identity-mutation-01','account':'1','character':'1','action':'sp','value':1,'reason':'fixture'}
  for key,value in [('uid','00000001'),('login_id','changed1'),('username','nickname')]:
   with self.assertRaisesRegex(ValueError,'参数无效'):self.call('character.edit',body={**edit,key:value})
  self.assertIs(self.bridge.process,process);self.assertIsNone(self.bridge.pending())
 def test_missing_pvf_and_cloud_never_start_pipe(self):
  (self.client/'Script.pvf').unlink()
  with self.assertRaisesRegex(ValueError,'Script.pvf'):self.bridge.connect({})
  self.assertIsNone(self.bridge.process)
  self.environment.save({'profile':'115us','mode':'cloud','root':'/srv/synthetic','version':'fixture'})
  with self.assertRaisesRegex(ValueError,'云端'):self.bridge.connect({})
 def test_wrong_server_module_never_starts_or_backs_up(self):
  (self.root/'server/work/dfo-lan/go.mod').write_text('module unrelated\n')
  with self.assertRaisesRegex(ValueError,'115US'):self.bridge.connect({})
  self.assertIsNone(self.bridge.process)
  self.assertFalse((self.root/'manager/backups').exists())
