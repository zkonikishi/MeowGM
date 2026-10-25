"""The development console exposes only the Mrad read-only slice and UI bootstrap."""
from urllib.parse import urlsplit
import json
import threading
from desktop_host import DesktopHandler


class MradReadOnlyHandler(DesktopHandler):
    GET_API = frozenset({
        '/api/desktop/setup', '/api/health', '/api/public/config',
        '/api/admin/config', '/api/admin/audit', '/api/admin/profile',
        '/api/admin/operations', '/api/admin/connections', '/api/admin/environment',
        '/api/admin/mrad/status', '/api/admin/mrad/diagnostics',
        '/api/admin/mrad/audit',
    })
    POST_API = frozenset({
        '/api/desktop/connect', '/api/admin/mrad/settings',
        '/api/admin/mrad/connect', '/api/admin/mrad/disconnect', '/api/admin/mrad/read',
        '/api/admin/mrad/check',
    })

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith('/api/') and path not in self.GET_API:
            if not self.valid_host():
                return
            return self.reply(403, {'error': '此开发包只提供 Mrad 本机只读管理'})
        return super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path == '/api/desktop/quit':
            if not self.valid_host():
                return
            if self.headers.get('Origin') != 'http://' + self.server.authority:
                return self.reply(403, {'error': '请求来源无效'})
            if not self.session():
                return self.reply(401, {'error': '请先打开本机管理窗口'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 64 or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError()
                if json.loads(self.rfile.read(length)) != {}:
                    raise ValueError()
            except (ValueError, UnicodeError):
                return self.reply(400, {'error': '退出参数无效'})
            self.reply(200, {'ok': True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if urlsplit(self.path).path not in self.POST_API:
            if not self.valid_host():
                return
            return self.reply(403, {'error': '此开发包未开放该操作，仅支持 Mrad 本机只读管理'})
        return super().do_POST()
