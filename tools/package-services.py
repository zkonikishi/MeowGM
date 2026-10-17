"""Package only reviewed service sources and static UI, never runtime data/secrets."""
import hashlib
import json
from pathlib import Path
import zipfile
import argparse
import re

root=Path(__file__).resolve().parent.parent
files=[
    'services/gateway/'+name for name in (
        'pvf_tools.py','MeowGate.py','client_publisher.py','public_config.py','server.py','admission.py','operations.py','gm_adapter.py','connections.py','tunnel.py','deployment.py','deploy/managed_remote.py','content_export.py','content_contract.py',
        'ADMISSION-CONTRACT.txt','environment.example.txt',
        'deploy/oo-admission.service','deploy/check-admission.py','deploy/OPERATIONS.txt')
]+['apps/admin/'+name for name in ('minimize.png','close.png','pvf.js','launcher-config.js','shell.js','manager-background.png','arad-wordmark.png','index.html','app.js','desktop.js','connections.js','content-export.js','style.css')]+['tools/Start-Manager.ps1','tools/export-content.py']
payload={name:(root/name).read_bytes() for name in files}
shared=root.parent/'登陆器赞助版'/'pvf_protection.py'
payload['services/gateway/pvf_protection.py']=shared.read_bytes()
manifest={'format':1,'productionValidated':False,'documentation':'C:/workspace/README.md','files':{name:hashlib.sha256(data).hexdigest() for name,data in payload.items()}}
parser=argparse.ArgumentParser()
parser.add_argument('--release-name',required=True)
args=parser.parse_args()
if not re.fullmatch(r'[A-Za-z0-9._-]+',args.release_name) or args.release_name in ('.','..'):parser.error('invalid release name')
output=root/'releases'/args.release_name/'Gateway-MeowGM.zip'
output.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
    for name,data in payload.items():archive.writestr(name,data)
    archive.writestr('manifest.json',json.dumps(manifest,indent=2)+'\n')
with zipfile.ZipFile(output) as archive:
    assert archive.testzip() is None
    assert set(archive.namelist())==set(files)|{'manifest.json'}
print(str(output))
print('SHA256 '+hashlib.sha256(output.read_bytes()).hexdigest())
