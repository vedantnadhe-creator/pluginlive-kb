# Centralized LLM routing — live on DEV, UAT and PROD

Deployed to DEV and UAT **2026-10-09**; **PROD live 2026-10-09 ~18:41 UTC** (release `release-v1.41-hotfix-4`, Raj K). PROD gateway: ConfigMap `litellm-task-policy` (= `litellm-central/prod/tasks-prod.json`, 41 tasks) mounted as a directory at `/app/policies`, hook ConfigMap `litellm-fallback-hook` = `litellm-central/pl_openai_fallback.py`, mount mirrored into `~/pl-oks-cluster/api-ns/litellm/litellm.yaml`; `corporate-node-v2-prod` key gained the 10 `pl/corporate-*` tasks. Gateway backups: `~/backups/litellm-hotfix4-20261009T184033Z/` on the PROD builder. Checks: `prod_apply_policy.sh` → 41 valid / 7 models registered; `prod_check_routes.sh` → 36 text tasks OK on primary, 0 failures; unknown task 400; legacy model names 200.

**Migrated on PROD:** fast-api `be2b28b` (`pl-fast-api:2026-10-09-18-45-32-release-v1.41-hotfix-4`) and corporate-node-v2 + worker `ef2b53f` (`pl-corporate-api-v2:2026-10-09-18-47-57-release-v1.41-hotfix-4`). **Not migrated on PROD (deferred by Raj K):** pg-vector-api-service and form-data-normalization stay on `release-v1.38-hotfix-1` and still send physical model names (served unchanged); the runbook's form-data-normalization Secret was NOT created. Audio/image/grounding tasks are not yet exercised on PROD.

## Runtime contract

All migrated chat, audio, grounding and image calls send a stable `pl/<task>` name to the environment's LiteLLM gateway using a service virtual key. Services retain prompts, inputs, output validation and an overall request deadline. Gateway policy owns physical model names, provider credentials, reasoning/thinking settings, per-attempt timeouts, retries and fallback chains. SDK retries are disabled in migrated chat clients to avoid multiplying gateway attempts.

`~/litellm/pl_openai_fallback.py` reads `~/litellm/policies/tasks.json` at the start of **every task request**, replacing caller routing settings. It snapshots that request's permitted models and reasoning settings before trying a deployment. An edit affects the next request; an in-flight request keeps its original chain. Unknown tasks return 400; unreadable/invalid policy returns 503. Missing gateway configuration fails explicitly in migrated clients rather than using a provider key directly.

The LiteLLM callback handles Gemini/OpenAI payload differences on **each attempt**, including a fallback: strips Gemini thinking fields; maps OpenAI thinking off to `reasoning_effort: none`; uses `max_completion_tokens`; removes sampling settings incompatible with reasoning; reserves at least 4096 tokens where reasoning needs them; and relaxes Gemini-oriented strict JSON schemas for OpenAI. Service output validation still applies. Gemini 3.8 uses low reasoning rather than the rejected disable setting. Gemini 2.5 Pro retains its native reasoning default.

Audio policies permit only approved Gemini hops. Input audio on a text task is rejected, and any deployment outside the request's policy is rejected. Luna/Mini are text/image-input models and cannot substitute for an audio listener. GoogleSearch grounding and image-generation tasks retain compatible Gemini-only routes. Adding a different provider/model family needs payload and modality/tool compatibility validation; changing a name does not make capabilities interchangeable.

## Changing a model without restarting services or LiteLLM

Policy directory is bind-mounted read-only at `/app/policies`, so an atomic host file replacement is visible immediately. Copy the environment's active policy, edit the chosen task, and validate before applying:

```bash
cd ~/litellm
cp policies/tasks.json tasks-candidate.json
# Edit tasks-candidate.json: primary, fallbacks, reasoning, timeout, retries.
python3 apply_policy.py tasks-candidate.json
python3 apply_policy.py tasks-candidate.json --apply
```

