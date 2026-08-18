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

⚠️ **`deploy.sh` only builds/runs `datanormalization`** — it does *not* recreate the `-worker`/`-cron` siblings, and rebuilding the image does not restart them. After any redeploy, recreate the two siblings manually (or add them to `deploy.sh`). **This bites hardest on worker-only changes** (`workers/normalization_worker.py`): `auto_deploy.sh` reports success, the API container is new, and the normalization logic is still running the old code. Always check `docker ps` — if `-worker`/`-cron` show an older `Up …` than `datanormalization`, they were not rolled.

**Tag drift (resolved 2026-08-05):** the siblings historically ran a separate **`datanormalization:api-mastersrc`** tag while `deploy.sh` builds `datanormalization:api`, so a plain redeploy left them on a stale image even after a manual `docker restart`. As of 2026-08-05 all three UAT containers run **`datanormalization:api`**. Recreate them from that tag:
```bash
cd ~/api/form-data-normalization
for m in worker cron; do
  docker rm -f datanormalization-$m
  docker run -itd --name datanormalization-$m --restart unless-stopped --env-file .env \
    --log-opt tag='service_name={{.Name}}' --log-opt max-size=100m --log-opt max-file=3 \
    datanormalization:api python main.py $m
done
```
Expect `No pending sheets found.` (worker) and `Scheduler started` (cron) in the logs. Code + SA key are **baked into the image** (`COPY . /app`), so config/key changes require an image rebuild, not just an `.env` edit. The runtime config (batch sizes, model, normalizer URL) is read from the baked `/app/.env`, but OS env vars set via `docker run -e`/`--env-file` **override** it.

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

**Candidate-level duplicate skip (`ALLOW_DUPLICATE_CANDIDATES`):** by default the worker marks a row `normalization_status = 'skipped'` (reason `duplicate_candidate`) when `is_candidate_duplicate(email, mobile, role_id)` finds the same email/mobile already exists for that role — both the `##NO##` path and the normal path. Setting **`ALLOW_DUPLICATE_CANDIDATES=true`** (`config/settings.py`, default `False`) disables that pre-check in both paths **and** short-circuits the `get_candidate_id_without_role` reuse lookup (forcing `existing_candidate_id = None`), so every duplicate submission flows to `insert_candidate_new` (which does **no** dedup) → **fresh candidate row** → `insert_candidate_job_details` (new `(candidate_id, role)` mapping) → `create-full`. student-node dedups on its side (`"Student already exists. Job role mapping created successfully."`), so no broken student records. **Why the reuse lookup must also be gated:** `get_candidate_id_without_role` despite its name matches on **email only** (the role param is unused in its SQL), so with just the pre-check removed a true duplicate returned the existing candidate, entered the `if existing_candidate_id:` branch, `insert_candidate_job_details` returned `None` (mapping exists), and the role-mapping sub-block referenced an **unbound `candidate_id`** → `UnboundLocalError` → rows went to **`failed`** (not skipped). Fixed 2026-07-03 by (a) gating the reuse lookup behind the flag and (b) correcting that sub-block to use `existing_candidate_id`. **Forward-only:** rows already marked `skipped` stay skipped — reset them to `pending` to re-normalize. **Current UAT state: `ALLOW_DUPLICATE_CANDIDATES=true`** (baked into `datanormalization:api` via `.env`, requested 2026-07-03 to stop dropping duplicate candidates). Empty-string env coerces to `False` via the shared `_coerce_empty_bool` validator. Flip to `false` + rebuild to restore duplicate suppression.

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

**Degree / Department filter options = the ACTIVE master, matched by id OR text**
— *UAT + DEV, 2026-07-31.* `GET /api/student-metrics/degrees` and `/departments`
return `SELECT DISTINCT TRIM(name) FROM institute.degrees|streams WHERE status = 1`
(`services/db_service.py` → `fetch_distinct_degrees` / `fetch_distinct_departments`) —
i.e. exactly the list the admin **System Config → Institute Settings → Degree** screen
shows. Dropdown size: **PROD 297 degrees / 1849 streams; UAT 324 / 772.**

History — this flipped twice, so read the whole note before changing it again:

1. Originally the master filtered to `status = 1`, but the list filter matched only
   `LOWER(TRIM(current_course.degree))`, so selecting a master name returned nothing
   for candidates whose text had drifted.
2. *2026-07-29* it was changed to source from `student.current_course` (candidate
   free-text). That guaranteed every option returned ≥1 row, but exposed **~2200
   distinct spellings** on PROD — `Bachelor of Engineering (B.E)`,
   `B.E (Bachelor of Engineering)`, `Bachelor of Engineering - Chemical`, … — where
   the master holds one curated `Bachelor Of Engineering`. Unusable as a filter list.
3. *2026-07-31* back to the ACTIVE master, **but the filter predicate was fixed at the
   same time** so option (1)'s failure mode can't recur. `degree`/`department` now match
   the raw text **OR** the linked master's name:

```sql
EXISTS (SELECT 1 FROM student.current_course cc
        LEFT JOIN institute.degrees d ON d.id = cc.degree_id
        WHERE cc.student_id = s.id
          AND (LOWER(TRIM(cc.degree)) IN (:names) OR LOWER(TRIM(d.name)) IN (:names)))
```

**Why the OR is load-bearing:** on PROD 68% of `current_course` rows carry a `degree_id`
resolving to an ACTIVE master, and **8% of those have drifted from the master's name**.
Selecting `Bachelor Of Engineering` returns **14,847** candidates with id-or-text vs
**11,263** with text alone — a name-only match silently drops 3,584 people. Never
revert the predicate to text-only while the options come from the master.

4. *2026-08-04* the OR still let through rows whose `degree_id` links to an **inactive**
   or otherwise-null master purely on text — i.e. the id-or-text OR was never actually
   requiring the id side to be active. Added `AND d.status = 1` inside the `EXISTS`
   (both the list and single-value branches) so a match now requires the *resolved*
   master to be active, not just a text/name string coincidence:

```sql
EXISTS (SELECT 1 FROM student.current_course cc
        LEFT JOIN institute.degrees d ON d.id = cc.degree_id
        WHERE cc.student_id = s.id
          AND (LOWER(TRIM(cc.degree)) IN (:names) OR LOWER(TRIM(d.name)) IN (:names))
          AND d.status = 1)
```

   Net effect on UAT for `degree=BACHELOR OF ENGINEERING`: **1099 → 1042** — the 57
   dropped candidates all had `current_course.degree_id` NULL/unlinked (text matched,
   but there was no master row to be active in the first place). Verified against the
   admin-node `/meta-dashboard/students` case-sensitive-exact-`cc.degree_id` query,
   which independently returns the same **1042** for the active `BACHELOR OF ENGINEERING`
   master id (`69c5559d-3145-4c1e-8107-1b6d2625a745` on UAT). Shared by both
   `GET /api/student-metrics` and `POST /api/student-metrics/download` since both go
   through `_build_student_filter_clause`. Deployed DEV + UAT same day
   (`services/db_service.py`, commit `4d60f34` merged Development → UAT as `5498e8f`).

Search collapses runs of whitespace (`regexp_replace(..., '\s+', ' ', 'g')`) because some
master rows carry a stray double space — `BACHELOR OF  ENGINEERING TCS` is invisible to a
plain `LIKE '%bachelor of engin%'` even though the master screen's fuzzy search-service
finds it.

**Consequence — junk in the ACTIVE master is now visible in Analytics.** Page 1 of the UAT
degree dropdown currently shows `1. TEDxYouth@PalmRoad (07/2018-11/2018)` and
`ANNA UNNIVERSITY`. These are real active master rows minted by the self-appending
behaviour below; they carry letters so the write-time guard does not reject them (the
documented college-name gap). Fix them by deactivating in the Degree master screen —
**not** by changing this endpoint.

admin-react `CandidateMetricDetails/CandidateMetricMain.js` (`fetchDegrees`/`fetchDepts`)
calls these via `candidateRequest`, matching how Cities/States/Roles on the same page
already work.

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
| **Resume Parser** (`resume-parser.uat.pluginlive.com`, container `resumeparser`) — ⚠️ **CV parsing moved into `fastapi-ai-engine` on 2026-08-17** (`POST /cv-parser/parseResume`); this standalone service still runs and this row still describes it, but `student-node` now calls the engine. See `Infrastructure/document-parsers.md`. | PDF CV parsing via Gemini. As of 2026-06-29 its `generate_content` calls are **routed through the LiteLLM gateway** (`LITELLM_PROXY_URL`+`LITELLM_VIRTUAL_KEY`, shim `USING API/gateway_client.py`). Fixes the **"CV Parse Error: HTTP 500 … google.genai.errors.ClientError: 401 UNAUTHENTICATED / ACCESS_TOKEN_TYPE_UNSUPPORTED"** seen in the normalization UI, caused by the `AQ.…`-format Gemini key failing through the raw google-genai SDK. See `Infrastructure/ai-gateway.md`. **Supported CV formats:** PDF (PyMuPDF), `.docx` (docx2txt), and as of 2026-06-30 legacy `.doc` (OLE2, magic `\xd0\xcf\x11\xe0`) via **`antiword`** — `extract_text_from_bytes` / `fetch_document_content` route OLE2 bytes to `extract_doc_text` (shells out to antiword). Google Drive `.doc`/`.docx`/`.pdf` resumes are downloaded with the `pluginalex` service account (`auth_creds.json`, share files with `pluginliveservice@pluginalex.iam.gserviceaccount.com`); anything else → `ValueError: Unsupported file format`. **Deploy note:** `antiword` is installed via an `apt-get` line in the **UAT box's** `Dockerfile` (added before `COPY`), which is intentionally divergent from git (git Dockerfile bakes a dead key; the UAT copy bakes the `AQ.` key + antiword). Rebuild = `cd ~/api/Resume_parser/"USING API" && docker build -t resumeparser:api .`; recreate with the gateway `-e` env. |
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

