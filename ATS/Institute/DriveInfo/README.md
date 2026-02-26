# Drive Info Module

**Route:** `/drives/driveInfo`
**Frontend:** `institute-react/src/modules/DriveInfo/`

## Overview

The Drive Info module displays detailed information about a specific placement drive. It shows the drive's candidate list and drive metadata, scoped to the institute campus.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Drive info page layout |
| `Partials/Details.js` | Drive details | Drive metadata display |
| `Partials/DriveInfoTable/` | Candidate table | Paginated candidate list for the drive |

---

## Redux Actions & API Endpoints

**File:** `action.js`

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getStudentDriveListData` | `/students/drive/{driveId}/candidate/list?collegeId={campusId}` | GET | Paginated candidate list for a drive, filtered by institute campus |
| `getViewDriveInfo` | `/corporates/drive/{driveId}/institute/{campusId}` | GET | Drive metadata and details |

---

## State Shape

```js
{
  studentsDriveList: [],
  viewDriveInfo: {}
}
```

---

## Key Features

- **Campus-scoped:** All data filtered by `instituteCampusId`
- **Pagination:** `pageLimit=10`, `pageNo` (0-indexed)
- **Drive details:** Corporate drive metadata with institute context
