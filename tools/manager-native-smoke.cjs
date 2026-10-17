const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),net=require('node:net'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const data=fs.mkdtempSync(path.join(root,'target/manager-qa-'));
 const reservation=net.createServer();await new Promise(r=>reservation.listen(0,'127.0.0.1',r));const port=reservation.address().port;await new Promise(r=>reservation.close(r));
 const exe=path.join(root,'target/release/meow-manager.exe');
 const gm=require('node:http').createServer((req,res)=>{res.setHeader('Content-Type','application/json');if(req.url==='/api/auth/login'){res.setHeader('Set-Cookie','qa=ok; Path=/');res.end('{"success":true}');return;}if(req.headers.cookie!=='qa=ok'){res.writeHead(401);res.end('{}');return;}res.end(JSON.stringify(req.url.startsWith('/api/characters')?{characters:[{accountId:7,characterId:9,name:'隔离测试角色',level:1,jobName:'测试'}]}:{accounts:[{accountId:7,name:'00000001',characterCount:1}]}));});
 await new Promise(r=>gm.listen(0,'127.0.0.1',r));
 let child,browser,base;
 async function start(){
  child=spawn(exe,[],{windowsHide:true,stdio:'ignore',env:{...process.env,OO_MANAGER_DATA:data,WEBVIEW2_USER_DATA_FOLDER:path.join(data,'webview'),WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`}});
  for(let i=0;i<160;i++){try{const r=await fetch(`http://127.0.0.1:${port}/json/version`);if(r.ok)break;}catch{}if(child.exitCode!==null)throw Error('Desktop exited '+child.exitCode);await delay(250);}
  browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
  let page;for(let i=0;i<80;i++){page=browser.contexts()[0].pages().find(p=>p.url().startsWith('http://127.0.0.1:'));if(page)break;await delay(250);}
  assert.ok(page,'native WebView exists');base=new URL(page.url()).origin;return page;
 }
 async function stop(){
  if(browser){const page=browser.contexts()[0].pages().find(p=>p.url().startsWith(base));await page.click('[data-window=close]').catch(()=>{});}
  for(let i=0;i<40&&child.exitCode===null;i++)await delay(250);
  assert.notEqual(child.exitCode,null,'custom close exits native application');
  if(browser){await browser.close().catch(()=>{});browser=null;}
  for(let i=0;i<40;i++){try{await fetch(base+'/api/health');}catch{return;}await delay(250);}throw Error('Backend leaked after desktop exit');
 }
 try{
  let page=await start();await page.waitForFunction(()=>document.querySelector('#login h2')?.textContent.includes('首次使用'));
  await page.evaluate(()=>{window.qaFocusEvents=0;window.addEventListener('focus',()=>window.qaFocusEvents++);window.addEventListener('blur',()=>window.qaFocusEvents++);});
  await page.click('#username');await page.keyboard.press('Control+A');await page.keyboard.type('focus_check');
  await delay(1500);assert.equal(await page.inputValue('#username'),'focus_check');
  assert.ok(await page.evaluate(()=>window.qaFocusEvents<10),'focus does not oscillate continuously');
  assert.equal(await page.locator('#manager-chrome').count(),1);
  const dragBounds=await page.locator('#manager-drag').boundingBox(),inputBounds=await page.locator('#username').boundingBox();assert.ok(inputBounds.y>=dragBounds.y+dragBounds.height,'drag region does not cover inputs');
  await page.click('[data-window=minimize]');
  const restore=spawn(exe,[],{windowsHide:true,stdio:'ignore',env:{...process.env,OO_MANAGER_DATA:data}});await new Promise(r=>restore.once('exit',r));await delay(500);
  await page.waitForFunction(()=>document.visibilityState==='visible');
  const actualMetrics=await page.evaluate(()=>({width:innerWidth,height:innerHeight,dpr:devicePixelRatio}));
  await page.setViewportSize({width:900,height:650});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.equal(await page.locator('[data-window=close]').isVisible(),true);
  await page.screenshot({path:path.join(root,'docs/qa/manager-native-compact.png')});
  await page.setViewportSize({width:actualMetrics.width,height:actualMetrics.height});
  fs.writeFileSync(path.join(root,'docs/qa/manager-native-metrics.json'),JSON.stringify({actualMetrics,compactLayout:{width:900,height:650},focusEvents:await page.evaluate(()=>window.qaFocusEvents)},null,2));
  await page.waitForFunction(()=>[...document.querySelectorAll('img[alt=Arad]')].every(i=>i.complete&&i.naturalWidth>0));
  await page.screenshot({path:path.join(root,'docs/qa/manager-login.png')});
  const denial=await page.evaluate(async()=>{const r=await fetch('/api/desktop/setup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:'fixture-password-123'})});return r.status;});assert.equal(denial,403);
  await page.click('#username');await page.keyboard.press('Control+A');await page.keyboard.type('qa_owner');assert.equal(await page.inputValue('#username'),'qa_owner');await page.click('#password');await page.keyboard.type('fixture-password-123');assert.equal(await page.inputValue('#password'),'fixture-password-123');await page.click('#login-form label:last-of-type input');await page.keyboard.type('fixture-password-123');assert.equal(await page.inputValue('#login-form label:last-of-type input'),'fixture-password-123');await page.click('#login-form button');
  await page.waitForSelector('#workspace:visible');
  assert.equal(await page.locator('aside nav>button').count(),7);
  await page.click('aside [data-open-page=settings]');await page.waitForFunction(()=>document.getElementById('manager-about').textContent.includes('0.5.0'));
  assert.match(await page.textContent('#manager-about'),/MeowGM/);
  assert.equal(await page.locator('#manager-update-check').isVisible(),true);
  await page.click('aside [data-open-page=launcher]');
  const distribution=path.join(data,'待发布 客户端');fs.mkdirSync(distribution);fs.mkdirSync(path.join(distribution,'客户端 测试'));
  fs.copyFileSync(path.join(root,'target/release/meow-launcher.exe'),path.join(distribution,'MeowLauncher.exe'));
  fs.writeFileSync(path.join(distribution,'客户端 测试/DNF.exe'),'fixture only; never executed');
  await page.fill('#package-directory',distribution);await page.fill('#package-client','客户端 测试');
  await page.click('#package-inspect');await page.waitForFunction(()=>document.getElementById('package-result').textContent.includes('未通过'));
  assert.equal(await page.locator('#package-install').isDisabled(),true);
  assert.equal(fs.existsSync(path.join(distribution,'launcher.public.json')),false);
  assert.equal(await page.locator('#release-build').isVisible(),true);await page.fill('#release-client-directory',path.join(distribution,'客户端 测试'));await page.click('#release-build');await page.waitForFunction(()=>document.getElementById('release-state').textContent.includes('版本与 S4A21'));assert.equal(await page.locator('#release-open').isVisible(),false);
  const publicationClient=path.join(data,'受控发行夹具');fs.mkdirSync(publicationClient);
  fs.copyFileSync('C:/workspace/86JP S4A21/Client/S4A21_CN/DNF.exe',path.join(publicationClient,'DNF.exe'));
  for(const [name,value] of Object.entries({'az.dll':'fixture plugin never loaded','ijl15.dll':'fixture never loaded','GameGaurd.dll':'fixture never loaded','GameGaurd.ini':'fixture defaults','Script.pvf':'fixture pvf never run','ImagePacks2/main.NPK':'fixture images','SoundPacks/main.ogg':'fixture sounds','data/private.json':'private fixture not packaged','ScreenShots/private.png':'private fixture not packaged'})){const file=path.join(publicationClient,name);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,value);}
  await page.fill('#release-client-directory',publicationClient);await page.click('#release-build');await page.waitForFunction(()=>document.getElementById('release-state').textContent.includes('已生成'),null,{timeout:60000});
  assert.match(await page.textContent('#release-state'),/尚未上线/);const publications=path.join(data,'data/client-publications');const publication=fs.readdirSync(publications).find(name=>/^[a-f0-9]{32}$/.test(name));assert.ok(publication);const sourceManifest=path.join(publications,publication,'manifest.pending.json');const built=JSON.parse(fs.readFileSync(sourceManifest,'utf8'));assert.equal(built.archiveRoot,'S4A21_CN');assert.equal(built.files.some(f=>f.path.startsWith('data/')||f.path.startsWith('ScreenShots/')),false);
  fs.writeFileSync(path.join(publicationClient,'Script.pvf'),'fixture updated pvf');await page.setInputFiles('#release-baseline',sourceManifest);await page.fill('#release-version','1.1.0');await page.click('#release-build');await page.waitForFunction(()=>document.getElementById('release-state').textContent.includes('替换 1'));
  const pvfFixture=path.join(data,'fixture.pvf');
  require('node:child_process').execFileSync(process.env.OO_PYTHON||'python',['-c',"import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from pvf_tools import capabilities;from test_pvf_protection import fixture_header;Path(sys.argv[2]).write_bytes(fixture_header(1048576)+b'X'*1048576)",path.join(root,'services/gateway'),pvfFixture],{windowsHide:true});
  assert.equal(await page.locator('#pvf-protect').isEnabled(),false);await page.fill('#pvf-source',pvfFixture);await page.click('#pvf-inspect');await page.waitForFunction(()=>document.getElementById('pvf-state').textContent.includes('检测完成'));
  const pvfOriginal=JSON.parse(await page.textContent('#pvf-report'));assert.equal(pvfOriginal.capabilities.huazhiGameEncryption,false);assert.equal(await page.locator('#pvf-protect').isEnabled(),true);
  await page.click('#pvf-key-generate');await page.waitForFunction(()=>document.getElementById('pvf-key-path').value.endsWith('.key'));await page.click('#pvf-protect');await page.waitForFunction(()=>document.getElementById('pvf-state').textContent.includes('已生成加密分发副本'));
  const pvfEncrypted=JSON.parse(await page.textContent('#pvf-report'));assert.equal(pvfEncrypted.gameReadable,false);assert.equal(pvfEncrypted.keyIncluded,false);assert.equal(await page.locator('#pvf-open').isVisible(),true);
  await page.fill('#pvf-source',pvfEncrypted.path);await page.click('#pvf-inspect');await page.waitForFunction(()=>document.getElementById('pvf-unprotect').disabled===false);await page.click('#pvf-unprotect');await page.waitForFunction(()=>document.getElementById('pvf-state').textContent.includes('已解密并校验副本'));
  const pvfPlain=JSON.parse(await page.textContent('#pvf-report'));assert.equal(pvfPlain.sha256,pvfOriginal.sha256);assert.deepEqual(fs.readFileSync(pvfFixture),fs.readFileSync(pvfPlain.path));assert.equal(fs.readdirSync(path.dirname(pvfEncrypted.path)).some(name=>name.endsWith('.key')),false);
  fs.writeFileSync(path.join(root,'docs/qa/manager-pvf-native.json'),JSON.stringify({passed:true,scope:'Actual Manager EXE bundled cryptography/PVF module, synthetic 1 MiB A21-header fixture; not game-loader compatibility',roundtripSha256:pvfPlain.sha256,gameReadable:false,keyIncluded:false},null,2));
  await page.click('aside [data-open-page=deploy]');
  assert.equal(await page.locator('#deploy-start').count(),1);assert.equal(await page.locator('#deploy-uninstall').count(),1);
  await page.click('#manager-subnav [data-open-page=deploy]');await page.click('#deploy-start');await page.waitForFunction(()=>document.getElementById('status').textContent.includes('输入内容不正确'));
  assert.equal(await page.evaluate(async()=>{const r=await fetch('/api/admin/deployment/status',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});return (await r.json()).jobs.length;}),0);
  await page.click('aside [data-open-page=deploy]');await page.click('#manager-subnav [data-open-page=connections]');await page.locator('[data-manager-page=connections] summary').first().click();await page.click('#tunnel-status');await page.waitForFunction(()=>document.getElementById('tunnel-result').textContent==='需配置');
  await page.click('aside [data-open-page=notices]');await page.click('#add');await page.fill('.announcement input','桌面管理器验收');await page.fill('.announcement textarea','独立测试数据');await page.click('#publish');
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('本地草稿已保存'));
  await page.click('aside [data-open-page=deploy]');await page.click('#manager-subnav [data-open-page=connections]');await page.fill('#connection-gm','http://127.0.0.1:'+gm.address().port);await page.fill('#connection-gm-password','qa-secret');await page.click('#connection-save');
  await page.waitForFunction(()=>document.getElementById('connection-status').textContent.includes('已加密保存'));
  assert.equal(await page.inputValue('#connection-gm-password'),'');
  await page.click('#connection-check');await page.waitForFunction(()=>document.getElementById('connection-status').textContent.includes('GM：通过'));
  await page.click('aside [data-open-page=accounts]');await page.click('#game-refresh');await page.waitForSelector('#game-accounts button');assert.match(await page.textContent('#game-accounts'),/00000001/);
  await page.click('#game-accounts button');await page.waitForFunction(()=>document.getElementById('game-characters').textContent.includes('隔离测试角色'));
  await page.click('aside [data-open-page=notices]');await page.setInputFiles('#content-base',path.join(root,'packages/launcher-core/fixtures/content.json'));await page.fill('#content-reason','隔离导出验收');await page.fill('#content-planned','2030-01-01T12:00');await page.click('#content-export');
  await page.waitForFunction(()=>document.getElementById('content-result').textContent.includes('等待官网审核发布'));
  assert.ok(fs.readdirSync(path.join(data,'data/exports')).length===1);
  await page.screenshot({path:path.join(root,'docs/qa/manager-desktop.png'),fullPage:true});
  await page.click('#logout');await page.waitForSelector('#login:visible');await stop();
  page=await start();await page.waitForSelector('#login:visible');assert.equal(await page.textContent('#login h2'),'管理员登录');
  await page.click('#username');await page.keyboard.press('Control+A');await page.keyboard.type('qa_owner');assert.equal(await page.inputValue('#username'),'qa_owner');await page.click('#password');await page.keyboard.type('fixture-password-123');assert.equal(await page.inputValue('#password'),'fixture-password-123');await page.click('#login-form button');await page.waitForSelector('#workspace:visible');await page.click('aside [data-open-page=notices]');assert.equal(await page.inputValue('.announcement input'),'桌面管理器验收');
  await page.click('aside [data-open-page=deploy]');await page.click('#manager-subnav [data-open-page=connections]');await page.click('#connection-load');await page.waitForFunction(()=>document.getElementById('connection-status').textContent.includes('配置已读取'));assert.equal(await page.inputValue('#connection-gm'),'http://127.0.0.1:'+gm.address().port);assert.equal(await page.inputValue('#connection-gm-password'),'');
  await stop();
  console.log('PASS: actual EXE/WebView2, editable first setup, focus stability, auto-login, six-task navigation, about version, native updater command, incomplete client and unsupported publication rejected, GM fixture, draft/export, logout, restart persistence and backend cleanup');
 }catch(e){if(browser){const p=browser.contexts()[0].pages().find(p=>p.url().startsWith(base));if(p)console.error(JSON.stringify(await p.evaluate(()=>({status:document.getElementById('status')?.textContent,publication:document.getElementById('release-state')?.textContent}))))}throw e;}finally{if(browser)await browser.close().catch(()=>{});if(child&&child.exitCode===null)child.kill();await new Promise(r=>gm.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
