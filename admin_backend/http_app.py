"""WSGI embedding seam only. No listener, service startup or implicit authority."""
import json
from http import HTTPStatus
from .security import AdminFault
from .readonly import AdminReadGateway


class AdminHttpApp:
    def __init__(self, gateway=None):
        self.gateway = gateway if gateway is not None else AdminReadGateway()

    def __call__(self, environ, start_response):
        try:
            # Host supplies the original request target, without proxy normalization.
            # Only a trusted fixed-prefix proxy may strip /max before this point.
            target = environ.get('RAW_URI') or environ.get('REQUEST_URI')
            if not target:
                raise AdminFault('admin_original_target_required', 503)
            if environ.get('CONTENT_LENGTH', '') not in ('', '0') or environ.get('HTTP_TRANSFER_ENCODING'):
                raise AdminFault('admin_request_body_rejected', 400)
            data = self.gateway.handle(environ.get('REQUEST_METHOD', ''), target,
                                       environ.get('HTTP_AUTHORIZATION'))
            status = 200
            payload = data
        except AdminFault as error:
            status = error.status
            payload = {'error': {'code': error.code}}
        except Exception:
            status = 503
            payload = {'error': {'code': 'admin_backend_unavailable'}}
        try:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        except (ValueError, TypeError):
            status = 503
            body = b'{"error":{"code":"admin_response_unavailable"}}'
        headers = [('Content-Type', 'application/json; charset=utf-8'), ('Content-Length', str(len(body))),
                   ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
                   ('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'"),
                   ('Referrer-Policy', 'no-referrer')]
        if status == 401:
            headers.append(('WWW-Authenticate', 'Bearer'))
        if status == 405:
            headers.append(('Allow', 'GET'))
        start_response(f'{status} {HTTPStatus(status).phrase}', headers)
        return [body]
