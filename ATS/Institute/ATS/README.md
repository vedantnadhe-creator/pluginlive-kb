# ATS (Applicant Tracking System) Module

**Route:** `/jobRoles/ats/:roleId`
**Frontend:** `institute-react/src/modules/ATS/`

## Overview

The ATS module is the core applicant tracking interface within a job role. It manages interview rounds, candidate evaluation stages, status updates, conflict resolution, bulk uploads, and candidate exports. Accessed from the Job Roles module for a specific role, it provides a round-by-round view of candidate progress through the evaluation pipeline.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | ATS pipeline view for a role |
| `Components/Round.js` | Round view | Individual interview round display |
| `Components/Table.js` | Candidate table | Candidate listing per round/stage |
| `Components/Metrics/` | Metrics | Candidate count metrics per stage |
| `Components/IndividualTable/` | Detail table | Individual candidate detail table |
| `Components/EvaluationForm.js` | Eval form | Candidate evaluation form |
| `Components/EvaluationProcessFilter/` | Filters | Stage, degree, department, specialisation filters |
| `Components/ResolveConflict.js` | Conflict | Resolve scheduling/assignment conflicts |
| `Components/ResultUploader.js` | Upload results | Upload evaluation results |
| `Components/Upload/` | File upload | General upload component |
| `Components/DatePicker/` | Date picker | Date selection for scheduling |

---

## Redux Actions & API Endpoints

**File:** `action.js`

### Interview Rounds

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `addNewRound` | `/corporates/role/{roleId}/interviewRounds` | GET | Fetch interview rounds for a role |
| `updateNewRound` | `/corporates/role/{roleId}/interviewRounds` | PUT | Add/update interview rounds |

### Candidate Management

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `updateCandidateRoleStatus` | `/corporates/instiuteCampus/{campusId}/jobs/{jobId}/status/update` | PUT | Update candidate status (shortlist, reject, schedule, etc.) |
| `bulkUploadForAts` | `/corporates/instituteCampus/{campusId}/job/{jobId}/candidates/status/bulkUpload` | POST | Bulk upload candidate statuses via CSV |
| `getPreviewData` | `/students/{studentId}` | GET | Student preview data (dispatches to store) |
| `getPreview` | `/students/{studentId}` | GET | Student preview data (returns directly) |
| `StudentEmailList` | `/students/instiuteCampus/{campusId}/jobs/{roleId}/evaluation/candidate/list` | POST | Full candidate email list (pageLimit=5000) |

### Filters

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getCandidateDegree` | `/students/instiuteCampus/{campusId}/jobs/{roleId}/evaluation/candidate/filter` | GET | Degree filter options per stage, with `forInstitute` flag |
| `getCandidateDepart` | `/students/instiuteCampus/{campusId}/jobs/{roleId}/evaluation/candidate/filter?forStream=true` | GET | Department filter (filtered by selected degrees) |
| `getCandidateSpecialization` | `/students/instiuteCampus/{campusId}/jobs/{roleId}/evaluation/candidate/filter?forSpecialisation=true` | GET | Specialisation filter (filtered by degrees + departments) |
| `statusFilterList` | `/students/instiuteCampus/{campusId}/jobs/{roleId}/evaluation/statusfilter/list` | GET | Status filter options per stage (offer vs round) |
| `corporateFilterList` | `/corporate/institute/{campusId}/jobs/{roleId}/corpfilter` | POST | Corporate-level filter options |
| `studentFilterList` | `/students/instiuteCampus/{campusId}/jobs/{roleId}/evaluation/candidate/studentfilter` | GET | Student-level filter options |

### Conflict Resolution

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `resolveConflict` | `/corporates/instituteCampus/{campusId}/job/{jobId}/conflictCandidates/list` | GET | List conflicting candidates with pagination, search, round filter |

### Export

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `atsExportCandidate` | `/students/role/{roleId}/instituteCampus/{campusId}/candidate/{type}/export` | PUT | Export candidates (CSV blob, Google Sheets, or count). Includes response headers for blob downloads |

---

## State Shape

```js
{
  roundData: {},
  updateRoundData: {},
  previewData: {},
  jobRolePreviewData: {}
}
```

---

## Key Features

- **Round-based pipeline:** View and manage candidates across interview rounds
- **Stage filtering:** `stageIndex` parameter for round-specific data
- **Institute vs Corporate:** `forInstitute` flag differentiates institute-published vs corporate-published roles
- **Cascading filters:** Degree → Department → Specialisation with stage context
- **Bulk status upload:** CSV-based bulk candidate status updates
- **Conflict resolution:** Detect and resolve candidate scheduling conflicts per round
- **Export with count:** `key='count'` returns candidate count without downloading
