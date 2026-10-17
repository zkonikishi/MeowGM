"""Profile-scoped local/remote configuration. Inspection never starts game processes."""
import json
import os
import re
import threading
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import urlsplit

class Environment:
    def __init__(self,path):self.path=Path(path);self.lock=threading.RLock()
    def read(self):
        with self.lock:
            document=self.document()
            return self.validate(document['targets'][document['active']])
    def document(self):
        default=self.validate({'profile':'115us','mode':'local','root':'','version':''})
        if not self.path.exists():return {'schema':2,'active':'general.local','targets':{'general.local':default}}
        if self.path.stat().st_size>65536:raise ValueError('环境配置过大，原文件保留')
        value=json.loads(self.path.read_text(encoding='utf-8'))
        if isinstance(value,dict) and 'schema' not in value:
            legacy=self.validate(value)
            key=legacy['productMode']+'.'+legacy['mode']
            return {'schema':2,'active':key,'targets':{key:legacy}}
        if not isinstance(value,dict) or set(value)!={'schema','active','targets'} or value['schema']!=2 or not isinstance(value['targets'],dict) or not isinstance(value['active'],str) or value['active'] not in value['targets']:raise ValueError('环境配置结构无效，原文件保留')
        for key,target in value['targets'].items():
            checked=self.validate(target)
            if key!=checked['productMode']+'.'+checked['mode']:raise ValueError('目标配置身份不匹配')
        return value
    def target(self,product,mode):
        if product not in ('general','custom') or mode not in ('local','cloud'):raise ValueError('目标类型无效')
        with self.lock:
            document=self.document()
            value=document['targets'].get(product+'.'+mode,{'profile':'115us','productMode':product,'mode':mode,'root':'','version':''})
            return self.inspect(self.validate(value))
    @staticmethod
    def validate(value):
        if not isinstance(value,dict) or not {'profile','mode','root','version'}<=set(value) or set(value)-{'profile','mode','root','version','productMode','managementBaseUrl','realm'}:raise ValueError('环境配置字段不正确')
        value={**{'productMode':'general','managementBaseUrl':'','realm':''},**value}
        if value['productMode'] not in ('general','custom'):raise ValueError('请选择通用或自定义模式')
        if value['profile']!='115us':raise ValueError('86S4A21 已冻结停止，不允许切回或启动旧服')
        if value['mode'] not in ('local','cloud'):raise ValueError('请选择本地或云端管理')
        if not all(isinstance(value[k],str) and len(value[k])<=2048 for k in ('root','version')):raise ValueError('环境配置过长')
        if value['root'] and value['mode']=='local' and not Path(value['root']).is_absolute():raise ValueError('本地目录必须是绝对路径')
        if value['root'] and value['mode']=='cloud' and (not PurePosixPath(value['root']).is_absolute() or '..' in PurePosixPath(value['root']).parts or '\\' in value['root'] or any(ord(x)<32 for x in value['root'])):raise ValueError('云端根目录必须是无跳转的 Linux 绝对路径')
        if not isinstance(value['realm'],str) or (value['realm'] and not re.fullmatch(r'[A-Za-z0-9._-]{1,80}',value['realm'])):raise ValueError('区服标识格式无效')
        base=value['managementBaseUrl']
        if not isinstance(base,str) or len(base)>2048:raise ValueError('管理地址格式无效')
        if base:
            try:
                url=urlsplit(base)
                if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('','/') or any(ord(x)<=32 or x=='\\' for x in base) or url.port==0:raise ValueError()
            except ValueError:raise ValueError('管理地址必须为 HTTPS 源地址，不含账号、密码、路径、查询或片段') from None
            value['managementBaseUrl']=base.rstrip('/')
        if value['version'] and not re.fullmatch(r'[A-Za-z0-9._-]{1,80}',value['version']):raise ValueError('版本标签格式不正确')
        return dict(value)
    def save(self,value):
        with self.lock:
            document=self.document()
            if isinstance(value,dict) and 'productMode' not in value:value={**value,'productMode':self.read()['productMode']}
            if isinstance(value,dict):
                prior=document['targets'].get(str(value.get('productMode'))+'.'+str(value.get('mode')), {})
                value={**{k:prior.get(k,'') for k in ('managementBaseUrl','realm')},**value}
            value=self.validate(value)
            key=value['productMode']+'.'+value['mode']
            document['targets'][key]=value;document['active']=key
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(document,ensure_ascii=False),encoding='utf-8');os.replace(temporary,self.path)
        return self.inspect()
    def inspect(self,value=None):
        value=value if value is not None else self.read()
        result={**value,'configured':False,'running':None,'connected':False,'manifestVersion':None,'modkitAvailable':False,
                'message':'请选择 115US 环境目录；文件存在不代表服务正在运行。','capabilities':{'startGame':False,'console':False,'modkitControl':False,'accountWrite':False}}
        if value['mode']=='cloud':
            result['configured']=bool(value['managementBaseUrl'] and value['realm'] and value['root'])
            result['message']='云端目标配置；HTTPS 管理合同待服务端确认，尚未连接或验证权限。'
            return result
        if not value['root']:return result
        root=Path(value['root'])
        if not root.is_dir() or root.is_symlink() or getattr(root,'is_junction',lambda:False)():
            result['message']='环境目录不存在或为链接，请选择实际 115US 目录。';return result
        manifest=root/'version.json'
        if manifest.is_file() and not manifest.is_symlink() and manifest.stat().st_size<=65536:
            try:
                data=json.loads(manifest.read_text(encoding='utf-8-sig'))
                version=data.get('version')
                if isinstance(version,str) and len(version)<=80:result['manifestVersion']=version
            except (ValueError,OSError):pass
        result['configured']=True
        result['message']='已读取本地目录。尚未与 115US 编排程序握手，运行状态未知；未读取或修改玩家数据库。'
        return result