### Behavior — candidate name mapping & single-`Name`-column fallback (Jul 2026)

`map_to_final_schema` builds `admin.firstName`/`admin.lastName` from the
`normalized_columns` mapping table, where **`first_name → admin.firstName`** and
**`last_name → admin.lastName`**. The `full_name` slug exists but has a **NULL
`mapping_field`** — it is deliberately not mapped into the payload.

**The gap this created:** source sheets that expose a single **`Name`** column
(e.g. assessment-result exports like *"amazon aws - …"* whose rows are
`{Name, Email, Total Score, CEFR Level, …}`) get mapped by the LLM to
**`full_name` only** — no `first_name`/`last_name`. Because `full_name` maps to
nothing, `admin.firstName`/`lastName` went out **empty**, so student-node created
the student with a **blank name** (blank `first_name`/`last_name`/`full_name` in
`student.students`). The Candidate-Metrics UI (admin-react `CandidateMetricDetails`,
served by this service's `/api/student-metrics/*`) renders
`full_name || first_name+last_name || '-'`, so those students showed **no name**.
An earlier fix (`##NO##` name fallback, commit `9f3a3d0`, 2026-05-21) covered
**only the `##NO##` no-normalization path**, so the LLM path stayed broken.

**Fix (2026-07-06, UAT `2ad2191`):** `map_to_final_schema` now backfills at the
top — when **both** `first_name` and `last_name` are blank (no alpha chars), it
seeds `first_name` from `normalized_data['full_name']`, else from a raw
`Name`-like column (`name`, `full name`, `candidate name`, `student name`,
`applicant name`, …), leaving `last_name` empty. The existing
`first_name → admin.firstName` mapping then carries it into the payload. Guarded
on both-blank so a valid first/last is **never** overwritten; runs on **both**
paths. **Forward-only:** the ~349 already-created blank-name students
(2026-02-10 → 2026-06-15) are unaffected — they need a one-off backfill from
`candidate_job_details.normalized_data.full_name` into `student.students`.

**Follow-up (2026-08-05, DEV + UAT `b6f1b05`) — the fallback ran too late.** It
lived *inside* `map_to_final_schema`, which runs **after**
`insert_candidate_job_details`, and it mutates the flat dict used to build the
payload — **not** the `normalized_data` list that gets stored. So the seeded
`first_name` reached the create-full payload only; the persisted
`candidate_job_details.normalized_data` still had `full_name` and **no
`first_name`/`last_name` key at all**. That is invisible while the push succeeds,
but any candidate that *fails* the push stays in **Mismatched Candidates**, and
that list (`CandidateService.get_candidates`) builds its display name as
`first_name + ' ' + last_name`, falling back to `candidates.name` — so those rows
render **`-`** in the CANDIDATE column and **`N/A`** in the drawer header, even
though the drawer's Normalized Data panel shows the name. The list's **search
clause matches `first_name`/`last_name`/concat/`email` but never `full_name`**, so
those candidates were also **unfindable by name**.

⚠️ The `candidates.name` fallback is **dead** — `insert_candidate_new` is called
with `name=normalized.get("name")` and the normalizer never emits a `name` slug
(only `full_name`/`first_name`/`last_name`). On PROD `candidates.name` is NULL for
**all 52,149 rows**. Do not rely on it; the display name comes from
`normalized_data` alone.

**Fix:** the fallback is now the reusable
`NormalizationWorker._seed_first_name_from_full_name(normalized_data, raw_data)`
(same both-blank guard, same `full_name` → raw-`Name`-column precedence), called
in `_process_single_candidate` **before** the insert — after the CV name-fill and
before the duplicate check, a single point covering both the existing-candidate
and new-candidate insert branches. `map_to_final_schema` keeps its call as a
payload-side safety net for the other callers. **Forward-only:** existing rows
keep their empty `normalized_data`; re-normalize (`normalization_status='pending'`)
to repair them.

### Behavior — `create-full` is skipped when `admin.email` is missing (Aug 2026)

student-node's create-full schema (`app/schemas/student.js`, `CreateFullStudentBodySchema`)
declares `admin.email` as **required with `format: "email"`**, so a blank or
malformed email is a **guaranteed 400**:

```
{"statusCode":400,"code":"FST_ERR_VALIDATION","error":"Bad Request",
 "message":"body/admin/email must match format \"email\""}
```

**Institute-ERP sheets are the common trigger** — an ERP export with **no Email
and no Mobile column at all** (only Full Name / Age / Gender / education / work
experience) normalizes fine, then 400s on **every** row. The candidates land in
Mismatched Candidates with `api_status='api_failed'`, `student_id` NULL, and the
drawer showed the raw Fastify blob, which reads like a platform bug rather than
missing source data. Observed on PROD 2026-07-27 (sheet
`3dd3f65d-…-196630e5c909_1785132809.xlsx`, campus `3dd3f65d-…`, all 3 rows).

**Fix (2026-08-05, DEV + UAT `b6f1b05`):** `NormalizationWorker.create_full_student`
now short-circuits **before** the HTTP call when `admin.email` is absent, blank,
has no `@`, or contains whitespace, returning

```
Skipped create-full — admin.email is missing or malformed ('');
also blank: phoneNumber, countryCode.
The source record has no usable email; add one and push again.
```

with `error_type='MissingMandatoryField'`. All three call sites already treat
`status: False` as `api_failed` + a `create_full_student_response` WARNING log, so
this string is what the drawer's "API Failed / RESPONSE" box shows — no call-site
changes were needed. The check is **deliberately permissive** (present, has `@`,
no whitespace) rather than a strict regex: AJV's `format: "email"` accepts values
like `user@localhost`, so anything ambiguous still goes to student-node, which
stays the source of truth on format. `firstName`/`phoneNumber`/`countryCode` are
**reported** in the message but **not blocked on** — the schema has no `minLength`
on them, so `""` currently passes validation and blocking would change behavior
for existing rows. This replaces the long-commented-out `mandatory_fields` block.

**This does not rescue affected candidates** — with no email anywhere in the
source there is nothing to push. Fill the email via the drawer's Edit → Push to
API, or re-upload the ERP sheet with Email/Mobile columns. Regression checks:
`tests/test_missing_email_and_name_fallback.py` (runs standalone, no DB/LLM).

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
  `educationLevel` **plus** degree/institutionName, each existing row claimed once — a
  level can legitimately hold two rows, e.g. a finished PG and one being pursued)
  + `currentCourse` + `resume` (the last two only when present in
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
- **Gotcha (fixed Jun 2026):** the existing-student update reuses `Student.update`, which
  does **nested Prisma writes** into `student` / `currentCourse` / `resume`. The create-full
  payload's `resume` is the **CV-parser object** (`admin`, `education[]`, `student`,
  `currentCourse`, `studentPersonalProfile`, `workExperience`…), almost none of which are
  columns on the `resume` model. Passing it raw makes Prisma reject the call —
  `Unknown argument 'admin'`, and the union resolver then falls back to
  `studentPersonalProfileUncheckedUpdateInput` and rejects the `student` relation
  (`Failed to update`). The **create** path already guards this with a resume whitelist
  (`ALLOWED_RESUME_FIELDS` → `objective/projects/internships/courses/training/awards/workExperience`)
  + skill-row sanitize; the update path must do the **same** (extracted to
  `sanitizeResumeForPersist`) and also `_.omit` non-column keys from `student`
  (`email`/`phoneNumber`/`countryCode`/`studentId`/`journey`/…, the keys `Student.create`
  omits). The old corporate-lead-only update path never hit this because those leads carry
  no `resume`/`currentCourse`.

### Behavior — academic masters are self-appending; implausible names are now rejected (2026-07-29)

`institute.degrees` and `institute.streams` are **self-appending**. Combined with
`activate: true` above, this means: any degree/department string a candidate record
carries with **no master id** becomes a **live** row in the master that feeds every
degree/department picker on the platform.

Candidate sheets routinely put the wrong value under a degree column. Traced on PROD:
ingest row `289e2d0b` carried `"PG Degree": "81.0%"` (the recruiter typed the PG
**marks** into the degree column). The degree matcher can't match that, its no-match
path deliberately keeps the ORIGINAL value, and `create-full` then minted `81.0%` as an
**active degree**. When found, PROD held **4454 degrees / only 297 active / 4243
carrying a `student_id`**, including marks, CGPA, years of passing, roll numbers and
Google Drive links.

**The guard now exists in THREE places — keep them in sync:**

| Where | What |
|---|---|
| `institute-node` `app/helpers/masterNameGuard.js` | `isPlausibleMasterName()`, enforced in `degreeHandler.createDegreeForStudentsOthers` for degree/stream/specialisation, on both create **and** rename |
| `form-data-normalization` `workers/normalization_worker.py` | `_is_plausible_academic_name()` + a deterministic scrub in `map_to_final_schema` that blanks implausible `education_<level>_degree/_department` and `highest_qualification_degree/_department` |
| `institute.is_implausible_academic_name(text)` | SQL, for cleanup/reporting (DB-Scripts `Academic Master Data Hygiene/`) |

Rule — **conservative by design**: rejects only values that *cannot* be an academic
name — no letter at all (`0.81`, `7.44`, `2019`, `523281`, `10+2`, `---`), marks with a
unit (`81.0%`, `80 %`, `8.5 CGPA`), a ratio (`8.5/10`, `450 out of 500`), a URL, an
email, or `<2` / `>120` chars. Back-tested against all 4454 PROD degree names: **97
rejected, zero false positives.**

- institute-node returns a rejected value as `{ dataType: "REJECTED", name }` with **no
  `id`**. Both callers already branch on `.id`, so they no-op safely — the candidate
  keeps the raw text on their profile, it just never becomes a master row.
- FDN blanks the value so the mapping loop (which skips `""`) omits the field —
  an honestly-empty degree instead of a wrong one. The raw sheet value survives in
  `result["rawJson"]` and in the `create_full_student_request` log.
