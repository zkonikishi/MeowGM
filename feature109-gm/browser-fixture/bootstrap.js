'use strict';
// Test-only globals required by the original scripts. No network/auth/data-store adapter.
const $ = selector => document.querySelector(selector);
let selected={id:101,name:'合成角色 A',classId:0},busy=false;
const onlineMailReady=false,onlineAdminReady=false;
const fixtureLog=[],fixtureErrors=[];let delayNext=false,pendingOld=null;
function record(kind,data){fixtureLog.push({kind,...data});$('#fixture-log').textContent=JSON.stringify(fixtureLog.slice(-30),null,2);}
function blocked(kind){record('blocked',{operation:kind});throw Error('隔离fixture禁止真实调用：'+kind);}
window.fetch=()=>Promise.reject(Error('fixture blocks fetch'));
window.XMLHttpRequest=class{constructor(){blocked('XMLHttpRequest');}};
window.WebSocket=class{constructor(){blocked('WebSocket');}};
window.EventSource=class{constructor(){blocked('EventSource');}};
navigator.sendBeacon=()=>false;
window.addEventListener('error',e=>{fixtureErrors.push(String(e.message||'resource error'));});
window.addEventListener('unhandledrejection',e=>{fixtureErrors.push(String(e.reason));});
function lock(){document.querySelectorAll('.write').forEach(e=>{e.disabled=true;});}
function message(text){record('message',{text});}
function manage(){return blocked('manage');}
function afterMailDelivery(){return blocked('real afterMailDelivery adapter');}
function createItemIcon(){const span=document.createElement('span');span.textContent='◇';return span;}
const jobs=['swordman','fighter','gunner','mage','priest','at gunner','thief','at fighter','at mage','demonic swordman','creator mage','at swordman','knight','demonic lancer','at priest','gun blader','archer','imperial knight'];
for(const job of ['',...jobs]){const option=document.createElement('option');option.value=job;option.textContent=job||'全部职业';$('#item-job').append(option);}
const stackRecords=Array.from({length:61},(_,i)=>({id:900000+i,name:`合成材料 ${i+1}`,type:i%2?'material':'consumable'}));
const equipmentRecords=Array.from({length:61},(_,i)=>({id:910000+i,name:`合成装备 ${i+1}`,type:'weapon',level:1,rarity:0,jobs:'262143',durability:10}));
async function api(path,body){
  if(body!==undefined||typeof path!=='string'||path.startsWith('/')||path.includes('://'))return blocked('api write or absolute path');
  const url=new URL(path,'http://fixture.invalid/');record('synthetic-api',{path});
  if(url.pathname==='/stackable-types')return [{type:'material',label:'合成材料',count:30},{type:'consumable',label:'合成消耗品',count:31}];
  if(url.pathname==='/stackables'){
    const q=url.searchParams.get('q')||'',type=url.searchParams.get('type')||'',offset=Number(url.searchParams.get('offset')||0);
    const rows=stackRecords.filter(x=>(!q||x.name.includes(q)||String(x.id)===q)&&(!type||x.type===type));
    return {total:rows.length,items:rows.slice(offset,offset+30)};
  }
  if(url.pathname==='/equipment'){
    const q=url.searchParams.get('q')||'',type=url.searchParams.get('type')||'',offset=Number(url.searchParams.get('offset')||0),limit=Number(url.searchParams.get('limit')||30);
    // Jobs are intentionally all-compatible: assertions check the submitted filter, not resource eligibility.
    const rows=equipmentRecords.filter(x=>(!q||x.name.includes(q)||String(x.id)===q)&&(!type||x.type===type));
    const data={total:rows.length,items:rows.slice(offset,offset+limit)};
    if(delayNext){delayNext=false;return new Promise(resolve=>{pendingOld=()=>{resolve(data);pendingOld=null;record('old-response-released',{});};record('response-held',{path});});}
    return data;
  }
  if(/^\/equipment\/[0-9]+\/custom-options$/.test(url.pathname))return {required:false};
  return blocked('unknown api '+path);
}
function choose(value){selected=value;document.dispatchEvent(new CustomEvent('dnf110:character-selected'));$('#fixture-status').textContent='当前合成目标：'+(selected?.name||'无');}
for(const button of document.querySelectorAll('[data-tab]'))button.addEventListener('click',()=>{
  document.querySelectorAll('[data-panel]').forEach(panel=>{panel.hidden=panel.dataset.panel!==button.dataset.tab;});
});
$('#fixture-a').onclick=()=>choose({id:101,name:'合成角色 A',classId:0});
$('#fixture-b').onclick=()=>choose({id:102,name:'合成角色 B',classId:1});
$('#fixture-clear').onclick=()=>choose(null);
$('#fixture-refresh').onclick=()=>{record('synthetic-event',{name:'same CID post-mail refresh; no mail sent'});choose(selected&&{...selected});};
$('#fixture-delay').onclick=()=>{if(pendingOld)return blocked('second held response');delayNext=true;$('#fixture-status').textContent='下一装备响应将暂存；请随后提交新查询，再释放旧响应。';};
$('#fixture-release').onclick=()=>{if(pendingOld)pendingOld();};
window.GmFixture=Object.freeze({scope:'synthetic-no-real-auth',snapshot:()=>({selected:selected&&{...selected},calls:structuredClone(fixtureLog),errors:[...fixtureErrors],held:!!pendingOld})});
document.addEventListener('DOMContentLoaded',()=>{$('#fixture-status').textContent='隔离fixture就绪；真实发放按钮必须禁用。';document.querySelector('[data-tab="stackables"]').click();});
