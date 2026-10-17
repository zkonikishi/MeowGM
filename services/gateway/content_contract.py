"""Read-only validation of an OO draft or the canonical public feed. No deploy/write."""
import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from urllib.parse import urlsplit, parse_qs

def validate(data):
    def require(ok, message):
        if not ok: raise ValueError(message)
    def timestamp(value, field, optional=False):
        if optional and value is None: return None
        require(isinstance(value,str) and value.endswith('Z'),field+': UTC Z required')
        try: return dt.datetime.fromisoformat(value[:-1]+'+00:00')
        except ValueError: raise ValueError(field+': invalid timestamp')
    def realms(value):
        require(isinstance(value,list) and len(value)>0 and all(x in ('s4a21','115us') for x in value) and len(value)==len(set(value)),'invalid realms')
    def url(value):
        require(isinstance(value,str),'URL must be a string')
        u=urlsplit(value)
        require(u.scheme=='https' and u.netloc=='launcher.invalid' and not u.username,'URL must use canonical website HTTPS origin')
        return u
    require(isinstance(data,dict) and type(data.get('schemaVersion')) is int and data['schemaVersion']==1,'schemaVersion must be 1')
    require(set(data)=={'schemaVersion','updatedAt','items','maintenance'},'unexpected top-level fields')
    updated=timestamp(data['updatedAt'],'updatedAt')
    require(isinstance(data['items'],list) and len(data['items'])<=500,'invalid items')
    ids={}
    for item in data['items']:
        require(isinstance(item,dict),'invalid item')
        required={'id','category','title','summary','body','publishedAt','updatedAt','url','realms'}
        require(required<=set(item) and set(item)<=required|{'relatedUrl'},'unexpected/missing item fields')
        ident=item['id']
        require(isinstance(ident,str) and re.fullmatch('[a-z0-9][a-z0-9-]{0,79}',ident) and ident not in ids,'invalid/duplicate id')
        require(item['category'] in ('notice','news','maintenance'),'invalid category')
        ids[ident]=item
        for key,limit in [('title',160),('summary',1000),('body',20000)]:
            require(isinstance(item[key],str) and 0<len(item[key])<=limit and not any(ord(c)<32 and c not in '\n\t' for c in item[key]),key+': invalid text')
        published=timestamp(item['publishedAt'],'publishedAt')
        changed=timestamp(item['updatedAt'],'item.updatedAt')
        require(published<=changed<=updated,'invalid article timestamp order')
        u=url(item['url'])
        require(u.path=='/news/' and parse_qs(u.query)=={'article':[ident]} and not u.fragment,'detail URL must match id')
        if 'relatedUrl' in item:url(item['relatedUrl'])
        realms(item['realms'])
    m=data['maintenance']
    require(isinstance(m,dict) and set(m)=={'status','updatedAt','realms','plannedStartAt','plannedEndAt','actualStartAt','actualEndAt','noticeId'},'invalid maintenance fields')
    require(m['status'] in ('unknown','scheduled','active','resolved','cancelled'),'invalid maintenance status')
    require(timestamp(m['updatedAt'],'maintenance.updatedAt')<=updated,'maintenance newer than feed')
    realms(m['realms'])
    times={k:timestamp(m[k],k,True) for k in ('plannedStartAt','plannedEndAt','actualStartAt','actualEndAt')}
    for start,end in [('plannedStartAt','plannedEndAt'),('actualStartAt','actualEndAt')]:
        require(not times[end] or (times[start] and times[start]<=times[end]),'invalid maintenance time order')
    require(m['status']!='scheduled' or times['plannedStartAt'] is not None,'scheduled requires planned start')
    require(m['status'] not in ('active','resolved') or times['actualStartAt'] is not None,'actual start required')
    require(m['status']!='resolved' or times['actualEndAt'] is not None,'resolved requires actual end')
    require(m['status']!='active' or times['actualEndAt'] is None,'active cannot have actual end')
    require(m['noticeId'] is None or (m['noticeId'] in ids and ids[m['noticeId']]['category']=='maintenance'),'invalid maintenance notice reference')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('draft',type=pathlib.Path)
    args=parser.parse_args()
    try:
        raw=args.draft.read_bytes()
        if len(raw)>2_000_000:raise ValueError('file exceeds 2MB')
        validate(json.loads(raw.decode('utf-8')))
        print('VALID: schema v1; not approved or published')
    except (ValueError,OSError,KeyError,TypeError) as error:
        print('INVALID: '+str(error),file=sys.stderr);sys.exit(1)
