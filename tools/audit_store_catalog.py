"""Verify storefront gift IDs against an existing CN PVF resource index, read-only.

This is catalog evidence, never approval, checkout, payment or delivery.
"""
import argparse
import json
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone


def audit(catalog, database):
    metadata = dict(database.execute('SELECT key,value FROM metadata'))
    if metadata.get('complete') != 'true':
        raise ValueError('PVF resource index is not complete')
    if not isinstance(catalog, dict) or not isinstance(catalog.get('items'), list):
        raise ValueError('Store catalog structure is invalid')
    results, seen_products = [], set()
    for product in catalog['items']:
        product_id = product.get('id')
        if not isinstance(product_id, str) or not product_id or product_id in seen_products:
            raise ValueError('Missing or duplicate storefront product ID')
        seen_products.add(product_id)
        variants = product.get('variants')
        if not isinstance(variants, list) or not variants:
            variants = [product]
        seen_variants = set()
        for variant in variants:
            item_id = variant.get('itemId')
            issues = []
            if not isinstance(item_id, str) or not re.fullmatch(r'[1-9][0-9]{0,9}', item_id) or int(item_id) > 4294967295:
                results.append({'productId': product_id, 'itemId': None, 'issues': ['invalid_item_id']})
                continue
            if item_id in seen_variants:
                issues.append('duplicate_variant_item_id')
            seen_variants.add(item_id)
            row = database.execute('SELECT name,kind,type FROM item WHERE id=?', (int(item_id),)).fetchone()
            entries = database.execute('SELECT COUNT(*) FROM package_entry WHERE container_id=?', (int(item_id),)).fetchone()[0]
            if row is None:
                issues.append('item_missing_from_current_cn_catalog')
            else:
                if row[2] != '[cera package]':
                    issues.append('not_a_cera_package')
                if not row[0] or '\ufffd' in row[0]:
                    issues.append('cn_name_unavailable')
                if variant.get('name') != row[0]:
                    issues.append('variant_name_differs_from_cn_catalog')
            if entries == 0:
                issues.append('package_contents_not_indexed')
            if 'directEntries' in variant and variant['directEntries'] != entries:
                issues.append('declared_contents_count_mismatch')
            results.append({'productId': product_id, 'itemId': item_id, 'cnName': row[0] if row else None,
                            'kind': row[1] if row else None, 'type': row[2] if row else None,
                            'indexedContentRows': entries, 'issues': issues})
    return {'checkedAt': datetime.now(timezone.utc).isoformat(), 'resourceSource': metadata.get('source'),
            'products': len(seen_products), 'variants': len(results),
            'variantsWithIssues': sum(bool(row['issues']) for row in results), 'items': results,
            'catalogEvidenceOnly': True, 'purchaseEnabledByThisCheck': False,
            'contentApproved': False, 'paymentVerified': False, 'gameDeliveryVerified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog', type=Path)
    parser.add_argument('resource_index', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    index = args.resource_index.resolve(strict=True)
    if not index.name.endswith('.items-v2.db'):
        parser.error('Expected PVF items-v2 resource index, never a game save')
    with sqlite3.connect(index.as_uri() + '?mode=ro', uri=True) as database:
        report = audit(json.loads(args.catalog.read_text(encoding='utf-8')), database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'items'}, ensure_ascii=True))


if __name__ == '__main__':
    main()
