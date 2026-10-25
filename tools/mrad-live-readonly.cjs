// Actual-server read-only UI check. Starts only a temporary MeowGM source console.
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const path=require('node:path');
const os=require('node:os');
const fs=require('node:fs');
const readline=require('node:readline');
const assert=require('node:assert/strict');

(async()=>{
 const root=path.resolve(__dirname,'..');
 const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'meowgm-live-'));
 const child=process.env.MRAD_CONSOLE_EXE
  ?spawn(process.env.MRAD_CONSOLE_EXE,['--no-open','--data',temporary],{windowsHide:true})
  :spawn(process.env.OO_PYTHON||'python',['-u',path.join(root,'tools/start_mrad_console.py'),'--data',temporary],{windowsHide:true});
 const lines=readline.createInterface({input:child.stdout});
 let browser,page;
 try{
  const startup=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Console startup timeout')),15000);lines.once('line',line=>{clearTimeout(timer);resolve(line);});child.once('error',reject);});
  const url=startup.slice(startup.indexOf('http://'));
  assert.ok(url.startsWith('http://127.0.0.1:'));
  browser=await chromium.launch({headless:true,channel:'msedge'});
  page=await browser.newPage({viewport:{width:1280,height:900}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(url);
  await page.waitForFunction(()=>document.body.dataset.mradOnly==='true' && document.getElementById('gmTools')?.open);
  await page.waitForFunction(()=>!document.getElementById('mrad-connect').disabled);
  assert.match(await page.locator('#mrad-evidence-title').textContent(),/联调诊断与验收/);
  assert.match(await page.locator('[aria-labelledby="mrad-evidence-title"]').textContent(),/客户端游戏认证未验收客户端角色界面未验收选角进入城镇未验收/);
  await page.locator('#mrad-connect').click();
  await page.waitForFunction(()=>!document.getElementById('mrad-refresh').disabled,{},{timeout:20000});
  await page.locator('#mrad-refresh').click();
  await page.waitForFunction(()=>document.getElementById('mrad-accounts-note').textContent.includes('已读取')&&!document.getElementById('mrad-account').disabled);
  const accountCount=await page.locator('#mrad-account option').count();
  let accountsChecked=0,charactersObserved=0;
  // IDs remain inside the browser session; no names, amounts, screenshots or IDs are printed.
  for(let index=0;index<Math.min(accountCount,5);index++){
   await page.locator('#mrad-account').selectOption({index});
   await page.waitForFunction(()=>document.getElementById('mrad-characters-note').textContent.includes('已读取')&&!document.getElementById('mrad-account').disabled);
   charactersObserved+=await page.locator('#mrad-character option').count();accountsChecked++;
  }
  const report={ui:'passed',accountCount,accountsChecked,charactersObserved,
   resources:await page.locator('#mrad-resources').textContent(),writeEnabled:false,gameEntryVerified:false};
  await page.locator('#mrad-disconnect').click();
  await page.waitForFunction(()=>document.getElementById('mrad-state').textContent.includes('断开'));
  assert.equal(await page.locator('#mrad-account option').count(),0);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify(report,null,2));
 }finally{
  if(page)await page.evaluate(async()=>{await fetch('/api/desktop/quit',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});}).catch(()=>{});
  if(browser)await browser.close();
  lines.close();
  await new Promise(resolve=>{if(child.exitCode!==null)return resolve();const timer=setTimeout(()=>{child.kill();resolve();},10000);child.once('exit',()=>{clearTimeout(timer);resolve();});});
  const resolved=path.resolve(temporary);
  if(path.dirname(resolved)===path.resolve(os.tmpdir())&&path.basename(resolved).startsWith('meowgm-live-'))fs.rmSync(resolved,{recursive:true,force:true});
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
