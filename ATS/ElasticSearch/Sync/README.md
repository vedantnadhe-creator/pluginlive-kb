# Sync Module

**Controller Prefix:** `/sync`
**Auth:** Admin only
**Source:** `search-service-1/src/modules/sync/`

## Overview

The Sync module handles data synchronization from PostgreSQL (institute schema) to ElasticSearch indices. Each endpoint triggers a full or incremental sync for a specific index type. All endpoints accept an optional `query_date` parameter for incremental syncs (only records updated after that date). The sync service is the largest module (~260KB) containing all SQL queries and ES bulk insert logic.

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

- **Incremental sync:** `query_date` allows syncing only records modified after a given date
- **Type variants:** Many indices have multiple variants (e.g., degree_department_ls, degree_department_ssw_lsp) serving different filter contexts
- **SQL → ES pipeline:** Reads from PostgreSQL views/tables, transforms, and bulk-inserts into ES
- **Index aliasing:** Uses timestamped indices with aliases for zero-downtime reindexing
- **Index config:** All ES index mappings and settings defined in `sync/index/indexConfig.ts` (~249KB)
