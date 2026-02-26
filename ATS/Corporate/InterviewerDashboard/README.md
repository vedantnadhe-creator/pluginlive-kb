# Interviewer Dashboard Module

**Routes:**
- `/interviewerDashboard` — Interviewer dashboard (all interviewers)
- `/interviewerDashboard/:userId` — Specific interviewer's dashboard
- `/interviewerRoles/:roleId/:interID/:date` — Role-specific interview details
- `/interviewerRoles/:roleId/:userId/:interID/:date` — User-specific role interview details
- `/interviewerList` — Full interviewer listing

**Frontend:** `corporate-react-1/src/modules/InterviewerDashboard/`

## Overview

The Interviewer Dashboard manages the interview scheduling and tracking workflow for corporate interviewers. It provides interviewer listings, role-specific interview schedules, candidate scoring, bulk score uploads, and date-based interview filtering.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Dashboard orchestration |
| `Partials/DashboardCards/` | Metric cards | Summary cards for interview stats |
| `Partials/DashboardStats/` | Statistics | Interview statistics display |
| `Partials/DashboardRoles/` | Roles view | Role-based interview breakdown |
| `Partials/InstitutesDetails/` | Institute info | Institute-level interview details |
| `Partials/InterviewerList/` | Interviewer list | Paginated list of interviewers |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Interviewer Listing

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getInterviweList` | `/corporates/{corpId}/inteviewer/list` | GET | Paginated interviewer list with sort |
| `getInterviweListDetails` | `/corporates/{corpId}/interview/inteviewer/list` | GET | Detailed interviewer list with sort |

### Role & Candidate Management

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getListOfRolesForInterviwer` | `/corporates/{corpId}/inteviewer/{userId}/interview/list` | GET | Paginated role-interview list per interviewer. Filters: occurrence, roleIds, rounds, date range, search |
| `getListOfCandidateForRoleTOInterview` | `/corporates/{corpId}/inteviewer/{userId}/candidate/list` | GET | Candidate list for an interviewer's role. Filters: stage, status, score range, startTime |
| `getListOfCandidateListDownload` | `/students/corporate/{corpId}/interviewer/{userId}/candidate/list/export` | GET | Export candidate list for an interviewer |

### Filters

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getFilterRoleList` | `/corporates/{corpId}/inteviewer/{userId}/roles/list` | GET | Available role filter options (pageLimit=1000) |
| `getFilterRoundList` | `/corporates/{corpId}/inteviewer/{userId}/rounds/list` | GET | Available round filter options (pageLimit=1000) |
| `getListOfDatesInterviewer` | `/corporates/{corpId}/inteviewer/{userId}/interviewDates/list` | GET | Available interview dates for calendar view |

### Scoring

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `bulkFileUploadStatus` | `/corporates/interview/{interviewId}/{interviewerID}/students/bulkScoreUpdate` | PUT | Bulk upload interview scores via file |
| `getDriveScoreDetails` | `/corporates/drive/{driveId}/student/{studentId}/scoreDetails` | GET | Individual student score details for a drive |
| `getDriveScoreParameterDetails` | `/corporates/interview/{studentInterviewmap}/interviewer/{interviewerId}/scoreDetails` | GET | Detailed score parameters per interviewer |
| `getRoleRoundInterviewerLists` | `/corporates/role/{roleId}/interviewRound/startTime/{startTime}` | GET | Interviewers available for a round at a specific time |

---

## Key Features

- **Multi-level views:** All interviewers → specific interviewer → role details → candidate details
- **Date-based filtering:** Calendar-based interview schedule management
- **Occurrence filter:** Upcoming/ongoing/completed interviews
- **Score management:** Individual and bulk score upload for interview rounds
- **Export:** Download candidate lists per interviewer
- **Pagination:** `pageLimit=10`, `pageNo` (0-indexed)
