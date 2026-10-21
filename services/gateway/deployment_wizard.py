"""Offline 115US preflight. Evidence is inventory, never a deployment receipt."""
import base64
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

class DeploymentWizard:
 def __init__(self,trusted_keys=None,trust_store=None):
  self.trusted_keys=dict(trusted_keys or {});self.trust_store=Path(trust_store) if trust_store is not None else None
 def verification_key(self,keyid,realm):
  if not isinstance(keyid,str):raise ValueError('连接描述签名 keyId 无效')
  if self.trust_store is None:
   if keyid not in self.trusted_keys:raise ValueError('连接描述签名公钥尚未由 GM 信任库固定')
   return self.trusted_keys[keyid]
  self.safe(self.trust_store)
  if not self.trust_store.is_file():raise ValueError('GM 部署公钥信任库尚未配置')
  if self.trust_store.stat().st_size>65536:raise ValueError('GM 部署公钥信任库过大')
  store=self.read(self.trust_store)
  if not isinstance(store,dict) or set(store)!={'schema','keys'} or store['schema']!='meow-gm-deployment-trust-v1' or not isinstance(store['keys'],list) or len(store['keys'])>32:raise ValueError('GM 部署公钥信任库结构无效')
  names=set();selected=None
  for row in store['keys']:
   if not isinstance(row,dict) or set(row)!={'keyId','publicKey','realms','notBefore','notAfter','revoked'}:raise ValueError('GM 部署公钥条目无效')
   name=row['keyId']
   if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,80}',name) or name in names:raise ValueError('GM 部署公钥标识无效或重复')
   names.add(name)
   if not isinstance(row['realms'],list) or not row['realms'] or len(row['realms'])>64 or any(not isinstance(x,str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,80}',x) for x in row['realms']):raise ValueError('GM 部署公钥区服范围无效')
   if type(row['revoked']) is not bool or type(row['notBefore']) is not int or type(row['notAfter']) is not int or not 0<=row['notBefore']<row['notAfter']<=253402300799:raise ValueError('GM 部署公钥有效期无效')
   try:
    if not isinstance(row['publicKey'],str):raise ValueError()
    key=base64.b64decode(row['publicKey'],validate=True)
    if len(key)!=32:raise ValueError()
   except (ValueError,TypeError):raise ValueError('GM 部署公钥必须为 32 字节 Ed25519 公钥') from None
   if name==keyid:selected=(row,key)
  if selected is None:raise ValueError('连接描述签名公钥未登记')
  row,key=selected;now=int(time.time())
  if row['revoked']:raise ValueError('连接描述签名公钥已撤销')
  if not row['notBefore']<=now<row['notAfter']:raise ValueError('连接描述签名公钥不在有效期内')
  if realm not in row['realms']:raise ValueError('连接描述签名公钥不允许此区服')
  return key
 @staticmethod
 def safe(path):
  for item in (path,*path.parents):
   if item.is_symlink() or getattr(item,'is_junction',lambda:False)():raise ValueError('预检路径不能包含链接')
 @classmethod
 def read(cls,path):
  cls.safe(path)
  if path.stat().st_size>1048576:raise ValueError('预检文件过大')
  try:return json.loads(path.read_text(encoding='utf-8-sig'))
  except (ValueError,UnicodeError):raise ValueError('预检 JSON 无效') from None
 @staticmethod
 def descriptor(value):
  if not isinstance(value,dict) or set(value)!={'schema','realm','host','port','admissionOrigin','adapterVersion'} or value['schema']!='meow-player-connection-draft-v1':raise ValueError('公开连接描述字段无效')
  if not isinstance(value['realm'],str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,80}',value['realm']):raise ValueError('区服标识无效')
  if not isinstance(value['host'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}',value['host']):raise ValueError('游戏主机无效')
  if type(value['port']) is not int or not 1<=value['port']<=65535:raise ValueError('游戏端口无效')
  if not isinstance(value['adapterVersion'],str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,80}',value['adapterVersion']):raise ValueError('adapter 版本无效')
  origin=value['admissionOrigin']
  if not isinstance(origin,str) or len(origin)>2048 or any(ord(c)<=32 or ord(c)>=127 or c==chr(92) for c in origin):raise ValueError('准入地址无效')
  try:
   url=urlsplit(origin)
   if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment or '?' in origin or '#' in origin or url.path not in ('','/') or url.port==0:raise ValueError()
  except ValueError:raise ValueError('准入地址必须为无凭据的 HTTPS 源地址') from None
  return dict(value)
 def signature(self,envelope,descriptor):
  if not isinstance(envelope,dict) or set(envelope)!={'keyId','algorithm','signature','descriptor'} or envelope['algorithm']!='Ed25519' or envelope['descriptor']!=descriptor:raise ValueError('连接描述签名封装无效')
  keyid=envelope['keyId']
  public_key=self.verification_key(keyid,descriptor['realm'])
  try:
   signature=base64.b64decode(envelope['signature'],validate=True)
   Ed25519PublicKey.from_public_bytes(public_key).verify(signature,json.dumps(descriptor,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8'))
  except Exception:raise ValueError('连接描述签名验证失败') from None
  return envelope
 def inspect(self,body):
  if not isinstance(body,dict) or set(body)!={'directory'} or not isinstance(body['directory'],str) or not Path(body['directory']).is_absolute():raise ValueError('请选择预检包绝对目录')
  root=Path(body['directory']);self.safe(root);root=root.resolve(strict=True)
  manifest=self.read(root/'gm-deployment.evidence.json')
  if not isinstance(manifest,dict) or set(manifest)!={'schema','components','connection'} or manifest['schema']!='meow-gm-preflight-v1':raise ValueError('部署证据清单字段无效')
  components=manifest['components']
  if not isinstance(components,dict) or set(components)!={'server','gateway','adapter'}:raise ValueError('需要分别提供 server、gateway、adapter 证据')
  checks=[]
  for role,row in components.items():
   if not isinstance(row,dict) or set(row)!={'path','version','sha256','protocol'}:raise ValueError('组件证据字段无效')
   if not isinstance(row['version'],str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,80}',row['version']):raise ValueError('组件版本无效')
   if not isinstance(row['protocol'],str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,80}',row['protocol']):raise ValueError('组件协议标识无效')
   if not isinstance(row['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',row['sha256']):raise ValueError('组件指纹无效')
   rel=row['path']
   if not isinstance(rel,str) or not rel or len(rel)>512 or chr(92) in rel or ':' in rel or any(x in ('','..','.') for x in rel.split('/')):raise ValueError('组件路径越界')
   path=root/rel;self.safe(path)
   if not path.resolve().is_relative_to(root):raise ValueError('组件路径越界')
   if not path.is_file() or path.stat().st_size>536870912:raise ValueError('组件缺失或超过预检上限')
   digest=hashlib.sha256()
   with path.open('rb') as source:
    for chunk in iter(lambda:source.read(1048576),b''):digest.update(chunk)
   checks.append({'role':role,'path':rel,'version':row['version'],'protocol':row['protocol'],'sha256':digest.hexdigest(),'hashMatches':digest.hexdigest()==row['sha256']})
  public=self.descriptor(manifest['connection'])
  versions_match=public['adapterVersion']==components['adapter']['version']
  protocols_match=len({row['protocol'] for row in components.values()})==1
  signed=None;signature_status='missing'
  envelope=root/'player-connection.signed.json'
  self.safe(envelope)
  if envelope.exists():signed=self.signature(self.read(envelope),public);signature_status='verified'
  blockers=[]
  if not all(x['hashMatches'] for x in checks):blockers.append('组件文件指纹不匹配')
  if not versions_match:blockers.append('公开描述与 adapter 版本不一致')
  if not protocols_match:blockers.append('server/gateway/adapter 声明的协议不一致')
  if not signed:blockers.append('没有经固定公钥验证的连接描述；仅生成未签名草稿')
  # No native ABI is enabled until host/authority publish their frozen contract and receipts.
  blockers.append('115US 原生握手承载、host proof 与绑定消费合同及实测证据尚未登记')
  return {'schema':'meow-gm-deployment-plan-v1','dryRun':True,'supported':False,'executed':False,'components':checks,'declaredProtocolsMatch':protocols_match,'adapterVersionMatches':versions_match,'blockers':blockers,'privateConfigTemplate':{'schema':'meow-owner-config-template-v1','credentialStorage':'GM protected local store; fill credentials outside player distribution','databaseSecretRef':None,'sshCredentialRef':None,'signingKeyRef':None},'playerConnectionDraft':public,'signedPlayerConnection':signed,'signatureStatus':signature_status,'plan':[{'step':'preserve','action':'记录现有服务单元、二进制指纹和配置；由 owner 做一致性存档备份'},{'step':'verify','action':'由 host/账号 owner 核实握手、证书、公钥与版本能力证据'},{'step':'apply','action':'未支持；不执行 SSH、安装、签发证书或数据库操作'},{'step':'rollback','action':'失败时由 owner 回退原程序/单元及私有配置；不自动覆盖玩家库'}],'rollback':{'automatic':False,'restorePlayerDatabase':False,'requiredArtifacts':['previous-unit','previous-binary-sha256','protected-config-backup','consistent-save-backup-receipt']}}
