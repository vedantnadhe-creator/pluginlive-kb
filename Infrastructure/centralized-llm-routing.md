# Centralized LLM routing — live on DEV, UAT and PROD

Deployed to DEV and UAT **2026-10-09**; **PROD live 2026-10-09 ~18:41 UTC** (release `release-v1.41-hotfix-4`, Raj K). PROD gateway: ConfigMap `litellm-task-policy` (= `litellm-central/prod/tasks-prod.json`, 41 tasks) mounted as a directory at `/app/policies`, hook ConfigMap `litellm-fallback-hook` = `litellm-central/pl_openai_fallback.py`, mount mirrored into `~/pl-oks-cluster/api-ns/litellm/litellm.yaml`; `corporate-node-v2-prod` key gained the 10 `pl/corporate-*` tasks. Gateway backups: `~/backups/litellm-hotfix4-20261009T184033Z/` on the PROD builder. Checks: `prod_apply_policy.sh` → 41 valid / 7 models registered; `prod_check_routes.sh` → 36 text tasks OK on primary, 0 failures; unknown task 400; legacy model names 200.

**Migrated on PROD:** fast-api `be2b28b` (`pl-fast-api:2026-10-09-18-45-32-release-v1.41-hotfix-4`) and corporate-node-v2 + worker `ef2b53f` (`pl-corporate-api-v2:2026-10-09-18-47-57-release-v1.41-hotfix-4`). **Not migrated on PROD (deferred by Raj K):** pg-vector-api-service and form-data-normalization stay on `release-v1.38-hotfix-1` and still send physical model names (served unchanged); the runbook's form-data-normalization Secret was NOT created. Audio/image/grounding tasks are not yet exercised on PROD.

## Runtime contract

All migrated chat, audio, grounding and image calls send a stable `pl/<task>` name to the environment's LiteLLM gateway using a service virtual key. Services retain prompts, inputs, output validation and an overall request deadline. Gateway policy owns physical model names, provider credentials, reasoning/thinking settings, per-attempt timeouts, retries and fallback chains. SDK retries are disabled in migrated chat clients to avoid multiplying gateway attempts.

`~/litellm/pl_openai_fallback.py` reads `~/litellm/policies/tasks.json` at the start of **every task request**, replacing caller routing settings. It snapshots that request's permitted models and reasoning settings before trying a deployment. An edit affects the next request; an in-flight request keeps its original chain. Unknown tasks return 400; unreadable/invalid policy returns 503. Missing gateway configuration fails explicitly in migrated clients rather than using a provider key directly.

The LiteLLM callback handles Gemini/OpenAI payload differences on **each attempt**, including a fallback: strips Gemini thinking fields; maps OpenAI thinking off to `reasoning_effort: none`; uses `max_completion_tokens`; removes sampling settings incompatible with reasoning; reserves at least 4096 tokens where reasoning needs them; and keeps a strict JSON schema strict for OpenAI when every property is required (adding `additionalProperties: false`), relaxing only schemas that cannot be strict (see `ai-gateway.md`). Service output validation still applies. Gemini 3.8 uses low reasoning rather than the rejected disable setting. Gemini 2.5 Pro retains its native reasoning default.

**JSON output must be requested with a schema from the caller.** The gateway forwards a caller's JSON schema to the provider (fast-api: pass a Pydantic `response_schema` to `_gemini_json` / `_gemini_json_background_contents`; the shim sends it as `response_format: json_schema`). It does not inject one. A prompt-only "return JSON" is not enough on thinking models: `pl/reading-audio` (gemini-3.8-flash, low) answered in prose about 10% of the time (40% on hard clips), and `{"type": "json_object"}` did not fix that. On PROD every reading check failed with `Gemini response not JSON` from 10-09 (139 failures in 72h on 10-15). With a schema: 108/108 clips judged on the DEV eval (`~/reading-tune/model_eval.py`). Both reading calls (`Proctoring/reading_judge.ReadingJudgement`, `VerifyReadingResponse`) send a schema on DEV + UAT from 2026-10-15 (fast-api Development `9da1d6b`, UAT `89d7062`); PROD pending. **The caller also validates locally:** when a `response_schema` is given, `_gemini_json` runs `model_validate` on the parsed JSON and returns **502 `Gemini response off-schema`** on mismatch (missing field, wrong type, out-of-range value), because the gateway can loosen a schema and a partial object such as `{"verdict":"spontaneous"}` used to default `p_read` to 0 and clear the answer as human @ 1.0. `VerifyReadingResponse` is binary (`verdict: read|human`, `confidence` 0–1); `ReadingJudgement` bounds `p_read`/`p_prompted` to 0–1 and event times ≥ 0 (DEV `2a784c4`, UAT `136a553`, 2026-10-15; PROD pending). Other `_gemini_json` callers still rely on the prompt, though none fail today.

