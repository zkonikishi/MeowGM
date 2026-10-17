"""Prepare a private, local client publication for operator review. No upload."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/gateway'))
from client_publisher import build
parser=argparse.ArgumentParser()
parser.add_argument('--client-directory',required=True)
parser.add_argument('--version',required=True)
parser.add_argument('--output-parent',required=True)
parser.add_argument('--baseline')
parser.add_argument('--full-zip',action='store_true')
parser.add_argument('--archive-root',default='')
args=parser.parse_args()
body={'directory':args.client_directory,'version':args.version,'buildArchive':args.full_zip,'archiveRoot':args.archive_root}
if args.baseline:
    path=Path(args.baseline)
    if path.stat().st_size>8388608:parser.error('baseline is larger than 8 MiB')
    body['baseline']=json.loads(path.read_text(encoding='utf-8'))
result=build(body,Path(args.output_parent))
print(json.dumps(result,ensure_ascii=False))
