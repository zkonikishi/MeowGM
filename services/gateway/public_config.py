"""Install public settings into an operator-prepared client distribution folder."""
import json
import os
import re
import tempfile
import threading
import uuid
import hashlib
import struct
from pathlib import Path
from urllib.parse import urlsplit, unquote

FILENAME = 'launcher.public.json'
FIELDS = {'schemaVersion','brand','accountProtocol','accountBaseUrl','websiteUrl','registerUrl','forgotUrl','contentUrl','realmId','realmName','adapterId','gameHost','gamePort','clientDirectory'}
OPTIONAL = {'updateBaseUrl','clientManifestUrl','clientArtifactPrefix','clientEdition'}
LOCK = threading.Lock()
DNF_SHA256 = '1f8244d3f7309bbe2fde4299e1863a894f6b28d5707bf01732980585b20b00dd'

def validate(value):
    required=FIELDS-{'registerUrl','forgotUrl'}
    if not isinstance(value,dict) or not required<=set(value) or set(value)-(FIELDS|OPTIONAL): raise ValueError('public fields')
    if type(value['schemaVersion']) is not int or value['schemaVersion']!=1 or value['accountProtocol']!='platform-v1' or value['adapterId']!='s4a21-cn-local-20261013': raise ValueError('version')
    for field in ('brand','realmName'):
        s=value[field]
        if not isinstance(s,str) or not s.strip() or len(s)>80 or any(ord(c)<32 or 127<=ord(c)<=159 for c in s): raise ValueError('label')
    if not isinstance(value['realmId'],str) or not re.fullmatch('[a-z0-9-]{1,32}',value['realmId']): raise ValueError('realm')
    host=value['gameHost']
    if not isinstance(host,str) or len(host)>253 or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',p) for p in host.split('.')): raise ValueError('host')
    if type(value['gamePort']) is not int or not 1<=value['gamePort']<=65535: raise ValueError('port')
    for field in ('accountBaseUrl','websiteUrl','registerUrl','forgotUrl','contentUrl','updateBaseUrl','clientManifestUrl','clientArtifactPrefix'):
        if field not in value or (field not in required and value[field] is None):continue
        s=value[field]
        if not isinstance(s,str) or len(s)>2048 or not s.startswith('https://') or any(ord(c)<=32 or ord(c)>=127 or c=='\\' for c in s): raise ValueError('https')
        u=urlsplit(s)
        if not u.hostname or u.username is not None or u.password is not None or '#' in s or '?' in s or (u.port is not None and not 1<=u.port<=65535): raise ValueError('url')
        if field in ('accountBaseUrl','updateBaseUrl') and u.path not in ('','/'): raise ValueError('origin')
        if field=='updateBaseUrl' and s.endswith('/'):raise ValueError('update origin must not end with slash')
    source=[value.get(k) for k in ('clientManifestUrl','clientArtifactPrefix','clientEdition')]
    present=sum(v is not None for v in source)
    if present not in (0,3):raise ValueError('client source fields must be configured together')
    if present:
        manifest,prefix,edition=source
        if not isinstance(edition,str) or not re.fullmatch(r'[A-Za-z0-9-]{1,80}',edition):raise ValueError('client edition')
        m,prefix_url=urlsplit(manifest),urlsplit(prefix)
        if m.path not in ('','/') and not m.path.endswith('.json'):raise ValueError('manifest path')
        if not prefix.endswith('/') or (m.scheme,m.hostname,m.port or 443)!=(prefix_url.scheme,prefix_url.hostname,prefix_url.port or 443):raise ValueError('client source origin')
        if any(unquote(segment) in ('.','..') for segment in prefix_url.path.split('/')):raise ValueError('noncanonical artifact prefix')
        host=prefix_url.hostname
        canonical_host='['+host+']' if ':' in host else host
        if prefix_url.port not in (None,443):canonical_host+=':'+str(prefix_url.port)
        if prefix!='https://'+canonical_host+prefix_url.path:raise ValueError('noncanonical artifact prefix')
    p=value['clientDirectory']
    if not isinstance(p,str) or (p!='.' and (not p or len(p.encode())>512 or any(c in '\\:*?"<>|' or ord(c)<32 or 127<=ord(c)<=159 for c in p) or any(c in ('','.','..') or c.endswith(('.',' ')) for c in p.split('/')))): raise ValueError('relative path')
    if len(json.dumps(value,ensure_ascii=False).encode())>16384: raise ValueError('size')
    return value