- **Not caught:** college names typed into degree columns (`Sri Mittapalli College Of
  Engineering`, `Kristu Jayanti College`). They're real words; separating those from
  degrees is the semantic matcher's job, not a syntactic guard's.

**Cleanup scripts** live in DB-Scripts `Academic Master Data Hygiene/`:

- `20260729T050158Z__deactivate_implausible_degree_stream_masters.sql` — records each
  row's previous status in a new `institute.master_name_cleanup_audit` table, then flips
  junk `status 1 → 0`. **Nothing is deleted**, so `current_course` references and the
  candidate's raw text survive; rollback SQL is in the file. Idempotent.
  *DEV + UAT applied (UAT retired 1 stream, `"2222321"`); PROD pending (12 active
  degrees, 0 active streams).*
- `20260729T053000Z__requeue_candidates_with_implausible_degree.sql` — finds candidates
  whose `current_course.degree/department` is implausible and re-queues their ingest rows
  (`normalization_status='pending'`) so the corrected pipeline rewrites them in place
  (create-full **updates** an existing student — see the section above). **Section 2 is
  operator-initiated and left commented out**: it makes the worker re-call the LLM
  providers per row and rewrites live candidate records. *UAT: function + review applied,
  38 affected candidates all linkable to an ingest row; PROD pending, 129 affected /
  123 linkable.*

> **Order matters:** deploy the guards **before** running the cleanup, or the tables
> re-pollute within days. The re-queue script is a **no-op until the FDN guard is
> deployed** — without it the pipeline re-derives the same junk from the same column.

### Behavior — `currentCourse.domainId`/`domain` now derived from the degree master (2026-07-31)

ERP/normalization `create-full` payloads only ever resolved `currentCourse.degreeId`
+ `streamId` (`workers/normalization_worker.py` has no domain concept at all), so
`current_course.domain_id` stayed **NULL** for every ERP-sourced student. That silently
dropped them from every domain-scoped screen: the students-list / batch-folder / report
filters AND `domainId` together with `degreeId`/`streamId`
(`student-node app/models/Student.js`, `getStudentPlacementCounts`), so a course row with
a correct degree+stream but no domain is excluded the instant a TPO picks a domain — the
first filter step on all three screens. Confirmed on DEV: 17,429 `current_course` rows had
`domain_id IS NULL`, of which 9,757 had a resolvable `degreeId` (100% resolvable, 0
orphans) — mostly MANAGEMENT (8,586), ENGINEERING (383), SCIENCE (281).

Domain hangs off the degree master (`institute.degrees."domainId"` → `institute.domains`),
one degree carries exactly one domain, so it's fully derivable from `degreeId` alone —
same source the CSV bulk-upload path already reads (`common.js` builds `currentCourse`
from `instituteCourseData.degreeStreamMap.degree.domain`), just not wired for create-full.

Fix (`student-node app/handlers/common.js`, `Development`/`UAT` `2d2ac7c7`):

- New `app/helpers/courseDomain.js` → `getDomainLookupDegreeId(course)` picks the degree id
  to resolve the domain from: `course.degreeId`, or `course.otherDegreeId` when
  `degreeId === "OTHERS"` (the pending-master sentinel — same `institute.degrees` table,
  just `status !== 1`). Returns `null` (skip) when the course already has a `domainId`, or
  has no degree at all.
- `materializeMissingMasterIds` gained `ensureDomain(currentCourse)`, called right after
  `ensureDegreeStream(currentCourse)` so a degree minted in the same request is covered too.
  One `institute.degrees JOIN institute.domains` read, sets both `domainId` and `domain`
  (the name) — best-effort like its sibling `ensure*` helpers, never blocks student
  creation.
- **`currentCourse` only** — `education[]` rows are untouched; the domain-scoped filters
  read `current_course`, not `education_profile`.
- The existing ERP canonical-or-NULL guard (drops `degreeId`/`streamId` when only one of
  the pair resolved) now also drops `domainId`/`domain` in that case, so a course never
  persists a domain it can no longer be traced back to.

**No backfill was run** — this only fixes the write path going forward. The 17,429
existing NULL-domain rows on DEV (and UAT/PROD equivalents) are still NULL.

### Behavior — arrears reach `currentCourse` from BOTH slug families (2026-08-03)

Institute-ERP bulk uploads always sent `currentCourse.noOfArrears` /
`historyOfArrears` as **0**, whatever the sheet's "Current Arrears" /
"History of Arrears" columns said.

Root cause is a **duplicate slug registration** in
`candidate_ingestion_schema.normalized_columns` — arrears exist under two
competing *active* families, and only one is mapped:

| slug | `mapping_field` |
|---|---|
| `pg_current_arrears_count` / `pg_past_arrears_count` (and `ug_`, `diploma_`, `iti_`, `puc_`, `phd_`, `pd_`, `p_g_diploma_`) | `education_pg.currentArrearsCount` / `…pastArrearsCount` |
| `education_pg_current_arrears_count` / `education_pg_past_arrears_count` (also `education_diploma_*`, `education_p_g_diploma_*`) | **NULL** |

`map_to_final_schema` only ever read the bare `<level>_*_arrears_count` family.
On an ERP sheet the LLM picks the **`education_<level>_*`** variant instead —
"PG Current Arrears" sits alongside every other `education_pg_*` header
(`education_pg_degree`, `education_pg_marks`, …), so that naming wins — and the
`education_<level>_<field>` regex grouping then swallows it into `education_map`
where nothing consumed it. The value was silently dropped in both places that
read arrears: `currentCourse` and each `education[]` record.

Fix (`workers/normalization_worker.py`, Development `edb00ac` → UAT `f6e9abc`,
deployed 2026-08-03; **PROD pending**): one `arrears_for_level(level)` resolver
that reads `<level>_<kind>_arrears_count` first and
`education_<level>_<kind>_arrears_count` second, used for `currentCourse` and for
each `education[]` row. It also replaced the four duplicated per-level lookups in
the `highest_qualification_level` if/elif chain.

Verified by replaying `map_to_final_schema` against the captured
`normalized_data` of a failing ERP row (sheet: current 0 / history 2 → payload
was 0 / 0, now 0 / 2). Regression test:
`tests/test_arrears_slug_families.py` (both families + zero-arrears default) —
`docker exec datanormalization python -m unittest discover -s tests`.

Two related quirks worth knowing:

- `pg_current_arrears_count`'s `mapping_field` (`education_pg.currentArrearsCount`)
  is a **pseudo-path** — no such key exists in create-full, so `set_nested` writes a
  junk top-level `payload.education_pg` object (43 UAT payloads since May 2026).
  Harmless (student-node ignores it) and *not* how `currentCourse` gets its values —
  the direct lookup is what counts — but it is dead config.
- `education[]` records carry **`historyOfArrears` only**; student-node's create-full
  schema has no `noOfArrears` on education rows. Current arrears live on
  `currentCourse` alone.
- `currentCourse` is dropped entirely by the "no meaningful value" prune when every
  field is falsy (`0`/`""`), then partially rebuilt by the `set_nested` mapping pass —
  so a candidate with zero arrears *and* no resolved `degreeId` legitimately ships a
  `currentCourse` without the arrears keys. student-node's schema defaults both to 0.

### Behavior — ERP `currentCourse` carries the CAMPUS city/state (2026-08-03)

Institute-ERP bulk uploads never sent `currentCourse.city` / `cityId` / `state` /
`stateId`, so every ERP-created student's current course landed with a blank
location. An ERP sheet has no college-address column, so there was nothing in the
normalized slugs to map — but the student demonstrably studies at the **campus that
uploaded the sheet**, whose location is already known server-side
(`institute.institutes_campuses.city / city_id / state / state_id`).

Fix (`services/db_service.py` + `workers/normalization_worker.py`, Development
`c90e11c` → UAT `5d90f9e`, deployed 2026-08-03; **PROD pending**):

- New `DBService.get_campus_location(campus_id)` reads the campus row. `city_id` /
  `state_id` are **nullable** on `institutes_campuses` (23,132 UAT campuses have a
  city name but no `city_id`), so it falls back to a name lookup against
  `admin.mongo_db_cities` / `mongo_db_states` — the same masters the student profile
  UI writes.
- `_apply_institute_erp_overrides()` (now `async`, all three call sites `await`) fills
  the four `currentCourse` fields, cached per campus on the worker instance — one
  query per upload, not per row. It uses `setdefault("currentCourse", {})`, so the
  location survives the "no meaningful value" prune that drops an all-empty
  `currentCourse` (student-node creates the row regardless).

Only fields the campus actually has are written: a campus whose city name doesn't
match the city master (e.g. campus `"Ranebennur"` vs master `"Ranibennur"`) ships
`city` and **omits** `cityId` rather than writing an empty string or a wrong id. A
lookup failure logs a warning and never fails the upload.

student-node needed no change — `createFullStudentBodySchema.currentCourse` already
allows all four keys and `Student.create()` spreads `currentCourse` straight into the
Prisma nested create.

**Forward-only:** existing ERP students keep their blank location until re-uploaded.
Regression test `tests/test_erp_campus_location.py` (5 cases: full location, missing-id
omission, absent `currentCourse`, unknown campus, per-upload caching) —
`docker exec datanormalization python -m unittest discover -s tests`.

### Behavior — a postcode column that is really an address no longer kills the student (2026-08-04)

An institute ERP upload of **157 candidates created only 104 students**. All 157 rows
normalized and were reported as **Done / 0 Failed** on the upload status screen; 53
students simply did not exist.

Root cause, two independent defects:

