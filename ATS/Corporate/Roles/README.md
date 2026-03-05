# Roles Module

**Routes:**
- `/roles` — Role listing
- `/roles/new-role` — Create new role
- `/roles/new-role/:jobId` — Continue creating role (draft)
- `/roles/edit-role/:jobId` — Edit existing role
- `/roles/:jobId/view-role` — View role details
- `/roles/:jobId/view-roleChart` — Role analytics chart
- `/roles/:jobId/applicant-tracking-system` — ATS for a role
- `/roles/:jobId/ex-student` — Experienced student candidates
- `/roles/:jobId/view-role/:instituteCampusId/:candidates/view-college-details` — College-level candidate details
- `/questionaire-dashboard/:jobId` — Questionnaire dashboard

**Frontend:** `corporate-react-1/src/modules/Roles/`

## Overview

The Roles module is the core of the corporate portal. It manages the entire job role lifecycle — creation, editing, publishing to institutes, viewing applied colleges and candidates, ATS tracking, questionnaire-based evaluation, drive management, and role analytics. This is the largest module (~2900 lines in actions.js).

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main listing | Role listing with filters and metrics |
| `Container/NewRoleContainer/` | Create/Edit | Role creation and editing flow |
| `Container/ViewRoleContainer/` | View role | Detailed role view with colleges and candidates |
| `Container/ViewRoleChartContainer/` | Charts | Role analytics charts |
| `Container/ApplicantTrackingSystemContainer/` | ATS | Applicant tracking for a role |
| `Container/ExStudentContainer/` | Ex-students | Experienced student candidate management |
| `Container/ViewCollegeDetailsContainer/` | College details | Institute-campus level candidate details |
| `Container/DashboardContainer/` | Questionnaire | Questionnaire dashboard for a role |
| `NewRoleCreation/` | Role form | Role creation form with partials |
| `Partials/RolesTable/` | Table | Paginated role listing table |
| `Partials/RolesFilter/` | Filters | Job type, status, date filters |
| `Partials/ViewCollegeDetails/` | College view | College-level detail partials |
| `ViewRole/` | Role detail | Role detail components |
| `ViewRole/ApplicantTrackingSystem/` | ATS view | ATS pipeline components |
| `ViewRole/CandidatesTable/` | Candidates | Candidate listing table |
| `ViewRole/CollegesTable/` | Colleges | Applied colleges table |
| `ViewRole/DriveDrawers/` | Drawers | Drive creation/management drawers |
| `ViewRole/ExStudent/` | Ex-student view | Ex-student components |
| `ViewRole/Header/` | Header | Role detail page header |
| `ViewRole/ViewRoleChart/` | Chart view | Chart components |
| `ViewRoleChart/` | Charts | Standalone chart components |

---

## Redux Actions & API Endpoints

**File:** `actions.js` (~2895 lines)

### Role CRUD

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getJobsList` | `/corporates/{corpId}/jobs/lists` | GET | Paginated role listing with search, jobType, status, date range, sort |
| `getCorporateMetricsData` | `/corporates/{corpId}/jobs/metrics` | GET | Role count metrics (active, closed, draft, etc.) |
| `newCorporateJobRoles` | `/corporates/{corpId}/job` | POST | Create new role. Syncs skills to ES after creation |
| `updateCorporateJobRoles` | `/corporates/{corpId}/jobs/{jobId}` | PUT | Update role. Syncs skills to ES |
| `updateJobRole` | `/corporates/{corpId}/jobs/{jobId}` | PUT | Update job role (alternate action with button loading) |
| `publishCorporateJobRole` | `/corporates/{corpId}/jobs/{jobId}/publish` | POST | Publish role to selected institutes |
| `postCorporateJobRole` | `/corporates/{corpId}/jobs` | POST | Save role details |
| `closeApplication` | `/corporates/{corpId}/jobs/{jobId}/close` | POST | Close a role for applications |
| `duplicateRole` | `/corporates/{corpId}/jobs/{jobId}/duplicate` | POST | Duplicate an existing role |
| `deleteRole` | `/corporates/{corpId}/jobs/{jobId}` | DELETE | Delete a role |
| `getSingleRoleData` | `/corporates/{corpId}/jobs/{jobId}` | GET | Fetch single role details. Optional `skillsRequired` & `degreeRequired` params |
| `getRoleDraftData` | `/corporates/{corpId}/jobs/draft/{jobId}` | GET | Fetch draft role data |
| `getPreviewData` | `/corporates/jobs/{roleId}` | GET | Role preview data |

### Institute & College Management

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getInstitutesList` | `/institutes/campus/preview/list` | POST | Institute campus list with search, location, tier, specialisation, published filter. Supports `tpoCollegeList` flag |
| `getInstitutesLocationList` | `/institutes/campus/location/list` | POST | Institute location list for filtering |
| `getAppliedCollegesList` | `/institutes/instituteCampus/corporate/{corpId}/jobrole/{roleId}/list` | GET | Colleges that applied/received a role with filters: city, tier, ranking, candidate count, drive status |
| `getInstituteCampusDetails` | `/institutes/instituteCampus/{id}` | GET | Single institute campus details |
| `getRoleCityData` | `/institutes/corporate/{corpId}/jobRole/{jobId}/instituteLocation/list` | GET | Location list for a role's institutes |

