"""Report remaining identifiers without editing compatibility or attribution."""
import argparse
import json
from pathlib import Path
import re

PATTERN = re.compile(r'115|cn|地下城与勇士|地下城|国服|dnf|dfo', re.IGNORECASE)
EXCLUDED = {'.git', '.runtime', 'dist', 'node_modules', 'target', 'bin', 'obj', '__pycache__'}
TEXT = {'.md', '.txt', '.html', '.js', '.cjs', '.py', '.rs', '.cs', '.toml', '.json', '.ps1', '.yaml', '.yml'}


def scan(root):
    hits = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if not path.is_file() or any(part in EXCLUDED for part in relative.parts) or path.suffix not in TEXT:
            continue
        if path.stat().st_size > 2_000_000:
            continue
        try:
            lines = path.read_text(encoding='utf-8-sig').splitlines()
        except UnicodeError:
            continue
        attribution = path.name.startswith(('LICENSE', 'NOTICE', 'UPSTREAM', 'upstream'))
        for number, line in enumerate(lines, 1):
            tokens = sorted({match.group() for match in PATTERN.finditer(line)})
            if tokens:
                hits.append({'path': relative.as_posix(), 'line': number, 'tokens': tokens,
                             'review': 'attribution-preserved' if attribution else 'manual-compatibility-review'})
    return {'product': 'Mrad Max', 'publicVersion': None, 'completeCleanup': False,
            'policy': 'Literal case-insensitive scan; language tags and substrings also match. No source or secrets copied.',
            'excludedDirectories': sorted(EXCLUDED), 'remainingLines': len(hits), 'remaining': hits}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = scan(root)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'remainingLines': report['remainingLines'], 'completeCleanup': False}))
