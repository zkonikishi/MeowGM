const connectionSection=document.createElement('section');
connectionSection.innerHTML=`<h2>服务连接</h2><p>保存后立即生效。密钥在本机加密保存，留空保留原值。</p>
<label>GM 地址<input id="connection-gm" placeholder="http://127.0.0.1:5051"></label>
<small>远程 GM 通过本机 SSH 隧道连接。</small>
<label>GM 密码<input id="connection-gm-password" type="password" autocomplete="new-password"></label>
<label class="check"><input id="connection-gm-clear" type="checkbox">清除已保存的 GM 密码</label>
<label>平台地址<input id="connection-platform" placeholder="https://平台服务域名"></label>
<label>平台管理密钥<input id="connection-admin-key" type="password" autocomplete="new-password"></label>
<label class="check"><input id="connection-admin-clear" type="checkbox">清除已保存的平台管理密钥</label>
<label>私有 CA 文件（可选）<input id="connection-ca" placeholder="使用系统受信证书时留空"></label>
<button id="connection-load">读取配置</button> <button id="connection-reset">备份并重置连接</button> <button id="connection-save">保存连接</button> <button id="connection-check">检测已保存连接</button>
<p id="connection-status" role="status">尚未检测。配置完成不代表服务已接通。</p>`;
document.getElementById('workspace').prepend(connectionSection);
const tunnelSection=document.createElement('details');
tunnelSection.innerHTML=`<summary>SSH 专用转发连接</summary><p>仅使用已部署的专用密钥身份；不支持 root 或密码登录。主机记录必须事先核验。</p><label>服务器<input id="tunnel-host" placeholder="服务器 IP 或域名"></label><label>专用用户名<input id="tunnel-user"></label><label>私钥文件<input id="tunnel-key" placeholder="本机绝对路径"></label><label>已验证的 known_hosts 文件<input id="tunnel-known" placeholder="本机绝对路径"></label><label>本机端口<input id="tunnel-port" type="number" min="1024" max="65535" value="15051"></label><button id="tunnel-save">保存转发配置</button> <button id="tunnel-start">连接</button> <button id="tunnel-stop">断开</button> <button id="tunnel-status">刷新状态</button><p id="tunnel-result" role="status">需配置专用身份；尚未连接。</p>`;
connectionSection.append(tunnelSection);
function tunnelShow(data){$('tunnel-result').textContent=data.state+(data.localPort?`；GM 地址：http://127.0.0.1:${data.localPort}（填写上方并保存）`:'');}
$('tunnel-save').onclick=()=>run(async()=>tunnelShow(await api('/api/admin/tunnel/save',{host:$('tunnel-host').value,user:$('tunnel-user').value,keyFile:$('tunnel-key').value,knownHosts:$('tunnel-known').value,localPort:Number($('tunnel-port').value)})));
for(const action of ['start','stop','status'])$('tunnel-'+action).onclick=()=>run(async()=>tunnelShow(await api('/api/admin/tunnel/'+action,{})));
function connectionShow(data){if(data.configurationError)$('connection-status').textContent=data.configurationError;$('connection-gm').value=data.gmUrl;$('connection-platform').value=data.platformUrl;$('connection-ca').value=data.caFile;for(const [id,exists] of [['connection-gm-password',data.gmPasswordSet],['connection-admin-key',data.adminKeySet]]){$(id).value='';$(id).placeholder=exists?'已保存，留空保留':'未配置';}$('connection-gm-clear').checked=false;$('connection-admin-clear').checked=false;}
$('connection-load').onclick=()=>run(async()=>{connectionShow(await api('/api/admin/connections'));if(!$('connection-status').textContent.includes('不可读取'))$('connection-status').textContent='配置已读取；密钥不回显。';});
$('connection-save').onclick=()=>run(async()=>{const clearSecrets=[];if($('connection-gm-clear').checked)clearSecrets.push('gmPassword');if($('connection-admin-clear').checked)clearSecrets.push('adminKey');try{const data=await api('/api/admin/connections',{gmUrl:$('connection-gm').value,platformUrl:$('connection-platform').value,caFile:$('connection-ca').value,gmPassword:$('connection-gm-password').value,adminKey:$('connection-admin-key').value,clearSecrets});connectionShow(data);await loadOperations();$('connection-status').textContent='已加密保存。请检测连接。';}finally{$('connection-gm-password').value='';$('connection-admin-key').value='';}});
$('connection-check').onclick=()=>run(async()=>{$('connection-status').textContent='正在检测…';const data=await api('/api/admin/connections/check',{});$('connection-status').textContent=Object.entries(data).map(([name,r])=>`${name==='gm'?'GM':'平台'}：${r.ok?'通过':'未通过'} · ${r.message}`).join('；');});

