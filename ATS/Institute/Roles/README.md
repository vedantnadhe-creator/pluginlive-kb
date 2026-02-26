# Roles Module

**Route:** `/roles`
**Frontend:** `institute-react/src/modules/Roles/`

## Overview

The Roles module displays job roles available to the institute campus. TPO users can view role listings filtered by tier, view detailed job information, accept/reject roles, save/unsave roles, share jobs via email, and view corporate details.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Orchestrates roles listing and data fetching |
| `Partials/RolesInfoTable/` | Roles table | Paginated table of job roles |
| `Partials/StatusTabs/` | Tab navigation | Tabs for filtering roles by status |
| `Partials/ViewIndividualRole/` | Role detail | Detailed view of an individual role |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getRolesListData` | `/corporates/jobsByInstitute/{id}/lists` | GET | Paginated role listing filtered by institute tier |
| `getJobDetails` | `/corporates/{corpId}/jobs/{roleId}/instituteCampus/{id}` | GET | Detailed job/role information |
| `acceptOrReject` | `/corporates/jobs/{jobId}/jobsByInstitute/{id}/updateStatus` | POST | Accept or reject a role for the institute |
| `updateRoleData` | `/corporates/jobs/{id}/jobsByInstitute/{id}/saved` | POST | Save/unsave a role |
| `corporateAboutUs` | `/corporates/{corpId}` | GET | Corporate about-us details |
| `getCities` | `/search/cities` | GET | City list for location filters |
| `jobSharingEmail` | `/users/{userId}/jobSharing` | POST | Share job role via email |
| `getUserCorpList` | `/user?coporateId={id}` | GET | Users associated with a corporate |

---

## State Shape

```js
{
  rolesList: {},
  singleRoleDetails: {},
  aboutUs: {},
  cities: [],
  jobId: null,
  pageNum: 0
}
```

---

## Key Features

- **Tier-based filtering:** Roles filtered by institute tier (tier1, tier2, etc.)
- **Accept/Reject:** TPO can accept or reject job roles for their campus
- **Save/Unsave:** Bookmark roles for quick access
- **Job Sharing:** Email job details to stakeholders
- **Pagination & Sort:** Standard pagination with column-based sorting
