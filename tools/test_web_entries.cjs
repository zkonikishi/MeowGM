// Offline checks against the actual website candidate, without starting a server.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '../../website-work/public');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const script = read('assets/cdk.js');
const html = read('CDK/index.html');
const gm = read('GM/index.html');
const checks = [];
async function check(name, run) { await run(); checks.push(name); }
async function session(token, reply) {
  const state = {textContent: ''}, calls = [], removed = [], timers = new Set();
  let submit;
  const context = {
    document: {querySelector(selector) {
      if (selector === '#cdk-session') return state;
      if (selector === 'form') return {addEventListener(event, callback) {
        assert.equal(event, 'submit'); submit = callback;
      }};
      throw new Error('Unexpected DOM access');
    }},
    sessionStorage: {getItem(key) {assert.equal(key, 'arad.platform.session.v1'); return token;},
      removeItem(key) {removed.push(key);}},
    AbortController,
    setTimeout(callback) { const id = {}; timers.add(id); return id; },
    clearTimeout(id) {timers.delete(id);},
    fetch: async (url, options) => {calls.push({url, options}); return reply(options);}
  };
  await vm.runInNewContext(`(async()=>{${script}\n})()`, context, {timeout: 1000});
  let prevented = false;
  submit({preventDefault() {prevented = true;}});
  assert.ok(prevented, 'Submission must remain blocked');
  assert.equal(timers.size, 0, 'Timeout must be cleared');
  assert.ok(!state.textContent.includes('synthetic-private-profile'));
  for (const call of calls) {
    assert.equal(call.url, '/api/account/session');
    assert.equal(call.options.cache, 'no-store');
    assert.equal(call.options.redirect, 'error');
    assert.equal(call.options.headers.Authorization, `Bearer ${token}`);
    assert.equal(call.options.method, undefined); // fetch default GET only
  }
  return {state, calls, removed};
}
(async()=>{
  await check('anonymous: no network or redemption', async()=>{
    const result = await session(null, ()=>assert.fail('Anonymous network request'));
    assert.equal(result.calls.length, 0); assert.match(result.state.textContent, /尚未登录/);
  });
  await check('valid player session: still no redemption or admin rights', async()=>{
    const result = await session('fixture', ()=>({status:200,ok:true,json:async()=>({ok:true,username:'synthetic-private-profile',admin:true})}));
    assert.equal(result.calls.length, 1); assert.match(result.state.textContent, /仍未开放/);
  });
  await check('expired session: removed locally', async()=>{
    const result = await session('fixture', ()=>({status:401,ok:false}));
    assert.deepEqual(result.removed, ['arad.platform.session.v1']); assert.match(result.state.textContent, /失效/);
  });
  for (const status of [403,429,503]) await check(`HTTP ${status}: unavailable, never success`, async()=>{
    const result = await session('fixture', ()=>({status,ok:false}));
    assert.match(result.state.textContent, /暂时无法/);
  });
  await check('HTTP 200 with ok=false: unavailable', async()=>{
    const result = await session('fixture', ()=>({status:200,ok:true,json:async()=>({ok:false})}));
    assert.match(result.state.textContent, /暂时无法/);
  });
  for (const failure of ['network','invalid JSON','abort']) await check(`${failure}: fail closed`, async()=>{
    const result = await session('fixture', ()=>{
      if(failure === 'invalid JSON') return {status:200,ok:true,json:async()=>{throw new SyntaxError();}};
      throw new Error(failure);
    });
    assert.match(result.state.textContent, /连接失败/);
  });
  await check('candidate markup: disabled CDK and static GM', async()=>{
    assert.match(html, /<fieldset\s+disabled[\s>]/i);
    assert.match(gm, /管理功能暂未开放/);
    assert.doesNotMatch(gm, /<script|<iframe|<form|http:\/\/127\.|localhost|#setup=/i);
    for (const page of [html, gm]) {
      assert.doesNotMatch(page, /(?:src|href|action)=["'][^"']*(?:\/gm\/|\/internal\/|[?&](?:token|password)=)/i);
      for (const match of page.matchAll(/(?:src|href)=["'](\/assets\/[^"']+)["']/g))
        assert.ok(fs.statSync(path.join(root, match[1])).isFile(), `Missing asset: ${match[1]}`);
    }
  });
  const hashes = Object.fromEntries(['CDK/index.html','GM/index.html','assets/cdk.js'].map(file=>
    [file,crypto.createHash('sha256').update(read(file)).digest('hex')]));
  const report = {checkedAt:new Date().toISOString(),candidateRoot:root,checks,passed:checks.length,
    failed:0,hashes,liveNetworkUsed:false,serverStarted:false,deploymentVerified:false,rewardsDelivered:false};
  const output = path.resolve(__dirname,'../.runtime/mrad-qa/web-entry-offline.json');
  fs.mkdirSync(path.dirname(output),{recursive:true}); fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
