# AI Gateway (LiteLLM)

Self-hosted **LiteLLM** proxy that fronts all LLM calls for the platform: one OpenAI-compatible endpoint with a dashboard for **provider-key management, cost/usage tracking, fallbacks, retries, and per-service virtual keys**. One gateway is deployed **per environment** (isolated; no shared cross-env instance).

## Endpoints

| Env | Dashboard | API base | Internal (for services) |
|---|---|---|---|
| DEV | `https://dev.pluginlive.com/ai-gateway` | `…/ai-gateway/v1` | `http://172.17.0.1:4000/v1` |
| UAT | `https://uat.pluginlive.com/ai-gateway` | `…/ai-gateway/v1` | `http://172.17.0.1:4000/v1` |
| PROD | `https://ai-gateway.prod.pluginlive.com/ai-gateway/ui/` | `…/ai-gateway/v1` | `http://litellm/v1` (in-cluster) |

- Dashboard login is the LiteLLM UI (username `pluginlive`; password + master key in `~/litellm/secrets.env` on each box).
- Runtime **DEV/UAT**: `litellm` container (`ghcr.io/berriai/litellm:main-stable`, port 4000, published on `127.0.0.1` for nginx and `172.17.0.1` for sibling containers) + `litellm-db` Postgres. Config `~/litellm/config.yaml`; served under `SERVER_ROOT_PATH=/ai-gateway`; nginx route in `static-website.conf`.
- Runtime **PROD**: K8s namespace `api` — `litellm` + `litellm-postgres` deployments, manifests in `~/pl-oks-cluster/api-ns/litellm/`. Apps connect **in-cluster** at `http://litellm/v1`; the public ingress exists only for the UI. Only `GEMINI_API_KEY` is configured — router fallbacks map `gpt-*` / `llama-*` to `gemini-2.5-flash`. Query gateway spend directly with `kubectl -n api exec -i deploy/litellm-postgres -- psql -U litellm -d litellm`.

## What routes through it

- **LLM / chat calls** — Gemini, OpenAI, Groq. Routing is by **model name**; the calling service authenticates with a **virtual key** (per service: `fastapi-ai-engine`, `form-data-normalization`, …), and the real provider keys live on the gateway.
- **Image generation** — Google **Imagen** (`imagen-4.0-fast-generate-001`, `imagen-4.0-generate-001`, registered `gemini/imagen-4.0-*`). Called via the OpenAI-schema `/v1/images/generations` endpoint; tracked in `LiteLLM_SpendLogs` as `aimage_generation` (~$0.02/image). Used by Assessment communication/hinglish "Question Based Response" question generation.
- **Excluded — embeddings.** `pg-vector-api-service` / Chroma embeddings (`text-embedding-004`, `gemini-embedding-001`, `text-embedding-3-small`) stay native — routing them would change vector dimensions and corrupt existing vector stores.
- **Excluded — STT/TTS** (Deepgram, ElevenLabs, Azure Speech): not routable through this gateway.

Services opt in via env vars `LITELLM_PROXY_URL` + `LITELLM_VIRTUAL_KEY` (default-off — unset = native provider calls, unchanged behaviour).

