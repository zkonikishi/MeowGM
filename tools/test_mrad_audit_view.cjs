// Execute the real UI handlers offline with a minimal DOM; no local server starts.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map();
function node(id='') {return {id,hidden:true,value:'',textContent:'',disabled:false,
  children:[],replaceChildren(){this.children=[];},append(...items){this.children.push(...items);}};}
const page=node('mrad');
Object.defineProperty(page,'innerHTML',{set(html){
  for(const match of html.matchAll(/id="([^"]+)"/g))nodes.set(match[1],node(match[1]));
}});
page.querySelectorAll=()=>[...nodes.values()];
nodes.set('workspace',node('workspace'));
let response={version:1,available:false,items:[],nextCursor:null},failure=null,calls=[];
const context={pages:new Map([['mrad',page]]),document:{head:node(),
  createElement:()=>node(),getElementById:id=>nodes.get(id)},
  $:id=>nodes.get(id),window:{addEventListener(){}},
  MutationObserver:class{observe(){}},
  api:async route=>{calls.push(route);if(failure)throw Error(failure);return response;},
  console};
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'../apps/admin/mrad.js'),'utf8'),context);
(async()=>{
  const get=id=>nodes.get('mrad-'+id);
  assert.equal(calls.length,0,'Must not auto-query');
  await get('audit-refresh').onclick();
  assert.deepEqual(calls,['/api/admin/mrad/audit']);
  assert.match(get('audit-state').textContent,/不可用/);
  assert.match(get('audit-count').textContent,/没有读取/);
  assert.equal(get('audit-next').disabled,true);
  get('audit-kind').onchange();assert.equal(get('audit-count').textContent,'未读取回执。');
  response={version:1,available:true,items:[{uid:'unverified-player'}]};
  await get('audit-refresh').onclick();
  assert.match(get('state').textContent,/不能展示未经验证/);
  assert.ok(!get('audit-count').textContent.includes('unverified-player'));
  failure='403 无此审计权限';await get('audit-refresh').onclick();
  assert.match(get('state').textContent,/403/);
  assert.equal(get('audit-count').textContent,'未读取回执。');
  assert.equal(get('audit-next').disabled,true);
  console.log('PASS: real audit UI unavailable state, no auto-query, pagination disabled, category reset, unverified data and permission rejection clear stale state; offline only');
})().catch(error=>{console.error(error);process.exitCode=1;});
