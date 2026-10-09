#!/usr/bin/env bash
# PROD equivalent of apply_policy.py. Run on the PROD builder (140.245.25.134).
#   prod_apply_policy.sh <candidate.json>           validate only
#   prod_apply_policy.sh <candidate.json> --apply   validate, back up, activate, wait until the pod sees it
# Rollback = run it with a file from ~/pl-oks-cluster/api-ns/litellm/policy-backups/.
# Needs the central hook already rolled out (validate_policy lives in it).
set -euo pipefail
export PATH=$HOME/bin:$PATH
NS=api
CAND=$1
DIR=$HOME/pl-oks-cluster/api-ns/litellm
python3 -m json.tool "$CAND" >/dev/null

# 1. Validate with the exact hook code running in the gateway pod.
kubectl -n $NS exec -i deploy/litellm -- python -c '
import json,sys
sys.path.insert(0,"/app")
from pl_openai_fallback import validate_policy
p=json.load(sys.stdin)
assert p.get("version")==1 and isinstance(p.get("tasks"),dict) and p["tasks"], "bad document"
for t,v in p["tasks"].items(): validate_policy(t,v)
print("valid tasks:",len(p["tasks"]))' < "$CAND"

# 2. Every model in every chain must be registered on PROD.
kubectl -n $NS exec -i deploy/litellm -- python -c '
import json,os,sys,urllib.request
p=json.load(sys.stdin)
r=urllib.request.Request("http://localhost:4000/v1/models",headers={"Authorization":"Bearer "+os.environ["LITELLM_MASTER_KEY"]})
have={m["id"] for m in json.load(urllib.request.urlopen(r,timeout=30))["data"]}
used={m for v in p["tasks"].values() for m in [v["primary"],*v["fallbacks"]]}
missing=used-have
if missing: sys.exit("Register on PROD first: "+", ".join(sorted(missing)))
print("all",len(used),"models registered")' < "$CAND"

[ "${2:-}" = "--apply" ] || { echo "Validated only. Re-run with --apply to activate."; exit 0; }

# 3. Back up the live policy, then activate.
mkdir -p "$DIR/policy-backups"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
if kubectl -n $NS get cm litellm-task-policy >/dev/null 2>&1; then
  kubectl -n $NS get cm litellm-task-policy -o jsonpath='{.data.tasks\.json}' > "$DIR/policy-backups/tasks-$STAMP.json"
  echo "backup: $DIR/policy-backups/tasks-$STAMP.json"
fi
kubectl -n $NS create configmap litellm-task-policy --from-file=tasks.json="$CAND" --dry-run=client -o yaml | kubectl apply -f -
cp "$CAND" "$DIR/tasks.json"   # builder copy = source of truth for the next edit

# 4. kubelet propagates a directory-mounted ConfigMap in ~60-120 s; wait for the pod to see it.
WANT=$(sha256sum < "$CAND" | cut -d' ' -f1)
for _ in $(seq 1 36); do
  GOT=$(kubectl -n $NS exec deploy/litellm -- sh -c 'sha256sum < /app/policies/tasks.json' 2>/dev/null | cut -d' ' -f1 || true)
  [ "$GOT" = "$WANT" ] && { echo "Active in pod; next request uses it. Run prod_check_routes.sh."; exit 0; }
  sleep 5
done
echo "Pod has not picked up the policy after 180 s; check the volume mount (must not be subPath)." >&2
exit 1
