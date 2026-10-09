#!/usr/bin/env bash
# One-time PROD virtual-key setup for centralized routing. Run on the PROD builder
# AFTER the gateway has the hook + policy, BEFORE deploying migrated services.
# Prints no secrets. Idempotent except step 2 (skips if the Secret already exists).
set -euo pipefail
export PATH=$HOME/bin:$PATH
NS=api

# 1. corporate-node-v2-prod is restricted to physical model names; the gateway checks
#    the requested name (pl/<task>) against it, so add the corp tasks. Keep the old
#    names: src/lib/pdfVision.ts still sends env.JD_PARSER_MODEL (gemini-2.5-flash).
kubectl -n $NS get cm corp-v2-api-config -o jsonpath='{.data.\.env}' \
 | sed -n 's/^LITELLM_VIRTUAL_KEY=//p' | tr -d '"\r' \
 | kubectl -n $NS exec -i deploy/litellm -- python -c '
import json,os,sys,urllib.request
corp=sys.stdin.read().strip(); master=os.environ["LITELLM_MASTER_KEY"]
def call(path,body):
    r=urllib.request.Request("http://localhost:4000"+path,data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+master,"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(r,timeout=30))
r=urllib.request.Request("http://localhost:4000/key/info?key="+corp,headers={"Authorization":"Bearer "+master})
models=json.load(urllib.request.urlopen(r,timeout=30))["info"]["models"]
tasks=["pl/corporate-"+t for t in ("screening","guidance","probe","stage-decision","diagnosis","jd-generation","jd-parse","assessment-settings","workflow","web-search")]
new=sorted(set(models)|set(tasks))
call("/key/update",{"key":corp,"models":new})
print("corporate-node-v2-prod models:",new)'

# 2. form-data-normalization (+worker, +cron) already reaches the gateway on PROD with the
#    unrestricted "form-data-normalization" key: the builder env file is baked into the
#    image as /app/.env and load_dotenv() exports it. The migrated client fails closed if
#    the vars are missing from os.environ, so also expose them as real env on all three
#    deployments (attached in rollout step 6), independent of import order.
if ! kubectl -n $NS get secret form-data-normalization-llm >/dev/null 2>&1; then
  ENVF=$HOME/repositories/envs/api/form-data-normalization.env
  kubectl -n $NS create secret generic form-data-normalization-llm \
    --from-literal=LITELLM_PROXY_URL="$(sed -n 's/^LITELLM_PROXY_URL=//p' "$ENVF" | tr -d '"\r')" \
    --from-literal=LITELLM_VIRTUAL_KEY="$(sed -n 's/^LITELLM_VIRTUAL_KEY=//p' "$ENVF" | tr -d '"\r')"
  echo "created secret form-data-normalization-llm from $ENVF"
fi
