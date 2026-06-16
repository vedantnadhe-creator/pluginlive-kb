---
type: reference
tags: [service, api, python, normalization, ingestion, ai]
---

# Form Data Normalization Service

**Repo:** `/home/ubuntu/api/form-data-normalization`
**Stack:** Python 3.11 · FastAPI · PostgreSQL · OpenAI (GPT-4o-mini) · Gemini 3.0 Flash
**Port:** 5013 (production) / 8001 (development)
**Docker Image:** `form-data-normalization`

---

## What It Does

Ingests candidate/student data from Google Drive spreadsheets and API payloads, normalizes free-text fields using LLM, matches them against master data (institutes, degrees, cities, roles) via fuzzy matching, and enriches profiles with assessment scores and CV parsing.

**Flow:**
```
Google Drive / API → Ingest raw data → LLM normalization → Entity matching → Normalized candidate record
```

---

## Real-Time Ingest via Google Drive Webhook (UAT + PROD — LIVE)

As of **2026-06-11 (UAT)** and **2026-06-12 (PROD)**, both environments ingest in **real time** through a Google Drive push-notification (`changes.watch`) webhook — no waiting for the daily cron. End-to-end latency is seconds (ingest) + a few seconds (AI normalization).

**Flow:** file added/edited in the watched Drive folder → Google POSTs (empty ping) to the webhook → `DriveChangeService.process_and_log_changes()` lists changes since the saved `drive_state.start_page_token` → for each changed spreadsheet calls `ingest_file()` (rows → `candidates_raw_data`, status `pending`) → `worker` normalizes. The POST handler (`api/drive_webhook.py`) returns `200` immediately and does the work in a background task; an `asyncio.Lock` prevents concurrent double-processing.

**Service account (changed):** Both UAT and PROD use the **`pluginalex`** SA `pluginliveservice@pluginalex.iam.gserviceaccount.com` (the same `auth_creds.json` that student/corporate/institute-node use for Google Sheet export), **not** the old `data-eng-dev-486917` SA. The Drive folders are shared with this SA. On **PROD** the key is mounted from k8s Secret `data-normalization-sa` at `/app/secrets/auth_creds.json` (NOT baked in the image); on **UAT** it sits in the repo as `./auth_creds.json` and is baked into `datanormalization:api`.

