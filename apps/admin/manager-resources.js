(()=>{
 const section=document.createElement('section');section.innerHTML='<h2>资源诊断与只读图像</h2><p>文件存在不代表功能已就绪。图像仅按物品 ID 通过当前原生 GM 读取，不安装或修改资源。</p><button id="gm-resources-read">读取资源状态</button><ul id="gm-resources-list"></ul><pre id="gm-resources-warnings"></pre><label>物品 ID<input id="gm-preview-id" type="number" min="1" max="4294967295" step="1"></label><button id="gm-preview-read" disabled>读取物品名称与图像</button><p id="gm-preview-status" role="status">先手动连接本地 GM。</p><img id="gm-preview-image" alt="所选物品的原生只读图像" hidden width="96" height="96">';
 pages.get('native-gm').append(section);
 function render(data){
  const list=$('gm-resources-list');list.replaceChildren();
  for(const [label,key] of [['锻造规则','refine'],['图像资源','images'],['中文显示名','names']]){const li=document.createElement('li');li.textContent=label+'：'+(data.resources?.[key]?.message||'未检测');list.append(li);}
  $('gm-resources-warnings').textContent=(data.resourceWarnings||[]).join('\n');
  $('gm-preview-read').disabled=data.state!=='ready';
  if(data.state!=='ready'){$('gm-preview-image').hidden=true;$('gm-preview-image').removeAttribute('src');$('gm-preview-status').textContent='先手动连接本地 GM。';}
  else if($('gm-preview-status').textContent==='先手动连接本地 GM。')$('gm-preview-status').textContent='已连接；填写当前 PVF 中的物品 ID 进行只读预览。';
 }
 window.addEventListener('meow-gm-connection',event=>render(event.detail||{}));
 $('gm-resources-read').onclick=()=>run(async()=>{const data=await api('/api/admin/gm/status');window.meowGMConnection=data;window.dispatchEvent(new CustomEvent('meow-gm-connection',{detail:data}));});
 $('gm-preview-read').onclick=()=>run(async()=>{
  $('gm-preview-image').hidden=true;$('gm-preview-image').removeAttribute('src');
  const connection=window.meowGMConnection,id=Number($('gm-preview-id').value);
  if(connection?.state!=='ready'||!Number.isInteger(id)||id<1||id>4294967295)throw Error('请连接当前 GM 并填写有效物品 ID');
  const data=await api('/api/admin/gm/preview',{connectionId:connection.connectionId,id});
  if(window.meowGMConnection?.connectionId!==connection.connectionId)return;
  $('gm-preview-status').textContent=(data.item?.name||'物品 '+id)+' · '+data.message;
  if(data.imageState==='decoded'&&data.png){$('gm-preview-image').src='data:image/png;base64,'+data.png;$('gm-preview-image').hidden=false;}
 });
})();
