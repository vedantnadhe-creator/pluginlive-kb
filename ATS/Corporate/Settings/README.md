# Settings Module

**Route:** `/settings`
**Frontend:** `corporate-react-1/src/modules/Settings/`

## Overview

The Settings module manages corporate branch/office locations. Corporate users can add, edit, delete, and list branch locations. All mutations are synced to ElasticSearch via the `corporate_list` sync endpoint.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Settings page with branch management |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getCorporateLocationsList` | `/corporates/{corpId}/branch` | GET | Paginated branch/location list (`currentPage`, `pageLimit`) |
| `addCorporateBranch` | `/corporates/{corpId}/branch` | POST | Add new branch. Syncs to ES `corporate_list` |
| `getLocationDetails` | `/corporates/branch/{locationId}` | GET | Single branch details |
| `updateLocationAPI` | `/corporates/{corpId}/branch/{locationId}` | PUT | Update branch details. Syncs to ES `corporate_list` |
| `deleteLocationAPI` | `/corporates/branch/{locationId}` | DELETE | Delete a branch. Syncs to ES `corporate_list` |

### ElasticSearch Sync

After every add/update/delete operation:
- **Endpoint:** `/sync/corporate_list` (POST)
- **Payload:** `{ query_date: "yyyy-mm-dd" }` (today's date)
- **Request util:** `elasticSearchSyncRequest`

---

## State Shape

```js
{
  corporateLocationsList: {},
  singleLocation: {}
}
```

---

## Key Features

- **Branch CRUD:** Full create, read, update, delete for corporate locations
- **ElasticSearch sync:** Every mutation syncs to `corporate_list` ES index
- **Pagination:** `pageLimit=10`, `currentPage` (1-indexed)
- **Success/Error messaging:** Feedback for all operations
