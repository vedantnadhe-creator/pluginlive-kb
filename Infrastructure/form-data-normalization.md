---
type: reference
tags: [service, api, python, normalization, ingestion, ai]
---

# Form Data Normalization Service

**Repo:** `/home/ubuntu/api/form-data-normalization`
**Stack:** Python 3.11 · FastAPI · PostgreSQL · OpenAI (GPT-4o-mini) · **Gemini 2.5 Flash-Lite** (primary normalization model)
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

⚠️ **`deploy.sh` only builds/runs `datanormalization`** — it does *not* recreate the `-worker`/`-cron` siblings, and rebuilding the image does not restart them. After any redeploy, recreate the two siblings manually (or add them to `deploy.sh`). Code + SA key are **baked into the image** (`COPY . /app`), so config/key changes require an image rebuild, not just an `.env` edit. The runtime config (batch sizes, model, normalizer URL) is read from the baked `/app/.env`, but OS env vars set via `docker run -e`/`--env-file` **override** it.

### PROD runtime topology — 3 Deployments in ns `api`

| Deployment | Args | Role | Replicas (2026-06-19) |
|-----------|------|------|----|
| `form-data-normalization` | (image CMD) `uvicorn api.main:app … :5013` | API + **webhook receiver** | 1 |
| `form-data-normalization-worker` | `python main.py worker` | AI normalization loop (scalable; atomic claim is race-safe) | **1** |
| `form-data-normalization-cron` | `python main.py cron` | APScheduler — **must stay at 1 replica** | 1 |

All three reference the same image (`bom.ocir.io/bmv2bqg5gpcd/form-data-normalization:<date>-<branch>`) and mount the pluginalex SA from Secret `data-normalization-sa` at `/app/secrets/auth_creds.json`. Image pull secret: `oracleregistry`. Inline env on each container (these **override** the baked `/app/.env`):
- `GOOGLE_SERVICE_ACCOUNT_FILE=/app/secrets/auth_creds.json`
- `GOOGLE_DRIVE_WEBHOOK_URL=https://data-normalization.prod.pluginlive.com/webhooks/google-drive`
- `ENVIRONMENT=production`

PROD runtime config (from baked `/app/.env`): `AI_BATCH_SIZE=100`, `API_INGEST_BATCH_SIZE=20`, `API_INGEST_POLL_INTERVAL_SECONDS=30`, `GEMINI_MODEL=gemini-3-flash-preview` (PROD has **not** yet received the gemini-2.5-flash-lite + compact-prompt optimization — that is DEV+UAT only), `ENTITY_NORMALIZER_API_URL=https://vector-search.prod.pluginlive.com/api/v1/normalize`. The matcher service `pg-vector-api-service` runs **1 replica** in ns `api`. PG `max_connections=450` (~171 in use).

Deploy via `deploy.sh` (option `17`) which builds + pushes the image and does `kubectl set image deployment/form-data-normalization …`. ⚠️ `deploy.sh` only rolls the **API** deployment — you must also `kubectl set image deployment/form-data-normalization-worker` and `…-cron` (same image tag) to roll the siblings. The first time these were created (2026-06-12) the worker/cron manifests had to be applied manually; consider adding them to `deploy.sh` or a manifest repo.

---

## Architecture

| Component | Role |
|-----------|------|
| **FastAPI app** (`api/main.py`) | REST API, CORS, lifespan hooks |
| **Normalization worker** | Background loop: **atomically claims** pending rows → LLM → entity matcher → writes normalized data. Safe to run across multiple replicas (see Concurrency below) |
| **Assessment worker** | Syncs assessment scores from assessment DB |
| **Form metadata worker** | Fetches Google Forms metadata |
| **Export worker** | Async CSV/Excel generation for large exports |
| **Scheduler** (APScheduler) | Daily ingest (1 AM, now a safety-net backfill behind the webhook), webhook health check (**hourly**, `CronTrigger(hour="*/1")`), webhook renewal (Sun 1 AM), status report (every 5 min), log cleanup (2 AM) |

---

## Key Services

| File | Lines | Purpose |
|------|-------|--------|
| `services/db_service.py` | ~5,800 | Database abstraction — raw data CRUD, batch ops, export queries, webhook state |
| `services/normalization_service.py` | ~3,700 | LLM calls, batch processing, email/gender validation, CV parsing, retry loop |
| `services/normalization_matcher.py` | ~3,750 | Fuzzy matching (rapidFuzz) + AI entity resolution against master data |
| `services/candidate_service.py` | ~1,500 | Search & filtering — 20+ filter combinations, full-text search |
| `services/normalization_prompt.py` | ~1,680 | Two system prompts: legacy `SYSTEM_PROMPT` (~15K tokens) and compact `SYSTEM_PROMPT_V2` (~1K tokens, default). Both emit the SAME flat slug-keyed JSON; V2 just shrinks the rules block. Toggle with `NORMALIZATION_COMPACT_PROMPT` |
| `workers/normalization_worker.py` | ~6,500 | Main worker: atomic claim → LLM → entity match (memoized) → insert normalized → `create-full` → log |

