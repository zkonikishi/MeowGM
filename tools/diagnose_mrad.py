"""Read-only account/character diagnostics; does not start a game server or open SQLite."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services' / 'gateway'))
from mrad_client import MradClient, MradError
from mrad_transport import DEFAULT_URL


def diagnose(base_url=DEFAULT_URL, account_id=None, character_id=None):
    if character_id is not None and account_id is None:
        raise MradError('查询角色进度时须同时指定账号 ID', 400)
    # Only this tool's endpoint settings are written, in an automatically removed directory.
    with tempfile.TemporaryDirectory(prefix='mrad-diagnostic-') as directory:
        client = MradClient(directory)
        try:
            client.save({'baseUrl': base_url})
            status = client.connect({})
            connection = status['connectionId']
            accounts = client.read({'resource': 'accounts', 'connectionId': connection})
            result = {'status': 'readable', 'baseUrl': status['baseUrl'], 'processId': status['processId'],
                      'accountCount': len(accounts['items']), 'accountsPossiblyTruncated': accounts['possiblyTruncated'],
                      'schema': status['capabilities'].get('schema'),
                      'resources': {key: status['capabilities'][key] for key in
                                    ('console', 'mail', 'content', 'index', 'administration')},
                      'writeEnabled': False, 'gameEntryVerified': False,
                      'gameAcceptance': {'authenticationVerified': False, 'characterScreenVerified': False, 'townEntryVerified': False},
                      'evidenceScope': 'GM HTTP reads only; stored characters and requiresReselect do not prove town entry'}
            if account_id is not None:
                chars = client.read({'resource': 'characters', 'connectionId': connection, 'accountId': account_id})
                result.update(characterCount=len(chars['items']), charactersPossiblyTruncated=chars['possiblyTruncated'])
                if character_id is not None:
                    if not any(row['characterId'] == str(character_id) for row in chars['items']):
                        raise MradError('所选角色不在此账号的已读取列表中；请核对归属及列表上限', 409)
                    progress = client.read({'resource': 'progress', 'connectionId': connection,
                                            'accountId': account_id, 'characterId': character_id})['data']
                    result['selectedCharacter'] = {key: progress.get(key) for key in
                                                    ('level', 'job', 'requiresReselect', 'revision')}
            result['lastCheckedAt'] = client.status()['lastCheckedAt']
            return result
        finally:
            client.close()


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default=DEFAULT_URL)
    parser.add_argument('--account-id', help='exact decimal internal account ID')
    parser.add_argument('--character-id', help='exact decimal character ID, requires --account-id')
    args = parser.parse_args()
    try:
        result = diagnose(args.base_url, args.account_id, args.character_id)
    except MradError as exc:
        print(json.dumps({'status': 'unavailable', 'httpStatus': exc.status, 'error': str(exc),
                          'writeEnabled': False, 'gameEntryVerified': False,
                          'gameAcceptance': {'authenticationVerified': False, 'characterScreenVerified': False, 'townEntryVerified': False}}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
