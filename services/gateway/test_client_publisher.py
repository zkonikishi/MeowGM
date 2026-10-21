import json,tempfile,unittest,zipfile
from pathlib import Path
from client_publisher import build,digest,safe_path

class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'client';self.root.mkdir()
        for name,data in {'DNF.exe':b'fixture never executed','az.dll':b'fixture plugin','ijl15.dll':b'fixture image plugin','GameGaurd.dll':b'fixture guard plugin','Script.pvf':b'v1 script','GameGaurd.ini':b'default plugins','AutoFire.ini':b'default key bindings','ImagePacks2/old.NPK':b'v1 images','SoundPacks/main.ogg':b'v1 sounds','data/account.json':b'private fixture','ScreenShots/private.png':b'private fixture','OOManager.exe':b'operator program'}.items():
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        self.exe_sha=digest(self.root/'DNF.exe')
    def run_build(self,**fields):
        return build({'directory':str(self.root),'version':'1.0.0',**fields},self.base/'output',exe_sha=self.exe_sha)
    def test_archive_wrapper_and_baseline_added_replaced_removed(self):
        first=self.run_build(buildArchive=True,archiveRoot='S4A21_CN');baseline=json.loads(Path(first['manifest']).read_text(encoding='utf-8'))
        self.assertFalse(first['published']);self.assertEqual(baseline['archiveRoot'],'S4A21_CN')
        with zipfile.ZipFile(first['archive']) as z:
            names=z.namelist();self.assertIn('S4A21_CN/DNF.exe',names);self.assertFalse(any('private' in n or 'OOManager' in n for n in names))
        (self.root/'Script.pvf').write_bytes(b'v2 script');(self.root/'ImagePacks2/old.NPK').unlink();(self.root/'ImagePacks2/new.NPK').write_bytes(b'v2 image');(self.root/'GameGaurd.ini').write_bytes(b'new defaults');(self.root/'AutoFire.ini').unlink()
        second=self.run_build(version='1.1.0',baseline=baseline,buildArchive=False,archiveRoot='');review=json.loads(Path(second['review']).read_text(encoding='utf-8'));manifest=json.loads(Path(second['manifest']).read_text(encoding='utf-8'))
        self.assertEqual(review['added'],['ImagePacks2/new.NPK']);self.assertEqual(review['replaced'],['Script.pvf']);self.assertEqual(review['removed'],['ImagePacks2/old.NPK']);self.assertIn('GameGaurd.ini',review['defaultSettingsUpdated']);self.assertIn('AutoFire.ini',review['playerSettingsPreserved']);self.assertNotIn('AutoFire.ini',manifest['removeFiles'])
        self.assertFalse(review['readyForProduction']);self.assertIsNone(second['archive'])
        old_dnf=next(f for f in baseline['files'] if f['path']=='DNF.exe');new_dnf=next(f for f in manifest['files'] if f['path']=='DNF.exe');self.assertEqual(old_dnf['url'],new_dnf['url'])
        self.assertFalse((Path(second['path'])/'assets/files'/f"{self.exe_sha}.bin").exists())
        self.assertEqual((self.root/'data/account.json').read_bytes(),b'private fixture')
    def test_rejects_other_baseline_wrong_executable_and_private_paths(self):
        first=self.run_build(buildArchive=False);baseline=json.loads(Path(first['manifest']).read_text(encoding='utf-8'));baseline['edition']='sponsor'
        with self.assertRaisesRegex(ValueError,'其他发行版'):self.run_build(baseline=baseline)
        with self.assertRaisesRegex(ValueError,'版本'):build({'directory':str(self.root),'version':'1.0.0'},self.base/'output')
        for path in ['../outside','a\\b','data/account.json','ScreenShots/private.png','OOManager.exe','CON.txt','name:stream']:
            with self.assertRaises(ValueError,msg=path):safe_path(path)
    def test_management_secrets_rejected_even_inside_resource_folders(self):
        for name in ['ImagePacks2/server-settings.json','SoundPacks/identity.json','ImagePacks2/.ssh/id_ed25519','SoundPacks/private.pem','ImagePacks2/game.sqlite3','SoundPacks/.env.production']:
            with self.subTest(path=name),self.assertRaises(ValueError):safe_path(name)

    def test_output_never_enters_client_or_accepts_unsafe_wrapper(self):
        with self.assertRaisesRegex(ValueError,'客户端内'):build({'directory':str(self.root),'version':'1.0.0','buildArchive':False},self.root/'output',exe_sha=self.exe_sha)
        with self.assertRaises(ValueError):self.run_build(archiveRoot='../bad')

if __name__=='__main__':unittest.main()
