"""Durable operation outbox for explicitly configured platform admin API."""
import json
import sqlite3
import ssl
import threading
import time
import urllib.request
import urllib.error
import uuid
from contextlib import contextmanager
from urllib.parse import urlsplit

class OperationError(Exception):pass
class AdminTransport:
    def __init__(self,url,key,cafile=None):
        p=urlsplit(url)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.query or p.fragment or len(key)<32:raise ValueError('HTTPS admin endpoint and dedicated key required')
        self.url=url.rstrip('/')+'/internal/v1/admin/account-status';self.key=key
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=cafile)))
    def __call__(self,body):
        req=urllib.request.Request(self.url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Arad-Service-Key':self.key})
        try:response=self.opener.open(req,timeout=10)
        except urllib.error.HTTPError as e:response=e
        except OSError:raise OperationError('结果未确认，请使用原操作重试') from None
        with response:
            raw=response.read(16385)
            if len(raw)>16384:raise OperationError('回执过大，结果未确认')
            try:result=json.loads(raw)
            except ValueError:raise OperationError('回执无法解析，结果未确认') from None
            if response.status>=500:raise OperationError('服务暂不可用，结果未确认')
            if response.status!=200:return {'ok':False,'error':'服务拒绝操作','statusCode':response.status}
            expected_status='banned' if body['action']=='ban' else 'active'
            if not isinstance(result,dict) or result.get('ok') is not True or result.get('operation_id')!=body['operation_id'] or result.get('uid')!=body['uid'] or result.get('status')!=expected_status:
                raise OperationError('回执与原操作不匹配，结果未确认')
            return {k:result.get(k) for k in ('ok','operation_id','uid','status','auth_epoch','online_disconnect')}

class Operations:
    def __init__(self,path,transport,actor='admin'):
        self.actor=actor
        self.path=str(path);self.transport=transport;self.lock=threading.Lock();self.active=set()
        with self.db() as db:db.execute('CREATE TABLE IF NOT EXISTS admin_operations(id TEXT PRIMARY KEY,actor TEXT,created INTEGER,payload TEXT,state TEXT,result TEXT)')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def list(self):
        with self.db() as db:
            return [{'id':r['id'],'actor':r['actor'],'created':r['created'],'request':json.loads(r['payload']),'state':r['state'],'result':json.loads(r['result']) if r['result'] else None} for r in db.execute('SELECT * FROM admin_operations ORDER BY created DESC,rowid DESC LIMIT 100')]
    def create(self,body):
        if not self.transport:raise OperationError('尚未配置平台管理接口')
        if set(body)!={'uid','action','reason'}:raise OperationError('操作字段不正确')
        uid,action,reason=body['uid'],body['action'],body['reason']
        if not isinstance(uid,str) or len(uid)!=8 or not uid.isascii() or not uid.isdigit() or uid=='00000000' or action not in ('ban','unban'):raise OperationError('UID 或操作无效')
        if not isinstance(reason,str) or not 1<=len(reason.strip())<=500 or any(ord(c)<32 for c in reason):raise OperationError('请输入有效处理原因')
        body={**body,'reason':reason.strip(),'operation_id':str(uuid.uuid4())};rid=body['operation_id']
        with self.db() as db:db.execute('INSERT INTO admin_operations VALUES(?,?,?,?,?,NULL)',(rid,self.actor,int(time.time()),json.dumps(body),'pending'))
        return self.execute(rid)
    def execute(self,rid):
        if not self.transport:raise OperationError('尚未配置平台管理接口')
        with self.lock,self.db() as db:
            row=db.execute('SELECT * FROM admin_operations WHERE id=?',(rid,)).fetchone()
            if not row:raise OperationError('操作不存在')
            if rid in self.active:raise OperationError('原操作仍在处理中')
            if row['state'] in ('completed','rejected'):return {'id':rid,'state':row['state'],'result':json.loads(row['result'])}
            self.active.add(rid);body=json.loads(row['payload'])
        try:
            result=self.transport(body);state='completed' if result.get('ok') is True else 'rejected'
        except Exception:state='uncertain';result={'ok':False,'error':'结果未确认，请重试原操作，不要新建重复操作'}
        try:
            with self.db() as db:db.execute('UPDATE admin_operations SET state=?,result=? WHERE id=?',(state,json.dumps(result),rid))
            return {'id':rid,'state':state,'result':result}
        finally:
            with self.lock:self.active.discard(rid)
