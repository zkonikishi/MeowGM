"""Exact read-only admin route candidate; no listener, remote config or writes."""
from urllib.parse import urlsplit, parse_qs
import uuid
import hashlib
from .security import AdminFault


ROUTES = {
    '/api/admin/v1/gm/status': ('gm.read.status', 'status', ()),
    '/api/admin/v1/gm/accounts': ('gm.read.accounts', 'accounts', ()),
    '/api/admin/v1/gm/characters': ('gm.read.characters', 'characters', ('accountId',)),
    '/api/admin/v1/gm/progress': ('gm.read.progress', 'progress', ('accountId', 'characterId')),
    '/api/admin/v1/audit/auction': ('gm.audit.auction', 'auction', ()),
}


class AdminReadGateway:
    def __init__(self, verifier=None, readers=None, audit_sink=None):
        self.verifier = verifier
        self.readers = dict(readers or {})
        self.audit_sink = audit_sink

    def handle(self, method, target, authorization=None):
        """Host entry after TLS/header limits; never bind verifier/readers from a body."""
        if self.verifier is None or self.audit_sink is None:
            raise AdminFault('admin_backend_not_ready', 503)
        request_id = str(uuid.uuid4())
        context = {'requestId': request_id, 'actorRef': None, 'route': 'unmapped'}
        try:
            result = self._handle(method, target, authorization, context)
        except AdminFault as error:
            self._audit(context, error.status, error.code)
            raise
        self._audit(context, 200, 'admin_read_completed')
        return result

    def _audit(self, context, status, code):
        try:
            self.audit_sink({**context, 'status': status, 'code': code})
        except Exception:
            raise AdminFault('admin_audit_unavailable', 503) from None

    def _handle(self, method, target, authorization, context):
        identity = self.verifier.verify(authorization)
        context['actorRef'] = hashlib.sha256((identity.issuer + '\0' + identity.subject).encode()).hexdigest()
        if method != 'GET':
            raise AdminFault('admin_read_only', 405)
        if (not isinstance(target, str) or not target.startswith('/') or target.startswith('//')
                or len(target) > 2048 or any(ord(char) <= 32 or ord(char) == 127 for char in target)
                or '\\' in target):
            raise AdminFault('invalid_admin_route', 400)
        split = urlsplit(target)
        route = ROUTES.get(split.path)
        if route is None or split.fragment:
            raise AdminFault('admin_route_not_found', 404)
        context['route'] = split.path
        scope, resource, required = route
        if scope not in identity.scopes:
            raise AdminFault('admin_scope_required', 403)
        try:
            query = parse_qs(split.query, keep_blank_values=True, strict_parsing=True, max_num_fields=4)
        except ValueError:
            raise AdminFault('invalid_admin_query', 400) from None
        if set(query) != set(required) or any(len(value) != 1 for value in query.values()):
            raise AdminFault('invalid_admin_query', 400)
        values = {key: value[0] for key, value in query.items()}
        for key, value in values.items():
            maximum = 65535 if key == 'characterId' else 9223372036854775807
            if not value.isascii() or not value.isdecimal() or value.startswith('0') or len(value) > 19 or not 1 <= int(value) <= maximum:
                raise AdminFault('invalid_admin_query', 400)
        reader = self.readers.get(resource)
        if reader is None:
            raise AdminFault('admin_resource_unavailable', 503)
        try:
            return reader(identity, values)
        except AdminFault:
            raise
        except Exception:
            # Do not expose SQL, paths, credentials or raw upstream response bodies.
            raise AdminFault('admin_resource_unavailable', 503) from None
