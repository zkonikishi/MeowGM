'use strict';
// No global $, selected, api, refresh, select or afterMailDelivery replacement:
// these are provided in full by the pinned production scripts.
const glueCalls=[],glueErrors=[];
let glueCharacterMode='normal';
const glueCharacters=[{id:101,accountId:501,name:'合成角色 A',classId:0,level:1,gold:0,cera:0,revision:'synthetic-a'},
 {id:102,accountId:501,name:'合成角色 B',classId:1,level:1,gold:0,cera:0,revision:'synthetic-b'}];
const glueEquipment=Array.from({length:61},(_,i)=>({id:910000+i,name:`合成装备 ${i+1}`,type:'weapon',level:1,rarity:0,jobs:'262143',durability:10}));
function glueRecord(kind,data={}){glueCalls.push({kind,...data});document.querySelector('#fixture-log').textContent=JSON.stringify(glueCalls.slice(-35),null,2);}
function glueReject(kind){glueRecord('blocked',{operation:kind});throw Error('隔离glue fixture禁止：'+kind);}
const mailView={error:null},inventoryView={error:null};
async function loadMail(){if(!selected)return;await api(`characters/${selected.id}/mail`);glueRecord('synthetic-mail-loader');}
async function loadInventory(){if(!selected)return;await api(`characters/${selected.id}/inventory`);glueRecord('synthetic-inventory-loader');}
function openSetup(){return glueReject('setup must not run');}
const GmPolling=Object.freeze({create(){glueRecord('polling-disabled',{scope:'fixture does not create production recurring timer'});}});
window.XMLHttpRequest=class{constructor(){glueReject('XHR');}};
window.WebSocket=class{constructor(){glueReject('WebSocket');}};
window.EventSource=class{constructor(){glueReject('EventSource');}};
navigator.sendBeacon=()=>false;
window.addEventListener('error',e=>glueErrors.push(String(e.message||'resource error')));
window.addEventListener('unhandledrejection',e=>glueErrors.push(String(e.reason)));
// Native fetch is never retained or invoked. app110's actual api uses this test transport.
window.fetch=async(input,options={})=>{
 if(typeof input!=='string'||(options.method&&options.method!=='GET')||options.body!==undefined||!input.startsWith('/api/')||input.includes('://'))return glueReject('network/write');
 const url=new URL(input,'http://synthetic.invalid');glueRecord('synthetic-fetch',{path:url.pathname+url.search});let data;
 if(url.pathname==='/api/status')data={configured:true,serverRunning:true,databaseAvailable:true,onlineMailReady:false,onlineAdminReady:false};
 else if(url.pathname==='/api/characters')data=glueCharacterMode==='empty'?[]:structuredClone(glueCharacters);
 else if(/^\/api\/characters\/(101|102)\/progress$/.test(url.pathname))data={growType:0,branches:[]};
 else if(/^\/api\/characters\/(101|102)\/(mail|inventory)$/.test(url.pathname))data={items:[],fixtureOnly:true};
 else if(url.pathname==='/api/equipment'){
  const q=url.searchParams.get('q')||'',type=url.searchParams.get('type')||'',offset=Number(url.searchParams.get('offset')||0),limit=Number(url.searchParams.get('limit')||30);
  const items=glueEquipment.filter(x=>(!q||x.name.includes(q))&&(!type||x.type===type));data={total:items.length,items:items.slice(offset,offset+limit)};
 }else if(/^\/api\/equipment\/910[0-9]{3}\/custom-options$/.test(url.pathname))data={required:false};
 else return glueReject('unlisted read '+url.pathname);
 return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});
};
document.addEventListener('dnf110:character-selected',()=>glueRecord('actual-character-selected-event'));
window.GlueFixture=Object.freeze({scope:'synthetic-only-no-real-auth-mail',snapshot:()=>({calls:structuredClone(glueCalls),errors:[...glueErrors],characterMode:glueCharacterMode,selected:selected&&{...selected},rows:rows.map(x=>({...x}))})});
