import unittest
from developer_control import DeveloperControl

class DeveloperControlTests(unittest.TestCase):
 def test_capabilities_do_not_claim_remote_or_execution(self):
  c=DeveloperControl.capabilities();self.assertFalse(c['productionAvailable']);self.assertFalse(c['remoteProbed']);self.assertFalse(c['executionEnabled'])
  self.assertEqual(c['path'],'/mods/dev.meowscope/devtest')
 def test_all_valid_operations_fail_closed_without_management_session(self):
  for body in [{'op':'list'},{'op':'status'},{'op':'report','run_id':'fixture'},{'op':'cancel','run_id':'fixture'},{'op':'enable','enabled':True},{'op':'start','scenario':'fixture','concurrency':1,'rate':1,'calls':1,'duration_ms':1}]:
   with self.subTest(body=body):self.assertEqual(DeveloperControl.request(body),{'ok':False,'code':'management_session_unavailable','enabled':False})
 def test_caller_authority_or_arbitrary_target_rejected(self):
  for field in ['actor','owner','uid','role','url','host','target','script','shell','sql','token']:
   with self.subTest(field=field),self.assertRaises(ValueError):DeveloperControl.request({'op':'list',field:'fixture'})
 def test_budget_types_and_limits(self):
  body={'op':'start','scenario':'fixture','concurrency':1,'rate':1,'calls':1,'duration_ms':1}
  for field,value in [('concurrency',True),('concurrency',5),('rate',101),('calls',1001),('duration_ms',30001),('calls',0),('scenario','../escape')]:
   with self.subTest(field=field,value=value),self.assertRaises(ValueError):DeveloperControl.request({**body,field:value})
 def test_run_id_and_boolean_validation(self):
  for body in [{'op':'cancel'},{'op':'report','run_id':'../bad'},{'op':'enable','enabled':1},{'op':'status','actor':'fixture'},{'op':'Status'}]:
   with self.subTest(body=body),self.assertRaises(ValueError):DeveloperControl.request(body)
