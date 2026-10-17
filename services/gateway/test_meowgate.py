import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class MeowGateEntryTests(unittest.TestCase):
    def test_preflight_rejects_missing_configuration_without_creating_data(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'new-data'
            env=dict(os.environ)
            for key in ['OO_PLATFORM_URL','OO_PLATFORM_GATEWAY_KEY','OO_GAME_KEY']:env.pop(key,None)
            env['OO_ADMISSION_DATA']=str(target)
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('MeowGate.py')),'--check'],env=env,capture_output=True,text=True)
            self.assertEqual(r.returncode,2);self.assertIn('Missing required',r.stdout);self.assertFalse(target.exists())
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('MeowGate.py')),'--help'],env=env,capture_output=True,text=True)
            self.assertEqual(r.returncode,0);self.assertIn('MeowGate',r.stdout);self.assertFalse(target.exists())
