import sqlite3
import tempfile
import unittest
from pathlib import Path
from server import Store

class AdminNameTests(unittest.TestCase):
    def test_custom_name_login_and_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'admin.db')
            store.initialize('fixture-password-123','owner_21')
            self.assertTrue(store.verify('fixture-password-123','owner_21'))
            self.assertFalse(store.verify('fixture-password-123','admin'))
            self.assertFalse(store.verify('wrong-password','owner_21'))
            with self.assertRaises(sqlite3.IntegrityError):store.initialize('fixture-password-123','another')
            store.publish(store.read())
            self.assertEqual(store.audit()[0]['actor'],'owner_21')
            self.assertEqual(store.admin_name(),'owner_21')
