const assert=require('node:assert/strict');
const {reconcileDungeonRules,validateCompassExtras}=require('./rule-previews.cjs');
const original={schemaVersion:1,revision:'old-revision',catalogVersion:'old-pvf',rules:[
  {id:'keep',name:'保留额度',enabled:true,mode:'selected',dungeonIds:[1,2],excludedIds:[3],reviveMode:'custom',reviveLimit:4,potionLimit:7},
  {id:'gone',enabled:true,mode:'selected',dungeonIds:[2],excludedIds:[]},
  {id:'global',enabled:true,mode:'all',dungeonIds:[],excludedIds:[2],percent:120}]};
let passed=0;function check(name,action){action();passed++;console.log('PASS '+name);}
check('MOD change retains valid rules and usage settings',()=>{const p=reconcileDungeonRules(original,'new-pvf',[1,3],{complete:true});assert.equal(p.state.rules[0].reviveLimit,4);assert.equal(p.state.rules[0].potionLimit,7);assert.deepEqual(p.state.rules[0].dungeonIds,[1]);});
check('removed dungeons pruned and empty selected rules never expand',()=>{const p=reconcileDungeonRules(original,'new-pvf',[1,3],{complete:true});assert.deepEqual(p.droppedRuleIds,['gone']);assert.deepEqual(p.removedDungeonIds,[2]);assert.deepEqual(p.state.rules[1].excludedIds,[]);});
check('preview never mutates original and gives stable revised token',()=>{const p=reconcileDungeonRules(original,'new-pvf',[1,3],{complete:true});assert.equal(original.catalogVersion,'old-pvf');assert.deepEqual(original.rules[0].dungeonIds,[1,2]);assert.equal(p.state.revision,reconcileDungeonRules(original,'new-pvf',[1,3],{complete:true}).state.revision);assert.notEqual(p.state.revision,original.revision);});
check('unavailable or empty catalog cannot wipe rules',()=>{assert.throws(()=>reconcileDungeonRules(original,'new-pvf',[1]));assert.throws(()=>reconcileDungeonRules(original,'new-pvf',[],{complete:true}));});
check('unknown schema and damaged bindings fail closed',()=>{assert.throws(()=>reconcileDungeonRules({...original,schemaVersion:2},'new',[1],{complete:true}));const x=structuredClone(original);x.rules[0].dungeonIds=[1,1];assert.throws(()=>reconcileDungeonRules(x,'new',[1],{complete:true}));});
check('unchanged catalog does not rewrite revision',()=>assert.equal(reconcileDungeonRules(original,'old-pvf',[1,2,3],{complete:true}).state.revision,'old-revision'));
const definitions={10:{effects:[{kind:'CompassAdditionalDrop'}]},11:{effects:[{kind:'HP'}]},12:{effects:[{kind:'CompassAdditionalDrop'},{kind:'HP'}]}};
check('drop extras retain repeated values instead of deduplicating',()=>assert.deepEqual(validateCompassExtras([10,10,10],[10],definitions,2),[10,10,10]));
check('ordinary and mixed non-drop extras remain nonrepeatable',()=>{assert.throws(()=>validateCompassExtras([11,11],[11],definitions,2));assert.throws(()=>validateCompassExtras([12,12],[12],definitions,2));});
check('slot count and ticket allowlist remain enforced',()=>{assert.throws(()=>validateCompassExtras([10,10,10],[10],definitions,6));assert.throws(()=>validateCompassExtras([10],[],definitions,2));});
console.log(JSON.stringify({passed,failed:0,scope:'pure previews only',appliedToBackend:false,gameWrites:false}));
