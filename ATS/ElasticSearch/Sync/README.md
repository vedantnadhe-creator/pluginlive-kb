# Sync Module

**Controller Prefix:** `/sync`
**Auth:** Admin only
**Source:** `search-service-1/src/modules/sync/`

## Overview

**On all three environments (DEV, UAT, PROD — all on `SEARCH_ENGINE_DEFAULT=pg` as of 2026-08-24) "sync" means refreshing a Postgres materialized view, not writing to ElasticSearch.** Each endpoint resolves its engine flag and, under PG, calls `search_engine.refresh_one(<mv>, true)` — `REFRESH MATERIALIZED VIEW CONCURRENTLY` — for the MV(s) backing that dataset, then returns. The ES bulk-insert pipeline below it is legacy and unreachable. See the PG-engine section in [../README.md](../README.md) for the full picture.

Two consequences that catch people out:

- **`query_date` is accepted and ignored.** Under PG there is no incremental path: the DTO still takes the field, but a `CONCURRENTLY` refresh re-runs the MV's entire defining query and diffs the whole result set. Passing yesterday's date does not make the call cheaper.
- **These calls are slow and are on user-facing save paths.** End-to-end endpoint times measured on PROD (warm): `/sync/institutes_master` **11.2 s**, `/sync/institute_campus_cources` **8.4 s** (it refreshes two MVs — `mv_institute_campus_course` 5.1 s plus the events MV), `/sync/institute_locations` **7.6 s**. Cold, the underlying MVs took 42.2 s / 21.5 s / 26.5 s. Everything else is under a second. Callers should fire them concurrently and never in an awaited chain — admin-react's System Config save did exactly that and cost 29 s per college create until 2026-08-24.

Refreshes are debounced per MV via `pgRefreshMvs` (`SEARCH_MV_REFRESH_TTL_SECONDS`, default 900; `institutes_master`, `institute_campus_cources` and `del_index_institute_campus_cources` override to 30 s so a user-initiated save is visible immediately). Outcomes land in `search_engine.refresh_log`.

The sync service is the largest module (~260KB); most of its bulk is the legacy SQL and ES bulk-insert logic kept behind the engine flag.

---

## API Endpoints

All endpoints are **POST** and return a success message on completion.

### Academic Data

| Route | Payload | Description |
|-------|---------|-------------|
| `/sync/degrees/streams/specialisations` | — | Sync degree-stream-specialisation hierarchy |
| `/sync/degrees/streams/specialisations/events` | — | Sync events degree-stream-specialisation index |
| `/sync/degree_data` | `SyncDateRequest` | Sync degree data |
| `/sync/degree_department_master` | `syncTypeRequest` (type: LS, SSW, LSP, SSWLSP) | Sync degree-department master. Default type: LSP |
| `/sync/degree_department_master_not_cm` | `SyncDateRequest` | Sync degree-department NOT CM variant |
| `/sync/specialization_master` | `syncTypeRequest` (type: LS, LSP_SCW, LSP & SCW) | Sync specialisation master. Default: LSP & SCW |
| `/sync/specialization_master_cas` | `syncTypeRequest` (type: CAS, NOT CAS, NOT_CAS) | Sync specialisation CAS/NOT CAS |
| `/sync/crud_degree_department` | `SyncDateRequest` | Sync institute CRUD degree-department index |

### Geography

| Route | Payload | Description |
|-------|---------|-------------|
| `/sync/countries` | `SyncDateRequest` | Sync countries |
| `/sync/states` | `SyncDateRequest` | Sync states |
| `/sync/cities` | `SyncDateRequest` | Sync cities |
| `/sync/citiesDetails` | `SyncDateRequest` | Sync cities with country and state details |
| `/sync/state_with_country` | `SyncDateRequest` | Sync states with parent country |
| `/sync/locationsDetails` | `SyncDateRequest` | Sync locations with city, country, state |

### Universities

| Route | Payload | Description |
|-------|---------|-------------|
| `/sync/universities_master` | `SyncDateRequest` | Sync universities master |
| `/sync/universties_li` | `SyncDateRequest` | Sync universities LI variant |
| `/sync/universties_scw` | `SyncDateRequest` | Sync universities SCW variant |
| `/sync/universties_ssw` | `SyncDateRequest` | Sync universities SSW variant |

