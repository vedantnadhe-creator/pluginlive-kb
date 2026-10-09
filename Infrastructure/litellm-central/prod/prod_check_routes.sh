#!/usr/bin/env bash
# Calls every text pl/<task> once inside the PROD gateway pod and prints which model
# actually answered (x-litellm-model-group), the fallback count and latency.
# Audio, image and grounding tasks are skipped: verify them through the real
# fastapi / corp endpoints (see centralized-llm-routing.md, PROD rollout step 8).
# Run on the PROD builder. ~35 tiny calls, a few paise.
set -euo pipefail
export PATH=$HOME/bin:$PATH
kubectl -n api exec -i deploy/litellm -- python - <<'EOF'
import json,os,time,urllib.request,urllib.error
p=json.load(open("/app/policies/tasks.json"))["tasks"]
key=os.environ["LITELLM_MASTER_KEY"]; bad=0
for task,v in sorted(p.items()):
    if v["modality"]!="text":
        print(f"SKIP {task} ({v['modality']})"); continue
    body=json.dumps({"model":task,"messages":[{"role":"user","content":"Reply with the single word OK."}]}).encode()
    req=urllib.request.Request("http://localhost:4000/v1/chat/completions",data=body,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    t=time.time()
    try:
        with urllib.request.urlopen(req,timeout=v["timeout"]*(len(v["fallbacks"])+1)+10) as r:
            group=r.headers.get("x-litellm-model-group"); fb=r.headers.get("x-litellm-attempted-fallbacks","0")
            flag="OK  " if group==v["primary"] else "FALL"
            print(f"{flag} {task:34} {group:22} fallbacks={fb} {time.time()-t:5.1f}s")
    except urllib.error.HTTPError as e:
        bad+=1; print(f"FAIL {task:34} HTTP {e.code} {e.read()[:160]!r}")
    except Exception as e:
        bad+=1; print(f"FAIL {task:34} {e}")
print("failures:",bad)
EOF
