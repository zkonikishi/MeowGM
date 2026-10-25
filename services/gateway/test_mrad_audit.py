"""Offline synthetic contract validation; no server or player data."""
import unittest
from types import SimpleNamespace
from mrad_audit import AuditError, normalize_page, unavailable


class AuditTests(unittest.TestCase):
    def page(self, kind='delivery', **changes):
        row = dict(operationId='op-1', uid='opaque-user', cid='65535', realm='cn', state='queued',
                   requestId='stable-fixture', token='must-drop', email='must-drop', password='must-drop')
        if kind != 'delivery':
            row['state'] = {'claim': 'claimed', 'ownership': 'active', 'auction': 'sold'}[kind]
        return dict(version=1, available=True, queryId='instance-filter-v1', items=[row], nextCursor='page_2', **changes)

    def normalize(self, page, kind='delivery', scopes=None, query='instance-filter-v1'):
        return normalize_page(page, kind=kind, query_id=query,
                              authorized_scopes=scopes if scopes is not None else {'gm.audit.' + kind})

    def test_unavailable_is_explicit_and_empty(self):
        self.assertFalse(unavailable()['available'])
        self.assertEqual(unavailable()['items'], [])

    def test_player_and_wrong_scope_denied(self):
        for scopes in ({'player'}, {'gm.audit.auction'}, set()):
            with self.assertRaises(AuditError) as error:
                self.normalize(self.page(), scopes=scopes)
            self.assertEqual(error.exception.status, 403)

    def test_all_kinds_and_sensitive_fields_dropped(self):
        for kind in ('delivery', 'claim', 'ownership', 'auction'):
            result = self.normalize(self.page(kind), kind)
            self.assertEqual(result['items'][0]['uid'], 'opaque-user')
            self.assertNotIn('token', result['items'][0])
            self.assertNotIn('email', result['items'][0])
            self.assertNotIn('password', result['items'][0])
            self.assertFalse(result['writeEnabled'])

    def test_cursor_bound_to_query_and_instance(self):
        with self.assertRaises(AuditError) as error:
            self.normalize(self.page(), query='other-instance-or-filter')
        self.assertEqual(error.exception.status, 409)
        page = self.page(); page['nextCursor'] = 'https://elsewhere/?token=secret'
        with self.assertRaises(AuditError): self.normalize(page)

    def test_page_limit_duplicates_and_unknown_state(self):
        for change in ('limit', 'duplicate', 'state'):
            page = self.page()
            if change == 'limit': page['items'] *= 101
            elif change == 'duplicate': page['items'] *= 2
            else: page['items'][0]['state'] = 'pretend-delivered'
            with self.assertRaises(AuditError): self.normalize(page)

    def test_exact_strings_and_final_page(self):
        page = self.page('auction'); page['nextCursor'] = None
        page['items'][0].update(buyerDebit='9007199254740993', sellerCredit='9007199254740992', fee='1')
        result = self.normalize(page, 'auction')
        self.assertEqual(result['items'][0]['buyerDebit'], '9007199254740993')
        self.assertIsNone(result['nextCursor'])
        page['items'][0]['buyerDebit'] = 9007199254740993
        with self.assertRaises(AuditError): self.normalize(page, 'auction')

    def test_unavailable_never_renders_supplied_rows(self):
        page = self.page(); page['available'] = False
        self.assertEqual(self.normalize(page)['items'], [])

    def test_ownership_and_realm_filters_reject_mismatch(self):
        for condition in ({'expected_uid': 'other-user'}, {'expected_cid': '2'}, {'expected_realm': 'other-realm'}):
            with self.assertRaises(AuditError) as error:
                normalize_page(self.page(), kind='delivery', query_id='instance-filter-v1',
                               authorized_scopes={'gm.audit.delivery'}, **condition)
            self.assertEqual(error.exception.status, 409)

    def test_local_endpoint_requires_window_and_never_queries_upstream(self):
        # Invoke routing directly: no socket, HTTP server or game service starts.
        from server import Handler
        for authenticated, expected in ((False, 401), (True, 200)):
            replies = []
            request = SimpleNamespace(path='/api/admin/mrad/audit', valid_host=lambda: True,
                                      session=lambda: authenticated,
                                      reply=lambda status, data: replies.append((status, data)))
            Handler.do_GET(request)
            self.assertEqual(replies[0][0], expected)
            if authenticated:
                self.assertFalse(replies[0][1]['available'])
                self.assertEqual(replies[0][1]['items'], [])


if __name__ == '__main__': unittest.main()
