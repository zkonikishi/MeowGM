import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from environment import Environment
from mod_manager import ModManager

class ModManagerTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.module=self.root/'server/work/dfo-lan';self.module.mkdir(parents=True);(self.module/'go.mod').write_text('module dfolan\n')
  self.environment=Environment(self.root/'environment.json');self.environment.save({'profile':'115us','mode':'local','root':str(self.root),'version':''});self.manager=ModManager(self.environment)
  self.add_mod('base');self.add_mod('child',['base'])
 def add_mod(self,mod_id,requires=None):
  directory=self.module/'mods'/mod_id;directory.mkdir(parents=True)
  manifest={'schema':2,'id':mod_id,'name':mod_id,'version':'1.0.0','permissions':['server.hook'],'requires':requires or [],'layers':{'server':{'package':'.','hooks':[{'name':'server.boot'}]}}}
  (directory/'mod.json').write_text(json.dumps(manifest),encoding='utf-8')
 def change(self,body):return self.manager.set_enabled({**body,'module':str(self.module.resolve())})
 def test_stale_environment_is_rejected_before_write(self):
  with self.assertRaisesRegex(ValueError,'环境已改变'):self.manager.set_enabled({'id':'child','enabled':False,'module':str(self.root/'other')})
  self.assertFalse((self.module/'mods/enabled.json').exists())
 def test_dependency_is_enforced_and_state_reread(self):
  self.assertEqual(len(self.manager.list()['mods']),2)
  with self.assertRaisesRegex(ValueError,'依赖'):self.change({'id':'base','enabled':False})
  self.change({'id':'child','enabled':False});result=self.change({'id':'base','enabled':False})
  self.assertFalse(next(m for m in result['mods'] if m['id']=='base')['enabled'])
  self.assertTrue(list((self.module/'mods').glob('enabled.json.before-meowgm-*')))
  with self.assertRaisesRegex(ValueError,'依赖'):self.change({'id':'child','enabled':True})
  self.change({'id':'base','enabled':True});self.change({'id':'child','enabled':True})
  self.assertIsNone(result['gameRunning']);self.assertFalse(result['runtimeFresh'])
 def test_rejects_unknown_mod_and_invalid_boolean(self):
  with self.assertRaises(ValueError):self.change({'id':'missing','enabled':True})
  with self.assertRaises(ValueError):self.change({'id':'base','enabled':'false'})
  self.assertFalse((self.module/'mods/enabled.json').exists())
 def test_fresh_and_stale_runtime_are_distinct(self):
  runtime=self.module/'runtime';runtime.mkdir()
  def write(age):
   (runtime/'mods-status.json').write_text(json.dumps({'schema':1,'writtenAt':(datetime.now(timezone.utc)-timedelta(seconds=age)).isoformat(),'mods':[{'id':'base','live':True,'requiresRestart':False}]}))
  write(0);self.assertTrue(next(m for m in self.manager.list()['mods'] if m['id']=='base')['reportedLive'])
  write(60);self.assertIsNone(next(m for m in self.manager.list()['mods'] if m['id']=='base')['reportedLive'])
 def test_cloud_and_wrong_profile_never_run_tool(self):
  self.environment.save({'profile':'115us','mode':'cloud','root':'/srv/synthetic','version':''})
  with self.assertRaisesRegex(ValueError,'云端'):self.manager.list()
  self.environment.save({'profile':'115us','mode':'local','root':str(self.root),'version':''})
  (self.module/'go.mod').write_text('module oldserver\n')
  with self.assertRaisesRegex(ValueError,'dfolan'):self.manager.list()
