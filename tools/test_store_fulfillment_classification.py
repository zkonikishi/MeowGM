import unittest
from classify_store_fulfillment import classify


class ClassificationTests(unittest.TestCase):
    source = 'CeraPackageCn115.Parse [cera package] [usable cera package] opcode == 510'

    def report(self, entries=13, kind='[cera package]'):
        return {'items': [{'productId': 'product', 'itemId': '38', 'type': kind,
                           'indexedContentRows': entries, 'issues': []}]}

    def test_handler_and_entries_do_not_approve_sale(self):
        result = classify(self.report(), self.source)
        self.assertEqual(result['fulfillable'], 0)
        self.assertEqual(result['items'][0]['status'], 'pending_evidence')
        self.assertFalse(result['items'][0]['saleEnabled'])

    def test_missing_entries_never_auto_expand(self):
        row = classify(self.report(0), self.source)['items'][0]
        self.assertIn('package_entries_not_available', row['reasons'])
        self.assertFalse(row['automaticExpansionAllowed'])

    def test_mismatched_type_and_missing_handler_explicit(self):
        row = classify(self.report(kind='[waste]'), '')['items'][0]
        self.assertEqual(row['status'], 'unsupported_in_this_package_flow')
        self.assertIsNone(row['handlerFamily'])


if __name__ == '__main__': unittest.main()
