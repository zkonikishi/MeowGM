"""Real loopback SSH handshake/authentication; no remote commands or production data."""
import base64
import hashlib
import socket
import threading
import unittest
import paramiko
from manager_ssh import ManagerSSH

class Settings:
    def __init__(self,data):self.data=data
    def read(self):return dict(self.data)

class SSHTests(unittest.TestCase):
    def setUp(self):
        self.key=paramiko.RSAKey.generate(2048)
        self.fingerprint='SHA256:'+base64.b64encode(hashlib.sha256(self.key.asbytes()).digest()).decode().rstrip('=')
        self.auth=[];self.transports=[]
        self.listener=socket.socket();self.listener.bind(('127.0.0.1',0));self.listener.listen();self.listener.settimeout(0.2)
        self.stop=threading.Event()
        owner=self
        class Server(paramiko.ServerInterface):
            def get_allowed_auths(self,username):return 'password'
            def check_auth_password(self,username,password):
                owner.auth.append((username,password))
                return paramiko.AUTH_SUCCESSFUL if (username,password)==('fixture','fixture-password') else paramiko.AUTH_FAILED
        def serve():
            while not self.stop.is_set():
                try:conn,_=self.listener.accept()
                except socket.timeout:continue
                except OSError:return
                transport=paramiko.Transport(conn);self.transports.append(transport);transport.add_server_key(self.key)
                try:transport.start_server(server=Server())
                except (paramiko.SSHException,EOFError,OSError):transport.close()
        self.thread=threading.Thread(target=serve,daemon=True);self.thread.start()
        self.settings=Settings({'host':'127.0.0.1','port':self.listener.getsockname()[1],'username':'fixture','password':'fixture-password','hostFingerprint':self.fingerprint})
        self.client=ManagerSSH(self.settings)
    def tearDown(self):
        self.client.close();self.stop.set();self.listener.close();self.thread.join(timeout=2)
        for transport in self.transports:transport.close()
    def test_explicit_connection_uses_custom_port_and_disconnects(self):
        self.assertFalse(self.client.status()['connected'])
        result=self.client.connect()
        self.assertTrue(result['connected']);self.assertFalse(result['gameConnected'])
        self.assertEqual(self.auth,[('fixture','fixture-password')])
        self.client.close();self.assertFalse(self.client.status()['connected'])
    def test_unknown_host_reports_fingerprint_without_sending_password(self):
        self.settings.data['hostFingerprint']=''
        result=self.client.connect()
        self.assertFalse(result['connected']);self.assertEqual(result['fingerprint'],self.fingerprint)
        self.assertEqual(self.auth,[])
    def test_changed_host_is_rejected_before_password(self):
        self.settings.data['hostFingerprint']='SHA256:'+'A'*43
        with self.assertRaisesRegex(ValueError,'指纹不匹配'):self.client.connect()
        self.assertEqual(self.auth,[])
    def test_wrong_password_does_not_leave_connected_state(self):
        self.settings.data['password']='wrong'
        with self.assertRaisesRegex(ValueError,'用户名或密码'):self.client.connect()
        self.assertFalse(self.client.status()['connected'])
