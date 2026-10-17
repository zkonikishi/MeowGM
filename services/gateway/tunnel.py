"""Managed key-only OpenSSH forward; never reads or stores SSH passwords."""
import json
import os
import re
import socket
import subprocess
import threading
from pathlib import Path

class Tunnel:
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.RLock();self.stop_event=threading.Event()
        self.worker=None;self.process=None;self.state='需配置';self.port=None
    def status(self):
        with self.lock:return {'state':self.state,'localPort':self.port,'configured':self.path.exists()}
    def save(self,body):
        if not isinstance(body,dict) or set(body)!={'host','user','keyFile','knownHosts','localPort'}:raise ValueError()
        if not isinstance(body['host'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}',body['host']):raise ValueError()
        if not isinstance(body['user'],str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,31}',body['user']) or body['user'].lower() in ('root','administrator'):raise ValueError()
        if type(body['localPort']) is not int or not 1024<=body['localPort']<=65535:raise ValueError()
        for name in ('keyFile','knownHosts'):
            if not isinstance(body[name],str) or not Path(body[name]).is_absolute() or not Path(body[name]).is_file() or any(c in body[name] for c in '\r\n"'):raise ValueError()
        self.stop();self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(body),encoding='utf-8');os.replace(temp,self.path)
        self.state='已配置，未连接';return self.status()
    def start(self):
        with self.lock:
            if self.worker and self.worker.is_alive():return self.status()
            if not self.path.exists():return self.status()
            data=json.loads(self.path.read_text(encoding='utf-8'))
            self.stop_event.clear();self.state='正在连接'
            self.worker=threading.Thread(target=self._run,args=(data,),daemon=True);self.worker.start()
            return self.status()
    def _run(self,data):
        # Fixed system executable and empty config prevent inherited ProxyCommand/config rules.
        ssh=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/OpenSSH/ssh.exe'
        empty=self.path.with_suffix('.sshconfig');empty.write_text('',encoding='utf-8')
        options=['BatchMode=yes','PasswordAuthentication=no','KbdInteractiveAuthentication=no','IdentitiesOnly=yes','IdentityAgent=none','StrictHostKeyChecking=yes','UpdateHostKeys=no','GlobalKnownHostsFile=NUL','ExitOnForwardFailure=yes','ConnectTimeout=10','ServerAliveInterval=10','ServerAliveCountMax=2',f'UserKnownHostsFile="{data["knownHosts"]}"']
        args=[str(ssh),'-F',str(empty),'-N','-T','-p','22','-i',data['keyFile']]
        for option in options:args+=['-o',option]
        args+=['-L',f'127.0.0.1:{data["localPort"]}:127.0.0.1:5051',data['user']+'@'+data['host']]
        for attempt in range(5):
            if self.stop_event.is_set():break
            try:
                # Reserve check makes existing listeners fail closed; ssh also verifies bind.
                with socket.socket() as probe:probe.bind(('127.0.0.1',data['localPort']))
                with self.lock:
                    if self.stop_event.is_set():break
                    self.process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                while not self.stop_event.wait(.5):
                    if self.process.poll() is not None:break
                    try:
                        with socket.create_connection(('127.0.0.1',data['localPort']),timeout=.2):pass
                        with self.lock:self.state='隧道已连接，GM 需检测';self.port=data['localPort']
                    except OSError:pass
            except OSError:pass
            finally:
                with self.lock:
                    if self.process and self.process.poll() is None:
                        self.process.terminate()
                        try:self.process.wait(timeout=5)
                        except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
                    self.process=None;self.port=None
            if self.stop_event.is_set():break
            self.state='连接失败或已断开，正在重试（请核对身份、密钥和网络）'
            if self.stop_event.wait(min(2**attempt,16)):break
        with self.lock:self.state='已断开' if self.stop_event.is_set() else '连接失败；核对主机记录、专用密钥和网络后重新连接'
    def stop(self):
        self.stop_event.set()
        with self.lock:
            if self.process and self.process.poll() is None:self.process.terminate()
        if self.worker:self.worker.join(timeout=12)
        with self.lock:self.port=None;self.state='已断开' if self.path.exists() else '需配置'
