# Search Module

**Controller Prefix:** `/search`
**Auth:** User (API key)
**Source:** `search-service-1/src/modules/search/`

## Overview

The Search module provides generic, parameterized search across all ElasticSearch data types (degrees, streams, skills, universities, specialisations, etc.) and dedicated geography lookup endpoints for countries, states, and cities. It is the primary search interface consumed by all frontend portals (Admin, Corporate, Institute, Student).

---

## API Endpoints

### Generic Search

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/search/:type` | User | Search any data type. `:type` is a `DATA_SET_TYPES` enum value (e.g., `degrees`, `streams`, `skills`, `universities`, `specialisations`, etc.) |

**Request Body (`SearchRequest`):**
```json
{
  "q": "search term",
  "autoCorrect": false,
  "removeSpecialChars": true,
  "size": 100,
  "page": 1,
  "filters": [{ "field": "fieldName", "value": "fieldValue" }],
  "should": [{ "field": "fieldName", "value": "fieldValue" }]
}
```

### Degree-Stream Hierarchical Search

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/search/degrees/streams` | User | Search degrees with nested streams. Extra param: `childSize` for stream result count |
| POST | `/search/degrees/streams/specialisations` | User | Search across degrees → streams → specialisations hierarchy. Supports `searchType`: ALL, DEGREE, STREAM, SPECIALISATION |
| POST | `/search/degrees/streams/specialisations/events` | User | Same hierarchical search but for event-specific degree-stream-specialisation index |

### Geography Lookups

| Method | Route | Auth | Parameters | Description |
|--------|-------|------|------------|-------------|
| GET | `/search/countries` | User | `search`, `currentPage`, `pageLimit`, `is_active`, `sort`, `order`, `groupBy` | Country list. Default pageLimit=1000 |
| GET | `/search/states` | User | `search`, `countryId`, `currentPage`, `pageLimit`, `sort`, `order` | State list, filterable by country |
| GET | `/search/cities` | User | `search`, `countryId`, `stateId`, `currentPage`, `pageLimit`, `sort`, `order` | City list, filterable by country/state |
| GET | `/search/states/cities` | User | Same as cities | Combined state+city lookup. Default pageLimit=10000 |

---

## Service Methods (`SearchServices`)

The service layer (`search.services.ts`, ~37KB) handles:
- **ES query building:** Constructs multi-match queries with boosted fields, fuzzy matching, auto-correct
- **Synonym support:** Queries against synonym-enabled indices
- **Hierarchical aggregation:** Degree → Stream → Specialisation nested aggregation queries
- **Geo data:** Country/state/city lookups with filtering and pagination from ES

---

## Key Features

- **50+ data types:** All defined in `DATA_SET_TYPES` enum, each mapped to a specific ES index config
- **Auto-correct:** Optional fuzzy search with `autoCorrect` flag
- **Special char handling:** Strip special characters from search terms with `removeSpecialChars`
- **Filter + Should queries:** Supports both mandatory (`filters`) and optional (`should`) ES query clauses
- **Search type scoping:** Hierarchical search can target just degrees, streams, or specialisations
- **Index prefix:** All index names are prefixed with `INDEX_PREFIX` env var for environment isolation
