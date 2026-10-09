import base64,json
from pathlib import Path
import requests
root=Path(__file__).resolve().parent
key=(root/'fastapi_vkey.txt').read_text().strip()
headers={'Authorization':'Bearer '+key}
clip=(root/'synthetic-listener.wav').read_bytes()
results=[]
for task in ['pl/aptitude-validation','pl/interview-must-ask','pl/interview-listener','pl/reading-audio','pl/role-transcription']:
 for force in [False,True]:
  p=json.loads((root/'policies/tasks.json').read_text())['tasks'][task]
  content='Return JSON {"ok":true}.'
  if p['modality']=='audio':content=[{'type':'text','text':'Listen and return JSON with a brief transcript.'},{'type':'input_audio','input_audio':{'data':base64.b64encode(clip).decode(),'format':'wav'}}]
  body={'model':task,'messages':[{'role':'user','content':content}],'response_format':{'type':'json_object'},'max_tokens':1024}
  if force:body['mock_timeout']=True
  r=requests.post('http://localhost:4000/v1/chat/completions',headers=headers,json=body,timeout=280)
  actual=r.headers.get('x-litellm-model-group');j=r.json()
  result={'task':task,'forced':force,'status':r.status_code,'actual':actual,'ok':r.status_code==200 and actual in (p['fallbacks'] if force else [p['primary'],*p['fallbacks']])}
  if not result['ok']:
   import re
   msg=j.get('error',{}).get('message','')
   result['quota_details']=[x[:160] for x in re.findall(r'.{0,10}(?:quotaMetric|quotaId|quotaValue|retryDelay|PerDay|PerMinute).{0,140}',msg)]
  results.append(result);print(json.dumps(result),flush=True)
(root/'remaining-route-results.json').write_text(json.dumps(results,indent=2)+'\n')
print('PASS',sum(r['ok'] for r in results),'/',len(results),flush=True)
