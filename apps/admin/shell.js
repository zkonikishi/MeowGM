// Task navigation only; all management APIs keep their own authorization.
const managerPages=[['overview','首页'],['deploy','服务器'],['accounts','玩家管理'],['launcher','客户端发布'],['notices','公告与活动'],['mods','MOD 与工具'],['settings','设置']];
const secondaryGroups={deploy:[['connections','连接服务器'],['deploy','网关组件'],['logs','操作记录']]};
const pageGroups={connections:'deploy',logs:'deploy'};
const pages=new Map();let selectedPage='overview';
for(const key of [...managerPages.map(p=>p[0]),'connections','logs']){const page=document.createElement('div');page.dataset.managerPage=key;page.hidden=true;pages.set(key,page);$('workspace').append(page);}
function moveTo(key,node){pages.get(key).append(node);}
moveTo('accounts',$('game-refresh').closest('section'));moveTo('accounts',$('account-operation-fields').closest('section'));
moveTo('notices',$('revision').parentElement);moveTo('notices',document.querySelector('.columns'));moveTo('notices',$('announcements').closest('section'));moveTo('notices',exportSection);
moveTo('connections',connectionSection);moveTo('deploy',deploymentSection);moveTo('logs',$('audit').closest('section'));
pages.get('overview').innerHTML=`<section class="welcome-card"><small>ARAD · 服主管理</small><h2>先连接服务器，再开始管理</h2><p>这里汇总当前连接和下一步操作。配置已保存与服务已接通会分别显示。</p><div class="setup-steps"><span class="complete">1 手动配置</span><span id="setup-connection-step">2 连接服务器</span><span id="setup-ready-step">3 验证服务</span></div><div class="server-summary"><div><small>当前服务器</small><strong id="overview-server">正在读取配置…</strong><p id="overview-connection">尚未检测连接</p></div><button id="overview-check" class="primary">检测服务连接</button></div><button data-open-page="connections">设置服务器连接</button></section><section><h2>开始一项工作</h2><div class="capability-grid"><article><h3>查看玩家</h3><p>查询游戏账号和角色，检查平台封禁状态。</p><button data-open-page="accounts">打开玩家管理</button></article><article><h3>准备客户端</h3><p>把服务器公开配置安装到准备发给玩家的客户端目录。</p><button data-open-page="launcher">制作客户端配置</button></article><article><h3>编辑公告</h3><p>保存草稿，生成供官网发布的文件。</p><button data-open-page="notices">打开公告管理</button></article></div></section>`;
const help={connections:'连接服务器上的 GM 和账号服务。保存配置后，请检测是否能访问。',deploy:'安装、更新或卸载本工具管理的入场网关。此处不控制游戏服进程。',accounts:'查询玩家账号与角色。查询需要先接通 GM，封禁需要平台管理接口。',launcher:'服主准备完整客户端包，玩家只需解压后运行启动器。',notices:'编辑本地公告草稿并生成待发布文件。生成文件不会自动上线。',logs:'查看本工具的操作记录。游戏日志和实时服务控制台尚未接通。',settings:'查看软件能力与连接说明。服务地址和密钥在“服务器”中配置。'};
for(const [key,text] of Object.entries(help)){const p=document.createElement('p');p.className='page-purpose';p.textContent=text;pages.get(key).prepend(p);}
function planned(key,title,text){const details=document.createElement('details');details.className='planned-capabilities';details.innerHTML=`<summary>${title}</summary><p>${text}</p>`;pages.get(key).append(details);}
planned('accounts','其他玩家管理功能','邮件、物品与点券修改仍在对接，当前没有可用的发放入口。');
planned('notices','活动与兑换码','活动、奖励与 CDK 共用接口尚未接通。');
planned('deploy','GM 工具与服务控制台','GM 安装更新、设备绑定以及游戏服启停、实时日志仍在接通。115US 远程控制接口尚未完成。');
pages.get('settings').innerHTML='<section><h2>连接与数据</h2><p>连接信息保存在本机，服务器使用自己的 SSH 或管理接口验证权限。</p><button data-open-page="connections">修改服务器连接</button></section><section><h2>AI 辅助</h2><p>AI 连接与日志分析尚未接通。后续会先展示发送内容与配置建议，再由管理员应用。</p></section>';
const nav=document.querySelector('aside nav');nav.replaceChildren();nav.setAttribute('aria-label','管理任务');
for(const [key,title] of managerPages){const button=document.createElement('button');button.textContent=title;button.dataset.openPage=key;nav.append(button);}
document.querySelector('aside p').textContent='86s4a21 服主管理';document.querySelector('aside small').textContent='MeowGM';
const header=document.querySelector('main>header');header.querySelector('small').textContent='ARAD MANAGER';
const subnav=document.createElement('nav');subnav.id='manager-subnav';subnav.setAttribute('aria-label','服务器任务');header.after(subnav);
const notice=document.querySelector('main>.notice');notice.hidden=true;
function managerMode(mode){document.body.dataset.managerMode=mode;document.querySelector('aside').hidden=mode!=='manage';document.querySelector('main').hidden=false;header.hidden=mode!=='manage';subnav.hidden=mode!=='manage'||!secondaryGroups[pageGroups[selectedPage]||selectedPage];}
function managerPage(key){selectedPage=pages.has(key)?key:'overview';const group=pageGroups[selectedPage]||selectedPage;for(const [name,page] of pages)page.hidden=name!==selectedPage;for(const button of nav.children)button.setAttribute('aria-current',String(button.dataset.openPage===group));header.querySelector('h1').textContent=managerPages.find(([name])=>name===group)[1];subnav.replaceChildren();for(const [name,title] of secondaryGroups[group]||[]){const button=document.createElement('button');button.dataset.openPage=name;button.textContent=title;button.setAttribute('aria-current',String(name===selectedPage));subnav.append(button);}subnav.hidden=document.body.dataset.managerMode!=='manage'||!secondaryGroups[group];document.querySelector('main').scrollTop=0;}
document.addEventListener('click',event=>{const button=event.target.closest('[data-open-page]');if(button)managerPage(button.parentElement===nav&&button.dataset.openPage==='deploy'?'connections':button.dataset.openPage);});
async function refreshOverview(){try{const c=await api('/api/admin/connections');$('overview-server').textContent=c.platformUrl||c.gmUrl||'尚未选择服务器';$('overview-connection').textContent=(c.gmUrl||c.platformUrl)?'连接配置已保存；请检测服务':'先填写服务器连接，再检测服务。';$('setup-connection-step').classList.toggle('complete',!!(c.gmUrl||c.platformUrl));}catch{}}
$('overview-check').onclick=()=>run(async()=>{const data=await api('/api/admin/connections/check',{});const parts=Object.entries(data);$('overview-connection').textContent=parts.map(([name,r])=>(name==='gm'?'游戏管理':'账号服务')+'：'+(r.ok?'可访问':'未接通')).join('；');$('setup-ready-step').classList.toggle('complete',parts.length>0&&parts.every(([,r])=>r.ok));});
new MutationObserver(()=>{managerMode($('workspace').hidden?'login':'manage');if(!$('workspace').hidden)refreshOverview();}).observe($('workspace'),{attributes:true,attributeFilter:['hidden']});
$('publish').textContent='保存草稿';$('reload').textContent='重新加载草稿';$('game-refresh').textContent='查询玩家';
managerPage('overview');managerMode($('workspace').hidden?'login':'manage');

