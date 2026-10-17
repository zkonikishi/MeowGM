// Operator-only distribution preparation. No credentials enter this document.
const launcherConfigSection=document.createElement('section');
launcherConfigSection.innerHTML=`<h2>准备玩家客户端包</h2><p>选择已经放好客户端与 MeowLauncher.exe 的目录。先检查文件，再安装公开配置，最后由服主打包上传百度网盘。</p>
<div class="setup-steps"><span class="complete">1 选择目录</span><span id="package-step-check">2 检查客户端</span><span id="package-step-install">3 安装配置</span></div>
<label>要发布的客户端目录<input id="package-directory" placeholder="D:\\发布包\\阿拉德"></label><button id="package-choose" type="button">选择客户端目录</button>
<label>客户端在包内的位置<input id="package-client" value="." placeholder="同目录填 .；子目录例如 Client/S4A21_CN"></label>
<label>服务器名称<input id="package-realm-name" value="86s4a21"></label>
<details id="package-advanced"><summary>服务器地址与高级配置</summary><p>仓库内不含任何默认服务器地址，请填写你自己的服务端点。不填写管理密码或私钥。</p>
<label>品牌名称<input id="package-brand" placeholder="例如 Arad"></label><label>账号服务地址<input id="package-account" placeholder="https://account.example.com"></label>
<label>官网<input id="package-website" placeholder="https://www.example.com"></label><label>注册页面<input id="package-register" placeholder="https://www.example.com/account/register/"></label>
<label>找回密码页面<input id="package-forgot" placeholder="https://www.example.com/account/forgot/"></label><label>公告来源<input id="package-content" placeholder="https://www.example.com/launcher/content.json"></label>
<label>区服标识<input id="package-realm" placeholder="例如 s4a21"></label><label>游戏 IP / 域名<input id="package-host" placeholder="例如 game.example.com"></label><label>游戏端口<input id="package-port" type="number" min="1" max="65535" value="7001"></label>
<p>客户端适配：86s4a21 CN；账号接口：platform-v1。定制版启动器使用固定线上 legacy-online 协议，无需安装此配置；平台版须单独验收。自建账号服务需提供兼容接口。</p></details>
<div class="task-actions"><button id="package-inspect" type="button" class="primary">检查客户端</button><button id="package-install" type="button" data-enabled="false" disabled>安装服务器配置</button></div>
<div id="package-checks"></div><p id="package-result" role="status">先选择目录并检查客户端。</p>
<details id="package-output-details" hidden><summary>查看生成文件与备份位置</summary><p id="package-output-path"></p></details>
<p class="next-step">配置安装成功后，请自行压缩完整目录、上传百度网盘，再把分享链接与提取码交给官网。玩家不需要管理器。</p>`;
pages.get('launcher').replaceChildren(launcherConfigSection);
$('package-choose').onclick=async()=>{try{if(!window.__TAURI__?.core)throw Error('浏览器模式请手动填写完整目录路径');const value=await window.__TAURI__.core.invoke('choose_package_directory');if(value){$('package-directory').value=value;invalidatePackage();}}catch(e){$('package-result').textContent=String(e.message||e);}};
function packageBody(){const value=id=>$('package-'+id).value.trim();const body={directory:value('directory'),config:{schemaVersion:1,brand:value('brand'),accountProtocol:'platform-v1',accountBaseUrl:value('account'),websiteUrl:value('website'),registerUrl:value('register'),forgotUrl:value('forgot'),contentUrl:value('content'),realmId:value('realm'),realmName:value('realm-name'),adapterId:'s4a21-cn-local-20261013',gameHost:value('host'),gamePort:Number(value('port')),clientDirectory:value('client')}};for(const name of ['register','forgot'])if(!value(name))delete body.config[name==='register'?'registerUrl':'forgotUrl'];for(const [id,key] of [['update-base','updateBaseUrl'],['manifest-source','clientManifestUrl'],['artifact-prefix','clientArtifactPrefix'],['client-edition','clientEdition']])if(value(id))body.config[key]=value(id);return body;}
function invalidatePackage(){$('package-install').dataset.enabled='false';$('package-install').disabled=true;$('package-step-check').classList.remove('complete');$('package-step-install').classList.remove('complete');$('package-checks').replaceChildren();$('package-result').textContent='目录或配置已修改，请重新检查客户端。';}
launcherConfigSection.addEventListener('input',invalidatePackage);
$('package-inspect').onclick=()=>run(async()=>{const report=await api('/api/admin/launcher/inspect',packageBody());$('package-checks').replaceChildren();for(const item of report.items){const p=document.createElement('p');p.textContent=item.name+'：'+(item.ok?'通过':'需要处理');p.dataset.ok=String(item.ok);$('package-checks').append(p);}$('package-install').disabled=!report.ready;$('package-step-check').classList.toggle('complete',report.ready);$('package-install').dataset.enabled=String(report.ready);$('package-result').textContent=report.ready?'基础检查通过，可以安装服务器配置。启动器还会检查插件；真实入场需单独验证。':'客户端基础检查未通过，请处理上方项目后重试。';});
$('package-install').onclick=()=>run(async()=>{const result=await api('/api/admin/launcher/install',packageBody());$('package-step-install').classList.add('complete');$('package-result').textContent='服务器配置已安装。下一步：打包完整目录，并进行实际登录与入场测试。';$('package-output-details').hidden=false;$('package-output-path').textContent='配置：'+result.path+(result.backup?'；旧配置备份：'+result.backup:'');});

