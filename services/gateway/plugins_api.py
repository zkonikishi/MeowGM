"""Authenticated Manager-to-MeowCore status transport; never invent loaded state."""
import base64
import json
import os
import re
import ssl
import threading
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit,quote
from connections import protect

class PluginError(ValueError):pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class Plugins:
    def __init__(self,path,edition='meowopia-custom',protector=protect):
        self.path=Path(path);self.edition=edition;self.protector=protector;self.lock=threading.RLock()
        mapping={'meowopia-custom':'custom','sponsor':'sponsored','s4a21-sponsor':'sponsored'}
        if edition not in mapping:raise PluginError('不支持的管理器发行版')
        self.host_edition=mapping[edition]
    def read(self):
        with self.lock:
            result={'url':'http://127.0.0.1:18071','caFile':'','key':''}
            if self.path.exists():
                data=json.loads(self.path.read_text(encoding='utf-8'));result.update({k:data[k] for k in ['url','caFile']});result['key']=self.protector(base64.b64decode(data['protected']),True).decode()
            return result
    def public(self):
        r=self.read();return {'url':r['url'],'caFile':r['caFile'],'keySet':bool(r['key']),'edition':self.edition,'hostEdition':self.host_edition,'serverVersion':'86s4a21'}
    @staticmethod
    def validate(r):
        u=urlsplit(r['url'])
        if not u.hostname or u.username is not None or u.password is not None or u.query or u.fragment or u.path not in ('','/') or '\\' in r['url'] or any(c.isspace() for c in r['url']):raise PluginError('MeowCore 地址须为来源地址，不能含路径或认证信息')
        if u.scheme!='https' and not(u.scheme=='http' and u.hostname in ['127.0.0.1','::1']):raise PluginError('云端 MeowCore 必须使用 HTTPS；HTTP 仅允许回环地址')
        if r['key'] and (not 32<=len(r['key'])<=4096 or any(ord(c)<33 or ord(c)>126 for c in r['key'])):raise PluginError('控制密钥须为至少32位可打印字符')
        try:ssl.create_default_context(cafile=r['caFile'] or None)
        except Exception:raise PluginError('MeowCore CA 文件无效')
    def save(self,body):
        if not isinstance(body,dict) or set(body)-{'url','caFile','key','clearKey'}:raise PluginError('插件连接参数无效')
        with self.lock:
            r=self.read()
            for k in ['url','caFile']:
                if k in body:
                    if not isinstance(body[k],str) or len(body[k])>2048:raise PluginError('插件连接字段无效')
                    r[k]=body[k].strip()
            if body.get('key'):
                if not isinstance(body['key'],str):raise PluginError('控制密钥无效')
                r['key']=body['key']
            if body.get('clearKey') is True:r['key']=''
            self.validate(r)
            data={'url':r['url'],'caFile':r['caFile'],'protected':base64.b64encode(self.protector(r['key'].encode())).decode()}
            self.path.parent.mkdir(parents=True,exist_ok=True);temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(data),encoding='utf-8');os.replace(temporary,self.path)
        return self.public()
    def request(self,method,path,body=None):
        r=self.read();self.validate(r)
        if not r['key']:raise PluginError('尚未配置 MeowCore 控制密钥')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=r['caFile'] or None)))
        payload=json.dumps(body).encode() if body is not None else None
        request=urllib.request.Request(r['url'].rstrip('/')+path,data=payload,method=method,headers={'X-Arad-Control-Key':r['key'],'Accept':'application/json','Content-Type':'application/json'})
        try:
            with opener.open(request,timeout=120 if method=='POST' else 8) as response:
                if response.status!=200:raise PluginError('MeowCore 状态接口暂不可用')
                raw=response.read(262145)
        except urllib.error.HTTPError as e:
            if e.code in [401,403,404]:raise PluginError('MeowCore 未认证或接口不兼容')
            raw=e.read(4096)
            try:detail=json.loads(raw).get('error','')
            except Exception:detail=''
            if not isinstance(detail,str) or len(detail)>200:detail=''
            raise PluginError('MeowCore 操作拒绝或失败：'+(detail or str(e.code))+'；请重新读取状态，不自动重试')
        except (OSError,urllib.error.URLError):raise PluginError('MeowCore 尚未接通，请检查宿主与连接设置')
        if len(raw)>262144:raise PluginError('MeowCore 状态响应过大')
        try:data=json.loads(raw)
        except (ValueError,UnicodeError):raise PluginError('MeowCore 状态响应无效')
        return data
    def status(self):
        expected='meowlink.custom' if self.host_edition=='custom' else 'meowlink.sponsored'
        if not self.read()['key']:return {'connected':False,'plugins':[],'supportedActions':[],'expectedDefault':expected,'defaultProduct':'MeowLink+' if self.host_edition=='custom' else 'MeowLink','error':'尚未配置 MeowCore 控制密钥；不能确认插件已安装或加载'}
        data=self.request('GET','/v1/plugins')
        if not isinstance(data,dict) or data.get('edition')!=self.host_edition or data.get('serverVersion') not in ['86s4a21','s4a21'] or not isinstance(data.get('plugins'),list) or len(data['plugins'])>200:raise PluginError('MeowCore 发行版、游戏版本或插件状态不匹配')
        seen=set()
        for p in data['plugins']:
            if not isinstance(p,dict) or not isinstance(p.get('id'),str) or not re.fullmatch('[A-Za-z0-9_.+-]{1,80}',p['id']) or p['id'] in seen or any(type(p.get(k)) is not bool for k in ['installed','loaded','required']) or p['loaded'] and not p['installed']:raise PluginError('MeowCore 插件状态无效')
            if p['id'] in ['meowlink.custom','meowlink.sponsored'] and p['id']!=expected:raise PluginError('MeowLink 发行版不能混用')
            seen.add(p['id'])
        actions=data.get('supportedActions',[])
        if not isinstance(actions,list) or any(not isinstance(x,str) for x in actions):raise PluginError('MeowCore 能力列表无效')
        return {**data,'serverVersion':'86s4a21','connected':True,'expectedDefault':expected,'defaultProduct':'MeowLink+' if self.host_edition=='custom' else 'MeowLink','supportedActions':[a for a in actions if a in ['list','configuration','enable','disable','uninstall','install-local','update-local']],'hostSupportedActions':actions}
    def installed(self,plugin_id,capability):
        status=self.status()
        if capability not in status['supportedActions']:raise PluginError('宿主尚未开放此操作')
        item=next((p for p in status['plugins'] if p['id']==plugin_id and p['installed']),None)
        if item is None:raise PluginError('插件尚未安装，未执行操作')
        return status,item
    def control(self,body):
        if set(body)!={'pluginId','action'} or body.get('action') not in ['enable','disable','uninstall']:raise PluginError('插件操作参数无效')
        status,p=self.installed(body['pluginId'],body['action'])
        if p['required'] or p['id']==status['expectedDefault']:
            if body['action'] in ['disable','uninstall']:raise PluginError('核心必需插件不能停用或卸载')
        return self.request('POST','/v1/plugins/action',body)
    def configuration(self,body):
        if set(body) not in [{'pluginId'},{'pluginId','expectedRevision','values'}]:raise PluginError('插件配置参数无效')
        _,p=self.installed(body['pluginId'],'configuration')
        if p.get('configurationSchema') is None:raise PluginError('插件未提供配置 schema')
        if 'values' in body:
            if type(body['expectedRevision']) is not int or body['expectedRevision']<0 or not isinstance(body['values'],dict):raise PluginError('插件配置版本或内容无效')
            return self.request('POST','/v1/plugins/configuration',body)
        return self.request('GET','/v1/plugins/configuration?pluginId='+quote(body['pluginId'],safe=''))
    def panels(self):
        self.status();data=self.request('GET','/v1/plugins/ui')
        if not isinstance(data,list) or len(data)>40:raise PluginError('插件 UI 内容无效')
        for entry in data:
            p=entry.get('panel') if isinstance(entry,dict) else None
            if not isinstance(p,dict) or not isinstance(p.get('title'),str) or len(p['title'])>200 or not isinstance(p.get('text'),list) or len(p['text'])>40 or any(not isinstance(t,str) or len(t)>2000 for t in p['text']):raise PluginError('插件 UI 只支持受控纯文本')
        return data
    def marketplace(self,check=False):
        self.status();data=self.request('POST' if check else 'GET','/v1/marketplace/check' if check else '/v1/marketplace')
        if not isinstance(data,dict) or not isinstance(data.get('releases'),list) or len(data['releases'])>200 or not isinstance(data.get('state'),str):raise PluginError('商城状态无效')
        return data
    def install(self,body,local=False):
        required={'pluginId','pluginVersion','sha256','approvedPermissions','riskAcknowledged'}|({'fileName'} if local else set())
        if set(body)!=required or not isinstance(body['pluginId'],str) or not re.fullmatch('[A-Za-z0-9_.+-]{1,80}',body['pluginId']) or not isinstance(body['pluginVersion'],str) or len(body['pluginVersion'])>64 or not isinstance(body['sha256'],str) or not re.fullmatch('[a-fA-F0-9]{64}',body['sha256']) or not isinstance(body['approvedPermissions'],list) or len(body['approvedPermissions'])>100 or any(not isinstance(p,str) or len(p)>100 for p in body['approvedPermissions']) or type(body['riskAcknowledged']) is not bool:raise PluginError('安装摘要、身份或权限参数无效')
        if local:
            name=body['fileName']
            if not isinstance(name,str) or len(name)>200 or not name.lower().endswith('.zip') or '/' in name or '\\' in name or ':' in name or body['riskAcknowledged'] is not True:raise PluginError('本地 DLL 包需独立暂存文件名和明确完全信任确认')
            if 'install-local' not in self.status()['supportedActions']:raise PluginError('宿主尚未开放本地安装事务')
            return self.request('POST','/v1/plugins/install-local',body)
        self.marketplace()
        return self.request('POST','/v1/marketplace/install',body)
