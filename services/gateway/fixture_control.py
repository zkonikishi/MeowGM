"""Local-only synthetic owned-process reference. No configurable command or target."""
from collections import deque
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

class FixtureControl:
    def __init__(self,data,enabled=False):
        self.data=Path(data)/'fixture-control';self.enabled=enabled
        self.lock=threading.RLock();self.action_lock=threading.RLock();self.process=None;self.generation=0
        self.last_heartbeat=None;self.ready=threading.Event();self.seq=0;self.lines=deque(maxlen=200)
    def log(self,text):
        self.seq+=1
        self.lines.append({'seq':self.seq,'at':datetime.now(timezone.utc).isoformat(),'text':text})
    def status(self):
        with self.lock:
            running=self.process is not None and self.process.poll() is None
            healthy=running and self.last_heartbeat is not None and time.monotonic()-self.last_heartbeat<3
            return {'enabled':self.enabled,'protocol':'meowgm-fixture-v1','scope':'synthetic-only','running':running,'healthy':healthy,'state':'running' if healthy else 'starting' if running else 'stopped','commands':['start','stop'] if self.enabled else [],'message':'仅内置合成进程；不是游戏或云端服务' if self.enabled else '未启用合成演练；真实管理合同尚未协商'}
    def logs(self,after=0):
        if type(after) is not int or after<0:raise ValueError('日志游标无效')
        with self.lock:
            rows=[dict(row) for row in self.lines if row['seq']>after]
            first=self.lines[0]['seq'] if self.lines else self.seq+1
            return {'scope':'synthetic-only','items':rows,'cursor':self.seq,'truncated':after<first-1}
    def start(self,body):
        with self.action_lock:return self._start(body)
    def _start(self,body):
        if body!={}:raise ValueError('合成演练不接受命令、路径或连接参数')
        with self.lock:
            if not self.enabled:raise ValueError('合成演练未在主机启动配置中启用')
            if self.process is not None and self.process.poll() is None:return self.status()
            self.data.mkdir(parents=True,exist_ok=True)
            self.generation+=1;generation=self.generation;self.ready=threading.Event();ready=self.ready;self.last_heartbeat=None
            command=[sys.executable,'--meowgm-fixture-worker'] if getattr(sys,'frozen',False) else [sys.executable,'-u',str(Path(__file__).with_name('fixture_worker.py'))]
            # Independent pipe is the only worker capability. Inherit no credentials or server variables.
            env={key:os.environ[key] for key in ('SystemRoot','WINDIR','PATH') if key in os.environ}
            env.update(TEMP=str(self.data),TMP=str(self.data),PYTHONIOENCODING='utf-8',PYTHONPYCACHEPREFIX=str(self.data/'pycache'))
            process=subprocess.Popen(command,cwd=self.data,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=0x08000000 if os.name=='nt' else 0)
            self.process=process;self.log('已启动内置合成进程，等待协议握手')
            def read():
                try:
                    while True:
                        raw=process.stdout.readline(4097)
                        if not raw:break
                        if len(raw)>4096:break
                        message=json.loads(raw)
                        if message.get('protocol')!='meowgm-fixture-v1':break
                        with self.lock:
                            if generation!=self.generation:return
                            if message.get('type') in ('ready','heartbeat'):
                                self.last_heartbeat=time.monotonic()
                                if message['type']=='ready':self.log('合成进程握手成功');ready.set()
                            elif message.get('type')=='stopped':self.log('合成进程已确认停止')
                except (ValueError,OSError):pass
            threading.Thread(target=read,daemon=True).start()
        if not ready.wait(5):
            self.close();raise ValueError('合成进程握手失败，已停止自有进程')
        return self.status()
    def stop(self,body):
        if body!={}:raise ValueError('停止只作用于本实例持有的合成进程，不接受 PID 或路径')
        self.close();return self.status()
    def close(self):
        with self.action_lock:self._close()
    def _close(self):
        with self.lock:
            self.generation+=1;process=self.process;self.process=None;self.last_heartbeat=None
            if process:self.log('正在停止本实例持有的合成进程')
        if process:
            try:
                if process.poll() is None:
                    process.stdin.write(b'stop\n');process.stdin.flush();process.wait(timeout=2)
            except (OSError,subprocess.TimeoutExpired):
                if process.poll() is None:process.kill();process.wait(timeout=3)
            finally:
                for stream in (process.stdin,process.stdout):
                    try:stream.close()
                    except (OSError,AttributeError):pass
            with self.lock:self.log('自有合成进程已停止；未操作其他进程')
