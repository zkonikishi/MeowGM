if(window.__TAURI__?.core){
  document.body.classList.add('desktop-frame');
  const chrome=document.createElement('div');chrome.id='manager-chrome';
  chrome.innerHTML='<div id="manager-drag" title="拖动窗口，双击最大化"></div><button class="window-control" data-window="minimize" aria-label="最小化"><img src="/minimize.png" alt=""></button><button class="window-control" data-window="close" aria-label="关闭管理器"><img src="/close.png" alt=""></button>';
  document.body.prepend(chrome);
  const action=value=>window.__TAURI__.core.invoke('manager_window_action',{action:value}).catch(()=>{});
  chrome.querySelector('#manager-drag').onmousedown=e=>{if(e.button===0&&e.detail===1)action('drag');};
  chrome.querySelector('#manager-drag').ondblclick=()=>action('maximize');
  for(const button of chrome.querySelectorAll('button'))button.onclick=()=>action(button.dataset.window);
}
(async()=>{
  const incoming=new URLSearchParams(location.hash.slice(1)).get('setup');
  if(incoming)sessionStorage.setItem('managerWindow',incoming);
  history.replaceState(null,'','/');
  const response=await fetch('/api/desktop/setup');
  if(!response.ok)throw Error('本机服务初始化失败');
  const state=await response.json();
  if(state.localMode){
    window.managerLocalMode=true;
    $('login').hidden=true;$('logout').hidden=true;
    window.reconnectLocal=async()=>{
      const nonce=sessionStorage.getItem('managerWindow');
      if(!nonce)throw Error('请从 MeowGM 程序窗口打开管理器');
      const r=await fetch('/api/desktop/connect',{method:'POST',headers:{'Content-Type':'application/json','X-OO-Window':nonce},body:'{}'});
      const result=await r.json();if(!r.ok)throw Error(result.error||'本机窗口验证失败');
    };
    await window.reconnectLocal();
  }
  await load();status(state.localMode?'本地模式 · 请配置服务器并手动连接。':'已恢复管理会话。');
})().catch(e=>status(e.message,true));
