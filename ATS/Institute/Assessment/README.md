# Assessment Module

**Route:** `/assessment`
**Frontend:** `institute-react/src/modules/Assessment/`

## Overview

The Assessment module provides the TPO-facing dashboard for managing and tracking student assessments. It displays active and completed assessments, student-level tracking across lifecycle stages (sent, pending, in-progress, dropped-off, completed), detailed assessment analytics with charts, and student reports. Supports Communication, Aptitude, Role-Based, Behavioral, and Custom assessment types.

> **Reference:** For backend assessment logic, scoring, proctoring, and scheduling, see `pluginlive-kb/Assessment/`.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Assessment dashboard orchestration |
| `Partials/ActiveAssessmentTable/` | Active table | Active assessments listing |
| `Partials/CompletedAssessmentTable/` | Completed table | Completed assessments listing |
| `Partials/UnifiedAssessmentTable/` | Unified table | Combined assessment table view |
| `Partials/AssessmentDetails/` | Details view | Single assessment detail page |
| `Partials/StudentsTable/` | Students table | Students assigned to an assessment |
| `Partials/AllStudentsTable/` | All students | All students across assessments |
| `Partials/CandidateList/` | Candidate list | Candidate listing for an assessment |
| `Partials/StudentReport/` | Student report | Individual student assessment report |
| `Partials/FullStudentReport/` | Full report | Comprehensive student report view |
| `Partials/DiagnosisList/` | Diagnosis | Assessment diagnosis data |
| `Partials/TpoStudentListTable.js` | TPO list | TPO-specific student listing |
| `components/AssessmentCharts.js` | Charts | Assessment analytics visualizations |
| `components/AssessmentDetailView.js` | Detail view | Detailed assessment information |
| `components/CardComponents.js` | Cards | Reusable card components |
| `components/ProgressCircle.js` | Progress | Circular progress indicator |

---

## Redux Actions & API Endpoints

**File:** `actions.js` (~2944 lines)

### Assessment Listing

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `fetchActiveAssessmentCount` | `/assessment/getActiveAssessmentCount` | GET | Count of active assessments by entity type |
| `fetchAssessmentCompletedCount` | `/assessment/getAssessmentCompletedCount` | GET | Count of completed assessments |
| `fetchActiveAssessments` | `/institutes/studentListInfo/getschedulesInfo` | GET | Paginated active assessment list with filters (search, sort, type, states, cities, trial, subscribed, passingYear) |
| `fetchCompletedAssessments` | (similar endpoint) | GET | Paginated completed assessment list |

### Assessment Details & Student Data

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `fetchAssessmentDetails` | `/assessment/getAssessmentDetails` | GET | Detailed assessment data with student lifecycle stages (sent, pending, inProgress, droppedOff, completed). Supports filters, search, pagination |

### Filter APIs (Cascading)

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getInstituteDomains` | `/institutes/studentListInfo/domains` | GET | Domain filter options |
| `getInstituteDegrees` | `/institutes/{id}/degree` | GET | Degree options by domain |
| `getInstituteDepartments` | `/institutes/{id}/streams` | POST | Department/stream options |
| `getInstituteSpecializations` | `/institutes/{id}/specialisations` | POST | Specialisation options |
| `getYearOfPassing` | `/students/institutes/{id}/yearOfPassing` | GET | Year of passing options |

### Assessment-Specific Filters

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getAssessmentDomains` | `/assessment/getDomain` | GET | Domains for assessment context |
| `getAssessmentDegrees` | `/assessment/getDegree` | GET | Degrees for assessment context |
| `getAssessmentDepartments` | `/assessment/getDepartment` | GET | Departments for assessment context |
| `getAssessmentSpecializations` | `/assessment/getSpecialization` | GET | Specializations for assessment context |

### Charts & Analytics

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `fetchAssessmentCharts` | (chart endpoint) | GET | Assessment chart data |
| `fetchCefrChartData` | (CEFR endpoint) | GET | CEFR level distribution chart |
| `fetchConsistencyData` | (consistency endpoint) | GET | Student consistency metrics |
| `fetchAptitudeGroups` | (aptitude endpoint) | GET | Aptitude grouping data |
| `fetchAptitudeMetrics` | (metrics endpoint) | GET | Aptitude-specific metrics |
| `fetchDiagnosisData` | (diagnosis endpoint) | GET | Assessment diagnosis data |

