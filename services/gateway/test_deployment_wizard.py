import base64
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from deployment_wizard import DeploymentWizard

class DeploymentWizardTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.components={}
  for role in ['server','gateway','adapter']:
   raw=('synthetic '+role).encode();(self.root/(role+'.bin')).write_bytes(raw)
   self.components[role]={'path':role+'.bin','version':'fixture-1','protocol':'unapproved-fixture','sha256':hashlib.sha256(raw).hexdigest()}
  self.public={'schema':'meow-player-connection-draft-v1','realm':'fixture','host':'game.invalid','port':27001,'admissionOrigin':'https://account.invalid','adapterVersion':'fixture-1'}
  self.manifest={'schema':'meow-gm-preflight-v1','components':self.components,'connection':self.public}
  self.path=self.root/'gm-deployment.evidence.json';self.write();self.wizard=DeploymentWizard()
 def write(self):self.path.write_text(json.dumps(self.manifest),encoding='utf-8')
 def inspect(self):return self.wizard.inspect({'directory':str(self.root)})
 def test_preflight_is_readonly_never_claims_support_or_execution(self):
  before={p.name:p.read_bytes() for p in self.root.iterdir()};result=self.inspect()
  self.assertFalse(result['supported']);self.assertFalse(result['executed']);self.assertTrue(result['dryRun'])
  self.assertTrue(all(x['hashMatches'] for x in result['components']))
  self.assertIsNone(result['signedPlayerConnection']);self.assertFalse(result['rollback']['restorePlayerDatabase'])
  self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()})
 def test_hash_protocol_and_version_mismatch_are_blockers(self):
  (self.root/'server.bin').write_bytes(b'tampered');self.components['gateway']['protocol']='different';self.public['adapterVersion']='different';self.write()
  result=self.inspect();self.assertFalse(result['components'][0]['hashMatches']);self.assertFalse(result['declaredProtocolsMatch']);self.assertFalse(result['adapterVersionMatches']);self.assertGreaterEqual(len(result['blockers']),4)
 def test_private_fields_rejected_in_public_description(self):
  for key in ['databasePassword','sshPrivateKey','ticket','token','uid','signingPrivateKey']:
   with self.subTest(key=key),self.assertRaises(ValueError):self.wizard.descriptor({**self.public,key:'fixture-secret'})
 def test_urls_never_carry_credentials_or_ticket(self):
  for url in ['http://account.invalid','https://user:pass@account.invalid','https://account.invalid/?ticket=fixture','https://account.invalid/#fixture']:
   with self.subTest(url=url),self.assertRaises(ValueError):self.wizard.descriptor({**self.public,'admissionOrigin':url})
 def test_path_escape_missing_component_and_unknown_fields(self):
  self.components['server']['path']='../server.bin';self.write()
  with self.assertRaises(ValueError):self.inspect()
  self.components['server']['path']='missing.bin';self.write()
  with self.assertRaises(ValueError):self.inspect()
  self.components['server']['path']='server.bin';self.manifest['password']='fixture';self.write()
  with self.assertRaises(ValueError):self.inspect()
 def test_signature_requires_pinned_key_and_does_not_imply_native_support(self):
  key=Ed25519PrivateKey.generate();raw=json.dumps(self.public,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
  envelope={'keyId':'fixture-key','algorithm':'Ed25519','descriptor':self.public,'signature':base64.b64encode(key.sign(raw)).decode()}
  signature=self.root/'player-connection.signed.json';signature.write_text(json.dumps(envelope))
  with self.assertRaises(ValueError):self.inspect()
  self.wizard=DeploymentWizard({'fixture-key':key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)})
  result=self.inspect();self.assertEqual(result['signatureStatus'],'verified');self.assertFalse(result['supported'])
  envelope['signature']=base64.b64encode(b'wrong').decode();signature.write_text(json.dumps(envelope))
  with self.assertRaises(ValueError):self.inspect()
 def test_symlink_component_rejected(self):
  link=self.root/'alias.bin'
  try:link.symlink_to(self.root/'server.bin')
  except OSError:self.skipTest('symlink unavailable')
  self.components['server']['path']='alias.bin';self.write()
  with self.assertRaises(ValueError):self.inspect()

class DeploymentTrustStoreTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.key=Ed25519PrivateKey.generate();now=int(time.time())
  self.row={'keyId':'fixture-key','publicKey':base64.b64encode(self.key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode(),'realms':['fixture'],'notBefore':now-10,'notAfter':now+300,'revoked':False}
  self.path=self.root/'gm-deployment-trust.json';self.save()
  self.wizard=DeploymentWizard(trust_store=self.path)
  self.public={'schema':'meow-player-connection-draft-v1','realm':'fixture','host':'game.invalid','port':27001,'admissionOrigin':'https://account.invalid','adapterVersion':'fixture-1'}
  raw=json.dumps(self.public,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
  self.envelope={'keyId':'fixture-key','algorithm':'Ed25519','descriptor':self.public,'signature':base64.b64encode(self.key.sign(raw)).decode()}
 def save(self):self.path.write_text(json.dumps({'schema':'meow-gm-deployment-trust-v1','keys':[self.row]}))
 def verify(self):return self.wizard.signature(self.envelope,self.public)
 def test_pinned_public_key_and_immediate_revocation_reload(self):
  self.assertEqual(self.verify(),self.envelope)
  self.row['revoked']=True;self.save()
  with self.assertRaisesRegex(ValueError,'撤销'):self.verify()
 def test_realm_and_time_constraints(self):
  self.row['realms']=['another'];self.save()
  with self.assertRaises(ValueError):self.verify()
  self.row['realms']=['fixture'];self.row['notAfter']=int(time.time())-1;self.row['notBefore']=0;self.save()
  with self.assertRaises(ValueError):self.verify()
  self.row['notBefore']=int(time.time())+10;self.row['notAfter']=int(time.time())+20;self.save()
  with self.assertRaises(ValueError):self.verify()
 def test_missing_malformed_store_and_private_key_fields_fail_closed(self):
  self.path.unlink()
  with self.assertRaises(ValueError):self.verify()
  self.path.write_text('{bad')
  with self.assertRaises(ValueError):self.verify()
  self.row['privateKey']='must never be accepted';self.save()
  with self.assertRaises(ValueError):self.verify()
 def test_duplicate_key_unknown_signer_and_wrong_key_rejected(self):
  self.path.write_text(json.dumps({'schema':'meow-gm-deployment-trust-v1','keys':[self.row,self.row]}))
  with self.assertRaises(ValueError):self.verify()
  self.save();self.envelope['keyId']='other'
  with self.assertRaises(ValueError):self.verify()
  self.envelope['keyId']='fixture-key';self.row['publicKey']=base64.b64encode(b'x'*32).decode();self.save()
  with self.assertRaises(ValueError):self.verify()
 def test_symlink_store_rejected(self):
  link=self.root/'linked.json'
  try:link.symlink_to(self.path)
  except OSError:self.skipTest('symlink unavailable')
  with self.assertRaises(ValueError):DeploymentWizard(trust_store=link).signature(self.envelope,self.public)
