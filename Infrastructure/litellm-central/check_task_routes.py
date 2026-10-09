"""Synthetic gateway routing checks; records actual model from response headers."""
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys
import time
import requests

root=Path(__file__).resolve().parent
policies=json.loads((root/'policies/tasks.json').read_text())['tasks']
key=Path(sys.argv[1]).read_text().strip()
headers={'Authorization':'Bearer '+key}
base='http://localhost:4000/v1'

def check(task,force):
    policy=policies[task]
    body={'model':task,'messages':[{'role':'user','content':'Return JSON {"ok":true} only.'}],
          'response_format':{'type':'json_object'},'max_tokens':256,
          'reasoning_effort':'disable','temperature':0}
    if force:body['mock_timeout']=True
    start=time.monotonic()
    response=requests.post(base+'/chat/completions',headers=headers,json=body,timeout=280)
    data=response.json();actual=response.headers.get('x-litellm-model-group')
    valid=policy['fallbacks'] if force else [policy['primary'],*policy['fallbacks']]
    ok=response.status_code==200 and actual in valid and bool(data.get('choices',[{}])[0].get('message',{}).get('content'))
    result={'task':task,'forced':force,'status':response.status_code,'actual':actual,
            'seconds':round(time.monotonic()-start,2),'ok':ok}
    if not ok:result['error']=str(data.get('error',{}))[:250]
    return result

results=[]
with ThreadPoolExecutor(max_workers=4) as pool:
    jobs=[pool.submit(check,task,force) for task,p in policies.items() if p['modality']=='text' for force in [False,True]]
    for job in as_completed(jobs):
        try:r=job.result()
        except Exception as e:r={'ok':False,'error':str(e)[:250]}
        results.append(r);print(json.dumps(r),flush=True)
# A real spoken clip verifies the audio request shape and its Gemini-only fallback.
clip=root/'synthetic-listener.wav'
if not clip.exists():subprocess.run(['espeak','-w',str(clip),'Hello. I worked with my team to solve a customer problem. We listened carefully and explained the next steps.'],check=True)
audio={'type':'input_audio','input_audio':{'data':base64.b64encode(clip.read_bytes()).decode(),'format':'wav'}}
for task in ['pl/interview-listener','pl/reading-audio','pl/role-transcription']:
    for force in [False,True]:
        body={'model':task,'messages':[{'role':'user','content':[{'type':'text','text':'Listen to this audio. Return JSON {"heard": "brief transcript"}.'},audio]}],
              'response_format':{'type':'json_object'},'max_tokens':1024}
        if force:body['mock_timeout']=True
        response=requests.post(base+'/chat/completions',headers=headers,json=body,timeout=280)
        data=response.json();actual=response.headers.get('x-litellm-model-group');p=policies[task]
        r={'task':task,'forced':force,'status':response.status_code,'actual':actual,
           'ok':response.status_code==200 and actual in (p['fallbacks'] if force else [p['primary'],*p['fallbacks']])}
        if not r['ok']:r['error']=str(data.get('error',{}))[:250]
        print(json.dumps(r),flush=True);results.append(r)
(root/'task-route-results.json').write_text(json.dumps(results,indent=2)+'\n')
print('TOTAL',sum(r['ok'] for r in results),'/',len(results),flush=True)
sys.exit(any(not r['ok'] for r in results))
