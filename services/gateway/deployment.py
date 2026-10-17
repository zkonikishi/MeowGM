"""Asynchronous, receipt-backed SSH gateway deployment with no persisted secrets."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid

ASSETS=Path(sys._MEIPASS)/'gateway-package' if getattr(sys,'frozen',False) else Path(__file__).parent

class Deployment:
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.Lock();self.active=False
        self.path.mkdir(parents=True,exist_ok=True)
    def status(self):
        rows=[]
        for path in sorted(self.path.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]:
            row=json.loads(path.read_text(encoding='utf-8'))
            if row['state']=='running' and not self.active:row['state']='unknown'
            rows.append(row)
        return {'active':self.active,'jobs':rows}
    def record(self,row):
        path=self.path/(row['id']+'.json');temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(row,ensure_ascii=False),encoding='utf-8');os.replace(temp,path)
    def validate(self,body):
        required={'action','host','user','port','keyFile','knownHosts'}
        if not isinstance(body,dict) or not required.issubset(body) or set(body)-required-{'platformUrl','gatewayKey','gameKey','operationId'}:raise ValueError()
        if body['action'] not in ('deploy','uninstall','status'):raise ValueError()
        if not isinstance(body['host'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}',body['host']):raise ValueError()
        if not isinstance(body['user'],str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}',body['user']) or body['user']=='root':raise ValueError()
        if type(body['port']) is not int or not 1<=body['port']<=65535:raise ValueError()
        for field in ('keyFile','knownHosts'):
            value=body[field]
            if not isinstance(value,str) or not Path(value).is_absolute() or not Path(value).is_file() or any(c in value for c in '\r\n"'):raise ValueError()
        if body['action']=='deploy':
            from urllib.parse import urlsplit
            url=urlsplit(body.get('platformUrl',''))
            if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:raise ValueError()
            for field in ('gatewayKey','gameKey'):
                if not isinstance(body.get(field),str) or not re.fullmatch(r'[A-Za-z0-9_+/=@~-]{32,256}',body[field]):raise ValueError()
            if body['gatewayKey']==body['gameKey']:raise ValueError()
        if body['action']=='status' and not re.fullmatch('[a-f0-9]{32}',body.get('operationId','')):raise ValueError()
    def start(self,body):
        self.validate(body)
        with self.lock:
            if self.active:raise RuntimeError('已有部署任务执行中')
            self.active=True
            row={'id':uuid.uuid4().hex,'action':body['action'],'host':body['host'],'user':body['user'],'state':'running','at':int(time.time())}
            self.record(row)
            threading.Thread(target=self.run,args=(dict(body),row),daemon=True).start()
            return row
    def run(self,body,row):
        try:
            script=(ASSETS/'deploy/managed_remote.py').read_bytes()
            payload={'id':body.get('operationId') if body['action']=='status' else row['id'],'action':body['action']}
            if body['action']=='deploy':
                code=(ASSETS/'admission.py').read_bytes()
                payload.update(code=base64.b64encode(code).decode(),sha256=hashlib.sha256(code).hexdigest(),environment={'OO_PLATFORM_URL':body['platformUrl'],'OO_PLATFORM_GATEWAY_KEY':body['gatewayKey'],'OO_GAME_KEY':body['gameKey']})
            ssh=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/OpenSSH/ssh.exe'
            empty=self.path/'empty-ssh-config';empty.write_text('',encoding='utf-8')
            args=[str(ssh),'-F',str(empty),'-T','-p',str(body['port']),'-i',body['keyFile']]
            for option in ('BatchMode=yes','PasswordAuthentication=no','KbdInteractiveAuthentication=no','IdentitiesOnly=yes','IdentityAgent=none','StrictHostKeyChecking=yes','UpdateHostKeys=no','GlobalKnownHostsFile=NUL','ConnectTimeout=10','ServerAliveInterval=10','ServerAliveCountMax=2',f'UserKnownHostsFile="{body["knownHosts"]}"'):args+=['-o',option]
            command='python3 -c "import base64;exec(base64.b64decode(\''+base64.b64encode(script).decode()+'\'))"'
            args+=[body['user']+'@'+body['host'],command]
            result=subprocess.run(args,input=json.dumps(payload),text=True,encoding='utf-8',capture_output=True,timeout=150,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            receipt=json.loads(result.stdout)
            allowed={'deployed','uninstalled','not_installed','preflight_failed','failed_rolled_back','rollback_incomplete','uninstall_incomplete','unknown','running'}
            if receipt.get('state') not in allowed or (receipt.get('state')!='preflight_failed' and receipt.get('id')!=payload['id']):raise ValueError()
            row.update(state=receipt['state'],remoteOperationId=payload['id'])
        except Exception:row.update(state='unknown',message='连接中断或回执无效。请用本任务编号回查，勿直接重复部署。')
        finally:
            body.clear()
            with self.lock:self.record(row);self.active=False
