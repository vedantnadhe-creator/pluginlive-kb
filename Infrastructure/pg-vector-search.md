---
type: reference
tags: [service, api, python, vector-search, normalization, ai, pgvector]
---

# PG Vector Search Service (Entity Normalizer)

**Repo:** `/home/ubuntu/api/pg-vector-api-service`
**Stack:** Python 3.12 · FastAPI · PostgreSQL (pgvector + pg_trgm) · Gemini · OpenAI
**Port:** 8002 (UAT/Prod) / 8000 (default)
**Docker Image:** `pg-vector-api-service`
**Live URLs:**
- DEV: `https://vector-search.dev.pluginlive.com`
- PROD: `https://vector-search.prod.pluginlive.com`

---

## What It Does

Entity normalization microservice that matches messy free-text inputs (abbreviations, typos, casing variations) to canonical reference data using **Multi-Signal Reciprocal Rank Fusion (RRF)**.

**Example:** `"BVRIT Narsapur"` → `"BV Raju Institute of Technology"` (confidence: 0.95)

---

## Ranking Architecture

```
Input (e.g., "BVRIT Narsapur")
  │
  ├─ Signal 1: Vector Search    (semantic similarity via pgvector HNSW, 1536-dim)
  ├─ Signal 2: Trigram Search    (character-level similarity via pg_trgm GIN)
  ├─ Signal 3: Acronym Search    (first-letter matching: B.V.R.I.T)
  └─ Signal 4: Exact Search      (case-insensitive exact match)
  │
  ▼
  Reciprocal Rank Fusion: RRF(candidate) = Σ 1/(k + rank), k=60
  │
  ▼
  Decision Ladder (first match wins):
  1. Exact signal hit         → confidence=1.0, method="exact"
  2. Single acronym match     → confidence=0.95, method="acronym"
  3. 3+ signals agree         → method="multi_signal"
  4. Top vector ≥ 0.85        → method="vector"
  5. Otherwise                → LLM picks from top 10 → method="llm_fallback"
  │
  ▼ (only on no_match)
  Cascade: Query rewriter expands abbreviations, resolves pincodes → re-runs signals
```

**Graceful Degradation:** When embedding/LLM API is down, circuit breaker skips vector signal and LLM — serves trigram/acronym/exact only.

### Role-family clustering (Development, 2026-08-24)

Role search also supports transitive semantic families. This solves cases where
`software developer` is close to `full stack engineer`, and `full stack engineer`
is close to `DevOps engineer`, even when the first and last titles do not clear a
direct cosine threshold.

- `POST /api/v1/admin/role-clusters/rebuild` loads every `role`, cleans its
  description/JD, weights the title more heavily, and embeds that combined text
  locally with the open-source `sentence-transformers/all-MiniLM-L6-v2` model
  through FastEmbed/ONNX. It folds
  case/whitespace-equivalent duplicate job postings into one title concept,
  builds a cosine k-nearest-neighbour graph, and partitions it with deterministic
  Louvain community detection. A small reviewed taxonomy supplies intentional
  long-range bridges that embeddings miss; the first family combines software,
  full-stack, frontend/backend, DevOps, SRE and cloud titles. All original
  job-role IDs are mapped back to the resulting cluster.
- Defaults: `neighbours=12`, `edge_threshold=0.68`, `resolution=0.8`, seed `42`.
  Parameters are query parameters so they can be tuned against reviewed DEV
  examples without a code release.
- Clusters are stored in `public.role_clusters`; membership is stored in
  `public.role_cluster_memberships`. Local 384-dimensional role embeddings are
  cached by content hash in `public.role_cluster_embeddings`, so later rebuilds
  generate vectors only for new or edited roles. Rebuild replacement is
  transactional.
- When the embedding queue processes a new or renamed `role`, it assigns the row
  to the cluster of its nearest embedded member at similarity `>= 0.68`; otherwise
  it creates a singleton. Periodic full rebuilds allow later bridge roles to
  reshape communities globally.
