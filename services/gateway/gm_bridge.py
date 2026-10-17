"""Explicit, environment-bound local gmtool pipe. No game process is launched."""
import json
import hashlib
import base64
import binascii
import struct
import os
from pathlib import Path
import queue
import re
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime,timezone
from read115 import Read115
from gm_resources import resources
from native_ids import native_id_from_request,native_id_to_wire,response_ids_to_wire

READ_METHODS={'prepare','overview','characters','character','filters','history','metadata','inventory.status','character.options','quests.mainline.preview','quests.prerequisites.preview','items','item','item.icon','item.detail','materials','quests','appearance.preview','appearance.share','appearance.share.apply','rules.meta','rules.get','rules.catalog','rules.detail','rules.preview','rules.impact','rules.selfcheck','rules.caps','patch.liveStatus'}
WRITE_METHODS={'character.edit','grant','equipment.send','equipment.send.batch','manage','rules.save','rules.reset','rules.blank','rules.import','rules.export'}
# Memory patch/DLL controls require a separate implementation and verification.

class GMBridge:
 def __init__(self,environment,data,tool=None,startup_timeout=1200,request_timeout=40):
  self.environment=environment;self.data=Path(data);self.settings_path=self.data/'gm-settings.json'
  self.pending_path=self.data/'gm-pending-points.json'
  self.tool=list(tool) if tool else [str(Path(sys._MEIPASS)/'tools/meowgm-gmtool.exe' if getattr(sys,'frozen',False) else Path('C:/dev-toolchain/tmp/meowgm-gmtool.exe'))]
  self.startup_timeout=startup_timeout;self.request_timeout=request_timeout
  self.lock=threading.RLock();self.rpc_lock=threading.Lock();self.process=None;self.responses=None
  self.generation=0;self.state='disconnected';self.message='GM 管道未连接';self.progress=[];self.connection_id='';self.target=None;self.backup=None;self.checksum=None
  self.resource_warnings=[]
 def settings(self):
  if not self.settings_path.exists():return {'clientDirectory':''}
  value=json.loads(self.settings_path.read_text(encoding='utf-8'))
  if not isinstance(value,dict) or set(value)!={'clientDirectory'} or not isinstance(value['clientDirectory'],str):raise ValueError('GM 客户端配置无效')
  return value
 def save(self,body):
  if not isinstance(body,dict) or set(body)!={'clientDirectory'} or not isinstance(body['clientDirectory'],str) or len(body['clientDirectory'])>2048:raise ValueError('请填写客户端目录')
  client=body['clientDirectory'].strip()
  if client and not Path(client).is_absolute():raise ValueError('客户端目录必须为绝对路径')
  with self.lock:
   if self.rpc_lock.locked():raise ValueError('GM 操作进行中，请完成后再修改客户端目录')
   self.close()
   self.data.mkdir(parents=True,exist_ok=True)
   temporary=self.settings_path.with_suffix('.tmp');temporary.write_text(json.dumps({'clientDirectory':client},ensure_ascii=False),encoding='utf-8');os.replace(temporary,self.settings_path)
  return self.status()
 def signature(self):return json.dumps([self.environment.read(),self.settings()],sort_keys=True,ensure_ascii=False)
 def pending(self):
  if not self.pending_path.exists():return None
  try:
   value=json.loads(self.pending_path.read_text(encoding='utf-8'))
   if not isinstance(value,dict) or set(value)!={'context','checksum','body'} or not isinstance(value['body'],dict):raise ValueError()
   value['body']={**value['body'],'account':native_id_to_wire(value['body']['account']),'character':native_id_to_wire(value['body']['character'])}
   return value
  except (ValueError,OSError,KeyError):raise ValueError('待核对流水记录不可读取，原文件保留；请人工核对后再修改技能点') from None
 def status(self):
  with self.lock:
   if self.state=='ready' and (not self.process or self.process.poll() is not None):self.state='failed';self.message='GM 组件已退出，请重新连接'
   if self.state=='ready' and self.target!=self.signature():self.state='stale';self.message='管理环境已改变，请断开并重新连接 GM'
   return {**self.settings(),'state':self.state,'message':self.message,'progress':list(self.progress),'resourceWarnings':list(self.resource_warnings),'resources':resources(self.environment,self.settings()['clientDirectory']),'connectionId':self.connection_id if self.state=='ready' else None,'contextId':hashlib.sha256((self.target or '').encode()).hexdigest() if self.state=='ready' else None,'pending':self.pending(),'backup':str(self.backup) if self.backup else None,'pvfChecksum':self.checksum,'localDatabase':True,'gameRunning':None,'memoryPatchSupported':False}
 def preview(self,body):
  if not isinstance(body,dict) or set(body)!={'connectionId','id'} or type(body['id']) is not int or not 0<body['id']<=4294967295:raise ValueError('请选择有效的物品 ID')
  item=self.call({'connectionId':body['connectionId'],'method':'item','query':{'id':[str(body['id'])]}})
  output={'id':body['id'],'item':item.get('item',{}),'imageState':'unavailable','message':'该物品图像未成功解码'}
  try:
   icon=self.call({'connectionId':body['connectionId'],'method':'item.icon','query':{'id':[str(body['id'])]}})
   png=icon.get('png')
   if not isinstance(png,str) or len(png)>2796204:raise ValueError('图像超过预览限制')
   raw=base64.b64decode(png,validate=True)
   if not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw)<33 or raw[12:16]!=b'IHDR' or len(raw)>2097152:raise ValueError('原生图像格式无效')
   width,height=struct.unpack('>II',raw[16:24])
   if not 0<width<=2048 or not 0<height<=2048:raise ValueError('图像尺寸超过预览限制')
   output.update(png=png,imageState='decoded',message='已只读解码此物品图像；不代表所有物品均可预览')
  except (ValueError,binascii.Error) as e:output['message']='图像不可用：'+str(e)[:500]
  return output
 def close(self):
  with self.lock:
   self.generation+=1;process=self.process;self.process=None;self.responses=None;self.connection_id='';self.target=None;self.state='disconnected';self.message='GM 管道未连接';self.checksum=None
   self.resource_warnings=[];self.progress=[]
  if process:
   try:
    process.kill();process.wait(timeout=4)
   except (OSError,subprocess.TimeoutExpired):pass
   for stream in (process.stdin,process.stdout,process.stderr):
    try:stream.close()
    except (OSError,AttributeError):pass
 def connect(self,body):
  with self.lock:return self._connect(body)
 def _connect(self,body):
  if body!={}:raise ValueError('GM 连接参数无效，请先保存配置')
  with self.lock:
   if self.state in ('preparing','ready'):return self.status()
  self.close()
  config=self.environment.read();settings=self.settings()
  if config['profile']!='115us' or config['mode']!='local' or not config['root']:raise ValueError('请先配置本地 115US 环境，云端 GM 协议尚未接入')
  root=Path(config['root'])
  if not root.is_absolute() or root.is_symlink() or getattr(root,'is_junction',lambda:False)():raise ValueError('请选择真实的本地 115US 目录')
  root=root.resolve(strict=True);client=Path(settings['clientDirectory'])
  module=root/'server/work/dfo-lan/go.mod'
  if not module.is_file() or module.is_symlink() or not module.resolve().is_relative_to(root) or not re.search(r'(?m)^module\s+dfolan\s*$',module.read_text(encoding='utf-8')):raise ValueError('所选目录不是受支持的 115US 服务端模块')
  if not client.is_absolute() or not client.is_dir() or client.is_symlink() or getattr(client,'is_junction',lambda:False)():raise ValueError('请选择实际的 115US 客户端目录')
  pvf=client/'Script.pvf'
  if not pvf.is_file() or pvf.is_symlink() or not pvf.resolve().is_relative_to(client.resolve()) or pvf.stat().st_size<16:raise ValueError('客户端目录缺少有效的 Script.pvf')
  if not Path(self.tool[0]).is_file():raise ValueError('当前构建缺少 gmtool 组件')
  # Validate the existing SQLite path/schema without creating or migrating it.
  with Read115(self.environment).database():pass
  with self.lock:
   self.state='preparing';self.message='正在备份已有存档并准备客户端资源';self.progress=[];self.resource_warnings=[];self.backup=None
   self.target=self.signature();generation=self.generation;target=self.target
  threading.Thread(target=self._open,args=(generation,target,root,client.resolve()),daemon=True).start()
  return self.status()
 def _open(self,generation,target,root,client):
  process=None
  try:
   directory=self.data/'backups'/('gm-connect-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+secrets.token_hex(4));directory.mkdir(parents=True,exist_ok=False)
   backup=directory/'save.sqlite3';deadline=time.monotonic()+60
   def progress(status,remaining,total):
    if time.monotonic()>deadline:raise ValueError('存档备份超时，未启动 GM')
   with Read115(self.environment).database() as source:
    destination=sqlite3.connect(backup)
    try:
     source.backup(destination,pages=256,progress=progress,sleep=.05)
     if destination.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('存档备份校验失败，未启动 GM')
    finally:destination.close()
   (directory/'backup.json').write_text(json.dumps({'createdAt':datetime.now(timezone.utc).isoformat(),'root':str(root),'clientDirectory':str(client),'backup':'save.sqlite3','quickCheck':'ok'},ensure_ascii=False,indent=2),encoding='utf-8')
   with self.lock:
    if generation!=self.generation:return
    if target!=self.signature():raise ValueError('环境在准备期间改变，已停止连接')
    self.backup=backup
   env={**os.environ,'LOCALAPPDATA':str(self.data/'cache'),'TEMP':str(self.data/'tmp'),'TMP':str(self.data/'tmp')}
   Path(env['LOCALAPPDATA']).mkdir(parents=True,exist_ok=True);Path(env['TEMP']).mkdir(parents=True,exist_ok=True)
   seeds=Path(sys._MEIPASS)/'tools/configs' if getattr(sys,'frozen',False) else Path(os.environ.get('MEOW_GM_SEEDS','upstream/115us-dfolauncher/gm/configs'))
   args=[*self.tool,'-stdio','-data-source','pvf','-root',str(root),'-operator','MeowGM','-client-dir',str(client),'-resource-seeds',str(seeds)]
   process=subprocess.Popen(args,cwd=root,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=0x08000000 if os.name=='nt' else 0)
   responses=queue.Queue(maxsize=8)
   def output():
    try:
     while True:
      line=process.stdout.readline(8388609)
      if not line:responses.put_nowait({'_bridge_transport_error':'GM 管道已关闭'});return
      if len(line)>8388608:raise ValueError('GM 返回内容超过限制')
      responses.put_nowait(json.loads(line))
    except Exception:
     try:responses.put_nowait({'_bridge_transport_error':'GM 管道响应异常'})
     except queue.Full:pass
   def diagnostics():
    try:
     for raw in iter(process.stderr.readline,b''):
      line=raw.decode('utf-8',errors='replace').strip()
      if 'GM_PROGRESS:' in line:line=line.split('GM_PROGRESS:',1)[1].strip()
      with self.lock:
       if generation==self.generation:
        self.progress=(self.progress+[line[:1000]])[-8:]
        if any(word in line for word in ('警告','缺少','不可用')):self.resource_warnings=(self.resource_warnings+[line[:1000]])[-24:]
    except (OSError,ValueError):pass
   with self.lock:
    if generation!=self.generation:process.kill();process.wait(timeout=4);return
    self.process=process;self.responses=responses
   threading.Thread(target=output,daemon=True).start();threading.Thread(target=diagnostics,daemon=True).start()
   greeting=responses.get(timeout=self.startup_timeout)
   if not isinstance(greeting,dict) or greeting.get('version')!=1 or greeting.get('ready') is not True or greeting.get('data_source')!='pvf' or not re.fullmatch('[0-9a-fA-F]{64}',greeting.get('pvf_checksum','')):raise ValueError('GM 管道版本或 PVF 身份不匹配')
   with self.lock:
    if generation!=self.generation:return
    if target!=self.signature():raise ValueError('环境在准备期间改变，已停止连接')
    self.state='ready';self.connection_id=secrets.token_urlsafe(24);self.checksum=greeting['pvf_checksum'];self.message='本地 GM 管道已连接；游戏进程状态未验证'
  except Exception as error:
   if process:
    try:process.kill();process.wait(timeout=4)
    except (OSError,subprocess.TimeoutExpired):pass
   with self.lock:
    if generation==self.generation:self.state='failed';self.message='GM 准备失败：'+('超时，请检查资源后重试' if isinstance(error,queue.Empty) else str(error))[:2000];self.connection_id=''
 def call(self,body):
  if not isinstance(body,dict) or set(body)-{'connectionId','method','query','body'}:raise ValueError('GM 请求字段无效')
  method=body.get('method')
  if not isinstance(method,str) or method not in READ_METHODS|WRITE_METHODS:raise ValueError('GM 方法未开放')
  query=body.get('query',{})
  if not isinstance(query,dict) or any(not isinstance(k,str) or not isinstance(v,list) or any(not isinstance(x,str) for x in v) for k,v in query.items()):raise ValueError('GM 查询格式无效')
  for key in {'character':('id',),'characters':('account',),'history':('account',)}.get(method,()):
   if key in query:
    if len(query[key])!=1:raise ValueError('native ID 查询只能有一个值')
    native_id_from_request(query[key][0])
  if isinstance(body.get('body'),dict):
   payload=dict(body['body'])
   for key in ('account','character'):
    if key in payload:payload[key]=native_id_from_request(payload[key])
   body={**body,'body':payload}
  request={k:body[k] for k in ('method','query','body') if k in body}
  raw=json.dumps(request,ensure_ascii=False).encode('utf-8')
  if len(raw)>1048576:raise ValueError('GM 请求过大')
  with self.rpc_lock:
   with self.lock:
    if self.status()['state']!='ready' or not self.connection_id or body.get('connectionId')!=self.connection_id:raise ValueError('GM 连接已失效，请重新连接')
    process=self.process;responses=self.responses;generation=self.generation
    points=method=='character.edit' and isinstance(body.get('body'),dict) and body['body'].get('action') in ('sp','tp')
    if points:
     edit=body['body']
     if set(edit)!={'id','account','character','action','value','reason'} or not isinstance(edit['id'],str) or not re.fullmatch(r'launcher-[A-Za-z0-9-]{7,91}',edit['id']) or any(type(edit[k]) is not int or edit[k]<=0 for k in ('account','character','value')) or edit['value']>65535 or not isinstance(edit['reason'],str) or not 1<=len(edit['reason'].strip())<=200:raise ValueError('技能点操作参数无效')
     record={'context':hashlib.sha256(self.target.encode()).hexdigest(),'checksum':self.checksum,'body':{**edit,'account':native_id_to_wire(edit['account']),'character':native_id_to_wire(edit['character'])}}
     prior=self.pending()
     if prior and prior!=record:raise ValueError('存在待核对技能点流水，请连接原环境并按原请求重试')
     if not prior:
      self.data.mkdir(parents=True,exist_ok=True)
      temporary=self.pending_path.with_suffix('.tmp');temporary.write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8');os.replace(temporary,self.pending_path)
   try:
    process.stdin.write(raw+b'\n');process.stdin.flush();result=responses.get(timeout=self.request_timeout)
    if not isinstance(result,dict):raise ValueError('GM 返回格式无效')
    if '_bridge_transport_error' in result:
     self.close();raise ValueError('GM 通道断开，操作结果未知；请保留流水号并查询回执')
    if 'error' in result:raise ValueError(str(result['error'])[:4000])
    if points and result.get('ok') is True and result.get('grant_id')==body['body']['id']:
     self.pending_path.unlink()
    return response_ids_to_wire(method,result)
   except queue.Empty:
    self.close();raise ValueError('GM 操作超时，结果未知；保留原流水号并重新查询，避免重复发放') from None
   except (OSError,BrokenPipeError):
    self.close();raise ValueError('GM 通道断开，结果未知；请先查询操作回执') from None
