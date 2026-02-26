# Assessment Module

**Routes:**
- `/assessment` — Assessment dashboard (active/completed)
- `/assessment/create` — Create new assessment
- `/assessmentAssignSubscription` — Assign subscription
- `/assessmentAssignSubscription/institute/:id` — Assign to specific institute
- `/assessmentAssignSubscription/corporate/:id` — Assign to specific corporate
- `/assessmentAccess` — Feature access (college table)

**Frontend:** `admin-react/src/modules/Assessment/`

## Overview

The Assessment module is the admin's comprehensive assessment management system. It handles assessment creation, subscription management, student tracking (by status: sent, pending, in-progress, dropped-off, completed), reminders, invites, aptitude topics, degree-based eligibility, and data export. Supports both college and corporate entity types. This is the largest admin module (~2637 lines in actions.js).

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main dashboard | Assessment listing (active/completed tabs) |
| `Partials/CreateAssessment` | Create flow | Assessment creation form |
| `Partials/AssignSubscription` | Subscription | Assign subscription to institute/corporate |
| `Partials/CollegeTable/CollegeTableMain` | Feature access | College-level feature access management |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Assessment Listing

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `fetchActiveAssessments` | `/assessment/getActiveAssessments` | GET (Admin) | Active assessments with filters: pageNo, pageLimit, searchBy, order, sort, type_name, isTrial, isSubscribed, states, cities, entityType, instituteId |
| `fetchCompletedAssessments` | (similar endpoint) | GET (Admin) | Completed assessments with same filter set |

### Student Data

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `fetchStudentsByStatus` | `/assessment/getAssessmentDetails` | GET (Admin) | Students by status for an assessment. Params: assessmentInstituteMapID, entityType, searchQuery. Returns sent/pending/inProgress/droppedOff/completed |
| `fetchAllStudentStatusCounts` | `/assessment/getAssessmentDetails` | GET (Admin) | All student status counts for an assessment |
| `exportStudentData` | `/assessment/exportStudentData` | GET (Admin) | Export student data as Excel (.xlsx) blob download |

### Communication

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `sendRemindersToStudents` | `/assessment/sendReminders` | POST (Admin) | Send reminders to students. Supports selected students or all |
| `resendInvitesToStudents` | `/assessment/resendInvites` | POST (Admin) | Resend invites to students. Supports selected students or all |

### Assessment Creation

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `fetchAptitudeTopics` | `/assessment/getAptitudeTopics` | GET (Admin) | Aptitude topic sections for assessment creation |
| `setAssessmentCreationData` | (Redux only) | — | Store assessment creation form data |
| `addBulkUploadData` | (Redux only) | — | Add bulk-uploaded student data to assessment |
| `clearAssessmentCreationData` | (Redux only) | — | Clear creation form |

### Degree Selection

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `updateDegreeSelection` | (Redux only) | — | Hierarchical degree → stream → specialisation selection with cascading select/deselect |

---

## State Shape (key parts)

```js
{
  activeAssessments: [],
  completedAssessments: [],
  activeAssessmentsPagination: {},
  completedAssessmentsPagination: {},
  activeAssessmentsMetrics: { total, completed, pending, trialCount, subscribedCount },
  studentDataSent: [], studentDataPending: [], studentDataInProgress: [],
  studentDataDroppedOff: [], studentDataCompleted: [],
  assessmentInfo: {},
  degreeSearchResults: [],
  filters: { pageNo, pageLimit, searchBy, order, sort, type_name, isTrial, isSubscribed, states, cities, entityType },
  recentActivityLogs: [],
  assessmentCreationData: {}
}
```

---

## Key Features

- **Dual entity support:** `entityType` = `college` or `corporate` throughout all APIs
- **Student lifecycle tracking:** Sent → Pending → In Progress → Dropped Off → Completed
- **Hierarchical degree selection:** Degree → Stream → Specialisation with bulk select/deselect
- **Subscription management:** Trial vs Subscribed institute/corporate tracking
- **Bulk upload:** CSV-based student upload for assessments
- **Excel export:** Student data export as .xlsx blob
- **Reminders & invites:** Send/resend to all or selected students
- **Aptitude topics:** Configurable assessment sections
- **CEFR levels:** Assessment info includes CEFR level data
