# TPO Requests Module

**Route:** `/tpoRequests`
**Frontend:** `institute-react/src/modules/TPORequests/`

## Overview

The TPO Requests module manages job-specific student requests that require TPO action. Students may request eligibility exceptions, express interest, or need approval for specific job roles. TPO users can view pending/completed requests, apply filters, approve/reject in bulk, and view detailed consent information.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Request listing and data orchestration |
| `Components/DashboardCard/` | Dashboard cards | Metrics cards (pending, urgent counts) |
| `Components/TPOInfoTable/` | Request table | Paginated request listing table |
| `Components/Filters/` | Filter panel | Company, role, reason, priority filters |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getTPOMetrics` | `/corporate/institute/{campusId}/requestMetrics` | GET | Request metrics (pending_count, urgent_count) |
| `getTpoUserList` | `/corporate/institute/{campusId}/requestList` | POST | Paginated request listing with filters: flag (PENDING/COMPLETED), search, sort, order, company, priorities, roles, rules |
| `updateAllRequestList` | `/corporate/institute/{campusId}/updaterequest` | PUT | Bulk approve/reject requests. Supports selectAll or specific student-role pairs |
| `getConsentDrawerList` | `/corporate/student/{studentId}/requestDrawer` | POST | Consent/request detail drawer data for a student |
| `getTPOFilter` | `/corporate/institute/{campusId}/requestFilter` | GET | Available filter options (roles, companies) with search support |

---

## State Shape

```js
{
  tpoMetrics: {},
  tpoUserList: {},
  tpoFilter: {}
}
```

---

## Key Features

- **Flag-based views:** PENDING vs COMPLETED request lists
- **Bulk operations:** Approve/reject all or selected student-role combinations
- **Priority filtering:** Filter by request priority levels
- **Reason filtering:** Filter by request reason types
- **Company & role filtering:** Filter by specific company or role with search
- **Consent drawer:** Detailed request information per student
- **Sort:** Column-based sorting with ASC/DESC order
- **Pagination:** `pageLimit=10`, `pageNo` (0-indexed)
