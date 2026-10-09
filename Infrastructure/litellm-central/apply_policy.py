#!/usr/bin/env python3
"""Validate a candidate policy, then atomically activate it without a restart."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.request
from dotenv import dotenv_values

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('candidate',type=Path)
parser.add_argument('--apply',action='store_true',help='activate after validation (default: validate only)')
args=parser.parse_args()
root=Path(__file__).resolve().parent
content=args.candidate.read_bytes()
document=json.loads(content)
# Validate through the exact installed gateway code without host LiteLLM dependencies.
with tempfile.NamedTemporaryFile(dir=root/'policies',suffix='.json',delete=False) as f:
    f.write(content);temporary=Path(f.name)
try:
    code='''import json,sys
from pl_openai_fallback import validate_policy
p=json.load(open(sys.argv[1]))
assert p.get("version")==1 and isinstance(p.get("tasks"),dict) and p["tasks"]
for task,policy in p["tasks"].items():validate_policy(task,policy)
'''
    subprocess.run(['docker','exec','litellm','python','-c',code,'/app/policies/'+temporary.name],check=True)
    key=dotenv_values(root/'litellm.env')['LITELLM_MASTER_KEY']
    request=urllib.request.Request('http://localhost:4000/v1/models',headers={'Authorization':'Bearer '+key})
    with urllib.request.urlopen(request,timeout=30) as response:
        registered={m['id'] for m in json.load(response)['data']}
    used={m for policy in document['tasks'].values() for m in [policy['primary'],*policy['fallbacks']]}
    missing=used-registered
    if missing:raise SystemExit('Register models in LiteLLM first: '+', '.join(sorted(missing)))
    print('Validated',len(document['tasks']),'tasks; all models registered')
    if args.apply:
        stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
        backup=root/'policy-backups'/('tasks-'+stamp+'.json');backup.parent.mkdir(exist_ok=True)
        shutil.copy2(root/'policies/tasks.json',backup)
        os.replace(temporary,root/'policies/tasks.json')
        print('Activated; next request uses this policy. Backup:',backup)
finally:
    temporary.unlink(missing_ok=True)
