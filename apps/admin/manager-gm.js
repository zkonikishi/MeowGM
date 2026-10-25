// Manual native GM preparation. Saving settings never starts the helper.
(()=>{
 const page=document.createElement('div');page.dataset.managerPage='native-gm';page.hidden=true;
 page.innerHTML='<section><h2>本地 GM 连接</h2><p>先在服务器连接中选择本地 Mrad Max 根目录，再填写客户端目录。连接前会备份现有 SQLite 存档；首次解析 PVF 可能需要较长时间。</p><label>Mrad Max 客户端目录<input id="native-gm-client" placeholder="包含 Script.pvf 的绝对路径" maxlength="2048"></label><button id="native-gm-load">读取已保存配置</button> <button id="native-gm-save">保存目录</button> <button id="native-gm-connect">连接本地 GM</button> <button id="native-gm-disconnect">断开</button><p id="native-gm-status" role="status">尚未读取；不会自动连接。</p><pre id="native-gm-progress"></pre><small>此连接仅管理本地存档，不代表游戏进程已启动。技能点管理已接入角色页；其他写操作、云端 GM 和内存补丁暂未开放。</small></section>';
 pages.set('native-gm',page);$('workspace').append(page);
 let timer=null,revision=0;
 function render(data){
  $('native-gm-status').textContent=data.message+(data.backup?' · 备份：'+data.backup:'');
  $('native-gm-progress').textContent=(data.progress||[]).join('\n');
  $('native-gm-connect').disabled=data.state==='preparing'||data.state==='ready';
  $('native-gm-save').disabled=data.state==='preparing';
  window.meowGMConnection=data;
  window.dispatchEvent(new CustomEvent('meow-gm-connection',{detail:data}));
 }
 function stop(){revision++;clearTimeout(timer);timer=null;}
 function poll(token){timer=setTimeout(async()=>{
  try{const data=await api('/api/admin/gm/status');if(token!==revision)return;render(data);if(data.state==='preparing')poll(token);}
  catch(error){if(token===revision)$('native-gm-status').textContent=error.message;}
 },1000);}
 $('native-gm-load').onclick=()=>run(async()=>{stop();const data=await api('/api/admin/gm/status');$('native-gm-client').value=data.clientDirectory||'';render(data);if(data.state==='preparing')poll(revision);});
 $('native-gm-save').onclick=()=>run(async()=>{stop();render(await api('/api/admin/gm/settings',{clientDirectory:$('native-gm-client').value}));});
 $('native-gm-connect').onclick=()=>run(async()=>{stop();render(await api('/api/admin/gm/settings',{clientDirectory:$('native-gm-client').value}));const data=await api('/api/admin/gm/connect',{});render(data);if(data.state==='preparing')poll(revision);});
 $('native-gm-disconnect').onclick=()=>run(async()=>{stop();render(await api('/api/admin/gm/disconnect',{}));});
 window.addEventListener('beforeunload',stop);
})();
