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

## Architecture

| Component | Role |
|-----------|------|
| **FastAPI app** (`api/main.py`) | REST API, CORS, lifespan hooks |
| **Normalization worker** | Background loop: **atomically claims** pending rows → OpenAI → entity matcher → writes normalized data. Safe to run across multiple replicas (see Concurrency below) |
| **Assessment worker** | Syncs assessment scores from assessment DB |
| **Form metadata worker** | Fetches Google Forms metadata |
| **Export worker** | Async CSV/Excel generation for large exports |
| **Scheduler** (APScheduler) | Daily ingest (1 AM), webhook health (15 min), webhook renewal (Sun 1 AM) |

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
| POST | `/webhooks/google-drive` | Receive Drive file change notifications |

### Ingest UI (HTML)

| Method | Endpoint | Purpose |
|--------|----------|--------|
| GET | `/ingest` | Interactive ingest UI |
| POST | `/ingest/start` | Start manual ingestion |
| GET | `/ingest/stream/{run_id}` | Stream logs (SSE) |

---

## Database Schema

**Schema:** `candidate_ingestion_schema`

| Table | Purpose |
|-------|--------|
| `ingested_sheets` | Track Excel/Form sources (source_sheet_id, source_file, form_status) |
| `candidates_raw_data` | Raw ingested data (JSONB), normalization status, timestamps |
| `candidates` | Normalized records (name, email, mobile, gender, DOB, assessment_scores JSONB) |
| `candidate_job_details` | Role-specific data (role, cv_url, normalized_data JSONB, cv_data JSONB) |
| `open_ai_logs` | LLM API calls (prompt, response, token counts) |
| `normalization_logs` | Audit trail (old_data, new_data, normalized_keys) |
| `validation_logs` | Field validation results |
| `drive_webhook_log` | Drive change events |
| `drive_state` | Webhook state (start_page_token, webhook_data JSONB) |
| `ingested_forms` | Google Forms metadata |
| `export_jobs` | Async download jobs (status, file_path) |

**Relationships:** `candidates_raw_data` → `ingested_sheets` (many-to-one), `candidates` → `candidates_raw_data` (1:1), `candidate_job_details` → `candidates` (many-to-one)

---

## Integration Points

| Service | Purpose |
|---------|--------|
| **Google Drive API** | List/download Excel files, webhook registration |
| **Google Forms API** | Fetch form metadata |
| **OpenAI API** (GPT-4o-mini) | Field normalization, entity matching |
| **Gemini API** (3.0 Flash) | Fallback AI normalization |
| **Resume Parser** (`resume-parser.uat.pluginlive.com`) | PDF CV parsing |
| **PG Vector Search** (`vector-search.dev.pluginlive.com`) | Master entity resolution |
| **Assessment DB** | Fetch assessment scores (separate PG connection) |

---

## Key Environment Variables

| Variable | Purpose |
|----------|--------|
| `POSTGRES_URL` | Main DB (with `?options=-csearch_path=candidate_ingestion_schema`) |
| `POSTGRES_ASSESSMENT_SCORE_URL` | Assessment DB connection |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | OpenAI config (default: gpt-4o-mini) |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Gemini fallback |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Service account JSON path |
| `GOOGLE_DRIVE_FOLDER_ID` | Drive folder to monitor |
| `GOOGLE_DRIVE_WEBHOOK_URL` | Webhook receiver URL (ngrok in dev) |
| `PDF_PARSER_URL` / `PDF_PARSER_AUTH_KEY` | Resume parser endpoint |
| `ENTITY_NORMALIZER_API_URL` | PG Vector Search endpoint |
| `API_SECRET_KEY` | Auth key for `/api/api-ingest` endpoints |
| `APP_ENV` | `local` / `uat` / `prod` |

---

## Docker & Deployment

```bash
# Build
docker build -t form-data-normalization .

# Run
docker run -p 5013:5013 --env-file .env form-data-normalization
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
