'use strict';
// Explicit test controls call the original production functions, not event substitutes.
function chainState(){return {page:document.querySelector('#item-page').textContent,job:document.querySelector('#item-job').value,
 selectedId:selected?.id??null,events:glueCalls.filter(x=>x.kind==='actual-character-selected-event').length,
 reads:glueCalls.filter(x=>x.kind==='synthetic-fetch').length};}
function showChain(record){glueRecord('chain-observation',record);document.querySelector('#glue-chain-observation').textContent=JSON.stringify(record,null,2);}
async function callOriginalAfterMail(recipient,label){
 const before=chainState();glueRecord('chain-begin',{label,recipient:recipient.id,before,noMailSent:true});
 await afterMailDelivery(recipient,'合成装备（无邮件）',1);
 const after=chainState();showChain({label,before,after,actualSelectedEventDelta:after.events-before.events,
  syntheticReadDelta:after.reads-before.reads,pageUnchanged:before.page===after.page,jobUnchanged:before.job===after.job,
  rendererScope:'loadMail/loadInventory are explicit synthetic adapters, not production renderers',realMailSent:false});
}
document.querySelector('#fixture-a').onclick=async()=>{const c=rows.find(x=>x.id===101);if(c)await select(c);};
document.querySelector('#fixture-b').onclick=async()=>{const c=rows.find(x=>x.id===102);if(c)await select(c);};
document.querySelector('#fixture-clear').onclick=()=>glueReject('use empty-refresh control to exercise real reset');
document.querySelector('#fixture-delay').onclick=()=>glueReject('delayed response covered by original fixture only');
document.querySelector('#fixture-release').onclick=()=>glueReject('delayed response covered by original fixture only');
document.querySelector('#fixture-refresh').onclick=async()=>{
 if(!selected)return;
 glueRecord('synthetic-mail-success-entry',{recipient:selected.id,noMailSent:true});
 await callOriginalAfterMail({id:selected.id,name:selected.name},'same-current-recipient');
 document.querySelector('#fixture-status').textContent='已执行生产 afterMailDelivery→refresh→select；仅合成读，无邮件发送。';
};
document.querySelector('#fixture-other-recipient').onclick=async()=>{
 const recipient=glueCharacters.find(x=>x.id!==selected?.id);
 await callOriginalAfterMail({id:recipient.id,name:recipient.name},'different-recipient');
};
document.querySelector('#fixture-empty-rows').onclick=async()=>{const before=chainState();glueCharacterMode='empty';await refresh();showChain({label:'actual-refresh-empty-rows',before,after:chainState(),realMailSent:false});};
document.querySelector('#fixture-normal-rows').onclick=async()=>{const before=chainState();glueCharacterMode='normal';await refresh();showChain({label:'actual-refresh-restored-rows',before,after:chainState(),realMailSent:false});};
document.addEventListener('DOMContentLoaded',()=>{
 document.querySelector('#fixture-status').textContent='独立胶水fixture：真实api/refresh/select/afterMailDelivery；mail/inventory loader为显式合成适配，非真实邮件UI。';
 document.querySelector('[data-tab="give"]').click();
});
