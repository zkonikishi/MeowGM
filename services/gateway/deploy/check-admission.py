"""Local authenticated process/storage check; does not consume a game ticket."""
import json
import os
import urllib.request

port=int(os.environ.get('OO_ADMISSION_PORT','17861'))
key=os.environ['OO_GAME_KEY']
request=urllib.request.Request(f'http://127.0.0.1:{port}/internal/v1/admissions/health',headers={'X-OO-Game-Key':key})
try:
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request,timeout=5) as response:
        result=json.loads(response.read(4096))
        if response.status!=200 or result.get('ok') is not True or result.get('protocol')!='prepare-claim-v1':raise ValueError()
    print('Admission process and local storage healthy; platform and real game admission not checked.')
except Exception:
    raise SystemExit('Admission health check failed; inspect service configuration without printing keys.') from None
