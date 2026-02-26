# Ingest Module

**Controller Prefix:** `/ingest`
**Auth:** Admin only
**Source:** `search-service-1/src/modules/ingest/`

## Overview

The Ingest module provides CRUD operations for individual ElasticSearch documents. It allows admins to create, update, and delete documents in any index type. All operations are parameterized by `DATA_SET_TYPES` and use filter-based targeting for updates and deletes. Also provides bulk insert and upsert utilities used by the Sync module.

---

## API Endpoints

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/ingest/:type` | Admin | Create a new document in the specified index. Returns created document with `_id` |
| PUT | `/ingest/:type` | Admin | Update documents matching filters. Uses ES `updateByQuery` with script |
| DELETE | `/ingest/:type` | Admin | Delete documents matching filters. Uses ES `deleteByQuery` |

**`:type`** — Any value from `DATA_SET_TYPES` enum (e.g., `degrees`, `streams`, `skills`, `universities`, etc.)

---

## Request DTOs

### Create (`Document`)
```json
{
  "document": { "name": "Computer Science", "type": "UG", ... }
}
```

### Update (`UpdateDocument`)
```json
{
  "document": { "name": "Updated Name" },
  "filters": [{ "field": "id", "value": "some-uuid" }]
}
```

### Delete (`DeleteDocument`)
```json
{
  "filters": [{ "field": "id", "value": "some-uuid" }]
}
```

---

## Service Methods (`IngestServices`)

| Method | Description |
|--------|-------------|
| `saveDocument(type, document)` | Create single document with UUID. Adds `orderType` for degree types |
| `updateDocument(type, payload)` | Update by query with filter-generated bool query and script |
| `deleteDocument(type, payload)` | Delete by query with filter-generated bool query |
| `bulkInsert(items, indexName)` | Bulk insert with auto-generated UUIDs (used by Sync) |
| `bulkInsertOrUpdate(items, indexName, key_name)` | Bulk upsert using `doc_as_upsert` (used by Sync) |
| `updateAlias(aliasName, indexName)` | Swap ES alias to new index, delete old indices |

---

## Key Features

- **Type validation:** All operations validate the `:type` parameter against `DATA_SET_TYPES`
- **Filter-based targeting:** Updates and deletes use `term` queries built from filter arrays
- **Degree type ordering:** Automatically adds `orderType` field for degree documents based on type (UG, PG, etc.)
- **Script-based updates:** Generates ES painless-style scripts from document field entries
- **Alias management:** `updateAlias` handles zero-downtime index swaps
- **Bulk operations:** `bulkInsert` (insert-only) and `bulkInsertOrUpdate` (upsert) for sync pipelines