The helper checks policy structure and registered models using the running hook, saves `policy-backups/tasks-<UTC timestamp>.json`, then atomically activates the candidate. Registration alone is not a health/quality test: verify an actual call and forced fallback and inspect `x-litellm-model-group` / `x-litellm-model-api-base`. The response body's model can echo the requested alias. Roll back a policy with `python3 apply_policy.py policy-backups/<backup>.json --apply`.

Registered DB-managed model credentials can be changed through LiteLLM's model administration. The JSON task policy is the task-routing source of truth; changing the gateway's legacy per-model fallback list does not change migrated task chains. Virtual-key access to a newly added task must be granted before release. Some legacy keys are unrestricted; existing restrictions were extended only with their own aliases rather than replaced by unrestricted keys.

A policy edit requires **no restart**. A hook-code change requires a gateway restart; a new caller/task name requires service code deployment once. Recreate the gateway via `~/auto_deploy.sh litellm` (dispatches to `~/litellm/run.sh`), which mounts config, hook and policy directory and runs unit checks. Keep `litellm.env` private, mode 600. This rollout preserved LiteLLM **1.89.3**, exact image `sha256:e050b8661eb452f6170bb19332800b64e33b15c8edc7acd2851278eb340a4b27`, instead of pulling a moving tag. A gateway recreation on these single-instance hosts briefly interrupts its endpoint.

## Mandatory rule for every new service

The canonical rule is in `/home/ubuntu/CLAUDE.md` on DEV and UAT, under **Centralized LLM routing — mandatory**. Repository AGENTS.md files reference that single source. Every new service and new LLM call must:

1. Use the environment's gateway and service virtual key; never put physical models, provider keys, reasoning, fallback logic or a direct-provider escape path in application code.
2. Register or reuse a stable `pl/<task>` policy; give its service key access and include service/task attribution.
3. Check capability, tool, payload and scoring compatibility for every hop. Verify a normal call and forced fallback before releasing the caller.
4. Fail explicitly when the gateway/task is missing; retain prompts and output validation in the service.

Existing embeddings retain their model and vector space until a separately validated migration. Existing Deepgram/ElevenLabs/Azure/Sarvam STT/TTS integrations remain separate where their APIs are unsupported by this gateway. This is not authorization to deploy to PROD.

## Deployed callers

| Caller | DEV | UAT | Tasks / notes |
|---|---|---|---|
| fastapi-ai-engine | `3d7f6fd` | `a4a715a` | Assessment generation/scoring, interview, reading audio/gaze, role transcription, resume match, CV/JD, image generation. Removed per-request interview routing/reasoning overrides. Usage ledger records upstream model header. |
| form-data-normalization | `0fff520` | `21d0646` | normalization, entity-match, column-map. Existing APIs and UAT worker/cron updated; export-only worker unchanged. |
| pg-vector-api-service | `f179182` | `557b0c5` | entity-disambiguation, pincode-resolution, query-rewrite. Existing embeddings unchanged. |
| corporate-node-v2 | `efe4f05` | `8599226` | screening/guidance/probe/stage/diagnosis/JD/settings/workflow/web-search; actual upstream model attribution. |
| admin-react-v2 server routes | `6c080e1` | Feature absent on current UAT branch | assistant-guide / assistant-chat for existing DEV Ask Oli/Jev. UAT was not given a new assistant feature. |
| standalone Llama-JD-Parser | Source pushed | Source pushed | Shim uses pl/jd-parse; no running standalone parser was found, so none was started. Current live CV/JD parsing is inside fastapi. |

Subsequent instruction-reference commits are also pushed to Development/UAT. Admin-node's stored `aiModel` value is display metadata, not a gateway request. Old physical-model env fields can remain for historical compatibility, but migrated task callsites no longer use them for routing.

## Active task policies (41)

All policies below use **0 retries**. Timeout is per attempt, not total end-to-end time. Most mappings are shared between DEV and UAT. UAT's existing must-ask deployment differs because flash-lite was not registered there.