def distribution(body):
    if set(body)!={'directory','config'} or not isinstance(body['directory'],str): raise ValueError('install fields')
    value=validate(body['config'])
    root=Path(body['directory'])
    if not root.is_absolute(): raise ValueError('absolute destination required')
    root=root.resolve(strict=True)
    if not any((root/name).is_file() for name in ('MeowLauncher.exe','OOLauncher.exe','OO Launcher.exe')): raise ValueError('launcher missing')
    client=(root/value['clientDirectory']).resolve(strict=True)
    if not client.is_relative_to(root) or not (client/'DNF.exe').is_file(): raise ValueError('client missing')
    return root,client,value

def inspect_distribution(body):
    root,client,value=distribution(body)
    items=[]
    for name in ('DNF.exe','az.dll','ijl15.dll','GameGaurd.dll'):
        ok=False
        try:
            path=(client/name).resolve(strict=True)
            if not path.is_relative_to(client) or not path.is_file():raise ValueError()
            with path.open('rb') as f:
                head=f.read(64)
                offset=struct.unpack_from('<I',head,60)[0]
                if head[:2]!=b'MZ' or offset>1048576:raise ValueError()
                f.seek(offset);pe=f.read(6)
                ok=pe[:4]==b'PE\0\0' and pe[4:6]==b'\x4c\x01'
        except (OSError,ValueError,struct.error):pass
        items.append({'name':name,'ok':ok})
    digest=hashlib.sha256()
    exe=(client/'DNF.exe').resolve(strict=True)
    if not exe.is_relative_to(client) or exe.stat().st_size>268435456:raise ValueError('unsafe executable')
    with exe.open('rb') as f:
        for chunk in iter(lambda:f.read(65536),b''):digest.update(chunk)
    items.append({'name':'S4A21 客户端版本','ok':digest.hexdigest()==DNF_SHA256})
    for name in ('Script.pvf','ImagePacks2','SoundPacks'):
        ok=False
        try:
            path=(client/name).resolve(strict=True)
            ok=path.is_relative_to(client) and (path.is_file() and path.stat().st_size>0 if name=='Script.pvf' else path.is_dir())
        except OSError:pass
        items.append({'name':name,'ok':ok})
    return {'ready':all(item['ok'] for item in items),'items':items,'message':'这是基础文件与版本检查；启动器仍会完整检查插件和资源，真实入场需另行验证。'}

def install(body):
    root,client,value=distribution(body)
    if not inspect_distribution(body)['ready']:raise ValueError('client checks failed')
    raw=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
    with LOCK:
        target=root/FILENAME
        if target.is_symlink() or (target.exists() and not target.is_file()): raise ValueError('invalid target')
        backup=None
        if target.exists():
            if target.stat().st_size>16384: raise ValueError('existing config too large')
            backup=root/(FILENAME+'.'+uuid.uuid4().hex+'.bak')
            with backup.open('xb') as out:
                out.write(target.read_bytes());out.flush();os.fsync(out.fileno())
        fd,tmp=tempfile.mkstemp(prefix='.launcher-public-',suffix='.tmp',dir=root)
        try:
            with os.fdopen(fd,'wb') as out:
                out.write(raw);out.flush();os.fsync(out.fileno())
            os.replace(tmp,target)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    return {'ok':True,'path':str(target),'backup':str(backup) if backup else None,'message':'公开配置已安装。尚未制作压缩包，也未验证真实游戏入场。'}
