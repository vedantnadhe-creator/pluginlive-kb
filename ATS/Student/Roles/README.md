# Roles Module

**Routes:**
- `/roles` — Job role listing
- `roles/viewrole/:CorpID/:JobID/questionnaire` — Questionnaire for a role
- `roles/viewrole/:CorpID/:JobID/questionnaire/feedback` — Questionnaire feedback
- `roles/questionnaire/:CorpID/:JobID/job/result` — Questionnaire result
- `/roles/questionnaire/:CorpID/:JobID/job/re-applied` — Re-application after fail

**Frontend:** `student-react/src/modules/Roles/`

## Overview

The Roles module is the primary job discovery interface for students. It lists all institute-accepted job roles available to the student, with rich filtering (job type, CTC range, location, job level), sorting, search, and pagination. Students can apply, save, or reject roles. Includes a questionnaire sub-flow for roles requiring questionnaire-based evaluation.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main listing | Role listing with filters |
| `Questionnaire/Container/index` | Questionnaire | Questionnaire flow for a role |
| `Questionnaire/Feedback/Container/index` | Feedback | Post-questionnaire feedback |
| `Questionnaire/ConfirmationScreens/ResultScreen` | Result | Questionnaire pass result |
| `Questionnaire/ConfirmationScreens/FailScreen` | Fail | Questionnaire fail / re-apply |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Role Listing & Details

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getRolesList` | `/corporates/instituteAcceptedJobsforStudent/{studentId}/lists` | GET (Corp) | Paginated role list. Filters: search, jobTypeLevels (ENTRY/INTERN/EXPERIENCED), jobType (FULL_TIME/PART_TIME), minCTC, maxCTC, jobLocation, sort (compensation asc/desc), pageLimit=10 |
| `getSingleRoleDetails` | `/corporates/{corpId}/jobs/{roleId}` | GET (Corp) | Single role details |
| `getRoleFloatDetails` | `/students/roleFloatDetails/{studentId}` | GET (Student) | Role float details for the student |
| `updateRoleFloatDetails` | `/students/roleFloatDetails/{studentId}?roleId={roleId}` | PUT (Student) | Update role float details |
| `getEligibleDetails` | `/corporates/{roleId}/{studentId}/eligibleDetails` | GET (Corp) | Eligibility details (skills, location match) |
| `getStudentRoleList` | `/corporates/roleFloatedforStudent/{studentId}/lists` | POST (Corp) | Role list with payload-based filters |
| `getCompTypeList` | `/institute/{studentId}/compensationList` | GET (Inst) | Compensation type list |

### Role Actions

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `ApplyRole` | `/students/role/apply` | POST (Student) | Apply for a role. Payload: roleId, studentId, corporateId, accessLevel |
| `RejectedRole` | `/students/role/reject` | POST (Student) | Reject a role |
| `SaveRole` | `/students/role/save` | POST (Student) | Save/unsave a role. Updates local state optimistically |

### Filters

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getCities` | `/cities` | GET (Auth) | City list for location filter (pageLimit=50) |
| `getRoleCities` | `/corporates/instituteAcceptedJobsforStudent/{studentId}/lists?forJobLocations=true` | GET (Corp) | Job location filter options |
| `getSkillLocationFilterData` | `/corporate/institute/{instituteId}/student/{studentId}/ruleEngine` | POST (Corp) | Skill & location filter data from rule engine |
| `getStudentRuleSet` | `/corporates/student/{studentId}/ruleEligibility` | POST (Corp) | Student rule eligibility set |

---

## Key Features

- **CTC filtering:** Min/max CTC range (converted to lakhs → actual value × 100000)
- **Job level mapping:** ENTRY LEVEL → ENTRY, INTERNSHIP → INTERN, EXPERIENCE → EXPERIENCED
- **Optimistic updates:** Apply/save actions update local Redux state immediately
- **Questionnaire flow:** Multi-step questionnaire with feedback and result/fail screens
- **Role float:** Track which roles have been floated to the student
- **Rule engine integration:** Eligibility checking via institute rule engine

## Resolved Incidents

- **Null preferred job locations caused `eligibleDetails` to return 500 (2026-08-24):** For a location-restricted role, `studentEligibleData` called `.some()` directly on `studentPersonalProfile.preferredJobLocation`. Profiles where that field was `null` failed with `Cannot read properties of null (reading 'some')`. `corporate-node/app/helpers/utils.js` now normalizes non-array values to `[]` in both `studentEligibleData` and the sibling `isStudentEligible` helper. Missing preferences therefore produce a normal location-ineligible result instead of crashing. Corporate-node commits: DEV `599bb67f`; UAT merge `bfddb2c2`. Deployed and health-checked in both environments on 2026-08-24.
