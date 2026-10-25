"""Pinned-key administrator verification; never reuse the local GM window session."""
import base64
from dataclasses import dataclass
import json
import re
import time
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class AdminFault(ValueError):
    def __init__(self, code, status):
        super().__init__(code)
        self.code, self.status = code, status


@dataclass(frozen=True)
class AdminIdentity:
    issuer: str
    subject: str
    session_id: str
    scopes: frozenset[str]


def _decode(segment):
    if not isinstance(segment, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', segment):
        raise AdminFault('invalid_admin_token', 401)
    try:
        raw = base64.urlsafe_b64decode(segment + '=' * (-len(segment) % 4))
    except (ValueError, TypeError):
        raise AdminFault('invalid_admin_token', 401) from None
    if base64.urlsafe_b64encode(raw).decode().rstrip('=') != segment:
        raise AdminFault('invalid_admin_token', 401)
    return raw


def _json(segment):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON field')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('invalid JSON constant')
    try:
        value = json.loads(_decode(segment), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise AdminFault('invalid_admin_token', 401) from None
    if not isinstance(value, dict):
        raise AdminFault('invalid_admin_token', 401)
    return value


class AdminTokenVerifier:
    """Proposed admin token profile, requires coordination with the issuer.

    No key discovery from headers. active_session must query authoritative admin
    authorization/revocation on EVERY request. No issuer or signing keys are made.
    """
    def __init__(self, *, issuer, public_keys, active_session, clock=time.time, maximum_lifetime=900):
        if not issuer or not public_keys or not callable(active_session) or not 1 <= maximum_lifetime <= 3600:
            raise ValueError('Explicit administrator trust configuration required')
        self.issuer, self.active_session = issuer, active_session
        self.clock, self.maximum_lifetime = clock, maximum_lifetime
        self.keys = {}
        for kid, pem in public_keys.items():
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', kid):
                raise ValueError('Invalid pinned key ID')
            key = serialization.load_pem_public_key(pem)
            if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
                raise ValueError('Pinned RSA public key of at least 2048 bits required')
            self.keys[kid] = key

    def verify(self, authorization):
        if not isinstance(authorization, str) or not authorization.startswith('Bearer '):
            raise AdminFault('admin_authentication_required', 401)
        token = authorization[7:]
        if len(token) > 8192 or token.count('.') != 2:
            raise AdminFault('invalid_admin_token', 401)
        head, body, signature = token.split('.')
        header, claims = _json(head), _json(body)
        if set(header) != {'alg', 'typ', 'kid'} or header['alg'] != 'RS256' or header['typ'] != 'JWT':
            raise AdminFault('invalid_admin_token', 401)
        key = self.keys.get(header['kid']) if isinstance(header['kid'], str) else None
        if key is None:
            raise AdminFault('invalid_admin_token', 401)
        try:
            key.verify(_decode(signature), (head + '.' + body).encode('ascii'), padding.PKCS1v15(), hashes.SHA256())
        except (InvalidSignature, ValueError):
            raise AdminFault('invalid_admin_token', 401) from None
        if claims.get('iss') != self.issuer or claims.get('aud') != 'mrad.admin.v1':
            raise AdminFault('invalid_admin_token', 401)
        now = int(self.clock())
        if any(type(claims.get(field)) is not int for field in ('iat', 'nbf', 'exp')):
            raise AdminFault('invalid_admin_token', 401)
        if not 0 <= claims['iat'] <= now or claims['nbf'] > now or claims['nbf'] < claims['iat'] or \
                claims['exp'] <= now or not 0 < claims['exp'] - claims['iat'] <= self.maximum_lifetime:
            raise AdminFault('invalid_admin_token', 401)
        for field in ('sub', 'sid'):
            value = claims.get(field)
            if not isinstance(value, str) or not value or len(value) > 256 or value.isspace() or any(ord(c) < 32 for c in value):
                raise AdminFault('invalid_admin_token', 401)
        scope = claims.get('scope')
        if not isinstance(scope, str) or len(scope) > 2048 or not re.fullmatch(r'[A-Za-z0-9_.:-]+(?: [A-Za-z0-9_.:-]+)*', scope):
            raise AdminFault('invalid_admin_token', 401)
        identity = AdminIdentity(self.issuer, claims['sub'], claims['sid'], frozenset(scope.split(' ')))
        try:
            active = self.active_session(identity)
        except Exception:
            raise AdminFault('admin_authority_unavailable', 503) from None
        if active is not True:
            raise AdminFault('admin_session_inactive', 401)
        return identity
