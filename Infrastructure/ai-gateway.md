# AI Gateway (LiteLLM)

Self-hosted **LiteLLM** proxy that fronts all LLM calls for the platform: one OpenAI-compatible endpoint with a dashboard for **provider-key management, cost/usage tracking, fallbacks, retries, and per-service virtual keys**. One gateway is deployed **per environment** (isolated; no shared cross-env instance).

## Endpoints

| Env | Dashboard | API base | Internal (for services) |
|---|---|---|---|
| DEV | `https://dev.pluginlive.com/ai-gateway` | `…/ai-gateway/v1` | `http://172.17.0.1:4000/v1` |
| UAT | `https://uat.pluginlive.com/ai-gateway` | `…/ai-gateway/v1` | `http://172.17.0.1:4000/v1` |
| PROD | not deployed | — | — |

- Dashboard login is the LiteLLM UI (username `pluginlive`; password + master key in `~/litellm/secrets.env` on each box).
- Runtime: `litellm` container (`ghcr.io/berriai/litellm:main-stable`, port 4000, published on `127.0.0.1` for nginx and `172.17.0.1` for sibling containers) + `litellm-db` Postgres. Config `~/litellm/config.yaml`; served under `SERVER_ROOT_PATH=/ai-gateway`; nginx route in `static-website.conf`.

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

## Observability

PostHog `$ai_generation` analytics continue in parallel (the gateway integration preserves the PostHog-wrapped clients). The LiteLLM dashboard adds per-key cost/usage and request logs.
