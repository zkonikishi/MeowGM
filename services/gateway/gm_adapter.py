"""Fixed read-only A21 GM API adapter; no generic URL or write proxy."""
import http.cookiejar
import json
import threading
import urllib.request
import urllib.error
from urllib.parse import urlsplit

class GmError(Exception):pass
class GmAdapter:
    def __init__(self,url,password=None):
        p=urlsplit(url)
        if p.scheme!='http' or p.hostname not in ('127.0.0.1','localhost','::1') or p.username or p.password or p.path not in ('','/') or p.query or p.fragment:
            raise ValueError('GM endpoint must be loopback; use a local SSH tunnel for remote GM')
        self.url=url.rstrip('/');self.password=password;self.lock=threading.Lock();self.authenticated=False
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def _request(self,path,body=None):
        req=urllib.request.Request(self.url+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        try:
            with self.opener.open(req,timeout=8) as response:
                raw=response.read(2097153)
                if len(raw)>2097152:raise GmError('GM 响应过大，请缩小查询范围')
                result=json.loads(raw)
                if not isinstance(result,dict) or result.get('success') is False:raise GmError('GM 未就绪或拒绝请求，请检查连接与认证')
                return result
        except urllib.error.HTTPError as e:
            if e.code==401:self.authenticated=False
            raise GmError('GM 接口不可用或登录已过期') from None
        except (OSError,ValueError,urllib.error.URLError):raise GmError('无法读取 GM，请确认服务或隧道已启动') from None
    def read(self,path):
        with self.lock:
            if self.password and not self.authenticated:
                self._request('/api/auth/login',{'password':self.password});self.authenticated=True
            return self._request(path)
    def accounts(self):
        result=self.read('/api/accounts');rows=result.get('accounts')
        if not isinstance(rows,list):raise GmError('GM 账号响应格式不匹配')
        fields=('accountId','name','cera','tokenCera','luckyStar','characterCount','characterNames')
        return {'accounts':[{k:row.get(k) for k in fields} for row in rows if isinstance(row,dict)]}
    def characters(self,account_id):
        if type(account_id) is not int or not 0<account_id<=2147483647:raise GmError('游戏账号 ID 无效')
        result=self.read('/api/characters?accountId='+str(account_id));rows=result.get('characters')
        if not isinstance(rows,list):raise GmError('GM 角色响应格式不匹配')
        fields=('characterId','name','level','jobName','accountId','accountName')
        if any(not isinstance(row,dict) or row.get('accountId')!=account_id for row in rows):raise GmError('GM 返回角色所属账号不匹配')
        return {'characters':[{k:row.get(k) for k in fields} for row in rows]}