1. **The postcode was built from the whole address.** The address column detector
   matches the word `pincode` / `postcode` / `zip` **in the header**, and these sheets
   name their columns `Current Address (State, City, Pincode)` /
   `Permanent Address (State, City, Pincode)`. So the value handed to the cleaner was
   the entire address, and the cleaner did `re.sub(r"[^0-9]", "", v)` — stripping every
   non-digit and **concatenating**:

   | raw address | old postcode | now |
   |---|---|---|
   | `MAULI, 102.1296, E Ward, … Kolhapur - 416006` | `1021296416006` | `416006` |
   | `Flat no. 2806, SRA Tower, … Mumbai - 400012` | `2806400012` | `400012` |
   | `Mig 161 block 5 sector 6 … road 800026` | `16156800026` | `800026` |

   `student_personal_profile.corr_post_code` / `perm_post_code` are **INT4**. Prisma does
   not reject an over-range value as a field error — it reaches the driver and aborts the
   **entire nested `student.create()`** with
   `ConversionError("Unable to fit integer value '1021296416006' into an INT4")`,
   surfaced to the worker as a generic 400 `"Something went wrong, please try again later."`
   One junk field cost the whole candidate. Correlation was exact: 53/53 failures had a
   postcode > 2147483647, 0/104 successes did.

2. **Failed rows were still marked `completed`.** `mark_completed(raw_data_id, …)` ran
   unconditionally after *both* the success and the `api_failed` branch. The ERP status
   screen (`get_raw_candidates`) counts purely off
   `candidates_raw_data.normalization_status`, so the 53 lost candidates showed as Done
   and Failed could never be non-zero for this class of error. The truth was only in
   `candidate_job_details.api_status = 'api_failed'`, which no screen reads.

Fix (Development `ffd1cbc` → UAT `6bcec11`, deployed 2026-08-04; **PROD pending**):

- New `extract_pincode()` in `services/normalization_service.py` takes the **trailing
  6-digit token** (`\b\d{6}\b`, last match — the PIN comes last in an Indian address),
  falling back to the bare digits only when they are exactly 6 (`560 034`, `560-034`).
  Anything else returns `""` and the caller **omits the field** rather than persisting
  junk. Replaces the digit-concatenating `re.sub` at **all five** postcode call sites
  (the `current_postcode` cleaner plus the explicit and positional 1-col/2-col address
  detectors). A 10-digit phone number has no 6-digit token boundary, so it is rejected.
- The worker only calls `mark_completed` when a student actually came back; otherwise
  `mark_failed`. `failed` is terminal (the claim query takes `pending` / stale
  `in_progress` only), shows under **Failed** on the status screen, and is replayable by
  setting `normalization_status='pending'`.

Checked against the 66 real addresses from the failed batch: **all 66 now yield the
correct PIN, none discarded, 0 remaining INT4 overflows.** Regression test
`tests/test_pincode_extraction.py` (7 cases incl. the exact strings that broke the
upload) — `docker exec datanormalization python -m unittest discover -s tests`.

**Not retroactive:** the 53 rows from the 2026-08-04 UAT batch (campus
`081849b1-7e7f-47bc-9c3a-6053e82f7f88`) are still `completed`-but-studentless. Replay
them by setting their `normalization_status` to `pending`.

> **Deploy note — the fix lives in the WORKER.** `auto_deploy.sh form-data-normalization`
> rebuilds `datanormalization:api` and recreates **only** the api container.
> `datanormalization-worker` / `-cron` run the `datanormalization:api-mastersrc` tag and
> are left on the old image, so normalization behaviour would not change. Always bump all
> three — see *Docker & Deployment* below.

### Gotcha — city/state "mismatch" = entity-normalizer (vector-search) Gemini key invalid

