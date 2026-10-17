"""MeowGM 0.7.0 local acceptance; all data and requests are isolated."""
import hashlib
from contextlib import closing
import json
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from server import Gateway, Store
from desktop_host import DesktopHandler

class Manager070Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.store=Store(self.root/'fixture.db')
        self.server=Gateway(('127.0.0.1',0),self.store)
        self.server.RequestHandlerClass=DesktopHandler
        self.server.setup_nonce='test-local-setup-nonce'
        self.base='http://'+self.server.authority
        self.cookie=''
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
    def request(self,path,body=None,authenticated=True,setup=False):
        headers={'Content-Type':'application/json','Origin':self.base}
        if authenticated:headers['Cookie']=self.cookie
        if setup:headers['X-OO-Setup']='test-local-setup-nonce'
        req=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:r=urllib.request.urlopen(req,timeout=10)
        except urllib.error.HTTPError as e:r=e
        with r:
            cookie=r.headers.get('Set-Cookie')
            if cookie:self.cookie=cookie.split(';')[0]
            return r.status,json.loads(r.read())
    def test_local_window_needs_no_admin_and_rejects_registration(self):
        self.server.local_mode=True;self.server.desktop_nonce='fixture-window'
        self.assertEqual(self.request('/api/desktop/setup')[1],{'required':False,'localMode':True})
        self.assertEqual(self.request('/api/desktop/setup',{},setup=True)[0],410)
        self.assertEqual(self.request('/api/admin/login',{})[0],410)
        self.assertEqual(self.request('/api/desktop/connect',{})[0],403)
        request=urllib.request.Request(self.base+'/api/desktop/connect',data=b'{}',headers={'Content-Type':'application/json','Origin':self.base,'X-OO-Window':'fixture-window'})
        with urllib.request.urlopen(request) as response:self.cookie=response.headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.request('/api/admin/config')[0],200)
        self.assertTrue(self.request('/api/admin/profile')[1]['localMode'])
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM admins').fetchone()[0],0)
    def test_native_gm_assets_and_private_routes(self):
        with urllib.request.urlopen(self.base+'/') as response:
            scripts=re.findall(r'<script src="(/[^"]+)"',response.read().decode())
        self.assertIn('/manager-character.js',scripts)
        for script in scripts:
            with urllib.request.urlopen(self.base+script) as response:
                self.assertEqual(response.status,200,script)
                self.assertIn('javascript',response.headers['Content-Type'])
        with urllib.request.urlopen(self.base+'/manager-gm.js') as response:
            self.assertEqual(response.status,200)
            self.assertIn('javascript',response.headers['Content-Type'])
            self.assertIn(b'/api/admin/gm/connect',response.read())
        self.assertEqual(self.request('/api/admin/gm/status',authenticated=False)[0],401)
        self.assertEqual(self.request('/api/admin/gm/connect',{},authenticated=False)[0],401)
        self.initialize()
        self.server.profile='115us'
        self.assertEqual(self.request('/api/admin/gm/status')[0],200)
        self.assertEqual(self.request('/api/admin/gm/call',{'method':'patch.liveStart'})[0],400)
    def test_target_preview_is_private_and_does_not_change_active_environment(self):
        endpoint='/api/admin/environment/target?productMode=custom&mode=cloud'
        self.assertEqual(self.request(endpoint,authenticated=False)[0],401)
        self.initialize();before=self.server.environment.read()
        status,data=self.request(endpoint)
        self.assertEqual(status,200);self.assertEqual(data['productMode'],'custom');self.assertEqual(data['mode'],'cloud')
        self.assertEqual(self.server.environment.read(),before)
        self.assertEqual(self.request('/api/admin/environment/target?productMode=sponsor&mode=cloud')[0],400)
    def test_fixture_management_is_private_and_cannot_control_external_targets(self):
        self.assertEqual(self.request('/api/admin/fixture-control/status',authenticated=False)[0],401)
        self.assertEqual(self.request('/api/admin/fixture-control/start',{},authenticated=False)[0],401)
        self.initialize()
        self.assertFalse(self.request('/api/admin/fixture-control/status')[1]['enabled'])
        self.assertEqual(self.request('/api/admin/fixture-control/start',{})[0],400)
        self.server.fixture_control.enabled=True
        self.assertEqual(self.request('/api/admin/fixture-control/start',{'command':'DFO.exe'})[0],400)
        code,state=self.request('/api/admin/fixture-control/start',{})
        self.assertEqual(code,200);self.assertTrue(state['healthy']);self.assertEqual(state['scope'],'synthetic-only')
        self.assertEqual(self.request('/api/admin/fixture-control/stop',{'pid':1})[0],400)
        self.assertFalse(self.request('/api/admin/fixture-control/stop',{})[1]['running'])
        rows=self.request('/api/admin/fixture-control/logs?after=0')[1]
        self.assertTrue(rows['items']);self.assertEqual(rows['scope'],'synthetic-only')
    def test_native_account_query_validates_decimal_string_before_store_access(self):
        self.initialize();self.server.profile='115us'
        with patch.object(self.server.read115,'characters',return_value={'characters':[]}) as read:
            for value in ('01','-1','1e3','1.0','9223372036854775808'):
                self.assertEqual(self.request('/api/admin/game/characters?accountId='+value)[0],503)
            read.assert_not_called()
            self.assertEqual(self.request('/api/admin/game/characters?accountId=9223372036854775807')[0],200)
            read.assert_called_once_with(9223372036854775807)
    def test_manual_server_configuration_is_saved_without_connecting(self):
        self.initialize()
        body={'host':'192.0.2.123','port':2222,'username':'fixture','password':'fixture-secret'}
        self.assertEqual(self.request('/api/admin/server-settings',body)[0],200)
        saved=self.request('/api/admin/server-settings')[1]
        self.assertEqual(saved['port'],2222);self.assertTrue(saved['passwordSet']);self.assertFalse(saved['connected'])
        self.assertNotIn('fixture-secret',json.dumps(saved))
        self.assertNotIn('fixture-secret',self.server.server_settings.path.read_text())
        self.assertEqual(self.request('/api/admin/server-settings',{'password':''})[0],200)
        self.assertTrue(self.request('/api/admin/server-settings')[1]['passwordSet'])
        self.assertEqual(self.request('/api/admin/server-settings',{'port':0})[0],400)
        self.assertEqual(self.request('/api/admin/server-settings',{'clearPassword':True})[0],200)
        self.assertFalse(self.request('/api/admin/server-settings')[1]['passwordSet'])
    def initialize(self):
        code,data=self.request('/api/desktop/setup',{'username':'owner_07','password':'fixture-password-123'},setup=True)
        self.assertEqual(code,200,data)
    def test_setup_validates_name_and_password_and_is_one_time(self):
        self.assertEqual(self.request('/api/desktop/setup',{'username':'x','password':'fixture-password-123'},setup=True)[0],400)
        self.assertEqual(self.request('/api/desktop/setup',{'username':'owner_07','password':'short'},setup=True)[0],400)
        self.assertEqual(self.request('/api/desktop/setup',{'username':'owner_07','password':'fixture-password-123'},setup=False)[0],403)
        self.initialize()
        self.assertEqual(self.request('/api/desktop/setup',{'username':'other','password':'fixture-password-123'},setup=True)[0],403)
        self.assertTrue(self.store.verify('fixture-password-123','owner_07'))
    def test_rename_keeps_data_and_requires_password_and_session(self):
        self.initialize()
        body={'username':'owner_new','password':'fixture-password-123'}
        self.assertEqual(self.request('/api/admin/profile',body,authenticated=False)[0],401)
        self.assertEqual(self.request('/api/admin/profile',{**body,'password':'wrong'})[0],400)
        self.assertEqual(self.request('/api/admin/profile',body)[0],200)
        self.assertEqual(self.request('/api/admin/profile')[1]['username'],'owner_new')
        self.assertTrue(self.store.verify('fixture-password-123','owner_new'))
        self.assertFalse(self.store.verify('fixture-password-123','owner_07'))
        self.assertEqual(self.store.audit()[0]['action'],'admin.rename')
        self.assertEqual(self.server.operations.actor,'owner_new')
    def test_optional_pvf_missing_never_breaks_core_and_does_not_write(self):
        self.initialize()
        source=self.root/'Script.pvf';source.write_bytes(b'local fixture, not a validated PVF')
        with patch('pvf_tools.provider',return_value=None):
            code,result=self.request('/api/admin/pvf/inspect',{'path':str(source)})
            self.assertEqual(code,200)
            self.assertFalse(result['headerValidated'])
            self.assertFalse(result['capabilities']['available'])
            self.assertEqual(result['sha256'],hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(self.request('/api/admin/pvf/key',{})[0],400)
            self.assertFalse((self.root/'pvf-keys').exists())
        self.assertEqual(self.request('/api/admin/config')[0],200)
    def test_removed_plugin_host_cannot_be_called(self):
        self.initialize()
        self.assertEqual(self.request('/api/admin/plugins')[0],410)
        self.assertEqual(self.request('/api/admin/plugins/install-local',{'path':'unused'})[0],410)
        self.assertFalse(hasattr(self.server,'plugins'))
    def test_config_persists_and_secret_does_not_echo(self):
        self.initialize()
        body={'gmUrl':'http://127.0.0.1:15051','gmPassword':'fixture-gm-password'}
        self.assertEqual(self.request('/api/admin/connections',body)[0],200)
        saved=self.request('/api/admin/connections')[1]
        self.assertTrue(saved['gmPasswordSet'])
        self.assertNotIn('fixture-gm-password',json.dumps(saved))
        self.assertEqual(saved['gmUrl'],body['gmUrl'])
        self.assertEqual(self.request('/api/admin/connections',{'gmUrl':'http://example.invalid'})[0],400)
        self.assertEqual(self.request('/api/admin/connections')[1]['gmUrl'],body['gmUrl'])


    def test_corrupt_connections_are_preserved_and_can_be_reset(self):
        self.initialize()
        path=self.root/'connections.json';path.write_text('{invalid fixture config')
        code,data=self.request('/api/admin/connections')
        self.assertEqual(code,200)
        self.assertIn('configurationError',data)
        self.assertEqual(self.request('/api/admin/connections/reset',{})[0],400)
        self.assertEqual(self.request('/api/admin/connections/reset',{'confirm':True})[0],200)
        backups=list(self.root.glob('connections.json.before-reset-*'))
        self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_text(),'{invalid fixture config')
    def test_115_profile_never_calls_old_server_or_deploys_old_gateway(self):
        self.initialize();self.server.profile='115us'
        for endpoint in ['/api/admin/deployment/start','/api/admin/account-status','/api/admin/tunnel/start']:
            self.assertEqual(self.request(endpoint,{})[0],409)
        result=self.request('/api/admin/connections/check',{})
        self.assertEqual(result[0],200)
        self.assertFalse(result[1]['gm']['ok'])
        self.assertEqual(self.request('/api/admin/game/accounts')[0],503)

