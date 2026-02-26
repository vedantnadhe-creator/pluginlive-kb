# Synonyms Module

**Controller Prefix:** `/synonyms`
**Auth:** Admin only
**Source:** `search-service-1/src/modules/synonyms/`

## Overview

The Synonyms module manages ElasticSearch synonym sets that improve search relevance. Synonyms allow the search to treat related terms as equivalent (e.g., "CS" ↔ "Computer Science"). Each `DATA_SET_TYPE` has a corresponding named synonym set in ES.

---

## API Endpoints

| Method | Route | Auth | Parameters | Description |
|--------|-------|------|------------|-------------|
| GET | `/synonyms?type=:type` | Admin | `type` (DATA_SET_TYPES enum) | Fetch all synonym rules for a data type |
| PUT | `/synonyms` | Admin | Body: `UpdateSynonymsSet` | Update synonym rules for a data type |

---

## Request DTO

### Update (`UpdateSynonymsSet`)
```json
{
  "id": "degrees",
  "synonyms_set": [
    { "id": "rule-1", "synonyms": "CS, Computer Science, CompSci" },
    { "id": "rule-2", "synonyms": "IT, Information Technology" }
  ]
}
```

---

## Synonym Set Mapping

| Data Type | ES Synonym Set ID |
|-----------|-------------------|
| `degrees` | `my-synonyms-degree` |
| `streams` | `my-synonyms-stream` |
| `skills` | `my-synonyms-skill` |
| `universities` | `my-synonyms-universities` |
| `specialisations` | `my-synonyms-specialisations` |
| `institutes_campuses` | `my-synonyms-institutes_campuses` |

---

## Key Features

- **Per-index synonyms:** Each data type has its own synonym set for targeted relevance tuning
- **ES native synonyms:** Uses ES `synonyms.getSynonym` / `synonyms.putSynonym` APIs
- **Type validation:** Validates the data type against `DATA_SET_TYPES` enum before operations
