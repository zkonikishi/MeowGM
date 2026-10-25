import json
import unittest
from admin_backend.http_app import AdminHttpApp
from admin_backend.security import AdminFault


class HttpTests(unittest.TestCase):
    def call(self, app=None, **changes):
        response = {}
        def start(status, headers):
            response.update(status=status, headers=dict(headers))
        env = {'RAW_URI': '/api/admin/v1/gm/accounts', 'REQUEST_METHOD': 'GET', **changes}
        body = b''.join((app or AdminHttpApp())(env, start))
        response['body'] = json.loads(body)
        return response

    def test_missing_dependencies_are_503_no_store(self):
        response = self.call()
        self.assertTrue(response['status'].startswith('503 '))
        self.assertEqual(response['headers']['Cache-Control'], 'no-store')
        self.assertNotIn('Access-Control-Allow-Origin', response['headers'])

    def test_raw_target_and_bearer_are_passed_without_player_cookie(self):
        class Gateway:
            def handle(self, method, target, authorization):
                self.args = method, target, authorization
                return {'items': [], 'writeEnabled': False}
        gateway = Gateway()
        response = self.call(AdminHttpApp(gateway), HTTP_COOKIE='player=fixture')
        self.assertEqual(gateway.args, ('GET', '/api/admin/v1/gm/accounts', None))
        self.assertEqual(response['body'], {'items': [], 'writeEnabled': False})

    def test_body_and_missing_original_target_rejected(self):
        self.assertEqual(self.call(CONTENT_LENGTH='1')['body']['error']['code'], 'admin_request_body_rejected')
        self.assertEqual(self.call(HTTP_TRANSFER_ENCODING='chunked')['body']['error']['code'], 'admin_request_body_rejected')
        self.assertEqual(self.call(RAW_URI=None)['body']['error']['code'], 'admin_original_target_required')

    def test_fault_and_unexpected_error_never_leak(self):
        class Gateway:
            def handle(self, *args): raise AdminFault('invalid_admin_token', 401)
        response = self.call(AdminHttpApp(Gateway()))
        self.assertEqual(response['headers']['WWW-Authenticate'], 'Bearer')
        class Broken:
            def handle(self, *args): raise OSError('private-secret')
        response = self.call(AdminHttpApp(Broken()))
        self.assertNotIn('private-secret', str(response))
        self.assertTrue(response['status'].startswith('503 '))