- `POST /api/v1/role-clusters/search` embeds free text locally and returns the
  complete family (`method=local_minilm_cluster_seed`). Reviewed family terms
  route to that family before nearest-role selection; this is how `full stack
  engineer` and `cloud engineer` reliably reach the software/DevOps/cloud family
  even when no exact canonical title exists.
  `GET /api/v1/admin/role-clusters/{role_id}` returns a family directly from a
  known role ID.

Title+JD DEV backfill result (2026-08-24): 7,505 role rows, 1,585 unique
normalized titles, 76 clusters. Acceptance queries `software developer`,
`full stack engineer`, `devops engineer`, and `cloud engineer` all resolve to
cluster `Software Engineering, DevOps & Cloud` (269 role rows).

UAT received the same implementation in merge commit `36c336e` on 2026-08-24.
The UAT backfill produced the same 7,505 rows / 1,585 titles / 76 clusters and
reused all 7,505 content-identical cached vectors. The four acceptance queries
pass through `https://vector-search.uat.pluginlive.com` and expand to the same
269-row software/DevOps/cloud family.

Role clustering and cluster search make no paid embedding API calls. The model
is baked into the service image and runs on DEV CPU. This is separate from the
existing Gemini-backed entity-normalizer fallback and its startup health check.

DEV backfill after deployment:

```bash
curl -X POST 'https://vector-search.dev.pluginlive.com/api/v1/admin/role-clusters/rebuild?neighbours=12&edge_threshold=0.68&resolution=0.8'
```

Implementation: `pg-vector-api-service` Development commits `a862470`,
`103f842`, `c84fdb8`, and `386d664` (following the original title-only commits
`f200744` and `888c322`).

> **Known issue (partially fixed, 2026-08-11) — degree aliases must resolve to the canonical master.**
> `/normalize/multi` with `entity_types=["degree","degree_level"]` for input `"B.E./B.Tech"` returns the
> `degrees_level` row **"BACHELOR DEGREE"** (conf 0.65, `method=llm_fallback`) instead of the exact
> `institute.degrees` row **`B.E/B.Tech`** — so the candidate's UG degree renders as generic
> "Bachelor Degree". Cause: `exact_search` is punctuation-sensitive (`WHERE LOWER(name)=LOWER($1)`), so
> `"B.E./B.Tech"` (with the extra dot) does not exact-match `"B.E/B.Tech"`; no exact hit → the LLM
> reranker chooses the broad degree_level. Separately, a raw **`BE`** exact-matched a legacy short-name
> degree row and displayed as `Be`. Fixed in `pg-vector-api-service` `87e1b3c`: degree-only lookup aliases
> now resolve `BE`/`B.E.` to **`Bachelor Of Engineering`** before matching, while retaining the raw input in
> audit logs. The punctuation-sensitive `B.E./B.Tech` case remains a separate follow-up.

---

## Directory Structure

```
pg-vector-api-service/
├── src/
│   ├── api/
│   │   ├── routes.py           # /normalize, /batch, /multi, /health
│   │   ├── admin_routes.py     # /setup-entity, /rebuild, /stats, /alerts
│   │   └── schemas.py          # Pydantic request/response models
│   ├── core/
│   │   ├── normalizer.py       # Multi-signal RRF engine (main logic)
│   │   ├── embedder.py         # Embedding API with token-bucket rate limiter
│   │   ├── llm_fallback.py     # LLM disambiguation from top 10 candidates
│   │   ├── query_rewriter.py   # Abbreviation expansion, pincode resolution
│   │   ├── api_monitor.py      # Circuit breaker, failure tracking, email alerts
│   │   └── batch_embedder.py   # Gemini Batch API for bulk rebuilds
│   ├── db/
│   │   ├── connection.py       # asyncpg pool with search_path
│   │   └── queries.py          # All SQL: 4 signals, admin ops, results logging
│   ├── workers/
│   │   └── queue_processor.py  # Background worker for auto-update queue
│   └── config.py               # Pydantic settings from .env
├── main.py                     # FastAPI entry point
├── requirements.txt
└── Dockerfile
```

---

## API Endpoints

### Normalize (4 endpoints)

