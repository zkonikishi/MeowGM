"""GM-side MeowScope contract projection; no host management authority exists yet."""
import json
import re

class DeveloperControl:
 protocol='meowscope-devtest-control-v1'
 path='/mods/dev.meowscope/devtest'
 @classmethod
 def capabilities(cls):
  return {'protocol':cls.protocol,'path':cls.path,'source':'local-contract-only','productionAvailable':False,'capabilityReason':'host_management_session_rbac_unavailable','readOperations':['list','status','report'],'writeOperations':['enable','start','cancel'],'remoteProbed':False,'executionEnabled':False}
 @staticmethod
 def validate(body):
  if not isinstance(body,dict) or not isinstance(body.get('op'),str):raise ValueError('invalid_request')
  try:
   if len(json.dumps(body,ensure_ascii=False,allow_nan=False).encode())>4096:raise ValueError()
  except (ValueError,TypeError):raise ValueError('invalid_request') from None
  op=body['op']
  if op=='list':valid=set(body)=={'op'}
  elif op=='enable':valid=set(body)=={'op','enabled'} and type(body['enabled']) is bool
  elif op=='start':
   valid=set(body)=={'op','scenario','concurrency','rate','calls','duration_ms'} and isinstance(body['scenario'],str) and re.fullmatch('[a-z][a-z0-9_.-]{0,63}',body['scenario']) is not None
   valid=bool(valid) and all(type(body[k]) is int and 1<=body[k]<=limit for k,limit in [('concurrency',4),('rate',100),('calls',1000),('duration_ms',30000)])
  elif op in ('status','report','cancel'):
   valid=set(body)<= {'op','run_id'} and (op=='status' and 'run_id' not in body or isinstance(body.get('run_id'),str) and re.fullmatch('[a-zA-Z0-9_-]{1,64}',body['run_id']) is not None)
  else:valid=False
  if not valid:raise ValueError('invalid_request')
  return dict(body)
 @classmethod
 def request(cls,body):
  cls.validate(body)
  # No localhost cookie, SSH connection or shared localgm token grants host RBAC.
  return {'ok':False,'code':'management_session_unavailable','enabled':False}
