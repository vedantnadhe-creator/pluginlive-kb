"""Prove policy changes take effect without restarting the gateway."""
from pathlib import Path
import json
import subprocess
import requests
root=Path(__file__).resolve().parent
base=json.loads((root/'policies/tasks.json').read_text())
original=(root/'policies/tasks.json').read_bytes()
candidate=root/'policy-smoke-candidate.json'
started=subprocess.check_output(['docker','inspect','litellm','-f','{{.State.StartedAt}}'],text=True).strip()
key=(root/'fastapi_vkey.txt').read_text().strip()
results=[]
try:
 for model in ['gpt-6-luna','gpt-5.4-mini']:
  base['tasks']['pl/policy-smoke']={'primary':model,'fallbacks':[],'timeout':30,'retries':0,'reasoning':{model:'none'},'modality':'text'}
  candidate.write_text(json.dumps(base))
  subprocess.run(['python3',str(root/'apply_policy.py'),str(candidate),'--apply'],check=True)
  r=requests.post('http://localhost:4000/v1/chat/completions',headers={'Authorization':'Bearer '+key},json={'model':'pl/policy-smoke','messages':[{'role':'user','content':'Reply OK.'}]},timeout=40)
  actual=r.headers.get('x-litellm-model-group');results.append({'configured':model,'actual':actual,'status':r.status_code})
  assert r.status_code==200 and actual==model
finally:
 candidate.write_bytes(original)
 subprocess.run(['python3',str(root/'apply_policy.py'),str(candidate),'--apply'],check=True)
 candidate.unlink()
ended=subprocess.check_output(['docker','inspect','litellm','-f','{{.State.StartedAt}}'],text=True).strip()
assert started==ended
result={'results':results,'gateway_start_unchanged':started==ended}
(root/'hot-switch-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