---

## Concurrency — claiming candidates (race-safe across replicas)

Candidates are claimed from `candidates_raw_data` with a **single atomic statement** so the same person is never normalized twice, even across multiple worker replicas.

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

Select + mark happen in one transaction, so `RETURNING` hands each row to **exactly one** worker. `FOR UPDATE SKIP LOCKED` means pod-2/pod-3 skip pod-1's locked rows and claim the next disjoint batch — so **scaling worker replicas needs no new lock**; it already self-distributes. The main worker `run_once` **excludes** the API-ingest sheet (`exclude_sheet_id = API_INGEST_SHEET_ID`); the API-ingest queue is drained only by the dedicated `api_ingest_worker` mode.

**Idempotency safety net:** `mark_completed` / `mark_skipped` only write when the row is still `normalization_status = 'in_progress'`, so a stale-reclaim overlap can't double-write a result.

---

## LLM retry / recovery (already implemented)

Four layers, none added by the cost optimization:
1. **Transport** — `_call_openai_with_retries` (3 attempts, exponential backoff `0.5·2^(n-1)`) wraps every Gemini/OpenAI call; OpenAI path never retries `insufficient_quota`.
2. **Cache fallback** — `gemini_client.create_completion`: a stale/deleted context-cache ref (4xx) drops the cache and retries once inline; a failed cache-create is parked 5 min.
3. **Parse/quality** — outer `for retry in range(1,4)` in `normalize()`: `json.JSONDecodeError` → sleep 0.5s, re-call (raises `ValueError` after 3); incomplete output (`_validate_normalization` finds dropped fields) → re-call; HTTP 429 → wait `2^attempt`. `_extract_json()` strips ```` ``` ```` fences + brace-matches before parsing so minor noise doesn't burn a retry.
4. **Queue durability** — failed `normalize()` marks the row failed/skipped; stale `in_progress > 15 min` rows are reclaimed (crash recovery). **`create-full` itself has no auto-retry** — a transient student-node 5xx sends the candidate to *Mismatched Candidates* for manual re-push.

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

### API Ingestion (`/api/api-ingest`) — requires `X-API-Key` header

| Method | Endpoint | Purpose |
|--------|----------|--------|
| POST | `/api/api-ingest/ingest` | Ingest candidate via API (`{data, cv_url}`) → enqueues `pending`, returns `ref_id` |
| GET | `/api/api-ingest/status/{ref_id}` | Ingestion status by reference ID |

Note: `/ingest` only enqueues; the dedicated `api_ingest_worker` mode (`python main.py api_ingest_worker`) drains the API-ingest sheet (it is **not** the running `worker`, which excludes that sheet). It drains all pending on startup, then polls every `API_INGEST_POLL_INTERVAL_SECONDS`.

### Google Drive Webhooks

| Method | Endpoint | Purpose |
|--------|----------|--------|
| GET | `/webhooks/google-drive` | Health check (`{"status":"ok"}`) |
| POST | `/webhooks/google-drive` | Receive Drive file change notifications (real-time ingest trigger) |

### Student Metrics (`/api/student-metrics`) — candidate analytics dashboard (admin-react)

Backs the admin-react Candidate Metrics dashboard. Supports the full filter set
(gender, status, institute, degree, roles, work experience, salary, passing years…)
plus pagination and async CSV/Excel export (`/download/async` → `export_jobs`,
drained by the `worker` sibling).

**Semantic role search (`role_search`)** — *live UAT + DEV, 2026-06-22.* A free-text
role query (e.g. `full stack`, `fullstack`, `software developer`) returns **all**
semantically-matching candidates in one shot, so users don't hand-pick every role
variant. Fixes the old literal-`LIKE` gaps where `fullstack` (no space) or
`software developer` returned no/few roles.

- Param `role_search` on `GET /api/student-metrics` and the download endpoints
  (the GET grid is wired; **async export via the `worker` sibling is not yet
  rebuilt** — it ignores `role_search` until the worker container is refreshed).
- How it works: `services/semantic_roles.py` embeds the query (Gemini
  `gemini-embedding-001` @ 1536 dims, L2-normalized, `RETRIEVAL_QUERY`), pulls the
  nearest role ids from the `ROLE_VECTOR_DB_URL` pgvector store
  (`job_role_embeddings`, cosine, top-k + threshold), then filters students via
  `corporate.job_role_student_map` (`is_applied=1`) — the same mapping the roles-chip
  filter uses, so typing a role and selecting its chips return the same candidates.
- **Fail-open**: if disabled, the store is unreachable, or the embed call fails,
  `expand()` returns `[]` and the grid falls back to existing behavior — it can't
  break the dashboard.
- Vector store: dedicated `role-vec-proto` pgvector container (named volume
  `role-vec-data`, `--restart`, published on `127.0.0.1:5460` + bridge gateway
  `172.17.0.1:5460`). Backfill (≈30s, ~1361 distinct titles): inside the app
  container run `python -m scripts.build_role_index`. Embeddings are a snapshot —
  re-run after roles change. **Not auto-provisioned by deploy.sh** — the container +
  backfill + env vars must exist on the box or the feature stays a no-op.

---

## Database Schema

**Schema:** `candidate_ingestion_schema`

| Table | Purpose |
|-------|--------|
| `ingested_sheets` | Track Excel/Form sources (source_sheet_id, source_file, last_processed_row, form_status) |
| `candidates_raw_data` | Raw ingested data (JSONB), normalization status, timestamps |
| `candidates` | Normalized records (name, email, mobile, gender, DOB, assessment_scores JSONB) |
| `candidate_job_details` | Role-specific data (role, cv_url, normalized_data JSONB, cv_data JSONB, `linkedin_data` JSONB) |
| `open_ai_logs` | LLM API calls (prompt, response, token counts) — 1 row per normalization call |
| `normalization_logs` | Audit trail (steps incl. `*_matcher_api`, `create_full_student_*`; old/new data, timestamps) |
| `validation_logs` | Field validation results |
| `drive_webhook_log` | Drive change events |
| `drive_state` | Single row `id='drive'` — webhook state (`start_page_token`, `webhook_data` JSONB) |
| `ingested_forms` | Google Forms metadata |
| `export_jobs` | Async download jobs (status, file_path) |

---

## Integration Points

| Service | Purpose |
|---------|--------|
| **Google Drive API** | List/download Excel files, webhook (`changes.watch`) registration |
| **Google Forms API** | Fetch form metadata |
| **Gemini API** (2.5 Flash-Lite / 3 Flash-Preview) | **Primary** field normalization (`USE_OPENAI=false`), routed through the **LiteLLM proxy** on UAT (`LITELLM_PROXY_URL`+`LITELLM_VIRTUAL_KEY` → OpenAI-compatible client, model name routes the provider). **"Invalid JSON from AI" fix (2026-06-24):** the LiteLLM path used `max_tokens=4096` and no `response_format`, so large candidates (45+ fields) were truncated mid-JSON. Now `_call_openai_sync` sends `response_format={"type":"json_object"}` + `max_tokens=GEMINI_MAX_OUTPUT_TOKENS` (16384), and the native `GeminiClient` sets `generationConfig.responseMimeType=application/json`. A `json_mode` flag (default True) is threaded through `_call_openai_with_retries`; the yes/no `_same_company_llm` call passes `json_mode=False`. **Belt-and-suspenders:** `_loads_lenient()` wraps `json.loads` with a **`json_repair`** fallback (dep `json-repair`) — Gemini 3-flash-preview *still* occasionally emits malformed JSON (unquoted keys, trailing/double commas, cut-off tail) even in JSON mode, and repair recovers it instead of failing the candidate. Used in both `normalize()` and `cv_gap`. Stuck `in_progress` rows are recovered by `reset_in_progress_to_pending` on worker startup. |
| **OpenAI API** (GPT-4o-mini) | Alternate normalization + matcher AI tie-break when `USE_OPENAI=true` |
| **Resume Parser** (`resume-parser.uat.pluginlive.com`) | PDF CV parsing |
| **PeopleDataLabs** (`api.peopledatalabs.com/v5/person/enrich`) | LinkedIn profile enrichment for experienced-role candidates (opt-in, `PDL_ENABLED`). See "LinkedIn enrichment" below. |
| **PG Vector Search / Entity Normalizer** (`vector-search.{dev,prod}.pluginlive.com`, k8s `pg-vector-api-service`) | Master entity resolution (institute/degree/city/state/country/department). **5–10s per call**; the dominant per-candidate latency. |
| **Assessment DB** | Fetch assessment scores (separate PG connection) |
| **student-node `POST /students/create-full`** | Final push of the normalized candidate → student record. URL = `{BASE_URL}/students/create-full`, auth via `auth-key: STUDENT_API_KEY`. UAT `BASE_URL=https://api-std.uat.pluginlive.com`, PROD `https://api-stud.pluginlive.com`. Responds ~0.4s. |

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

