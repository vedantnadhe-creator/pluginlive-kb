# ElasticSearch Service (search-service-1)

This folder contains module-wise documentation for the PluginLive Search Service — a NestJS backend that provides ElasticSearch-powered search, data ingestion, synchronization, and index management for the entire ATS platform.

## ⚠️ Search engine per environment (ES → Postgres migration)

| Env | Engine | Notes |
|---|---|---|
| DEV | **Postgres** (`SEARCH_ENGINE_DEFAULT=pg`) | ES container removed |
| UAT | **Postgres** (`SEARCH_ENGINE_DEFAULT=pg`) | Full PG code deployed 2026-07-10 |
| PROD | **ElasticSearch** | Unchanged — everything below still describes PROD |

Under the PG engine (flag resolved per endpoint by `src/modules/search/pg/engine.flag.ts`, default via `SEARCH_ENGINE_DEFAULT`; the flag must live in the box `.env`, not `docker -e`):

- **Reads** are served from materialized views in the `search_engine` Postgres schema (one MV per former ES index, e.g. `mv_institutes_master`, `mv_corporate_list`, `mv_degree_stream_specialisation_master`, `mv_institute_job_role`). Query logic lives in `src/modules/search/pg/pgSearch.service.ts`. Search semantics mirror ES: per-word prefix AND for multi-word terms, punctuation-stripped short-form matching (`B.C.S` ⇄ `BCS`), trigram typo tolerance for single words, and exact-name > exact-short-form > prefix > contains ranking (score terms are NULL-proofed — `similarity(NULL, q)` once poisoned the ordering).
- **`/sync/*` endpoints and their crons** no longer write ES — they `REFRESH MATERIALIZED VIEW CONCURRENTLY` the corresponding MV(s) via `search_engine.refresh_one()` (helper `pgRefreshMvs` in `sync.service.ts`). Outcomes are logged in `search_engine.refresh_log`. Datasets with no MV no-op with a log.
- **`/ingest/*`** (per-document writes from institute/corporate/student-node) is an acknowledged **no-op** under PG — data freshness is cron-cadence (12h + the 3/5-min degree-stream-spec pair), not per-write realtime.
- **`/synonyms`** stays ES-only (no callers); synonyms under PG come from the `search_engine.pluginlive` text-search dictionary.
- **`/collegenamecorporatesfilter/lists`** returns an empty result under PG — its source views (`institute.college_name_corporates_filter_*_view`) no longer exist on any env, so the ES pipeline was already dead; recreate the views to restore data.
- **DB migrations** live in `PluginLive-Technologies/DB-Scripts` → `Search Service Postgres Migration/` (001–009 + `institute_job_role_mv`). DEV + UAT applied; **PROD pending** — apply all of them (sorted by filename) before ever flipping PROD to `pg`.
- Known data caveat: exact-short-form junk degrees in DEV/UAT master data (e.g. "BE TESTING DEGREE", short form `BE`) legitimately rank alongside Bachelor of Engineering for `BE` searches — clean the master data, don't change the ranking.
- **Per-dataset `orSearchCols` (since UAT 2026-07-13):** a `PgDataset` can list extra columns OR'd into the search predicate as punctuation-stripped contains, with a +4 boost on exact match. Used by `INSTITUTES_MASTER` with `orSearchCols: ['instute_campus_short_name']` to recover the ES `instituteCampus.shortName^2` behavior — short-form institute lookups like `?search=pcwd` now hit a college whose campus short form is `pcwd`/`PCWD`/`P.C.W.D`. Other datasets inherit name-only matching.

**Backend:** `search-service-1`
**Framework:** NestJS (TypeScript)
**Port:** 3001 (default)
**Swagger:** `/api`

## Architecture

- **ElasticSearch Client:** `@elastic/elasticsearch` v8.11 — wrapped in `ClientServices`
- **Database:** PostgreSQL (TypeORM, institute schema) + MongoDB (Mongoose) — source data for sync
- **Authentication:** API key-based (`api-key` header). Two roles: `User` (read-only search) and `Admin` (sync, ingest, synonyms)
- **Scheduling:** `@nestjs/schedule` — interval-based jobs for periodic data sync
- **Index Prefix:** Configurable via `INDEX_PREFIX` env var for environment isolation