// The native layer selects this edition's update source.
if(window.__TAURI__?.core){
 const section=document.createElement('section');section.innerHTML='<h2>MeowGM · 软件更新</h2><p id="manager-about">正在读取版本…</p><p id="manager-edition">发行版信息由当前程序提供。</p><button id="manager-update-check">检查更新</button> <button id="manager-update-download" hidden>下载并校验新版</button> <button id="manager-update-open" hidden>打开新版文件夹</button><p id="manager-update-status" role="status">尚未检查</p><small>新版通过官网代理下载，校验 SHA256 和程序身份。下载后退出管理器，将同名 EXE 替换到原目录；本地连接配置保持原数据位置。</small>';
 pages.get('settings').prepend(section);
 const nativeInvoke=(name)=>window.__TAURI__.core.invoke(name);
 let updating=false;
 async function updateCheck(){if(updating)return;updating=true;$('manager-update-check').disabled=true;$('manager-update-status').textContent='正在在线检查…';$('manager-update-download').hidden=true;
  try{const result=await nativeInvoke('manager_check_update');$('manager-update-status').textContent=result.available?`发现新版 ${result.version}`:'当前已是最新版本';$('manager-update-download').hidden=!result.available;}
  catch(e){$('manager-update-status').textContent=e?.message||'更新服务暂不可用';}
  finally{updating=false;$('manager-update-check').disabled=false;}
 }
 $('manager-update-check').onclick=updateCheck;
 $('manager-update-download').onclick=async()=>{if(updating)return;updating=true;$('manager-update-check').disabled=true;$('manager-update-download').disabled=true;$('manager-update-open').hidden=true;$('manager-update-status').textContent='正在下载并校验 SHA256，请稍候…';
  try{const r=await nativeInvoke('manager_download_update');if(!r.verified||r.program!=='MeowGM')throw{message:'程序身份校验失败'};$('manager-update-status').textContent=`${r.version} 已下载，SHA256 和程序身份校验通过。退出后替换原管理器文件即可。`;$('manager-update-open').hidden=false;}
  catch(e){$('manager-update-status').textContent=e?.message||'下载失败，现有程序未修改';}
  finally{updating=false;$('manager-update-check').disabled=false;$('manager-update-download').disabled=false;}
 };
 $('manager-update-open').onclick=()=>nativeInvoke('manager_open_update').catch(e=>{$('manager-update-status').textContent=e?.message||'文件夹无法打开';});
 nativeInvoke('manager_about').then(info=>{$('manager-about').textContent=`${info.product} ${info.version}`;$('manager-edition').textContent=info.notes+(info.author?' · 项目维护/改动作者：'+info.author:'');}).catch(()=>{$('manager-about').textContent='版本读取失败';});
 updateCheck();
}