| Task | Primary | Fallbacks in order | Reasoning by model | Timeout (s) | Capability |
|---|---|---|---|---:|---|
| `pl/interview-probe` | `gemini-3-flash-preview` | `gpt-5.4-mini` | gemini-3-flash-preview: disable; gpt-5.4-mini: none | 6 | text |
| `pl/interview-must-ask` | `gemini-3.1-flash-lite` | `gpt-6-luna` | gemini-3.1-flash-lite: disable; gpt-6-luna: none | 4 | text |
| `pl/interview-final-score` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: low | 120 | text |
| `pl/interview-turn-score` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 30 | text |
| `pl/interview-setup` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/interview-romanize` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 12 | text |
| `pl/interview-phone` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 12 | text |
| `pl/interview-repeat-check` | `gemini-3-flash-preview` | `gpt-5.4-mini` | gemini-3-flash-preview: disable; gpt-5.4-mini: none | 6 | text |
| `pl/interview-listener` | `gemini-2.5-pro` | `gemini-3.8-flash` → `gemini-2.5-flash` | gemini-2.5-pro: native default; gemini-3.8-flash: low; gemini-2.5-flash: disable | 120 | audio |
| `pl/reading-audio` | `gemini-3.8-flash` | `gemini-2.5-flash` | gemini-3.8-flash: low; gemini-2.5-flash: disable | 60 | audio |
| `pl/reading-gaze` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 30 | text |
| `pl/aptitude-generation` | `gemini-3.8-flash` | `gpt-5.4-mini` | gemini-3.8-flash: low; gpt-5.4-mini: low | 120 | text |
| `pl/communication-generation` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/hinglish-generation` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/role-generation` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 120 | text |
| `pl/communication-score` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/role-score` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/resume-match` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/cv-parse` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 120 | text |
| `pl/jd-parse` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 120 | text |
| `pl/normalization` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 120 | text |
| `pl/entity-match` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/column-map` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 120 | text |
| `pl/entity-disambiguation` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/pincode-resolution` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/query-rewrite` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/corporate-screening` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/corporate-guidance` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/corporate-probe` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/corporate-stage-decision` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/corporate-diagnosis` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/corporate-jd-generation` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/corporate-jd-parse` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/corporate-assessment-settings` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/corporate-workflow` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/assistant-guide` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: none | 60 | text |
| `pl/assistant-chat` | `gemini-3.8-flash` | `gpt-6-luna` | gemini-3.8-flash: low; gpt-6-luna: low | 60 | text |
| `pl/corporate-web-search` | `gemini-3.8-flash` | `gemini-2.5-flash` | gemini-3.8-flash: low; gemini-2.5-flash: disable | 60 | grounding |
| `pl/assessment-image` | `gemini-2.5-flash-image` | None | native default | 120 | image |
| `pl/role-transcription` | `gemini-3.8-flash` | `gemini-2.5-flash` | gemini-3.8-flash: low; gemini-2.5-flash: disable | 60 | audio |
| `pl/aptitude-validation` | `gpt-5.4-mini` | `gpt-6-luna` → `gemini-3.8-flash` | gpt-5.4-mini: low; gpt-6-luna: low; gemini-3.8-flash: low | 120 | text |

**Preview model retired 2026-10-09 (DEV+UAT):** `gemini-3-flash-preview` was replaced by `gemini-3.8-flash` everywhere **except the live interview tasks** (`pl/interview-probe`, `pl/interview-repeat-check`, UAT `pl/interview-must-ask`). Reason: 3.8 rejects thinking-off (`minimal`/`disable` fail and fall back), and with `low` it takes 6.5–8 s per call, which exceeds the 6 s live-turn cap, so every live call would time out and hit `gpt-5.4-mini` 6 s late. Moving those tasks to 3.8 also requires raising their timeout, which is a product decision.

**UAT override:** `pl/interview-must-ask`: `gemini-3-flash-preview` → `gpt-5.4-mini`; reasoning disable → none; 6 seconds per attempt. DEV uses flash-lite → Luna, 4 seconds. Do not copy DEV policy wholesale over UAT without checking registrations and intended differences.

Aptitude validation now uses `gpt-5.4-mini` with low reasoning → Luna low → Gemini 3 Flash. The old DEV `gpt-5-mini` registration failed authentication; leaving it as primary would have hidden an avoidable failed attempt.

## PROD rollout runbook

Prepared and checked 2026-10-09 against the live cluster (read-only). Every step below was dry-run except the cluster writes themselves. Files are in [litellm-central/prod/](litellm-central/prod/). Run everything on the PROD builder `ssh ubuntu@140.245.25.134` with `export PATH=$HOME/bin:$PATH` first (without it `kubectl` fails with `executable oci not found`).

### What PROD has today (2026-10-09)

| Item | PROD state | Needed |
|---|---|---|
| LiteLLM | `deploy/litellm` in ns `api`, 1 replica, **v1.90.1** (DEV/UAT 1.89.3), image `litellm@sha256:4d7ced46…`. RollingUpdate 25%/25% → with 1 replica a new pod is ready before the old one stops, so a rollout has no gap. | — |
| Hook | ConfigMap `litellm-fallback-hook`, mounted by **subPath** at `/app/pl_openai_fallback.py` — the pre-central 10-07 version (no task routing). | Replace with `litellm-central/pl_openai_fallback.py`. subPath ⇒ needs a pod rollout. |
| Task policy | none | New ConfigMap `litellm-task-policy`, mounted as a **directory** at `/app/policies` (never subPath — subPath freezes the file at pod start). |
| Models | `gemini-2.0-flash, 2.5-flash, 2.5-flash-image, 2.5-flash-lite, 2.5-pro, 3-flash-preview, 3.8-flash, gpt-5-mini, gpt-5.4-mini, gpt-6-luna` | All 7 used by the PROD policy are registered. **`gemini-3.1-flash-lite` is not**, so PROD uses the UAT must-ask mapping (preview → gpt-5.4-mini, 6 s). |
| Keys | `fastapi-ai-engine` (unrestricted) is also used by `pg-vector-api-service`, `jdparser`, `resume-parser`. `form-data-normalization` (unrestricted). `corporate-node-v2-prod` **restricted to physical Gemini names**. | Add the 10 `pl/corporate-*` tasks to the corp key (it would 401 on task names). Own keys for pg-vector/parsers are a later attribution clean-up, not a blocker. |
| Service gateway env | fast-api `fast-api-config` `.env` and corp-v2 `corp-v2-api-config` `.env`: `LITELLM_PROXY_URL=http://litellm/v1` + key ✔. pg-vector: deployment env ✔. form-data-normalization ×3: only via baked `/app/.env` + `load_dotenv()`. | Expose the fdn vars as real env too (Secret `form-data-normalization-llm`) — the migrated client fails closed when they are missing from `os.environ`. |
| Images (rollback targets) | fast-api `pl-fast-api:2026-10-09-16-16-38-release-v1.41-hotfix-3-oncall`; corporate-node-v2 (+worker) `pl-corporate-api-v2:2026-09-16-08-21-14-release-v1.40-hotfix-1`; form-data-normalization ×3 `form-data-normalization:2026-09-04-05-31-54-release-v1.38-hotfix-1`; pg-vector `pg-vector-api-service:2026-09-04-08-48-52-release-v1.38-hotfix-1` (all under `bom.ocir.io/bmv2bqg5gpcd/`). Re-read them at rollout time. | — |
| Running code | Verified pod files == branch heads: fast-api `release-v1.41-hotfix-3-oncall`, corp-v2 `release-v1.40-hotfix-1`, fdn `release-v1.38-hotfix-1`, pg-vector `release-v1.38-hotfix-1`. | Cherry-pick plan below. |

