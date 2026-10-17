from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from fixture_control import FixtureControl

class FixtureControlTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.control=FixtureControl(Path(self.temp.name),enabled=True);self.addCleanup(self.control.close)
 def test_disabled_control_never_launches(self):
  self.control.enabled=False
  with self.assertRaises(ValueError):self.control.start({})
  self.assertIsNone(self.control.process)
 def test_owned_worker_health_stop_and_ordered_logs(self):
  self.assertFalse(self.control.status()['healthy'])
  state=self.control.start({});self.assertTrue(state['healthy']);self.assertEqual(state['scope'],'synthetic-only')
  process=self.control.process
  self.control.start({});self.assertIs(self.control.process,process)
  self.assertTrue(self.control.logs()['items'])
  cursor=self.control.logs()['cursor'];self.assertFalse(self.control.logs(cursor)['items'])
  self.assertFalse(self.control.stop({})['running']);self.assertIsNotNone(process.poll())
  lines=self.control.logs(cursor)['items'];self.assertTrue(lines)
  self.assertEqual([x['seq'] for x in lines],sorted({x['seq'] for x in lines}))
 def test_pid_command_and_root_injection_rejected_and_unrelated_process_survives(self):
  other=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],stdin=subprocess.DEVNULL)
  self.addCleanup(lambda:other.poll() is None and other.kill())
  self.control.start({})
  for params in [{'pid':other.pid},{'command':['whoami']},{'root':'/production'}]:
   with self.assertRaises(ValueError):self.control.start(params)
   with self.assertRaises(ValueError):self.control.stop(params)
  self.control.stop({});self.assertIsNone(other.poll())
  other.kill();other.wait(timeout=3)
 def test_stale_heartbeat_does_not_claim_health_and_log_ring_is_bounded(self):
  self.control.start({})
  with self.control.lock:
   self.control.last_heartbeat=time.monotonic()-30
   self.assertFalse(self.control.status()['healthy'])
   for i in range(230):self.control.log('synthetic event')
  result=self.control.logs(0);self.assertTrue(result['truncated']);self.assertEqual(len(result['items']),200)
