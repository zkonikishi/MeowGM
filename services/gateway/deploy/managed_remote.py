"""Linux user-systemd worker, invoked over authenticated SSH with JSON stdin."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.request

OWNER='oo-admission-managed-v1'
UNIT='oo-admission-managed.service'

def system(*args,check=True):
    return subprocess.run(['systemctl','--user',*args],check=check,capture_output=True,text=True)

def safe(path):
    if path.is_symlink() or path.resolve()!=path.absolute():raise ValueError('unsafe_path')

def write(path,data):
    safe(path);temporary=path.with_name(path.name+'.pending');safe(temporary)
    with temporary.open('w',encoding='utf-8') as f:f.write(data)
    os.chmod(temporary,0o600);os.replace(temporary,path)

def execute(p):
    import fcntl
    if sys.version_info<(3,11) or os.geteuid()==0:raise ValueError('requires_nonroot_python311')
    if p['action'] not in ('deploy','uninstall','status'):raise ValueError('invalid_action')
    if not re.fullmatch(r'[a-f0-9]{32}',p['id']):raise ValueError('invalid_id')
    home=Path.home();base=home/'.local/share/oo-admission-managed';safe(base)
    unit=home/'.config/systemd/user'/UNIT;safe(unit)
    system('show-environment')
    if p['action']=='deploy':
        linger=subprocess.run(['loginctl','show-user',str(os.getuid()),'-p','Linger','--value'],check=True,capture_output=True,text=True).stdout.strip()
        if linger!='yes':raise ValueError('enable_user_linger_required')
    marker=base/'.owner'
    if base.exists() and any(base.iterdir()) and (not marker.is_file() or marker.is_symlink() or marker.read_text()!=OWNER):raise ValueError('unmanaged_directory')
    if not base.exists() and p['action']!='deploy':return {'state':'not_installed','id':p['id']}
    base.mkdir(parents=True,exist_ok=True);os.chmod(base,0o700)
    for name in ('.owner','.lock','current','environment','data','releases','receipts','unit.sha256'):
        path=base/name
        if name!='current':safe(path)
    if not marker.exists():write(marker,OWNER)
    with (base/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        receipts=base/'receipts';receipts.mkdir(exist_ok=True)
        receipt=receipts/(p['id']+'.json');safe(receipt)
        if p['action']=='status':
            return json.loads(receipt.read_text()) if receipt.exists() else {'state':'unknown','id':p['id']}
        if receipt.exists():return json.loads(receipt.read_text())
        previous_unit=unit.read_text() if unit.exists() else None
        if previous_unit and ('# '+OWNER+'\n') not in previous_unit:raise ValueError('unmanaged_unit')
        digest=base/'unit.sha256'
        if previous_unit and (not digest.exists() or digest.read_text()!=hashlib.sha256(previous_unit.encode()).hexdigest()):raise ValueError('changed_unit')
        current=base/'current';old=os.readlink(current) if current.is_symlink() else None
        if current.exists() and not current.is_symlink():raise ValueError('unmanaged_current')
        if old and (current.resolve().parent!=(base/'releases').resolve() or not re.fullmatch('[a-f0-9]{64}',current.resolve().name)):raise ValueError('unsafe_release')
        was_active=system('is-active',UNIT,check=False).returncode==0
        was_enabled=system('is-enabled',UNIT,check=False).returncode==0
        def finish(state,**extra):
            result={'id':p['id'],'state':state,**extra};write(receipt,json.dumps(result));return result
        finish('running')
        if p['action']=='uninstall':
            try:
                if previous_unit:
                    system('disable','--now',UNIT)
                    if system('is-active',UNIT,check=False).returncode==0:raise ValueError('still_active')
                    unit.unlink();system('daemon-reload')
                if current.is_symlink():current.unlink()
                # Remove only recognized package files, never recursively remove state.
                releases=base/'releases'
                if releases.exists():
                    for release in releases.iterdir():
                        safe(release)
                        if not re.fullmatch('[a-f0-9]{64}',release.name) or not release.is_dir():continue
                        source=release/'admission.py';safe(source)
                        if source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest()==release.name:
                            source.unlink()
                            if not any(release.iterdir()):release.rmdir()
                return finish('uninstalled',retained=['environment','data','receipts'],gameModified=False)
            except Exception:return finish('uninstall_incomplete',retained=['environment','data','receipts'])
        oldenv=(base/'environment').read_text() if (base/'environment').exists() else None
        switched=False
        try:
            code=base64.b64decode(p['code'],validate=True)
            if not re.fullmatch('[a-f0-9]{64}',p['sha256']):raise ValueError('invalid_hash')
            if hashlib.sha256(code).hexdigest()!=p['sha256']:raise ValueError('hash_mismatch')
            compile(code,'admission.py','exec')
            # Fixed port; do not replace an unrelated listener.
            if not was_active:
                with socket.socket() as probe:probe.bind(('127.0.0.1',17861))
            release=base/'releases'/p['sha256'];safe(release);release.mkdir(parents=True,exist_ok=True)
            source=release/'admission.py';safe(source)
            if source.exists() and hashlib.sha256(source.read_bytes()).hexdigest()!=p['sha256']:raise ValueError('existing_release_mismatch')
            write(source,code.decode('utf-8'))
            environment=p['environment']
            if set(environment)!={'OO_PLATFORM_URL','OO_PLATFORM_GATEWAY_KEY','OO_GAME_KEY'}:raise ValueError('invalid_environment')
            from urllib.parse import urlsplit
            url=urlsplit(environment['OO_PLATFORM_URL'])
            if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:raise ValueError('invalid_platform')
            if any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_:/?.=&%+@~-]{1,2048}',v) for v in environment.values()):raise ValueError('invalid_environment')
            if any(len(environment[k])<32 for k in ('OO_GAME_KEY','OO_PLATFORM_GATEWAY_KEY')):raise ValueError('short_key')
            if environment['OO_GAME_KEY']==environment['OO_PLATFORM_GATEWAY_KEY']:raise ValueError('distinct_keys_required')
            # Verify TLS and protocol without consuming a ticket.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self,*args,**kwargs):return None
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
            with opener.open(environment['OO_PLATFORM_URL'].rstrip('/')+'/api/account/status',timeout=10) as response:status=json.loads(response.read(16384))
            if status.get('ok') is not True or status.get('protocol')!='platform-v1':raise ValueError('platform_not_ready')
            data=base/'data';data.mkdir(exist_ok=True);os.chmod(data,0o700)
            unit.parent.mkdir(parents=True,exist_ok=True)
            system('stop',UNIT,check=False);switched=True
            write(base/'environment',''.join(k+'='+v+'\n' for k,v in environment.items()))
            temporary=base/'next';safe(temporary);temporary.symlink_to(release);os.replace(temporary,current)
            content='# '+OWNER+'\n[Unit]\nDescription=OO S4A21 admission gateway\n[Service]\nExecStart=/usr/bin/python3 '+str(current/'admission.py')+'\nEnvironmentFile='+str(base/'environment')+'\nEnvironment=OO_ADMISSION_DATA='+str(data)+'\nEnvironment=PYTHONDONTWRITEBYTECODE=1\nRestart=on-failure\nUMask=0077\nNoNewPrivileges=true\n[Install]\nWantedBy=default.target\n'
            write(unit,content);system('daemon-reload');system('enable','--now',UNIT)
            for attempt in range(15):
                try:
                    request=urllib.request.Request('http://127.0.0.1:17861/internal/v1/admissions/health',headers={'X-OO-Game-Key':environment['OO_GAME_KEY']})
                    with opener.open(request,timeout=2) as response:health=json.load(response)
                    pid=int(system('show',UNIT,'--property=MainPID','--value').stdout)
                    if pid<=0 or health.get('pid')!=pid or health.get('service')!='oo-admission' or health.get('ok') is not True:raise ValueError('identity_mismatch')
                    write(digest,hashlib.sha256(content.encode()).hexdigest())
                    return finish('deployed',sha256=p['sha256'],port=17861,gameAdmissionVerified=False)
                except Exception:
                    if attempt==14:raise
                    time.sleep(1)
        except Exception:
            rollback=True
            if switched:
                try:
                    system('stop',UNIT)
                    if current.is_symlink():current.unlink()
                    if old:current.symlink_to(old)
                    if oldenv is not None:write(base/'environment',oldenv)
                    elif (base/'environment').exists():(base/'environment').unlink()
                    if previous_unit:write(unit,previous_unit)
                    elif unit.exists():unit.unlink()
                    system('daemon-reload')
                    system('enable' if was_enabled else 'disable',UNIT,check=False)
                    if was_active:system('start',UNIT)
                except Exception:rollback=False
            return finish('failed_rolled_back' if rollback else 'rollback_incomplete',dataRetained=True)

if __name__=='__main__':
    try:print(json.dumps(execute(json.load(sys.stdin))))
    except Exception:print(json.dumps({'state':'preflight_failed','message':'检查Python3.11、非root部署身份、用户systemd/linger、目录所有权及服务冲突'}));sys.exit(1)