**Webhook URLs (no more ngrok anywhere):**
- UAT: `https://data-normalization.uat.pluginlive.com/webhooks/google-drive` (nginx `data-normalization.conf` → `localhost:5013`, Let's Encrypt).
- PROD: `https://data-normalization.prod.pluginlive.com/webhooks/google-drive` (k8s Ingress `data-normalization-prod-ingress` in ns `api` → Service `form-data-normalization:80` → pod `:5013`, TLS secret `data-normalization-tls`, ingress IP `152.67.29.77`).

ngrok is **local-dev only**; its `*.ngrok-free.dev` domains are pre-verified with Google, custom domains are not (see below).

**⚠️ Folder-scope filter (critical, since UAT+PROD share the SA):** Google Drive's change feed is **per-service-account, global**, not per-folder. Without filtering, the UAT webhook ingests files modified in the PROD folder and vice versa — this actually happened during the rollout (UAT picked up 1010 PROD rows; PROD picked up 3 UAT rows). The fix is in `services/drive_change_service.py`: every change is checked against `settings.GOOGLE_DRIVE_FOLDER_ID` (using `file.parents` from the Drive API) and dropped if it's not in this env's folder. **Daily ingest (`ingest_parallel`) was already folder-scoped; only the webhook path leaked.** If you ever share an SA across environments again, this filter is what keeps them separate. Code lives on `Development` (`bb5c848`), `UAT` (`68f5f59`), `release-v1.33-hotfix-1` (`f61f581`).

**Drive folders (separate per env):**
- UAT: `1OJ2sGcz85VmGk2fHkg3XALW5nX5M06Ug`
- PROD: `1vnv0vCwqPnAU_I3afaW7zRn3ge8QLNtG`

**Domain verification (one-time prerequisite):** Google rejects `changes.watch` unless the webhook's domain is verified **in the project that owns the SA** — here `pluginalex`. `pluginlive.com` is verified in Search Console + added under **Cloud Console → Domain verification (project `pluginalex`)**, which covers all subdomains (UAT + PROD). Change the SA → re-verify under the new SA's project.

**Channel lifecycle:** watch channels expire after **7 days**. The `cron` process auto-renews (`ensure_webhook_active` hourly, `weekly_webhook_renewal` Sun 1 AM). Channel/token state lives in the single `drive_state` row (`id='drive'`: `start_page_token` + `webhook_data` JSONB). When switching SA, reset `start_page_token` to NULL so the new SA seeds a fresh change-feed.

**Incremental dedup (important):** ingest is per-sheet incremental — `ingest_spreadsheet_file` skips a sheet when `last_row_number <= already_processed` (`ingested_sheets.last_processed_row`, keyed on `source_sheet_id`=Drive file_id + sheet name). Re-saving a sheet with the same rows inserts nothing; **only rows beyond the last processed row ingest.** Not a bug — prevents duplicates. To test, add a *new* row.

### UAT runtime topology — 3 sibling containers

The Docker image's CMD only runs the API. The worker and scheduler run as **separate containers from the same `datanormalization:api` image** (overriding CMD), all `--restart always --env-file .env`:

| Container | Command | Role |
|-----------|---------|------|
| `datanormalization` | (image CMD) `uvicorn api.main:app … :5013` | API + **webhook receiver** (`-p 5013:5013`) |
| `datanormalization-worker` | `python main.py worker` | AI normalization loop |
| `datanormalization-cron` | `python main.py cron` | APScheduler (renewal, daily ingest, status) |

⚠️ **`deploy.sh` only builds/runs `datanormalization`** — it does *not* recreate the `-worker`/`-cron` siblings, and rebuilding the image does not restart them. After any redeploy, recreate the two siblings manually (or add them to `deploy.sh`). Code + SA key are **baked into the image** (`COPY . /app`), so config/key changes require an image rebuild, not just an `.env` edit.

### PROD runtime topology — 3 Deployments in ns `api`

| Deployment | Args | Role |
|-----------|------|------|
| `form-data-normalization` | (image CMD) `uvicorn api.main:app … :5013` | API + **webhook receiver** (Service `:80` → `:5013`, Ingress `data-normalization-prod-ingress`) |
| `form-data-normalization-worker` | `python main.py worker` | AI normalization loop (scalable; atomic claim is race-safe) |
| `form-data-normalization-cron` | `python main.py cron` | APScheduler — **must stay at 1 replica** (two schedulers = duplicate watch registrations) |

All three reference the same image (`bom.ocir.io/bmv2bqg5gpcd/form-data-normalization:<date>-<branch>`) and mount the pluginalex SA from Secret `data-normalization-sa` at `/app/secrets/auth_creds.json`. Image pull secret: `oracleregistry`. Inline env on each container (these **override** the baked `/app/.env`):
- `GOOGLE_SERVICE_ACCOUNT_FILE=/app/secrets/auth_creds.json`
- `GOOGLE_DRIVE_WEBHOOK_URL=https://data-normalization.prod.pluginlive.com/webhooks/google-drive`
- `ENVIRONMENT=production`

Deploy via `deploy.sh` (option `17`) which builds + pushes the image and does `kubectl set image deployment/form-data-normalization …`. ⚠️ `deploy.sh` only rolls the **API** deployment — you must also `kubectl set image deployment/form-data-normalization-worker` and `…-cron` (same image tag) to roll the siblings. The first time these were created (2026-06-12) the worker/cron manifests had to be applied manually; consider adding them to `deploy.sh` or a manifest repo.

---

## Architecture

| Component | Role |
|-----------|------|
| **FastAPI app** (`api/main.py`) | REST API, CORS, lifespan hooks |
| **Normalization worker** | Background loop: **atomically claims** pending rows → OpenAI → entity matcher → writes normalized data. Safe to run across multiple replicas (see Concurrency below) |
| **Assessment worker** | Syncs assessment scores from assessment DB |
| **Form metadata worker** | Fetches Google Forms metadata |
| **Export worker** | Async CSV/Excel generation for large exports |
| **Scheduler** (APScheduler) | Daily ingest (1 AM, now a safety-net backfill behind the webhook), webhook health check (**hourly**, `CronTrigger(hour="*/1")`), webhook renewal (Sun 1 AM), status report (every 5 min), log cleanup (2 AM) |

---

## Key Services

| File | Lines | Purpose |
|------|-------|--------|
| `services/db_service.py` | ~5,800 | Database abstraction — raw data CRUD, batch ops, export queries, webhook state |
| `services/normalization_service.py` | ~3,700 | LLM calls (GPT-4o-mini), batch processing, email/gender validation, CV parsing |
| `services/normalization_matcher.py` | ~3,750 | Fuzzy matching (rapidFuzz) + AI entity resolution against master data |
| `services/candidate_service.py` | ~1,500 | Search & filtering — 20+ filter combinations, full-text search |
| `services/normalization_prompt.py` | ~1,600 | System prompt engineering for field extraction (structured JSON output) |
| `workers/normalization_worker.py` | ~6,500 | Main worker: atomic claim → OpenAI → entity match → insert normalized → log |

---

## Concurrency — claiming candidates (race-safe across replicas)

PROD runs **2 corporate-node + 3 FastAPI replicas**, so multiple worker/producer loops can hit the queue at once. Candidates are claimed from `candidates_raw_data` with a **single atomic statement** so the same person is never normalized twice.

**`db_service.claim_pending_for_normalization(batch_size, sheet_id?, exclude_sheet_id?)`** — the only correct way to pick up work:

```sql
WITH claimed AS (
    UPDATE candidates_raw_data
    SET normalization_status = 'in_progress', processing_started_at = NOW()
    WHERE id IN (
        SELECT id FROM candidates_raw_data
        WHERE normalization_status = 'pending'
           OR (normalization_status = 'in_progress'
               AND processing_started_at < NOW() - INTERVAL '15 minutes')  -- stale reclaim
        ORDER BY id ASC
        LIMIT :batch
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *
)
SELECT claimed.*, s.source_file, s.source_sheet, s.source_sheet_id, s.source_form_id
FROM claimed LEFT JOIN ingested_sheets s ON s.id = claimed.sheet_id
ORDER BY claimed.id ASC;
```

Select + mark happen in one transaction, so `RETURNING` hands each row to **exactly one** worker. Callers: `normalization_worker.run_once`, `run_once_sheet_wise`, and `Kafka/kafka_producer.run_once`.

**Why not the old way:** the previous flow used `fetch_pending_for_normalization()` (a `SELECT ... FOR UPDATE SKIP LOCKED` inside a `begin()` block that **committed and released the locks** as soon as it returned) followed by a separate `mark_in_progress()` UPDATE. Between those two transactions the rows were still `pending`, so a second replica re-read and re-normalized the same candidate. `SKIP LOCKED` only dedupes while the transaction is held open — committing first defeated it. `fetch_pending_for_normalization` / `mark_in_progress` still exist but must **not** be used to pick up work.

**Idempotency safety net:** `mark_completed` / `mark_skipped` only write when the row is still `normalization_status = 'in_progress'` (`... WHERE id = :id AND normalization_status = 'in_progress'`), so a stale-reclaim overlap can't double-write a result.

**No schema change** — uses existing `normalization_status`, `processing_started_at`, `normalized_at` columns.

---

## API Endpoints

### Candidates (`/api/candidates`)

| Method | Endpoint | Purpose |
|--------|----------|--------|
| GET | `/api/candidates` | List with advanced filtering (search, role, skills, experience, salary, scores) |
| GET | `/api/candidates/{id}` | Get by ID |
| GET | `/api/candidates/raw` | Raw (un-normalized) data |
| GET | `/api/candidates/raw-by-sheet/{sheet_id}` | Raw data by source sheet |
| POST | `/api/candidates/download` | Export as CSV/Excel |
| POST | `/api/candidates/normalized/update` | Update normalized data |
| GET | `/api/candidates/columns` | Available export columns |
| GET | `/api/candidates/validation-log/{raw_data_id}` | Validation logs |
| GET | `/api/candidates/normalization-log/{raw_data_id}` | LLM normalization logs |
| POST | `/api/candidates/ingest` | Trigger Google Drive ingestion |
| GET | `/api/candidates/ingest/status` | Ingestion status |
| POST | `/api/candidates/normalize` | Trigger normalization worker |
| POST | `/api/candidates/normalize-sheet/{sheet_id}` | Normalize specific sheet |

### Student Metrics (`/api/students`)

| Method | Endpoint | Purpose |
|--------|----------|--------|
| GET | `/api/students` | List with filtering |
| GET | `/api/students/{id}` | Student details |
| GET | `/api/students/assessment/{id}` | Assessment scores |
| POST | `/api/students/download` | Export |
| POST | `/api/students/download/async` | Async export job |
| GET | `/api/students/download/status/{job_id}` | Export status |
| GET | `/api/students/dashboard-summary` | Dashboard stats |

**Filter endpoints** (all GET under `/api/students/`): `institute-campuses`, `degrees`, `departments`, `cities`, `states`, `roles`, `work-companies`, `work-designations`, `work-industries`, `passing-years`, `master-corporates`, `master-institutes`

### API Ingestion (`/api/api-ingest`) — requires `X-API-Key` header

| Method | Endpoint | Purpose |
|--------|----------|--------|
| POST | `/api/api-ingest/ingest` | Ingest candidate via API (raw_data + cv_url) |
| GET | `/api/api-ingest/status/{ref_id}` | Ingestion status by reference ID |

### Google Drive Webhooks

| Method | Endpoint | Purpose |
|--------|----------|--------|
| GET | `/webhooks/google-drive` | Health check (`{"status":"ok"}`) |
| POST | `/webhooks/google-drive` | Receive Drive file change notifications (real-time ingest trigger) |

### Ingest UI (HTML)

| Method | Endpoint | Purpose |
|--------|----------|--------|
| GET | `/ingest` | Interactive ingest UI |
| POST | `/ingest/start` | Start manual ingestion |
| GET | `/ingest/stream/{run_id}` | Stream logs (SSE) |

### Admin-React UI Triggers

The `POST /api/candidates/ingest` + `GET /api/candidates/ingest/status` (poll every 3s until `status.running === false`) endpoints are exposed via an **Ingest** button on two admin-react screens (both call them through `utils/candidateRequest`, base URL `REACT_APP_API_URL`):

| Screen | Component | Ingest button | Normalize button |
|--------|-----------|---------------|------------------|
| Mismatched Candidates List | `modules/CandidateMetrics/index.js` | **Enabled** | Hidden (commented) |
| Candidates Raw / list screen | `modules/CandidatesRaw/index.js` | Enabled | — |

Note: on `CandidateMetrics` the Ingest button was commented out by the Apr-2026 Google-Drive ingestion redesign (commit `06bc28f0`) and re-enabled later — the `handleIngest`/`handleNormalize` handlers were never removed, only the JSX was toggled. The **Normalize Data** button there remains commented out.

---

## Database Schema

**Schema:** `candidate_ingestion_schema`

| Table | Purpose |
|-------|--------|
| `ingested_sheets` | Track Excel/Form sources (source_sheet_id, source_file, last_processed_row, form_status) |
| `candidates_raw_data` | Raw ingested data (JSONB), normalization status, timestamps |
| `candidates` | Normalized records (name, email, mobile, gender, DOB, assessment_scores JSONB) |
| `candidate_job_details` | Role-specific data (role, cv_url, normalized_data JSONB, cv_data JSONB) |
| `open_ai_logs` | LLM API calls (prompt, response, token counts) |
| `normalization_logs` | Audit trail (old_data, new_data, normalized_keys) |
| `validation_logs` | Field validation results |
| `drive_webhook_log` | Drive change events |
| `drive_state` | Single row `id='drive'` — webhook state (`start_page_token`, `webhook_data` JSONB) |
| `ingested_forms` | Google Forms metadata |
| `export_jobs` | Async download jobs (status, file_path) |

**Relationships:** `candidates_raw_data` → `ingested_sheets` (many-to-one), `candidates` → `candidates_raw_data` (1:1), `candidate_job_details` → `candidates` (many-to-one). NB: the only DB-enforced FKs into `ingested_sheets` are from `candidates_raw_data.sheet_id`, `candidates.sheet_id`, `ingested_forms.sheet_id`. The `candidates.raw_data_id` and `candidate_job_details.candidate_id` columns are NOT FK-enforced — cleanup scripts must delete them manually in order.

---

## Integration Points

| Service | Purpose |
|---------|--------|
| **Google Drive API** | List/download Excel files, webhook (`changes.watch`) registration |
| **Google Forms API** | Fetch form metadata |
| **OpenAI API** (GPT-4o-mini) | Field normalization, entity matching |
| **Gemini API** (3.0 Flash) | Fallback AI normalization |
| **Resume Parser** (`resume-parser.uat.pluginlive.com`) | PDF CV parsing |
| **PG Vector Search** (`vector-search.dev.pluginlive.com`) | Master entity resolution |
| **Assessment DB** | Fetch assessment scores (separate PG connection) |
| **student-node `POST /students/create-full`** | Final push of the normalized candidate → student record. URL = `{BASE_URL}/students/create-full`, auth via `auth-key: STUDENT_API_KEY`. UAT `BASE_URL=https://api-std.uat.pluginlive.com`, PROD `https://api-stud.pluginlive.com`. |

---

## Push to student-node `create-full` (the "Push to API" / "Ingest" step)

The **Ingest** button (Mismatched Candidates List) re-pushes a candidate through
`CandidateService.process_single_completed_candidate(candidate_id)`. This is
**deterministic — it does NOT re-run the LLM**: it reads the already-stored
`candidate_job_details.normalized_data`, re-maps to the create-full schema
(`NormalizationWorker.map_to_final_schema`), cleans currentCourse/education, then
POSTs `mapped_data` to student-node via `NormalizationWorker.create_full_student`
(`workers/normalization_worker.py`, `url = {BASE_URL}/students/create-full`).

On failure the **full request payload is persisted** in `normalization_logs`
(`step_name='push_to_api'`, `log_level='WARNING'`, `details.request = mapped_data`,
`details.response`), and the candidate surfaces under **Mismatched Candidates**
(data status `Valid`, API status `API Failed`).

### Gotcha — `cumulativeType` enum rejection (FST_ERR_VALIDATION)

student-node's create-full Fastify schema restricts both `currentCourse.cumulativeType`
and `education[].cumulativeType` to the enum **`["Percentage","CGPA"]`** (schema
`default: "Percentage"`). The normalization LLM prompt can emit values that are **not
in this enum** — most commonly an empty string `""` (currentCourse with no captured
grade-type), and potentially `"CGPA (decimal)"` / `"GPA"`. AJV's `default` only applies
when the field is **absent**, NOT when it is present-but-empty, so `""` is rejected with:

```
400 FST_ERR_VALIDATION  body/currentCourse/cumulativeType must be equal to one of the allowed values
```

This blocked a large mismatched-candidate backlog (~3.6k on PROD, Jun 2026).

**Guard (student-node `app/routes/student.js`, create-full `preValidation`):** an
empty/whitespace `cumulativeType` is **deleted** so the schema default `"Percentage"`
applies; `"percentage"`/`"cgpa"` case-variants are canonicalised; unknown non-empty
values pass through so the validator still rejects them with the original token visible.
Sibling guards in the same hook normalise `admin.gender`, `educationLevel`, and coerce
marks strings.

**Producer-side guard (IMPLEMENTED, Jun 2026):** `NormalizationWorker._sanitize_payload_cumulative_types()`
runs at the top of `create_full_student` (the single push chokepoint, so it covers
both the worker's initial push and the dashboard re-push). It canonicalises
`currentCourse.cumulativeType` and every `education[].cumulativeType`:
`*cgpa*`/`*gpa*` → `CGPA`, `*percent*`/`%` → `Percentage`, and **drops anything else**
(empty / unknown / non-string) so student-node's schema default `Percentage` applies.
Value-agnostic — a single bad token can never block the push again. This let the PROD
backlog clear **without touching student-node**: deployed to all 3 PROD deployments on
`release-v1.33-hotfix-1` (image `…2026-06-16-05-02-52-release-v1.33-hotfix-1`); the
`config/settings.py` `BASE_URL` default stays `https://api-stud.pluginlive.com` (do NOT
merge the UAT value `api-std.uat.pluginlive.com` onto release — it would repoint PROD
pushes at UAT). After deploy, the **Ingest** button re-pushes the mismatched candidates.

---

## Key Environment Variables

| Variable | Purpose |
|----------|--------|
| `POSTGRES_URL` | Main DB (with `?options=-csearch_path=candidate_ingestion_schema`) |
| `POSTGRES_ASSESSMENT_SCORE_URL` | Assessment DB connection |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | OpenAI config (default: gpt-4o-mini) |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Gemini fallback |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Service account JSON path. **UAT: `./auth_creds.json`** (baked); **PROD: `/app/secrets/auth_creds.json`** (k8s Secret `data-normalization-sa`). Both = pluginalex SA `pluginliveservice@pluginalex.iam.gserviceaccount.com`. |
| `GOOGLE_DRIVE_FOLDER_ID` | Drive folder to monitor. **UAT: `1OJ2sGcz85VmGk2fHkg3XALW5nX5M06Ug`** · **PROD: `1vnv0vCwqPnAU_I3afaW7zRn3ge8QLNtG`** |
| `GOOGLE_DRIVE_WEBHOOK_URL` | Webhook receiver URL. **UAT: `https://data-normalization.uat.pluginlive.com/webhooks/google-drive`** · **PROD: `https://data-normalization.prod.pluginlive.com/webhooks/google-drive`** (both Let's Encrypt; ngrok is local-dev only) |
| `PDF_PARSER_URL` / `PDF_PARSER_AUTH_KEY` | Resume parser endpoint |
| `ENTITY_NORMALIZER_API_URL` | PG Vector Search endpoint |
| `API_SECRET_KEY` | Auth key for `/api/api-ingest` endpoints |
| `APP_ENV` | `local` / `uat` / `prod` |

---

## Docker & Deployment

```bash
# Build (UAT image tag)
docker build --build-arg ENVIRONMENT=uat -t datanormalization:api .

# API + webhook receiver
docker run -itd --name datanormalization --restart always --env-file .env -p 5013:5013 datanormalization:api
# Normalization worker (sibling container)
docker run -itd --name datanormalization-worker --restart always --env-file .env datanormalization:api python main.py worker
# Scheduler (sibling container)
docker run -itd --name datanormalization-cron --restart always --env-file .env datanormalization:api python main.py cron
```

```bash
# PROD (k8s) — after deploy.sh builds & pushes the image, also roll the siblings:
TAG=bom.ocir.io/bmv2bqg5gpcd/form-data-normalization:<date>-<branch>
kubectl -n api set image deployment/form-data-normalization        form-data-normalization=$TAG
kubectl -n api set image deployment/form-data-normalization-worker form-data-normalization-worker=$TAG
kubectl -n api set image deployment/form-data-normalization-cron   form-data-normalization-cron=$TAG
```

**CLI modes** (via `main.py`):
```bash
python main.py ingest              # Ingest from Google Drive
python main.py worker              # Start normalization worker
python main.py cron                # Start scheduler
python main.py form_metadata_worker  # Fetch form metadata
python main.py api_ingest_worker   # Process API ingestion queue
python main.py ingest_parallel     # Parallel multi-file ingestion
```

**Dev setup:**
```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn api.main:app --reload --host 0.0.0.0 --port 8001  # API server
python main.py worker   # Normalization worker (separate terminal)
python main.py cron     # Scheduler (separate terminal)
```
