"""Private desktop host, bundled with Python into MeowGM."""
import json
import os
import secrets
import hmac
import sqlite3
import threading
import time
from pathlib import Path
from server import Gateway, Handler, Store

class DesktopHandler(Handler):
    def do_GET(self):
        if self.path=='/api/desktop/setup':
            if not self.valid_host():return
            if getattr(self.server,'local_mode',False):return self.reply(200,{'required':False,'localMode':True})
            return self.reply(200,{'required':bool(self.server.setup_nonce)})
        return super().do_GET()
    def do_POST(self):
        if getattr(self.server,'local_mode',False):
            if self.path=='/api/desktop/connect':return self.connect_window()
            if self.path in ('/api/desktop/setup','/api/admin/login','/api/admin/profile','/api/admin/logout'):
                if not self.valid_host():return
                return self.reply(410,{'error':'本地模式无需创建或登录本机账号，请从 MeowGM 窗口连接服务器。'})
        if self.path!='/api/desktop/setup':return super().do_POST()
        if not self.valid_host():return
        if self.headers.get('Origin')!=f'http://{self.server.authority}':return self.reply(403,{'error':'请求来源无效'})
        with self.server.auth_lock:
            if not self.server.setup_nonce or not hmac.compare_digest(self.headers.get('X-OO-Setup',''),self.server.setup_nonce):return self.reply(403,{'error':'初始化入口已失效'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4096:raise ValueError()
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                    return self.reply(415,{'error':'需要 JSON'})
                body=json.loads(self.rfile.read(size))
                if not isinstance(body,dict) or set(body)!={'username','password'}:
                    return self.reply(400,{'error':'请填写管理员账号和密码'})
                password=body.get('password')
                if not isinstance(password,str) or not 12<=len(password)<=256:
                    return self.reply(400,{'error':'管理员密码需要12至256位'})
                username=body.get('username','admin')
                self.server.store.initialize(password,username)
                self.server.operations.actor=username
                self.server.setup_nonce=''
                key=secrets.token_urlsafe(32)
                self.server.sessions[key]=time.time()+1800
                return self.reply(200,{'ok':True},cookie=f'oo_session={key}; HttpOnly; SameSite=Strict; Path=/; Max-Age=1800')
            except ValueError as e:return self.reply(400,{'error':str(e) or '初始化参数不正确'})
            except (TypeError,AttributeError):return self.reply(400,{'error':'初始化参数不正确'})
            except sqlite3.IntegrityError:return self.reply(409,{'error':'管理员已经创建，请重新打开登录页'})

    def connect_window(self):
        if not self.valid_host():return
        if self.headers.get('Origin')!=f'http://{self.server.authority}':return self.reply(403,{'error':'请求来源无效'})
        token=getattr(self.server,'desktop_nonce','')
        if not token or not hmac.compare_digest(self.headers.get('X-OO-Window',''),token):
            return self.reply(403,{'error':'本机窗口验证失败，请重新打开 MeowGM'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=64 or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError()
            if json.loads(self.rfile.read(length))!={}:raise ValueError()
        except (ValueError,TypeError):return self.reply(400,{'error':'本机窗口连接参数无效'})
        with self.server.auth_lock:
            key=secrets.token_urlsafe(32)
            # A private window can renew its own session. It does not create an admin account.
            self.server.sessions={k:v for k,v in self.server.sessions.items() if v>time.time()}
            if len(self.server.sessions)>=16:self.server.sessions.clear()
            self.server.sessions[key]=time.time()+1800
        return self.reply(200,{'ok':True,'localMode':True},cookie=f'oo_session={key}; HttpOnly; SameSite=Strict; Path=/; Max-Age=1800')

def main():
    if __import__('sys').argv[1:]==['--meowgm-fixture-worker']:
        from fixture_worker import main as worker_main
        return worker_main()
    os.environ.setdefault('MEOW_MANAGER_PROFILE','115us')
    managed_server=None
    if os.name=='nt' and os.environ.get('OO_MANAGER_PARENT'):
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        parent=kernel.OpenProcess(0x00100000,False,int(os.environ['OO_MANAGER_PARENT']))
        if not parent:raise SystemExit('Desktop parent unavailable')
        def watch():
            kernel.WaitForSingleObject(parent,0xffffffff)
            if managed_server:
                managed_server.fixture_control.close()
                managed_server.gm_bridge.close()
                managed_server.tunnel.stop()
            os._exit(0)
        threading.Thread(target=watch,daemon=True).start()
    data=Path(os.environ['OO_MANAGER_DATA']);data.mkdir(parents=True,exist_ok=True)
    store=Store(data/'gateway.sqlite3')
    server=Gateway(('127.0.0.1',0),store)
    managed_server=server
    server.RequestHandlerClass=DesktopHandler
    server.local_mode=True
    server.operations.actor='本机管理'
    server.setup_nonce=''
    server.desktop_nonce=secrets.token_urlsafe(32)
    print(json.dumps({'port':server.server_port,'setup':server.desktop_nonce}),flush=True)
    try:server.serve_forever()
    finally:server.server_close()

if __name__=='__main__':main()