### Currently routed
- `fastapi-ai-engine` (Assessment: communication / hinglish / aptitude / role / AI-interview / resume-match LLM calls, **plus Imagen image generation** for communication/hinglish Question-Based-Response questions) — DEV + UAT. Image gen routes through `utils/portkey_gateway.build_image_client()` → `QuestionGeneration/Communication/image_generation_google.py` (gateway-first, native `google.genai` fallback only when `LITELLM_*` env unset).
- `form-data-normalization` (candidate-data normalization LLM disambiguation) — DEV + UAT. NOTE: only the main `datanormalization` API container is redeployed by `auto_deploy`; the `datanormalization-worker` / `-cron` siblings run a separate image and are not yet on the gateway.
- `pg-vector-api-service` (entity-normalizer LLM disambiguation/pincode) — code ready, gated; embeddings excluded.
- `resume-parser` (CV parsing — the `parseResume` / `parseResumeAndUpload` Gemini calls behind `form-data-normalization`'s CV ingest) — UAT (container `resumeparser`, port 5011). Routed via a tiny google-genai-compatible shim (`USING API/gateway_client.py`) using `requests`, not the OpenAI SDK. Gateway env passed at `docker run` (`-e LITELLM_PROXY_URL=http://172.17.0.1:4000/v1 -e LITELLM_VIRTUAL_KEY=…`), not baked into the image. Manual build/run (not in `auto_deploy`): `cd ~/api/Resume_parser/"USING API" && docker build -t resumeparser:api . && docker stop/rm + docker run`.

**Why this was needed (gotcha):** the consolidated Gemini key is in the `AQ.Ab8RN6K…` format. LiteLLM uses it correctly, but the raw `google.genai` SDK (`genai.Client(api_key="AQ.…")`) mis-sends it as an OAuth token → `401 UNAUTHENTICATED / ACCESS_TOKEN_TYPE_UNSUPPORTED`, which surfaced in the normalization UI as **"CV Parse Error: HTTP 500 … google.genai.errors.ClientError: 401"**. Routing the SDK calls through the gateway fixes it without needing a per-service AI-Studio (`AIza…`) key. Same root cause hit **Imagen image generation**: `image_generation_google.py` called `genai.Client(api_key=GEMINI_API_KEY).models.generate_images(...)` directly with the `AQ.` key → `401 UNAUTHENTICATED` on every attempt → the whole communication/hinglish generation aborted with *"Assessment cannot be generated right now. Image generation failed…"*. Fixed by registering `gemini/imagen-4.0-*` on the gateway and routing image gen through `/v1/images/generations` (2026-07-02, DEV + UAT).

## Managing keys & models

- **Rotate / change a provider API key**, add models, mint virtual keys: LiteLLM dashboard → Models / Keys (live, no redeploy) for DB-managed models. Models defined in `config.yaml` are read-only in the UI; change those by editing `config.yaml` and `docker restart litellm`.
- **Gotcha:** the wildcard `"*"` model entry mis-routes bare `gemini-*` names to **Vertex AI** ("default credentials not found"). Every Gemini model an app uses must be registered explicitly with the `gemini/` prefix in `config.yaml`.

### Gotcha: a bad key on one model is SILENT — router fallbacks hide it

Each DB-managed model row stores its **own** API key, and the keys can drift apart between model rows and between environments. When a model's key is invalid, the call does **not** surface an error to the app — LiteLLM's router fallback quietly serves the request from a different model, so the caller gets a normal 200 and never learns it was downgraded.

**Live example (UAT, found 2026-08-12).** `gemini-3-flash-preview` and `gemini-2.5-flash` were registered with *different* keys. The `gemini-3-flash-preview` key was invalid, so every request for it failed auth and fell back:

```
x-litellm-model-group:      gemini-2.5-flash          # asked for gemini-3-flash-preview
x-litellm-attempted-fallbacks: 1
```

DEV was healthy at the same moment (`model-group: gemini-3-flash-preview`, `attempted-fallbacks: 0`), so this is **per-environment** and will not show up in DEV testing.

**How to detect it.** A fallback is only visible in the response headers, or by forcing the real error:

```bash
# Does the model actually serve, or is it being substituted?
curl -sD- -o/dev/null -X POST http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer $VKEY" -H 'Content-Type: application/json' \
  -d '{"model":"<model>","messages":[{"role":"user","content":"hi"}],"max_tokens":5}' \
  | grep -iE 'model-group|attempted-fallbacks'

# Surface the underlying provider error instead of the fallback
... -d '{"model":"<model>", ..., "num_retries":0, "fallbacks":[]}'
```

Health-check every model group after any key rotation — `/v1/models` only proves a model is *registered*, not that its key works, and the ledger's `model` column records what actually answered (the fallback), not what was requested.

Note the stored `api_key` in `LiteLLM_ProxyModelTable` is **encrypted**, and `/model/info` masks it, so keys cannot be compared by reading the DB — compare behaviour, not values.

## Observability

PostHog `$ai_generation` analytics continue in parallel (the gateway integration preserves the PostHog-wrapped clients). The LiteLLM dashboard adds per-key cost/usage and request logs.

## Cost tracking — the `ai_usage` ledger

**The LiteLLM dashboard alone cannot answer "what did this assessment cost".** Three reasons:

1. Spend is keyed by **virtual key = service**, so it reports that `fastapi-ai-engine` spent $X, never that it was AI Interview.
2. `LiteLLM_SpendLogs` retention is short, so historical averages are not retrievable from it.
3. **STT/TTS never traverse the gateway** — Deepgram, ElevenLabs, Sarvam, Azure and Google TTS spend is invisible to it.

Point 3 dominates. On a measured AI Interview turn, speech cost **$0.00631** against **$0.000052** of LLM — a gateway-only report misses roughly **99%** of the real spend.

So `fastapi-ai-engine` writes its own durable ledger, a **superset** of LiteLLM spend.

- **Table:** `ai_usage.ai_usage_ledger`, one row per paid AI call, plus views `ai_usage.v_module_daily_cost` (cost per IST day / module / modality / provider) and `ai_usage.v_module_attempt_cost` (attempts measured, avg / median / max cost per attempt, per module).
- **Live on:** DEV, UAT (`uat_pluginlive`) and PROD (`prod_pluginlive` on the live PG16 host `10.0.6.104`) since **2026-08-12**. Schema is in the `DB-Scripts` repo under `AI Usage Cost Tracking`.
- **Module attribution is derived from the router prefix** (`/ai-interview` → `AI_Interview`), and the names deliberately match `assessment.assessment_type.type_name`, so the ledger joins straight to assessment data. One middleware covers every router — no per-router edits.
- **LLM cost is never computed locally.** It is read from LiteLLM's `x-litellm-response-cost` response header (`cost_source='gateway'`, exact). STT/TTS rows are priced from a published rate card (`cost_source='rate_card'`, list price × measured quantity).
- **Default-OFF.** Tracking writes only when `AI_USAGE_DATABASE_URL` is set (plus optional `AI_USAGE_ENV`). It never blocks a request and never raises into one — rows go through a bounded queue flushed by a background thread. Set on UAT in `.env.uat`; on PROD in the `fast-api-config` ConfigMap.
- Docs live with the code at `fastapi-ai-engine/docs/ai-usage-tracking.md`.
- **Reading the `model` column:** it records the model that *answered*, taken from the response, not the one the code asked for. If a router fallback fired (see the silent-fallback gotcha above), the ledger shows the substitute. That makes the ledger a useful way to spot fallbacks — a module whose rows show an unexpected model is being silently downgraded.

## Assessment scoring model (2026-08-12)

`gemini-2.5-pro` was retired from assessment scoring: Aptitude, Communication (incl. the deepgram/video/score paths), Hinglish, Role_Based and AI-Interview `score-final` now all request the **`gemini-3-flash-preview`** model group (23 call sites, commit `8aae021`, on UAT via `555f8f4`). The exact group name matters — plain `gemini-3-flash` is not registered and 404s.

**Caveat on UAT:** because of the invalid-key fallback documented above, requests for `gemini-3-flash-preview` on UAT are currently served by `gemini-2.5-flash`. Assessment scoring there is therefore running on 2.5-flash, a weaker model than the 2.5-pro it replaced, until that model row's key is fixed on the UAT gateway. Question generation was already affected before this change, since it already used the same group.

### Joining a cost back to a candidate / corporate / institute

```
ai_usage_ledger.attempt_id (text)
  = assessment.assessment_assigned_students.assessment_assigned_id (uuid)
      -> assessment_corporate_map -> corporate.corporates
      -> assessment_institute_map -> institute.institutes
      -> primary_email -> student.student_personal_profile -> student.students
```

For AI Interview, `attempt_id` may be the interview session id instead — resolve via `assessment.ai_interview_sessions.id -> assessment_assigned_id`. `attempt_id` is text, so always guard the cast with `attempt_id ~ '^[0-9a-fA-F-]{36}$'`.

### Known gaps (state these when reporting a total)

- **No ledger history before 2026-08-12.** For earlier LLM-only spend use `LiteLLM_SpendLogs`, and say that speech is excluded from that number.
- **Not every row carries an `attempt_id`.** Communication and Hinglish scoring endpoints already receive `assessment_assigned_id`; AI Interview and Role_Based do not yet (the fix is frontend-side — append `?assessment_assigned_id=<id>`). Those rows still count toward module totals but cannot be attributed to a candidate or drive.
- **`resume-parser` and `jdparser` bypass both sources** — they call Gemini directly with a raw key, so their cost appears only in Google Cloud billing.
- `x-litellm-call-id` is **not** `LiteLLM_SpendLogs.request_id`; use it for tracing, not as a join key.

### Querying it

On PROD, use the read-only helper `/home/ubuntu/scripts/prod-aicost-query.sh` on the builder box (140.245.25.134). It targets the **live PG16 host `10.0.6.104`** and wraps every query in `BEGIN READ ONLY … ROLLBACK`. **Do not use `prod-readonly-query.sh`** for this — it still points at `10.0.2.105`, the frozen pre-cutover PG14 box, which has no `ai_usage` schema.

The **AI Cost Analyst** agent in the OliBot dashboard's Agents tab wraps all of the above conversationally: per-candidate, per-corporate-drive, per-institute and per-module spend, cost per completed candidate, and cost-efficiency comparisons. It is PROD-scoped and read-only (`whatsapp-engineer/agents/ai-cost-analyst/`).
