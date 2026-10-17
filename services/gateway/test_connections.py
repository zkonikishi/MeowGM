import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from connections import Connections

class ConnectionsTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','DPAPI requires Windows')
    def test_encrypted_restart_and_retained_secret(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{},clear=True):
            path=Path(directory)/'connections.json';settings=Connections(path)
            settings.save({'gmUrl':'http://127.0.0.1:5051','gmPassword':'private-gm-password','platformUrl':'https://platform.example','adminKey':'private-key-'+'k'*32})
            self.assertNotIn('private-',path.read_text())
            self.assertNotIn('adminKey',settings.public())
            settings=Connections(path);self.assertEqual(settings.read()['gmPassword'],'private-gm-password')
            settings.save({'gmPassword':''});self.assertTrue(settings.public()['gmPasswordSet'])
            settings.save({'clearSecrets':['gmPassword']});self.assertFalse(settings.public()['gmPasswordSet'])
    def test_invalid_endpoint_does_not_save(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{},clear=True):
            path=Path(directory)/'connections.json';settings=Connections(path)
            with self.assertRaises(ValueError):settings.save({'gmUrl':'http://external.example'})
            with self.assertRaises(ValueError):settings.save({'platformUrl':'http://platform.example'})
            self.assertFalse(path.exists())