const releaseSection=document.createElement('section');
releaseSection.innerHTML='<h2>生成客户端下载与资源更新</h2><p>选择干净的 S4A21_CN 客户端目录。首次生成完整 ZIP；以后选择上一版受管清单，生成新增、替换、删除列表与待发布资源。不会自动上线。</p><label>游戏客户端目录<input id="release-client-directory" placeholder="包含 DNF.exe、ImagePacks2、SoundPacks 的目录"></label><button id="release-choose">选择客户端目录</button><label>资源版本<input id="release-version" value="1.0.0" maxlength="64"></label><label>上一版 manifest.json（首次可留空）<input id="release-baseline" type="file" accept="application/json,.json"></label><label class="check"><input id="release-archive" type="checkbox" checked>同时生成完整 ZIP</label><label>ZIP 外层目录（自动安装会去掉这一层）<input id="release-wrapper" value="S4A21_CN"></label><button id="release-build" class="primary">生成待审核发布包</button> <button id="release-open" hidden>打开发布目录</button><p id="release-state" role="status">只收集游戏程序、DLL、PVF、资源目录及已知插件默认设置；不收集截图、日志、启动器或私人数据。已有玩家 INI/CFG/XML/JSON 不覆盖、不删除。</p><small>文件复制与压缩可能需要较长时间。确认 changes.pending.json 后，先上传资源并核对真实 HTTPS 直链、大小、SHA256 和 Range 响应，最后发布 manifest.json。删除仅作用于旧清单受管且未修改的文件；发生冲突时启动器拒绝更新。</small>';
pages.get('launcher').prepend(releaseSection);
let publicationId;
$('release-choose').onclick=async()=>{try{if(!window.__TAURI__?.core)throw Error('浏览器模式请手动输入完整目录');const p=await window.__TAURI__.core.invoke('choose_package_directory');if(p)$('release-client-directory').value=p;}catch(e){$('release-state').textContent=e.message||String(e);}};
$('release-baseline').onchange=()=>{if($('release-baseline').files.length){$('release-archive').checked=false;$('release-wrapper').value='';}};
$('release-build').onclick=()=>run(async()=>{let baseline;const file=$('release-baseline').files[0];if(file){if(file.size>8388608)throw Error('基线清单最大 8 MB');baseline=JSON.parse(await file.text());}
 $('release-open').hidden=true;$('release-state').textContent='正在校验、复制和压缩客户端资源，请稍候…';
 try{const body={directory:$('release-client-directory').value.trim(),version:$('release-version').value.trim(),buildArchive:$('release-archive').checked,archiveRoot:$('release-archive').checked?$('release-wrapper').value.trim():''};if(baseline)body.baseline=baseline;const r=await api('/api/admin/client/publish',body);publicationId=r.id;$('release-state').textContent=`已生成 ${r.files} 个文件的待审核清单：新增 ${r.added}，替换 ${r.replaced}，删除 ${r.removed}，玩家设置保留 ${r.settingsPreserved}。路径：${r.path}。尚未上线。`;$('release-open').hidden=!window.__TAURI__?.core;}
 catch(e){$('release-state').textContent=e.message;throw e;}
});
$('release-open').onclick=()=>window.__TAURI__.core.invoke('manager_open_publication',{id:publicationId}).catch(e=>{$('release-state').textContent=e?.message||String(e);});

const sources=document.createElement('details');sources.innerHTML='<summary>更新与资源来源（可选）</summary><label>更新源 HTTPS origin<input id="package-update-base" placeholder="https://updates.example.com"></label><label>客户端清单 URL<input id="package-manifest-source" placeholder="https://cdn.example.com/client/manifest.json"></label><label>资源 URL 前缀<input id="package-artifact-prefix" placeholder="https://cdn.example.com/client/releases/"></label><label>客户端发行标识<input id="package-client-edition" placeholder="sponsor"></label><p>客户端清单、资源前缀、发行标识须同时填写或同时留空。注册和找回网页可以留空。</p>';
$('package-advanced').append(sources);
window.addEventListener('meow-profile',event=>{$('package-advanced').querySelector('p').textContent='请填写你自己的公开服务地址；本仓库不提供默认服务器地址，也不填写管理密钥。';});
