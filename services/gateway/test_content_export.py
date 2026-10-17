import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from server import Store
from content_export import create_export

class ContentExportTests(unittest.TestCase):
    def test_complete_snapshot_receipt_and_no_public_write(self):
        base=Path(__file__).resolve().parents[2]/'packages/launcher-core/fixtures/content.json'
        original=base.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'gateway.sqlite3');draft=store.read();draft['announcements']=[{'title':'测试公告','body':'隔离测试正文'}];store.publish(draft)
            result=create_export(store,{'baseRaw':original.decode(),'reason':'隔离验证','plannedAt':'2026-10-14T00:00:00Z'})
            content=Path(result['contentPath']).read_bytes();data=json.loads(content);meta=json.loads(Path(result['handoffPath']).read_bytes())
            self.assertEqual(data['maintenance'],json.loads(original)['maintenance'])
            self.assertEqual(meta['baseSha256'],hashlib.sha256(original).hexdigest())
            self.assertEqual(meta['sha256'],hashlib.sha256(content).hexdigest())
            self.assertEqual(result['state'],'review_required')
            again=create_export(store,{'baseRaw':content.decode(),'reason':'重复草稿','plannedAt':'2026-10-14T00:00:00Z'})
            self.assertEqual(len(json.loads(Path(again['contentPath']).read_bytes())['items']),len(data['items']))
        self.assertEqual(base.read_bytes(),original)
