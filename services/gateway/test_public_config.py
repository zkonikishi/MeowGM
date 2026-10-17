import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from public_config import FILENAME, install, validate, inspect_distribution

FIXTURE=Path(__file__).resolve().parents[2]/'packages/launcher-core/fixtures/public-config.json'
class PublicConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'待发布 客户端';self.root.mkdir()
        self.inspection=patch('public_config.inspect_distribution',return_value={'ready':True}).start()
        self.addCleanup(patch.stopall)
        self.config=json.loads(FIXTURE.read_text(encoding='utf-8'))
        (self.root/'OO Launcher.exe').write_bytes(b'fixture launcher')
        (self.root/self.config['clientDirectory']).mkdir()
        (self.root/self.config['clientDirectory']/'DNF.exe').write_bytes(b'fixture client')
    def body(self):return {'directory':str(self.root),'config':self.config}
    def test_fake_client_is_not_ready(self):
        patch.stopall()
        self.assertFalse(inspect_distribution(self.body())['ready'])
        with self.assertRaises(ValueError):install(self.body())
        self.assertFalse((self.root/FILENAME).exists())
    def test_install_backup_move(self):
        result=install(self.body());self.assertIsNone(result['backup'])
        original=(self.root/FILENAME).read_bytes()
        self.config['gamePort']=19001
        result=install(self.body());self.assertEqual(Path(result['backup']).read_bytes(),original)
        moved=self.root.with_name('已搬迁 文件夹');self.root.rename(moved)
        value=json.loads((moved/FILENAME).read_text(encoding='utf-8'))
        self.assertTrue((moved/value['clientDirectory']/'DNF.exe').is_file())
    def test_replace_failure_preserves_old_config_and_client(self):
        install(self.body());old=(self.root/FILENAME).read_bytes()
        with patch('public_config.os.replace',side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):install(self.body())
        self.assertEqual((self.root/FILENAME).read_bytes(),old)
        self.assertEqual((self.root/self.config['clientDirectory']/'DNF.exe').read_bytes(),b'fixture client')
        self.assertFalse(list(self.root.glob('.launcher-public-*.tmp')))
    def test_secrets_escape_unknown_protocol_and_missing_exe_rejected(self):
        for key,value in [('adminKey','secret'),('clientDirectory','../outside'),('gameHost','host?command'),('accountBaseUrl','http://localhost'),('accountProtocol','legacy')]:
            with self.subTest(key=key),self.assertRaises(ValueError):validate({**self.config,key:value})
        (self.root/'OO Launcher.exe').unlink()
        with self.assertRaises(ValueError):install(self.body())
        self.assertFalse((self.root/FILENAME).exists())

    def test_optional_account_links_and_new_sources_are_backward_compatible(self):
        value=dict(self.config);value.pop('registerUrl');value.pop('forgotUrl')
        self.assertEqual(validate(value),value)
        value.update(updateBaseUrl='https://cdn.example.com',clientManifestUrl='https://cdn.example.com/client/manifest.json',clientArtifactPrefix='https://cdn.example.com/client/releases/',clientEdition='sponsor')
        self.assertEqual(validate(value),value)
        for bad in [dict(value,updateBaseUrl='https://cdn.example.com/'),dict(value,clientArtifactPrefix='https://other.example.com/client/releases/'),dict(value,clientEdition=None),dict(value,clientArtifactPrefix='https://cdn.example.com/client/../releases/')]:
            with self.assertRaises(ValueError):validate(bad)
