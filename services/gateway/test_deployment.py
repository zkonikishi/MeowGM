import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from deployment import Deployment

spec=importlib.util.spec_from_file_location('managed_remote',Path(__file__).parent/'deploy/managed_remote.py')
remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)

class DeploymentTests(unittest.TestCase):
    def test_validates_before_start_and_does_not_store_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);key=root/'key';key.write_text('fixture')
            d=Deployment(root/'jobs');body={'action':'deploy','host':'example.test','user':'operator','port':22,'keyFile':str(key),'knownHosts':str(key),'platformUrl':'https://example.test','gatewayKey':'a'*40,'gameKey':'b'*40}
            for invalid in ({**body,'user':'root'},{**body,'gameKey':'short'},{**body,'host':'-oProxyCommand=x'}):
                with self.assertRaises(ValueError):d.start(invalid)
            with patch('deployment.threading.Thread'):
                d.start(body)
            raw=''.join(p.read_text() for p in (root/'jobs').glob('*.json'))
            self.assertNotIn('a'*40,raw);self.assertNotIn('b'*40,raw)

    def test_remote_deploy_uninstall_preserves_data_and_rejects_changed_unit(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);state={'active':False,'enabled':False}
            def system(*args,check=True):
                if args[0]=='enable':state.update(active=True,enabled=True)
                if args[0]=='start':state['active']=True
                if args[0] in ('stop','disable'):state['active']=False
                if args[0]=='disable':state['enabled']=False
                rc=0
                if args[0]=='is-active':rc=0 if state['active'] else 3
                if args[0]=='is-enabled':rc=0 if state['enabled'] else 1
                return types.SimpleNamespace(returncode=rc,stdout='321')
            class Opener:
                def open(self,request,timeout):
                    data={'ok':True,'protocol':'platform-v1'} if isinstance(request,str) else {'ok':True,'service':'oo-admission','pid':321}
                    return io.BytesIO(json.dumps(data).encode())
            code=b'print("fixture")\n';payload={'action':'deploy','id':'1'*32,'code':base64.b64encode(code).decode(),'sha256':hashlib.sha256(code).hexdigest(),'environment':{'OO_PLATFORM_URL':'https://example.test','OO_PLATFORM_GATEWAY_KEY':'a'*40,'OO_GAME_KEY':'b'*40}}
            flock=types.SimpleNamespace(flock=lambda *args:None,LOCK_EX=1,LOCK_NB=2)
            with patch.dict('sys.modules',{'fcntl':flock}),patch.object(remote.os,'geteuid',return_value=1000,create=True),patch.object(remote.os,'getuid',return_value=1000,create=True),patch.object(remote.Path,'home',return_value=home),patch.object(remote,'system',side_effect=system),patch.object(remote.subprocess,'run',return_value=types.SimpleNamespace(stdout='yes')),patch.object(remote.urllib.request,'build_opener',return_value=Opener()):
                result=remote.execute(payload);self.assertEqual(result['state'],'deployed')
                base=home/'.local/share/oo-admission-managed';(base/'data/account.db').write_text('retained')
                oldcurrent=(base/'current').resolve();oldenvironment=(base/'environment').read_text()
                class BadHealth:
                    def open(self,request,timeout):
                        return io.BytesIO(json.dumps({'ok':True,'protocol':'platform-v1'}).encode())
                changed=b'print("changed")\n'
                nextpayload={**payload,'id':'4'*32,'code':base64.b64encode(changed).decode(),'sha256':hashlib.sha256(changed).hexdigest()}
                with patch.object(remote.urllib.request,'build_opener',return_value=BadHealth()),patch.object(remote.time,'sleep'):
                    failed=remote.execute(nextpayload)
                self.assertEqual(failed['state'],'failed_rolled_back');self.assertEqual((base/'current').resolve(),oldcurrent);self.assertEqual((base/'environment').read_text(),oldenvironment);self.assertTrue(state['active'])
                unit=home/'.config/systemd/user'/remote.UNIT;original=unit.read_text();unit.write_text(original+'# edit')
                with self.assertRaises(ValueError):remote.execute({'action':'uninstall','id':'2'*32})
                self.assertTrue(state['active']);unit.write_text(original)
                result=remote.execute({'action':'uninstall','id':'3'*32});self.assertEqual(result['state'],'uninstalled')
                self.assertEqual((base/'data/account.db').read_text(),'retained');self.assertTrue((base/'environment').exists());self.assertFalse(unit.exists());self.assertFalse((base/'current').exists())
                self.assertEqual(remote.execute({'action':'status','id':'3'*32})['state'],'uninstalled')

if __name__=='__main__':unittest.main()