const modSection=document.createElement('section');modSection.innerHTML='<small>115US · 工具链</small><h2>MOD 管理</h2><p>旧 MeowCore 插件宿主与插件商城已移除。</p><p>115US 使用上游 modkit 与启动器编排。当前尚未完成适配，暂不提供安装、启停或商城入口。</p>';pages.get('mods').append(modSection);
const profileSection=document.createElement('section');profileSection.innerHTML='<h2>本机管理员</h2><p id="admin-profile">登录后读取账号</p><form id="rename-admin-form"><label>新的管理员账号<input id="rename-admin-name" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_-]{3,32}" autocomplete="username"></label><label>当前密码<input id="rename-admin-password" type="password" required maxlength="256" autocomplete="current-password"></label><button class="primary">保存账号名称</button></form><p id="rename-admin-status" role="status">改名不会修改游戏账号，也不会更改管理员密码。</p>';pages.get('settings').prepend(profileSection);
$('rename-admin-form').onsubmit=e=>{e.preventDefault();run(async()=>{const r=await api('/api/admin/profile',{username:$('rename-admin-name').value,password:$('rename-admin-password').value});$('rename-admin-password').value='';$('admin-profile').textContent='当前管理员：'+r.username;$('username').value=r.username;$('rename-admin-status').textContent='账号名称已保存，其他登录会话已失效。';});};
async function loadProfile(){try{const r=await api('/api/admin/profile');window.managerProfile=r;document.querySelector('aside small').textContent='MeowGM · '+r.version;profileSection.hidden=!!r.localMode;$('admin-profile').textContent='当前管理员：'+r.username;$('rename-admin-name').value=r.username;window.dispatchEvent(new CustomEvent('meow-profile',{detail:r}));}catch{}}
new MutationObserver(()=>{if(!$('workspace').hidden)loadProfile();}).observe($('workspace'),{attributes:true,attributeFilter:['hidden']});if(!$('workspace').hidden)loadProfile();