**Verified on PROD's exact image (v1.90.1)**, in a scratch container on the builder (not the cluster): hook unit tests + OpenAI conversion tests pass; the PROD policy validates (41 tasks); a `pl/` request ignores caller `timeout`/`fallbacks`/`reasoning_effort`; a forced primary failure falls back; unknown task → 400; a policy edit and a **ConfigMap-style `..data` symlink swap** both take effect on the next request with no restart.

### Service code to ship (cherry-pick the **UAT** commits, not the Development ones)

Cut a new release branch from **whatever PROD runs at rollout time** (fast-api moves often — re-check `kubectl -n api get deploy fast-api -o wide`), then `git cherry-pick -x`:

| Repo | Base on 2026-10-09 | Commits, in order | Dry-run |
|---|---|---|---|
| fastapi-ai-engine | `release-v1.41-hotfix-3-oncall` | `8d96dc1 1018c09 0eee665 a4a715a` | clean |
| corporate-node-v2 | `release-v1.40-hotfix-1` | `0a9ce64 8599226 269ffaa` | clean |
| pg-vector-api-service | `release-v1.38-hotfix-1` | `5d50d0c 557b0c5 63bf2ef` (`5d50d0c` = gateway module tagging, a prerequisite) | clean; does **not** pull the unreleased role-cluster commits |
| form-data-normalization | `release-v1.38-hotfix-1` | `21d0646 eaf3463` | conflict, resolved: `git rm services/column_mapper.py` (bulk-upload file not on PROD) and take **theirs** for `services/gemini_client.py`. Then compiles and `python -m unittest tests.test_llm_transport_routing` passes (3/3). |