When the normalized-data UI flags **Current City / Current State** red (and `corrCityId` /
`corrStateId` arrive empty in the create-full payload), the cause is usually the
**entity-normalizer** (`vector-search.{dev,uat}.pluginlive.com/api/v1/normalize`, container
`vectorsearch`) returning **500** for `entity_type` city/state. Root cause seen Jun 2026 on
**both DEV and UAT**: the container's `GEMINI_API_KEY` is invalid/expired
(`google.genai ClientError: 400 API_KEY_INVALID`), and the embedding step runs first, so
**every** `/normalize` call dies — city/state/role/department all fail to resolve. Fix is to
**rotate the Gemini key** and recreate the `vectorsearch` container with the new env (env is
baked at build, so recreate with `-e`). `EMBEDDING_PROVIDER=gemini` (model
`gemini-embedding-001`, 1536-dim); the container also has `OPENAI_*` configured, but **do not
just flip `EMBEDDING_PROVIDER` to openai** — the pgvector store is embedded in the Gemini
vector space, so a provider switch needs a full re-embed first.

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
> **Gotcha 4 — internships & projects were dropped from the payload (fixed 2026-07-10, UAT `69bb547`).**
> `map_to_final_schema` only rebuilt `resume.workExperience` (from `work_N_*`/`recent_*`). The
> normalizer also emits `internship_N_*` and `project_N_*`, but nothing mapped them into the
> create-full payload, so ERP internships/projects were silently missing (only appeared if a
> parsed CV/LinkedIn `cv_data` happened to carry them). Fix: two additive blocks mirroring the
> workExperience merge build `resume.internships` (`{role, organization, started_in, ended_in,
> description?, skills?}` from `internship_N_*`) and `resume.projects` (`{title, …}` from
> `project_N_*`), then keep non-duplicate CV entries. Guarded — only set when non-empty, so
> candidates without these columns produce byte-identical payloads. `internships`/`projects`
> are already whitelisted (`ALLOWED_RESUME_FIELDS`) and modeled (`resume.internships/projects
> Json[]`) in student-node.
>
> **Gotcha 5 — university dropped from education[] (fixed 2026-07-13, UAT `c101b1c`).**
> The normalizer only had an `institution_name` (college) slug — no university slug — so a
> "Graduation University" / "Post Graduation University" column had nowhere to map and was
> dropped, even though student-node's `educationProfile` has a `university` column. Fix:
> (a) registered slugs `education_ug_university` + `education_pg_university` in
> `candidate_ingestion_schema.normalized_columns` (mapping_field NULL, like `education_ug_city`),
> (b) prompts (V2 live + V1 + no-norm) map university columns to `education_<level>_university`,
> distinct from the college, (c) `map_to_final_schema`'s `education[]` record now carries
> `"university": data.get("university","")` (+ in has_data). Name-only — `universityId` left
> empty (no university-master matching). **PROD needs the same 2 slug INSERTs** (config table,
> not shipped by code): `INSERT ... education_ug_university / education_pg_university`.
>
> **Gotcha 6 — CGPA won over Percentage when a level had both columns (fixed 2026-07-13, UAT `c101b1c`
> prompt-only, hardened `6e692c6`).** The compact score rule (`SYSTEM_PROMPT_V2`) had no guidance when
> a level exposed BOTH a percentage column and a CGPA/GPA column, so the LLM took CGPA. Added a "PREFER
> PERCENTAGE" prompt rule (V2 + V1). But the LLM still applied CGPA→% conversion **inconsistently**
> (CGPA-only sheets sometimes stored raw `7.9` shown in UI as "7.90%") — hardened with a **deterministic**
> `_cgpa_marks_to_percentage()` in `map_to_final_schema`, run for every education level +
> `highest_qualification_marks` before the mapping loop: CGPA-flagged or bare 0–10 values ×10 (0–1 ×100),
> relabel `cumulative_type=Percentage`. Guarded — values already >10 are only relabelled, never re-scaled.
>
> **Gotcha 7 — Certifications column dropped; now → `resume.courses[]` (fixed 2026-07-13, UAT `6e692c6`).**
> A "Certifications" column often lists several entries ("1. … \n 2. …") with no mapping at all. Prompt
> now splits each into `course_1_title, course_2_title, …` (title only, numbering/trailing-desc stripped);
> worker builds `resume.courses[]` (`{title}`, mirrors the internships/projects blocks) from `course_N_title`
> / `courses_N_title`, keeping non-duplicate CV entries.
>
> **Gotcha 8 — Extra-curricular achievements dropped (fixed 2026-07-13, UAT `6e692c6`).** The
> `extra_curricular` slug existed but had `mapping_field=NULL`. Prompt now maps the "Extra-curricular
> achievements" column (distinct from "Academic achievements") to it; DB `mapping_field` set to
> `studentPersonalProfile.extraCurriculars` (single string field, applied directly to shared UAT DB —
> config data, not shipped by code; **PROD needs the same UPDATE**).
>
> **Gotcha 9 — "Other Degree" (second PG/second qualification) dropped (fixed 2026-07-13, UAT `6e692c6`).**
> A sheet with BOTH "Post Graduation ___" and "Other Degree ___" blocks only kept Post Graduation — Other
> Degree had no level assignment and vanished. Prompt now infers the level from the DEGREE NAME (not
> hardcoded): Bachelor→ug, Master/M.Tech/MBA/MHRD→pg, PhD→phd, PG-Diploma/PGDM→p_g_diploma, Diploma
> →diploma; if that level is already occupied (e.g. `pg` held by Post Graduation), it falls through the
> nearest empty higher-ed slot (`pg → p_g_diploma → pd → phd → diploma`) so both qualifications survive
> as distinct `education[]` blocks. Reuses existing `education_<level>_*` slugs — no new DB rows.
>
> **Address (reference):** both current & permanent address normalize. current_* →
> `studentPersonalProfile.corr*` (corrAddrLine1/corrCity/corrState/corrPostCode/corrCountry, +IDs);
> permanent_* → `perm*`. If current-address fields are blank the worker copies permanent→current.
> The `*_address_city/state/pincode` slug variants are unmapped (NULL) decoys — the canonical
> `current_*`/`permanent_*` slugs carry the data. CV parsing runs whenever a sheet has a
> CV/resume URL column (`Upload CV`, `CV URL`, `Resume URL`, …) → `parse_pdf`; no CV column = no parse.
>
> **Gotcha — current-course SPECIALISATION never populated (fixed 2026-07-17, UAT `f5c72ae`).**
> `spp.current_course.specialisation` / `specialisationId` stayed empty for every candidate. The value
> exists on the education level (`education_pg_specializations` = "Human Resources") but nothing plumbed
> it into `currentCourse` — `map_to_final_schema` never wrote a specialisation into the payload (grep: only
> read in export queries). There is no entity-normalizer "specialisation" type, so the fix sends the raw
> text into `currentCourse`. Source level = `highest_qualification_education_level` (falls back to the
> highest present level). **Follow-up (`b6d3fd4`): resolve the REAL specialisation master id instead of
> always `"OTHERS"`.** Sending `specialisationId="OTHERS"` makes student-node's create-full
> (`createOrUpdateDegreeDeptAndSpecilisation` → institute-node `/institutes/crud/degree/stream/specialisation/bulk`)
> **create a new "other" master** whenever its EXACT match misses — and it missed on a plural/singular
> difference ("Human Resources" vs existing master "Human Resource"), so real specialisations were being
> duplicated as OTHERS. There is no vector-search "specialisation" entity, so `resolve_specialisation_master`
> (db_service) now matches `institute.specialisation_master` (status=1) directly — case/space-insensitive,
> tolerant of a trailing-'s' plural mismatch, preferring global masters (empty `student_id`). On a hit it
> sends the real `specialisationId` (+ canonical master name); only a genuine no-match falls back to
> `"OTHERS"`. Validated: `cc.specialisationId` = real UUID, `cc.specialisation` = "Human Resource".
>
> **Gotcha — "Other Degree" diploma DEGREE + DEPARTMENT dropped, and UG department stolen (fixed
> 2026-07-17, UAT `1e1a460`).** ERP sheets (JBIMS / pharmacy colleges) label the diploma/extra
> qualification block **"Other Degree ___"** instead of "Diploma ___" (e.g. `Other Degree`="D-Pharmacy",
> `Other Degree Stream`="Medical"). The **deterministic** degree/department extractors in
> `services/normalization_service.py` (`get_diploma_degree`/`get_diploma_department`) only matched keys
> containing the literal word "diploma", so they returned `None` → the block at ~L3144-3154 then
> **POPPED** the LLM's already-correct `education_diploma_degree`/`_department`, leaving the diploma
> `education[]` entry with empty degree + department (UI showed "Diploma – <college>" then just "in").
> Worse, `get_ug_department`'s fallback (no "other" in its exclusion list) then claimed
> "Other Degree Stream"="Medical" as the **UG** department (rendered "UG … in Medicine"). Fix:
> `get_diploma_degree`/`get_diploma_department` fall back to the "Other Degree" column family (a genuine
> "Diploma ___" column still wins); `get_ug_department` excludes "other" columns. Now diploma resolves
> D-Pharmacy→"Doctor Of Pharmacy" + Medical→"Medicine", and UG department = the real "Graduation Stream".
> Config-free (code only). **PROD needs the same code deploy.**
>
> **Gotcha — UG department stolen from "Post Graduation Stream"; extra-curriculars dropped when
> `mapping_field` NULL (fixed 2026-07-27, UAT `266ec7d` / Development `3909856`).** On the standard
> "Graduation ___" / "Post Graduation ___" sheet template (columns `Graduation Degree`=B.E./B.Tech,
> `Graduation Stream`=Computer Science and Engineering, `Post Graduation Stream`=Human Resources), a
> B.E./B.Tech CSE candidate rendered as **UG "… in Human Resource"**. The LLM output was already correct
> (`education_ug_department`="Computer Science and Engineering"); the **deterministic** override in
> `services/normalization_service.py` clobbered it. Root cause: `get_ug_department`/`get_pg_department`
> did not know the ERP "Graduation" (UG) / "Post Graduation" (PG) naming — "graduation" was not a UG
> keyword and the exclusion list only had "post graduate"/"postgraduate" (not "post graduation"). So the
> UG **fallback branch** (any bare *Stream column) grabbed "Post Graduation Stream"="Human Resources" and
> overwrote the correct value; `get_pg_department` returned `None`, so the PG dept was popped too. Fix:
> add "graduation" to `get_ug_department` UG keywords, add "post graduation"/"postgraduation"/"post grad"
> to its non-UG exclusion **and gate BOTH primary and fallback on it** (a "Post Graduation ___" column
> also contains "graduation", so it must be excluded first); add "post graduation"/"postgraduation" to
> `get_pg_department`'s keywords. Same commit adds `extra_curricular → studentPersonalProfile.extraCurriculars`
> to the worker `FALLBACK_MAPPING` (`workers/normalization_worker.py`) so extra-curriculars are not
> silently dropped when `normalized_columns.mapping_field` is NULL (as it is on PROD; UAT already had the
> DB mapping). Config-free (code only). **PROD needs the same code deploy** (and, independently, the
> `extra_curricular` `mapping_field` UPDATE if not relying on the fallback). Note: the sibling **degree**
> mis-map ("B.E./B.Tech" → generic "Bachelor Degree") is NOT this service — it is the pg-vector-search
> entity normalizer returning a `degree_level` over the exact `B.E/B.Tech` degree (see
> `Infrastructure/pg-vector-search.md`).
>
> **Gotcha — Roll No. / Preferred Location / social links ingested but never mapped (fixed 2026-07-28,
> UAT `706fb08` / Development `8460c9b`).** Three ERP columns reached `candidates_raw_data` and (for
> roll no) the LLM output, but never the create-full payload:
> - **`Roll No.` → `student.uniRollNo`** — the `roll_no` slug IS registered and the LLM emits it
>   (e.g. `24-MF-01`), but `mapping_field` is NULL in every env, so it fell through to `result["extra"]`
>   and `uniRollNo` stayed `""`. Added `roll_no`/`roll_number`/`uni_roll_no`/`university_roll_no` to the
>   worker `FALLBACK_MAPPING`, plus a raw-column fallback matched on `\broll\b` (word-bounded so
>   "Payroll" / "Enrollment No" don't false-positive).
> - **`Preferred Location (Anywhere or Particular City)` → `isAnywhere` / `preferredJobLocation[]`** —
>   nothing assembled it. "Anywhere" is a FLAG, not a place: it sets `isAnywhere=true` and contributes no
>   city rows. Other values are split on `, ; / |` + "and" and resolved via `DBService.lookup_city_state_ids`
>   (→ `get_state_country_from_city` → `get_state_name_by_id`) against `admin.mongo_db_cities` /
>   `mongo_db_states`, producing the production shape `{city_id, city_name, state_id, state_name}`; a value
>   that is a state, not a city, yields a state-only row `{state_id, state_name}` (both shapes exist in PROD,
>   written by the student profile UI). Unresolvable tokens are logged and skipped, never published.
>   Since 2026-08-04 the master lookup is **spelling-tolerant** — see the gotcha below.
> - **LinkedIn / social / portfolio columns → `socialMedia[{media, link}]`** — never assembled. Platform is
>   derived from the URL **host** (`_SOCIAL_HOSTS`) so a "LinkedIn URL" column holding a GitHub link is
>   still labelled `Github`, falling back to the column header; multiple URLs per cell are supported,
>   bare `www.` is upgraded to `https://`, entries deduped by link.
>
> All three read the normalized slug FIRST and the raw column second, deliberately: `preferred_location` /
> `social_media` / `linkedin_url` are registered on UAT but NOT PROD, so a slug-only implementation would
> have silently done nothing on PROD — the same `normalized_columns` config gap that dropped
> extra-curriculars. Consumers: `student.uni_roll_no`, `student_personal_profile.preferred_job_location` /
> `is_anywhere` / `social_media`; `preferredJobLocation`/`isAnywhere` also drive the corporate
> preferred-location candidate filter (`StudentRoleMapping.js`).
>
> Same commit **stops persisting the `[{"city_id":"","state_id":""}]` placeholder** that the payload
> template wrote to `preferred_job_location` for every student with no preferred location (visible on
> thousands of PROD rows). `preferredJobLocation`/`socialMedia`/`isAnywhere` are now dropped from the
> payload when empty — so an ERP re-upload no longer wipes locations a student set in the UI. The
> `studentPersonalProfile.preferredJobLocation.*` mapping_field hook was made index-safe (it used to rely
> on the placeholder dict at `[0]`). Config-free (code only). **PROD needs the same code deploy.**
>
> **Gotcha — a preferred location typed without a space silently vanished (fixed 2026-08-04, Development
> `658a714` / UAT `3f0c19e`).** `DBService.lookup_city_state_ids` matched the masters with an exact
> `name ILIKE :name`, but the ERP cell is hand-typed: a sheet reading `tamilnadu` never found the
> `Tamil Nadu` master row, both the city and state lookups returned `None`, and the worker's
> "matched no city/state master row — skipped" branch dropped the whole entry — the student was created
> with an EMPTY `preferred_job_location` and `is_anywhere=false`, with no error anywhere in the pipeline.
> The lookup now falls back to a **squashed** comparison when the exact match misses
> (`regexp_replace(lower(name),'[^a-z0-9]','','g')`, mirrored in Python by `squash_place_name`), so
> `tamilnadu` / `TAMIL-NADU` / `Tamil  Nadu` all resolve, as does `newdelhi` → `New Delhi`. Exact ILIKE
> still runs first; the fallback scan is cheap (~5.7k cities, 41 states) and only fires on a miss.
> Because the helper is shared, campus-location and candidate city/state resolution gained the same
> tolerance. Regression check: `tests/test_preferred_location_spelling.py` (hits the real masters,
> skips when the DB is unreachable). Config-free (code only). **PROD needs the same code deploy.**
> Note: already-ingested candidates are NOT backfilled — re-run affected raw rows via
> `normalization_status='pending'` to populate their locations.
>
> **Gotcha — a "Language" column on the sheet never reached the profile; Languages empty on the resume
> page (fixed 2026-08-04, Development `3ae47d2` / UAT `09b06d7`).** The `languages` slug IS registered
> AND mapped (`normalized_columns.mapping_field = studentPersonalProfile.languages` on UAT), yet
> `student_personal_profile.languages` stayed `[]` for every ERP-uploaded student. Three independent
> breaks:
> - **The model doesn't emit the `languages` slug for a plain "Language" column.** It files the value
>   under the legacy `language_proficiency_<lang>` slugs instead — a leftover from Google-Form sheets
>   whose columns read `Language Proficiency [English]`. Those slugs have `mapping_field` NULL in every
>   env, so the value fell through to `result["extra"]` and was never persisted. Confirmed on the
>   `Language = " English "` ERP row: `pre_mapping_debug` shows `"language_proficiency_english": true`
>   and **no** `languages` key.
> - **No raw-column fallback**, unlike roll-no / preferred-location / social-media above.
> - **Type mismatch.** When `languages` *is* emitted its value is a STRING (`"Tamil, English"`), while
>   student-node's create-full schema types the field `{ type: "array" }` — `set_nested` would have
>   written the string straight through and 400'd the **whole candidate** with `FST_ERR_VALIDATION`.
>
> Fix: the `studentPersonalProfile.languages` mapping_field is now **skipped** by the generic mapping
> loop and the array is assembled deterministically in `map_to_final_schema`, reading (in order of trust)
> the `languages` slug → truthy `language_proficiency_<lang>` slugs → raw headers. Two header shapes are
> handled: **value-carries-the-language** (`Language`, `Language Proficiency`, `.1`/`.2` dedup suffixes,
> `Mother Tongue`, `What are the languages you know?`) and **header-carries-the-language**
> (`Language Proficiency [English]`, where the cell is only a rating — `4`, `100%`, `Option 3`, `N/A` —
> so the language comes off the bracket and the cell merely gates inclusion). `_is_language_name` rejects
> ratings, the `Other (Mother Tongue)` placeholder and proficiency words; `_NOT_A_LANGUAGE_HEADER_RE`
> excludes "programming/coding languages" skill questions; a trailing `(CQ)` custom-question marker is
> stripped before bracket detection so it isn't read as a language named "CQ". Values are split on
> `, ; / | & +` + "and", title-cased and deduped case-insensitively. Consumer:
> `student_personal_profile.languages` (jsonb array of text — see `Student.js`, which reads it with
> `jsonb_array_elements_text` and treats `'[""]'` as NULL) → student-react resume "Additional Info".
> Regression check: `tests/test_languages_from_sheet.py` (14 cases, no DB needed). Config-free (code
> only) — no `normalized_columns` row is required for any of the three paths. **PROD needs the same code
> deploy** — all three FDN deployments (api/worker/cron), since `map_to_final_schema` runs in the
> **worker**; see "UAT reality — `auto_deploy.sh` only bumps 1 of the 3 containers" below. The UAT
> deploy on 2026-08-04 ran `auto_deploy.sh form-data-normalization UAT`, then rebuilt
> `datanormalization:api-mastersrc` from the same checkout and recreated `-worker` / `-cron`.
> Note: already-ingested candidates are NOT backfilled — re-run affected raw rows via
> `normalization_status='pending'`.
>
> **Gotcha — UG (any-level) department dropped when the sheet has a "Stream"/"Branch" column, not a
> "Department" column (fixed 2026-07-17, UAT `72c4d4b`).** Sheets carry e.g. "Graduation Stream" =
> "Electronics and Telecommunication" (no "Graduation Department" column). The extraction model
> (gpt-4o-mini, `AI_PROVIDER=openai_compatible`) DROPS that value and emits `education_ug_department = "NA"`
> → `education_profile.department` shows nothing, `stream_id` NULL. Two-layer fix: (1) a `SYSTEM_PROMPT_V2`
> rule (STREAM/BRANCH → DEPARTMENT, keeping specialization distinct), and — because gpt-4o-mini doesn't
> reliably honour it — (2) a **deterministic backfill** in `map_to_final_schema`: map each raw
> "<level> Stream"/"Branch" column to its education level and fill `education_<level>_department` when the
> model left it blank/"NA". This restores the department **text** (visible in DEG & DEPARTMENT); the
> `stream_id` master link stays NULL for backfilled values (the value never went through entity-matching) —
> resolving that would require injecting pre-`_resolve_and_store_all_ids`. Specialization columns are
> skipped (distinct from department). Pre-fix rows need re-normalization (reset
> `candidates_raw_data.normalization_status='pending'`); note `ALLOW_DUPLICATE_CANDIDATES=true` on UAT.
>
> **Gotcha — marks shown as raw decimal fraction, e.g. "0.91%" instead of "91%" (fixed 2026-07-17, UAT
> `f5f24a5`).** A sheet cell percentage-formatted in Excel/Sheets (displays "90.6%") exports as its raw
> fraction `0.906`; the model correctly sets `cumulative_type="Percentage"` but never scales the fraction.
> The old `_cgpa_marks_to_percentage` guard only fired when `cumulative_type` was empty or said
> "CGPA"/"GPA" — so a value already (correctly) labelled "Percentage" was skipped, leaving `0.906` verbatim.
> Fix: any `marks < 1` is unscaled regardless of the assigned type (a real exam percentage is never sub-1)
> → `×100`. Genuine CGPA-scale values (`0 < marks ≤ 10`, type says CGPA/GPA or type is blank) still `×10` as
> before. Applies to every `education_<level>_marks` + `highest_qualification_marks`.
>
> **Gotcha — "Batch" year wrong for a correctly-dated candidate, e.g. PG ends 2027 but showed 2025/2022
> (fixed 2026-07-17, UAT `f5f24a5`).** `highest_qualification_education_level`/`_degree`/`_department` can
> correctly name the most-recent block (e.g. "pg") while `highest_qualification_end_date`/`_start_date`
> get a SIBLING level's year instead (UG's 2025 copied in instead of PG's own 2027) — an LLM
> extraction slip, not a prompt gap. `highest_qualification_end_date` maps straight to
> `currentCourse.endedOn`, which `institute-react`'s students-list "Batch" column
> (`StudentsInfoTable/index.js` — `new Date(startedOn/endedOn).getFullYear()`) reads directly. Fix: since
> `highest_qualification_education_level` unambiguously names the authoritative `education_<level>_*`
> block, `map_to_final_schema` now always mirrors `end_date`/`start_date`/`marks`/`cumulative_type` from
> THAT block over the model's own `highest_qualification_*` copy (runs after both marks-scaling passes, so
> the source is already percentage-normalized). Degree/department are left alone — they resolve to master
> IDs earlier in `_resolve_and_store_all_ids`, so overwriting the text post-hoc without re-resolving the ID
> would desync `currentCourse.degreeId` from `currentCourse.degree`.
>
> **Gotcha — permanent city/state kept the raw sheet blob as display text (fixed 2026-07-17, UAT `834c62a`).**
> In `_resolve_and_store_all_ids` the **current/correspondence** path resolves `city_id`/`state_id`
> then does a master DB lookup and overwrites `normalized[city_key]`/`[state_key]` with the **canonical
> name** — so `spp.corr_city`/`corr_state` store clean values (`Mumbai`, `Maharashtra`). The
> **permanent** block resolved `perm_city_id`/`perm_state_id` correctly but **never wrote the name
> back**, so `spp.perm_city`/`perm_state` kept the raw un-split sheet text — e.g. a single combined
> address cell `"Maharashtra, Bhandara, 441904"` got dumped into **both** `perm_city` and `perm_state`
> even though the IDs (Bhandara city, Maharashtra state) were right. `permanent_city`/`permanent_state`
> map straight to `spp.perm_city`/`perm_state` (`db_service.py` final-schema map), so the blob reached
> the DB verbatim. `permanent_country` was unaffected — its path already had a canonical write-back.
> **The `834c62a` attempt was INCOMPLETE — real fix is `b6d3fd4`.** `834c62a` only mutated the in-memory
> `normalized["permanent_city"]`/`["permanent_state"]` dict, but the persistence layer
> (`update_normalized_data_resolved_names`) writes canonical names to
> `candidate_job_details.normalized_data` keyed by `city_key`/`state_key` — which are the **current_***
> keys when a current address exists — and never persisted `permanent_city`/`permanent_state`. Since
> `map_to_final_schema` reads the values back from that DB store (not the in-memory dict), the mutation
> was discarded and the blob survived. (This was masked earlier by validating via a manual SQL UPDATE
> instead of a real re-normalization.) `b6d3fd4` passes `perm_city_id`/`perm_state_id` into
> `update_normalized_data_resolved_names` and patches `names["permanent_city"]`/`["permanent_state"]`
> from `admin.mongo_db_cities`/`_states` — same mechanism the `permanent_country` write-back already used.
> Validated by re-normalization: `perm_city`="Nashik", `perm_state`="Maharashtra". Forward-only: pre-fix
> rows keep the blob until re-normalized; their `perm_*_id` are already correct so a targeted
> `perm_city`/`perm_state` text update from the master also fixes them.
>
> **Gotcha — a shared STATE overwrote the permanent CITY (fixed 2026-08-18, UAT `17c9ad7`).**
> The write-back documented above is only as good as the id it writes back from. In
> `_resolve_and_store_all_ids` the permanent block reused the current address's resolved ids
> whenever **either** the city **or** the state matched — and reused them as a *bundle*:
> `if same_city or same_state: perm_city_id = city_id; perm_state_id = state_id; ...`. Sharing a
> state is the ordinary case for a candidate applying locally, so **"current Chennai / permanent
> Tirunelveli, both Tamil Nadu"** took the current **city's** id, and the canonical name write-back
> then rewrote `permanent_city` as `"Chennai"` before the create-full payload was ever built. The
> candidate's permanent city was destroyed upstream of everything that reads it.
>
> Seen on UAT as *"the address doesn't change"*: a candidate who applied to role A, then came back
> through the Tally form for role B with a new permanent address, had the **old** city recorded
> against role B. It looked intermittent because rows whose sheet left `Permanent Address - State`
> as `N/A` didn't match on state and so resolved their permanent city correctly.
>
> Reuse is now decided **per field**, in the module-level `permanent_ids_from_current()`
> (`workers/normalization_worker.py`, unit-tested in `tests/test_permanent_address_reuse.py`):
> permanent city matches → the whole `(city, state, country)` tuple applies; only the state matches →
> keep state/country and resolve the city separately; nothing matches → resolve each separately. When
> the city is resolved separately its own state wins, so city and state stay coherent.
>
> **Downstream reads change** — they had been consuming the duplicated current city:
> `corporate-node/app/models/eligiblityCertriaFilter.js` (recruiter permanent city/state filter **and**
> its `DISTINCT perm_city_id, perm_city` dropdown) and `admin-node/app/models/MetaDashboard.js`
> (`corr_city OR perm_city` matching, `COUNT(DISTINCT perm_state) AS state_coverage`, grouping by
> `perm_state`). Candidates previously unfindable by their real permanent city become findable.
> Forward-only: existing rows keep the value they were given, and an already-frozen applied-role
> snapshot is **not** repaired by a re-run (`ON CONFLICT DO NOTHING` — see
> [Applied-Role Snapshots](../ATS/Student/AppliedRoles/applied-role-snapshots.md)).
>
> **Deploy gotcha:** `deploy.sh` (ID 20) rebuilds `datanormalization:api` but recreates **only** the
> `datanormalization` API container. `datanormalization-worker` and `datanormalization-cron` keep
> running the old image, and the **worker** is what executes `_resolve_and_store_all_ids` — so
> `auto_deploy.sh form-data-normalization` alone reports success and changes nothing. Recreate all
> three together:
> ```bash
> cd ~/api/form-data-normalization
> docker rm -f datanormalization-worker datanormalization-cron
> docker run -itd --name datanormalization-worker --restart unless-stopped --env-file .env \
>   --log-opt tag="service_name={{.Name}}" datanormalization:api python main.py worker
> docker run -itd --name datanormalization-cron   --restart unless-stopped --env-file .env \
>   --log-opt tag="service_name={{.Name}}" datanormalization:api python main.py cron
> ```
> Verify with `docker exec <c> grep -c permanent_ids_from_current /app/workers/normalization_worker.py`
> on all three. Same rule on PROD, where a mixed worker version previously produced ERP orphans.
>
> **Gotcha — résumé `started_in`/`ended_in` emitted in a format student-react can't parse (fixed
> 2026-07-17, UAT `905723e`).** The four date-bearing résumé sections `map_to_final_schema` builds —
> `resume.workExperience`, `resume.internships`, `resume.projects`, `resume.courses` — format their
> `started_in`/`ended_in` via `_normalize_work_date` (`workers/normalization_worker.py`), which used to
> output `YYYY-MM-DD` / `YYYY-MM` / bare `YYYY`. But **student-react**'s resume screens
> (`Resume/Components/ResumeDownload.js`, `Resume/DrawerComponents/ProjectDetails/ProjectForm.js`) parse
> these with a **strict `moment(x, 'MM/YYYY')`**, so any non-`MM/YYYY` value silently fails to parse →
> blank/invalid dates on the student's resume (and broken end-date sort in ResumeDownload). Fix rewrote
> `_normalize_work_date` to always emit `MM/YYYY` (converts `YYYY-MM-DD`, `YYYY-MM`, `DD/MM/YYYY`,
> `"Apr 2019"`/`"April 2019"`, `"2019 April"`; added a pass-through for input already `MM/YYYY`/`M/YYYY`
> which previously fell through to the broken bare-year branch). Bare year with **no** month now returns
> `""` (a half-formed non-`MM/YYYY` string is worse than an omitted date; downstream already treats empty
> as "no date"). Shared by both the corporate and institute-ERP paths — not ERP-only. `awards` uses a
> separate single-date field `awarded_on` and is untouched; there is no `training` section built in the
> mapper today. Config-free (code only). **PROD needs the same code deploy.**
>
> **Follow-up — the CV/LinkedIn half of the same bug (fixed 2026-07-29, UAT `2316363`).** The 2026-07-17
> fix only covered the **sheet-derived** entries (`recent_*` / `work_N_*` / `internship_N_*` /
> `project_N_*` / `course_N_*`). Each of those four sections then **appends the CV-parser entries** that
> don't duplicate a sheet row (`cv_data.resume.workExperience/internships/projects/courses`, also used
> for the LinkedIn/PDL resume) — and those were appended **verbatim**, keeping the parser's raw
> `2023-07-01` style values and the `start_date`/`end_date` aliases. So any candidate whose work history
> came from a **CV rather than sheet columns** still produced un-parseable dates. This is the common case
> for **corporate-role Tally applies** (candidate uploads a CV), which is why ERP bulk uploads looked
> fixed while corporate applicants did not. Fix adds `_normalize_cv_entry_dates(entry)` next to
> `_normalize_work_date` and wraps every appended CV entry in all four sections; it also collapses the
> `start_date`/`end_date` aliases onto `started_in`/`ended_in`. **PROD pending.**
>
> **Gotcha — internship start/end dates dropped because the sheet header is bare (fixed 2026-07-30,
> UAT `50f6303` / Development `6bb8924`).** ERP sheets qualify most columns (`Intership Company 1: Sector`,
> `Internship Company 1: Skills`) but label the internship date pair **bare** — `Started Date (MM/YYYY)` /
> `Ended Date (MM/YYYY)` — and rely on the column *sitting inside* the internship block for its meaning
> (pandas mangles the second occurrence to `Started Date (MM/YYYY).1`). That position is **destroyed
> before the LLM ever sees the row**: `candidates_raw_data.raw_data` is a **jsonb** column, and Postgres
> jsonb reorders object keys by (length, bytes). The logged prompt shows the keys length-sorted, so
> `Started Date (MM/YYYY)` arrives with no neighbours and nothing to attribute it to → the LLM emitted
> `internship_1_company/role/skills/description/duration` but **no** `internship_1_started_in`/`_ended_in`,
> and create-full received `{"started_in":"","ended_in":""}`. Work experience was unaffected because those
> headers name themselves (`Company 1 Started Date - mm/yyyy` → `recent_work_start_date`). The slugs were
> never the problem — `internship_N_started_in`/`_ended_in` are registered and active.
> Fix: `ExcelReader._qualify_bare_date_headers()` (`services/excel_reader.py`) rewrites a bare start/end-date
> header to `"<nearest preceding entity header>: <bare header>"` (→ `Intership Company 1: Started Date
> (MM/YYYY)`) **at parse time, while pandas column order is still intact**, stripping pandas' `.N` dupe
> suffix; collision-guarded so two columns can never collapse onto one key. The entity qualifier is the
> greedy match up to the last `intern(?)ship|company|employer|organization|project|course` + optional
> number, so already-qualified headers are untouched. Covers **both** ingest paths (institute-ERP upload
> and the Drive/Sheets webhook — both go through `ExcelReader.read_all_sheets`). Verified end-to-end on
> the reported sheet: `internship_1_started_in=2019-04-01`, `_ended_in=2019-06-01` →
> `_normalize_work_date` → `04/2019` / `06/2019`. Check: `tests/test_bare_date_headers.py`.
> **Only helps NEW uploads** — rows already in `candidates_raw_data` keep the ambiguous keys, so re-running
> normalization on them cannot recover the dates; the sheet must be re-ingested. **PROD needs the same
> code deploy.** General rule this establishes: **never** try to fix a mapping by relying on column
> adjacency in the prompt — qualify the header at ingest instead.
>
> **Gotcha — two PG blocks in one sheet collapse into one, leftover shown as "P.G. Diploma"
> (fixed 2026-07-31, UAT `fa8c382` / Development `3c81f40`; student-node UAT `fd252ff7` /
> Development `ca87b9de`).** ERP templates repeat the **whole** Post Graduation block when a candidate
> has a finished PG plus one being pursued: `Post Graduation College` … `Year of Passing`, then
> `Post Graduation College - currently pursuing` followed by the **same five headers again** (pandas
> mangles the repeats to `… Degree Stream.1`). Three failures compounded:
> (1) every `get_pg_*` helper in `normalization_service.py` returns the **first** header match, so block 1
> always won and block 2 was invisible to the deterministic layer — degree came from one block and year of
> passing from the other; (2) the normalized schema is **flat** (one `education_<level>_*` family per
> level), so the model pushed the leftover block onto `education_p_g_diploma_*` and
> `education_level_defaults` then hard-relabelled it → a **"P.G. Diploma" the candidate never took**;
> (3) ERP sheets write `"NA"`, not blanks, and `"NA"` is truthy — a fresher's NA-filled first PG block beat
> the real PG further right, so `education_pg_department` became `"NA"` and the degree was lost outright.
> Fix (5 parts):
> - **`services/education_blocks.py` (new)** — classifies each sheet column into (level, field);
>   `qualify_repeated_education_headers()` runs **at ingest in `ExcelReader.read_all_sheets`, while column
>   order still exists**, tagging the 2nd block's headers with a trailing `" (2)"`. Mandatory: `raw_data` is
>   **jsonb** and reorders keys, so block membership must be readable from the header TEXT alone (same root
>   cause as the bare-internship-date gotcha above). Two marks columns (`Aggregate CGPA` +
>   `Aggregate Percentage`) deliberately do **not** open a new block — only structural anchors
>   (institution/university/degree/department/ended_on/board) do.
> - **`apply_multi_block_education()`** (`normalization_service.py`, runs **last** in the deterministic
>   layer so it is the final authority): the block with the **latest** year of passing keeps
>   `education_<level>_*` — so `currentCourse` and `highest_qualification_*`, which derive from those slugs,
>   describe the course actually in progress — and each earlier block moves to a spare slot
>   (`p_g_diploma` → `phd`, both of which have a full slug family) **carrying its TRUE
>   `education_<slot>_education_level`**, applied after `education_level_defaults` so the slot is not
>   relabelled. Reuses existing slugs — **no new DB rows**. No-op for levels with a single block.
> - Placeholder cells (`NA`/`N/A`/`Nil`/`None`/`-`) are hidden from the `get_<level>_*` helpers via a
>   filtered `edu_input`; the explicit "sheet says no PG" guard now reads the **raw** cell so it still fires.
> - A degree sitting in front of a stream (`"M.Sc, finance"` in `Post Graduation Degree Stream`) is split
>   into degree + department when the level has no degree — some templates have no PG degree column at all.
>   The genuinely ambiguous header `Post Graduation Degree University` (holds `M.Tech` in one block,
>   `Anna University` in the next) is disambiguated **by value**, not by header.
> - **`normalization_worker.py`** mirrors `degree` + `department` (not just dates/marks) from the
>   identified highest-qualification block into `currentCourse`.
> - **student-node `createFullStudent`** (`app/handlers/common.js`, existing-student path) upserted
>   education rows by `educationLevel` **alone**, so two `pg` rows made the second overwrite the first and a
>   **re-upload collapsed both into one entry**. Now matches on level **plus** degree or institutionName and
>   claims each existing row once; unchanged when a level has a single row. (`education_profile` has no
>   unique constraint on `(student_id, education_level)`, and the create path uses a nested `create:` — both
>   already allowed two rows.)
> Verified on the reported sheet with keys reordered jsonb-style: current PG (`M.Sc` / finance /
> Anna University / 91 / **2026**) owns `pg`; the finished `M.Tech` (IISc / Civil Engineering / 81 /
> **2021**) sits in the spare slot reporting `education_level: "pg"`. Rows 1–2 (NA first block) now recover
> `M.Sc` + `finance` where the degree was previously lost. Check:
> `docker exec datanormalization python -m unittest discover -s tests` (`tests/test_education_blocks.py`).
> **Only helps NEW uploads** — rows already in `candidates_raw_data` keep the untagged headers, so
> re-running normalization on them cannot split the blocks; the sheet must be **re-ingested**.
> **Limit:** only two spare slots exist, so a third same-level block is logged and dropped, not blended.
> **PROD needs the same code deploy (both repos).**
>
> **Sequel — a "Currently Pursuing Course" column holding a COLLEGE opened a FALSE second block
> (fixed 2026-08-03, Development `a1ee514` / UAT `20d890b`; PROD pending).** The JBIMS `MHRD - 2027`
> sheet has ONE PG block, but every PG column after the first came back tagged `" (2)"` in
> `candidates_raw_data` (`PG Degree (2)`, `PG Specializations (2)`, `PG YOP (2)`…). Cause: the block's
> first column is `PG Currently Pursuing Course`, which **holds the college**
> ("Rani Anna Government College for Women test, Tirunelveli") while its header says "Course", so
> `field_from_label` classified it as a **degree** column — the next real `PG Degree` column then looked
> like a repetition and opened block 2. One misread column produced three symptoms on 28 candidates:
> - **6/28 had an empty `currentCourse.specialisation`.** The model scattered the PG block across `pg`
>   plus the PG-diploma slot, and on those 6 rows spelled the slot `education_pg_diploma_*` instead of
>   the canonical `education_p_g_diploma_*`. The specialisation probe used exact keys, so it found
>   nothing. (Same class as the arrears slug-family bug: read the slug the LLM **actually emitted**.)
> - **28/28 got a PG qualification of `ANNA UNNIVERSITY`.** The college name in a degree slug reached the
>   degree normalizer, which fuzzy-matched it onto that master at **62%**. `ANNA UNNIVERSITY` is a junk
>   row in `institute.degrees` — a misspelled *university* in the DEGREE master, `status=1`, created
>   2024-10-07; `BHUPAL NOBLES UNIVERSITY` and `Asian College of Journalism` are also active there.
>   10 UAT `student.education_profile` rows (Dec 2025–Apr 2026) still point at it — **master cleanup
>   pending**, see the `masterNameGuard` section above.
> - **4/28 got a `currentCourse.startedOn` the sheet never stated** (816/824/827 = 2027, the year of
>   PASSING; 820 = 2026). Unrelated to the block split: the model invented
>   `highest_qualification_start_date`, and the highest-qualification mirror in `map_to_final_schema`
>   only ever **overwrote** that field, never cleared it.
>
> Fix (4 parts):
> - `field_from_label` decides a course/degree header **by its VALUE** — new `looks_like_institution()`;
>   a college in a "Course"/"Degree" column is read as `institution_name`. Same value-over-header
>   principle already used for `Post Graduation Degree University`.
> - `ExcelReader.read_all_sheets` passes the **first real cell of each column** into
>   `qualify_repeated_education_headers(headers, samples)` — header text alone cannot decide this.
>   Without samples the function keeps its old header-only behaviour.
> - the `currentCourse` specialisation probe matches slugs by a **punctuation-squashed** form, so
>   `pg_diploma` ≡ `p_g_diploma` and the off-spelling no longer loses the value.
> - the highest-qualification mirror now **clears** `highest_qualification_start_date` when
>   `education_<hq_level>_started_on` is empty, and `_call_degree_normalizer_api` **refuses
>   institution-looking input** outright.
>
> Verified: the real workbook re-ingested through the fixed reader produces **zero `(2)` tags**; the 4
> failing rows replayed through the fixed worker (`map_to_final_schema` on the stored
> `normalization_logs.details->'payload'->'responceData'`) give `specialisation = "Human Resource"` and
> `startedOn = 0` with `endedOn` unchanged. Checks: `tests/test_education_blocks.py`,
> `tests/test_current_course_from_erp_sheet.py` (41 tests) — run them in-container:
> `docker exec -w /app datanormalization-worker python -m unittest discover -s tests`.
> **Only helps NEW uploads** — already-ingested rows keep their `(2)`-tagged headers; the sheet must be
> re-ingested, not merely re-normalized.
>
> **Separate, still open — half the batch got an nginx `504` from `create_full_student`.** 14 of the 28
> calls logged `create_full_student_response` as failed with a 504 Gateway Time-out, yet 31 students were
> created in that window: student-node exceeds the nginx timeout and the normalizer records a false
> failure. Retrying such an upload risks duplicates.
>
> **Known gap (not fixed) — internship / work-experience SKILLS never become `skill_set`.** The sheet's
> `Internship Company N: Skills` is extracted (`internship_1_skills`) and the worker does ship it, but as a
> raw **string** (`"skills": "A, B, C"`), which is what lands in `resume.internships[]`. The platform's
> canonical shape is `skill_set: [{id, name}]` resolved against the `student.skills` master — that's what
> `student-node/app/helpers/utils.js` reads when collecting a student's skills and what every resume
> renderer maps (`student-react ResumeDownload.js`, `institute-react ResumeDownload/Partials/DownloadFile.js`).
> Nothing reads the `skills` string, so ERP-imported skills display nowhere and count for nothing in
> role/skill matching. Work-experience skills are lost one step earlier, on a key mismatch: the LLM emits
> `recent_work_skills` but the worker reads `recent_work_skill_set` (both slugs exist), so the payload
> ships `"skills": ""`. Skills embedded in the Certifications text are also discarded (only
> `course_N_title` is taken). student-node already resolves skill names → master ids for education /
> currentCourse (`Student.js` `student.skills` lookup) — internships and workExperience simply never run it.
>
> **Not the same bug as a "Invalid date" on the corporate candidate drawer** — a correctly stored
> `MM/YYYY` value can still *render* as `Invalid date` if the frontend parses it without the format
> token. See `ATS/Corporate/README.md`; the two failures look identical in the UI but only one is a data
> problem. Check the stored value before assuming normalization is at fault.
>
> **Deploy target (important):** the hook runs in the **`datanormalization-worker`** container
> (`python main.py worker`) on **uat.pluginlive.com** — that's what processes the ingest
> queue. `deploy.sh` option 20 only rebuilds the API container, so it never updates the
> worker/cron. As of **2026-07-30 all three containers run the `datanormalization:api` tag** —
> the hand-set tags (`api-degreeguard` 2026-07-29, `api-namefix` before that) are gone, because that
> deploy ran `auto_deploy.sh form-data-normalization UAT` (builds `:api`) and then recreated `-worker`
> and `-cron` from the same `:api` image. **Still check the live tag with `docker ps` before building** —
> if someone hand-tags again, the api and worker will silently diverge. Deploy normalization changes manually, keeping the existing `.env` (do **not**
> `cp .env.uat .env` — it can regress the hand-applied Gemini keyfix):
> (a `git pull` 403 here means the org GitHub token expired — see `Infrastructure/github-access.md`)
> `ssh uat → cd ~/api/form-data-normalization → git pull origin UAT → docker build --build-arg ENVIRONMENT=uat -t datanormalization:<tag> . →`
> recreate **all three** containers with their exact cmd/ports/restart (`datanormalization` api
> `-p 5013:5013 --restart always`, `-worker` `python main.py worker`, `-cron` `python main.py cron`,
> both `--restart unless-stopped`, all `--env-file .env`).

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

