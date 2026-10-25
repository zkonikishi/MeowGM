"""Read a small Chinese name sample from the existing resource index; never a player DB."""
import argparse
import json
from pathlib import Path
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('resource_index', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    path = args.resource_index.resolve(strict=True)
    if not path.name.endswith('.items-v2.db'):
        parser.error('Expected the existing PVF items-v2 resource index')
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as database:
        metadata = dict(database.execute('SELECT key,value FROM metadata'))
        if metadata.get('complete') != 'true' or not metadata.get('source', '').endswith(':items-v2'):
            raise ValueError('Resource index is incomplete or unrecognized')
        rows = database.execute("SELECT id,name,kind FROM item WHERE instr(name,?)>0 "
                                "AND kind IN ('equipment','stackable') ORDER BY id LIMIT 100", ('剑',)).fetchall()
    if not rows:
        raise ValueError('No Chinese item name sample found')
    result = {'source': {'locale': 'zh-CN', 'realm': 'cn', 'complete': True,
                         'resourceFingerprint': metadata['source']},
              'items': [{'itemId': str(item_id), 'name': name, 'kind': kind} for item_id, name, kind in rows],
              'sampleOnly': True, 'indexTotal': int(metadata['total'])}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'sampleItems': len(rows), 'indexTotal': result['indexTotal'],
                      'readOnlyResourceIndex': True, 'playerDataRead': False}))


if __name__ == '__main__':
    main()
