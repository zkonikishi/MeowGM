import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from meowpay_simulation import Catalog,CatalogError,CatalogConflict

class SimulationCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.catalog=Catalog(self.root)
        self.body={'revision':1,'pointsPerMinor':10,'monthlyMinor':1000,'yearlyMinor':9900,'blackDiamondEnabled':True}
    def test_persists_revision_calendar_terms_and_actor_audit(self):
        r=self.catalog.write(self.body,'fixture-admin');self.assertTrue(r['simulation']);self.assertFalse(r['productionEntitlementImplemented'])
        self.assertEqual(r['catalog']['blackDiamond']['monthly']['termUnit'],'calendar_month');self.assertEqual(r['catalog']['blackDiamond']['yearly']['termUnit'],'calendar_year')
        self.assertEqual(Catalog(self.root).read()['catalog']['revision'],2);self.assertEqual(r['audit'][0]['actor'],'fixture-admin')
        self.assertEqual(r['regions']['86s4a21']['clientRegion'],'CN')
    def test_stale_revision_rejected_and_no_client_actor_override(self):
        self.catalog.write(self.body,'fixture-admin')
        with self.assertRaises(CatalogConflict):self.catalog.write(self.body,'fixture-admin')
        with self.assertRaises(CatalogError):self.catalog.write({**self.body,'actor':'forged'},'fixture-admin')
        self.assertEqual(len(self.catalog.read()['audit']),1)
    def test_concurrent_writers_have_one_winner(self):
        def update(_):
            try:Catalog(self.root).write(self.body,'fixture-admin');return True
            except CatalogConflict:return False
        self.catalog.read()
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sorted(pool.map(update,range(2))),[False,True])
        self.assertEqual(len(self.catalog.read()['audit']),1)
    def test_invalid_price_or_unidentified_actor_cannot_change_catalog(self):
        for b,actor in [({**self.body,'monthlyMinor':-1},'fixture-admin'),(self.body,'')]:
            with self.assertRaises(CatalogError):self.catalog.write(b,actor)
        self.assertEqual(self.catalog.read()['catalog']['revision'],1)
