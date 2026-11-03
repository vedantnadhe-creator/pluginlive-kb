# PROD Kubernetes rollouts: deploy path and zero-downtime rules

PROD runs on OCI Kubernetes (namespaces `api`, `frontend`). Access is via the PROD box (`ssh ubuntu@140.245.25.134`). Non-interactive shells need `export PATH=$HOME/bin:$HOME/.local/bin:$PATH` for the `oci` kubectl credential plugin.

## Deploy path
`~/autodeploy.sh <app> <branch>` on the PROD box:
- it checks out `<branch>` in `~/repositories/<api|frontend>/<app>` (`git stash`, `fetch`, `checkout`, `pull`);
- it builds with `--build-arg ENVIRONMENT=prod` and pushes `bom.ocir.io/bmv2bqg5gpcd/<ocr>:<timestamp>-<branch>`;
- it rolls out with **`kubectl set image`** only. The rest of the deployment spec (probes, resources, env) is untouched.

Ship a fix by cherry-picking onto the branch PROD currently runs: take it from the image tag (`kubectl -n <ns> get deploy <app> -o jsonpath='{..image}'`). Check that the branch has no unreleased commits first. Leave held work out: `[attempt-integrity]` has PROD HOLD (see `Assessment/attempt-integrity.md`). Resolve conflicts by keeping PROD's lines and changing only your own.

## Zero-downtime rule: every single-replica deployment needs a readiness probe
With `replicas: 1`, `maxSurge 50%` and `maxUnavailable 25%`, Kubernetes surges 1 new pod and removes the old one as soon as the new one is Ready. **Without a readiness probe, "Ready" means the container has started**, not that the app is listening. You get a few seconds of 502s on every rollout and restart.

| Deployment | Probe | Since |
|---|---|---|
| `frontend/institute-react-v2` | `httpGet /v2/dashboard :3000` | (pre-existing) |
| `api/institute-node` | `tcpSocket :8080`, initialDelay 5s, period 5s, failureThreshold 3 | 2026-11-03 (`kubectl patch` on the same image; old pod served until the new one listened) |

Adding a probe with `kubectl patch` triggers one rollout, and the new pod already carries the probe, so the patch itself causes no gap. If the probe is wrong, the rollout stalls while the old pod keeps serving; recover with `kubectl rollout undo`. **Never `kubectl apply` an old saved YAML that lacks the probe.** institute-node has no SIGTERM handler, so a request in flight at the instant the old pod stops can still fail (sub-second; any restart).

## 2026-11-03 deploy record (progression drawer changes)
- `api/institute-node` → `release-v1.42-hotfix-2` @ `52fa1f0` (hotfix-1 + `8f04a67` Current difficulty = latest suggested CEFR + `d02526c` per-sitting level from `progression_history`, cherry-picked without the attempt-integrity columns). Image `pl-institute-api:2026-11-03-06-25-13-release-v1.42-hotfix-2`.
- `frontend/institute-react-v2` → `release-v1.42-hotfix-3` @ `84c6c54` (hotfix-2 + `95104d6`). Image `pl-institute-react-v2:2026-11-03-06-29-27-release-v1.42-hotfix-3`.
- Verified: both 1/1 with 0 restarts and 0 5xx. The live drawer API for `riya0125@vsmedu.in` returns Achieved A2 · Current difficulty A2 · Diagnosis B1 / #1 A1 / #2 A1. The bundle has the change and no dev/uat URLs. `https://institute.pluginlive.com/v2/dashboard` returns 200.
- 07:41Z: `api/institute-node` → `release-v1.42-hotfix-3` @ `9a4e17a` (hotfix-2 + `a8d25ca`: post-diagnosis Communication sitting level = previous row's suggested CEFR). Before shipping, read-only timings on PROD's heaviest Communication schedules (~21k assignments) were unchanged: overview/roster ~2 s, drawer ~1 s. The rollout kept the old pod until the new one was ready; 0 restarts, 0 5xx, 0 error-level lines. Live Riya: Diagnosis B1 · #1 A2 · #2 A2, Achieved A2 · Current difficulty A2.
- Rollback: `~/prod-deploy-20261103-progression/` on the PROD box (`rollback-images.txt`, `*.before.yaml`). For example, `kubectl -n api set image deploy/institute-node institute-node=<previous image>`.
