"""Instance-bound, read-only adapter for the Mrad Max C# management API."""
import json
import os
from pathlib import Path
import secrets
import threading
from datetime import datetime, timezone

from mrad_transport import DEFAULT_URL, ProbeError, get_json, handshake, health_identity, validate_url, make_opener
from native_ids import native_id_from_request, native_id_to_wire


class MradError(ValueError):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def wire(value, key=''):
    if isinstance(value, dict):
        return {k: wire(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [wire(v) for v in value]
    if key in ('accountId', 'characterId') and value is not None:
        return native_id_to_wire(value)
    if type(value) is int and abs(value) > 9007199254740991:
        return str(value)
    return value


class MradClient:
    def __init__(self, directory):
        self.file = Path(directory) / 'mrad-settings.json'
        self.lock = threading.RLock()
        self.identity = None
        self.base_url = None
        self.connection_id = ''
        self.capabilities = None
        self.message = '尚未连接 Mrad Max'
        self.state = 'disconnected'
        self.last_checked_at = None
        self.observations = {'accounts': None, 'characters': None, 'progress': None}
        self.opener = make_opener()

    def settings(self):
        try:
            value = json.loads(self.file.read_text(encoding='utf-8')) if self.file.exists() else {'baseUrl': DEFAULT_URL}
            if not isinstance(value, dict) or set(value) != {'baseUrl'} or not isinstance(value['baseUrl'], str):
                raise ValueError()
            return {'baseUrl': validate_url(value['baseUrl'])}
        except (OSError, ValueError):
            raise MradError('Mrad 连接配置不可读取，请重新保存地址；原文件已保留', 503) from None

    def status(self):
        with self.lock:
            settings = self.settings()
            if self.identity and settings['baseUrl'] != self.base_url:
                self.fail(MradError('管理地址已变化，请重新连接', 409))
            return {**settings, 'state': self.state, 'message': self.message,
                    'connectionId': self.connection_id or None, 'writeEnabled': False,
                    'lastCheckedAt': self.last_checked_at,
                    'gameAcceptance': {'authenticationVerified': False, 'characterScreenVerified': False, 'townEntryVerified': False},
                    'processId': self.identity[0] if self.identity else None,
                    'capabilities': wire(self.capabilities) if self.capabilities else None}

    def close(self):
        with self.lock:
            self.identity = None
            self.base_url = None
            self.connection_id = ''
            self.capabilities = None
            self.last_checked_at = None
            self.observations = {'accounts': None, 'characters': None, 'progress': None}
            self.state = 'disconnected'
            self.message = '已断开 Mrad 连接'

    def fail(self, error):
        self.close()
        self.state = 'failed'
        self.message = str(error)

    def save(self, body):
        if not isinstance(body, dict) or set(body) != {'baseUrl'} or not isinstance(body['baseUrl'], str):
            raise MradError('请填写 Mrad 本机 HTTP 地址', 400)
        try:
            address = validate_url(body['baseUrl'])
        except ProbeError:
            raise MradError('地址须为本机回环 IP，例如 http://127.0.0.1:7000', 400) from None
        with self.lock:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.file.with_suffix('.tmp')
            temporary.write_text(json.dumps({'baseUrl': address}), encoding='utf-8')
            os.replace(temporary, self.file)
            self.close()
            self.message = '地址已保存，点击连接后读取服务状态'
            return self.status()

    def connect(self, body):
        if body != {}:
            raise MradError('请先保存地址，再连接', 400)
        with self.lock:
            self.close()
            try:
                address = self.settings()['baseUrl']
                health, caps = handshake(address)
                self.identity = health_identity(health)
                self.base_url = address
                self.capabilities = caps
                self.connection_id = secrets.token_urlsafe(24)
                self.state = 'ready'
                self.last_checked_at = datetime.now(timezone.utc).isoformat()
                self.message = '已连接 Mrad Max，请查看资源就绪状态'
                return self.status()
            except (ProbeError, MradError) as exc:
                self.fail(exc)
                raise MradError('连接失败：' + str(exc), getattr(exc, 'status', 502)) from None

    def check(self, body):
        if not isinstance(body, dict) or set(body) != {'connectionId'}:
            raise MradError('实例检查参数无效', 400)
        with self.lock:
            if self.state != 'ready' or not self.connection_id or body['connectionId'] != self.connection_id:
                raise MradError('连接已失效，请重新连接', 409)
            try:
                if self.settings()['baseUrl'] != self.base_url:
                    raise MradError('管理地址已变化，请重新连接', 409)
                health, caps = handshake(self.base_url)
                if health_identity(health) != self.identity:
                    raise MradError('服务进程、数据库或资源已变化，请重新连接', 409)
                self.capabilities = caps
                self.last_checked_at = datetime.now(timezone.utc).isoformat()
                return self.status()
            except (ProbeError, MradError) as exc:
                self.fail(exc)
                raise MradError(str(exc), getattr(exc, 'status', 502)) from None

    def diagnostics(self):
        with self.lock:
            status = self.status()  # Reads only GM's endpoint settings, never the game database.
            caps = self.capabilities or {}
            return {
                'formatVersion': 1, 'generatedAt': datetime.now(timezone.utc).isoformat(),
                'state': status['state'], 'message': status['message'], 'baseUrl': status['baseUrl'],
                'processId': status['processId'], 'lastCheckedAt': self.last_checked_at,
                'readApiVersion': 1 if self.identity else None,
                'schema': caps.get('schema') if type(caps.get('schema')) is int else None,
                'resources': {key: caps.get(key) for key in
                              ('console', 'mail', 'content', 'strings', 'index', 'icons', 'administration')},
                'observations': json.loads(json.dumps(self.observations)),
                'evidenceScope': 'Snapshot of last successful GM reads, not a live game-client acceptance result',
                'writeEnabled': False, 'gameEntryVerified': False, 'gameAcceptance': status['gameAcceptance'],
            }

    def read(self, body):
        if not isinstance(body, dict) or set(body) - {'connectionId', 'resource', 'accountId', 'characterId'}:
            raise MradError('Mrad 查询参数无效', 400)
        resource = body.get('resource')
        required = {'connectionId', 'resource'}
        if resource in ('characters', 'progress'):
            required.add('accountId')
        if resource == 'progress':
            required.add('characterId')
        if resource not in ('accounts', 'characters', 'progress') or set(body) != required:
            raise MradError('仅支持账号、角色和角色进度只读查询', 400)
        try:
            account = str(native_id_from_request(body['accountId'])) if 'accountId' in body else None
            character = str(native_id_from_request(body['characterId'])) if 'characterId' in body else None
            if character is not None and int(character) > 65535:
                raise ValueError('角色 ID 须在 1..65535 范围内')
        except ValueError as exc:
            raise MradError(str(exc), 400) from None
        with self.lock:
            if self.state != 'ready' or not self.connection_id or body['connectionId'] != self.connection_id:
                raise MradError('连接已失效，请重新连接并选择账号和角色', 409)
            base = self.base_url
            path = {'accounts': '/gm/accounts', 'characters': '/gm/characters?accountId=' + (account or '')}.get(resource)
            if resource == 'progress':
                path = f'/gm/tool/characters/{character}/progress?accountId={account}'
            try:
                if self.settings()['baseUrl'] != base:
                    raise MradError('管理地址已变化，请重新连接', 409)
                if not self.capabilities['console'] or (resource == 'progress' and not self.capabilities['administration']):
                    raise MradError('服务端账号或角色管理资源尚未就绪', 503)
                self.check_identity(base)
                result = get_json(self.opener, base, path, 5, self.identity[0])
                self.check_identity(base)
                self.last_checked_at = datetime.now(timezone.utc).isoformat()
                if resource == 'progress':
                    if not isinstance(result, dict):
                        raise ProbeError('角色进度响应结构无效')
                    self.observations['progress'] = {
                        'checkedAt': self.last_checked_at, 'scope': 'most recently queried character',
                        'requiresReselect': result.get('requiresReselect') if type(result.get('requiresReselect')) is bool else None,
                        'townEntryVerified': False,
                    }
                    return {'connectionId': self.connection_id, 'lastCheckedAt': self.last_checked_at, 'data': wire(result)}
                if not isinstance(result, list) or len(result) > 2000:
                    raise ProbeError('账号或角色列表响应结构无效')
                id_field = 'accountId' if resource == 'accounts' else 'characterId'
                for row in result:
                    if not isinstance(row, dict) or id_field not in row:
                        raise ProbeError('列表缺少内部 ID')
                    native_id_to_wire(row[id_field])
                    if resource == 'characters' and int(native_id_to_wire(row[id_field])) > 65535:
                        raise ProbeError('角色 ID 超出服务端数据库范围')
                    if resource == 'characters' and native_id_to_wire(row.get('accountId')) != account:
                        raise ProbeError('角色归属不匹配，请重新读取账号列表')
                if resource == 'accounts':
                    self.observations['characters'] = None
                self.observations['progress'] = None
                self.observations[resource] = {
                    'checkedAt': self.last_checked_at, 'count': len(result),
                    'possiblyTruncated': len(result) == 2000,
                    'scope': 'returned account list' if resource == 'accounts' else 'most recently queried account',
                }
                return {'connectionId': self.connection_id, 'lastCheckedAt': self.last_checked_at, 'items': wire(result),
                        'possiblyTruncated': len(result) == 2000}
            except (ProbeError, ValueError) as exc:
                status = getattr(exc, 'status', 502)
                self.fail(exc)
                raise MradError(str(exc), status) from None

    def check_identity(self, base):
        health = get_json(self.opener, base, '/gm/tool/health', 5, self.identity[0])
        if health_identity(health) != self.identity:
            raise MradError('服务进程、数据库或资源已变化，请重新连接', 409)
