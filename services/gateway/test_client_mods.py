import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from client_mods import ClientMods

class ClientModsTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);(self.root/'mods/demo').mkdir(parents=True)
  (self.root/'mods/demo/demo.dll').write_bytes(b'synthetic fixture')
  self.path=self.root/'mods/mods.json'
  self.original={'autoDiscover':False,'custom':{'keep':1},'plugins':[{'name':'demo','path':'mods/demo/demo.dll','enabled':True,'custom':'retain'}]}
  self.path.write_text(json.dumps(self.original),encoding='utf-8')
  self.settings={'clientDirectory':str(self.root)}
  self.target={'profile':'115us','mode':'local','root':str(self.root)}
  self.manager=ClientMods(SimpleNamespace(read=lambda:self.target),SimpleNamespace(settings=lambda:self.settings))
 def body(self):
  data=self.manager.list()
  return {'id':'demo','enabled':False,'clientDirectory':data['clientDirectory'],'revision':data['revision']}
 def test_toggle_preserves_unknown_fields_backup_and_dll(self):
  result=self.manager.set_enabled(self.body())
  self.assertFalse(result['mods'][0]['enabled']);self.assertTrue(result['mods'][0]['filePresent'])
  self.assertIsNone(result['mods'][0]['reportedLive'])
  actual=json.loads(self.path.read_text());self.assertEqual(actual['custom'],{'keep':1});self.assertEqual(actual['plugins'][0]['custom'],'retain')
  backup=list(self.path.parent.glob('mods.json.before-meowgm-*'));self.assertEqual(len(backup),1)
  self.assertEqual(json.loads(backup[0].read_text()),self.original)
  self.assertEqual((self.root/'mods/demo/demo.dll').read_bytes(),b'synthetic fixture')
 def test_stale_revision_and_changed_directory_rejected(self):
  body=self.body();self.path.write_text(json.dumps({**self.original,'new':1}))
  with self.assertRaises(ValueError):self.manager.set_enabled(body)
  self.assertFalse(list(self.path.parent.glob('mods.json.before-*')))
  body=self.body();self.settings['clientDirectory']=str(self.root/'other')
  with self.assertRaises(ValueError):self.manager.set_enabled(body)
 def test_host_manifest_is_read_only(self):
  self.path.unlink();host=self.root/'.115us-mods';host.mkdir();(host/'plugins.json').write_text(json.dumps(self.original))
  data=self.manager.list();self.assertFalse(data['mods'][0]['canToggle'])
  with self.assertRaises(ValueError):self.manager.set_enabled(self.body())
  self.assertEqual(json.loads((host/'plugins.json').read_text()),self.original)
 def test_invalid_json_duplicate_id_and_path_escape_preserved(self):
  for value in ['{bad',json.dumps({**self.original,'plugins':self.original['plugins']*2}),json.dumps({'plugins':[{'name':'demo','path':'../escape.dll'}]})]:
   self.path.write_text(value)
   with self.assertRaises(ValueError):self.manager.list()
   self.assertEqual(self.path.read_text(),value)
 def test_symlink_rejected(self):
  alias=self.root/'mods/alias'
  try:alias.symlink_to(self.root/'mods/demo',target_is_directory=True)
  except OSError:self.skipTest('symlink creation unavailable')
  self.path.write_text(json.dumps({'plugins':[{'name':'demo','path':'mods/alias/demo.dll'}]}))
  with self.assertRaises(ValueError):self.manager.list()
 def test_cloud_and_non_boolean_never_write(self):
  body=self.body();body['enabled']='false'
  with self.assertRaises(ValueError):self.manager.set_enabled(body)
  self.target['mode']='cloud'
  with self.assertRaises(ValueError):self.manager.list()
 def test_loader_and_bypass_warning(self):
  host=self.root/'.115us-mods';host.mkdir();(host/'mod-loader.dll').write_bytes(b'fixture')
  (host/'plugins.json').write_text(json.dumps({'autoDiscover':False,'recurse':False,'plugins':[{'name':'mod-loader','path':'mod-loader.dll'}]}))
  self.assertTrue(self.manager.list()['loaderAvailable'])