### Candidate Management

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getAppliedCandidateList` | `/students/roles/{roleId}/candidate/list` | POST | Paginated candidate list with filters: status, gender, rating, percentage, degree, college, bulk download |
| `getDriveCreatedCandidates` | `/students/role/{roleId}/drive/jobRoleInstituteAndNameCount` | POST | Candidates with drives created (DRIVE_CREATED type) |
| `getDriveNotCreatedCandidates` | `/students/role/{roleId}/drive/jobRoleInstituteAndNameCount` | POST | Candidates without drives (DRIVE_NOT_CREATED type) |
| `getDriveCreatedCandidatesPreview` | `/students/role/{roleId}/drive/jobRoleInstituteAndNameCount` | POST | Preview of drive-created candidates |
| `getApplicantCandidateList` | (ATS candidate list endpoint) | POST | Applicant tracking candidate list with stage, status, offer filters |

### Drive Management

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `createDrive` | `/corporates/jobdrive/apply` | POST | Create a new drive |
| `getDriveRoleMetrics` | `/corporates/{driveId}/roles/metrics` | GET | Metrics for roles within a drive |

### ElasticSearch & Master Data

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getEligibilityCriteriaQualification` | `/search/degrees/streams/specialisations` | POST (ES) | ElasticSearch-based qualification search for eligibility |
| `getElasticSearchDegreeData` | `/search/degrees/streams` | POST (ES) | ES degree-stream search |
| `getCourses` | `/search/degrees/streams/specialisations` | POST (ES) | Course search with filters |
| `getListOfSkills` | `/students/crud/skill` | GET (ES) | Skill search |
| `searchAPI` | `/search/{type}` or `/students/crud/skill` | POST/GET | Generic master data search (skills, cities, etc.) |
| `getCities` | `/cities` | GET (ES) | City search |
| `getListOfDegree` | `/institutes/search/degreeStreams` | GET | Degree-stream list |
| `getYearOfPassing` | `/corporates/jobs/yearOfPassing` | GET | Year of passing filter |

### Ranking & Questionnaire

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getRoleRankingConfig` | `/corporate/role/{roleId}/roleRankConfig` | GET | Role ranking configuration |
| `updateRoleRankingConfig` | `/corporate/role/{roleId}/roleRankConfig` | PUT | Update ranking config |
| `questionarieShortlistReject` | `/students/role/{roleId}/updatestatus` | PUT | Shortlist/reject candidates based on questionnaire |

---

## Key Features

- **Full role lifecycle:** Draft → Create → Publish → Active → Close
- **Institute publishing:** Select institutes by location, tier, specialisation
- **ElasticSearch integration:** Degree, skill, and qualification searches
- **ES sync on mutations:** `student_crud_skill` and `skill_master` synced after role create/update
- **ATS pipeline:** Applicant tracking with round-based candidate management
- **Questionnaire dashboard:** Questionnaire-based candidate evaluation
- **Role charts:** Visual analytics per role
- **Drive management:** Create drives from role → college combinations
- **Candidate filtering:** Rating, percentage, degree, gender, status, college
- **Bulk download:** `bulkDownload=true` flag for candidate exports
- **Google Form (ITI/Diploma):** Application Form via Google Forms for ITI/Diploma roles — see [`GoogleForm/README.md`](GoogleForm/README.md)

---

## Sub-Modules

| Sub-Module | Folder | Description |
|------------|--------|-------------|
| Google Form | `GoogleForm/` | Application Form feature for ITI/Diploma roles — Google Forms integration, templates, per-college form creation |
