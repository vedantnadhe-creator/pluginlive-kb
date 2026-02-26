# Settings Module

**Route:** `/setting`
**Frontend:** `institute-react/src/modules/Settings/`

## Overview

The Settings module allows TPO users to view and update institute campus information, including institute details, tax information, partner configurations, and additional settings. Changes are synced to ElasticSearch for search index consistency.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Settings page layout with tabbed sections |
| `Components/InstituteInfo/` | Institute info | Institute name, address, contact, university details |
| `Components/TaxInfo/` | Tax info | GST, PAN, and tax-related settings |
| `Components/Partners/` | Partners | Partner/MOU configuration |
| `Components/AddtionalInfo/` | Additional info | Extra institute settings |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Institute Info

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getInstituteInfo` | `/institutes/instituteCampus/{id}` | GET | Fetch current institute campus details |
| `updateInstituteInfos` | `/institutes/instituteCampus/{id}` | PUT | Update institute details, then syncs to ElasticSearch |

### ElasticSearch Sync

After updating institute info, the module triggers an ElasticSearch sync:
- **Endpoint:** `/sync/institutes_master` (POST)
- **Payload:** `{ query_date: "yyyy-mm-dd" }` (today's date)
- **Request util:** `elasticSearchSyncRequest`

### Master Data Lookups

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getUniversityList` | `/search/universities` | POST (ES) | ElasticSearch-based university search for association |
| `getMasterSearchApi` | `/search/{type}` or `/students/crud/skill` | POST/GET | Generic master data search (skills, cities, etc.) |

---

## State Shape

```js
{
  instituteData: {},
  universityList: []
}
```

---

## Key Features

- **ElasticSearch sync:** Institute updates are immediately synced to `institutes_master` ES index
- **University association:** Link institute to a university via ES search
- **Master search:** Generic search across skills, cities, and other master data
- **Tabbed layout:** Institute info, tax info, partners, additional info sections
- **Uses `systemConfig.universities`:** Predefined ES payload for university search