admin-react-v2 (Ask Oli) and the standalone Llama-JD-Parser are **not** in scope: Ask Oli is not on PROD, and PROD's `jdparser`/`resume-parser` deployments are legacy (live CV/JD parsing is inside fastapi). Leave them unchanged.

Known gap carried to PROD: corp-v2 `src/lib/pdfVision.ts` still sends `env.JD_PARSER_MODEL` (`gemini-2.5-flash`), so it bypasses task policy. That's why the corp key keeps its physical names. Fix in code later (`pl/corporate-jd-parse`).

### Steps

0. **Preconditions.** Explicit PROD go-ahead. **Gemini quota on the PROD key:** on 2026-10-09 Google 429'd PROD `3-flash-preview`, `2.5-flash` and `2.5-pro`. After cutover `gemini-3.8-flash` becomes primary for ~30 tasks (~3,000 calls/day), so confirm its quota/billing first. Otherwise traffic silently runs on OpenAI: it works, but costs more and final scoring takes ~17 s on Luna. Do not run alongside another PROD release.
1. **Stage files** on the builder in `~/pl-oks-cluster/api-ns/litellm/`: `pl_openai_fallback.py`, `prod/*.sh`, `prod/litellm-deployment-patch.yaml`, `prod/tasks-prod.json` (from this KB).
2. **Gateway** — backward compatible: legacy model-name requests behave exactly as today; only `pl/*` requests read the policy.
   ```bash
   cd ~/pl-oks-cluster/api-ns/litellm
   kubectl -n api create configmap litellm-task-policy --from-file=tasks.json=tasks-prod.json --dry-run=client -o yaml | kubectl apply -f -
   cp litellm-fallback-hook-configmap.yaml litellm-fallback-hook-configmap.yaml.bak-$(date -u +%Y%m%dT%H%M%SZ)   # 10-07 hook = rollback
   kubectl -n api create configmap litellm-fallback-hook --from-file=pl_openai_fallback.py --dry-run=client -o yaml > litellm-fallback-hook-configmap.yaml
   kubectl apply -f litellm-fallback-hook-configmap.yaml
   kubectl -n api patch deploy litellm --type strategic --patch-file litellm-deployment-patch.yaml   # triggers the rollout that loads the new hook
   kubectl -n api rollout status deploy/litellm --timeout=5m
   ```
   Mirror the volume + mount into `litellm.yaml` — the next `kubectl apply -f litellm.yaml` would otherwise drop it, and every task would return 503.
