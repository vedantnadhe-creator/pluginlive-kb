# Job Roles Module

**Route:** `/jobRoles`
**Frontend:** `institute-react/src/modules/JobRoles/`

## Overview

The Job Roles module is the primary interface for TPO users to manage and view job roles posted by corporates for their institute. It supports listing, filtering, detailed view, candidate export, role duplication, and eligibility criteria management via ElasticSearch.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Orchestrates job roles listing |
| `PageHeader/` | Header section | Title, filters, transfer, and action buttons |
| `PageHeader/JobRoleFilter/` | Filter panel | Status, role, schedule, domain, degree, department filters |
| `PageHeader/Components/` | Shared components | Reusable header sub-components |
| `PageHeader/Transfer.js` | Transfer | Student transfer functionality |
| `NewJobRole/` | Create/Edit | New job role creation flow |
| `NewJobRole/CompanyCard/` | Company info | Corporate company card display |
| `NewJobRole/CompanyDetails/` | Company details | Detailed corporate information |
| `NewJobRole/RolesForm/` | Role form | Job role creation form |
| `CustomDateRange.js` | Date picker | Custom date range selector |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Job Role Listing

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getJobRoleList` | `/corporates/instiuteCampus/{id}/jobs` | POST | Paginated job role listing with filters |
| `getCorporateData` | `/corporates/{corpId}` | GET | Corporate details for a role |
| `getInstituteData` | `/corporate/institute/{campusId}/company/{companyId}` | GET | Institute-company relationship data |

### Filters

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getStatusFilter` | `/corporates/filterStatus/instituteCampus/{id}/jobs` | GET | Available status filter options |
| `getRoleFilter` | `/corporates/filterRole/instituteCampus/{id}/jobs` | GET | Available role filter options |
| `getScheduleFilter` | `/corporates/filterEvaluation/instituteCampus/{id}/jobs` | GET | Evaluation schedule filter options |
| `getDomainList` | `/institutes/{campusId}/domain` | GET | Domain list for eligibility filters |
| `getDegreeList` | `/institutes/{campusId}/degree` | GET | Degree list filtered by domain |
| `getDepartmentList` | `/institutes/{campusId}/streams` | POST | Department/stream list |
| `getYear` | `/students/institutes/{id}/yearOfPassing` | GET | Year-of-passing list |

### Eligibility & ElasticSearch

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getEligibilityCriteriaQualification` | `/search/degrees/streams/specialisations` | POST | ElasticSearch-based qualification lookup for eligibility criteria |

### Export & Actions

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `exportCandidate` | `/students/role/{roleId}/instituteCampus/{id}/candidate/{type}/export` | PUT | Export candidates (CSV/Google Sheets) |
| `getExportFiledData` | `/students/institutes/heading/export` | GET | Available export field headings |
| `exportCSV` | `/corporates/instituteCampus/{id}/export/{type}` | GET | Export job roles data |
| `duplicateRole` | `/corporates/{corpId}/jobs/{jobId}/duplicate` | POST | Duplicate an existing job role |

---

## Key Features

- **Job category filter:** `jobCategory` param (e.g., PLACEMENT)
- **ElasticSearch integration:** Qualification search uses `elasticSearchRequest` with `systemConfig.degree_streams_specialisation`
- **Export options:** CSV blob download or Google Sheets integration
- **Role duplication:** Clone existing roles with `instituteCampusId`
- **Filters:** Status, role type, evaluation schedule, domain, degree, department, year
