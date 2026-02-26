# Role Page Module

**Route:** `/rolePage`
**Frontend:** `corporate-react-1/src/modules/RolePage/`

## Overview

The Role Page module provides a category-based job role listing view. It supports job category filtering (Placement, Internship, etc.), status/role/schedule filters, candidate export (CSV/Google Sheets), degree/department/domain lookups, interview round management, and role duplication. This serves as an alternative role management interface alongside the main Roles module.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Role page layout and data orchestration |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Role Listing

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getJobRoleList` | `/corporates/corporate/{corpId}/jobs` | POST | Paginated job role list with payload-based filters |
| `getJobCategory` | `/corporates/filters/jobtype/corporate/{corpId}/jobs` | GET | Available job category/type filter options |

### Filters

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getStatusFilter` | `/corporates/filterStatus/corporate/{corpId}/jobs?jobCategory={cat}` | GET | Status filter options per job category |
| `getRoleFilter` | `/corporates/filterRole/corporate/{corpId}/jobs?jobCategory={cat}` | GET | Role filter options per job category |
| `getScheduleFilter` | `/corporates/filterEvaluation/corporate/{corpId}/jobs?jobCategory={cat}` | GET | Evaluation schedule filter options |
| `getDomainList` | `/institutes/{campusId}/domain` | GET | Domain list filtered by job category |
| `getDegreeList` | `/institutes/{campusId}/degree` | GET | Degree list filtered by domain and job category |
| `getDepartmentList` | `/institutes/{campusId}/streams` | POST | Department/stream list |
| `getYear` | `/students/institutes/{campusId}/yearOfPassing` | GET | Year of passing filter |

### Export

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `exportCandidate` | `/students/role/{roleId}/instituteCampus/{campusId}/candidate/{type}/export` | PUT | Export candidates (CSV blob or Google Sheets) |
| `getExportFiledData` | `/students/institutes/heading/export` | GET | Available export field headings |
| `exportCSV` | `/corporates/corporate/{corpId}/export/{type}` | GET | Export roles data with domain, degree, stream, year, degreeType filters |

### Interview Rounds

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `addNewRound` | `/corporates/role/{roleId}/interviewRounds` | GET | Fetch interview rounds for a role |
| `updateNewRound` | `/corporates/role/{roleId}/interviewRounds` | PUT | Add/update interview rounds |

### Supporting Data

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getCorporateData` | `/corporates/{corpId}` | GET | Corporate details |
| `getInstituteData` | `/corporate/institute/{campusId}/company/{companyId}` | GET | Institute-company relationship data |
| `duplicateRole` | `/corporates/{corpId}/jobs/{jobId}/duplicate` | POST | Duplicate a role with instituteCampusId |
| `getEligibilityCriteriaQualification` | `/search/degrees/streams/specialisations` | POST (ES) | ElasticSearch qualification search |

---

## Key Features

- **Job category filtering:** PLACEMENT, INTERNSHIP, APPRENTICESHIP, GIGS
- **Category-scoped filters:** Status, role, and schedule filters are scoped per job category
- **Multiple export formats:** CSV blob or Google Sheets integration
- **Interview round management:** View and update rounds per role
- **ElasticSearch integration:** Degree/stream/specialisation qualification search
