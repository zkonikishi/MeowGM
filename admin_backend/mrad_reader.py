"""Project existing Mrad read client results; its connection is configured by host.

No connect/settings/disconnect driver is exposed remotely. No window credential
or internal resource path is returned. Not enabled until the trusted host wires it.
"""
from .security import AdminFault


class MradReaders:
    def __init__(self, client):
        self.client = client

    def bindings(self):
        return {key: self.status if key == 'status' else self._reader(key)
                for key in ('status', 'accounts', 'characters', 'progress')}

    def status(self, identity, query):
        status = self.client.status()
        caps = status.get('capabilities') or {}
        return {'available': status.get('state') == 'ready', 'state': status.get('state'),
                'lastCheckedAt': status.get('lastCheckedAt'),
                'resources': {key: caps.get(key) is True for key in ('console', 'mail', 'content', 'strings', 'index', 'icons', 'administration')},
                'writeEnabled': False}

    def _reader(self, resource):
        def read(identity, query):
            status = self.client.status()
            if status.get('state') != 'ready' or not status.get('connectionId'):
                raise AdminFault('admin_resource_unavailable', 503)
            result = self.client.read({'resource': resource, 'connectionId': status['connectionId'], **query})
            fields = {
                'accounts': ('accountId', 'accountName', 'disabled', 'characters'),
                'characters': ('characterId', 'accountId', 'name', 'level', 'job', 'growth'),
                'progress': ('revision', 'totalSp', 'remainingSp', 'totalTp', 'remainingTp', 'requiresReselect'),
            }[resource]
            def project(row):
                return {key: row[key] for key in fields if key in row}
            if resource == 'progress':
                return {'data': project(result['data']), 'writeEnabled': False}
            return {'items': [project(row) for row in result['items']],
                    'possiblyTruncated': result.get('possiblyTruncated') is True, 'writeEnabled': False}
        return read
