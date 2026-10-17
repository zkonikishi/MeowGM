"""Export saved local announcements into a complete website snapshot for review."""
import argparse
from contextlib import closing
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

def export(base, draft, now):
    result=json.loads(json.dumps(base))
    known={item['id'] for item in result['items']}
    for item in draft['announcements']:
        title=item['title'].strip();body=item['body'].strip()
        if not title or not body:raise ValueError('Each exported announcement requires a title and body')
        ident='oo-'+hashlib.sha256((title+'\n'+body).encode()).hexdigest()[:24]
        if ident in known:continue
        result['items'].append({'id':ident,'category':'notice','title':title,'summary':body[:300],'body':body,'publishedAt':now,'updatedAt':now,'url':'https://launcher.invalid/news/?article='+ident,'realms':['s4a21']})
        known.add(ident)
    result['updatedAt']=now
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,required=True,help='Current complete canonical website snapshot')
    parser.add_argument('--database',type=Path,default=Path(__file__).resolve().parents[1]/'services/gateway/data/gateway.sqlite3')
    parser.add_argument('--validator',type=Path,required=True,help='Website owner validate-content.py')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reason',required=True)
    parser.add_argument('--planned-at',required=True,help='Proposed publication time in UTC, ending Z')
    args=parser.parse_args()
    receipt=args.output.with_suffix('.handoff.json')
    if not args.reason.strip() or not args.planned_at.endswith('Z'):raise ValueError('Reason and UTC proposed publication time are required')
    dt.datetime.fromisoformat(args.planned_at[:-1]+'+00:00')
    if args.output.exists() or receipt.exists() or args.output.resolve()==args.base.resolve():raise ValueError('Choose new output files; existing files are never overwritten')
    base_raw=args.base.read_bytes()
    with closing(sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        revision,body=db.execute('SELECT revision,body FROM state WHERE id=1').fetchone()
    draft=json.loads(body)
    now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    snapshot=export(json.loads(base_raw),draft,now)
    raw=(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n').encode()
    with tempfile.TemporaryDirectory() as directory:
        candidate=Path(directory)/'content.json';candidate.write_bytes(raw)
        validation=subprocess.run([sys.executable,str(args.validator.resolve()),str(candidate)],capture_output=True,text=True,encoding='utf-8')
        if validation.returncode:raise ValueError('Website validator rejected export: '+validation.stderr.strip())
    metadata={'state':'review_required','revision':revision,'baseSha256':hashlib.sha256(base_raw).hexdigest(),'sha256':hashlib.sha256(raw).hexdigest(),'reason':args.reason.strip(),'plannedAt':args.planned_at,'exportedAt':now,'maintenanceChanged':False,'localMaintenanceProposal':{'enabled':draft['maintenance'],'message':draft['maintenanceMessage']},'note':'Complete snapshot; existing articles and maintenance preserved. New local notices added. Editing or deletion of existing website articles requires owner review.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('xb') as file:file.write(raw)
    with receipt.open('x',encoding='utf-8') as file:json.dump(metadata,file,ensure_ascii=False,indent=2)
    print(str(args.output.resolve()));print('SHA256 '+metadata['sha256']);print('Validated draft only; not approved or published.')

if __name__=='__main__':main()
