import base64
import json
import unittest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from admin_backend.security import AdminFault, AdminTokenVerifier
from admin_backend.readonly import AdminReadGateway
from admin_backend.mrad_reader import MradReaders
from admin_backend.pure_admin_contract import menu_for
from admin_backend.security import AdminIdentity


class AdminTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Test key stays in memory, never saved or used by a production issuer.
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.pem = cls.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)

    def setUp(self):
        self.active = True
        self.calls, self.audit = [], []
        self.verifier = AdminTokenVerifier(issuer='https://fixture-issuer.invalid', public_keys={'fixture': self.pem},
                                          active_session=lambda identity: self.active, clock=lambda: 1000)
        self.gateway = AdminReadGateway(self.verifier, {'accounts': lambda identity, query: self.calls.append(query) or {'items': []}}, self.audit.append)
        self.claims = {'iss': 'https://fixture-issuer.invalid', 'aud': 'mrad.admin.v1', 'sub': 'fixture-admin',
                       'sid': 'fixture-admin-session', 'iat': 900, 'nbf': 900, 'exp': 1100, 'scope': 'gm.read.accounts'}

    def token(self, changes=None, header=None):
        claims = {**self.claims, **(changes or {})}
        def encode(value):
            return base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).decode().rstrip('=')
        head, body = encode(header or {'alg': 'RS256', 'typ': 'JWT', 'kid': 'fixture'}), encode(claims)
        data = (head + '.' + body).encode()
        sig = self.key.sign(data, padding.PKCS1v15(), hashes.SHA256())
        return 'Bearer ' + head + '.' + body + '.' + base64.urlsafe_b64encode(sig).decode().rstrip('=')

    def request(self, token=None, method='GET', path='/api/admin/v1/gm/accounts'):
        return self.gateway.handle(method, path, self.token() if token is None else token)

    def reject(self, expected, **kwargs):
        with self.assertRaises(AdminFault) as error:
            self.request(**kwargs)
        self.assertEqual(error.exception.status, expected)
        self.assertFalse(self.calls)

    def test_valid_admin_and_minimal_audit(self):
        self.assertEqual(self.request(), {'items': []})
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(set(self.audit[0]), {'requestId', 'status', 'code', 'actorRef', 'route'})
        self.assertNotIn('fixture-admin', str(self.audit))

    def test_pure_admin_menu_is_scope_filtered_but_not_authorization(self):
        identity = AdminIdentity('fixture', 'fixture', 'fixture', frozenset({'gm.read.accounts'}))
        menu = menu_for(identity)
        self.assertEqual([row['name'] for row in menu], ['gm-accounts'])
        self.assertTrue(menu[0]['readOnly'])
        self.reject(403, token=self.token({'scope': 'gm.read.status'}))
        self.assertEqual(menu_for(AdminIdentity('fixture', 'fixture', 'fixture', frozenset())), [])

    def test_player_game_and_fulfillment_audiences_rejected(self):
        for audience in ('mrad.player.v1', 'cn115.game', 'mrad.shop.internal.v1'):
            self.reject(401, token=self.token({'aud': audience}))

    def test_missing_auth_and_local_window_token_rejected(self):
        for token in ('', 'local-window-token', 'Bearer fixture-window', 'Cookie player-session'):
            self.reject(401, token=token)

    def test_wrong_scope_and_wildcard_denied(self):
        for scope in ('gm.read.status', 'admin', 'player'):
            self.reject(403, token=self.token({'scope': scope}))

    def test_revoked_session_checked_on_every_request(self):
        token = self.token(); self.request(token); self.calls.clear(); self.active = False
        self.reject(401, token=token)

    def test_revocation_source_failure_fails_closed(self):
        def unavailable(identity): raise OSError('sensitive connection details')
        self.verifier.active_session = unavailable
        self.reject(503)
        self.assertNotIn('sensitive', str(self.audit))

    def test_invalid_signature_wrong_key_and_header_url(self):
        token = self.token(); parts = token.split('.'); parts[-1] = 'A' * len(parts[-1])
        self.reject(401, token='.'.join(parts))
        self.reject(401, token=self.token(header={'alg': 'RS256', 'typ': 'JWT', 'kid': 'unknown'}))
        self.reject(401, token=self.token(header={'alg': 'RS256', 'typ': 'JWT', 'kid': 'fixture', 'jku': 'https://elsewhere.invalid'}))

    def test_expiry_future_clock_issuer_and_types(self):
        for changes in ({'exp': 1000}, {'nbf': 1001}, {'iat': 1001}, {'exp': 9999}, {'exp': True}, {'iss': 'other'}):
            self.reject(401, token=self.token(changes))

    def test_no_write_or_connection_configuration_routes(self):
        self.reject(405, method='POST')
        self.reject(404, path='/api/admin/mrad/connect')
        self.reject(400, path='/api/admin/v1/gm/accounts?baseUrl=http://elsewhere')

    def test_client_claims_cannot_grant_scope(self):
        self.reject(403, token=self.token({'scope': 'player', 'role': 'admin', 'permissions': ['gm.read.accounts']}))

    def test_unconfigured_backend_or_reader_unavailable(self):
        with self.assertRaises(AdminFault) as error: AdminReadGateway().handle('GET', '/api/admin/v1/gm/accounts')
        self.assertEqual(error.exception.status, 503)
        self.reject(503, token=self.token({'scope': 'gm.audit.auction'}), path='/api/admin/v1/audit/auction')

    def test_query_duplicates_and_cross_route_fields_rejected(self):
        self.reject(400, path='/api/admin/v1/gm/accounts?uid=forged')
        self.reject(400, token=self.token({'scope': 'gm.read.characters'}), path='/api/admin/v1/gm/characters?accountId=1&accountId=2')

    def test_audit_failure_never_returns_data(self):
        def unavailable(event): raise OSError('private path')
        self.gateway.audit_sink = unavailable
        with self.assertRaises(AdminFault) as error: self.request()
        self.assertEqual(error.exception.code, 'admin_audit_unavailable')

    def test_control_characters_cannot_be_normalized_into_allowed_routes(self):
        for path in ('/api/admin/v1/gm/acc\tounts', '/api/admin/v1/gm/accounts\n',
                     '/api/admin/v1/gm/accounts\x00', '/api/admin/v1/gm/accounts ',
                     '/api/admin/v1/gm/\\accounts'):
            self.reject(400, path=path)
        self.assertTrue(all(event['route'] == 'unmapped' for event in self.audit))

    def test_algorithm_confusion_and_wildcard_scope_rejected(self):
        for alg in ('none', 'HS256', 'RS512'):
            self.reject(401, token=self.token(header={'alg': alg, 'typ': 'JWT', 'kid': 'fixture'}))
        self.reject(401, token=self.token({'scope': '*'}))

    def test_all_unsafe_methods_and_sensitive_routes_rejected(self):
        for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'CONNECT', 'TRACE'):
            self.reject(405, method=method)
        for path in ('/api/admin/v1/gm/settings', '/api/admin/v1/gm/mail/send',
                     '/api/admin/v1/gm/database', '/api/admin/v1/gm/diagnostics',
                     '/max/api/admin/v1/gm/accounts'):
            self.reject(404, path=path)

    def test_read_source_error_is_sanitized_and_audited(self):
        def unavailable(identity, query): raise OSError('private-database-password')
        self.gateway.readers['accounts'] = unavailable
        self.reject(503)
        self.assertEqual(self.audit[-1]['code'], 'admin_resource_unavailable')
        self.assertNotIn('private-database-password', str(self.audit))

    def test_existing_reader_projection_omits_window_token_and_paths(self):
        class Client:
            def status(self):
                return {'state': 'ready', 'connectionId': 'secret-window', 'baseUrl': 'private', 'database': 'private', 'capabilities': {'console': True}}
            def read(self, request):
                return {'items': [{'accountId': '9223372036854775807', 'accountName': 'fixture', 'token': 'private'}]}
        readers = MradReaders(Client()).bindings()
        self.assertNotIn('connectionId', readers['status'](None, {}))
        self.assertEqual(readers['accounts'](None, {})['items'], [{'accountId': '9223372036854775807', 'accountName': 'fixture'}])


if __name__ == '__main__': unittest.main()
