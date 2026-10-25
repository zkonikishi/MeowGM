"""Classify existing JSON evidence only; no PVF loading, SQL, orders or delivery."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def classify(report, handler_source):
    # Positive evidence of a handler family is not proof of a specific PVF instance.
    family_present = all(text in handler_source for text in
                         ('CeraPackageCn115.Parse', '[cera package]', '[usable cera package]', 'opcode == 510'))
    rows = []
    for item in report['items']:
        reasons = []
        status = 'pending_evidence'
        if not item.get('itemId') or 'item_missing_from_current_cn_catalog' in item.get('issues', []):
            reasons.append('current_item_identity_unverified')
        if item.get('type') not in ('[cera package]', '[usable cera package]'):
            status = 'unsupported_in_this_package_flow'
            reasons.append('package_handler_type_not_matched')
        if not family_present:
            reasons.append('current_handler_family_not_confirmed')
        if item.get('indexedContentRows', 0) == 0:
            reasons.append('package_entries_not_available')
        else:
            reasons.append('entry_count_only_not_full_recipe_evidence')
        reasons.extend(['exact_pvf_flags_costs_expiry_and_job_gates_unverified',
                        'nested_random_selection_and_avatar_options_unverified',
                        'mail_claim_and_opening_result_unverified',
                        'approved_immutable_content_manifest_missing'])
        rows.append({'productId': item['productId'], 'itemId': item.get('itemId'),
                     'cnName': item.get('cnName'), 'exactType': item.get('type'),
                     'indexedContentRows': item.get('indexedContentRows', 0), 'status': status,
                     'handlerFamily': 'Cn115PackageOpenHandler / CeraPackageCn115 / C510' if family_present else None,
                     'reasons': reasons, 'saleEnabled': False, 'automaticExpansionAllowed': False})
    return {'checkedAt': datetime.now(timezone.utc).isoformat(),
            'resourceSource': report.get('resourceSource'),
            'handlerSourceSha256': hashlib.sha256(handler_source.encode('utf-8')).hexdigest(),
            'variants': len(rows), 'summary': dict(Counter(row['status'] for row in rows)),
            'fulfillable': 0, 'sourceEvidenceOnly': True, 'gameDeliveryVerified': False, 'items': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('id_report', type=Path)
    parser.add_argument('handler_source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = classify(json.loads(args.id_report.read_text(encoding='utf-8')),
                      args.handler_source.read_text(encoding='utf-8'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'items'}))


if __name__ == '__main__': main()
