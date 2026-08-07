# Applied Roles Module

**Routes:**
- `/applied_roles` — All applied roles
- `/applied_roles/:Status` — Applied roles filtered by status

**Frontend:** `student-react/src/modules/Applied_Roles/`

## Overview

The Applied Roles module tracks all roles a student has applied to. It provides a paginated listing with search and status filtering, along with metrics showing counts by application status. Also tracks new role counts for badge notifications.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Applied roles listing with filters |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getAppliedRoleList` | `/students/roles/applied/list/{studentId}` | GET (Student) | Paginated applied roles. Filters: search, filter (status), currentPage. pageLimit=10 |
| `getAppliedRoleMetrics` | `/students/roles/{studentId}/metrics` | GET (Student) | Application status metrics (counts per status). On 401, clears session and redirects to auth |
| `getNewRoleMetrics` | `/corporates/roleMetrics/{studentId}/count` | PUT (Corp) | New role count for notification badge. Payload: `{ count: true }` |

---

## State Shape

```js
{
  appliedRoleList: {},
  appliedRoleMetrics: {},
  viewRoleData: {},
  newRoleCount: {}
}
```

---

## Key Features

- **Status filtering:** Filter by application status via URL param (`:Status`)
- **Metrics dashboard:** Count cards showing applied, shortlisted, offered, etc.
- **New role badge:** Tracks new floated role count for notifications
- **Auth error handling:** 401 errors trigger session clear and redirect to auth URL
- **Pagination:** `pageLimit=10`, `currentPage`

---

## Related

- [Applied-Role Snapshots](applied-role-snapshots.md) — freezes candidate profile/education/course data at apply time so later profile edits do not retroactively change submitted applications. Flag: APPLIED_SNAPSHOT_READS.