### Behavior — Tally/normalization students are NOT linked to a college (`source` field, Jun 2026)

Students ingested via a Tally form through normalization are **not registered through a
college**, so they must not appear under one. The student roster's "under a college" filter
is driven purely by `student.students.institute_campus_id`, so the rule is enforced at the
producer:

- `workers/normalization_worker.py` sets the create-full `student` payload to
  **`source: "TALLY_FORM"`** and **`instituteCampusId: ""`** (it no longer resolves the
  studied-at institute into the campus link). `instituteCampusName` / `courseId` / `education`
  are still populated for reporting — only the membership *id* is dropped.
- student-node persists a new column **`student.students.source`** (`text DEFAULT 'MANUAL'`,
  Prisma `student.source`). `MANUAL` = admin/institute-created; `TALLY_FORM` = normalization
  ingested. Accepted via `CreateFullStudentBodySchema.student.source` and written by
  `Student.create` (it spreads the `student` object). The Prisma client is regenerated at
  build time, so a redeploy is required when the schema changes.
- With an empty `instituteCampusId`, the create-full handler already treats the candidate as
  experienced/corporate (`isExpStudent = true`); the campus-gated college-metrics trigger and
  the role-map campus simply no-op. The student still maps to the **job role** they applied to.
- **Gotcha (fixed Jun 2026):** clearing the id but **keeping the campus name** is not enough on its
  own. student-node's `createFullStudent` → `materializeMissingMasterIds` → `ensureStudentCampus`
  used to **re-derive `instituteCampusId` from `instituteCampusName`** (via `InstituteService.saveinstitute`)
  whenever the id was empty — silently re-linking the Tally student back to the college (even an
  **inactive** one, which it would re-create). Fixed by skipping that backfill when
  `student.source === 'TALLY_FORM'` (`app/handlers/common.js`). The name is still kept for reporting.
  Without this, every new Tally candidate reappeared under its studied-at college.

