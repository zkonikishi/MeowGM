import sqlite3
import unittest
from audit_store_catalog import audit


class StoreCatalogTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.executescript("CREATE TABLE metadata(key TEXT,value TEXT); INSERT INTO metadata VALUES('complete','true');"
                              "CREATE TABLE item(id INTEGER,name TEXT,kind TEXT,type TEXT);"
                              "CREATE TABLE package_entry(container_id INTEGER);"
                              "INSERT INTO item VALUES(38,'礼包甲','stackable','[cera package]');"
                              "INSERT INTO package_entry VALUES(38);")
        self.catalog = {'items': [{'id': 'product', 'itemId': '38', 'name': '礼包甲', 'directEntries': 1}]}

    def test_valid_id_evidence_does_not_approve_fulfillment(self):
        result = audit(self.catalog, self.db)
        self.assertEqual(result['variantsWithIssues'], 0)
        self.assertFalse(result['contentApproved'])
        self.assertFalse(result['gameDeliveryVerified'])

    def test_wrong_name_and_unknown_id_detected(self):
        self.catalog['items'][0]['variants'] = [{'itemId': '38', 'name': 'wrong'}, {'itemId': '39', 'name': 'other'}]
        result = audit(self.catalog, self.db)
        self.assertEqual(result['variantsWithIssues'], 2)
        self.assertIn('item_missing_from_current_cn_catalog', result['items'][1]['issues'])

    def test_invalid_and_duplicate_variant_ids(self):
        self.catalog['items'][0]['variants'] = [{'itemId': '38'}, {'itemId': '38'}, {'itemId': '../38'}]
        result = audit(self.catalog, self.db)
        self.assertIn('duplicate_variant_item_id', result['items'][1]['issues'])
        self.assertIn('invalid_item_id', result['items'][2]['issues'])

    def test_wrong_type_and_contents_mismatch(self):
        self.db.execute("UPDATE item SET type='[waste]'")
        self.catalog['items'][0]['directEntries'] = 13
        issues = audit(self.catalog, self.db)['items'][0]['issues']
        self.assertIn('not_a_cera_package', issues)
        self.assertIn('declared_contents_count_mismatch', issues)

    def test_incomplete_source_and_duplicate_products_fail(self):
        self.catalog['items'] *= 2
        with self.assertRaises(ValueError): audit(self.catalog, self.db)
        self.db.execute("UPDATE metadata SET value='false'")
        with self.assertRaises(ValueError): audit({'items': []}, self.db)


if __name__ == '__main__': unittest.main()
