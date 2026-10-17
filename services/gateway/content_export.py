"""Generate reviewed-content handoff artifacts, never publish website files."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import ssl
import urllib.request
import uuid
from content_contract import validate

def create_export(store,body):
    if not isinstance(body,dict) or set(body)-{'baseRaw','reason','plannedAt'}:raise ValueError('公告导出字段不正确')
    reason=body.get('reason','');planned=body.get('plannedAt','')
    if not isinstance(reason,str):raise ValueError('修改理由格式无效')
    reason=reason.strip()
    if not reason or len(reason)>500 or not isinstance(planned,str) or not planned.endswith('Z'):raise ValueError('请填写修改理由和UTC拟发布时间')
    dt.datetime.fromisoformat(planned[:-1]+'+00:00')
    raw=body.get('baseRaw')
    if raw is None:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        try:
            with opener.open('https://launcher.invalid/launcher/content.json',timeout=8) as response:base=response.read(524289)
        except Exception:raise ValueError('无法读取官网当前内容，请导入官网完整 content.json 再导出') from None
    else:
        if not isinstance(raw,str):raise ValueError('官网内容格式无效')
        base=raw.encode('utf-8')
    if len(base)>524288:raise ValueError('官网内容超出启动器支持大小')
    snapshot=json.loads(base);validate(snapshot)
    if len(snapshot['items'])>200:raise ValueError('公告数量超出启动器支持范围')
    draft=store.read();now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    known={item['id'] for item in snapshot['items']}
    for item in draft['announcements']:
        title=item['title'].strip();text=item['body'].strip()
        if not title or not text:raise ValueError('导出公告必须填写标题和正文')
        ident='oo-'+hashlib.sha256((title+'\n'+text).encode()).hexdigest()[:24]
        if ident in known:continue
        known.add(ident)
        snapshot['items'].append({'id':ident,'category':'notice','title':title,'summary':text[:300],'body':text,'publishedAt':now,'updatedAt':now,'url':'https://launcher.invalid/news/?article='+ident,'realms':['s4a21']})
    snapshot['updatedAt']=now;validate(snapshot)
    exported=(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n').encode()
    if len(exported)>524288 or len(snapshot['items'])>200:raise ValueError('导出公告超过启动器支持范围')
    metadata={'state':'review_required','revision':draft['revision'],'baseSha256':hashlib.sha256(base).hexdigest(),'sha256':hashlib.sha256(exported).hexdigest(),'reason':reason,'plannedAt':planned,'exportedAt':now,'maintenanceChanged':False,'localMaintenanceProposal':{'enabled':draft['maintenance'],'message':draft['maintenanceMessage']}}
    directory=Path(store.path).parent/'exports'/str(uuid.uuid4());directory.mkdir(parents=True)
    content=directory/'content.json';handoff=directory/'content.handoff.json'
    content.write_bytes(exported);handoff.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'state':'review_required','contentPath':str(content.resolve()),'handoffPath':str(handoff.resolve()),'sha256':metadata['sha256'],'message':'已生成校验通过的交接文件，等待官网审核发布；未修改线上内容。'}