Audio policies permit only approved Gemini hops. Input audio on a text task is rejected, and any deployment outside the request's policy is rejected. Luna/Mini are text/image-input models and cannot substitute for an audio listener. GoogleSearch grounding and image-generation tasks retain compatible Gemini-only routes. Adding a different provider/model family needs payload and modality/tool compatibility validation; changing a name does not make capabilities interchangeable.

## Decision tasks — Gemini / OpenAI Decisions APIs through the gateway (DEV + UAT 2026-11-13, audio 2026-11-20; PROD pending)

The Decisions APIs (`generativelanguage.googleapis.com/v1beta/decisions`, model `gemini-decision-1`; `api.openai.com/v1/decisions`, model `gpt-6-luna`) return typed yes/no probabilities, not text, and LiteLLM has no route for them. They are served by a **LiteLLM custom provider**, `~/litellm/pl_decisions.py` (`custom_provider_map: pldecision → pl_decisions.decision_handler` in `config.yaml`, mounted read-only at `/app/pl_decisions.py` by `run.sh`). Services keep the normal contract: a `pl/<task>` chat request with the service virtual key.

- **Caller contract:** system message = the yes/no question; user message = evidence (text + `image_url` data URLs or https URLs, and since 2026-11-20 chat `input_audio` parts `{"data": <base64>, "format": webm|ogg|wav|mp3|mpeg|mp4|m4a|aac|flac}`). Answer content = `{"probability": <0..1>, "model": "<answering deployment>"}`. The response's top-level `model` can echo the task alias, so read the deployment from the content. Audio goes to Gemini Decisions as an `audio` block; **OpenAI Decisions takes no audio** (only `input_text`/`input_image`/`input_json`), so the provider refuses audio for it with a 400 and an audio decision task must not list it as a fallback. Other part types → 400. The policy hook (`pl_openai_fallback.py`) allows `input_audio` on `audio` **and** `decision` tasks.
- **Deployments** (DB-registered, keys copied from the env's `gemini-2.5-flash` / `gpt-6-luna` rows, cost $0.10/1M input, output free): `gemini-decision-1` → `pldecision/gemini-decision-1` with `extra_body.image_resolution: low` (≈450–570 tokens/frame vs ≈1,300 at default, same accuracy on our test); `openai-decision-gpt-6-luna` → `pldecision/openai-decision-gpt-6-luna`.
- **Policy:** modality `"decision"`. `validate_policy` enforces that a decision task uses only `DECISION_MODELS` and no other task uses them. Errors (timeout, provider 4xx/5xx incl. Google's safety block, refusal, missing probability) raise, so the router falls back.
- **Task:** `pl/proctor-phone` — `gemini-decision-1` → `openai-decision-gpt-6-luna`, 15 s per attempt, 0 retries. Caller: fastapi `Proctoring/ImageProctoring/phone_decision.py` (fastapi key, unrestricted). Verified on both hosts with fastapi's key: normal call served by Gemini; `mock_timeout` call served by OpenAI. Note: `mock_testing_fallbacks` does **not** force a fallback here; use `mock_timeout: true, timeout: 1`. See `Assessment/proctoring.md` for the accuracy study.
- **Task:** `pl/proctor-faces` (2026-11-20) — same chain and limits as `pl/proctor-phone`. Caller: fastapi `Proctoring/ImageProctoring/face_decision.py` (two questions per snapshot: face visible, 2+ real people). Verified on DEV and UAT with fastapi's key: normal call → Gemini, `mock_timeout` → OpenAI.
- **Task:** `pl/proctor-reading` (2026-11-20) — `gemini-decision-1` only (no fallback, OpenAI takes no audio), 30 s per attempt, 1 retry. Caller: fastapi `Proctoring/reading_decision.py`, second check on reading-judge "read" verdicts with the answer audio. Verified on DEV and UAT with fastapi's key. Backups 2026-11-20: UAT `~/central-llm/backups/proctor-decisions-20261120T072520Z` (files + policy), policy `tasks-20261120T072527Z.json`; DEV policy `tasks-20261120T060804Z.json` / `…T064439Z.json`. UAT recreated the same way as below (tests inside the container, `run.sh` minus the host test line).
- **UAT gateway recreation gotcha:** the UAT host has no `fastapi` Python package, so `run.sh`'s host-side `test_pl_openai_fallback.py` always fails there ("hook unit test failed; not recreating") — independent of this change. On 2026-11-13 the three test files were run **inside** the running `litellm` container (copied to `/tmp/gwt` with the policy), all passed, and the gateway was recreated with `run.sh` minus that one line. Backups: `~/central-llm/backups/proctor-phone-20261113T121921Z` (DEV), `…T123141Z` (UAT); policy backups `tasks-20261113T122240Z.json` (DEV), `tasks-20261113T123325Z.json` (UAT).
- **PROD:** not rolled out. Needs the hook + `pl_decisions.py` ConfigMaps, `custom_provider_map` in the PROD config, the two DB models with PROD keys, the policy entry, and a paid Gemini key (free-tier data is used by Google to improve products).

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
| aividya (eduspeak-india) | — (aividya DEV is hosted Supabase) | **Live on UAT** (chat simulations, Robo Teacher, Doubt Desk) | `pl/sim-persona` (gemini-3-flash-preview, thinking off → gpt-5.4-mini, 12 s), `pl/sim-judge` (gemini-3.8-flash low → gpt-6-luna, 60 s), `pl/sim-generate` (gemini-3.8-flash medium → gpt-6-luna low, 120 s), `pl/robo-teacher` (gemini-2.5-flash, thinking off → gemini-3-flash-preview → gpt-5.4-mini, 20 s; primary changed 2026-11-12 to match Banking Robo Play), `pl/robo-quiz` (gemini-3.8-flash medium → gpt-6-luna low, 90 s), `pl/doubt-answer` (gemini-3-flash-preview, thinking off → gpt-5.4-mini, 30 s; added 2026-11-12, caller `doubt-desk` edge function), `pl/robo-stt` (gemini-2.5-flash, thinking off → gemini-3.8-flash low, 20 s, **audio**; added 2026-11-12, caller `robo-speech`), `pl/report-remarks` (gemini-3-flash-preview, thinking off → gpt-5.4-mini, 35 s; added 2026-11-13, caller `school-ai` draft_remarks), `pl/homework-mark` (gemini-2.5-flash, thinking off → gpt-5.4-mini, 25 s, text task with image input; added 2026-11-13, caller `school-ai` suggest_homework_mark), `pl/school-curriculum-extract` (gemini-2.5-flash, thinking off → gpt-6-luna, 45 s, PDF file parts; added 2026-11-16, caller `school-curriculum-agent`), `pl/school-curriculum-verify` (gpt-5.4-mini → gemini-2.5-flash, 40 s; independent check of the extract; added 2026-11-16); all 0 retries. **UAT** key alias `aividya-app` (`~/litellm/aividya_app_vkey.txt` on the UAT host), restricted to these eleven tasks (school-curriculum tasks granted 2026-11-16, policy backup `policy-backups/tasks-20261116T183537Z.json`); the two 2026-11-13 tasks verified with a normal call and a forced fallback (`mock_timeout` → gpt-5.4-mini), policy backup `policy-backups/tasks-20261113T180505Z.json`. Each verified with a normal call and a forced fallback (`mock_timeout` → OpenAI). Latest policy backup: `policy-backups/tasks-20261112T173809Z.json`. `tasks-uat.json` refreshed from the live UAT policy 2026-11-12 (63 tasks). Note: the legacy `ai-doubt-bot` function calls OpenAI directly and has no frontend caller; do not reuse it. |
| banking-app (bankingjobreadiness edge functions) | — (no DEV) | UAT `02abb762` (2026-11-04) / PROD `b7eefe24` (2026-11-02) | `pl/banking-video-check` (UAT, gemini-2.5-flash → gemini-3.8-flash, 120 s, modality audio to keep the chain Gemini-only; PROD pending) · `pl/sim-persona-turn` (gpt-5.4-mini → gpt-6-luna, reasoning none, 12 s, 0 retries on UAT and PROD from 2026-11-22) serves the Robo persona's spoken reply via the `simulation-turn` LLM Settings row (inherits `simulation` where unconfigured; Gemini direct `gemini-2.5-flash` as the provider-level fallback row) — measured ~1.2 s on both gateways vs ~5 s p50 before, and a forced primary failure is answered by gemini-2.5-flash; `pl/banking-topic-content` (gemini-3-flash-preview low → gemini-3.8-flash medium, 60 s) used by `ai-content`; `pl/banking-curriculum` (gemini-2.5-flash, reasoning off → gpt-6-luna, 120 s, 0 retries) used by `generate-trainer-curriculum` via `_shared/curriculum-generation-gateway.ts`; **`pl/college-assignment-writing`** (gemini-3.8-flash low → gpt-6-luna, 45 s, 0 retries) is registered on UAT and PROD for the institute-only assignment AI-writing signal. **`pl/college-curriculum`** (gemini-2.5-flash reasoning disabled → gpt-6-luna, 120 s, 0 retries; PDF file parts on the primary) is registered on UAT and PROD (2026-11-16) for the college curriculum agent and granted to `banking-app` and `banking-app-prod`; normal and forced-fallback calls verified on both. **UAT** key alias `banking-app` (`~/litellm/banking_app_vkey.txt` on the UAT host), model-restricted: gemini-2.5-flash, gemini-2.5-flash-lite, gemini-3-flash-preview, `pl/banking-curriculum`, `pl/banking-topic-content`, `pl/sim-persona-turn`, `pl/banking-video-check`, `pl/college-assignment-writing`; normal and `mock_timeout` forced-fallback calls returned 200 on 2026-11-14. **PROD** key alias `banking-app-prod` (created 2026-11-02; `~/pl-oks-cluster/api-ns/litellm/banking_app_prod_vkey.txt` on the PROD builder), model-restricted to the existing six entries plus `pl/college-assignment-writing`; normal and forced-fallback calls returned 200 on 2026-11-14. **Banking PROD used the UAT gateway until 2026-11-02** (`ai-content`, `bulk-export-worker`, `simulation` rows all pointed at `uat.pluginlive.com/ai-gateway`); all four litellm rows now point at `https://ai-gateway.prod.pluginlive.com/ai-gateway/v1` with the PROD key — the public ingress is reachable from the banking VM (200 in ~80 ms). `bulk-export-worker` still names physical `gemini-2.5-flash`; UAT and PROD `simulation` now name `pl/banking-simulation` (2026-11-22 repairs below). |
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

**2026-10-16 (release-v1.42 prep, Raj K):** PROD policy 41 → **44 tasks**: added the AI_Interview_v2 tasks `pl/interview-skeleton` (120 s), `pl/interview-slot` (120 s) and `pl/interview-v2-score` (60 s), each gemini-3.8-flash (low) → gpt-6-luna, copied from UAT. Applied with `prod_apply_policy.sh` (backup `policy-backups/tasks-20261016T151603Z.json`). Verified from the fast-api pod with its own key (unrestricted, no key change): normal calls served by gemini-3.8-flash, `mock_timeout` calls by gpt-6-luna, all 200.

**2026-11-19 — Roles v2 corp-node on PROD (Kushal's go):** the release-v1.43 corporate-node image calls `pl/corp-*` tasks, but PROD had neither the tasks nor gateway env, so JD generation, JD parse and the apply link's CV parse/autofill all failed ("AI gateway is not configured"). Fixed without a code change:
- Policy 46 → **52 tasks**: added `pl/corp-apply-autofill`, `-assessment-paper`, `-interview-guidance`, `-resume-contact`, `-stage-prefill`, `-workflow-design`, copied from UAT (gemini-3.8-flash low → gpt-6-luna; 60 s, paper 120 s, workflow 90 s). Backup `policy-backups/tasks-20261119T051148Z.json`; copy in `litellm-central/prod/tasks-prod.json`.
- New key alias **`corporate-node-prod`**, restricted to those 6 + `pl/corporate-jd-generation` + `pl/corporate-jd-parse`.
- ConfigMap `corp-api-config` (`/app/.env` of deploy `corporate-node`) gained `LITELLM_PROXY_URL=http://litellm/v1`, `LITELLM_VIRTUAL_KEY`, `OCI_*` (private bucket `pl-prod-assessment`, same as student-node/corp-v2) and `CORPORATE_V2_APPLY_BASE_URL=https://corporate.pluginlive.com/v2/apply`; also appended to the builder's `~/repositories/envs/api/corporate-node.env`. Backups in `~/pl-oks-cluster/api-ns/corp-config-backups/*-20261119T051326Z`. Deploy restarted.
- Verified in PROD: the app's `chatJson` for jd-generation / resume-contact / apply-autofill OK; all 8 tasks OK normally and fall back to gpt-6-luna under `mock_timeout`; OCI bucket reachable from the pod.
- **Still missing on PROD corp-node:** `NORMALIZATION_API_URL` / `NORMALIZATION_API_KEY` (Roles v2 bulk candidate upload returns 503). The ConfigMap has drifted from the builder env file (AWS_*, CLOUDFRONT_URL, ELASTIC_SERVICE_API_KEY, LOGIN_TOKEN_EXPIRES_IN, PIL_WEBSITE_URL, PORT differ; AI_MATCH_*/REDIS_URL only in the ConfigMap): the ConfigMap is the live truth — never regenerate it from the file.

**2026-11-19 (later) — Roles v2 evaluation engine ON for PROD corp-node:** `corp-api-config` gained `ROLES_V2_ENGINE_ENABLED=true` and `ROLES_V2_INTERNAL_TOKEN` (= `std-api-config` `CORPORATE_ATS_TOKEN`). Without the flag, Resume Screening never ran. **Do NOT set `QUEUE_ENV` on PROD corp-node:** it renames the AI match queue `cv-jd-match-default` (which `corporate-node-ai-match-worker` and other producers use) to `cv-jd-match-<env>`. It was set for ~10 min on 11-19 and stranded 3 jobs on `cv-jd-match-prod`; they were re-queued with `triggerAiMatchForCandidates` and removed. With it unset, the engine queue is `corp-roles-eval-dev` on PROD (harmless name, PROD Redis). Still open: student-node `CORPORATE_ATS_URL=http://corporate-node-v2` (should point at `corporate-node` for assessment-scored hooks; needs a student-node restart), `APPLIED_SNAPSHOT_READS` (needs the PROD backfill), `NORMALIZATION_*` (needs a form-data-normalization release with `corporate_bulk`).

### Changing a model on PROD afterwards (no restart)

Edit a copy of `~/pl-oks-cluster/api-ns/litellm/tasks.json`, then run `./prod_apply_policy.sh <copy>` (validate) and `./prod_apply_policy.sh <copy> --apply`. It backs up the live policy to `policy-backups/`, applies the ConfigMap and waits until the pod sees it (kubelet sync is about 1–2 min, not instant like DEV/UAT). Rollback: run it with the backup file.

### Rollback

- **Service:** `kubectl -n api set image deploy/<d> <container>=<previous image>`. Previous tags are in the Images row above; re-check with `kubectl rollout history`. Old code sends physical model names, which the gateway still serves.
- **Gateway:** re-apply the 10-07 hook (`litellm-fallback-hook-configmap.yaml.bak-<ts>` from step 2) and `kubectl -n api rollout undo deploy/litellm`. Only do this **after** services are rolled back: task names would return 400 with the old hook.

## DEV/UAT deployment and rollback (2026-10-09)

This initial migration redeployed services once. Python routing files were built into immutable overlays on the **exact currently running dependency image**, compiled before stopping the previous container, then deployed through the `auto_deploy.sh` central-release dispatch. Containers retained their environment, mounts, ports and networks; API, normalization workers/cron and vector search were checked. Corp and DEV admin used isolated source releases with existing dependencies. No dependency upgrades were introduced. Corp health endpoint is `/v2/health`; an initial wrong `/health` check triggered rollback and was corrected before successful deployment.

`CENTRAL_LLM_RELEASE=1 ~/auto_deploy.sh <service> Development|UAT` uses `/home/ubuntu/scripts/deploy-central-llm.py`. **This is a limited migration helper, not the general deployment default**: Python overlays include the production `.py` files (added/modified/renamed) changed since the revision the running image was built from (its `pluginlive.central-llm.revision` label, or explicit `CENTRAL_LLM_BASE`). An unknown base or a base that is not an ancestor of the target fails explicitly. **Before 2026-10-12 it always used only the target commit's files**, so a push of several commits shipped the last commit only: a UAT fastapi deploy then failed its health check on a missing new module and rolled itself back. For fast-api it also imports `main` inside the new image before swapping containers. On UAT, the 2026-10-30 attempt-integrity deployment extended copying to `Proctoring/models/` assets (Silero `.jit` and license); only Python files are compiled. Verify model loading separately because app import does not load it. Labels and checkouts can lag after overlays, so confirm actual image file hashes. Use only when dependencies are identical. It cannot deploy dependency changes or reconstruct a complete service from arbitrary history. Normal future service changes use the established complete build workflow.

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

**2026-11-04 (UAT):** policy 47 → 53 tasks: added the six `pl/corp-*` Roles tasks. New UAT service key alias `corporate-node` (`~/litellm/corporate_node_vkey.txt`), limited to those plus `pl/corporate-jd-generation`. Normal call and forced fallback (served `gpt-6-luna`) verified.

### Banking PROD simulation recovery — 2026-11-22

Candidate end-to-end testing found `pl/sim-persona-turn` absent from the live PROD policy despite its earlier
registration. The legacy direct-provider chain could not recover: Gemini reported depleted prepayment credits.
The repair restores task routing without changing provider keys, billing, unrelated tasks or the held video checker.

| PROD task | Primary → fallback | Per-attempt timeout | Reasoning | Caller |
|---|---|---|---|---|
| `pl/sim-persona-turn` | `gpt-5.4-mini` → `gpt-6-luna` | 12 s, zero retries | none on both | `simulation-turn` LLM config |
| `pl/banking-simulation` | `gpt-6-luna` → `gpt-5.4-mini` | 20 s, zero retries | none on both | `simulation` LLM config, including debrief |

Both are text tasks granted to `banking-app-prod`. Normal probes returned 200 from the primary (1.3 s and 1.2 s);
`mock_timeout` probes returned 200 from the fallback (1.1 s and 0.9 s). The actual candidate's persona reply and scored
debrief passed through the banking application. The gateway hook still owns model policy and fallback conversion;
no application-level provider fallback was added. The same two-task policy was subsequently applied to UAT below.

Applied using the PROD policy validator against registered models, then hot-reloaded via the ConfigMap. Builder
source is `~/pl-oks-cluster/api-ns/litellm/tasks.json` on `140.245.25.134`, now 59 tasks; candidate copy
`tasks-prod-journeys-20261122.json`. Original live policy backup: `policy-backups/tasks-20261122T115305Z.json`;
intermediate backups `tasks-20261122T115453Z.json` and `tasks-20261122T115710Z.json`. Always derive subsequent policy
edits from the live ConfigMap/current `tasks.json`: the legacy `tasks-prod.json` is an obsolete 41-task snapshot.
Banking config baseline (no secrets): `/data/backups/simulation-route-before-journeys-20261122.txt` on `130.210.28.66`.

### Banking UAT simulation backport — 2026-11-22

At the user's request, UAT now uses the two banking task policies shown in the PROD table above, through its own
`banking-app` virtual key and `https://uat.pluginlive.com/ai-gateway/v1`. The live policy went from 76 to 77 tasks:
updated `pl/sim-persona-turn` and added `pl/banking-simulation`; all other task entries and existing key grants were
preserved. Granted the new task and checked that both banking config rows use the expected UAT service key.

Normal and `mock_timeout` probes all returned 200: persona primary gpt-5.4-mini (1.2 s), fallback gpt-6-luna (0.9 s);
non-turn primary gpt-6-luna (0.8 s), fallback gpt-5.4-mini (1.1 s). A candidate completed a real topic simulation with
an AI reply and scored debrief through the application. No gateway restart, credential replacement or billing change.

Applied using `~/litellm/apply_policy.py`; backup `policy-backups/tasks-20261122T121151Z.json`; candidate
`tasks-banking-journeys-20261122.json`. The versioned `litellm-central/policies/tasks-uat.json` now matches the complete
live 77-task policy. Only the banking `simulation` row's model changed from `gemini-2.5-flash` to
`pl/banking-simulation`; baseline `~/banking-sb/snapshots/uat-journeys-config-20261122/simulation-before.txt`.
