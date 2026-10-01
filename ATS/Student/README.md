# Student Portal

This folder contains module-wise documentation for the PluginLive Student Portal — the interface used by students to browse job roles, apply for positions, manage their resume/profile, attend drives, receive offers, and participate in campus events.

**Frontend:** `student-react`
**Route prefix:** `/` (authenticated student)

## Modules

### Core Modules

| Module | Folder | Route(s) | Description |
|--------|--------|----------|-------------|
| Dashboard | `Dashboard/` | `/dashboard`, `/` | Student landing page with opt-out status management |
| Roles | `Roles/` | `/roles` | Browse and filter available job roles, apply, save, reject |
| View Role | `ViewRole/` | `appliedroles/viewrole/:CorpID/:JobID` | Detailed view of an applied role with apply/save/share actions |
| View Single Role | `ViewSingleRole/` | `roles/viewrole/:CorpID/:JobID` | Detailed view of a role from listing (pre-apply) |
| Questionnaire | (inside Roles) | `roles/viewrole/:CorpID/:JobID/questionnaire`, `.../feedback`, `roles/questionnaire/:CorpID/:JobID/job/result`, `/roles/questionnaire/:CorpID/:JobID/job/re-applied` | Questionnaire-based evaluation flow with feedback and result screens |
| Applied Roles | `AppliedRoles/` | `/applied_roles`, `/applied_roles/:Status` | Track applied roles with status filtering and metrics |
| Resume | `Resume/` | `/resume` | Resume builder, profile editing, education, skills, work experience |
| Drives | `Drives/` | `/drives` | Upcoming/ongoing/completed placement drives listing |
| Drive Details | `DriveDetails/` | `/driveDetails/:RoleID/:DriveID` | Individual drive interview details with date selection |
| Offer Letter | `OfferLetter/` | `/offerReceived`, `/offerReceived/:Status`, `/offerReceived/ExCand/:offerID`, `/offerReceived/uploadDocument/:offerID` | Offer management — accept, reject, negotiate, upload documents, join |
| Events | `Events/` | `/events` | Campus events listing, calendar view, event registration |
| Manage Profile | `ManageProfile/` | `/manageprofile` | Account settings, OTP verification, notifications |

### Onboarding (Anonymous + Authenticated)

| Module | Folder | Route(s) | Description |
|--------|--------|----------|-------------|
| Onboarding | `Onboarding/` | `/onboarding/activate/:studentId` (anon), `/not-interested/:studentId` (anon), `/not-interested/final/:studentId` (anon), `/onboarding/final/:studentId`, `/onboarding/register/:studentId`, `/onboarding/notification/:studentId` | Student activation, registration, not-interested flow |

---

## Architecture

- **State Management:** Redux (actions → reducers pattern)
- **API Layers:** Multiple Axios instances — `studentRequest`, `corporateRequest`, `instituteRequest`, `authRequest`, `searchRequest`, `elasticSearchSyncRequest`, `adminRequest`, `authRequested`
- **UI Framework:** Ant Design (antd) + styled-components
- **Routing:** React Router (`anonymous` + `authenticated` route groups)
- **Student creation `POST /students` (student-node `createPublicStudent`) is server-to-server only** — `privateByKey: true` since 2026-10-01 (DEV `ce998bfd`, UAT `6648b8a7`, PROD pending); missing/wrong `auth-key` → 401. The only caller is admin-node `StudentService.createPublicStudent` (invites, broadcasts, custom assessments), which sends `auth-key: AUTH_KEY`. admin-node and student-node `AUTH_KEY` must be identical per env; `verifyAuthKey` compares with `==`, so an **unset** key on both sides fails *open*. The old CRA public sign-up forms (`Static-website`, `New-Static-Webiste` `/Student_Registration`) also posted here from the browser — they are not served by the live pluginlive.com (Next.js) and would get 401 now.

## Documentation Structure

Each module folder contains a `README.md` covering:
- Overview & purpose
- Key UI components
- Redux actions & API endpoints
- Filters, sorting, pagination
- Key features
