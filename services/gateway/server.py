"""OO Gateway local operations service. Python 3.11+, no third-party dependencies."""
from contextlib import contextmanager
import os
import sys
import re
from gm_adapter import GmAdapter, GmError
from operations import Operations, AdminTransport, OperationError
from connections import Connections, ServerSettings
from gm_bridge import GMBridge
from fixture_control import FixtureControl
from native_ids import native_id_from_request
from mod_manager import ModManager
from client_mods import ClientMods
from deployment_wizard import DeploymentWizard
from developer_control import DeveloperControl
from manager_ssh import ManagerSSH
from environment import Environment
from read115 import Read115, Read115Error
from tunnel import Tunnel
from deployment import Deployment
from content_export import create_export
from public_config import install as install_public_config, inspect_distribution
from client_publisher import PublicationError, build as build_client_publication
from pvf_tools import execute as execute_pvf, ProtectionError
from meowpay_simulation import Catalog, CatalogError, CatalogConflict
import argparse
import getpass
import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[2]
if getattr(sys, 'frozen', False): ROOT = Path(sys._MEIPASS)

class Store:
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.Lock()
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS admins(name TEXT PRIMARY KEY,salt BLOB,hash BLOB);
            CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER,body TEXT);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at INTEGER,actor TEXT,action TEXT,revision INTEGER);
            """)
            default = {"realm":"S4A21","maintenance":False,"maintenanceMessage":"","announcements":[]}
            db.execute("INSERT OR IGNORE INTO state VALUES(1,0,?)", (json.dumps(default),))
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path, timeout=10)
        try:
            with db: yield db
        finally: db.close()
    def initialize(self, password, username='admin'):
        if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,32}',username):raise ValueError('管理员账号需要3至32位字母、数字、下划线或短横线')
        if not isinstance(password,str) or not 12 <= len(password) <= 256: raise ValueError("管理员密码需要12至256位")
        salt=secrets.token_bytes(16)
        digest=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM admins LIMIT 1').fetchone():raise sqlite3.IntegrityError('管理员已存在')
            db.execute("INSERT INTO admins VALUES(?,?,?)",(username,salt,digest))
    def admin_name(self):
        with self.connect() as db:row=db.execute('SELECT name FROM admins LIMIT 1').fetchone()
        return row[0] if row else 'admin'
    def rename_admin(self, username, password):
        if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,32}',username):
            raise ValueError('管理员账号需要3至32位字母、数字、下划线或短横线')
        if not isinstance(password,str) or not 1 <= len(password) <= 256:
            raise ValueError('请输入当前管理员密码')
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT name,salt,hash FROM admins LIMIT 1').fetchone()
            if not row or not hmac.compare_digest(row[2],hashlib.scrypt(password.encode(),salt=row[1],n=16384,r=8,p=1)):
                raise ValueError('当前管理员密码错误')
            db.execute('UPDATE admins SET name=? WHERE name=?',(username,row[0]))
            revision=db.execute('SELECT revision FROM state WHERE id=1').fetchone()[0]
            db.execute('INSERT INTO audit(at,actor,action,revision) VALUES(?,?,?,?)',(int(time.time()),username,'admin.rename',revision))
        return {'username':username}
    def verify(self,password,username='admin'):
        if not isinstance(username,str):return False
        with self.connect() as db: row=db.execute("SELECT salt,hash FROM admins WHERE name=?",(username,)).fetchone()
        return bool(row and hmac.compare_digest(row[1],hashlib.scrypt(password.encode(),salt=row[0],n=16384,r=8,p=1)))
    def read(self):
        with self.connect() as db: rev,body=db.execute("SELECT revision,body FROM state WHERE id=1").fetchone()
        return {"revision":rev,**json.loads(body)}
    def publish(self, body):
        if set(body)!={"revision","realm","maintenance","maintenanceMessage","announcements"}: raise ValueError("配置字段不正确")
        if type(body['revision']) is not int or body['realm']!='S4A21' or type(body['maintenance']) is not bool: raise ValueError("区服配置不正确")
        if not isinstance(body['maintenanceMessage'],str) or len(body['maintenanceMessage'])>200: raise ValueError("维护说明最多 200 字")
        items=body['announcements']
        if not isinstance(items,list) or len(items)>20: raise ValueError("最多发布 20 条公告")
        for item in items:
            if not isinstance(item,dict) or set(item)!={'title','body'}: raise ValueError("公告字段不正确")
            if not isinstance(item['title'],str) or not 1<=len(item['title'].strip())<=80: raise ValueError("标题为 1 至 80 字")
            if not isinstance(item['body'],str) or len(item['body'])>4000: raise ValueError("正文最多 4000 字")
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT revision FROM state WHERE id=1').fetchone()[0]
            if old!=body['revision']: raise RuntimeError("配置已被修改，请重新加载后编辑")
            state={k:v for k,v in body.items() if k!='revision'}
            db.execute('UPDATE state SET revision=?,body=? WHERE id=1',(old+1,json.dumps(state,ensure_ascii=False)))
            actor=db.execute('SELECT name FROM admins LIMIT 1').fetchone()
            db.execute('INSERT INTO audit(at,actor,action,revision) VALUES(?,?,?,?)',(int(time.time()),actor[0] if actor else 'admin','publish',old+1))
        return self.read()
    def audit(self):
        with self.connect() as db:
            return [dict(zip(('id','at','actor','action','revision'),r)) for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')]

class Gateway(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,store):
        super().__init__(address,Handler)
        self.store=store
        self.profile=os.environ.get('MEOW_MANAGER_PROFILE','s4a21')
        self.server_settings=ServerSettings(Path(store.path).parent/'server-settings.json')
        self.manager_ssh=ManagerSSH(self.server_settings)
        self.environment=Environment(Path(store.path).parent/'environment.json')
        self.gm_bridge=GMBridge(self.environment,Path(store.path).parent)
        self.fixture_control=FixtureControl(Path(store.path).parent,enabled=os.environ.get('MEOW_GM_SYNTHETIC_CONTROL')=='1')
        self.read115=Read115(self.environment)
        self.mod_manager=ModManager(self.environment)
        self.client_mods=ClientMods(self.environment,self.gm_bridge)
        self.deployment_wizard=DeploymentWizard(trust_store=Path(store.path).parent/'gm-deployment-trust.json')
        self.connections=Connections(Path(store.path).parent/'connections.json')
        self.tunnel=Tunnel(Path(store.path).parent/'tunnel.json')
        self.deployment=Deployment(Path(store.path).parent/'deployment-jobs')
        self.connection_error=''
        try:self.gm,transport=self.connections.adapters(self.connections.read())
        except (ValueError,OSError,KeyError):
            self.gm,transport=None,None
            self.connection_error='连接配置不可读取，可能来自其他 Windows 用户。原文件保留，请在连接页备份并重置。'
        self.operations=Operations(store.path,transport,actor=store.admin_name())
        self.sessions={}
        self.mock_catalog=Catalog(Path(store.path).parent)
        self.auth_lock=threading.Lock()
        self.attempts=[]
    def server_close(self):
        self.fixture_control.close()
        self.gm_bridge.close()
        self.manager_ssh.close()
        self.tunnel.stop()
        super().server_close()
    @property
    def authority(self): return f'127.0.0.1:{self.server_port}'

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)
    def log_message(self,*args): pass # Never log request bodies, cookies or passwords.
    def reply(self,status,body,kind='application/json; charset=utf-8',cookie=None):
        raw=json.dumps(body,ensure_ascii=False).encode() if kind.startswith('application/json') else body
        self.send_response(status)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(raw)
    def session(self):
        cookies=dict(part.strip().split('=',1) for part in self.headers.get('Cookie','').split(';') if '=' in part)
        key=cookies.get('oo_session','')
        with self.server.auth_lock:
            self.server.sessions={k:v for k,v in self.server.sessions.items() if v>time.time()}
            return key if key in self.server.sessions else None
    def valid_host(self):
        if self.headers.get('Host')!=self.server.authority:
            self.reply(403,{'error':'访问地址无效，请使用 127.0.0.1'});return False
        return True
    def do_GET(self):
        if not self.valid_host(): return
        path=urlsplit(self.path).path
        if path=='/api/public/config': return self.reply(200,self.server.store.read())
        if path=='/api/health': return self.reply(200,{'ok':True,'profile':self.server.profile,'gameIntegration':False})
        if path=='/api/admin/gm/status':
            if not self.session():return self.reply(401,{'error':'请先打开本机管理窗口'})
            if self.server.profile!='115us':return self.reply(409,{'error':'GM 管道仅适用于 115US'})
            try:return self.reply(200,self.server.gm_bridge.status())
            except (ValueError,OSError):return self.reply(503,{'error':'GM 配置不可读取，原文件已保留'})
        if path.startswith('/api/admin/fixture-control/'):
            if not self.session():return self.reply(401,{'error':'请先打开本机管理窗口'})
            if path=='/api/admin/fixture-control/status':return self.reply(200,self.server.fixture_control.status())
            if path=='/api/admin/fixture-control/logs':
                try:return self.reply(200,self.server.fixture_control.logs(int(parse_qs(urlsplit(self.path).query).get('after',['0'])[0])))
                except ValueError:return self.reply(400,{'error':'日志游标无效'})
            return self.reply(404,{'error':'合成演练接口不存在'})
        if path=='/api/admin/developer-control/capabilities':
            if self.server.profile!='115us':return self.reply(409,{'error':'开发者控制仅适用于 115US'})
            if not self.session():return self.reply(401,{'error':'请先打开本机管理窗口'})
            return self.reply(200,DeveloperControl.capabilities())
        if path=='/api/admin/client-mods':
            if self.server.profile!='115us':return self.reply(409,{'error':'客户端 MOD 管理仅适用于 115US'})
            if not self.session():return self.reply(401,{'error':'请先打开本机管理窗口'})
            try:return self.reply(200,self.server.client_mods.list())
            except (ValueError,OSError) as e:return self.reply(400,{'error':str(e)})
        if path=='/api/admin/mod-manager':
            if self.server.profile!='115us':return self.reply(409,{'error':'MOD 管理仅适用于 115US'})
            if not self.session():return self.reply(401,{'error':'请先打开本机管理窗口'})
            try:return self.reply(200,self.server.mod_manager.list())
            except (ValueError,OSError) as e:return self.reply(400,{'error':str(e)})
        if path=='/api/admin/server-settings':
            if not self.session():return self.reply(401,{'error':'请先打开本机管理窗口'})
            try:return self.reply(200,self.server.server_settings.public())
            except (ValueError,OSError):return self.reply(503,{'error':'服务器配置不可读取，原文件已保留'})
        if path=='/api/admin/environment/target':
            if not self.session():return self.reply(401,{'error':'请先打开本机管理窗口'})
            query=parse_qs(urlsplit(self.path).query)
            try:return self.reply(200,self.server.environment.target(query.get('productMode',[''])[0],query.get('mode',[''])[0]))
            except (ValueError,OSError) as e:return self.reply(400,{'error':str(e)})
        if path=='/api/admin/environment':
            if not self.session():return self.reply(401,{'error':'请先登录管理台'})
            try:return self.reply(200,self.server.environment.inspect())
            except (ValueError,OSError):return self.reply(503,{'error':'环境配置不可读取，请核对本机 environment.json；没有修改配置。'})
        if path=='/api/admin/profile':
            if not self.session():return self.reply(401,{'error':'请先登录管理台'})
            local=getattr(self.server,'local_mode',False)
            return self.reply(200,{'username':'本机管理' if local else self.server.store.admin_name(),'localMode':local,'edition':'unified','version':os.environ.get('MEOW_MANAGER_VERSION','development')})
        if path.startswith('/api/admin/plugins'):
            if not self.session():return self.reply(401,{'error':'请先登录管理台'})
            return self.reply(410,{'error':'旧插件宿主已移除；115US MOD 由上游 modkit 管理，当前尚未接通。'})
        if path=='/api/admin/meowpay/catalog':
            if not self.session():return self.reply(401,{'error':'请先登录管理台'})
            if os.environ.get('MEOW_MANAGER_TEST_MODE')!='1':return self.reply(409,{'error':'生产支付未接通；模拟配置仅用于隔离测试'})
            try:return self.reply(200,self.server.mock_catalog.read())
            except (CatalogError,OSError,sqlite3.Error):return self.reply(503,{'error':'MeowPay 模拟配置暂不可用；生产支付未接通'})
        if path in ('/api/admin/config','/api/admin/audit'):
            if not self.session(): return self.reply(401,{'error':'请先登录管理台'})
            return self.reply(200,self.server.store.read() if path.endswith('config') else self.server.store.audit())
        if path=='/api/admin/connections':
            if not self.session():return self.reply(401,{'error':'请先登录管理台'})
            try:return self.reply(200,self.server.connections.public())
            except (ValueError,OSError,KeyError):return self.reply(200,{'gmUrl':'','platformUrl':'','caFile':'','gmPasswordSet':False,'adminKeySet':False,'configurationError':self.server.connection_error or '连接配置不可读取，请备份并重置。'})
        if path in ('/api/admin/game/accounts','/api/admin/game/characters'):
            if not self.session():return self.reply(401,{'error':'请先登录管理台'})
            if self.server.profile=='115us':
                try:
                    result=self.server.read115.accounts() if path.endswith('/accounts') else self.server.read115.characters(native_id_from_request(parse_qs(urlsplit(self.path).query).get('accountId',['0'])[0]))
                    return self.reply(200,result)
                except (ValueError,OSError,sqlite3.Error):return self.reply(503,{'error':'115US 本地存档尚不可读取，请核对环境目录、local.json 与存档结构；没有连接旧服或修改数据库。'})
            if not self.server.gm:return self.reply(503,{'error':'尚未配置 A21 GM 连接'})
            try:
                if path.endswith('/accounts'):result=self.server.gm.accounts()
                else:result=self.server.gm.characters(int(parse_qs(urlsplit(self.path).query).get('accountId',['0'])[0]))
                return self.reply(200,result)
            except (ValueError,GmError) as e:return self.reply(503,{'error':str(e) if isinstance(e,GmError) else '游戏账号 ID 无效'})
        if path=='/api/admin/operations':
            if not self.session():return self.reply(401,{'error':'请先登录管理台'})
            return self.reply(200,{'enabled':self.server.profile!='115us' and self.server.operations.transport is not None,'items':self.server.operations.list()})
        files={'/manager-mods.js':'manager-mods.js','/gm-view.html':'gm-view.html','/gm-adapter.js':'gm-adapter.js','/gm-adapter.css':'gm-adapter.css','/upstream-app.css':'upstream-app.css','/upstream-gm.css':'upstream-gm.css','/upstream-gm-difficulty.css':'upstream-gm-difficulty.css','/environment.js':'environment.js','/plugins.js':'plugins.js','/meowpay.js':'meowpay.js','/pvf.js':'pvf.js','/minimize.png':'minimize.png','/close.png':'close.png','/launcher-config.js':'launcher-config.js','/shell.js':'shell.js','/manager-background.png':'manager-background.png','/arad-wordmark.png':'arad-wordmark.png','/':'index.html','/app.js':'app.js','/style.css':'style.css','/desktop.js':'desktop.js','/connections.js':'connections.js','/content-export.js':'content-export.js'}
        files['/manager-gm.js']='manager-gm.js'
        files['/manager-character.js']='manager-character.js'
        files['/manager-resources.js']='manager-resources.js'
        files['/manager-console.js']='manager-console.js'
        files['/native-ids.js']='native-ids.js'
        if path in files:
            file=ROOT/'apps'/'admin'/files[path]
            kind={'.png':'image/png','.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}[file.suffix]
            return self.reply(200,file.read_bytes(),kind)
        self.reply(404,{'error':'页面不存在'})
    def do_POST(self):
        if not self.valid_host(): return
        if self.headers.get('Origin')!=f'http://{self.server.authority}': return self.reply(403,{'error':'请求来源无效'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            maximum=16777216 if self.path=='/api/admin/client/publish' else (1048576 if self.path=='/api/admin/content/export' else 262144)
            if not 0<length<=maximum: return self.reply(413,{'error':'请求大小不正确'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json': return self.reply(415,{'error':'需要 JSON'})
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict): raise ValueError('需要 JSON 对象')
            path=urlsplit(self.path).path
            if path=='/api/admin/login':
                with self.server.auth_lock:
                    self.server.attempts=[t for t in self.server.attempts if t>time.time()-60]
                    if len(self.server.attempts)>=10: return self.reply(429,{'error':'登录过于频繁，请一分钟后重试'})
                    self.server.attempts.append(time.time())
                password=body.get('password')
                if not isinstance(password,str) or len(password)>256: raise ValueError('密码格式不正确')
                if not self.server.store.verify(password,body.get('username','admin')): return self.reply(401,{'error':'账号或密码错误'})
                key=secrets.token_urlsafe(32)
                with self.server.auth_lock: self.server.sessions[key]=time.time()+1800
                return self.reply(200,{'ok':True},cookie=f'oo_session={key}; HttpOnly; SameSite=Strict; Path=/; Max-Age=1800')
            key=self.session()
            if not key: return self.reply(401,{'error':'请先登录管理台'})
            if path.startswith('/api/admin/fixture-control/'):
                if path=='/api/admin/fixture-control/start':return self.reply(200,self.server.fixture_control.start(body))
                if path=='/api/admin/fixture-control/stop':return self.reply(200,self.server.fixture_control.stop(body))
                raise ValueError('合成演练接口不存在')
            if path.startswith('/api/admin/gm/'):
                if self.server.profile!='115us':return self.reply(409,{'error':'GM 管道仅适用于 115US'})
                bridge=self.server.gm_bridge
                if path=='/api/admin/gm/settings':return self.reply(200,bridge.save(body))
                if path=='/api/admin/gm/connect':return self.reply(200,bridge.connect(body))
                if path=='/api/admin/gm/disconnect':
                    bridge.close()
                    return self.reply(200,bridge.status())
                if path=='/api/admin/gm/call':return self.reply(200,bridge.call(body))
                if path=='/api/admin/gm/preview':return self.reply(200,bridge.preview(body))
                raise ValueError('GM 请求路径无效')
            if path=='/api/admin/developer-control/request':
                if self.server.profile!='115us':return self.reply(409,{'error':'开发者控制仅适用于 115US'})
                try:result=DeveloperControl.request(body)
                except ValueError:return self.reply(400,{'ok':False,'code':'invalid_request','enabled':False})
                return self.reply(503,result)
            if path=='/api/admin/deployment-wizard/inspect':
                if self.server.profile!='115us':return self.reply(409,{'error':'部署预检仅适用于 115US'})
                return self.reply(200,self.server.deployment_wizard.inspect(body))
            if path=='/api/admin/client-mods/set':
                if self.server.profile!='115us':return self.reply(409,{'error':'客户端 MOD 管理仅适用于 115US'})
                return self.reply(200,self.server.client_mods.set_enabled(body))
            if path=='/api/admin/mod-manager/set':
                if self.server.profile!='115us':return self.reply(409,{'error':'MOD 管理仅适用于 115US'})
                return self.reply(200,self.server.mod_manager.set_enabled(body))
            if path=='/api/admin/server-settings':
                result=self.server.server_settings.save(body)
                self.server.manager_ssh.close()
                return self.reply(200,result)
            if path=='/api/admin/server-ssh/connect':
                if body!={}:raise ValueError('连接参数无效，请先保存配置')
                return self.reply(200,self.server.manager_ssh.connect())
            if path=='/api/admin/server-ssh/status':return self.reply(200,self.server.manager_ssh.status())
            if path=='/api/admin/server-ssh/disconnect':
                self.server.manager_ssh.close()
                return self.reply(200,self.server.manager_ssh.status())
            if path=='/api/admin/environment':
                with self.server.gm_bridge.lock:
                    if self.server.gm_bridge.rpc_lock.locked():return self.reply(409,{'error':'GM 操作进行中，请完成后再修改管理环境'})
                    result=self.server.environment.save(body)
                    self.server.gm_bridge.close()
                    self.server.manager_ssh.close()
                    return self.reply(200,result)
            if self.server.profile=='115us' and path in ('/api/admin/deployment/start','/api/admin/account-status','/api/admin/retry-operation','/api/admin/tunnel/start','/api/admin/publish'):
                return self.reply(409,{'error':'115US 对应控制协议尚未接通；86S4A21 已冻结，不执行旧服操作。'})
            if self.server.profile=='115us' and path=='/api/admin/connections/check':
                return self.reply(200,{'gm':{'ok':False,'message':'115US 管理协议尚未接通；没有探测旧服'},'platform':{'ok':False,'message':'身份服务桥接尚未接入；没有发起网络请求'}})
            if path=='/api/admin/profile':
                if set(body)!={'username','password'}:raise ValueError('改名参数不正确')
                with self.server.auth_lock:
                    result=self.server.store.rename_admin(body['username'],body['password'])
                    self.server.operations.actor=result['username']
                    self.server.sessions={key:time.time()+1800}
                return self.reply(200,result)
            if path.startswith('/api/admin/plugins/'):
                return self.reply(410,{'error':'旧插件宿主已移除；当前没有插件安装入口。'})
            if path=='/api/admin/meowpay/catalog':
                if os.environ.get('MEOW_MANAGER_TEST_MODE')!='1':return self.reply(409,{'error':'生产支付未接通；模拟配置仅用于隔离测试'})
                try:return self.reply(200,self.server.mock_catalog.write(body,self.server.store.admin_name()))
                except CatalogConflict as e:return self.reply(409,{'error':str(e)})
                except CatalogError as e:return self.reply(400,{'error':str(e)})
                except (OSError,sqlite3.Error):return self.reply(503,{'error':'模拟配置保存失败，请重新读取确认状态'})
            if path.startswith('/api/admin/pvf/'):
                try:return self.reply(200,execute_pvf(path.rsplit('/',1)[-1],body,Path(self.server.store.path).parent))
                except ProtectionError as e:return self.reply(400,{'error':str(e)})
                except ImportError:return self.reply(503,{'error':'加密分发依赖不可用；不会启用游戏加密'})
                except OSError:return self.reply(400,{'error':'PVF 副本处理失败，请检查文件权限、占用和磁盘空间'})
            if path=='/api/admin/client/publish':
                try:return self.reply(200,build_client_publication(body,Path(self.server.store.path).parent/'client-publications'))
                except PublicationError as e:return self.reply(400,{'error':str(e)})
                except OSError:return self.reply(400,{'error':'客户端资源生成失败，请检查文件占用、权限与磁盘空间；未发布到线上'})
            if path=='/api/admin/launcher/inspect':
                try:return self.reply(200,inspect_distribution(body))
                except OSError:return self.reply(400,{'error':'无法检查目录，请确认文件存在且可读取'})
            if path=='/api/admin/launcher/install':
                try:return self.reply(200,install_public_config(body))
                except OSError:return self.reply(400,{'error':'无法写入目标目录，原配置未主动删除；请检查路径和权限'})
            if path=='/api/admin/content/export':return self.reply(200,create_export(self.server.store,body))
            if path=='/api/admin/connections':
                with self.server.operations.lock:
                    if self.server.operations.active:return self.reply(409,{'error':'操作正在进行，完成后再修改连接'})
                    self.server.gm,self.server.operations.transport=self.server.connections.save(body)
                return self.reply(200,self.server.connections.public())
            if path=='/api/admin/connections/reset':
                if body!={'confirm':True}:raise ValueError('请确认备份并重置连接配置')
                with self.server.operations.lock:
                    if self.server.operations.active:return self.reply(409,{'error':'请等待当前操作结束'})
                    self.server.connections.reset()
                    self.server.gm=None;self.server.operations.transport=None;self.server.connection_error=''
                return self.reply(200,self.server.connections.public())
            if path=='/api/admin/connections/check':return self.reply(200,self.server.connections.check())
            if path=='/api/admin/tunnel/save':return self.reply(200,self.server.tunnel.save(body))
            if path=='/api/admin/tunnel/start':return self.reply(200,self.server.tunnel.start())
            if path=='/api/admin/tunnel/stop':
                self.server.tunnel.stop()
                return self.reply(200,self.server.tunnel.status())
            if path=='/api/admin/tunnel/status':return self.reply(200,self.server.tunnel.status())
            if path=='/api/admin/deployment/status':return self.reply(200,self.server.deployment.status())
            if path=='/api/admin/deployment/start':return self.reply(202,self.server.deployment.start(body))
            if path=='/api/admin/logout':
                with self.server.auth_lock: self.server.sessions.pop(key,None)
                return self.reply(200,{'ok':True},cookie='oo_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if path=='/api/admin/account-status':return self.reply(200,self.server.operations.create(body))
            if path=='/api/admin/retry-operation':return self.reply(200,self.server.operations.execute(body.get('id','')))
            if path=='/api/admin/publish': return self.reply(200,self.server.store.publish(body))
            self.reply(404,{'error':'接口不存在'})
        except OperationError as e:self.reply(400,{'error':str(e)})
        except (ValueError,UnicodeError) as e: self.reply(400,{'error':str(e) or '输入内容不正确，请检查字段和长度'})
        except RuntimeError as e: self.reply(409,{'error':str(e)})
        except sqlite3.Error: self.reply(503,{'error':'保存失败，请稍后重新加载确认状态'})

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path(__file__).parent/'data')
    parser.add_argument('--port',type=int,default=17860)
    parser.add_argument('--init-admin',action='store_true')
    args=parser.parse_args()
    args.data.mkdir(parents=True,exist_ok=True)
    store=Store(args.data/'gateway.sqlite3')
    if args.init_admin:
        pw=getpass.getpass('设置管理员密码（至少12位）: ')
        if pw!=getpass.getpass('再次输入: '): raise SystemExit('两次密码不一致')
        try: store.initialize(pw)
        except sqlite3.IntegrityError: raise SystemExit('管理员已存在，未覆盖')
        print('管理员已创建。')
    else:
        server=Gateway(('127.0.0.1',args.port),store)
        print(f'OO 管理台: http://{server.authority} （本地管理；游戏接口尚未接入）',flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.server_close()
