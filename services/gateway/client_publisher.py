"""Generate reviewed client assets and explicit baseline changes; never deploy them."""
import hashlib,json,os,re,shutil,tempfile,uuid,zipfile
from pathlib import Path
from urllib.parse import urlsplit
EDITION='meowopia-custom'
REALM='s4a21'
ADAPTER='s4a21-cn-local-20261013'
EXE_SHA='1f8244d3f7309bbe2fde4299e1863a894f6b28d5707bf01732980585b20b00dd'
ORIGIN='https://launcher.invalid/launcher/client/meowopia-custom/s4a21/releases/'
PROTECTED={'data','updates','screenshot','screenshots','capture','captures','log','logs','launcher.public.json','meowlauncher.exe','meowmanager.exe','meow-launcher.exe','meow-manager.exe','oolauncher.exe','oomanager.exe','oo launcher.exe','oo manager.exe','oo-launcher.exe','oo-manager.exe'}
SETTINGS={'.ini','.cfg','.xml','.json'}
class PublicationError(ValueError):
    """A controlled, operator-facing validation message."""

ROOT_SETTINGS={'GameGaurd.ini','GameNative.ini','AutoFire.ini','CombatPower.ini','DpsMeter.ini','EquipmentSwap.ini','ImeFix.ini','MultiInstance.ini','audio.xml'}
def safe_path(name):
    if not isinstance(name,str) or not name or len(name.encode())>512 or any(c in '\\:*?"<>|' or ord(c)<32 or 127<=ord(c)<=159 for c in name):raise PublicationError('不安全的客户端文件名')
    parts=name.split('/')
    if parts[0].lower() in PROTECTED or parts[0].lower().startswith('.oo-'):raise PublicationError('客户端清单包含私人或启动器数据')
    for part in parts:
        stem=part.split('.')[0].upper()
        if part in ('','.','..') or part.endswith(('.',' ')) or stem in ('CON','PRN','AUX','NUL') or re.fullmatch(r'(COM|LPT)[1-9]',stem):raise PublicationError('不安全的客户端路径')
    return name
def regular(path):
    if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise PublicationError('客户端包含链接或重解析点')
    if not path.is_file():raise PublicationError('客户端清单文件不存在')
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
    return h.hexdigest()
def inventory(root):
    if root.is_symlink() or getattr(root,'is_junction',lambda:False)():raise PublicationError('客户端目录不能是链接')
    result=[]
    for path in root.iterdir():
        if path.name.lower() in PROTECTED or path.name.startswith('.oo-'):continue
        if path.is_file() and (path.name in ROOT_SETTINGS or path.suffix.lower() in ('.dll','.exe') or path.name in ('Script.pvf','DNF.ico','dstr.dat')):regular(path);result.append(path)
    for folder in ('ImagePacks2','SoundPacks'):
        base=root/folder
        if not base.is_dir():raise PublicationError('客户端缺少 '+folder)
        if base.is_symlink() or getattr(base,'is_junction',lambda:False)():raise PublicationError('资源目录不能是链接')
        for directory,folders,files in os.walk(base,followlinks=False):
            for name in folders:
                p=Path(directory)/name
                if p.is_symlink() or getattr(p,'is_junction',lambda:False)():raise PublicationError('资源目录包含链接')
            for name in files:
                path=Path(directory)/name;regular(path)
                if path.suffix.lower() not in ('.log','.tmp','.bak','.dmp'):result.append(path)
    return sorted(result,key=lambda p:p.relative_to(root).as_posix().lower())
