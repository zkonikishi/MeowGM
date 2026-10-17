"""Local connection settings. Windows secrets use current-user DPAPI."""
import base64
import ctypes
import json
import os
from pathlib import Path
import threading
import time
import urllib.request
from gm_adapter import GmAdapter
from operations import AdminTransport

PUBLIC=('gmUrl','platformUrl','caFile')
SECRETS=('gmPassword','adminKey')
ENV={'gmUrl':'OO_GM_URL','platformUrl':'OO_PLATFORM_URL','caFile':'OO_PLATFORM_CA_FILE','gmPassword':'OO_GM_PASSWORD','adminKey':'OO_PLATFORM_ADMIN_KEY'}

def protect(raw, decrypt=False):
    if os.name!='nt':raise ValueError('持久保存连接密钥仅支持 Windows；其他系统使用服务环境配置')
    from ctypes import wintypes
    class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_byte))]
    buffer=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_byte)));target=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    fn=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    fn.restype=wintypes.BOOL
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ValueError('连接密钥保护失败，请使用保存配置的 Windows 用户')
    try:return ctypes.string_at(target.data,target.size)
    finally:
        kernel=ctypes.WinDLL('kernel32');kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree(target.data)

class Connections:
    def __init__(self,path,protector=protect):self.path=Path(path);self.protector=protector;self.lock=threading.RLock()
    def read(self):
        with self.lock:
            result={k:os.environ.get(v,'') for k,v in ENV.items()}
            if self.path.exists():
                data=json.loads(self.path.read_text(encoding='utf-8'))
                result.update({k:data.get(k,'') for k in PUBLIC})
                secret=json.loads(self.protector(base64.b64decode(data['protected']),True))
                result.update({k:secret.get(k,'') for k in SECRETS})
            return result
    def public(self):
        values=self.read()
        return {**{k:values[k] for k in PUBLIC},**{k+'Set':bool(values[k]) for k in SECRETS}}
    def reset(self):
        with self.lock:
            if self.path.exists():
                backup=self.path.with_name(self.path.name+'.before-reset-'+str(time.time_ns()))
                os.replace(self.path,backup)
    @staticmethod
    def adapters(values):
        gm=GmAdapter(values['gmUrl'],values['gmPassword'] or None) if values['gmUrl'] else None
        admin=AdminTransport(values['platformUrl'],values['adminKey'],values['caFile'] or None) if values['platformUrl'] and values['adminKey'] else None
        if values['platformUrl'] and not admin:AdminTransport(values['platformUrl'],'validation-placeholder-key-0000000',values['caFile'] or None)
        return gm,admin
    def save(self,body):
        allowed=set(PUBLIC+SECRETS)|{'clearSecrets'}
        if not isinstance(body,dict) or set(body)-allowed:raise ValueError('连接设置字段无效')
        with self.lock:
            values=self.read()
            for key in PUBLIC:
                value=body.get(key,values[key])
                if not isinstance(value,str) or len(value)>2048:raise ValueError('连接设置过长')
                values[key]=value.strip()
            clear=body.get('clearSecrets',[])
            if not isinstance(clear,list) or any(k not in SECRETS for k in clear):raise ValueError('清除密钥字段无效')
            for key in SECRETS:
                value=body.get(key,'')
                if not isinstance(value,str) or len(value)>4096:raise ValueError('密钥格式无效')
                if value:values[key]=value
                if key in clear:values[key]=''
            adapters=self.adapters(values)
            protected=self.protector(json.dumps({k:values[k] for k in SECRETS}).encode())
            data={**{k:values[k] for k in PUBLIC},'protected':base64.b64encode(protected).decode()}
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(data),encoding='utf-8');os.replace(temporary,self.path)
            return adapters
    def check(self):
        values=self.read();gm,_=self.adapters(values);result={}
        if gm:
            try:result['gm']={'ok':True,'message':'已认证读取账号列表','accountCount':len(gm.accounts()['accounts'])}
            except Exception:result['gm']={'ok':False,'message':'无法读取账号，请检查 GM 服务、密码或 SSH 隧道'}
        else:result['gm']={'ok':False,'message':'未配置 GM 地址'}
        if values['platformUrl']:
            try:
                transport=AdminTransport(values['platformUrl'],'health-probe-placeholder-key-00000',values['caFile'] or None)
                with transport.opener.open(values['platformUrl'].rstrip('/')+'/api/account/status',timeout=8) as response:
                    raw=response.read(16385)
                    if len(raw)>16384:raise ValueError()
                    data=json.loads(raw)
                    if data.get('ok') is not True or data.get('protocol')!='platform-v1':raise ValueError()
                result['platform']={'ok':True,'message':'平台身份接口可达；管理权限需实际操作回执确认'}
            except Exception:result['platform']={'ok':False,'message':'平台状态不可用，请检查地址、证书或部署'}
        else:result['platform']={'ok':False,'message':'未配置平台地址'}
        return result


class ServerSettings:
    """Manual SSH settings; saving never opens a network connection."""
    def __init__(self,path,protector=protect):
        self.path=Path(path);self.protector=protector;self.lock=threading.RLock()
    def read(self):
        if not self.path.exists():return {'host':'','port':22,'username':'','password':'','hostFingerprint':''}
        data=json.loads(self.path.read_text(encoding='utf-8'))
        data.setdefault('hostFingerprint','')
        data['password']=self.protector(base64.b64decode(data.pop('protected')),True).decode('utf-8')
        return data
    def public(self):
        with self.lock:
            data=self.read();secret=data.pop('password');return {**data,'passwordSet':bool(secret),'connected':False}
    def save(self,body):
        if not isinstance(body,dict) or set(body)-{'host','port','username','password','clearPassword','hostFingerprint'}:raise ValueError('服务器配置字段无效')
        with self.lock:
            data=self.read();old_target=(data['host'],data['port'])
            for key in ('host','username'):
                value=body.get(key,data[key])
                if not isinstance(value,str) or len(value)>253 or any(c.isspace() for c in value.strip()):raise ValueError('服务器地址或用户名格式无效')
                data[key]=value.strip()
            fingerprint=body.get('hostFingerprint',data.get('hostFingerprint',''))
            import re
            if not isinstance(fingerprint,str) or (fingerprint and not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}',fingerprint)):raise ValueError('主机指纹需要为 OpenSSH SHA256 格式')
            if old_target!=(data['host'],body.get('port',data['port'])) and 'hostFingerprint' not in body:fingerprint=''
            data['hostFingerprint']=fingerprint
            port=body.get('port',data['port'])
            if type(port) is not int or not 1<=port<=65535:raise ValueError('SSH 端口需要为 1 至 65535')
            data['port']=port
            password=body.get('password','')
            if not isinstance(password,str) or len(password)>4096:raise ValueError('SSH 密码格式无效')
            if password:data['password']=password
            if body.get('clearPassword') is True:data['password']=''
            encoded={k:v for k,v in data.items() if k!='password'}
            encoded['protected']=base64.b64encode(self.protector(data['password'].encode('utf-8'))).decode('ascii')
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(encoded),encoding='utf-8');os.replace(temporary,self.path)
            return self.public()