**Identifying existing Tally students** (for backfill): `student.students.response_data IS NOT NULL`
— that jsonb column is populated *only* on the normalization path (its keys are normalized-form
fields like `highest_qualification_education_level`). DB-Scripts migration
`Tally Student Source/001_add_source_column_to_students.sql`. UAT backfill (Jun 2026): 6,267
tagged `TALLY_FORM`, 5,296 detached from a college (`institute_campus_id` → NULL, name kept);
reversible snapshot in `student.backup_tally_campus_20260622`. PROD pending. **Going forward the
canonical identifier is `source = 'TALLY_FORM'`** (response_data is the historical-only proxy);
to catch any re-linked rows: `WHERE source='TALLY_FORM' AND institute_campus_id <> ''`.

### Behavior — existing student is updated, not rejected; materialized masters are active (Jun 2026)

Two `create-full` behaviors changed in student-node (`app/handlers/common.js`,
`createFullStudent`):

- **Existing student → data is refreshed on every call.** Previously `create-full`
  only updated an existing student in the narrow corporate-lead case
  (`access_level == [2]` only **and** `is_corporate == true`); any other existing
  email either just created a job-role mapping (when `roleId` was sent) or returned
  `400 "A student with email … already exists."`. Now **any** existing student is
  updated via the shared `updateExistingStudentData(req, studentId, { promoteCorporate })`
  helper — it re-applies the `admin`/profile fields, materializes missing masters,
  then writes `student` + `studentPersonalProfile` + `education` (upsert per
  `educationLevel`) + `currentCourse` + `resume` (the last two only when present in
  the payload; `Student.update` does a nested *update*, so those child rows must
  already exist). `promoteCorporate:true` keeps the old corporate-lead promotion
  (`accessLevel [2] → [1,2]`, `isCorporate → false`); the general path passes
  `false`. The no-`roleId` existing case now returns **`200 "Student already exists.
  Data updated successfully."`** instead of `400`. Role-mapping logic is unchanged.