> **UAT reality — `auto_deploy.sh` only bumps 1 of the 3 containers.**
> `./auto_deploy.sh form-data-normalization UAT` builds `datanormalization:api` and
> recreates **only** the `datanormalization` (api) container. On UAT the worker and cron
> containers run the separate **`datanormalization:api-mastersrc`** tag, so they keep
> serving the previous build and any change to `workers/` or `services/` has no effect —
> which is most of this service's behaviour. After the script finishes, retag and roll the
> siblings (their env is `--env-file .env`, restart policy `unless-stopped`):
>
> ```bash
> cd ~/api/form-data-normalization
> docker tag $(docker inspect datanormalization-worker --format '{{.Image}}') \
>            datanormalization:api-mastersrc-prev          # rollback tag
> docker tag datanormalization:api datanormalization:api-mastersrc
> docker rm -f datanormalization-worker datanormalization-cron
> for m in worker cron; do
>   docker run -itd --name datanormalization-$m --restart unless-stopped --env-file .env \
>     --log-opt max-size=100m --log-opt max-file=3 --log-opt tag='service_name={{.Name}}' \
>     datanormalization:api-mastersrc python main.py $m
> done
> ```
>
> Verify all three actually carry the change, e.g.
> `for c in datanormalization datanormalization-worker datanormalization-cron; do docker exec $c grep -c '<new symbol>' <file>; done`.

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
