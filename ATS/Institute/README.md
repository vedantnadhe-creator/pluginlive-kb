# Institute Portal

This folder contains module-wise documentation for the PluginLive Institute (TPO) Portal — the primary interface used by Training & Placement Officers to manage students, corporates, events, job roles, placements, and assessments.

**Frontend:** `institute-react`
**Route prefix:** `/` (authenticated institute user)

## Modules

### Core Modules (Nav Menu)

| Module | Folder | Route(s) | Description |
|--------|--------|----------|-------------|
| TPO Dashboard | `TPODashboard/` | `/tpoDashboard` | Placement analytics — job profile status, CTC analysis, student placement with PDF export |
| Dashboard | `Dashboard/` | `/dashboard`, `/dashboard/roles/:corpID`, `/dashboard/drives/:roleID/:corpID`, `/dashboard/roles/drive/:driveID/:roleID` | Drive and role metrics overview with drill-down |
| Students | `Students/` | `/students` | Student CRUD, bulk upload, blacklist, opt-out, notifications |
| Corporate | `Corporate/` | `/corporate`, `/corporate/newCorporate`, `/corporate/editCorporate/:corporateId` | Institute-level corporate/company management |
| Roles | `Roles/` | `/roles`, `/roles/details` | Job roles listing, details, accept/reject, save |
| Placement | `Placement/` | `/placement` | Batch folders — course-wise student placement data |
| Job Roles | `JobRoles/` | `/jobRoles`, `/jobRoles/newRole`, `/jobRoles/editRole/:roleId`, `/jobRoles/newRole/companyDetails` | Job role management with filters, export, duplicate |
| Job Preview | `JobPreview/` | `/jobRoles/jobPreview/:roleId` | Detailed job role view with candidates, placement history, resume viewer |
| ATS | `ATS/` | `/jobRoles/ats/:roleId` | Applicant tracking — interview rounds, candidate evaluation, status updates, bulk upload |
| Events | `Events/` | `/events`, `/events/newevent`, `/events/editevent/:eventID`, `/events/drafts`, `/events/:eventId` | Event creation, listing, calendar, drafts, bulk upload |
| Users | `Users/` | `/users` | TPO user management (create, edit, activate, delete) |
| Rule Engine | `RuleEngine/` | `/ruleEngine`, `/ruleEngine/draft-page`, `/ruleEngine/yet-to-set-rule`, `/ruleEngine/setting-new-rule`, `/ruleEngine/setting-new-rule/:ruleId`, `/ruleEngine/rule-creation/:ruleId` | Placement eligibility rules per degree/department |
| Approvals | `Approvals/` | `/approvals` | Hub for profile, opt-out, job-specific & restriction approvals |
| TPO Approval | `TPOApproval/` | `/tpoApproval`, `/tpoApproval/approval-listing`, `/tpoApproval/student-resume/:studentId` | Field-level profile approval config, approval listing, student resume review |
| TPO Requests | `TPORequests/` | `/tpoRequests` | Job-specific student requests — approve/reject with priority & filters |
| Reports | `Reports/` | `/reports`, `/reports/studentreports` | Management & student reports with export (CSV/Google Sheets) |
| Settings | `Settings/` | `/setting` | Institute info, tax info, partners, additional settings |
| Courses | `Courses/` | `/courses` | Course (degree-stream) management with ElasticSearch sync |
| Assessment | `Assessment/` | `/assessment` | Assessment dashboard, student tracking, charts, reports |
| Drive Info | `DriveInfo/` | `/drives/driveInfo` | Drive detail view with candidate list |

### Supporting Modules

| Module | Folder | Route(s) | Description |
|--------|--------|----------|-------------|
| Auth | `Auth/` | `/signin` | User authentication (sign-in, token management) |
| OnBoarding | `OnBoarding/` | `/onboarding` | Institute registration and initial setup wizard |
| Manage Profile | `ManageProfile/` | `/manageprofile` | User profile management, password change, OTP phone verification |

---

## Architecture

- **State Management:** Redux (actions → reducers → selectors pattern)
- **API Layers:** Multiple Axios instances — `instRequest`, `studentRequest`, `corporateRequest`, `adminRequest`, `elasticSearchRequest`
- **UI Framework:** Ant Design (antd) + styled-components
- **Routing:** React Router v6

## Documentation Structure

Each module folder contains a `README.md` covering:
- Overview & purpose
- Key UI components (Container, Partials)
- Redux actions & API endpoints
- Filters, sorting, pagination
- Related backend services
