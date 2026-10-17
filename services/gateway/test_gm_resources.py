import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from environment import Environment
from gm_bridge import GMBridge
from gm_resources import resources

class ResourceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.env=Environment(self.root/'environment.json');self.env.save({'profile':'115us','mode':'local','root':str(self.root),'version':'fixture'})
  self.client=self.root/'client';self.client.mkdir()
 def test_presence_does_not_enable_forging_or_preview(self):
  config=self.root/'server/work/dfo-lan/configs';config.mkdir(parents=True)
  rule=config/'refine.json';rule.write_text(json.dumps({'version':1,'max_level':8,'record_offset':70}))
  images=self.client/'ImagePacks2';images.mkdir();(images/'fixture.NPK').write_bytes(b'not a valid NPK')
  before=hashlib.sha256(rule.read_bytes()).hexdigest()
  data=resources(self.env,str(self.client))
  self.assertEqual(data['refine']['state'],'parsed');self.assertFalse(data['refine']['operationEnabled'])
  self.assertEqual(data['images']['state'],'present');self.assertFalse(data['images']['previewVerified'])
  self.assertEqual(data['refine']['sha256'],before);self.assertEqual(hashlib.sha256(rule.read_bytes()).hexdigest(),before)
 def test_missing_invalid_rules_do_not_use_defaults(self):
  data=resources(self.env,str(self.client));self.assertEqual(data['refine']['state'],'unavailable')
  config=self.root/'server/work/dfo-lan/configs';config.mkdir(parents=True)
  (config/'refine.json').write_text('{"version":99}')
  data=resources(self.env,str(self.client));self.assertEqual(data['refine']['state'],'unavailable');self.assertNotIn('maxLevel',data['refine'])
 def test_preview_uses_only_native_read_methods_and_reports_decode_error(self):
  bridge=GMBridge(self.env,self.root/'manager')
  bridge.call=Mock(side_effect=[{'item':{'id':1,'name':'native text'}},{'png':'not-base64'}])
  result=bridge.preview({'id':1,'connectionId':'fixture'})
  self.assertEqual(result['imageState'],'unavailable');self.assertNotIn('png',result)
  self.assertEqual([c.args[0]['method'] for c in bridge.call.call_args_list],['item','item.icon'])
 def test_preview_validates_png_before_returning_data(self):
  png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aRz8AAAAASUVORK5CYII='
  bridge=GMBridge(self.env,self.root/'manager');bridge.call=Mock(side_effect=[{'item':{'id':1}},{'png':png}])
  result=bridge.preview({'id':1,'connectionId':'fixture'})
  self.assertEqual(result['imageState'],'decoded');self.assertEqual(result['png'],png)
  with self.assertRaises(ValueError):bridge.preview({'id':True,'connectionId':'fixture'})
