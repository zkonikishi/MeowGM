import json
from pathlib import Path
import tempfile
import unittest
from environment import Environment

class TargetTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.path=Path(self.temp.name)/'environment.json';self.env=Environment(self.path)
 def test_four_targets_are_independent_and_preview_never_activates(self):
  for product in ('general','custom'):
   for mode in ('local','cloud'):
    value={'profile':'115us','productMode':product,'mode':mode,'root':str(self.path.parent/product) if mode=='local' else '/srv/'+product,'version':product+'-'+mode,'managementBaseUrl':'https://'+product+'.example.invalid' if mode=='cloud' else '', 'realm':product}
    self.env.save(value)
  before=self.path.read_bytes()
  for product in ('general','custom'):
   for mode in ('local','cloud'):
    self.assertEqual(self.env.target(product,mode)['version'],product+'-'+mode)
  self.assertEqual(self.path.read_bytes(),before)
  self.assertEqual(self.env.read()['mode'],'cloud')
  self.assertFalse(self.env.inspect()['connected'])
 def test_legacy_config_migrates_on_explicit_save_without_losing_local(self):
  old={'profile':'115us','mode':'local','root':str(self.path.parent),'version':'old'}
  self.path.write_text(json.dumps(old))
  self.assertEqual(self.env.read()['productMode'],'general')
  self.assertEqual(json.loads(self.path.read_text()),old)
  self.env.save({'profile':'115us','productMode':'custom','mode':'cloud','root':'/srv/custom','version':'new'})
  self.assertEqual(self.env.target('general','local')['root'],old['root'])
 def test_no_credentials_or_unsafe_https_target_are_accepted(self):
  base={'profile':'115us','mode':'cloud','root':'/srv/test','version':''}
  for url in ['http://example.invalid','https://user:secret@example.invalid','https://example.invalid/api','https://example.invalid?token=x','https://example.invalid#x','https://example.invalid:0','https://example.invalid\\evil']:
   with self.subTest(url=url),self.assertRaises(ValueError):self.env.save({**base,'managementBaseUrl':url})
  with self.assertRaises(ValueError):self.env.save({**base,'dbPassword':'secret'})
  with self.assertRaises(ValueError):self.env.save({**base,'root':'/srv/../production'})
  self.assertFalse(self.path.exists())
 def test_corrupt_target_identity_is_preserved(self):
  self.path.write_text(json.dumps({'schema':2,'active':'general.local','targets':{'general.local':{'profile':'115us','productMode':'custom','mode':'local','root':'','version':''}}}))
  original=self.path.read_bytes()
  with self.assertRaises(ValueError):self.env.read()
  self.assertEqual(self.path.read_bytes(),original)
 def test_older_client_save_preserves_omitted_cloud_fields(self):
  self.env.save({'profile':'115us','productMode':'custom','mode':'cloud','root':'/srv/test','version':'v1','managementBaseUrl':'https://example.invalid','realm':'fixture'})
  self.env.save({'profile':'115us','mode':'cloud','root':'/srv/test','version':'v2'})
  self.assertEqual(self.env.read()['managementBaseUrl'],'https://example.invalid')
  self.assertEqual(self.env.read()['realm'],'fixture')
