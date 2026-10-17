"""Explicit SSH authentication only; no remote commands or game health assumptions."""
import base64
import hashlib
import hmac
import socket
import threading

class ManagerSSH:
    def __init__(self,settings):
        self.settings=settings;self.transport=None;self.target=None;self.lock=threading.RLock()
    def close(self):
        with self.lock:
            if self.transport:self.transport.close()
            self.transport=None;self.target=None
    def status(self):
        with self.lock:
            connected=bool(self.transport and self.transport.is_active() and self.transport.is_authenticated())
            return {'connected':connected,'target':self.target if connected else None,'gameConnected':False,'message':'SSH 已认证连接；115US 管理协议尚未接通' if connected else 'SSH 未连接'}
    def connect(self):
        import paramiko
        with self.lock:
            self.close()
            data=self.settings.read()
            if not data['host'] or not data['username'] or not data['password']:raise ValueError('请先保存服务器地址、SSH 用户名和密码')
            channel=None;sock=None
            try:
                sock=socket.create_connection((data['host'],data['port']),timeout=8)
                channel=paramiko.Transport(sock)
                channel.banner_timeout=8;channel.auth_timeout=8
                channel.start_client(timeout=8)
                if not channel.is_active():raise ValueError('SSH 握手未完成')
                key=channel.get_remote_server_key()
                fingerprint='SHA256:'+base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
                expected=data.get('hostFingerprint','')
                if not expected:
                    return {'connected':False,'gameConnected':False,'fingerprint':fingerprint,'keyType':key.get_name(),'message':'尚未验证服务器主机身份。请从服务器控制台核对指纹，填写并保存后再次连接；尚未发送密码。'}
                if not hmac.compare_digest(expected,fingerprint):raise ValueError('服务器主机指纹不匹配，连接已拒绝；请从服务器控制台核对')
                channel.auth_password(data['username'],data['password'],fallback=False)
                if not channel.is_authenticated():raise ValueError('SSH 认证未完成')
                channel.set_keepalive(30)
                self.transport=channel;self.target={'host':data['host'],'port':data['port'],'username':data['username']}
                channel=None;sock=None
                return self.status()
            except paramiko.AuthenticationException:raise ValueError('SSH 用户名或密码不正确，或服务器未开放密码认证') from None
            except (paramiko.SSHException,OSError,EOFError):raise ValueError('SSH 连接失败，请检查地址、端口、网络和服务器 SSH 配置') from None
            finally:
                if channel:channel.close()
                if sock:sock.close()