| Method | Endpoint | Purpose |
|--------|----------|--------|
| POST | `/api/v1/normalize` | Normalize single input against one entity type |
| POST | `/api/v1/normalize/batch` | Normalize multiple inputs |
| POST | `/api/v1/normalize/multi` | Normalize across multiple entity types (min 2) |
| GET | `/api/v1/health` | Service health & DB connectivity |

**Example request:**
```json
POST /api/v1/normalize
{
  "entity_type": "college",
  "raw_input": "BVRIT Narsapur",
  "context": {"pincode": "560001"}
}
```

**Example response:**
```json
{
  "matched_name": "BV Raju Institute of Technology",
  "id": "97b7ab50-...",
  "institute_id": "6fea3e05-...",
  "city": "Narsapur",
  "state": "Telangana",
  "confidence": 0.64,
  "method": "llm_fallback"
}
```

### Admin (8+ endpoints under `/api/v1/admin/`)

| Method | Endpoint | Purpose |
|--------|----------|--------|
| POST | `/admin/setup-entity` | Register new entity type (creates columns, indexes, triggers) |
| GET | `/admin/entity-configs` | List all registered entity types |
| PATCH | `/admin/entity-configs/{type}` | Update thresholds |
| DELETE | `/admin/entity-configs/{type}` | Remove entity type |
| POST | `/admin/rebuild-embeddings` | Start bulk re-embedding (background) |
| GET | `/admin/rebuild-status/{task_id}` | Check rebuild progress |
| GET | `/admin/queue-status` | Embedding queue counts |
| GET | `/admin/stats` | Normalization stats & match rates |
| POST | `/admin/alert-recipients` | Add email for alerts |
| GET | `/admin/alert-recipients` | List alert recipients |

---

## Registered Entity Types

The system is generic — any entity type can be added via `setup-entity`. Currently registered:

| Entity Type | Source Table | Embed Columns |
|-------------|-------------|---------------|
| `college` | `institutes_campuses` | campus_name |
| `country` | `mongo_db_countries` | name |
| `state` | `mongo_db_states` | name |
| `city` | `mongo_db_cities` | name |
| `degree` | `degrees` | name |
| `degree_level` | `degrees_level` | name |
| `department` | `streams` | name |
| `role` | `job_roles` | name |

### Active-row filter (and the `college` exception)

At `setup-entity`, the service auto-detects an `is_active`/`status` column on the source table and records it on the entity's `entity_configs` row (`active_column` / `active_value`). All four match signals then append that filter (e.g. `AND "is_active" = true`) via `_active_filter()` in `db/queries.py`, so **inactive reference rows are normally excluded** from candidate matching.

**Exception — `college`:** a campus can be deactivated *after* students/candidates were already mapped to it. If the filter were applied, the campus name would match nothing → `no_match` → `instituteCampusId` saved as **null**, wiping the real mapping. So `_active_filter()` is **skipped for the `college` entity** (`_PRESERVE_INACTIVE_ENTITIES = {"college"}`): a campus name resolves to its `instituteCampusId` **regardless of `is_active`**. The `college` row in `entity_configs` still shows `active_column = is_active` (auto-detected at setup), but it is bypassed in code. All other entities keep the active-only filter.

---

## Key Modules

| Module | Purpose |
|--------|--------|
| `core/normalizer.py` | RRF engine — garbage filtering, acronym extraction, signal execution, decision ladder, cascade |
| `core/embedder.py` | Embedding API calls with token-bucket rate limiter (20 tokens, refill 20/60s) and retry |
| `core/llm_fallback.py` | Sends top 10 candidates to LLM for disambiguation (strict prompt, ranks 1-10 or 0) |
| `core/query_rewriter.py` | Expands abbreviations, resolves pincodes to city names via LLM |
| `core/api_monitor.py` | Circuit breaker (CLOSED → OPEN → HALF_OPEN), failure tracking, 9 email alert types |
| `db/queries.py` | SQL for 4 signals (vector cosine, trigram similarity, acronym first-letter, exact match) |
| `workers/queue_processor.py` | Polls `embedding_queue` every 30s, re-embeds rows on INSERT/UPDATE, nullifies on DELETE |