3. **Gateway checks:** `./prod_apply_policy.sh tasks-prod.json` (validate only) → `valid tasks: 41`, `all 7 models registered`. Then `./prod_check_routes.sh` → no `FAIL`; `FALL` means the fallback answered (e.g. Google quota). Confirm legacy traffic still flows: `kubectl -n api logs deploy/fast-api --since=10m | grep -ci error`, and that spend logs keep growing.
4. **Keys:** `./prod_service_keys.sh` (adds `pl/corporate-*` to the corp key; creates Secret `form-data-normalization-llm` from the builder env file). It prints no secrets.
5. **Build** each release branch with its usual builder script, pointed at the new branch: fast-api `~/autodeploy.sh fast-api <branch>`; corp-v2 a copy of `~/build-corp-v2-140hf1.sh` (api only); fdn a copy of `~/fdn_deploy_v138hf1.sh` (keep its ABORT guards; all three deployments get the **same** image); pg-vector a copy of `~/pgvector_deploy_v138hf1.sh`.
6. **Deploy order:** pg-vector → form-data-normalization → corporate-node-v2 (+`-worker`) → fast-api last (live interviews). For fdn, attach the env before or with the image:
   `for d in form-data-normalization form-data-normalization-worker form-data-normalization-cron; do kubectl -n api set env deploy/$d --from=secret/form-data-normalization-llm; done`
7. **Verify each service on PROD:** in `LiteLLM_SpendLogs` (`kubectl -n api exec -i deploy/litellm-postgres -- psql -U litellm -d litellm`), new rows should have `pl/<task>` requests served by the policy primary or fallback. fast-api: an AI Interview must-ask + score-turn call returns 200 and probes take ≤6 s; a real aptitude/communication score completes. corp-v2: `/v2/health` plus one screening. fdn: one normalization job is processed by the worker. pg-vector: one query-rewrite search.
8. **Audio/image/grounding:** the listener, reading audio, role transcription, image generation and web search are Gemini-only. Verify through the real endpoints once quota allows. They cannot fall back to OpenAI.
9. **Run the PROD sanity suite** (the only Jev run allowed on PROD): `~/jev-qa/bin/start.sh sanity --env prod`.
10. **Update this KB:** flip the header to "PROD live", record the PROD commits/images, and copy the live policy back to `litellm-central/prod/tasks-prod.json`.

### Changing a model on PROD afterwards (no restart)

Edit a copy of `~/pl-oks-cluster/api-ns/litellm/tasks.json`, then run `./prod_apply_policy.sh <copy>` (validate) and `./prod_apply_policy.sh <copy> --apply`. It backs up the live policy to `policy-backups/`, applies the ConfigMap and waits until the pod sees it (kubelet sync is about 1–2 min, not instant like DEV/UAT). Rollback: run it with the backup file.

### Rollback

- **Service:** `kubectl -n api set image deploy/<d> <container>=<previous image>`. Previous tags are in the Images row above; re-check with `kubectl rollout history`. Old code sends physical model names, which the gateway still serves.
- **Gateway:** re-apply the 10-07 hook (`litellm-fallback-hook-configmap.yaml.bak-<ts>` from step 2) and `kubectl -n api rollout undo deploy/litellm`. Only do this **after** services are rolled back: task names would return 400 with the old hook.

## DEV/UAT deployment and rollback (2026-10-09)

This initial migration redeployed services once. Python routing files were built into immutable overlays on the **exact currently running dependency image**, compiled before stopping the previous container, then deployed through the `auto_deploy.sh` central-release dispatch. Containers retained their environment, mounts, ports and networks; API, normalization workers/cron and vector search were checked. Corp and DEV admin used isolated source releases with existing dependencies. No dependency upgrades were introduced. Corp health endpoint is `/v2/health`; an initial wrong `/health` check triggered rollback and was corrected before successful deployment.

`CENTRAL_LLM_RELEASE=1 ~/auto_deploy.sh <service> Development|UAT` uses `/home/ubuntu/scripts/deploy-central-llm.py`. **This is a limited migration helper, not the general deployment default**: Python overlays include only production `.py` files changed in the target commit compared with its parent. Use only when the running image already contains all earlier required changes and dependencies are identical. It cannot deploy dependency changes or reconstruct a complete service from arbitrary history. Normal future service changes use the established complete build workflow.