- **Materialized masters are created ACTIVE, not pending.** `materializeMissingMasterIds`
  (`ensureDegreeStream` / `ensureInstitute` / `ensureStudentCampus`) used to create
  missing degree/stream/specialisation/college as **pending/inactive** (degree+stream
  via institute-node `createDegreeForStudentsOthers` → `status 0` / `dataType "OTHERS"`;
  college via `studentcollege` → institute `status` default `0`). create-full is
  admin-driven, so those masters should be live immediately. This is now **opt-in** on
  institute-node so other callers (student self-service "Others") keep the pending
  default:
  - `createDegreeForStudentsOthers` accepts **`activate: true`** → freshly-created
    degree/stream/specialisation use `status 1` / `dataType "CURRENT"`.
  - `studentcollege` schema (`createstudentInstituteSchema`) now allows
    **`institute.status`**; create-full passes `status: 1` so the new college is active
    (the model already spreads `institute` fields into `prisma.institute.create`).
  - student-node sends `activate: true` (degrees) and `institute.status: 1` (colleges)
    from `materializeMissingMasterIds` only. **Existing inactive masters are not
    force-activated** — only newly-created ones go live.
  - The `TALLY_FORM` skip above is unchanged: Tally students still never re-link/recreate
    their studied-at college.

### Gotcha — `cumulativeType` enum rejection (FST_ERR_VALIDATION)

student-node's create-full Fastify schema restricts both `currentCourse.cumulativeType`
and `education[].cumulativeType` to the enum **`["Percentage","CGPA"]`** (schema
`default: "Percentage"`). The normalization LLM prompt can emit values that are **not
in this enum** — most commonly an empty string `""`. AJV's `default` only applies when
the field is **absent**, NOT present-but-empty, so `""` is rejected with `400
FST_ERR_VALIDATION`. **Producer-side guard:** `NormalizationWorker._sanitize_payload_cumulative_types()`
runs at the top of `create_full_student` and canonicalises `*cgpa*`/`*gpa*` → `CGPA`,
`*percent*`/`%` → `Percentage`, dropping anything else so the schema default applies.
Sibling guards normalise `admin.gender`, `educationLevel`, and coerce marks strings.

### Gotcha — phone number dropped when `countryCode` is empty (FIXED, Jun 2026)

`create-full` maps `admin.phoneNumber` → `studentPersonalProfile.phoneNumber`. The mapping
in student-node `app/handlers/common.js` was gated on **both** `countryCode && phoneNumber`,
so a payload with `"countryCode": ""` silently dropped the phone. Fixed via a shared
`formatAdminPhone(admin)` helper that stores the phone whenever `phoneNumber` exists.
Deployed DEV + UAT; PROD pending. Historical rows with empty countryCode have NULL
`contact_number` and need a backfill.

---

## LinkedIn enrichment via PeopleDataLabs (opt-in, UAT-LIVE Jun 2026)

For candidates applying to an **experienced role** who supply a **LinkedIn URL but no CV**,
the normalization worker enriches the profile from PeopleDataLabs (PDL) and feeds it into
the same `create-full` `resume` payload the CV parser produces. Mirrors the CV path so a
LinkedIn-sourced candidate gets a populated work history / education without a résumé.

**Three hard gates** (all must hold, in `NormalizationWorker._process_single_candidate`):
1. `PDL_ENABLED=true` **and** `PDL_API_KEY` set (feature OFF by default).
2. The role is **experienced** — `DBService.is_experienced_role(role_id)` checks
   `corporate.job_roles.job_type_levels` contains `EXPERIENCED` **or** `BOTH` (`role_id`
   is the filename `#`-suffix = `corporate.job_roles.id`).
3. The candidate has a `linkedin_url` **and** no `cv_url` (CV candidates are already
   covered by the resume parser).

