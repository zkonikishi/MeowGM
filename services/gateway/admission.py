"""Loopback-only S4A21 admission adapter. Secrets belong to server environment."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import ssl
import threading
import time
import uuid
import urllib.request
import urllib.error
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

class Fault(Exception):
    def __init__(self,code,status=409):self.code,self.status=code,status

class PlatformConsumer:
    def __init__(self,url,key,cafile=None):
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('HTTPS platform URL required')
        if len(key)<32:raise ValueError('platform service key required')
        self.url=url.rstrip('/')+'/internal/v1/game-tickets/consume'
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=cafile)))
        self.key=key
    def __call__(self,ticket,request_id):
        data=json.dumps({'ticket':ticket,'realm_id':'hk','audience':'game-hk','request_id':request_id}).encode()
        req=urllib.request.Request(self.url,data=data,headers={'Content-Type':'application/json','X-Arad-Service-Key':self.key})
        try:
            with self.opener.open(req,timeout=8) as response:
                raw=response.read(16385)
                if len(raw)>16384:raise Fault('invalid_platform_response',503)
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            if e.code in (400,401,403,409):raise Fault('ticket_rejected',401) from None
            raise Fault('platform_unavailable',503) from None
        except (OSError,ValueError,urllib.error.URLError):raise Fault('platform_unavailable',503) from None

class AdmissionStore:
    def __init__(self,path,consume):
        self.path=str(path);self.consume=consume;self.boot=secrets.token_hex(16)
        self.lock=threading.Lock();self.inflight=set()
        with self.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS admissions(
                connection_id TEXT PRIMARY KEY,boot TEXT NOT NULL,ticket_hash TEXT UNIQUE NOT NULL,
                request_id TEXT UNIQUE NOT NULL,uid TEXT NOT NULL,created INTEGER NOT NULL,
                state TEXT NOT NULL,response TEXT)
            """)
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    @staticmethod
    def connection(value):
        if not isinstance(value,str):raise Fault('invalid_connection',400)
        try: parsed=uuid.UUID(value)
        except ValueError:raise Fault('invalid_connection',400) from None
        if str(parsed)!=value:raise Fault('invalid_connection',400)
        return value
    def prepare(self,connection_id,uid,ticket):
        cid=self.connection(connection_id)
        if not isinstance(uid,str) or len(uid)!=8 or not uid.isascii() or not uid.isdigit() or uid=='00000000':raise Fault('invalid_uid',400)
        if not isinstance(ticket,str) or not 32<=len(ticket)<=2048 or not all(c.isascii() and (c.isalnum() or c in '-_') for c in ticket):raise Fault('invalid_ticket',400)
        digest=hashlib.sha256(ticket.encode()).hexdigest()
        with self.lock,self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM admissions WHERE connection_id=?',(cid,)).fetchone()
            if row:
                if row['boot']!=self.boot:raise Fault('connection_lost')
                if row['ticket_hash']!=digest or row['uid']!=uid:raise Fault('connection_mismatch')
                if row['created']+60<=time.time():raise Fault('ticket_expired',401)
                if row['state']=='ready':return json.loads(row['response'])
                if row['state']!='pending':raise Fault('admission_used')
                rid=row['request_id']
            else:
                rid=str(uuid.uuid4())
                try:db.execute('INSERT INTO admissions VALUES(?,?,?,?,?,?,?,NULL)',(cid,self.boot,digest,rid,uid,int(time.time()),'pending'))
                except sqlite3.IntegrityError:raise Fault('ticket_replayed',401) from None
            if cid in self.inflight:raise Fault('admission_pending')
            self.inflight.add(cid)
        try:
            result=self.consume(ticket,rid)
            if not isinstance(result,dict) or result.get('ok') is not True or result.get('uid')!=uid or result.get('realm_id')!='hk' or result.get('game_login_name')!=uid or type(result.get('game_account_id')) is not int or not 0<result['game_account_id']<=2147483647:
                raise Fault('binding_mismatch',401)
            admission=result.get('admission_id')
            if admission!=rid:raise Fault('admission_mismatch',401)
            try:uuid.UUID(admission)
            except (ValueError,TypeError,AttributeError):raise Fault('invalid_platform_response',503) from None
            response={'ok':True,'connection_id':cid,'admission_id':admission,'uid':uid,'game_account_id':result['game_account_id'],'game_login_name':uid,'realm_id':'hk'}
            with self.lock,self.db() as db:
                changed=db.execute("UPDATE admissions SET state='ready',response=? WHERE connection_id=? AND state='pending'",(json.dumps(response),cid)).rowcount
                if changed!=1:raise Fault('connection_closed')
            return response
        except Fault as e:
            if e.status<500:
                with self.lock,self.db() as db:db.execute("UPDATE admissions SET state='rejected' WHERE connection_id=? AND state='pending'",(cid,))
            raise
        finally:
            with self.lock:self.inflight.discard(cid)
    def claim(self,cid,admission_id):
        cid=self.connection(cid)
        with self.lock,self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM admissions WHERE connection_id=?',(cid,)).fetchone()
            if not row or row['boot']!=self.boot or row['state']!='ready' or row['created']+60<=time.time():raise Fault('admission_unavailable')
            response=json.loads(row['response'])
            if response['admission_id']!=admission_id:raise Fault('admission_mismatch')
            db.execute("UPDATE admissions SET state='claimed' WHERE connection_id=?",(cid,))
            return response
    def close(self,cid):
        cid=self.connection(cid)
        with self.lock,self.db() as db:db.execute("UPDATE admissions SET state='closed' WHERE connection_id=? AND boot=?",(cid,self.boot))
        return {'ok':True}

class AdmissionServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,store,key):
        if address[0]!='127.0.0.1' or len(key)<32:raise ValueError('loopback and service key required')
        self.store,self.key=store,key
        super().__init__(address,AdmissionHandler)
class AdmissionHandler(BaseHTTPRequestHandler):
    def setup(self):super().setup();self.connection.settimeout(10)
    def log_message(self,*args):pass
    def reply(self,status,data):
        raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if not hmac.compare_digest(self.headers.get('X-OO-Game-Key',''),self.server.key):return self.reply(403,{'ok':False,'error':'forbidden'})
        if self.path!='/internal/v1/admissions/health':return self.reply(404,{'ok':False,'error':'not_found'})
        try:
            with self.server.store.db() as db:db.execute('SELECT 1 FROM admissions LIMIT 1').fetchone()
            self.reply(200,{'ok':True,'service':'oo-admission','protocol':'prepare-claim-v1','platform_checked':False,'pid':os.getpid()})
        except Exception:self.reply(503,{'ok':False,'error':'storage_unavailable'})
    def do_POST(self):
        if not hmac.compare_digest(self.headers.get('X-OO-Game-Key',''),self.server.key):return self.reply(403,{'ok':False,'error':'forbidden'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=8192:raise Fault('invalid_size',400)
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise Fault('json_required',415)
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):raise Fault('invalid_request',400)
            cid=body.get('connection_id')
            if self.path=='/internal/v1/admissions/prepare':result=self.server.store.prepare(cid,body.get('uid'),body.get('ticket'))
            elif self.path=='/internal/v1/admissions/claim':result=self.server.store.claim(cid,body.get('admission_id'))
            elif self.path=='/internal/v1/admissions/close':result=self.server.store.close(cid)
            else:raise Fault('not_found',404)
            self.reply(200,result)
        except Fault as e:self.reply(e.status,{'ok':False,'error':e.code})
        except (ValueError,UnicodeError):self.reply(400,{'ok':False,'error':'invalid_request'})
        except Exception:self.reply(503,{'ok':False,'error':'temporarily_unavailable'})

if __name__=='__main__':
    data=Path(os.environ.get('OO_ADMISSION_DATA',str(Path(__file__).parent/'data')))
    data.mkdir(parents=True,exist_ok=True)
    consumer=PlatformConsumer(os.environ['OO_PLATFORM_URL'],os.environ['OO_PLATFORM_GATEWAY_KEY'],os.environ.get('OO_PLATFORM_CA_FILE'))
    store=AdmissionStore(data/'admissions.sqlite3',consumer)
    server=AdmissionServer(('127.0.0.1',int(os.environ.get('OO_ADMISSION_PORT','17861'))),store,os.environ['OO_GAME_KEY'])
    print('OO admission adapter listening on loopback; platform TLS enabled',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
