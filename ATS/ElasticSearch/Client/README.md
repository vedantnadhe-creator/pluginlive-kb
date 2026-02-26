# Client Module

**Type:** Internal service (no HTTP endpoints)
**Source:** `search-service-1/src/modules/client/`

## Overview

The Client module is a singleton wrapper around the `@elastic/elasticsearch` Client. It provides a centralized, error-handled interface for all ElasticSearch operations used by other modules (Search, Ingest, Sync, Synonyms, Cleanup).

---

## Service Methods (`ClientServices`)

### Core Operations

| Method | ES Operation | Description |
|--------|-------------|-------------|
| `search(params)` | `client.search()` | Execute a search query. Returns `SearchResponse` |
| `count(params)` | `client.count()` | Count documents matching a query |
| `create(params)` | `client.create()` | Create a single document |
| `updateByQuery(params)` | `client.updateByQuery()` | Update documents matching a query using a script |
| `deleteByQuery(params)` | `client.deleteByQuery()` | Delete documents matching a query |
| `bulk(indexName, items)` | `client.bulk()` | Bulk insert/update with `refresh: true` |

### Synonym Operations

| Method | ES Operation | Description |
|--------|-------------|-------------|
| `getSynonym(params)` | `client.synonyms.getSynonym()` | Fetch synonym set rules |
| `putSynonym(params)` | `client.synonyms.putSynonym()` | Update synonym set rules |

### Index Management

| Method | ES Operation | Description |
|--------|-------------|-------------|
| `createIndex(indexName, query)` | `client.indices.create()` | Create index with mappings and settings |
| `isIndexExist(indexName)` | `client.indices.exists()` | Check if an index exists |
| `getIndicesForAlias(aliasName)` | `client.indices.getAlias()` | Get all indices behind an alias |
| `updateAlias(aliasName, newIndex, oldIndices)` | `client.indices.updateAliases()` | Swap alias from old indices to new index |
| `deleteIndex(oldIndex)` | `client.indices.delete()` | Delete an index |

---

## Configuration

- **ES URL:** `ES_URL` env var (default: `http://localhost:9200`)
- **Auth:** Basic auth via `ES_USER_NAME` / `ES_PASSWORD`
- **TLS:** `rejectUnauthorized: false` (accepts self-signed certs)

---

## Key Features

- **Centralized error handling:** All operations throw `HttpException` with status 417 on failure
- **Global singleton:** Injected into all modules that need ES access
- **Alias-based reindexing:** `updateAlias` + `deleteIndex` enables zero-downtime index swaps
- **Bulk with refresh:** Bulk operations use `refresh: true` for immediate searchability
