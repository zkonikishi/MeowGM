"""Fail-closed read-only audit contract; no upstream transport is enabled yet."""
import re

KINDS = ('delivery', 'claim', 'ownership', 'auction')
STATES = {'delivery': {'pending', 'queued', 'failed'},
          'claim': {'unclaimed', 'claimed', 'expired', 'cancelled'},
          'ownership': {'active', 'disabled', 'revoked'},
          'auction': {'listed', 'sold', 'cancelled', 'expired', 'pending', 'failed'}}
FIELDS = ('operationId', 'deliveryKey', 'requestId', 'uid', 'cid', 'realm',
          'state', 'revision', 'createdAt', 'updatedAt', 'errorCode',
          'listingId', 'buyerDebit', 'sellerCredit', 'fee')


class AuditError(ValueError):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def unavailable():
    return {'version': 1, 'available': False, 'state': 'unavailable',
            'message': '服务端尚未提供受权限保护的审计分页与回执接口',
            'kinds': list(KINDS), 'items': [], 'nextCursor': None,
            'writeEnabled': False, 'gameEntryVerified': False}


def normalize_page(payload, *, kind, query_id, authorized_scopes,
                   expected_uid=None, expected_cid=None, expected_realm=None):
    """Only call after trusted server-side authorization, never browser claims.

    This validates a proposed envelope, not a currently deployed Max API.
    query_id must identify the instance and full filters, including UID/realm.
    """
    if kind not in KINDS:
        raise AuditError('未知审计类别', 400)
    if 'gm.audit.' + kind not in authorized_scopes:
        raise AuditError('无此审计权限', 403)
    if not isinstance(query_id, str) or not query_id:
        raise AuditError('审计查询上下文无效', 400)
    if not isinstance(payload, dict) or payload.get('version') != 1 or payload.get('queryId') != query_id:
        raise AuditError('审计版本或查询上下文不匹配', 409)
    if payload.get('available') is not True:
        return unavailable()
    rows = payload.get('items')
    if not isinstance(rows, list) or len(rows) > 100:
        raise AuditError('审计分页结构或数量无效')
    cursor = payload.get('nextCursor')
    if cursor is not None and (not isinstance(cursor, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,512}', cursor)):
        raise AuditError('审计游标格式无效')
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or row.get('state') not in STATES[kind]:
            raise AuditError('审计状态无效')
        clean = {}
        for field in FIELDS:
            if field not in row:
                continue
            value = row[field]
            if not isinstance(value, str) or not value or len(value) > 256 or any(ord(c) < 32 for c in value):
                raise AuditError('审计字段须为有界精确字符串')
            if field in ('buyerDebit', 'sellerCredit', 'fee', 'revision') and not re.fullmatch(r'0|[1-9][0-9]{0,38}', value):
                raise AuditError('审计金额或版本无效')
            clean[field] = value
        if any(not clean.get(key) for key in ('operationId', 'uid', 'realm', 'state')):
            raise AuditError('审计记录缺少关联字段')
        for key, expected in (('uid', expected_uid), ('cid', expected_cid), ('realm', expected_realm)):
            if expected is not None and clean.get(key) != expected:
                raise AuditError('审计记录归属或区服与查询条件不匹配', 409)
        if clean['operationId'] in seen:
            raise AuditError('审计页含重复回执')
        seen.add(clean['operationId'])
        result.append(clean)
    return {'version': 1, 'available': True, 'state': 'ready', 'kind': kind,
            'queryId': query_id, 'items': result, 'nextCursor': cursor,
            'writeEnabled': False, 'gameEntryVerified': False}
