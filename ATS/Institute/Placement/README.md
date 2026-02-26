# Placement Module

**Route:** `/placement`
**Frontend:** `institute-react/src/modules/Placement/`

## Overview

The Placement module manages "Batch Folders" — a hierarchical view of students organized by education type, domain, degree, and stream. TPO users can browse course-wise student data, view placement status, track year-of-passing, download resumes in bulk, and manage batch history.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Orchestrates placement data and navigation |
| `FolderPath/` | Breadcrumb | Hierarchical folder navigation (domain → degree → stream) |
| `Header/` | Page header | Title and action buttons |
| `FilterData/` | Filters | Filter controls for placement data |
| `Table/` | Data table | Student placement table |
| `Table/TableData/` | Table body | Table rows and data rendering |
| `Table/TableFilter/` | Table filter | Inline table filters |

---

## Redux Actions & API Endpoints

**File:** `action.js`

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getPlacementData` | `/institutes/instituteCampus/{id}/courses/overView` | GET | Course overview grouped by educationType, domain, degree. Supports search |
| `getTableData` | `/students/institutes/{id}/batch/list` | POST | Paginated student batch list |
| `getPlacementStudent` | `/students/institutes/{id}/batch/list` | POST | Student list for a specific batch (same endpoint, different context) |
| `getUserBatchHistory` | `/institutes/{id}/batch/user/{userId}/history` | GET | User's batch browsing history |
| `updateUserBatchHistory` | `/institutes/{id}/batch/user/history` | PUT | Save/update user's batch history |
| `getYear` | `/students/institutes/{id}/yearOfPassing` | GET | Year-of-passing list with optional filters (educationLevel, domain, degree, stream) |
| `getPreviewData` | `/students/{studentId}` | GET | Single student preview data |
| `resumeBulkDownload` | `/students/resume/bulkdownload` | POST | Bulk download student resumes (returns blob or triggers async) |
| `resumeBulkDownloadJobRoles` | `/students/resume/bulkdownload/jobRoles` | POST | Bulk resume download for job roles context |

---

## State Shape

```js
{
  tableData: {},
  batchHistory: []
}
```

---

## Key Features

- **Hierarchical folder navigation:** educationType → domain → degree → stream
- **GroupBy parameter:** `groupBy` controls the folder grouping level
- **Batch history:** Tracks and restores user's last browsed batch path
- **Resume bulk download:** Supports blob download for small sets, async for large sets
- **Year of passing filter:** Filter students by graduation year
