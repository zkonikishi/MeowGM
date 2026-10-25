"""Explicit adapter for PascalCase library records, not an enabled HTTP endpoint.

Final HTTP serialization/path still requires Max's host contract. Never infer an
administrator role from player participation or caller-supplied Owner fields.
"""
import re
from mrad_audit import AuditError


def _text(value, maximum=256):
    if not isinstance(value, str) or not value or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise AuditError('拍卖查询字段无效')
    return value


def _guid(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value):
        raise AuditError('拍卖查询标识无效')
    return value


def _integer(value, minimum=0):
    # Python json parses integer tokens precisely. Never accept a float/bool.
    if type(value) is int:
        number = value
    elif isinstance(value, str) and re.fullmatch(r'0|[1-9][0-9]{0,18}', value):
        number = int(value)
    else:
        raise AuditError('拍卖数值必须是精确整数')
    if not minimum <= number <= 9223372036854775807:
        raise AuditError('拍卖数值超出范围')
    return str(number)


def adapt_library_search(payload, *, expected_instance, expected_query_id,
                         authorized_scopes, page_size=100, mine=False):
    """Call only with independently host-verified scopes and original query context.

    No upstream call. No participant-to-admin authorization conversion. Own-query
    authorization remains the upstream host's responsibility on every request.
    """
    if 'gm.audit.auction' not in authorized_scopes:
        raise AuditError('无拍卖管理审计权限', 403)
    _text(expected_instance)
    _guid(expected_query_id)
    if type(page_size) is not int or not 1 <= page_size <= 100 or type(mine) is not bool:
        raise AuditError('拍卖分页条件无效', 400)
    if not isinstance(payload, dict) or payload.get('Version') != 'auction-query-v1':
        raise AuditError('尚不支持该拍卖查询版本', 409)
    if payload.get('InstanceId') != expected_instance or payload.get('QueryId') != expected_query_id:
        raise AuditError('拍卖实例或查询上下文已变化', 409)
    rows = payload.get('Items')
    if not isinstance(rows, list) or len(rows) > page_size:
        raise AuditError('拍卖分页数量无效')
    result, seen = [], set()
    states = {'Listed': 'listed', 'Sold': 'sold', 'Cancelled': 'cancelled', 'Expired': 'expired'}
    for row in rows:
        if not isinstance(row, dict) or row.get('State') not in states:
            raise AuditError('拍卖状态无效')
        if not mine and row['State'] != 'Listed':
            raise AuditError('公开挂牌查询含非有效状态')
        listing = _guid(row.get('ListingId'))
        if listing in seen:
            raise AuditError('拍卖分页含重复挂牌')
        seen.add(listing)
        # Whitelist only. Do not forward Owner, UID/CID, snapshots or service secrets.
        result.append({'listingId': listing, 'itemId': _integer(row.get('ItemId'), 1),
                       'name': _text(row.get('Name'), 512), 'category': _text(row.get('Category')),
                       'quantity': _integer(row.get('Quantity'), 1), 'price': _integer(row.get('Price'), 1),
                       'expiresAt': _integer(row.get('ExpiresAt')), 'revision': _integer(row.get('Revision'), 1),
                       'state': states[row['State']]})
    cursor = payload.get('NextCursor')
    if cursor is not None:
        if not isinstance(cursor, dict) or cursor.get('QueryId') != expected_query_id:
            raise AuditError('拍卖游标查询不匹配', 409)
        context = cursor.get('Context')
        if not isinstance(context, str) or not re.fullmatch(r'[A-F0-9]{64}', context):
            raise AuditError('拍卖游标上下文无效')
        after = _guid(cursor.get('AfterId'))
        if not result or after != result[-1]['listingId']:
            raise AuditError('拍卖游标不对应本页末尾', 409)
        cursor = {'context': context, 'afterId': after, 'queryId': expected_query_id}
    return {'version': 'gm-auction-view-v1', 'sourceVersion': 'auction-query-v1',
            'instanceId': expected_instance, 'queryId': expected_query_id, 'items': result,
            'nextCursor': cursor, 'writeEnabled': False, 'gameEntryVerified': False}
