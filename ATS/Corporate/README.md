# Corporate Portal

This folder contains module-wise documentation for the PluginLive Corporate Portal — the interface used by corporate HR/recruiters to manage job roles, drives, candidates, interviews, and hiring analytics.

**Frontend:** `corporate-react-1`
**Route prefix:** `/` (authenticated corporate user)

## Modules

### Core Modules (Nav Menu)

| Module | Folder | Route(s) | Description |
|--------|--------|----------|-------------|
| Dashboard | `Dashboard/` | `/dashboard` | Corporate overview — drive stats, institute details, metrics cards |
| Corporate Dashboard | `CorporateDashboard/` | `/corporate-dashboard`, `/corporateDashboardPage2` | Advanced analytics dashboard with PDF export |
| Interviewer Dashboard | `InterviewerDashboard/` | `/interviewerDashboard`, `/interviewerDashboard/:userId`, `/interviewerRoles/:roleId/:interID/:date`, `/interviewerList` | Interviewer workload, schedules, candidate scoring |
| Roles | `Roles/` | `/roles`, `/roles/new-role`, `/roles/new-role/:jobId`, `/roles/edit-role/:jobId`, `/roles/:jobId/view-role`, `/roles/:jobId/view-roleChart`, `/roles/:jobId/applicant-tracking-system`, `/roles/:jobId/ex-student`, `/roles/:jobId/view-role/:instituteCampusId/:candidates/view-college-details` | Full role lifecycle — create, edit, publish, ATS, college details, charts |
| Role Page | `RolePage/` | `/rolePage` | Job role listing with filters, export, category-based views |
| Drives | `Drives/` | `/drives/role/:roleId`, `/drives/:driveId/role/:roleId` | Drive-level candidate management, evaluation, bulk uploads |
| Exp-Candidates | `ExpCandidates/` | `/expcandidates`, `/expcandidatedrive/:expcandidatesId`, `/expcandidates/:expcandidatesId/role/:roleId`, `/expcandidates/:expcandidatesId/role/:roleId/role` | Experienced candidate evaluation pipeline |
| Users | `Users/` | `/users` | Corporate user CRUD, notifications (email, WhatsApp, in-app) |
| Reports | `Reports/` | `/reports/role/published`, `/reports/application/status`, `/reports/drive/level`, `/reports/hiring/status`, `/reports/interview/schedule` | Five report types with filters and Excel export |
| Settings | `Settings/` | `/settings` | Branch/location management with ElasticSearch sync |

### Supporting Modules

| Module | Folder | Route(s) | Description |
|--------|--------|----------|-------------|
| Students | `Students/` | `/students` | Student listing (read-only from corporate side) |
| Manage Profile | `ManageProfile/` | `/manageprofile` | User profile management, password, phone OTP, file upload |
| Auth | `Auth/` | `/signin` | Corporate user authentication |

---

## Architecture

- **State Management:** Redux (actions → reducers → selectors pattern)
- **API Layers:** Multiple Axios instances — `corporateRequest`, `studentRequest`, `instituteRequest`, `elasticSearchRequest`, `elasticSearchSyncRequest`, `adminRequest`, `authRequest`
- **UI Framework:** Ant Design (antd) + styled-components
- **Routing:** React Router

## Documentation Structure

Each module folder contains a `README.md` covering:
- Overview & purpose
- Key UI components
- Redux actions & API endpoints
- Filters, sorting, pagination
- Related backend services
