(()=>{
 const section=document.createElement('section');section.innerHTML='<h2>独立合成演练</h2><p>仅控制本管理器内置的合成进程，用于验证健康、日志和启停。它不启动游戏、不连接云端、不读取玩家数据库。正常启动默认禁用演练；不能在此填写命令、PID 或数据库密钥。</p><button id="fixture-refresh">读取演练状态与日志</button><button id="fixture-start" disabled>启动合成进程</button><button id="fixture-stop" disabled>停止自有合成进程</button><p id="fixture-state" role="status">尚未读取；不会自动启动。</p><pre id="fixture-logs"></pre>';
 pages.get('deploy').append(section);
 let cursor=0,lines=[];
 function render(data){$('fixture-state').textContent=data.message+' · '+(data.running?(data.healthy?'进程握手/心跳正常':'尚无有效心跳'):'已停止');$('fixture-start').disabled=!data.enabled||data.running;$('fixture-stop').disabled=!data.running;}
 async function logs(){const data=await api('/api/admin/fixture-control/logs?after='+cursor);if(data.truncated)lines=['较早演练日志已移出缓存'];lines.push(...data.items.map(line=>line.seq+' · '+new Date(line.at).toLocaleString('zh-CN',{timeZone:'Asia/Hong_Kong',hour12:false})+' · '+line.text));lines=lines.slice(-200);cursor=data.cursor;$('fixture-logs').textContent=lines.join('\n');}
 $('fixture-refresh').onclick=()=>run(async()=>{render(await api('/api/admin/fixture-control/status'));await logs();});
 for(const action of ['start','stop'])$('fixture-'+action).onclick=()=>run(async()=>{render(await api('/api/admin/fixture-control/'+action,{}));await logs();});
})();
