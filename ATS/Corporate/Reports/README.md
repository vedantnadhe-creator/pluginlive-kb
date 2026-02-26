# Reports Module

**Routes:**
- `/reports/role/published` — Roles Published to Colleges
- `/reports/application/status` — Candidate Application Status
- `/reports/drive/level` — Applicants at Drive Level
- `/reports/hiring/status` — Hiring Status
- `/reports/interview/schedule` — Interview Schedule

**Frontend:** `corporate-react-1/src/modules/Report/`

## Overview

The Reports module provides five distinct hiring reports for corporate users. Each report has its own route, container, and data source, with shared filter components (city, tier, college, role, round, degree/department, date range) and Excel export capabilities.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/RolesPublished.js` | Roles Published | Roles published to colleges report |
| `Container/CandidateApplication.js` | Application Status | Candidate application status report |
| `Container/ApplicantsDriveLevel.js` | Drive Level | Applicants at drive level report |
| `Container/HiringStatus.js` | Hiring Status | Role-wise hiring status report |
| `Container/InterviewSchedule.js` | Interview Schedule | Candidate interview schedule report |
| `Partials/RolesPublished/` | Roles table | Roles published table and partials |
| `Partials/CandidateApplication/` | Application table | Application status table |
| `Partials/ApplicantsDriveLevel/` | Drive table | Drive-level applicant table |
| `Partials/HiringStatus/` | Hiring table | Hiring status table |
| `Partials/InterviewSchedule/` | Schedule table | Interview schedule table |
| `Partials/Filter/` | Shared filters | Common filter components |
| `Partials/CommonTable/` | Common table | Shared table component |
| `Partials/Export/` | Export | Excel/CSV export component |
| `CommonFunction/Function.js` | Utilities | Shared report helper functions |
| `ExcelHeaderData.js` | Excel config | Excel export header mappings |

---

## Redux Actions & API Endpoints

**File:** `action.js`

### Report Data APIs

| Action | API Base | Method | Purpose |
|--------|----------|--------|---------|
| `getRolePublishedToCollege` | `/corporates-reports/rolepublishtocollege/lists` | GET | Roles published to colleges with city, tier, date range, search, sort |
| `getCandidateApplicationStatus` | `/corporates-reports/candidateappstatus/lists` | GET | Candidate application status with college, role, offered, accepted filters |
| `getApplicationDriveLevel` | `/corporates-reports/applicationdrivelevel/lists` | GET | Drive-level applicant data with round, status, course type, degree, rank filters |
| `hiringLevelDetails` | `/corporates-reports/rolewisehiringstatus/lists` | GET | Hiring status per role with round, course type, rank filters |
| `interviewDetails` | `/corporates-reports/candidateinterviewschedule/lists` | GET | Interview schedule with round, course type, rank filters |

### Filter APIs

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `cityDetails` | `/cityrolecorporatesmaster/lists` | GET | City filter options with flag-based pagination |
| `tierDetails` | `/tiercorporatesfilter/lists` | GET | Tier filter options |
| `collegeDetails` | `/collegenamecorporatesfilter/lists` | GET | College name filter options |
| `roleDetails` | `/rolecorporatesfilter/lists` | GET | Role filter options |
| `roundDetails` | `/interviewroundmaster/lists` | GET | Round filter options |
| `courseTypeDetails` | `/coursetypemaster/lists` | GET | Course type filter options |
| `statusDetails` | `/interviewstatusroundmaster/lists` | GET | Interview status/round master options |
| `degreeDetails` | `/degreedepartmentreport/lists` | GET | Degree-department filter options |

### Supporting APIs

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `studentDetails` | `/students/{studentId}` | GET | Individual student details for drill-down |

---

## Common Filter Parameters

All report APIs share these parameters:
- **corpid:** Corporate ID (mandatory)
- **size/page:** Pagination (1-indexed pages)
- **sort/orderBy:** Column sorting
- **tier, city, college, role:** Filter by respective dimensions
- **createdAtStart/createdAtEnd:** Date range filter
- **appenddate:** Append date filter
- **excel flag:** When `true`, dispatches to `SET_EXCEL_DATA` for export instead of display

---

## Key Features

- **Five report types:** Each with dedicated API, container, and table
- **Excel export:** All reports support Excel export via `excel=true` flag
- **Shared filters:** City, tier, college, role, round, course type, degree
- **Rank filtering:** `rank` and `ranksign` (≤, ≥, =) for rank-based filtering
- **Paginated filters:** Filter dropdowns themselves are paginated with search
- **Date range:** `createdAtStart`, `createdAtEnd`, `appenddate` for temporal filtering
