"""115US installed server mods, through the upstream CLI only."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime,timezone

class ModManager:
    def __init__(self,environment,tool=None):
        self.environment=environment;self.lock=threading.RLock()
        self.tool=Path(tool) if tool else (Path(sys._MEIPASS)/'tools/meowgm-modkit.exe' if getattr(sys,'frozen',False) else Path('C:/dev-toolchain/tmp/meowgm-modkit.exe'))
    def module(self):
        config=self.environment.read()
        if config['profile']!='115us' or config['mode']!='local' or not config['root']:raise ValueError('请先配置本地 115US 整合包目录；云端 MOD 控制尚未接通')
        root=Path(config['root'])
        if root.is_symlink() or getattr(root,'is_junction',lambda:False)():raise ValueError('环境目录不能是链接')
        root=root.resolve(strict=True)
        module=root/'server/work/dfo-lan'
        if not module.is_dir():module=root
        module=module.resolve(strict=True)
        if not module.is_relative_to(root):raise ValueError('服务端目录越出所选环境')
        go=module/'go.mod'
        if go.is_symlink() or not go.is_file() or go.stat().st_size>65536 or not re.search(r'^module\s+dfolan\s*$',go.read_text(encoding='utf-8-sig'),re.M):raise ValueError('所选目录不是 115US 的 dfolan 服务端模块')
        if go.is_symlink():raise ValueError('服务端模块标识不能是链接')
        mods=module/'mods'
        if mods.is_symlink() or getattr(mods,'is_junction',lambda:False)():raise ValueError('MOD 目录不能是链接')
        count=0
        for current,dirs,files in os.walk(mods,followlinks=False):
            for name in dirs+files:
                path=Path(current)/name;count+=1
                if count>10000:raise ValueError('MOD 目录超过扫描上限')
                if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise ValueError('MOD 目录含链接，已停止操作')
                if path.name in ('mod.json','enabled.json') and path.is_file() and path.stat().st_size>1048576:raise ValueError('MOD 清单文件过大')
        if mods.is_symlink() or getattr(mods,'is_junction',lambda:False)():raise ValueError('MOD 目录不能是链接')
        return module
    def call(self,args,module):
        if not self.tool.is_file():raise ValueError('当前构建缺少上游 modkit 工具')
        try:
            result=subprocess.run([str(self.tool),*args,'--root',str(module)],capture_output=True,timeout=20,creationflags=0x08000000 if os.name=='nt' else 0,cwd=module)
        except subprocess.TimeoutExpired:raise ValueError('modkit 执行超时，结果未知；请刷新状态后再决定是否重试') from None
        if result.returncode:
            message=(result.stderr or result.stdout).decode('utf-8',errors='replace')[:4000]
            raise ValueError('modkit 拒绝操作：'+message)
        return result.stdout
    def list(self):
        with self.lock:
            module=self.module();raw=self.call(['mods','list','--json'],module)
            if len(raw)>2097152:raise ValueError('MOD 列表超出显示上限')
            data=json.loads(raw);items=data.get('mods') or []
            if not isinstance(items,list):raise ValueError('modkit 列表格式无效')
            reports={};fresh=False;runtime=module/'runtime/mods-status.json'
            if runtime.is_file() and not runtime.is_symlink() and runtime.resolve().is_relative_to(module) and runtime.stat().st_size<=1048576:
                try:
                    status=json.loads(runtime.read_text(encoding='utf-8-sig'))
                    written=datetime.fromisoformat(status['writtenAt'].replace('Z','+00:00'))
                    fresh=status.get('schema')==1 and 0<=(datetime.now(timezone.utc)-written).total_seconds()<=45
                    if fresh:reports={item['id']:item for item in status.get('mods',[]) if isinstance(item,dict) and isinstance(item.get('id'),str)}
                except (ValueError,KeyError,TypeError):pass
            for item in items:
                report=reports.get(item.get('id'),{})
                item['reportedLive']=report.get('live') if type(report.get('live')) is bool else None
                item['requiresRestart']=report.get('requiresRestart') if fresh else None
                item['requiresRebuild']=report.get('requiresRebuild') if fresh else None
            return {'mods':items,'note':data.get('note',''),'runtimeFresh':fresh,'module':str(module),'source':'upstream-modkit','gameRunning':None}
    def set_enabled(self,body):
        if not isinstance(body,dict) or set(body)!={'id','enabled','module'} or not isinstance(body['id'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}',body['id']) or type(body['enabled']) is not bool:raise ValueError('MOD 开关参数无效')
        with self.lock:
            module=self.module()
            if not isinstance(body['module'],str) or body['module']!=str(module):raise ValueError('管理环境已改变，请刷新 MOD 列表后再操作')
            installed=self.list()['mods']
            if body['id'] not in {item['id'] for item in installed}:raise ValueError('目标 MOD 未安装')
            if body['enabled']:
                index={item['id']:item for item in installed}
                visited=set()
                def check_dependencies(mod_id,chain):
                    if mod_id in chain:raise ValueError('MOD 依赖存在循环')
                    if mod_id in visited:return
                    for dependency in index[mod_id].get('requires',[]):
                        if dependency not in index or not index[dependency].get('enabled'):raise ValueError('请先安装并启用依赖 MOD：'+dependency)
                        check_dependencies(dependency,chain|{mod_id})
                    visited.add(mod_id)
                check_dependencies(body['id'],set())
            state=module/'mods/enabled.json'
            if state.exists():shutil.copy2(state,state.with_name('enabled.json.before-meowgm-'+str(time.time_ns())))
            self.call(['mods','enable' if body['enabled'] else 'disable','--id',body['id'],'--by','MeowGM'],module)
            result=self.list();item=next((m for m in result['mods'] if m['id']==body['id']),None)
            if item is None or item.get('enabled')!=body['enabled']:raise ValueError('写入后的状态未确认，请刷新检查')
            return {**result,'message':'MOD 配置已保存；实际生效以服务端最新上报为准'}