### Institutes

| Route | Payload | Description |
|-------|---------|-------------|
| `/sync/institutes_master` | `SyncDateRequest` | Sync institutes master |
| `/sync/institute_campus_cources` | `SyncDateRequest` | Sync institute campus courses |
| `/sync/institute_degree` | `SyncDateRequest` | Sync institute degree view |
| `/sync/institute_specialisation` | `SyncDateRequest` | Sync institute specialisation |
| `/sync/institute_streams` | `SyncDateRequest` | Sync institute streams |
| `/sync/institute_locations` | `SyncDateRequest` | Sync institute locations |

### Student Filters

| Route | Payload | Description |
|-------|---------|-------------|
| `/sync/college_name_master` | `syncTypeRequest` (type: LS, LSP) | Sync college name master |
| `/sync/student_state_master` | `SyncDateRequest` | Sync student state-city master |
| `/sync/student_city_master` | `syncTypeRequest` (type: LSP, SSW, NOT_SSW) | Sync student city master |
| `/sync/skill_master` | `SyncDateRequest` | Sync skill master |
| `/sync/student_crud_skill` | `SyncDateRequest` | Sync student CRUD skill data |

### Corporate

| Route | Payload | Description |
|-------|---------|-------------|
| `/sync/college_name_corporates` | `syncTypeRequest` (type: CA, NOT_CA) | Sync college name corporate filters |
| `/sync/city_role_corporate_master` | `syncTypeRequest` (type: RP, HS, NOT_RP_HS) | Sync city role corporate master |
| `/sync/corporate_locations` | `SyncDateRequest` | Sync corporate locations |
| `/sync/corporate_list` | `SyncDateRequest` | Sync corporate list |

### Master Data

| Route | Payload | Description |
|-------|---------|-------------|
| `/sync/sectordata` | `SyncDateRequest` | Sync sector data |
| `/sync/functiondata` | `SyncDateRequest` | Sync function data |
| `/sync/campus_preview_list` | `SyncDateRequest` | Sync campus preview new list |

### Index Management

| Route | Payload | Description |
|-------|---------|-------------|
| `/sync/del_index_institute_campus_cources` | `DelCourseRequest` (`course_id`) | Delete a specific course from institute campus course index |

---

## Request DTOs

- **`SyncDateRequest`:** `{ query_date?: "YYYY-MM-DD" }` — optional date for incremental sync (e.g., `"1990-01-01"` for full sync)
- **`syncTypeRequest`:** Extends `SyncDateRequest` with `{ type?: string }` — sub-variant filter (e.g., LS, LSP, SCW, CAS)
- **`DelCourseRequest`:** `{ course_id: string }` — UUID of course to delete

---

## Key Features

**Current (PG engine — all envs):**

- **Matview refresh:** each endpoint refreshes the `search_engine` MV(s) backing its dataset via `search_engine.refresh_one`, concurrently so readers are never blocked
- **Per-MV debounce:** `pgRefreshMvs` skips an MV refreshed successfully inside its TTL; user-initiated saves override to 30 s
- **Observability:** every refresh writes `view_name`, `started_at`, `duration_ms`, `row_count`, `status` and `error` to `search_engine.refresh_log` — the first place to look when search data looks stale or a save feels slow
- **Datasets with no MV** no-op with a log rather than erroring

**Legacy (ES engine — retired on every environment, kept behind the flag):**

- **Incremental sync:** `query_date` synced only records modified after a given date. Under PG the parameter is inert
- **Type variants:** Many indices have multiple variants (e.g., degree_department_ls, degree_department_ssw_lsp) serving different filter contexts — these map to separate MVs under PG
- **SQL → ES pipeline:** Reads from PostgreSQL views/tables, transforms, and bulk-inserts into ES
- **Index aliasing:** Uses timestamped indices with aliases for zero-downtime reindexing
- **Index config:** All ES index mappings and settings defined in `sync/index/indexConfig.ts` (~249KB)