Rollback images are tagged `central-llm-rollback/<container>:<UTC timestamp>`. Release artifacts under `~/releases/<repo>/<env>-<revision>-<timestamp>/` record original container inspection, private env file, overlay and deployed revision. The helper rolls back on startup-health failure. Corp uses a systemd `zz-central-llm.conf` pointing to an isolated release and restores the prior override on health failure. Initial gateway backups are in `~/central-llm/backups/` (DEV) and host-local release artifacts on UAT. Never commit env files, provider credentials, virtual keys or raw container inspection to the KB.

Single-instance DEV/UAT containers/services were restarted for the initial migration, so **zero downtime is not claimed**. Future policy changes do not restart them. PROD was not rolled out.

**Trap: corp-v2 on DEV and UAT is pinned to the migration snapshot.** `/etc/systemd/system/corporate-node-v2.service.d/zz-central-llm.conf` points `ExecStart` at `~/releases/corporate-node-v2/{DEV-efe4f051a043,UAT-859922694937}-20261009T07…/dist/index.js`. A normal deploy (pull + build in `~/api/corporate-node-v2` + restart) is therefore **silently ignored** — the service keeps running the snapshot. Removing the drop-in on its own is also wrong: the DEV checkout is at `7ff3c05` (2026-09-17), older than the snapshot, so DEV would roll back. Correct order for the next corp-v2 deploy on each host: check out and build the branch head in `~/api/corporate-node-v2` (which includes the central commits) → `sudo rm /etc/systemd/system/corporate-node-v2.service.d/zz-central-llm.conf && sudo systemctl daemon-reload && sudo systemctl restart corporate-node-v2` → `curl localhost:4001/v2/health`. PROD (K8s) is not affected.

## DEV/UAT verification and remaining provider limits

- Gateway policy tests and OpenAI conversion tests passed on both hosts. Five fastapi routing/client/attribution checks passed for each branch; normalization transport checks passed; corporate/admin TypeScript checks passed.
- Gateway checks exercised all 36 text policies normally and with forced Gemini/primary failure. The initial old GPT-5-mini authentication failure was fixed centrally and aptitude validation retested successfully on both hosts. Successful response headers identified Luna or Mini; this was not inferred from a configured list.
- Synthetic audio passed DEV's three audio tasks, normally and with a forced primary failure. UAT listener checks initially succeeded; later reading/transcription checks exhausted Google's daily quota across the audio chain. No audio was sent to OpenAI as a substitute.
- Actual fastapi suggest-parameters, must-ask question and score-turn endpoints returned 200 in each environment. After the final routing correction, general live question, phone brief and phone intent endpoints were rechecked.
- On **both** hosts, an isolated test policy switched from Luna to Mini and each actual model answered. LiteLLM container StartedAt did not change. Temporary smoke policy was removed; final manifest contains 41 tasks.
- **Provider blockers, still open:** UAT Google reports `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, **20 calls per model per day**, exhausted across the approved audio chain. Text calls continue via OpenAI. Real image-generation and GoogleSearch-grounding requests returned Google 429 on **DEV and UAT**. Those capability-specific tasks have no validated compatible OpenAI substitute. Existing UAT alternate Google credentials tested were also quota-limited or unauthenticated; no cross-environment key was copied. Enable funded Google billing/raise quota or provide a valid environment credential before claiming these tasks are operational end to end.
- This checks transport, routing and payload compatibility, not a new quality/accuracy benchmark. Previous scoring/listener evaluation remains relevant when choosing alternatives. The broad Jev UAT regression suite has not been run as part of these focused checks.

## Versioned operational files

Secret-free copies are in [litellm-central/](litellm-central/): hook, DEV/UAT policy manifests (`policies/tasks.json` = DEV, `policies/tasks-uat.json` = UAT), the PROD rollout kit in `prod/` (policy, deployment patch, apply/check/key scripts), unit checks, policy activation tool, route/hot-switch checks, gateway recreation script and limited migration helper. Runtime credentials and full gateway registration config remain only on their respective hosts. The host policy is live; the KB copies document this rollout and must be updated when policy changes.
