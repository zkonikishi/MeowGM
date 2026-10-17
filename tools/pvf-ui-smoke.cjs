// Isolated local PVF workflow, never touches an operator's files or server.
const {chromium}=require('playwright'),{spawn}=require('node:child_process');
const path=require('node:path'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'..');
 const code=`import sys,tempfile,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from server import Gateway,Store
from test_pvf_protection import fixture_header
with tempfile.TemporaryDirectory() as d:
 p=Path(d);source=p/'Script.pvf';source.write_bytes(fixture_header(1048576)+b'X'*1048576)
 s=Store(p/'qa.db');s.initialize('pvf-browser-fixture-password')
 g=Gateway(('127.0.0.1',0),s);print(json.dumps({'port':g.server_port,'source':str(source)}),flush=True);g.serve_forever()
`;
 const child=spawn(process.env.OO_PYTHON||'python',['-u','-c',code,path.join(root,'services/gateway')],{windowsHide:true});
 let browser;
 try{
  const fixture=await new Promise((resolve,reject)=>{child.stdout.once('data',d=>resolve(JSON.parse(d)));child.once('error',reject);child.once('exit',()=>reject(Error('fixture exited')));});
  browser=await chromium.launch({headless:true,channel:'msedge'});const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:'+fixture.port);await page.fill('#password','pvf-browser-fixture-password');await page.click('#login-form button');await page.waitForSelector('#workspace:visible');await page.click('aside [data-open-page=launcher]');
  assert.equal(await page.locator('#pvf-protect').isEnabled(),false);
  await page.fill('#pvf-source',fixture.source);await page.click('#pvf-inspect');await page.waitForFunction(()=>document.getElementById('pvf-state').textContent.includes('检测完成'));
  assert.equal(await page.locator('#pvf-protect').isEnabled(),true);assert.equal(await page.locator('#pvf-unprotect').isEnabled(),false);
  const original=JSON.parse(await page.textContent('#pvf-report'));assert.equal(original.capabilities.huazhiGameEncryption,false);
  await page.click('#pvf-key-generate');await page.waitForFunction(()=>document.getElementById('pvf-key-path').value.endsWith('.key'));
  await page.click('#pvf-protect');await page.waitForFunction(()=>document.getElementById('pvf-state').textContent.includes('已生成加密分发副本'));
  const result=JSON.parse(await page.textContent('#pvf-report'));assert.equal(result.gameReadable,false);assert.equal(result.keyIncluded,false);
  await page.fill('#pvf-source',result.path);assert.equal(await page.locator('#pvf-protect').isEnabled(),false);await page.click('#pvf-inspect');await page.waitForFunction(()=>document.getElementById('pvf-state').textContent.includes('检测完成'));assert.equal(await page.locator('#pvf-unprotect').isEnabled(),true);
  await page.click('#pvf-unprotect');await page.waitForFunction(()=>document.getElementById('pvf-state').textContent.includes('已解密并校验副本'));const plain=JSON.parse(await page.textContent('#pvf-report'));assert.equal(plain.sha256,original.sha256);assert.deepEqual(errors,[]);
  const report={passed:true,scope:'Isolated browser/local authenticated API, not Huazhi client compatibility',checks:['capability gating survives global busy state','file change invalidates capability','generated key separate from output','authenticated encrypted-copy roundtrip SHA matches','no game-readable encryption claim','no page errors']};fs.writeFileSync(path.join(root,'docs/qa/manager-pvf-ui.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{if(browser)await browser.close();child.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
