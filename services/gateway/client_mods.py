"""Client loader configuration; never loads DLLs or modifies host-owned manifests."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading

class ClientMods:
 def __init__(self,environment,bridge):
  self.environment=environment;self.bridge=bridge;self.lock=threading.RLock()
 def root(self):
  target=self.environment.read()
  if target['profile']!='115us' or target['mode']!='local' or not target['root']:raise ValueError('请先配置本地 115US 环境')
  value=self.bridge.settings()['clientDirectory']
  if not value:raise ValueError('请先保存 GM 客户端目录')
  path=Path(value)
  if not path.is_absolute():raise ValueError('客户端目录必须为绝对路径')
  self.safe(path)
  if not path.is_dir():raise ValueError('客户端目录不存在')
  return path.resolve(strict=True)
 @staticmethod
 def safe(path):
  for part in (path,*path.parents):
   if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise ValueError('客户端 MOD 路径不能包含链接')
 @classmethod
 def read_json(cls,path):
  cls.safe(path)
  if path.stat().st_size>1048576:raise ValueError('客户端 MOD 清单过大')
  raw=path.read_bytes()
  try:value=json.loads(raw.decode('utf-8-sig'))
  except (ValueError,UnicodeError):raise ValueError('客户端 MOD 清单无效，原文件保留') from None
  if not isinstance(value,dict) or not isinstance(value.get('plugins'),list):raise ValueError('客户端 MOD 清单缺少 plugins 数组')
  names=set()
  for row in value['plugins']:
   if not isinstance(row,dict) or not isinstance(row.get('name'),str) or not row['name'].strip() or len(row['name'])>128 or row['name'].casefold() in names:raise ValueError('客户端 MOD 名称无效或重复')
   names.add(row['name'].casefold())
   if 'enabled' in row and type(row['enabled']) is not bool:raise ValueError('客户端 MOD 启用状态无效')
   rel=row.get('path','')
   if not isinstance(rel,str) or not rel or len(rel)>1024:raise ValueError('客户端 MOD 文件路径无效')
   normalized=rel.replace(chr(92),'/')
   if normalized.startswith('/') or ':' in normalized or any(x in ('..','') for x in normalized.split('/')):raise ValueError('客户端 MOD 文件路径越界')
  return value,raw
 def list(self):
  with self.lock:
   root=self.root();switch=root/'mods/mods.json';host=root/'.115us-mods/plugins.json'
   self.safe(switch);self.safe(host)
   source=switch if switch.is_file() else host
   if not source.is_file():return {'clientDirectory':str(root),'source':'none','revision':'','mods':[],'message':'没有找到客户端 MOD 清单；不会自动创建加载器或执行 DLL。'}
   value,raw=self.read_json(source)
   writable=source==switch
   loader=False;bypass=True
   if host.is_file():
    try:
     manifest,_=self.read_json(host)
     rows=manifest['plugins']
     loaders=[x for x in rows if Path(x['path'].replace(chr(92),'/')).name.casefold()=='mod-loader.dll' and x.get('enabled',True)]
     dll=root/'.115us-mods/mod-loader.dll';self.safe(dll)
     loader=bool(loaders) and dll.is_file()
     bypass=manifest.get('autoDiscover',True) is not False or manifest.get('recurse',True) is not False or len(rows)!=1 or not loaders
    except ValueError:pass
   items=[]
   for row in value['plugins']:
    rel=row['path'].replace(chr(92),'/')
    path=(root/rel) if writable else (root/'.115us-mods'/rel)
    self.safe(path)
    legacy=writable and rel.casefold().startswith('.115us-mods/')
    if legacy:path=root/rel;self.safe(path)
    items.append({'id':row['name'],'path':row['path'],'enabled':row.get('enabled',True),'filePresent':path.is_file(),'reportedLive':None,'canToggle':writable,'bypassPossible':legacy and bypass})
   note='仅保存下次启动配置，实际加载状态未知。'
   if not writable:note+=' 宿主 plugins.json 由 modkit 管理，此处只读。'
   if writable and not loader:note+=' 未确认统一 mod-loader 可用，开关可能不生效。'
   if writable and bypass:note+=' 宿主仍可能直接加载旧插件，旧目录开关可能被绕过。'
   return {'clientDirectory':str(root),'source':'mods/mods.json' if writable else '.115us-mods/plugins.json','revision':hashlib.sha256(raw).hexdigest(),'mods':items,'loaderAvailable':loader,'message':note}
 def set_enabled(self,body):
  if not isinstance(body,dict) or set(body)!={'id','enabled','clientDirectory','revision'} or not isinstance(body['id'],str) or type(body['enabled']) is not bool:raise ValueError('客户端 MOD 开关参数无效')
  with self.lock:
   current=self.list()
   if current['clientDirectory']!=body['clientDirectory'] or current['revision']!=body['revision']:raise ValueError('客户端或清单已改变，请刷新后操作')
   if current['source']!='mods/mods.json':raise ValueError('宿主清单只读，请配置统一加载器清单')
   path=Path(current['clientDirectory'])/'mods/mods.json';value,raw=self.read_json(path)
   if hashlib.sha256(raw).hexdigest()!=body['revision']:raise ValueError('清单已改变，请刷新后操作')
   rows=[x for x in value['plugins'] if x['name']==body['id']]
   if len(rows)!=1:raise ValueError('目标客户端 MOD 不在清单中')
   rows[0]['enabled']=body['enabled']
   backup=path.with_name('mods.json.before-meowgm-'+secrets.token_hex(8))
   with backup.open('xb') as out:out.write(raw)
   temporary=path.with_name('mods.json.meowgm-'+secrets.token_hex(8)+'.tmp')
   try:
    with temporary.open('x',encoding='utf-8') as out:json.dump(value,out,ensure_ascii=False,indent=2)
    if self.root()!=path.parent.parent or path.read_bytes()!=raw:raise ValueError('客户端或清单已改变，已停止写入')
    self.safe(path);os.replace(temporary,path)
   finally:
    if temporary.exists():temporary.unlink()
   return self.list()