> **Gotcha — LLM drops non-standard URL columns.** The LLM normalizer maps `"LinkedIn
> Profile" → linkedin_url`, but real Tally forms use headers like **"Linkedin URL"** that
> it silently drops, so `linkedin_url` never reaches `normalized_data` and the gate never
> fires. Fixed (Jun 2026) with a deterministic, **header-agnostic** fallback
> `find_linkedin_url_in_raw(raw_data)` (in `peopledatalabs_service.py`) that scans the raw
> form **values** for a `linkedin.com/in|pub/...` URL, scheme-normalizes it
> (`www.linkedin.com/in/x → https://…`), and surfaces it into `normalized_data`. Mirrors
> the existing `cv_url` raw fallback. (The sibling `cv_url`/CV columns like "Upload CV
> (PDF)" can be dropped by the LLM the same way — a separate known gap.)
>
> **Gotcha 2 — LinkedIn URL mis-mapped into `cv_url`.** When a form has a LinkedIn URL and
> **no** real résumé (e.g. `Upload CV (PDF) = "N/A"`), the LLM puts the only URL it sees —
> the LinkedIn one — into the `cv_url` slug. That makes `parse_pdf` try to parse a LinkedIn
> page as a PDF **and** fails the enrichment "no cv_url" gate (so PDL never runs). Fixed
> (Jun 2026): right after `cv_url` is resolved, if `is_linkedin_profile_url(cv_url)` →
> clear `cv_url` and route the value to `linkedin_url`. So a LinkedIn URL is never treated
> as a CV.
>
> **Gotcha 3 — most-recent LinkedIn job dropped when the form has its own recent.**
> `linkedin_normalized_fields` emits the most-recent LinkedIn job as `recent_*` and the
> rest as `work_N_*`. If the FORM already filled `recent_*` (which wins on merge), the
> LinkedIn current job — excluded from `work_N_*` — was lost. Fixed (Jun 2026): **all**
> experience entries are emitted as `work_N_*` (including the most recent). When the form
> has no recent job, `recent_*` == `work_1_*` and `map_to_final_schema`'s sheet-entry dedup
> (role + start + end) collapses them, so no duplicate is introduced.
>
> **Deploy target (important):** the hook runs in the **`datanormalization-worker`** container
> (`python main.py worker`) on **uat.pluginlive.com** — that's what processes the ingest
> queue. `deploy.sh` option 24 only rebuilds the API container from the wrong branch
> (`git pull origin Development`), so deploy LinkedIn/normalization changes manually:
> `ssh uat → git pull origin UAT → (add PDL_* to .env) → docker build -t datanormalization:api . →`
> recreate **all three** containers (`datanormalization`, `-worker`, `-cron`).

**Flow** (`services/peopledatalabs_service.py`):
- `PeopleDataLabsService.enrich(linkedin_url=…)` → `GET /v5/person/enrich?profile=<url>&min_likelihood=6`,
  header `X-Api-Key`. Returns `{}` on disabled / no-match / 4xx-5xx (never raises). Raw
  provenance-tagged profile is stored on `candidate_job_details.linkedin_data` (JSONB) via
  the decoupled `DBService.update_candidate_job_linkedin_data` (fail-safe — wrapped in
  try/except so a missing column never breaks ingestion).
- `build_linkedin_resume(profile)` — **deterministic** (no LLM, PDL is already structured)
  reshape of the PDL profile into the create-full `resume` object: `admin`, `workExperience[]`,
  `education[]`, `currentCourse`. Fed to `map_to_final_schema` as the `cv_data` arg
  (`cv_data or linkedin_resume or {}`).
- `linkedin_normalized_fields(profile)` — scalar gap-fill merged into `normalized_data`
  (only where the form left a blank): `recent_role_title`→`student.currentDesignation`,
  `recent_company_name`→`student.currentOrganization`, `total_experience`, `work_N_*`
  (full history, `YYYY-MM-DD` dates so `map_to_final_schema`'s dedup collapses the recent
  role), `education_*` / `highest_qualification_*`.

**Gotchas:**
- PDL returns redacted fields (incl. all contact: `work_email`/`emails`/`phone_numbers`/
  `mobile_phone`) as the boolean `true`/`false` — the mapper drops these, so **no email/phone
  is ever pulled from PDL** (we already have those from the form). Current plan tier has no
  contact-data entitlement anyway.
- Do **not** add a nested `resume.workExperience` to `build_linkedin_resume` — the full
  history flows through the `work_N_*` normalized keys (`YYYY-MM-DD`); supplying it under
  `resume` too (in `MM/YYYY`) double-counts the recent job because dedup can't match the
  differing date formats.
- 1 PDL credit per successful match. `PDL_MIN_LIKELIHOOD=6` (PDL's precision default).

**Migration:** `candidate_job_details.linkedin_data JSONB` — DB-Scripts
`LinkedIn Enrichment (PeopleDataLabs)/001_add_linkedin_data_column.sql`. Applied UAT
2026-06-24; PROD pending.

---

## Key Environment Variables

| Variable | Purpose |
|----------|--------|
| `POSTGRES_URL` | Main DB (with `?options=-csearch_path=candidate_ingestion_schema`) |
| `POSTGRES_ASSESSMENT_SCORE_URL` | Assessment DB connection |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | OpenAI config (default: gpt-4o-mini) |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Gemini config — **primary** normalization model (default `gemini-2.5-flash-lite`; PROD still `gemini-3-flash-preview`) |
| `NORMALIZATION_COMPACT_PROMPT` | Use compact `SYSTEM_PROMPT_V2` (default `true`); `false` = legacy `SYSTEM_PROMPT` |
| `AI_BATCH_SIZE` / `API_INGEST_BATCH_SIZE` | Main-worker / api-ingest claim batch sizes (PROD 100 / 20) |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | SA JSON path. **UAT: `./auth_creds.json`** (baked); **PROD: `/app/secrets/auth_creds.json`** (Secret `data-normalization-sa`). Both = pluginalex SA. |
| `GOOGLE_DRIVE_FOLDER_ID` | Drive folder. **UAT: `1OJ2sGcz85VmGk2fHkg3XALW5nX5M06Ug`** · **PROD: `1vnv0vCwqPnAU_I3afaW7zRn3ge8QLNtG`** |
| `GOOGLE_DRIVE_WEBHOOK_URL` | Webhook receiver URL (UAT/PROD Let's Encrypt; ngrok local-dev only) |
| `PDF_PARSER_URL` / `PDF_PARSER_AUTH_KEY` | Resume parser endpoint |
| `PDL_ENABLED` / `PDL_API_KEY` | PeopleDataLabs LinkedIn enrichment master switch (default `false`) + API key. **UAT: enabled Jun 2026.** See "LinkedIn enrichment". |
| `PDL_API_BASE_URL` / `PDL_MIN_LIKELIHOOD` / `PDL_TIMEOUT_SECONDS` | PDL host (`https://api.peopledatalabs.com`), match-confidence floor (default `6`), HTTP timeout (default `30`s) |
| `ENTITY_NORMALIZER_API_URL` | PG Vector Search endpoint |
| `API_SECRET_KEY` | Auth key for `/api/api-ingest` endpoints |
| `APP_ENV` | `local` / `uat` / `prod` |
| `SEMANTIC_ROLE_SEARCH_ENABLED` | Enable the `role_search` semantic role filter (default `false`; `true` on UAT/DEV) |
| `ROLE_VECTOR_DB_URL` | pgvector store of role-title embeddings (UAT/DEV: `postgres@172.17.0.1:5460/roleproto` — the `role-vec-proto` container via the docker bridge gateway) |
| `ROLE_VECTOR_TOP_K` / `ROLE_VECTOR_THRESHOLD` | Expansion cap (default 50) and min cosine similarity (default 0.66) |

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

> To change `GEMINI_MODEL` / `NORMALIZATION_COMPACT_PROMPT` etc. on UAT you must **recreate**
> the containers with the new value (OS env overrides the baked `/app/.env`); editing `.env`
> alone does nothing for already-running containers.

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
python main.py api_ingest_worker   # Drain the API-ingest queue
python main.py ingest_parallel     # Parallel multi-file ingestion
```

---

## Cost optimization — compact prompt + Gemini 2.5 Flash-Lite (2026-06-19)

Per-candidate Gemini spend was dominated by the **input side**: the ~15.3K-token rules
block in `SYSTEM_PROMPT` was billed on (almost) every normalization call.

**Changes:**
- **Model → `gemini-2.5-flash-lite`** ($0.10/M input, $0.40/M output), set via `GEMINI_MODEL`.
- **`SYSTEM_PROMPT_V2`** — the rules block rewritten from ~15.3K → ~1K tokens while keeping
  the **identical flat slug-keyed output contract** (output is still stored in `open_ai_logs` →
  re-read via `get_normalized_data_from_candidate_job_details` → matched → mapped by
  `map_to_final_schema`, all unchanged). Hard-won rules preserved: phone/country-code strip,
  education-prefixed location exclusion (e.g. "UG City" → `education_ug_city`, never `current_*`),
  highest-qualification ug/pg coercion, internship-vs-work separation, work dedup, duplicate-field
  first-wins.
- **Toggle:** `NORMALIZATION_COMPACT_PROMPT` (default `true`). Set `false` to fall back to the
  legacy `SYSTEM_PROMPT` instantly without a redeploy.

**Measured (same candidate, gemini-2.5-flash-lite):** legacy 56K-char prompt ≈ 16.7K in / 500 out
≈ **0.19¢**; compact ≈ 4.7K in / 444 out ≈ **0.064¢** → **~69% cheaper** per normalization call.
Validated end-to-end on UAT: 10 students via `/api/api-ingest/ingest`, 10/10 created, 0 failures,
total token cost **$0.0077** ($0.000773/student).

**Important env note:** all three containers (`datanormalization`, `datanormalization-worker`,
`datanormalization-cron`) bake env via `-e`/`--env-file` at `docker run` (no env-file mount), and an
OS env `GEMINI_MODEL` **overrides** the `.env` file and the `settings.py` default. To change the model
you must **recreate the containers** with the new `GEMINI_MODEL`, not just edit `.env`.

> A literal "LLM emits the create-full payload directly" was evaluated and deferred: the flat output
> is slug-coupled across storage, re-read, structured logging, matchers, and mapping, so emitting the
> nested payload would require rewriting all of those. The entire cost win lives on the input side,
> which the compact prompt already captures.

---

## Matcher latency — per-candidate memoization (2026-06-19)

Profiling one candidate showed the create path is **matcher-bound, not LLM-bound**:
~68s of which the LLM is only ~5s and `create-full` is ~0.4s — the rest is **~9 sequential
5–10s HTTP calls** to the entity-normalizer (`pg-vector-api-service`) for
institute/degree/city/state/country/department.

Several of those calls resolve **identical text**: `highest_qualification_degree` equals the
selected level's `education_ug/pg_degree`, the highest-qual department equals the UG/PG
department, and current/permanent city or country often coincide. The three
`_call_*_normalizer_api` helpers in `_resolve_and_store_all_ids` were renamed to `*_impl`
and wrapped with thin **per-candidate memoizing wrappers** keyed by
`(entity_type, normalized_input)`. The matcher is deterministic, so identical input →
identical output — behaviour-preserving; only redundant round-trips are skipped. Call sites
are unchanged.

**Measured (UAT, 5 candidates):** matcher API calls **~9 → 6 per candidate (~33% fewer)**;
wall-clock ~21s → ~14s per student; 5/5 still created successfully, 0 failures.

> The remaining latency is the **serial** nature of the independent lookups + the
> 5–10s/call service latency. Bigger wins are **horizontal**: scale
> `form-data-normalization-worker` replicas (the `FOR UPDATE SKIP LOCKED` claim already
> hands disjoint batches to each pod) and scale `pg-vector-api-service` (currently **1
> replica** in PROD, the real bottleneck). PROD worker is also **1 replica** today, so
> normalization runs single-threaded. A full in-candidate concurrent (`asyncio.gather`)
> rewrite of the matcher blocks is the next code-side step but needs dedicated test coverage.

---

## Cost incident — gemini-3-flash-preview thinking runaway via LiteLLM (2026-06-24)

70 candidates uploaded to UAT cost **~₹1.5k (~$18)** — ~330× expected. Root cause chain
(diagnosed from LiteLLM `LiteLLM_SpendLogs`):

1. The **ai-gateway** work routed normalization LLM calls through the LiteLLM proxy
   (`LITELLM_PROXY_URL` + `LITELLM_VIRTUAL_KEY` set → `normalization_service._litellm=True`,
   calls go via the OpenAI-compatible `_call_openai_sync` instead of `gemini_client`).
2. `GEMINI_MODEL` was **reverted to `gemini-3-flash-preview`** (a *thinking* model).
3. Via the OpenAI-compatible proxy the **native `thinkingConfig` is dropped**, so the model
   spent its whole `max_tokens` budget on reasoning: **~13,400 output tokens/call, capped at
   16,370** (= `GEMINI_MAX_OUTPUT_TOKENS=16384`) → **~$0.05/call**.
4. Thinking truncated the JSON before the answer → "Invalid JSON from AI" → the **3× retry
   loop** fired → 3× the already-expensive calls. (The earlier "fix" — *raising* max_tokens —
   made it worse.) LiteLLM spend: `gemini-3-flash-preview` 383 calls = **$15.89**.

**Fix (code, default):**
- `settings.GEMINI_MODEL` default → **`gemini-2.5-flash`** (Development `1eb980c`, merged to UAT).
- `settings.GEMINI_MAX_OUTPUT_TOKENS` 16384 → **8192** (JSON is ~0.5–2K tokens; caps blast radius).
- `_call_openai_sync` sends **`reasoning_effort="disable"` for Gemini models** on the LiteLLM
  path (UAT `5d6a8b8`). Verified against the UAT proxy: output **61→19** tokens, no error;
  LiteLLM maps it to `thinkingBudget=0`. (gpt-4o-mini path is unaffected — guarded on `"gemini" in model`.)

**Measured after fix (UAT):** model `gemini-2.5-flash`, output **~13.4K → ~1.9K avg/call** (max
bounded 8192, no 16K cap-hits), **~$0.05 → ~$0.0058/call (~9× cheaper)**, and **0 "Invalid JSON"
retries** — the tell-tale that thinking is now off.

> **Env gotcha (again):** `GEMINI_MODEL` is set per-container via `docker run -e`; recreate the
> 3 UAT containers with the new model — editing `.env`/code default alone won't change a running
> container. Keep `LITELLM_PROXY_URL`/`LITELLM_VIRTUAL_KEY` so the gateway routing stays.
> DEV (Development branch) has **no** LiteLLM routing — it uses `gemini_client` directly, which
> already sets `thinkingConfig.thinkingBudget=0`, so DEV only needed the model switch.
