"""Real local Platform API + MariaDB + OO admission; no production/game database."""
import base64,json,os,secrets,socket,subprocess,sys,tempfile,time,uuid,urllib.request,urllib.error
from pathlib import Path
from contextlib import ExitStack
ROOT=Path(__file__).resolve().parents[1]
ARAD=ROOT.parents[1]
DBROOT=ARAD/'_src/PlatformDatabase';APIROOT=ARAD/'_src/DfoAccountService'
sys.path[:0]=[str(DBROOT/'.runtime/pylibs'),str(DBROOT),str(ROOT/'services/gateway')]
import pymysql
from bootstrap import initialize
from admission import AdmissionStore,Fault
from operations import Operations
NAME='pd_test_oo_'+uuid.uuid4().hex[:12]
conn=pymysql.connect(host='127.0.0.1',port=13317,user='root',autocommit=True)
with conn.cursor() as c:c.execute('CREATE DATABASE `'+NAME+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
conn.close()
def db():return pymysql.connect(host='127.0.0.1',port=13317,user='root',database=NAME,autocommit=True,charset='utf8mb4')
with db() as c:
 initialize(c)
 # Admin receipt schema comes from the formal 004 migration, never candidate DDL.
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
base='http://127.0.0.1:'+str(port)
env=os.environ.copy();env.update(ARAD_TEST_MODE='isolated',ARAD_DATABASE=f'Server=127.0.0.1;Port=13317;User ID=root;Database={NAME};SslMode=Disabled',ARAD_LISTEN=base,ARAD_PROXY_KEY=secrets.token_hex(32),ARAD_GATEWAY_KEY=secrets.token_hex(32),ARAD_IDENTITY_KEY=base64.b64encode(secrets.token_bytes(32)).decode(),ARAD_ADMIN_KEY=secrets.token_hex(32),ARAD_ADMIN_ACTOR='oo-integration',ARAD_ADMIN_PERMISSIONS='ban,unban')
# Remove inherited production transports, even though test mode already prevents real SMTP.
for key in list(env):
 if key.startswith('ARAD_SMTP_') or key.startswith('ARAD_PROVISION_'):env.pop(key)
def api(path,body=None,token=None,service='ARAD_PROXY_KEY'):
 headers={'X-Arad-Service-Key':env[service],'X-Arad-Client-IP':'203.0.113.199'}
 if body is not None:headers['Content-Type']='application/json'
 if token:headers['Authorization']='Bearer '+token
 req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
 try:r=urllib.request.urlopen(req,timeout=15)
 except urllib.error.HTTPError as e:r=e
 with r:
  payload=r.read();return r.status,json.loads(payload) if payload else {}
checks=[]
def check(name,ok):
 if not ok:raise AssertionError(name)
 checks.append(name);print('PASS',name,flush=True)
process=None
try:
 with tempfile.TemporaryDirectory(prefix='oo-platform-') as tmp:
  with open(Path(tmp)/'api.log','w',encoding='utf-8') as log, ExitStack() as cleanup:
   process=subprocess.Popen([str(Path(os.environ['LOCALAPPDATA'])/'Microsoft/dotnet/dotnet.exe'),str(Path(os.environ.get('OO_PLATFORM_BINARY',str(APIROOT/'bin/Release/DfoAccountService.dll')))),'--platform'],env=env,stdout=log,stderr=log,creationflags=0x08000000 if os.name=='nt' else 0)
   def stop_child():
    if process and process.poll() is None:process.terminate();process.wait(timeout=10)
   cleanup.callback(stop_child)
   for _ in range(80):
    if process.poll() is not None:raise RuntimeError('isolated API failed to start')
    try:
     if api('/api/account/status')[0]==200:break
    except OSError:pass
    time.sleep(.1)
   else:raise RuntimeError('isolated API readiness timeout')
   email='oo-integration@example.invalid';password=secrets.token_urlsafe(24)
   code_status,challenge=api('/api/account/sendCode',{'email':email,'purpose':'register'});check('real API accepts isolated registration challenge',code_status==202)
   for _ in range(100):
    status,mail=api('/__test/mail/'+challenge['challenge_id'])
    if status==200:break
    time.sleep(.1)
   status,registered=api('/api/account/register',{'email':email,'code':mail['code'],'challenge_id':challenge['challenge_id'],'password':password})
   check('real API creates isolated platform account',status==201);uid=registered['uid']
   status,login=api('/api/account/login',{'identifier':uid,'password':password,'intent':'platform'});check('platform session protocol',status==200 and login['protocol']=='platform-session-v1');session=login['sessionToken']
   check('pending binding cannot issue game ticket',api('/api/account/gameTickets',{},session)[0]==409)
   with db() as c:
    with c.cursor() as q:
     q.execute("UPDATE game_realm SET enabled=1 WHERE realm_id='hk'")
     q.execute("INSERT INTO game_binding(user_id,realm_id,game_account_id,game_login_name) SELECT user_id,'hk',4321,public_uid FROM platform_user WHERE public_uid=%s",(uid,))
   if '--native' in sys.argv:
    native_env=os.environ.copy();native_env.update(OO_TEST_PLATFORM_URL=base,OO_TEST_PLATFORM_KEY=env['ARAD_PROXY_KEY'],OO_TEST_UID=uid,OO_TEST_PASSWORD=password)
    cargo=Path(os.environ['USERPROFILE'])/'.cargo/bin/cargo.exe'
    result=subprocess.run([str(cargo),'test','--manifest-path',str(ROOT/'Cargo.toml'),'-p','meow-launcher-core','account::tests::platform_http_contract','--','--ignored','--exact'],env=native_env,check=False)
    check('native Rust account client real platform integration',result.returncode==0)
   def consume(ticket,rid):
    status,result=api('/internal/v1/game-tickets/consume',{'ticket':ticket,'request_id':rid,'realm_id':'hk','audience':'game-hk'},service='ARAD_GATEWAY_KEY')
    if status!=200:raise Fault('platform_rejected',401 if status<500 else 503)
    return result
   status,issued=api('/api/account/gameTickets',{},session);check('real API issues opaque game ticket',status==200 and issued['protocol']=='platform-ticket-v1')
   store=AdmissionStore(Path(tmp)/'admission.db',consume);cid=str(uuid.uuid4());ready=store.prepare(cid,uid,issued['ticket']);check('OO prepare consumes real platform ticket',ready['game_account_id']==4321)
   check('original connection prepare receipt stable',store.prepare(cid,uid,issued['ticket'])==ready)
   claimed=store.claim(cid,ready['admission_id']);check('OO claim binds strict UID',claimed['uid']==uid)
   try:store.claim(cid,ready['admission_id']);duplicate=True
   except Fault:duplicate=False
   check('second claim cannot open another admission',not duplicate)
   try:store.prepare(str(uuid.uuid4()),uid,issued['ticket']);replayed=True
   except Fault:replayed=False
   check('new connection cannot reuse consumed ticket',not replayed)
   _,fresh=api('/api/account/gameTickets',{},session)
   def admin(body):
    status,result=api('/internal/v1/admin/account-status',body,service='ARAD_ADMIN_KEY')
    if status!=200:raise AssertionError('admin API unavailable in current binary')
    return result
   ops=Operations(Path(tmp)/'ops.db',admin);ban=ops.create({'uid':uid,'action':'ban','reason':'isolated OO integration'})
   check('OO management receives real ban receipt',ban['state']=='completed')
   check('ban revokes platform session',api('/api/account/session',token=session)[0]==401)
   try:store.prepare(str(uuid.uuid4()),uid,fresh['ticket']);admitted=True
   except Fault:admitted=False
   check('ban blocks outstanding game ticket admission',not admitted)
   unban=ops.create({'uid':uid,'action':'unban','reason':'isolated OO integration complete'});check('OO unban receives real receipt',unban['state']=='completed')
   check('unban does not revive previous session',api('/api/account/session',token=session)[0]==401)
   process.terminate();process.wait(timeout=10);process=None
   log.flush();text=(Path(tmp)/'api.log').read_text()
   check('API log omits credentials',all(v not in text for v in (password,session,issued['ticket'],env['ARAD_GATEWAY_KEY'])))
finally:
 if process and process.poll() is None:process.terminate();process.wait(timeout=10)
 # Test schema retained for review; never delete a database using an unverified name.
report={'passed':checks,'database':NAME,'productionModified':False,'gameBinding':'synthetic account 4321; no game server/client','smtp':'isolated memory transport'}
(ROOT/'docs/qa/platform-admission-integration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS',len(checks),'checks; no production data modified')
