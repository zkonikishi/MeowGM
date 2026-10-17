import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tunnel import Tunnel

class TunnelTests(unittest.TestCase):
    def test_config_rejects_root_and_password_and_requires_real_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);key=root/'key';key.write_text('fixture')
            t=Tunnel(root/'tunnel.json')
            body=dict(host='example.test',user='gm_forward',keyFile=str(key),knownHosts=str(key),localPort=15051)
            for invalid in ({**body,'user':'root'},{**body,'password':'secret'},{**body,'host':'-oProxyCommand=x'},{**body,'keyFile':'missing'}):
                with self.assertRaises(ValueError):t.save(invalid)
            self.assertFalse(t.path.exists());t.save(body);self.assertTrue(t.status()['configured']);t.stop()
    def test_strict_key_only_child_is_stopped(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);key=root/'key';key.write_text('fixture')
            t=Tunnel(root/'tunnel.json');t.save(dict(host='example.test',user='gm_forward',keyFile=str(key),knownHosts=str(key),localPort=15051))
            captured=[]
            class Child:
                done=False
                def poll(self):return 0 if self.done else None
                def terminate(self):self.done=True
                def wait(self,timeout):return 0
            child=Child()
            def spawn(args,**kwargs):captured.append(args);t.stop_event.set();return child
            t.stop_event.clear()
            with patch('tunnel.subprocess.Popen',spawn):t._run(__import__('json').loads(t.path.read_text()))
            self.assertTrue(child.done);self.assertIsNone(t.port)
            for required in ('StrictHostKeyChecking=yes','BatchMode=yes','PasswordAuthentication=no','ExitOnForwardFailure=yes','IdentityAgent=none'):self.assertIn(required,captured[0])
            self.assertIn('127.0.0.1:15051:127.0.0.1:5051',captured[0])

if __name__=='__main__':unittest.main()
