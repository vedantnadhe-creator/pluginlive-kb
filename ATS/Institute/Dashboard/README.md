# Dashboard Module

**Route:** `/tpoDashboard`
**Frontend:** `institute-react/src/modules/Dashboard/`

## Overview

The Dashboard provides TPO users with a high-level overview of drives, roles, and candidate activity for their institute campus. It aggregates data from corporate drives and displays metrics, role details, and candidate statuses.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Orchestrates dashboard layout and data fetching |
| `Partials/DashboardDrive/` | Drive list | Displays corporate drive listings |
| `Partials/DashboardRoles/` | Roles overview | Shows roles associated with drives |
| `Partials/DriveRoleTable/` | Role table | Tabular view of drive roles |
| `Partials/DriveTabs/` | Tab navigation | Tabs for switching between drive views |
| `Partials/DrivesInfoTable/` | Drive info | Detailed drive information table |
| `Partials/CoursesStatus/` | Course stats | Course-wise placement status |
| `Partials/CoursesTable/` | Course table | Tabular course data |
| `Partials/CourseFilter/` | Filter | Course-based filter controls |
| `Partials/UsersFilter/` | Filter | User-based filter controls |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getDashboardDriveList` | `/instituteCampus/{id}/corporates/list` | GET | Paginated corporate drive list with search, sort, occurrence filter |
| `getDashboardRoleList` | `/corporates/jobsByInstitute/{id}/lists` | GET | Roles for a specific corporate, filtered by tier, occurrence, search |
| `getDashboardDriveSingleList` | `/corporates/instituteCampus/{id}/role/{roleId}/drive/list` | GET | Drives for a specific role |
| `getCandidateDriveList` | `/students/drive/{driveId}/candidate/list` | GET | Candidate list for a drive with stage/status filters |
| `getRoleMetrics` | `/corporates/{driveId}/roles/metrics` | GET | Role-level metrics (counts per stage) |
| `getDegreeAndDepartMent` | `/corporate/role/{roleId}/degree` | GET | Degree & department data for a role |
| `getSingleRoleStudentDetails` | `/corporate/role/{roleId}/{studentId}` | GET | Individual student details within a role |
| `getSpecialisationList` | `/student/specializationmaster/lists` | GET | Specialisation master list for filters |

---

## State Shape

```js
{
  dashboardDriveList: [],
  dashboardRoleList: [],
  dashboardDriveSingleList: [],
  candidateDriveList: [],
  roleMetrics: {},
  degreeList: [],
  singleRoleStudentDetails: {},
  specialisationList: []
}
```

---

## Filters & Parameters

- **Occurrence:** upcoming / ongoing / completed
- **Search:** text-based search across drives/roles
- **Sort:** column-based sorting with asc/desc order
- **Pagination:** `pageLimit=10`, `currentPage` (0-indexed)
- **Stage filters:** `all_candidates`, `offer`, or specific round names
- **Candidate status:** `SCHEDULED`, `SHORTLISTED`, `SELECTED`