const deploymentSection=document.createElement('section');
deploymentSection.innerHTML=`<h2>网关部署 / 卸载</h2><p>部署 86s4a21 入场网关（非赞助版注册服务），仅监听服务器 127.0.0.1:17861。需要 Linux、Python 3.11+、非 root 部署账号、用户 systemd 和已启用 linger。</p><p>复用上方 SSH 服务器、用户名、私钥和主机记录字段，但需要具备执行命令权限的部署身份，GM 专用转发身份不能部署。</p><label>SSH 端口<input id="deploy-port" type="number" value="22"></label><label>平台 HTTPS 地址<input id="deploy-platform" placeholder="https://账号服务域名"></label><label>平台消费密钥<input id="deploy-gateway-key" type="password" autocomplete="new-password"></label><label>游戏准入密钥<input id="deploy-game-key" type="password" autocomplete="new-password"></label><p>部署位置固定为部署用户的 ~/.local/share/oo-admission-managed，服务 oo-admission-managed.service。升级会重启该网关，当前登录流程可能需要重试。密钥仅经加密 SSH 注入服务器，不写本地任务日志。</p><button id="deploy-start">一键部署 / 更新网关</button> <button id="deploy-uninstall">一键卸载网关（保留数据）</button><p>卸载停止并禁用本工具创建的网关，移除服务和已校验程序；保留配置、密钥、数据库和回执，不改游戏服。首次部署健康成功不等于游戏全链路接通。</p><label>待回查任务编号<input id="deploy-query-id" maxlength="32"></label><button id="deploy-query">回查服务器任务</button> <button id="deploy-refresh">刷新本地记录</button><pre id="deploy-result" style="white-space:pre-wrap;overflow-wrap:anywhere" role="status">尚未执行部署。</pre>`;
document.getElementById('workspace').prepend(deploymentSection);
const deploymentLabels={running:'执行中',unknown:'结果未知，请回查服务器',deployed:'已部署，本机健康通过；游戏入场未验收',uninstalled:'已卸载，配置和数据保留',not_installed:'未安装',preflight_failed:'预检失败，检查身份权限、Python、systemd/linger和目录冲突',failed_rolled_back:'部署失败，已恢复此前服务配置',rollback_incomplete:'部署失败，回滚不完整，请检查服务器',uninstall_incomplete:'卸载未完成，请检查服务器'};
async function deploymentRefresh(){const data=await api('/api/admin/deployment/status',{});$('deploy-result').textContent=data.jobs.map(j=>`${j.id} · ${j.host} · ${j.action} · ${deploymentLabels[j.state]||j.state}`).join('\n')||'尚未执行部署。';return data.active;}
async function deploymentStart(action){const body={action,host:$('tunnel-host').value,user:$('tunnel-user').value,keyFile:$('tunnel-key').value,knownHosts:$('tunnel-known').value,port:Number($('deploy-port').value)};if(action==='deploy')Object.assign(body,{platformUrl:$('deploy-platform').value,gatewayKey:$('deploy-gateway-key').value,gameKey:$('deploy-game-key').value});if(action==='status')body.operationId=$('deploy-query-id').value;try{const row=await api('/api/admin/deployment/start',body);if(action!=='status')$('deploy-query-id').value=row.id;await deploymentRefresh();}finally{$('deploy-gateway-key').value='';$('deploy-game-key').value='';}}
$('deploy-start').onclick=()=>run(()=>deploymentStart('deploy'));
$('deploy-uninstall').onclick=()=>run(()=>deploymentStart('uninstall'));
$('deploy-query').onclick=()=>run(()=>deploymentStart('status'));
$('deploy-refresh').onclick=()=>run(deploymentRefresh);
setInterval(()=>{if(!document.getElementById('workspace').hidden)deploymentRefresh().catch(()=>{});},3000);

$('connection-reset').onclick=()=>{if(!confirm('将保留旧配置备份，并重置本机连接。确认继续？'))return;run(async()=>{connectionShow(await api('/api/admin/connections/reset',{confirm:true}));$('connection-status').textContent='旧配置已保留备份，连接已重置。请重新填写并保存。';});};