---

## Database Schema

### Service Tables (in `public` schema)

| Table | Purpose |
|-------|--------|
| `entity_configs` | Registered entity types (source_table, embed_columns, return_columns, thresholds) |
| `embedding_queue` | Rows needing re-embedding (table_name, record_id, operation, status) |
| `normalization_results` | Every match logged (raw_input, matched_name, confidence, method, signals JSONB) |
| `alert_recipients` | Email addresses for outage alerts |
| `ai_api_call_logs` | Every Gemini/OpenAI call logged (service, provider, model, tokens, response_time) |

### Reference Data Columns (added by setup-entity)

Each registered entity table gets a `*_embedding vector(1536)` column with an HNSW index, plus a PostgreSQL trigger that enqueues rows into `embedding_queue` on INSERT/UPDATE/DELETE.

---

## Integration Points

| Direction | Service | Purpose |
|-----------|---------|--------|
| **Outbound** | Gemini Embedding API | Generate 1536-dim vectors (`gemini-embedding-001`) |
| **Outbound** | Gemini LLM API | Disambiguate top 10 candidates (`gemini-3-flash-preview`) |
| **Outbound** | OpenAI API (fallback) | Alternative embedding (`text-embedding-3-small`) + LLM (`gpt-4o-mini`) |
| **Outbound** | SMTP | Outage/recovery/rebuild email alerts |
| **Inbound** | Form Data Normalization | Calls `/api/v1/normalize` for entity resolution |
| **Inbound** | Any internal service | REST API consumer |

---

## Key Environment Variables

| Variable | Default | Purpose |
|----------|---------|--------|
| `DATABASE_URL` | — | PostgreSQL connection string |
| `DB_SCHEMA` | `public` | Search path (e.g., `candidate_ingestion_schema,institute,public`) |
| `EMBEDDING_PROVIDER` | `gemini` | `gemini` or `openai` |
| `LLM_PROVIDER` | `gemini` | `gemini` or `openai` (independent from embedding) |
| `GEMINI_API_KEY` | — | Gemini API key |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | Embedding model |
| `GEMINI_LLM_MODEL` | `gemini-3-flash-preview` | LLM model |
| `OPENAI_API_KEY` | — | OpenAI fallback key |
| `EMBEDDING_DIMENSIONS` | `1536` | Vector dimensions (must match pgvector column) |
| `BATCH_SIZE` | `500` | Rows per batch during rebuild |
| `QUEUE_POLL_INTERVAL` | `30` | Seconds between queue worker polls |
| `PORT` | `8000` | Server port (UAT/Prod uses 8002) |
| `CIRCUIT_BREAKER_ENABLED` | `false` | Enable circuit breaker |
| `CIRCUIT_BREAKER_DURATION_SECONDS` | `60` | Cooldown before retry |
| `ALERT_ENABLED` | `false` | Enable SMTP alerts |
| `ALERT_FAILURE_THRESHOLD` | `5` | Consecutive failures before alert |

---

## Docker & Deployment

```bash
# Build
docker build -t pg-vector-api-service .

# Run
docker run -p 8002:8000 --env-file .env pg-vector-api-service
```

**PM2 (current production/UAT):**
```bash
pm2 start "uvicorn main:app --host 0.0.0.0 --port 8002" --name entity-api
pm2 start "python -m src.workers.queue_processor" --name entity-worker
```

**Adding a new entity type:**
```bash
curl -X POST "http://localhost:8002/api/v1/admin/setup-entity" \
  -d "entity_type=college&source_table=institutes_campuses&source_schema=institute&embed_columns=campus_name&return_columns=id,institute_id,campus_name,city,state&id_column=id"
```

**Rebuilding embeddings:**
```bash
curl -X POST "http://localhost:8002/api/v1/admin/rebuild-embeddings?entity_type=college"
# Check progress:
curl "http://localhost:8002/api/v1/admin/rebuild-status/{task_id}"
```
