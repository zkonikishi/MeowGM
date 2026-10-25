"""Menu metadata for the website owner; never an authorization decision."""
from .readonly import ROUTES


MENU = (
    ('gm-status', '服务状态', '/gm/status', '/api/admin/v1/gm/status'),
    ('gm-accounts', '账号查询', '/gm/accounts', '/api/admin/v1/gm/accounts'),
    ('gm-characters', '角色查询', '/gm/characters', '/api/admin/v1/gm/characters'),
    ('gm-progress', '角色进度', '/gm/progress', '/api/admin/v1/gm/progress'),
    ('gm-auction-audit', '拍卖审计', '/gm/audit/auction', '/api/admin/v1/audit/auction'),
)


def menu_for(identity):
    """Host calls only with a verified identity; gateway still enforces scopes."""
    return [{'name': name, 'title': title, 'path': path, 'apiPath': api,
             'requiredScope': ROUTES[api][0], 'readOnly': True}
            for name, title, path, api in MENU if ROUTES[api][0] in identity.scopes]
