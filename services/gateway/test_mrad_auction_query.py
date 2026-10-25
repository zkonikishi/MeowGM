import unittest
from mrad_audit import AuditError
from mrad_auction_query import adapt_library_search


class AuctionQueryTests(unittest.TestCase):
    query = 'a' * 32
    listing = 'b' * 32

    def page(self):
        return {'Version': 'auction-query-v1', 'InstanceId': 'fixture-instance', 'QueryId': self.query,
                'Items': [{'ListingId': self.listing, 'ItemId': '38', 'Name': '鬼剑士福包', 'Category': '道具',
                           'Quantity': 1, 'Price': 9007199254740993, 'ExpiresAt': 2000000000,
                           'Revision': 1, 'State': 'Listed', 'Snapshot': 'secret', 'UID': 'private',
                           'Owner': {'Cid': 'private'}, 'Token': 'secret'}], 'NextCursor': None}

    def adapt(self, page, **kwargs):
        args = dict(expected_instance='fixture-instance', expected_query_id=self.query,
                    authorized_scopes={'gm.audit.auction'})
        args.update(kwargs)
        return adapt_library_search(page, **args)

    def test_exact_numbers_chinese_names_and_whitelist(self):
        row = self.adapt(self.page())['items'][0]
        self.assertEqual(row['price'], '9007199254740993')
        self.assertEqual(row['name'], '鬼剑士福包')
        self.assertFalse({'Snapshot', 'UID', 'Owner', 'Token'} & row.keys())

    def test_participant_scope_never_becomes_admin(self):
        with self.assertRaises(AuditError) as error:
            self.adapt(self.page(), authorized_scopes={'auction.player', 'auction.receipt.own'})
        self.assertEqual(error.exception.status, 403)

    def test_version_instance_and_query_must_match(self):
        for key in ('Version', 'InstanceId', 'QueryId'):
            page = self.page(); page[key] = 'different'
            with self.assertRaises(AuditError): self.adapt(page)

    def test_cursor_preserved_without_extra_fields(self):
        page = self.page()
        page['NextCursor'] = dict(Context='A' * 64, AfterId=self.listing, QueryId=self.query, Owner='private')
        cursor = self.adapt(page)['nextCursor']
        self.assertEqual(set(cursor), {'context', 'afterId', 'queryId'})
        self.assertEqual(cursor['afterId'], self.listing)

    def test_changed_cursor_query_or_after_id_rejected(self):
        for key in ('QueryId', 'AfterId'):
            page = self.page(); page['NextCursor'] = dict(Context='A' * 64, AfterId=self.listing, QueryId=self.query)
            page['NextCursor'][key] = 'c' * 32
            with self.assertRaises(AuditError): self.adapt(page)

    def test_float_bool_overflow_and_duplicate_rejected(self):
        for bad in (1.0, True, 9223372036854775808):
            page = self.page(); page['Items'][0]['Price'] = bad
            with self.assertRaises(AuditError): self.adapt(page)
        page = self.page(); page['Items'] *= 2
        with self.assertRaises(AuditError): self.adapt(page)

    def test_public_vs_own_terminal_states(self):
        page = self.page(); page['Items'][0]['State'] = 'Sold'
        with self.assertRaises(AuditError): self.adapt(page)
        self.assertEqual(self.adapt(page, mine=True)['items'][0]['state'], 'sold')

    def test_empty_final_page_and_limit(self):
        page = self.page(); page['Items'] = []
        self.assertEqual(self.adapt(page)['items'], [])
        with self.assertRaises(AuditError): self.adapt(self.page(), page_size=0)


if __name__ == '__main__': unittest.main()
