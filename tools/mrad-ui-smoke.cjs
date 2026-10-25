// Isolated browser acceptance: no game server, client, or player database.
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const path=require('node:path');
const assert=require('node:assert/strict');
const readline=require('node:readline');
const fs=require('node:fs');
const os=require('node:os');

(async()=>{
 const root=path.resolve(__dirname,'..');
 const code=`import sys,json
sys.path.insert(0,sys.argv[1])
from test_mrad import MradTests
from desktop_host import DesktopHandler
fixture=MradTests()
fixture.setUp()
fixture.gateway.RequestHandlerClass=DesktopHandler
fixture.gateway.local_mode=True
fixture.gateway.desktop_nonce='fixture-window'
fixture.gateway.profile='115us'
fixture.gateway.mrad.save({'baseUrl':fixture.address})
original_characters=fixture.characters
print(json.dumps({'url':fixture.base,'upstream':fixture.address}),flush=True)
try:
 for line in sys.stdin:
  if line.strip()=='restart': fixture.health['processId']+=1
  elif line.strip()=='limit': fixture.accounts=[{'accountId':i+1,'accountName':'fixture-'+str(i+1)} for i in range(2000)]
  elif line.strip()=='unready': fixture.caps['administration']=False
  elif line.strip()=='empty': fixture.characters=[]
  elif line.strip()=='appear': fixture.characters=original_characters
  elif line.strip()=='selected': fixture.requires_reselect=True
  print('ack',flush=True)
finally: fixture.doCleanups()
`;
 const child=spawn(process.env.OO_PYTHON||'python',['-u','-c',code,path.join(root,'services/gateway')],{windowsHide:true});
 const lines=readline.createInterface({input:child.stdout});
 const nextLine=()=>new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Fixture timeout')),15000);lines.once('line',line=>{clearTimeout(timer);resolve(line);});child.once('error',reject);});
 child.stderr.on('data',data=>process.stderr.write(data));
 let browser,page,packaged,packagedLines,packagedDirectory;
 try{
  let {url,upstream}=JSON.parse(await nextLine());
  if(process.env.MRAD_CONSOLE_EXE){
   packagedDirectory=fs.mkdtempSync(path.join(os.tmpdir(),'meowgm-packaged-qa-'));
   packaged=spawn(process.env.MRAD_CONSOLE_EXE,['--no-open','--data',packagedDirectory],{windowsHide:true});
   packagedLines=readline.createInterface({input:packaged.stdout});
   const startup=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Packaged console startup timeout')),25000);packagedLines.once('line',line=>{clearTimeout(timer);resolve(line);});packaged.once('error',reject);});
   url=startup.slice(startup.indexOf('http://'));
  }
  const command=async name=>{const ack=nextLine();child.stdin.write(name+'\n');await ack;};
  browser=await chromium.launch({headless:true,channel:'msedge'});
  page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(packaged?url:url+'/#setup=fixture-window');
  if(packaged) await page.waitForFunction(()=>document.body.dataset.mradOnly==='true' && document.getElementById('gmTools')?.open);
  else await page.locator('#meowMainNav').getByRole('button',{name:'Mrad 只读管理',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('mrad-url').value.includes(':')&&!document.getElementById('mrad-connect').disabled);
  if(packaged){
   await page.fill('#mrad-url',upstream);
   await page.locator('#mrad-settings button[type=submit]').click();
   await page.waitForFunction(()=>document.getElementById('mrad-state').textContent.includes('地址已保存'));
  }
  assert.equal(await page.locator('#mrad-refresh').isDisabled(),true);
  await page.locator('#mrad-connect').click();
  await page.waitForFunction(()=>!document.getElementById('mrad-refresh').disabled);
  await page.locator('#mrad-refresh').click();
  await page.waitForFunction(()=>document.getElementById('mrad-account').options.length===1&&!document.getElementById('mrad-account').disabled);
  await page.selectOption('#mrad-account','9223372036854775807');
  await page.waitForFunction(()=>document.getElementById('mrad-character').options.length===1&&!document.getElementById('mrad-character').disabled);
  await page.selectOption('#mrad-character','65535');
  assert.match(await page.locator('#mrad-character-detail').textContent(),/9007199254740993/);
  assert.match(await page.locator('#mrad-account-detail').textContent(),/<script>fixture<\/script>/);
  assert.equal(await page.locator('#mrad-account-detail script').count(),0);
  await page.locator('#mrad-progress').click();
  await page.waitForFunction(()=>document.getElementById('mrad-online').textContent.includes('没有已选角'));
  assert.match(await page.locator('#mrad-progress-detail').textContent(),/剩余 SP8/);
  await command('selected');
  await page.locator('#mrad-progress').click();
  await page.waitForFunction(()=>document.getElementById('mrad-online').textContent.includes('存在已选角'));
  assert.match(await page.locator('#mrad-online').textContent(),/不能据此判定已进城/);
  const downloadPromise=page.waitForEvent('download');
  await page.locator('#mrad-export').click();
  const download=await downloadPromise;
  const diagnostic=JSON.parse(fs.readFileSync(await download.path(),'utf-8'));
  assert.equal(diagnostic.observations.accounts.count,1);
  assert.equal(diagnostic.observations.characters.count,1);
  assert.equal(diagnostic.observations.progress.requiresReselect,true);
  assert.equal(diagnostic.gameAcceptance.townEntryVerified,false);
  assert.ok(diagnostic.lastCheckedAt);
  for(const privateText of ['9223372036854775807','65535','<script>fixture</script>','synthetic/save.sqlite'])assert.ok(!JSON.stringify(diagnostic).includes(privateText));
  await page.waitForFunction(()=>!document.getElementById('mrad-check').disabled);
  await page.locator('#mrad-check').click();
  await page.waitForFunction(()=>!document.getElementById('mrad-check').disabled);
  assert.equal(await page.locator('#mrad-account option').count(),0);
  assert.match(await page.locator('#mrad-account-evidence').textContent(),/尚未读取/);
  await page.locator('#mrad-refresh').click();
  await page.waitForFunction(()=>document.getElementById('mrad-account').options.length===1&&!document.getElementById('mrad-account').disabled);
  await command('empty');
  await page.selectOption('#mrad-account','9223372036854775807');
  await page.waitForFunction(()=>document.getElementById('mrad-characters-note').textContent.includes('已读取 0')&&!document.getElementById('mrad-refresh-characters').disabled);
  await command('appear');
  await page.locator('#mrad-refresh-characters').click();
  await page.waitForFunction(()=>document.getElementById('mrad-character').options.length===1&&!document.getElementById('mrad-character').disabled);
  const output=path.join(root,'.runtime','mrad-qa');fs.mkdirSync(output,{recursive:true});
  await page.evaluate(()=>document.getElementById('gmTools').scrollTop=0);
  await page.screenshot({path:path.join(output,'readonly-desktop.png')});
  await page.setViewportSize({width:900,height:720});
  await page.evaluate(()=>document.getElementById('gmTools').scrollTop=0);
  assert.ok(await page.evaluate(()=>document.getElementById('gmTools').scrollWidth<=document.getElementById('gmTools').clientWidth+2));
  await page.screenshot({path:path.join(output,'readonly-compact.png')});
  await command('restart');
  await page.locator('#mrad-check').click();
  await page.waitForFunction(()=>document.getElementById('mrad-state').textContent.includes('变化'));
  assert.equal(await page.locator('#mrad-account option').count(),0);
  assert.equal(await page.locator('#mrad-refresh').isDisabled(),true);
  const failureDownloadPromise=page.waitForEvent('download');
  await page.locator('#mrad-export').click();
  const failureDownload=await failureDownloadPromise;
  const failureReport=JSON.parse(fs.readFileSync(await failureDownload.path(),'utf-8'));
  assert.equal(failureReport.state,'failed');
  assert.equal(failureReport.processId,null);
  assert.ok(Object.values(failureReport.observations).every(value=>value===null));
  assert.equal(failureReport.gameEntryVerified,false);
  await page.locator('#mrad-connect').click();
  await page.waitForFunction(()=>!document.getElementById('mrad-refresh').disabled);
  await command('limit');
  await page.locator('#mrad-refresh').click();
  await page.waitForFunction(()=>document.getElementById('mrad-accounts-note').textContent.includes('2000 行上限'));
  await page.fill('#mrad-filter','fixture-1999');
  assert.equal(await page.locator('#mrad-account option').count(),1);
  await page.locator('#mrad-disconnect').click();
  await page.waitForFunction(()=>document.getElementById('mrad-state').textContent.includes('断开'));
  assert.equal(await page.locator('#mrad-account option').count(),0);
  await command('unready');
  await page.locator('#mrad-connect').click();
  await page.waitForFunction(()=>document.getElementById('mrad-state').textContent.includes('已连接'));
  assert.match(await page.locator('#mrad-resources').textContent(),/角色管理：未就绪/);
  const address=await page.inputValue('#mrad-url');
  await page.fill('#mrad-url','http://127.0.0.1:1');
  assert.equal(await page.locator('#mrad-connect').isDisabled(),true);
  assert.equal(await page.locator('#mrad-refresh').isDisabled(),true);
  await page.fill('#mrad-url',address);
  await page.locator('#mrad-settings button[type=submit]').click();
  await page.waitForFunction(()=>document.getElementById('mrad-state').textContent.includes('地址已保存'));
  assert.equal(await page.locator('#mrad-refresh').isDisabled(),true);
  assert.deepEqual(errors,[]);
  console.log('PASS: connection, accounts, exact Int64, role/progress, literal text, explicit instance check, redacted diagnostic download, stale instance, 2000-row notice, filter, resource readiness, save/disconnect, responsive screenshots; no page errors');
 }finally{
  if(packaged&&page)await page.evaluate(()=>fetch('/api/desktop/quit',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).catch(()=>{});
  if(browser)await browser.close();
  if(packaged){
   packagedLines.close();
   await new Promise(resolve=>{if(packaged.exitCode!==null)return resolve();const timer=setTimeout(()=>{require('node:child_process').spawnSync('taskkill',['/PID',String(packaged.pid),'/T','/F'],{windowsHide:true});resolve();},10000);packaged.once('exit',()=>{clearTimeout(timer);resolve();});});
   const resolved=path.resolve(packagedDirectory);if(path.dirname(resolved)===path.resolve(os.tmpdir())&&path.basename(resolved).startsWith('meowgm-packaged-qa-'))fs.rmSync(resolved,{recursive:true,force:true});
  }
  lines.close();child.stdin.end();
  await new Promise(resolve=>{const timer=setTimeout(()=>{child.kill();resolve();},3000);child.once('exit',()=>{clearTimeout(timer);resolve();});});
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
