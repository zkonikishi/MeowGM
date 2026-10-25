// Read-only C# server workspace. This page never calls the Go GM bridge.
(()=>{
 'use strict';
 const page=pages.get('mrad');
 page.innerHTML=`<section id="mrad-panel"><h2>Mrad后台系统 · 只读管理（本机工具）</h2>
 <p>连接本机服务端，查询账号、角色和技能点状态。</p>
 <form id="mrad-settings"><label for="mrad-url">服务端地址</label><input id="mrad-url" type="url" value="http://127.0.0.1:7000" required spellcheck="false" aria-describedby="mrad-url-help"><p id="mrad-url-help">使用本机 IP 和服务端 HTTP 端口，默认 7000。</p><button type="submit">保存地址</button><button type="button" id="mrad-connect" class="primary">连接服务端</button><button type="button" id="mrad-disconnect">断开</button></form>
 <p id="mrad-state" role="status" aria-live="polite">尚未连接</p>
 <p><button id="mrad-check" type="button">检查当前实例与资源</button><button id="mrad-export" type="button">导出脱敏诊断</button></p>
 <section aria-labelledby="mrad-evidence-title"><h3 id="mrad-evidence-title">联调诊断与验收</h3><dl><dt>管理接口实例</dt><dd id="mrad-instance-evidence">尚未校验</dd><dt>账号列表</dt><dd id="mrad-account-evidence">尚未读取</dd><dt>当前账号角色</dt><dd id="mrad-character-evidence">尚未读取</dd><dt>客户端游戏认证</dt><dd>未验收</dd><dt>客户端角色界面</dt><dd>未验收</dd><dt>选角进入城镇</dt><dd>未验收</dd></dl><p>账号、角色存档及已选角连接用于诊断，不能据此判断客户端已进入城镇。</p></section>
 <details><summary>能力与资源状态</summary><ul id="mrad-resources"></ul><ul id="mrad-capabilities"></ul></details>
 <section aria-labelledby="mrad-audit-title"><h3 id="mrad-audit-title">只读资产与归属审计</h3><p>UID 是用户 ID，CID 是角色 ID。邮件入队、附件领取与拍卖成交分别核验，普通玩家登录不提供管理权限。</p><label for="mrad-audit-kind">审计类别</label><select id="mrad-audit-kind"><option value="delivery">稳定投递回执</option><option value="claim">附件领取回执</option><option value="ownership">UID / CID 归属</option><option value="auction">拍卖成交与资产</option></select><button id="mrad-audit-refresh" type="button">检查审计接口</button><p id="mrad-audit-state" role="status">尚未检查；不会自动查询玩家审计数据。</p><dl id="mrad-audit-contract"><dt>稳定关联</dt><dd>业务投递键、请求 ID、操作 ID</dd><dt>归属</dt><dd>可信 UID、CID、区服与映射版本</dd><dt>分页</dt><dd>游标绑定实例和筛选条件，不能将有限列表当作全部历史</dd><dt>成交核对</dt><dd>买方扣款、卖方收益、手续费分别核验</dd></dl><p id="mrad-audit-count">未读取回执。</p><button id="mrad-audit-next" type="button" disabled>下一页（待受控分页接口）</button></section>
 <div class="mrad-grid"><section><h3>账号</h3><button id="mrad-refresh" type="button">读取账号列表</button><label for="mrad-filter">筛选已读取账号</label><input id="mrad-filter" type="search" placeholder="账号名或内部 ID"><p id="mrad-accounts-note"></p><label for="mrad-account">选择账号</label><select id="mrad-account" size="8" aria-label="账号列表"></select><dl id="mrad-account-detail"></dl></section>
 <section><h3>角色</h3><button id="mrad-refresh-characters" type="button">刷新当前账号角色</button><p id="mrad-characters-note">选择账号后读取角色。</p><label for="mrad-character">选择角色</label><select id="mrad-character" size="8" aria-label="角色列表"></select><dl id="mrad-character-detail"></dl><button id="mrad-progress" type="button">读取角色进度</button><p id="mrad-online" role="status"></p><dl id="mrad-progress-detail"></dl></section></div></section>`;
 const link=document.createElement('link');link.rel='stylesheet';link.href='/mrad.css';document.head.append(link);
 let connection=null,accounts=[],characters=[],working=false,dirty=false,epoch=0,accountCount=null,characterCount=null;
 const el=id=>document.getElementById('mrad-'+id);
 const ready=()=>connection?.state==='ready'&&!dirty;
 function clearCharacters(){characters=[];characterCount=null;el('character').replaceChildren();el('character-detail').replaceChildren();el('progress-detail').replaceChildren();el('online').textContent='';el('characters-note').textContent='选择账号后读取角色。';}
 function clearPlayers(){epoch++;accounts=[];accountCount=null;el('account').replaceChildren();el('account-detail').replaceChildren();el('accounts-note').textContent='';clearCharacters();}
 function controls(){
  for(const node of page.querySelectorAll('button,input,select'))node.disabled=working;
  el('audit-next').disabled=true;
  el('connect').disabled=working||dirty;
  el('disconnect').disabled=working||!connection?.connectionId;
  el('check').disabled=working||!ready();el('export').disabled=working||dirty;
  el('refresh').disabled=working||!ready()||!connection.capabilities?.console;
  el('account').disabled=working||!ready();el('character').disabled=working||!ready();
  el('refresh-characters').disabled=working||!ready()||!el('account').value||!connection.capabilities?.console;
  el('progress').disabled=working||!ready()||!el('character').value||!connection.capabilities?.administration;
  el('instance-evidence').textContent=ready()?'最近校验通过 · PID '+connection.processId+(connection.lastCheckedAt?' · '+new Date(connection.lastCheckedAt).toLocaleString():''):'尚未校验或连接已失效';
  el('account-evidence').textContent=accountCount===null?'尚未读取':'已读取 '+accountCount+' 个'+(accountCount===2000?'（达到上限，可能不全）':'');
  el('character-evidence').textContent=characterCount===null?'尚未读取':'当前账号已读取 '+characterCount+' 个'+(characterCount===2000?'（达到上限，可能不全）':'');
 }
 function list(parent,values){parent.replaceChildren();for(const text of values){const li=document.createElement('li');li.textContent=text;parent.append(li);}}
 function drawStatus(data){
  if(connection?.connectionId!==data.connectionId)clearPlayers();connection=data;
  el('state').textContent=data.message+(data.processId?' · 服务进程 '+data.processId:'');
  const names={console:'账号查询',mail:'邮件组件',content:'游戏资源',strings:'名称文本',index:'物品索引',icons:'图标资源',administration:'角色管理'};
  list(el('resources'),Object.entries(names).map(([key,label])=>label+'：'+(data.capabilities?data.capabilities[key]?'已就绪':'未就绪':'待连接')));
  list(el('capabilities'),(data.capabilities?.items||[]).map(item=>(item.label||item.key)+'：'+(item.implemented?'服务端已实现':'尚未实现')+'（'+(item.method||'')+'）'));
  controls();
 }
 function detail(target,row,fields){target.replaceChildren();for(const [key,label] of fields){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=row?.[key]===undefined?'未知':typeof row[key]==='boolean'?(row[key]?'是':'否'):String(row[key]??'—');target.append(dt,dd);}}
 async function execute(fn){if(working)return;working=true;controls();try{await fn();}catch(error){
  clearAudit();clearPlayers();connection=null;el('resources').replaceChildren();el('capabilities').replaceChildren();el('state').textContent=error.message;
 }finally{working=false;controls();}}
 async function query(resource,extra={}){
  const token=epoch,id=connection?.connectionId;
  const result=await api('/api/admin/mrad/read',{connectionId:id,resource,...extra});
  if(token!==epoch||id!==connection?.connectionId||result.connectionId!==id)throw Error('管理对象已变化，请重新读取');
  connection.lastCheckedAt=result.lastCheckedAt;
  return result;
 }
 function drawAccounts(){
  const selected=el('account').value,filter=el('filter').value.toLocaleLowerCase();
  el('account').replaceChildren();
  for(const row of accounts){if(!String(row.accountName||'').toLocaleLowerCase().includes(filter)&&!row.accountId.includes(filter))continue;const option=document.createElement('option');option.value=row.accountId;option.textContent=(row.accountName||'未命名')+' · '+row.accountId;el('account').append(option);}
  el('account').value=selected;
  if(!el('account').value){el('account-detail').replaceChildren();clearCharacters();}
 }
 function clearAudit(){el('audit-count').textContent='未读取回执。';el('audit-state').textContent='尚未检查；不会自动查询玩家审计数据。';}
 el('audit-kind').onchange=clearAudit;
 el('audit-refresh').onclick=()=>execute(async()=>{
  clearAudit();el('audit-state').textContent='正在检查受控审计接口…';
  const result=await api('/api/admin/mrad/audit');
  if(result.available!==false||result.version!==1||result.items?.length)throw Error('审计接口合同尚未启用，不能展示未经验证的回执');
  el('audit-state').textContent='不可用：服务端尚未提供受权限保护的审计分页与回执接口。';
  el('audit-count').textContent='没有读取投递、领取、归属或拍卖数据；当前仅支持账号与角色只读查询。';
 });
 el('filter').oninput=()=>{epoch++;drawAccounts();controls();};
 el('url').oninput=()=>{dirty=true;clearPlayers();el('state').textContent='地址已编辑，请保存后连接';controls();};
 el('settings').onsubmit=event=>{event.preventDefault();execute(async()=>{const result=await api('/api/admin/mrad/settings',{baseUrl:el('url').value});dirty=false;clearPlayers();drawStatus(result);el('url').value=result.baseUrl;});};
 el('connect').onclick=()=>execute(async()=>{clearPlayers();drawStatus(await api('/api/admin/mrad/connect',{}));});
 el('disconnect').onclick=()=>execute(async()=>{clearPlayers();drawStatus(await api('/api/admin/mrad/disconnect',{}));});
 el('check').onclick=()=>execute(async()=>{clearPlayers();drawStatus(await api('/api/admin/mrad/check',{connectionId:connection.connectionId}));});
 el('export').onclick=()=>execute(async()=>{
  let failure='';
  if(ready())try{drawStatus(await api('/api/admin/mrad/check',{connectionId:connection.connectionId}));}
  catch(error){failure=error.message;clearPlayers();connection=null;el('resources').replaceChildren();el('capabilities').replaceChildren();}
  const report=await api('/api/admin/mrad/diagnostics');
  const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json;charset=utf-8'}));
  const download=document.createElement('a');download.href=url;download.download='Mrad-diagnostic-'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';download.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  el('state').textContent=(failure?'实例检查未通过：'+failure+'；':'')+'已导出脱敏诊断，仅含实例、资源及查询数量，游戏流程仍未验收。';
 });
 el('refresh').onclick=()=>execute(async()=>{clearPlayers();const result=await query('accounts');accounts=result.items;accountCount=accounts.length;drawAccounts();el('accounts-note').textContent='已读取 '+accounts.length+' 个账号。'+(result.possiblyTruncated?'已达服务端 2000 行上限，结果可能不全；筛选仅作用于已读取账号。':'');});
 async function loadCharacters(){
  epoch++;clearCharacters();const id=el('account').value;if(!id)return;
  const row=accounts.find(item=>item.accountId===id);
  detail(el('account-detail'),row,[['accountId','内部 ID'],['accountName','账号名'],['disabled','已禁用'],['characters','角色数量'],['cashBalance','点券余额'],['lastLogin','最近登录']]);
  const result=await query('characters',{accountId:id});characters=result.items;characterCount=characters.length;
  for(const character of characters){const option=document.createElement('option');option.value=character.characterId;option.textContent=character.name+' · Lv.'+character.level+' · '+character.characterId;el('character').append(option);}
  el('character').value='';el('characters-note').textContent='已读取 '+characters.length+' 个角色。'+(result.possiblyTruncated?'已达 2000 行上限，结果可能不全。':'');
 }
 el('account').onchange=()=>execute(loadCharacters);
 el('refresh-characters').onclick=()=>execute(loadCharacters);
 el('character').onchange=()=>{epoch++;el('online').textContent='';el('progress-detail').replaceChildren();const row=characters.find(item=>item.characterId===el('character').value);detail(el('character-detail'),row,[['characterId','角色内部 ID'],['name','角色名'],['level','等级'],['job','职业编号'],['growth','转职编号'],['gold','金币'],['experience','经验'],['pendingMail','待领取邮件']]);controls();};
 el('progress').onclick=()=>execute(async()=>{
  el('progress-detail').replaceChildren();el('online').textContent='正在查询…';
  const result=await query('progress',{accountId:el('account').value,characterId:el('character').value});
  el('online').textContent=typeof result.data.requiresReselect==='boolean'?(result.data.requiresReselect?'该账号存在已选角的在线连接；不能据此判定已进城。':'查询时该账号没有已选角的在线连接；游戏流程仍未验收。'):'服务端未提供在线选角状态。';
  detail(el('progress-detail'),result.data,[['revision','存档版本'],['totalSp','SP 总量'],['remainingSp','剩余 SP'],['totalTp','TP 总量'],['remainingTp','剩余 TP'],['questCount','可规划主线数量']]);
 });
 // Loading settings never connects to the game server automatically.
 async function load(){await execute(async()=>{const result=await api('/api/admin/mrad/status');el('url').value=result.baseUrl;dirty=false;drawStatus(result);});}
 new MutationObserver(()=>{if($('workspace').hidden){clearPlayers();connection=null;controls();}else load();}).observe($('workspace'),{attributes:true,attributeFilter:['hidden']});
 controls();if(!$('workspace').hidden)load();
 let dedicatedApplied=false;
 function dedicatedMode(){
  if(dedicatedApplied||!window.managerProfile?.mradOnly||!$('gmToolsNav'))return;
  dedicatedApplied=true;document.body.dataset.mradOnly='true';
  for(const button of $('meowMainNav').children)button.hidden=!['管理大厅','Mrad 只读管理'].includes(button.textContent);
  for(const button of $('gmToolsNav').children)button.hidden=button.dataset.tool!=='mrad';
  $('gmGlobalTarget').hidden=true;
  for(const button of document.querySelectorAll('#titlebar .tb-actions button'))button.hidden=!button.hasAttribute('data-native');
  document.querySelector('#titlebar .tb-title').textContent='MeowGM · Mrad后台系统只读工具';
  const home=$('meowLobby');home.replaceChildren();
  const heading=document.createElement('h1');heading.textContent='Mrad 只读管理开发测试包';
  const note=document.createElement('p');note.textContent='本机连接诊断、账号与角色查询。客户端认证、角色界面与进城另行验收。';
  const open=document.createElement('button');open.className='btn';open.textContent='打开只读管理';
  open.onclick=()=>$('gmToolsNav').querySelector('[data-tool="mrad"]').click();
  const quit=document.createElement('button');quit.className='btn';quit.textContent='退出 GM 网页';
  quit.onclick=async()=>{try{await api('/api/desktop/quit',{});$('gmTools').close();note.textContent='GM 网页服务已退出，可以关闭此标签页。游戏服务未受影响。';for(const button of document.querySelectorAll('button'))button.disabled=true;}catch(error){note.textContent=error.message;}};
  home.append(heading,note,open,quit);open.click();
 }
 window.addEventListener('meow-profile',dedicatedMode);window.addEventListener('meow-gm-view-ready',dedicatedMode);dedicatedMode();
})();
