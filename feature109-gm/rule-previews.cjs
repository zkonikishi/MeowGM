// Pure administrative previews for backend review. No transport or file mutation.
const crypto=require('node:crypto');
function reconcileDungeonRules(input,catalogVersion,knownIds,{complete=false}={}){
  if(!complete||!catalogVersion||!Array.isArray(knownIds)||!knownIds.length||knownIds.some(id=>!Number.isSafeInteger(id)||id<=0))throw Error('Complete current dungeon catalog required');
  if(input?.schemaVersion!==1||typeof input.catalogVersion!=='string'||!Array.isArray(input.rules)||input.rules.length>32)throw Error('Unsupported or damaged rules');
  const state=structuredClone(input),known=new Set(knownIds),removed=new Set(),dropped=[];
  for(const rule of state.rules){
    for(const key of ['dungeonIds','excludedIds']){
      if(!Array.isArray(rule[key])||rule[key].some(id=>!Number.isSafeInteger(id)||id<=0)||new Set(rule[key]).size!==rule[key].length)throw Error('Damaged dungeon bindings');
    }
  }
  if(state.catalogVersion===catalogVersion)return {changed:false,state,removedDungeonIds:[],droppedRuleIds:[]};
  state.rules=state.rules.filter(rule=>{
    for(const key of ['dungeonIds','excludedIds'])rule[key]=rule[key].filter(id=>{if(known.has(id))return true;removed.add(id);return false;});
    // Never convert an empty selected rule into an all-dungeon rule.
    if(rule.mode==='selected'&&!rule.dungeonIds.length){dropped.push(rule.id);return false;}return true;
  });
  state.catalogVersion=catalogVersion;
  const hash=crypto.createHash('sha256').update(JSON.stringify(state)).digest('hex').slice(0,32);
  state.revision=`${hash.slice(0,8)}-${hash.slice(8,12)}-${hash.slice(12,16)}-${hash.slice(16,20)}-${hash.slice(20)}`;
  return {changed:true,state,removedDungeonIds:[...removed].sort((a,b)=>a-b),droppedRuleIds:dropped};
}
// Only repeated EXTRA drop effects may be allowed. Ordinary group uniqueness is unchanged.
function validateCompassExtras(ids,allowed,definitions,ordinaryCount){
  if(!Array.isArray(ids)||!Number.isInteger(ordinaryCount)||ordinaryCount<0||ordinaryCount+ids.length>8)throw Error('Invalid compass slot count');
  const repeatableKinds=new Set(['OddAdditionalDrop','CompassAdditionalDrop','PartyCompassAdditionalDrop']);
  const seen=new Set();
  for(const id of ids){
    if(!Number.isInteger(id)||id<=0||id>255||!allowed.includes(id))throw Error('Unsupported extra option');
    const effects=definitions[id]?.effects;
    if(!Array.isArray(effects)||effects.length===0)throw Error('Unknown extra effect');
    if(seen.has(id)&&!effects.every(effect=>repeatableKinds.has(effect.kind)))throw Error('Non-drop extra cannot repeat');
    seen.add(id);
  }
  return [...ids];
}
module.exports={reconcileDungeonRules,validateCompassExtras};
