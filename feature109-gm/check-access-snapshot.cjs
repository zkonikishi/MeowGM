'use strict';
const assert = require('node:assert/strict');
const {consumeSnapshot, consumeObservationV2} = require('./access-snapshot.cjs');
const now = 100000, target = {requestId:'request-2', instanceId:'instance', realm:'realm', accountId:'9007199254740993', characterId:'65535'};
const counter = () => ({applicable:true, periodKey:'server-period', used:'4', naturalLimit:'3', effectiveLimit:'3'});
function fixture() {
  return {version:'gm-access-snapshot-v1',available:true,...target,settingsRevision:'settings-2',observationVersion:'a'.repeat(64),
    observedAtMs:now-1000,validUntilMs:now+1000,
    access:{ignoreDailyEntryLimits:false,ignoreWeeklyEntryLimits:false},
    towers:['origin','dazzlement'].map(id=>({id,daily:counter(),weekly:counter()}))};
}
let checks=0;
function test(name, body) { body(); checks++; process.stdout.write(`PASS ${name}\n`); }
function reject(change, context=target, at=now) {const s=fixture(); change(s);assert.deepEqual(consumeSnapshot(s,context,at),{available:false,message:'未就绪',writeEnabled:false});}
test('valid two towers exact large account and max CID',()=>{const r=consumeSnapshot(fixture(),target,now);assert.equal(r.available,true);assert.equal(r.towers.length,2);assert.equal(r.writeEnabled,false);});
test('toggle both ways preserves natural persistent usage',()=>{const s=fixture(), before=JSON.stringify(s.towers);for(const t of s.towers)for(const p of ['daily','weekly'])t[p].effectiveLimit=null;s.access.ignoreDailyEntryLimits=s.access.ignoreWeeklyEntryLimits=true;let r=consumeSnapshot(s,target,now);assert.equal(r.available,true);assert.equal(r.towers[0].daily.used,'4');for(const t of s.towers)for(const p of ['daily','weekly'])t[p].effectiveLimit=t[p].naturalLimit;s.access.ignoreDailyEntryLimits=s.access.ignoreWeeklyEntryLimits=false;r=consumeSnapshot(s,target,now);assert.equal(r.available,true);assert.equal(JSON.stringify(s.towers),before);});
test('Int64 max and values beyond safe Number stay strings',()=>{const s=fixture();s.towers[0].daily.used='9223372036854775807';s.towers[1].weekly.used='9007199254740993';const r=consumeSnapshot(s,target,now);assert.equal(r.towers[0].daily.used,'9223372036854775807');assert.equal(r.towers[1].weekly.used,'9007199254740993');});
test('zero usage is valid',()=>{const s=fixture();s.towers[0].daily.used='0';assert.equal(consumeSnapshot(s,target,now).towers[0].daily.used,'0');});
test('zero account and CID rejected',()=>{for(const k of ['accountId','characterId'])reject(s=>{s[k]='0';},{...target,[k]:'0'});});
test('CID above 65535 rejected',()=>reject(s=>{s.characterId='65536';},{...target,characterId:'65536'}));
test('Int64 overflow and Number usage rejected',()=>{reject(s=>{s.towers[0].daily.used='9223372036854775808';});reject(s=>{s.towers[0].daily.used=4;});});
test('duplicate or missing towers rejected',()=>{reject(s=>{s.towers[1].id='origin';});reject(s=>{s.towers.pop();});});
test('non-applicable requires all null',()=>{const s=fixture();s.towers[1].weekly={applicable:false,periodKey:null,used:null,naturalLimit:null,effectiveLimit:null};assert.equal(consumeSnapshot(s,target,now).available,true);s.towers[1].weekly.used='0';assert.equal(consumeSnapshot(s,target,now).available,false);});
test('time boundary observed equal valid and expiry equal rejected',()=>{const s=fixture();s.observedAtMs=now;assert.equal(consumeSnapshot(s,target,now).available,true);reject(s=>{s.validUntilMs=now;});reject(s=>{s.observedAtMs=now+1;});});
test('30 second lifetime exact boundary',()=>{const s=fixture();s.observedAtMs=now;s.validUntilMs=now+30000;assert.equal(consumeSnapshot(s,target,now).available,true);s.validUntilMs++;assert.equal(consumeSnapshot(s,target,now).available,false);});
test('all target mismatches rejected',()=>{for(const k of ['instanceId','realm','accountId','characterId'])reject(s=>{s[k]=k==='characterId'?'1':k==='accountId'?'2':'other';});});
test('old request response rejected even with same target',()=>reject(s=>{s.requestId='request-1';}));
test('different pinned settings revision or observation hash rejected',()=>{for(const k of ['settingsRevision','observationVersion']){const ctx={...target,['expected'+k[0].toUpperCase()+k.slice(1)]:'b'.repeat(64)};reject(()=>{},ctx);}});
test('observation requires canonical hash instead of random identifier',()=>{for(const value of ['random-guid','A'.repeat(64),'a'.repeat(63)])reject(s=>{s.observationVersion=value;});});
test('matching pinned revisions accepted',()=>assert.equal(consumeSnapshot(fixture(),{...target,expectedSettingsRevision:'settings-2',expectedObservationVersion:'a'.repeat(64)},now).available,true));
test('local boolean and missing revision cannot fake success',()=>{reject(s=>{delete s.settingsRevision;});reject(s=>{s.access.ignoreDailyEntryLimits=true;});});
test('period key absence rejected but business calendar not proven',()=>reject(s=>{s.towers[0].daily.periodKey='';}));
function producerFixture() {
  const s=fixture();s.observationVersion='A'.repeat(64);
  s.towers=Object.fromEntries(s.towers.map(({id,...counter})=>[id,counter]));
  s.towers.origin.daily.naturalLimit=s.towers.origin.daily.effectiveLimit='1';
  s.towers.origin.weekly.naturalLimit=s.towers.origin.weekly.effectiveLimit='3';
  s.towers.dazzlement.weekly={applicable:false,periodKey:null,used:null,naturalLimit:null,effectiveLimit:null};
  return s;
}
test('explicit observation-v2 transport adapter preserves reviewed shapes',()=>{
  const s=producerFixture(),r=consumeObservationV2(s,target,now);
  assert.equal(r.available,true);assert.equal(r.observationVersion,'a'.repeat(64));
  assert.equal(r.towers[0].daily.used,'4');assert.equal(r.towers[0].daily.naturalLimit,'1');
  assert.equal(r.towers[0].weekly.naturalLimit,'3');assert.deepEqual(r.towers[1].weekly,{applicable:false});
  assert.equal(s.observationVersion,'A'.repeat(64));
});
test('producer adapter still rejects stale target and revision',()=>{
  assert.equal(consumeObservationV2(producerFixture(),{...target,requestId:'new-request'},now).available,false);
  assert.equal(consumeObservationV2(producerFixture(),{...target,expectedSettingsRevision:'different'},now).available,false);
});
test('producer adapter rejects extra towers and invalid digest',()=>{
  const s=producerFixture();s.towers.extra={};assert.equal(consumeObservationV2(s,target,now).available,false);
  delete s.towers.extra;s.observationVersion='invalid';assert.equal(consumeObservationV2(s,target,now).available,false);
});
process.stdout.write(`checks=${checks}; scope=consumer-only; no network/database/host\n`);
