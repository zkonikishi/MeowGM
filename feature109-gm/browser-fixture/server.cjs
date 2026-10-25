'use strict';
// Preparation artifact: run explicitly after review. Does not launch a browser.
const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');
// Obtain the OS process birth time only when the fixture is explicitly started.
const processStartTimeUtc=execFileSync('powershell.exe',['-NoProfile','-NonInteractive','-Command',`(Get-Process -Id ${process.pid}).StartTime.ToUniversalTime().ToString('o')`],{encoding:'utf8',windowsHide:true,timeout:5000}).trim();
if(!/^\d{4}-\d{2}-\d{2}T/.test(processStartTimeUtc))throw Error('Cannot establish fixture process identity');
const root=path.resolve(__dirname,'../..'),sourceRoot=path.join(root,'../Mrad Max/src/DNF115CN.GM/wwwroot/js');
const pins={'stackables.js':'1841f4361e5893150576d842f1d820c3572a20f79368797776b3077090327b0d','equipment.js':'6adad125f5ca1ca1c9982396c0d0e041e0bffc486ae30b2ccdf8de2a5e8cc303'};
const digest=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const source=new Map();for(const [name,hash]of Object.entries(pins)){const bytes=fs.readFileSync(path.join(sourceRoot,name));if(digest(bytes)!==hash)throw Error('source pin mismatch: '+name);source.set('/source/'+name,bytes);}
const routes=new Map([['/',{bytes:fs.readFileSync(path.join(__dirname,'fixture.html')),type:'text/html; charset=utf-8'}],['/bootstrap.js',{bytes:fs.readFileSync(path.join(__dirname,'bootstrap.js')),type:'text/javascript; charset=utf-8'}],...[...source].map(([key,bytes])=>[key,{bytes,type:'text/javascript; charset=utf-8'}])]);
let lastAccess=Date.now(),closing=false;
const server=http.createServer((req,res)=>{
  const expectedHost='127.0.0.1:'+server.address().port;
  const route=req.method==='GET'&&req.headers.host===expectedHost&&routes.get(req.url);
  if(!route||req.headers['transfer-encoding']||req.headers['content-length']&&req.headers['content-length']!=='0'){
    res.writeHead(403,{'Content-Type':'text/plain','Cache-Control':'no-store'});res.end('fixture rejects request');return;
  }
  lastAccess=Date.now();res.writeHead(200,{'Content-Type':route.type,'Content-Length':route.bytes.length,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
    'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'"});res.end(route.bytes);
});
server.requestTimeout=5000;server.headersTimeout=5000;server.keepAliveTimeout=1000;
function stop(reason){if(closing)return;closing=true;clearInterval(timer);server.close(()=>{
  const after=Object.fromEntries(Object.keys(pins).map(name=>[name,digest(fs.readFileSync(path.join(sourceRoot,name)))]));
  console.log(JSON.stringify({event:'fixture-stopped',reason,pid:process.pid,processStartTimeUtc,sourcePinsUnchanged:Object.entries(after).every(([name,hash])=>pins[name]===hash),pins:after}));
});server.closeAllConnections();}
const timer=setInterval(()=>{if(Date.now()-lastAccess>=300000)stop('5-minute-idle');},1000);
process.on('SIGINT',()=>stop('SIGINT'));process.on('SIGTERM',()=>stop('SIGTERM'));
server.on('error',error=>{clearInterval(timer);console.error(error.message);process.exitCode=1;});
server.listen(0,'127.0.0.1',()=>console.log(JSON.stringify({event:'fixture-ready',url:'http://127.0.0.1:'+server.address().port+'/',pid:process.pid,processStartTimeUtc,idleTimeoutSeconds:300,browserLaunched:false,scope:'synthetic-no-real-auth',pins})));
