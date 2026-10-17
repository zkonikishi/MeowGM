// The first verified native mutation slice: SP/TP, receipts, explicit retries.
window.addEventListener('meow-gm-view-ready',()=>{
 const panel=document.createElement('section');panel.className='gm-card';panel.id='meowCharacterPoints';
 panel.innerHTML='<h2>技能点管理</h2><p id="meowPointsState" role="status">先连接本地 GM，再选择角色。</p><button type="button" class="btn" id="meowPointsRead">读取技能点与回执</button><form id="meowPointsForm"><label>类型<select id="meowPointsKind"><option value="sp">SP</option><option value="tp">TP</option></select></label><label>增加数量<input id="meowPointsValue" type="number" min="1" max="65535" value="1" required></label><label>原因<input id="meowPointsReason" maxlength="200" required></label><label><input id="meowPointsConfirm" type="checkbox" required>确认修改所选角色，重新选角后生效</label><button class="btn btn-blue" id="meowPointsSubmit">确认增加</button></form><p id="meowPointsPending"></p><button class="btn" id="meowPointsRetry" type="button" hidden>按原流水号重试待核对操作</button><pre id="meowPointsHistory"></pre>';
 $('gmCharacter').querySelector('.gm-advance').after(panel);
 const shortcut=document.querySelector('[data-advance="sp"]');shortcut.disabled=false;shortcut.title='打开技能点管理';shortcut.onclick=()=>panel.scrollIntoView({block:'start',behavior:'smooth'});
 let working=false,readKey='',loaded=false;

 function selectedId(value){if(!value)return '';try{return window.MeowNativeIds.native(value);}catch{return '';}}
 function target(){const connection=window.meowGMConnection;return {connection,account:selectedId($('gmAccount').value),character:selectedId($('gmStudioRole').value)};}
 function key(t){return JSON.stringify([t.connection?.connectionId,t.account,t.character]);}
 function pending(){return window.meowGMConnection?.pending||null;}
 function draw(){
  const t=target(),ready=t.connection?.state==='ready'&&!!t.account&&!!t.character;
  if(readKey!==key(t)){loaded=false;readKey=key(t);$('meowPointsHistory').textContent='';$('meowPointsConfirm').checked=false;}
  let p;try{p=pending();}catch(e){$('meowPointsState').textContent=e.message;p={};}
  $('meowPointsRead').disabled=working||!ready;
  $('meowPointsSubmit').disabled=working||!ready||!loaded||!!p;
  $('meowPointsRetry').hidden=!p?.body;
  $('meowPointsRetry').disabled=working||!ready||p?.context!==t.connection?.contextId||p?.checksum!==t.connection?.pvfChecksum||p?.body?.account!==t.account||p?.body?.character!==t.character;
  $('meowPointsPending').textContent=p?.body?'待核对流水：'+p.body.id+' · 账号 '+p.body.account+' / 角色 '+p.body.character+' · '+p.body.action.toUpperCase()+' +'+p.body.value+' · '+p.body.reason+'。重试会使用原请求，不会读取表单新值。':p?'待核对记录不可读取。':'';
 }
 async function call(t,method,extra={}){const result=await api('/api/admin/gm/call',{connectionId:t.connection.connectionId,method,...extra});if(result.error)throw Error(result.error);return result;}
 async function read(t){
  const data=await call(t,'character',{query:{id:[String(t.character)]}});
  if(key(t)!==key(target()))return;
  if(window.MeowNativeIds.native(data.account)!==t.account)throw Error('角色归属已改变，请重新选择账号');
  $('meowPointsState').textContent='SP '+JSON.stringify(data.summary.skill_points)+' · TP '+JSON.stringify(data.summary.technique_points);
  loaded=true;readKey=key(t);
  const history=await call(t,'history',{query:{account:[String(t.account)]}});
  if(key(t)===key(target()))$('meowPointsHistory').textContent=JSON.stringify(history.history||[],null,2);
 }
 async function execute(fn){if(working)return;working=true;draw();try{await fn();}catch(e){$('meowPointsState').textContent=e.message;}finally{try{window.meowGMConnection=await api('/api/admin/gm/status');}catch{}working=false;draw();}}
 $('meowPointsRead').onclick=()=>execute(()=>read(target()));
 async function apply(p,t){
  const result=await call(t,'character.edit',{body:p.body});
  if(result.ok!==true||result.grant_id!==p.body.id)throw Error('回执不匹配，请保留流水号核对');
  // Backend clears the durable request only after a matching success receipt.
  window.meowGMConnection.pending=null;
  $('meowPointsState').textContent=(result.applied?'已修改':'已存在，未重复修改')+' · '+result.grant_id;
  $('meowPointsConfirm').checked=false;
  await read(t);
 }
 $('meowPointsForm').onsubmit=e=>{e.preventDefault();execute(async()=>{
  const t=target();if(!loaded||readKey!==key(t)||t.connection?.state!=='ready')throw Error('请重新读取当前角色');
  if(pending())throw Error('已有待核对操作，请先按原流水号核对重试');
  const value=Number($('meowPointsValue').value),reason=$('meowPointsReason').value.trim();
  if(!Number.isInteger(value)||value<1||value>65535||!reason||!$('meowPointsConfirm').checked)throw Error('请填写有效数量、原因并确认');
  const p={context:t.connection.contextId,checksum:t.connection.pvfChecksum,body:{id:'launcher-'+crypto.randomUUID(),account:t.account,character:t.character,action:$('meowPointsKind').value,value,reason}};
  await apply(p,t);
 });};
 $('meowPointsRetry').onclick=()=>execute(async()=>{const p=pending(),t=target();if(!p||p.context!==t.connection?.contextId||p.checksum!==t.connection?.pvfChecksum||p.body.account!==t.account||p.body.character!==t.character)throw Error('请连接原环境并选择原角色');await apply(p,t);});
 for(const id of ['gmAccount','gmStudioRole','gmRefresh'])$(id).addEventListener(id==='gmRefresh'?'click':'change',draw);
 window.addEventListener('meow-gm-connection',draw);draw();
});