## Modules

### API Modules (with HTTP endpoints)

| Module | Folder | Controller Prefix | Auth | Description |
|--------|--------|-------------------|------|-------------|
| Search | `Search/` | `/search` | User | Generic search across all data types (degrees, streams, skills, etc.) + geo lookups (countries, states, cities) |
| DataSearch | `DataSearch/` | `/` (root) | User | Specialized search/filter endpoints for student, institute, corporate data — used by frontend filter dropdowns |
| Sync | `Sync/` | `/sync` | Admin | Trigger PostgreSQL → ElasticSearch data synchronization for all index types |
| Ingest | `Ingest/` | `/ingest` | Admin | CRUD operations on individual ES documents (create, update, delete by filter) |
| Synonyms | `Synonyms/` | `/synonyms` | Admin | Manage synonym sets for ES indices (degrees, streams, skills, etc.) |
| Cleanup | `Cleanup/` | `/cleanup` | User | Manual and cron-based cleanup of old ES indices |

### Internal Modules (no HTTP endpoints)

| Module | Folder | Description |
|--------|--------|-------------|
| Client | `Client/` | ElasticSearch client wrapper — search, count, create, update, delete, bulk, index/alias management |
| Auth | `Auth/` | API key guard with role-based access (User vs Admin) |
| Jobs | `Jobs/` | Scheduled interval jobs that trigger sync operations periodically |

## Data Set Types (ES Indices)

The service manages **50+ ElasticSearch index types** defined in `DATA_SET_TYPES` enum:

| Category | Indices |
|----------|---------|
| **Academic** | `degrees`, `streams`, `specialisations`, `degree_streams`, `degree_stream_specialisations`, `events_degree_stream_specialisations` |
| **Geography** | `countries`, `states`, `cities`, `cities_details`, `state_with_country`, `locations_details` |
| **Universities** | `universities`, `universities_master`, `universities_li`, `universities_scw`, `universities_ssw` |
| **Institutes** | `institutes_master`, `institutes_campuses`, `institute_campus_course`, `institute_degree`, `institute_specialisation`, `institute_stream`, `institute_locations` |
| **Student Filters** | `degree_department_ls`, `degree_department_ssw_lsp`, `degree_department_not_cm`, `specialization_ls`, `specialization_cas`, `specialization_not_cas`, `specialization_lsp_scw`, `college_name_ls`, `college_name_lsp`, `student_state`, `student_city_ls`, `city_master_scw_ssw`, `city_master_not`, `student_skill`, `student_crud_skill` |
| **Corporate** | `college_name_corporate_ca`, `college_name_corporate_not_ca`, `city_role_corporate_rp`, `city_role_corporate_hs`, `city_role_corporate_not_rp_hs`, `corporate_locations`, `corporate_list` |
| **Master Data** | `function_data`, `sector_data`, `degree_data`, `campus_preview_new_list`, `crud_degree_department` |
| **Other** | `skills`, `function`, `sector`, `industries`, `companyMaster` |

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `ES_URL` | ElasticSearch cluster URL |
| `ES_USER_NAME` / `ES_PASSWORD` | ES authentication |
| `API_KEY_TOKEN` | User-level API key |
| `ADMIN_API_KEY_TOKEN` | Admin-level API key |
| `INDEX_PREFIX` | Prefix for all ES index names (environment isolation) |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USERNAME` / `DB_PASSWORD` | PostgreSQL connection |
| `SCHEMA_NAME` | PostgreSQL schema |
| `DB_SSL` | Enable SSL for PostgreSQL |
| `MONGO_DB_URL` | MongoDB connection string |
| `ES_CLEANUP_KEEP_COUNT` | Number of old indices to retain during cleanup (default: 30) |

## Documentation Structure

Each module folder contains a `README.md` covering:
- Overview & purpose
- API endpoints (method, route, auth level, parameters)
- Service methods
- Key features