class Read115Tests(unittest.TestCase):
    def setUp(self):
        import sqlite3
        from environment import Environment
        from read115 import Read115
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        storage=self.root/'package/server/work/dfo-lan/runtime/storage';storage.mkdir(parents=True)
        self.database=storage/'dfolan.sqlite3'
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("BEGIN")
            db.executescript("CREATE TABLE accounts(id INTEGER PRIMARY KEY,username TEXT);CREATE TABLE characters(id INTEGER PRIMARY KEY,account_id INTEGER,name TEXT,profession INTEGER,state BLOB,deleted_at INTEGER);INSERT INTO accounts VALUES(1,'fixture-player');INSERT INTO characters VALUES(2,1,'fixture-role',11,'{\"level\":115}',NULL);")
            db.commit()
        (storage/'local.json').write_text(json.dumps({'sqlite_path':str(self.database)}),encoding='utf-8')
        self.env=Environment(self.root/'environment.json')
        self.env.save({'profile':'115us','mode':'local','root':str(self.root/'package'),'version':'fixture-115'})
        self.reader=Read115(self.env)
    def test_read_accounts_and_roles_without_changing_database(self):
        before=hashlib.sha256(self.database.read_bytes()).hexdigest()
        self.assertEqual(self.reader.accounts()['accounts'][0]['name'],'fixture-player')
        role=self.reader.characters(1)['characters'][0]
        self.assertEqual(role['level'],115)
        self.assertEqual(role['characterId'],'2')
        self.assertEqual(role['accountId'],'1')
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(),before)
    def test_int64_identifiers_remain_sqlite_integers_but_wire_strings(self):
        import sqlite3
        values=[2**53-1,2**53,2**53+1,9223372036854775807]
        with closing(sqlite3.connect(self.database)) as db:
            for value in values:
                db.execute('INSERT INTO accounts VALUES(?,?)',(value,'native-'+str(value)))
                db.execute('INSERT INTO characters VALUES(?,?,?,?,?,NULL)',(value,value,'role-'+str(value),11,'{"level":1}'))
            db.commit()
            self.assertTrue(all(row[0]=='integer' for row in db.execute('SELECT typeof(id) FROM accounts')))
        before=hashlib.sha256(self.database.read_bytes()).hexdigest()
        ids={row['accountId'] for row in self.reader.accounts()['accounts']}
        for value in values:
            self.assertIn(str(value),ids)
            role=self.reader.characters(value)['characters'][0]
            self.assertEqual(role['accountId'],str(value));self.assertEqual(role['characterId'],str(value))
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(),before)
    def test_missing_database_never_created_and_wrong_profile_rejected(self):
        from read115 import Read115Error
        self.database.rename(self.database.with_suffix('.saved'))
        with self.assertRaises(Read115Error):self.reader.accounts()
        self.assertFalse(self.database.exists())
        with self.assertRaises(ValueError):self.env.save({'profile':'86s4a21','mode':'local','root':'','version':''})
    def test_outside_root_database_and_cloud_mode_rejected(self):
        import sqlite3
        from read115 import Read115Error
        other=self.root/'other.sqlite3'
        with closing(sqlite3.connect(other)) as db:db.execute('CREATE TABLE private(value TEXT)')
        config=self.database.parent/'local.json';config.write_text(json.dumps({'sqlite_path':str(other)}))
        with self.assertRaises(Read115Error):self.reader.accounts()
        self.env.save({'profile':'115us','mode':'cloud','root':'','version':'fixture'})
        with self.assertRaises(Read115Error):self.reader.accounts()

if __name__=='__main__':unittest.main()
