"""Full gateway-to-Mrad tests using isolated loopback HTTP servers and synthetic data."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request

from server import Gateway, Store
from mrad_console_host import MradReadOnlyHandler
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from diagnose_mrad import diagnose


class MradTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.health = {'database': 'synthetic/save.sqlite', 'processId': 42, 'readApiVersion': 1,
                       'authentication': 'loopback', 'clientFingerprint': 'fixture',
                       'onlineMail': True, 'adminManagement': True}
        self.caps = {'items': [{'key': 'account.list', 'label': '账号列表', 'method': 'GET', 'implemented': True}],
                     **dict.fromkeys(('console', 'mail', 'content', 'strings', 'index', 'icons', 'administration'), True)}
        self.accounts = [{'accountId': 9223372036854775807, 'accountName': '<script>fixture</script>',
                          'characters': 1, 'disabled': False, 'cashBalance': 9007199254740993}]
        self.characters = [{'characterId': 65535, 'accountId': 9223372036854775807,
                            'name': '合成角色', 'level': 1, 'gold': 9007199254740993}]
        self.upstream_error = None
        self.change_after_read = None
        self.requires_reselect = False
        self.calls = []
        fixture = self

        class Upstream(BaseHTTPRequestHandler):
            def do_GET(self):
                fixture.calls.append((self.command, self.path, self.headers.get('X-GM-Process-Id')))
                code, data = 200, {}
                if fixture.upstream_error:
                    code = fixture.upstream_error
                elif self.path == '/gm/tool/health':
                    data = fixture.health
                elif self.path == '/gm/capabilities':
                    data = fixture.caps
                elif self.path == '/gm/accounts':
                    data = fixture.accounts
                elif self.path.startswith('/gm/characters?'):
                    data = fixture.characters
                elif self.path.startswith('/gm/tool/characters/'):
                    data = {'revision': 'fixture-revision', 'totalSp': 10, 'remainingSp': 8,
                            'requiresReselect': fixture.requires_reselect, 'branches': [{'id': 0}]}
                else:
                    code = 404
                raw = json.dumps(data).encode()
                if fixture.change_after_read and self.path == '/gm/accounts':
                    key, value = fixture.change_after_read
                    fixture.health[key] = value
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        self.upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        self.start(self.upstream)
        self.gateway = Gateway(('127.0.0.1', 0), Store(Path(self.directory.name) / 'gateway.sqlite'))
        self.gateway.sessions['fixture'] = time.time() + 1800
        self.start(self.gateway)
        self.base = 'http://' + self.gateway.authority
        self.address = f'http://127.0.0.1:{self.upstream.server_port}'

    def start(self, server):
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

    def request(self, action, body=None, authenticated=True, origin=None):
        headers = {'Content-Type': 'application/json', 'Origin': origin or self.base}
        if authenticated:
            headers['Cookie'] = 'oo_session=fixture'
        request = urllib.request.Request(self.base + '/api/admin/mrad/' + action,
                                         data=json.dumps(body).encode() if body is not None else None,
                                         headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.load(response)

    def connect(self):
        self.assertEqual(self.request('settings', {'baseUrl': self.address})[0], 200)
        code, result = self.request('connect', {})
        self.assertEqual(code, 200, result)
        self.connection = result['connectionId']
        return result

    def read(self, resource='accounts', **extra):
        return self.request('read', {'connectionId': self.connection, 'resource': resource, **extra})

    def test_complete_read_flow_with_exact_ids_and_no_upstream_writes(self):
        result = self.connect()
        self.assertFalse(result['writeEnabled'])
        self.assertNotIn('database', result)
        self.assertEqual(self.read()[1]['items'][0]['accountId'], '9223372036854775807')
        self.assertEqual(self.read()[1]['items'][0]['cashBalance'], '9007199254740993')
        code, chars = self.read('characters', accountId='9223372036854775807')
        self.assertEqual(code, 200)
        self.assertEqual(chars['items'][0]['characterId'], '65535')
        self.assertEqual(chars['items'][0]['gold'], '9007199254740993')
        code, progress = self.read('progress', accountId='9223372036854775807', characterId='65535')
        self.assertEqual(code, 200)
        self.assertEqual(progress['data']['branches'][0]['id'], 0)
        self.assertTrue(all(method == 'GET' for method, _, _ in self.calls))
        self.assertTrue(all(pid == '42' for _, path, pid in self.calls[1:]))

    def test_private_gateway_requires_session_and_origin(self):
        for action, body in (('status', None), ('diagnostics', None), ('check', {'connectionId': 'x'}), ('settings', {'baseUrl': self.address}), ('connect', {}),
                             ('disconnect', {}), ('read', {'resource': 'accounts', 'connectionId': 'x'})):
            self.assertEqual(self.request(action, body, authenticated=False)[0], 401)
        self.assertEqual(self.request('connect', {}, origin='http://untrusted.invalid')[0], 403)
        self.assertEqual(self.calls, [])

    def test_save_does_not_connect_and_invalidates_old_connection(self):
        self.connect()
        self.calls.clear()
        code, result = self.request('settings', {'baseUrl': self.address})
        self.assertEqual(code, 200)
        self.assertEqual(result['state'], 'disconnected')
        self.assertIsNone(result['connectionId'])
        self.assertEqual(self.read()[0], 409)
        self.assertEqual(self.calls, [])

    def test_rejects_invalid_ids_and_unlisted_resources_without_network(self):
        self.connect()
        self.calls.clear()
        for value in ('0', '-1', '01', '1e3', '9223372036854775808', 9007199254740993, True):
            with self.subTest(value=value):
                self.assertEqual(self.read('characters', accountId=value)[0], 400)
        for resource in ('mail', '/gm/tool/mail', 'character.edit'):
            self.assertEqual(self.read(resource)[0], 400)
        self.assertEqual(self.read('progress', accountId='1', characterId='65536')[0], 400)
        self.assertEqual(self.calls, [])

    def test_process_database_or_pvf_change_discards_results(self):
        for key, value in (('processId', 43), ('database', 'other.sqlite'), ('clientFingerprint', 'other')):
            with self.subTest(key=key):
                self.connect()
                self.change_after_read = (key, value)
                code, result = self.read()
                self.assertEqual(code, 409, result)
                self.assertNotIn('items', result)
                self.assertTrue(result['connectionInvalid'])
                self.assertIsNone(self.request('status')[1]['connectionId'])
                self.change_after_read = None

    def test_preserves_upstream_error_status_and_clears_connection(self):
        for status in (403, 409, 501, 503):
            with self.subTest(status=status):
                self.connect()
                self.upstream_error = status
                self.assertEqual(self.read()[0], status)
                self.assertIsNone(self.request('status')[1]['connectionId'])
                self.upstream_error = None

    def test_2000_row_limit_reports_possible_truncation(self):
        self.connect()
        self.accounts = [{'accountId': i + 1} for i in range(2000)]
        self.assertTrue(self.read()[1]['possiblyTruncated'])
        self.accounts.append({'accountId': 2001})
        self.assertEqual(self.read()[0], 502)

    def test_wrong_character_owner_is_rejected(self):
        self.connect()
        self.characters[0]['accountId'] = 2
        self.assertEqual(self.read('characters', accountId='9223372036854775807')[0], 502)

    def test_unready_resources_return_503(self):
        self.caps['console'] = False
        self.connect()
        self.assertEqual(self.read()[0], 503)

    def test_external_settings_change_and_corrupt_file(self):
        self.connect()
        self.gateway.mrad.file.write_text(json.dumps({'baseUrl': 'http://127.0.0.1:1'}))
        self.assertEqual(self.read()[0], 409)
        self.gateway.mrad.file.write_text('{broken')
        self.assertEqual(self.request('status')[0], 503)
        self.assertEqual(self.gateway.mrad.file.read_text(), '{broken')

    def test_assets_are_served(self):
        for path, expected in (('/mrad.js', b'/api/admin/mrad/read'), ('/mrad.css', b'.mrad-grid'),
                               ('/', b'/mrad.js')):
            with urllib.request.urlopen(self.base + path) as response:
                self.assertIn(expected, response.read())

    def test_diagnostic_report_excludes_player_names_and_database_paths(self):
        result = diagnose(self.address, '9223372036854775807', '65535')
        self.assertEqual(result['accountCount'], 1)
        self.assertEqual(result['characterCount'], 1)
        self.assertFalse(result['gameEntryVerified'])
        self.assertFalse(result['writeEnabled'])
        encoded = json.dumps(result)
        self.assertNotIn('synthetic/save.sqlite', encoded)
        self.assertNotIn('<script>fixture</script>', encoded)
        self.assertNotIn('9223372036854775807', encoded)
        self.assertEqual(result['gameAcceptance'], {'authenticationVerified': False, 'characterScreenVerified': False, 'townEntryVerified': False})

    def test_readonly_console_limits_routes_but_allows_mrad_queries(self):
        self.gateway.RequestHandlerClass = MradReadOnlyHandler
        self.gateway.mrad_only = True
        self.connect()
        self.assertEqual(self.read()[0], 200)
        self.assertEqual(self.request('check', {'connectionId': self.connection})[0], 200)
        self.assertEqual(self.request('diagnostics')[0], 200)
        for route in ('/api/admin/gm/call', '/api/admin/account-status', '/api/admin/operation', '/api/admin/config'):
            request = urllib.request.Request(self.base + route, data=b'{}', headers={
                'Content-Type': 'application/json', 'Origin': self.base, 'Cookie': 'oo_session=fixture'})
            with self.subTest(route=route), self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()

        with urllib.request.urlopen(urllib.request.Request(self.base + '/api/admin/profile', headers={'Cookie': 'oo_session=fixture'})) as response:
            self.assertTrue(json.load(response)['mradOnly'])
        for authenticated, origin, expected in ((False, self.base, 401), (True, 'http://invalid.invalid', 403)):
            headers = {'Content-Type': 'application/json', 'Origin': origin}
            if authenticated:
                headers['Cookie'] = 'oo_session=fixture'
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(self.base + '/api/desktop/quit', data=b'{}', headers=headers))
            self.assertEqual(error.exception.code, expected)
            error.exception.close()

    def test_current_instance_check_refreshes_resources_without_adopting_restart(self):
        self.connect()
        self.caps['icons'] = False
        code, status = self.request('check', {'connectionId': self.connection})
        self.assertEqual(code, 200)
        self.assertFalse(status['capabilities']['icons'])
        self.assertTrue(status['lastCheckedAt'])
        self.health['processId'] = 43
        self.assertEqual(self.request('check', {'connectionId': self.connection})[0], 409)
        self.assertIsNone(self.request('status')[1]['connectionId'])

    def test_diagnostic_snapshot_excludes_names_ids_paths_and_connection_secret(self):
        self.connect()
        self.read()
        self.read('characters', accountId='9223372036854775807')
        self.requires_reselect = True
        self.read('progress', accountId='9223372036854775807', characterId='65535')
        self.calls.clear()
        code, report = self.request('diagnostics')
        self.assertEqual(code, 200)
        self.assertEqual(self.calls, [])
        self.assertEqual(report['observations']['accounts']['count'], 1)
        self.assertEqual(report['observations']['characters']['count'], 1)
        self.assertTrue(report['observations']['progress']['requiresReselect'])
        self.assertFalse(report['observations']['progress']['townEntryVerified'])
        self.assertTrue(all(value is False for value in report['gameAcceptance'].values()))
        for private in ('synthetic/save.sqlite', '<script>fixture</script>', '9223372036854775807', self.connection, '65535'):
            self.assertNotIn(private, json.dumps(report))

    def test_character_appearance_and_selected_connection_never_imply_town_entry(self):
        self.connect()
        characters = self.characters
        self.characters = []
        self.assertEqual(self.read('characters', accountId='9223372036854775807')[1]['items'], [])
        self.characters = characters
        self.assertEqual(len(self.read('characters', accountId='9223372036854775807')[1]['items']), 1)
        for selected in (False, True, False):
            self.requires_reselect = selected
            code, result = self.read('progress', accountId='9223372036854775807', characterId='65535')
            self.assertEqual(code, 200)
            self.assertIs(result['data']['requiresReselect'], selected)
            report = self.request('diagnostics')[1]
            self.assertIs(report['observations']['progress']['requiresReselect'], selected)
            self.assertFalse(report['gameAcceptance']['townEntryVerified'])

    def test_failed_check_clears_diagnostic_observations(self):
        self.connect()
        self.read()
        self.upstream_error = 503
        self.assertEqual(self.request('check', {'connectionId': self.connection})[0], 503)
        report = self.request('diagnostics')[1]
        self.assertEqual(report['state'], 'failed')
        self.assertIsNone(report['processId'])
        self.assertIsNone(report['lastCheckedAt'])
        self.assertTrue(all(value is None for value in report['observations'].values()))



if __name__ == '__main__':
    unittest.main()
