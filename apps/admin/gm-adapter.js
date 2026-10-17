// MeowGM backend adapter. Window structure and styles are imported from the upstream GM.
(async()=>{
  'use strict';
  const response=await fetch('/gm-view.html');
  if(!response.ok)throw Error('GM 界面资源加载失败');
  const view=await response.text();
  document.documentElement.classList.add('gm-window');
  document.body.insertAdjacentHTML('beforeend',`<header id="titlebar"><div class="tb-brand"><div class="meow-mark">M</div><div><div class="tb-title">MeowGM · GM 工具</div><div class="tb-sub">115US · 独立管理窗口</div></div></div><div id="gmGlobalTarget" aria-label="全局管理对象"><label for="gmAccount">账号</label><select id="gmAccount"><option value="">请选择账号</option></select><label for="gmStudioRole">角色</label><select id="gmStudioRole" aria-label="当前角色"><option value="">请选择角色</option></select></div><div id="tbDrag" class="tb-drag"></div><div class="tb-actions"><button class="btn" id="gmConnectionOpen">服务器连接</button><button class="btn" id="gmModsOpen">MOD 管理</button><button class="btn" id="gmActivitiesOpen">游戏活动</button><button class="btn" id="gmToolsOpen">工具</button><button class="tb-btn" data-native="minimize" aria-label="最小化">−</button><button class="tb-btn" data-native="maximize" aria-label="最大化">□</button><button class="tb-btn tb-close" data-native="close" aria-label="关闭">×</button></div></header><main id="main"><div id="content">${view}</div></main><dialog id="gmTools"><header class="gm-tools-heading"><h2>MeowGM 工具</h2><button class="btn" id="gmToolsClose">关闭</button></header><nav id="gmToolsNav" aria-label="工具功能"></nav><p id="gmToolsStatus" role="status"></p><div id="gmToolsContent"></div></dialog>`);
  document.title='MeowGM · GM 工具';
  const showVersion=profile=>{if(profile?.version)document.querySelector('#titlebar .tb-sub').textContent='MeowGM '+profile.version+' · 独立管理窗口';};
  showVersion(window.managerProfile);window.addEventListener('meow-profile',event=>showVersion(event.detail));
  const root=$('page-gm');
  const side=document.createElement('aside');side.id='meowMainNav';side.setAttribute('aria-label','GM 功能分类');
  $('main').prepend(side);
  const lobby=document.createElement('section');lobby.id='meowLobby';
  lobby.innerHTML='<h1>管理大厅</h1><p>先确认当前目标，再选择要做的工作。保存目标不会自动连接。</p><article><h2>当前管理目标</h2><p id="meowLobbyTarget">正在读取本机配置…</p><p id="meowLobbyState"></p><button class="btn" id="meowLobbyConfigure">配置目标</button> <button class="btn" id="meowLobbyConnect">本地 GM 连接</button></article><article><h2>已接入的能力</h2><p>本地账号/角色查询；连接本地原生 GM 后读取技能点、增加 SP/TP、查询回执。MOD 支持已安装模块的配置启停，实际生效需服务端证据。</p><button class="btn" id="meowLobbyCharacter">管理角色技能点</button></article><article><h2>待接通的能力</h2><p>云端 HTTPS 管理协议尚未协商；云端目标只保存配置。其他角色写入、游戏活动、AI 分析和进程控制尚未完成。</p><p>MeowLink 尚未封包，无正式安装清单或下载地址。PVF 当前仅支持大小与 SHA256 检测，保护模块未提供。</p></article>';
  $('content').prepend(lobby);
  function showWorkspace(home){lobby.hidden=!home;root.hidden=home;for(const button of side.children)button.classList.toggle('active',button.dataset.section===(home?'home':''));}
  function openGMTab(name){showWorkspace(false);for(const button of side.children)button.classList.toggle('active',button.dataset.section===name);root.querySelector('[data-gm-tab="'+name+'"]').click();}
  for(const [label,key,action] of [
    ['管理大厅','home',()=>showWorkspace(true)],['角色属性','character',()=>openGMTab('character')],['物品与装备','equipment',()=>openGMTab('equipment')],['任务与晶体','quests',()=>openGMTab('quests')],['副本难度','difficulty',()=>openGMTab('difficulty')],
    ['目标与连接','tool',()=>openTool('connections')],['MOD / 插件','tool',()=>openTool('mods')],['PVF / 客户端','tool',()=>openTool('launcher')],['游戏活动','tool',()=>openTool('activities')],['控制台','tool',()=>openTool('deploy')],['设置','tool',()=>openTool('settings')]
  ]){const button=document.createElement('button');button.className='btn';button.dataset.section=key;button.textContent=label;button.onclick=action;side.append(button);}
  $('meowLobbyConfigure').onclick=()=>openTool('connections');$('meowLobbyConnect').onclick=()=>openTool('native-gm');$('meowLobbyCharacter').onclick=()=>openGMTab('character');
  async function refreshLobby(){try{const data=await api('/api/admin/environment');$('meowLobbyTarget').textContent=(data.productMode==='custom'?'自定义（内部）':'通用')+' · '+(data.mode==='cloud'?'云端':'本地')+' · '+(data.root||'尚未填写根目录');$('meowLobbyState').textContent=data.message;$('meowLobbyConnect').disabled=data.mode==='cloud';$('meowLobbyConnect').title=data.mode==='cloud'?'云端管理协议待协商，请切换本地目标后连接':'';}catch(e){$('meowLobbyState').textContent=e.message;}}
  window.addEventListener('meow-environment-saved',refreshLobby);
  window.addEventListener('meow-profile',refreshLobby);
  showWorkspace(true);refreshLobby();
  // Imported controls must never imply an available write operation.
  root.querySelectorAll('button,input,select,textarea').forEach(control=>{
    if(control.matches('[data-gm-tab],#gmRefresh'))return;
    control.disabled=true;control.title='115US 对应管理接口尚未接通';
  });
  root.querySelectorAll('form').forEach(form=>form.addEventListener('submit',e=>e.preventDefault()));
  $('gmResourceStatus').textContent='本地模式 · 账号/角色查询 · 技能点管理需手动连接本地 GM';
  $('gmPrepare').hidden=true;
  let toastTimer;
  function notify(message,error=false){$('gmStatus').textContent=message;$('gmStatus').dataset.error=String(error);$('gmStatus').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{$('gmStatus').hidden=true;},6500);}
  $('gmStatus').onclick=()=>{$('gmStatus').hidden=true;};
  function openTool(key){
    for(const page of $('gmToolsContent').children)page.hidden=page.dataset.managerPage!==key;
    $('gmToolsNav').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.tool===key));
    $('gmToolsStatus').textContent='';
    if(!$('gmTools').open)$('gmTools').showModal();
  }
  for(const [key,label] of [['connections','服务器连接'],['native-gm','本地 GM 连接'],['deploy','服务控制台'],['launcher','客户端发布'],['notices','公告与活动'],['mods','MOD 管理'],['activities','游戏活动'],['logs','操作记录'],['settings','设置']]){
    const page=pages.get(key);page.hidden=true;$('gmToolsContent').append(page);
    const button=document.createElement('button');button.className='btn';button.dataset.tool=key;button.textContent=label;button.onclick=()=>openTool(key);$('gmToolsNav').append(button);
  }
  $('gmToolsClose').onclick=()=>$('gmTools').close();
  $('gmConnectionOpen').onclick=()=>openTool('connections');
  $('gmModsOpen').onclick=()=>openTool('mods');
  $('gmActivitiesOpen').onclick=()=>openTool('activities');
  $('gmToolsOpen').onclick=()=>openTool('settings');
  const mirror=()=>{const text=$('status').textContent;if($('gmTools').open)$('gmToolsStatus').textContent=text;else if($('status').dataset.error==='true')notify(text,true);};
  new MutationObserver(mirror).observe($('status'),{childList:true,characterData:true,subtree:true});
  for(const button of document.querySelectorAll('[data-native]')){
    button.disabled=!window.__TAURI__?.core;
    button.onclick=()=>window.__TAURI__.core.invoke('manager_window_action',{action:button.dataset.native}).catch(e=>notify(String(e),true));
  }
  $('tbDrag').onmousedown=e=>{if(e.button===0&&e.detail===1)window.__TAURI__?.core.invoke('manager_window_action',{action:'drag'}).catch(()=>{});};
  $('tbDrag').ondblclick=()=>window.__TAURI__?.core.invoke('manager_window_action',{action:'maximize'}).catch(()=>{});
  root.querySelector('.gm-tabs').setAttribute('role','tablist');
  root.querySelectorAll('[data-gm-tab]').forEach(button=>{button.setAttribute('role','tab');button.setAttribute('aria-selected',String(button.classList.contains('active')));});
  const paneIds=['gmCharacter','gmCatalog','gmBag','gmMaterials','gmQuests','gmDifficulty','gmData'];
  const panes={character:'gmCharacter',bag:'gmBag',equipment:'gmCatalog',items:'gmCatalog',pets:'gmCatalog',avatar:'gmCatalog',materials:'gmMaterials',quests:'gmQuests',difficulty:'gmDifficulty'};
  for(const button of root.querySelectorAll('[data-gm-tab]'))button.onclick=()=>{
    root.querySelectorAll('[data-gm-tab]').forEach(b=>{const selected=b===button;b.classList.toggle('active',selected);b.setAttribute('aria-selected',String(selected));});
    for(const id of paneIds)$(id).hidden=id!==panes[button.dataset.gmTab];
    root.classList.toggle('gm-studio-page',button.dataset.gmTab==='avatar');
    if(button.dataset.gmTab!=='character'){
      const pane=$(panes[button.dataset.gmTab]);let note=pane.querySelector('.meow-pending');
      if(!note){note=document.createElement('p');note.className='gm-note meow-pending';pane.prepend(note);}
      note.textContent=button.textContent+'的 115US 接口尚未接通，当前不读取或修改游戏数据。';
    }
  };
  let accounts=[],characters=[],requestNumber=0;
  function resetRole(clearOptions=true){if(clearOptions){characters=[];$('gmStudioRole').replaceChildren(new Option('请选择角色',''));}$('gmTarget').textContent='尚未选择角色';for(const id of ['gmLevelNow','gmGoldNow','gmCeraNow'])$(id).textContent='尚未选择角色';$('gmProfessionSummary').textContent='选择角色后显示当前转职分支与觉醒阶段。';}
  $('gmRefresh').onclick=()=>run(async()=>{
    requestNumber++;resetRole();accounts=[];$('gmAccount').replaceChildren(new Option('请选择账号',''));
    try{const data=await api('/api/admin/game/accounts');accounts=data.accounts;for(const account of accounts)$('gmAccount').add(new Option(account.name+' · 内部账号键 '+account.accountId,String(account.accountId)));$('gmResourceStatus').textContent=`已读取 ${accounts.length} 个账号 · 只读模式`;if(!accounts.length)notify('当前环境没有游戏账号');}
    catch(e){$('gmResourceStatus').textContent=e.message;notify(e.message,true);}
  });
  $('gmAccount').onchange=async()=>{
    const accountId=$('gmAccount').value;const request=++requestNumber;resetRole();if(!accountId)return;
    try{const data=await api('/api/admin/game/characters?accountId='+encodeURIComponent(accountId));if(request!==requestNumber)return;characters=data.characters;for(const c of characters)$('gmStudioRole').add(new Option(c.name+' · Lv.'+c.level+' · '+c.jobName,String(c.characterId)));if(!characters.length)notify('该账号尚无角色');}
    catch(e){if(request===requestNumber)notify(e.message,true);}
  };
  $('gmStudioRole').onchange=()=>{
    const character=characters.find(c=>String(c.characterId)===$('gmStudioRole').value);if(!character){resetRole(false);return;}
    $('gmTarget').textContent=character.name+' · Lv.'+character.level+' · '+character.jobName+' · 内部角色键 '+character.characterId;
    $('gmLevelNow').textContent='当前等级：'+character.level;$('gmGoldNow').textContent='余额未读取';$('gmCeraNow').textContent='余额未读取';$('gmProfessionSummary').textContent=character.jobName+' · 转职与觉醒详情尚未读取';
  };
  window.dispatchEvent(new Event('meow-gm-view-ready'));
})().catch(e=>{const message=document.createElement('p');message.setAttribute('role','alert');message.style.cssText='margin:32px;color:#ffaaaa';message.textContent='GM 界面加载失败：'+e.message+'。请重新打开程序。';document.body.append(message);});