def build(body,parent,*,edition=EDITION,realm=REALM,adapter=ADAPTER,artifact_prefix=ORIGIN,exe_sha=EXE_SHA):
    if not isinstance(body,dict) or set(body)-{'directory','version','baseline','buildArchive','archiveRoot'}:raise PublicationError('客户端发布参数不正确')
    if not isinstance(body.get('directory'),str) or not Path(body['directory']).is_absolute():raise PublicationError('请选择客户端绝对目录')
    root=Path(body['directory']);
    for ancestor in (root,*root.parents):
        if ancestor.is_symlink() or getattr(ancestor,'is_junction',lambda:False)():raise PublicationError('客户端目录不能包含链接')
    root=root.resolve(strict=True)
    regular(root/'DNF.exe')
    if digest(root/'DNF.exe')!=exe_sha:raise PublicationError('DNF.exe 版本与 S4A21 适配器不一致')
    version=body.get('version','')
    if not isinstance(version,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,63}',version):raise PublicationError('资源版本格式不正确')
    prefix_url=urlsplit(artifact_prefix)
    if prefix_url.scheme!='https' or not prefix_url.hostname or prefix_url.username or prefix_url.password or prefix_url.query or prefix_url.fragment or not artifact_prefix.endswith('/'):raise PublicationError('可信资源地址不正确')
    baseline=body.get('baseline')
    old={}
    if baseline is not None:
        if not isinstance(baseline,dict) or baseline.get('schemaVersion')!=1 or any(baseline.get(k)!=v for k,v in [('edition',edition),('realm',realm),('adapter',adapter)]):raise PublicationError('基线清单属于其他发行版、区服或适配器')
        if not isinstance(baseline.get('files'),list) or len(baseline['files'])>50000:raise PublicationError('基线文件清单不正确')
        for entry in baseline['files']:
            if not isinstance(entry,dict) or not re.fullmatch('[0-9a-fA-F]{64}',entry.get('sha256','')) or type(entry.get('size')) is not int or entry['size']<0:raise PublicationError('基线文件记录不正确')
            name=safe_path(entry.get('path'));key=name.upper()
            if key in old:raise PublicationError('基线包含重复文件')
            old[key]=entry
    archive_root=body.get('archiveRoot','')
    if archive_root:safe_path(archive_root)
    make_archive=body.get('buildArchive',baseline is None)
    if type(make_archive) is not bool:raise PublicationError('压缩包选项不正确')
    if archive_root and not make_archive:raise PublicationError('外层目录仅适用于完整 ZIP')
    files=[];new=[];replaced=[];settings_updated=[];unchanged=[];mapping=[];seen=set()
    for path in inventory(root):
        name=safe_path(path.relative_to(root).as_posix());key=name.upper()
        if key in seen:raise PublicationError('客户端包含大小写重复路径')
        seen.add(key);size=path.stat().st_size
        if size>17179869184:raise PublicationError('资源文件过大')
        sha=digest(path);previous=old.get(key)
        unchanged_file=previous and previous['sha256'].lower()==sha and previous['size']==size
        url=previous.get('url','') if unchanged_file else ''
        if not isinstance(url,str) or not url.startswith(artifact_prefix) or any(x in url for x in ('/../','/./','%','?','#','\\')):url=artifact_prefix+version+'/files/'+sha+'.bin';mapping.append((path,sha))
        entry={'path':name,'size':size,'sha256':sha,'url':url};files.append(entry)
        if not previous:new.append(name)
        elif unchanged_file:unchanged.append(name)
        elif path.suffix.lower() in SETTINGS:settings_updated.append(name)
        else:replaced.append(name)
    if not any(f['path']=='DNF.exe' and f['sha256']==exe_sha for f in files):raise PublicationError('DNF.exe 版本与 S4A21 适配器不一致')
    required={'DNF.exe','az.dll','ijl15.dll','GameGaurd.dll','GameGaurd.ini','Script.pvf'}
    if not required.issubset({f['path'] for f in files}):raise PublicationError('客户端缺少必需的主程序、插件或默认配置')
    if any(not any(f['path'].startswith(folder+'/') for f in files) for folder in ('ImagePacks2','SoundPacks')):raise PublicationError('客户端资源目录不能为空')
    if len(files)>50000:raise PublicationError('客户端文件数量超过限制')
    removed=[entry['path'] for key,entry in old.items() if key not in seen and Path(entry['path']).suffix.lower() not in SETTINGS]
    preserved_missing_settings=[entry['path'] for key,entry in old.items() if key not in seen and Path(entry['path']).suffix.lower() in SETTINGS]
    manifest={'schemaVersion':1,'edition':edition,'realm':realm,'adapter':adapter,'version':version,'files':files,'removeFiles':removed}
    if len(json.dumps(manifest,ensure_ascii=False).encode())>8388608:raise PublicationError('客户端清单超过大小限制')
    parent=Path(parent).resolve()
    if parent.is_relative_to(root):raise PublicationError('发布输出目录不能在游戏客户端内')
    parent.mkdir(parents=True,exist_ok=True)
    need=sum(path.stat().st_size for path,_ in mapping)+(sum(f['size'] for f in files) if make_archive else 0)
    if shutil.disk_usage(parent).free<need:raise PublicationError('磁盘空间不足以生成待发布资源')
    if make_archive:
        mapped={sha for _,sha in mapping}
        for path in inventory(root):
            value=digest(path)
            if value not in mapped:mapping.append((path,value));mapped.add(value)
    output=parent/uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='.client-publish-',dir=parent) as temporary:
        stage=Path(temporary);assets=stage/'assets/files';assets.mkdir(parents=True)
        for path,sha in mapping:
            target=assets/(sha+'.bin')
            if not target.exists():shutil.copyfile(path,target)
            if digest(target)!=sha:raise PublicationError('源文件在打包时变化，发布已停止')
        if make_archive:
            archive=stage/'assets/client.zip'
            with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
                for f in files:
                    path=assets/(f['sha256']+'.bin');regular(path)
                    if digest(path)!=f['sha256']:raise PublicationError('源文件在压缩时变化，发布已停止')
                    z.write(path,((archive_root+'/') if archive_root else '')+f['path'])
            manifest['archive']={'url':artifact_prefix+version+'/client.zip','size':archive.stat().st_size,'sha256':digest(archive)}
            if archive_root:manifest['archiveRoot']=archive_root
        review={'readyForProduction':False,'version':version,'edition':edition,'added':new,'replaced':replaced,'removed':removed,'unchanged':unchanged,'defaultSettingsUpdated':settings_updated,'playerSettingsPreserved':preserved_missing_settings,'instruction':'删除只作用于旧清单受管且未修改资源。INI/CFG/XML/JSON 已有玩家设置不会覆盖或删除。上传并核验所有资源直链后，最后发布 manifest.json；本工具不自动上线。'}
        (stage/'manifest.pending.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(stage/'changes.pending.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        os.rename(stage,output)
    return {'id':output.name,'path':str(output),'manifest':str(output/'manifest.pending.json'),'review':str(output/'changes.pending.json'),'files':len(files),'added':len(new),'replaced':len(replaced),'removed':len(removed),'settingsPreserved':len(settings_updated)+len(preserved_missing_settings),'archive':str(output/'assets/client.zip') if make_archive else None,'published':False}
