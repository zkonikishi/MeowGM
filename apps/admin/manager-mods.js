// Installed server mods are managed only through the bundled upstream modkit.
const managedModsPage=pages.get('mods');managedModsPage.replaceChildren();
const modsPanel=document.createElement('section');modsPanel.innerHTML='<h2>MOD 管理</h2><p>读取当前本地 Mrad Max 环境中的已安装服务端 MOD，使用上游 modkit 保存启用状态。配置状态与服务端上报分开显示。</p><button id="managed-mods-refresh">刷新 MOD 列表</button><p id="managed-mods-status" role="status">尚未读取；不会自动启动游戏。</p><div id="managed-mods-list"></div><small>安装、卸载涉及客户端文件和服务端编译，当前尚未开放；此处支持已安装服务端 MOD 的启用和停用。</small>';managedModsPage.append(modsPanel);
function showManagedMods(data){
  $('managed-mods-list').replaceChildren();
  for(const mod of data.mods){
    const row=document.createElement('article');row.className='managed-mod-row';
    const heading=document.createElement('h3');heading.textContent=mod.name||mod.id;
    const details=document.createElement('p');details.textContent=mod.id+' · '+(mod.version||'版本未知')+' · 配置：'+(mod.enabled?'已启用':'已停用')+' · 最近上报：'+(mod.reportedLive===null?'未知/已过期':mod.reportedLive?'已生效':'未生效');
    if(mod.requiresRestart)details.textContent+=' · 需要重启';if(mod.requiresRebuild)details.textContent+=' · 需要重新编译';
    const dependencies=document.createElement('small');dependencies.textContent='依赖：'+((mod.requires||[]).join('、')||'无声明')+(mod.drift?'；'+mod.drift:'');
    const button=document.createElement('button');button.textContent=mod.enabled?'停用':'启用';button.onclick=()=>run(async()=>{button.disabled=true;try{const result=await api('/api/admin/mod-manager/set',{id:mod.id,enabled:!mod.enabled,module:data.module});showManagedMods(result);$('managed-mods-status').textContent=result.message;}finally{button.disabled=false;}});
    row.append(heading,details,dependencies,button);$('managed-mods-list').append(row);
  }
  if(!data.mods.length)$('managed-mods-list').textContent='所选环境没有已安装的服务端 MOD。';
  $('managed-mods-status').textContent=(data.runtimeFresh?'已读取服务端最近上报；不代表本工具已控制游戏进程。':'服务端实况未知或过期，不能据启用配置判断正在生效。')+(data.note?' '+data.note:'');
}
$('managed-mods-refresh').onclick=()=>run(async()=>{showManagedMods(await api('/api/admin/mod-manager'));});
const activityPage=document.createElement('div');activityPage.dataset.managerPage='activities';activityPage.hidden=true;pages.set('activities',activityPage);$('workspace').append(activityPage);
const activityPanel=document.createElement('section');activityPanel.innerHTML='<h2>游戏活动</h2><p>节日、副本、掉落活动需要对应的 Mrad Max 服务端控制接口。当前上游 GM 未提供统一开启命令，尚不能从此处开启活动。</p><div class="activity-grid"></div><small>签到相关内容来自所选客户端 PVF，运行日期另由服务端日历处理；读取 PVF 不等于开启活动。不会用本地草稿冒充已生效。</small>';activityPage.append(activityPanel);
for(const name of ['节日活动','副本活动','掉落活动']){const row=document.createElement('article');row.className='managed-mod-row';const title=document.createElement('h3');title.textContent=name;const text=document.createElement('p');text.textContent='开启状态未知 · 服务端开关尚未接通';const button=document.createElement('button');button.textContent='开启接口待接入';button.disabled=true;row.append(title,text,button);activityPanel.querySelector('.activity-grid').append(row);}

const clientModsPanel=document.createElement('section');
clientModsPanel.innerHTML='<h2>客户端 MOD</h2><p>使用 GM 设置中保存的客户端目录。清单配置与实际加载分开显示；保存后下次启动生效。</p><button id="client-mods-refresh">刷新客户端 MOD</button><p id="client-mods-status" role="status">尚未读取</p><div id="client-mods-list"></div>';
managedModsPage.append(clientModsPanel);
function showClientMods(data){
 $('client-mods-status').textContent=data.message;
 $('client-mods-list').replaceChildren();
 for(const mod of data.mods){
  const row=document.createElement('article');row.className='managed-mod-row';
  const title=document.createElement('h3');title.textContent=mod.id;
  const text=document.createElement('p');text.textContent=mod.path+' · 配置：'+(mod.enabled?'启用':'停用')+' · 文件：'+(mod.filePresent?'存在':'缺失')+' · 实际加载：未知'+(mod.bypassPossible?' · 宿主可能绕过此开关':'');
  const button=document.createElement('button');button.textContent=mod.enabled?'停用':'启用';button.disabled=!mod.canToggle;
  button.onclick=()=>run(async()=>{button.disabled=true;try{showClientMods(await api('/api/admin/client-mods/set',{id:mod.id,enabled:!mod.enabled,clientDirectory:data.clientDirectory,revision:data.revision}));}finally{button.disabled=!mod.canToggle;}});
  row.append(title,text,button);$('client-mods-list').append(row);
 }
 if(!data.mods.length)$('client-mods-list').textContent='未发现客户端 MOD 清单项。';
}
$('client-mods-refresh').onclick=()=>run(async()=>showClientMods(await api('/api/admin/client-mods')));
