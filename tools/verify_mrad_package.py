"""Validate a frozen console in a temporary data directory; never contacts a game server."""
import argparse
import json
from pathlib import Path
import queue
import re
import socket
import subprocess
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request


def verify(executable):
    with tempfile.TemporaryDirectory(prefix='mrad-package-check-') as directory:
        process = subprocess.Popen([str(Path(executable).resolve()), '--no-open', '--data', directory],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8',
                                   errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
        startup = queue.Queue()
        threading.Thread(target=lambda: startup.put(process.stdout.readline()), daemon=True).start()
        base = None
        cookie = ''
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def request(path, body=None, authenticated=True, window=None):
            headers = {'Origin': base, 'Content-Type': 'application/json'}
            if authenticated and cookie:
                headers['Cookie'] = cookie
            if window:
                headers['X-OO-Window'] = window
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
            try:
                response = opener.open(req, timeout=5)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                return response.status, response.read(), response.headers

        try:
            try:
                line = startup.get(timeout=25)
            except queue.Empty:
                raise RuntimeError('Executable did not report a local window within 25 seconds') from None
            match = re.search(r'http://127\.0\.0\.1:[0-9]+/\#setup=([^\s]+)', line)
            if not match:
                process.wait(timeout=5)
                raise RuntimeError('Executable failed before creating its local management window: ' + process.stderr.read()[-3000:])
            url = urllib.parse.urlsplit(match.group(0))
            base = urllib.parse.urlunsplit((url.scheme, url.netloc, '', '', ''))
            assert request('/api/admin/mrad/status', authenticated=False)[0] == 401
            code, _, headers = request('/api/desktop/connect', {}, authenticated=False, window=match.group(1))
            assert code == 200, 'Local window authentication failed'
            cookie = headers['Set-Cookie'].split(';')[0]
            code, raw, _ = request('/')
            assert code == 200 and b'/mrad.js' in raw, 'Packaged index missing'
            scripts = re.findall(rb'<script src="(/[^"]+)"', raw)
            for script in scripts:
                assert request(script.decode())[0] == 200, 'Packaged script missing'
            assert request('/mrad.css')[0] == 200
            assert json.loads(request('/api/admin/profile')[1])['mradOnly'] is True
            assert request('/api/admin/mrad/settings', {'baseUrl': 'http://127.0.0.1:1'})[0] == 200
            status = json.loads(request('/api/admin/mrad/status')[1])
            assert status['state'] == 'disconnected' and status['writeEnabled'] is False
            assert all(value is False for value in status['gameAcceptance'].values())
            report = json.loads(request('/api/admin/mrad/diagnostics')[1])
            assert report['state'] == 'disconnected' and report['lastCheckedAt'] is None
            assert 'connectionId' not in report and 'database' not in report
            assert request('/api/admin/mrad/check', {'connectionId': 'not-connected'})[0] == 409
            for path in ('/api/admin/account-status', '/api/admin/gm/call', '/api/admin/config'):
                assert request(path, {})[0] == 403, 'Read-only boundary failed'
            assert request('/api/admin/game/accounts')[0] == 403
            assert request('/api/desktop/quit', {})[0] == 200
            process.wait(timeout=20)
            assert process.returncode == 0, 'Executable exited with an error'
            with socket.socket() as sock:
                sock.settimeout(1)
                assert sock.connect_ex(('127.0.0.1', url.port)) != 0, 'Temporary console port was not closed'
            return {'startup': True, 'packagedScripts': len(scripts), 'assets': True,
                    'localWindowAuthentication': True, 'readOnlyBoundary': True,
                    'dataDirectory': 'temporary isolated directory', 'gracefulShutdown': True,
                    'gameServerContacted': False, 'gameEntryVerified': False}
        finally:
            if process.poll() is None:
                if base and cookie:
                    try:
                        request('/api/desktop/quit', {})
                        process.wait(timeout=5)
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                if process.poll() is None:
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                    process.wait(timeout=10)
            process.stdout.close()
            process.stderr.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    print(json.dumps(verify(parser.parse_args().executable), indent=2))