### Student Reports & Activity

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `fetchReports` | (reports endpoint) | GET | Assessment reports data |
| `fetchActivityMap` | (activity endpoint) | GET | Student activity calendar data |
| `fetchPracticeScores` | (practice endpoint) | GET | Practice assessment scores |
| `fetchCefrLevel` | (CEFR endpoint) | GET | Student CEFR level data |
| `fetchLastAssessment` | (last assessment endpoint) | GET | Most recent assessment for a student |
| `fetchMediaKeys` | (media endpoint) | GET | Proctoring media keys |
| `fetchMediaUrls` | (media URL endpoint) | GET | Proctoring media URLs |
| `checkReportAvailability` | (availability endpoint) | GET | Check if report is ready |

### TPO Student List

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `fetchTpoStudentList` | (TPO list endpoint) | GET | TPO-specific student listing |
| `fetchSpecificAssessmentStudentList` | (specific list endpoint) | GET | Students for a specific assessment |

---

## State Shape

```js
{
  loading: false,
  error: null,
  activeAssessmentCount: 0,
  completedAssessmentCount: 0,
  activeAssessments: [],
  completedAssessments: [],
  activeAssessmentsPagination: {},
  completedAssessmentsPagination: {},
  activeAssessmentsMetrics: {},
  completedAssessmentsMetrics: {},
  filters: {},
  studentData: { sent: [], pending: [], inProgress: [], droppedOff: [], completed: [] },
  studentDataLoading: false,
  assessmentFilters: {},
  chartFilters: {},
  activityMap: {},
  practiceScores: {},
  cefrLevel: {},
  reports: {},
  assessmentDetails: {},
  assessmentCharts: {},
  diagnosisData: {},
  mediaKeys: {},
  mediaUrls: {},
  tpoStudentList: {}
}
```

---

## Key Features

- **Student lifecycle tracking:** Sent → Pending → In Progress → Dropped Off → Completed
- **Assessment types:** Communication, Aptitude, Role-Based, Behavioral, Custom
- **CEFR levels:** Communication assessments track A1–C2 levels
- **Aptitude levels:** Beginner, Learner, Competent, Advanced
- **Canonical achieved level:** All v2 overview, competency, performance, and
  report views read the stored grade from `assessment.progression_history`
  (`assessment_cefr` for Communication, `assessment_aptitude_level` for
  Aptitude). `assessment_assigned_students.resulting_cefr` is a legacy copy and
  must not drive reporting because it can drift from progression history.
- **Diagnosis grouping:** Diagnosis attempts are folded into their owning
  schedules and do not appear as standalone rows in Assessment Sent.
- **Proctoring integration:** Media keys/URLs for proctoring review
- **Chart-based filters:** Interactive chart filtering with `setChartFilters`/`clearChartFilters`
- **Mock data support:** `useMockData` flag or `localStorage.ASSESSMENT_MOCK` for frontend development
- **Entity type:** Supports `college` entity type for institute context
- **Cascading filters:** Domain → Degree → Department → Specialisation → Year of Passing
- **Multiple API layers:** Uses `adminRequest`, `studentRequest`, `instRequest`, `corporateRequest`, `authRequest`

---

## Year Filtering & Race Condition Guards

All assessment listing APIs (`fetchActiveAssessments`, `fetchCompletedAssessments`, `fetchActiveAssessmentCount`, `fetchAssessmentCompletedCount`) pass `passingYear` and `instituteId` to ensure data is scoped to the selected year.

**Stale request guard:** `fetchActiveAssessments` uses a request counter (`_activeAssessmentsRequestId`) to prevent race conditions when the year changes rapidly. If a newer request is dispatched before the previous one returns, the stale response is discarded.

```javascript
let _activeAssessmentsRequestId = 0
export const fetchActiveAssessments = (params = {}) => async (dispatch, getState) => {
    if (!params.passingYear) return []  // Skip if no year selected
    const requestId = ++_activeAssessmentsRequestId
    // ... after API response:
    if (requestId !== _activeAssessmentsRequestId) return []  // Discard stale
}
```

The `handleMenuClick` useEffect in `index.js` includes `selectedYear` in its dependency array to re-fetch when year changes.

> **Backend:** When `passingYear` is null/empty, the schedule list API (`StudentListInfo.getschedulesInfo`) returns ALL schedules without year filtering, which can cause data mixing between years.
