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

## Cross-cutting features

Standalone docs in this folder, covering behaviour that spans several modules or
services:

| Doc | Covers |
|---|---|
| `cefr-levels.md` | CEFR bands as the corporate end sees them — pitching the level, how the band is computed, filtering/sorting in Drives |
| `cv-jd-match-scoring.md` | AI resume-vs-JD scoring (corporate-node + fastapi-ai-engine) |
| `shortlist-gate.md` | The shortlist gate for corporate-node-v2 — **built and reverted**, kept as the design record for a rework |
| `v2-strangler-fig.md` | corporate-react-v2 / corporate-node-v2 (**DEV only**) and the v1 nav flip that routes users into them — read before promoting a vertical to UAT/PROD |
| `bulk-candidate-upload.md` | Admin uploads a candidate spreadsheet (any columns) — LLM column mapping with a mandatory admin confirm, applicants enrolled straight into the workflow, and the screening stage's Resume/Form/Both option. **DEV + UAT** |

## Gotchas

**Résumé dates render as "Invalid date" when moment is called without the format token
(fixed 2026-07-29, UAT `8463ac97`).** Résumé `started_in`/`ended_in` are stored in the system format
**`MM/YYYY`** (`"01/2025"`). `moment("01/2025")` with **no** format argument is not RFC2822/ISO, so
moment falls back to `new Date("01/2025")` and yields **`Invalid date`** — the value in the DB is
perfectly good. The Roles candidate drawer
(`modules/Roles/Partials/ViewCollegeDetails/…/StudentDrawerContent/Partials/WorkExperienceSection`)
hit this on both its `resume` and non-`resume` branches, showing `Invalid date - Invalid date` under
every job title; the sibling `Students/` and `Page/` drawers already passed `'MM/YYYY'`, which is why
only the Roles ATS view was affected. Fix parses with `moment(value, 'MM/YYYY')` behind a
`formatMonthYear` helper that also `.isValid()`-guards, so blank/unparseable values render as empty /
`Present` instead of `Invalid date`.

Diagnosis order when you see `Invalid date` here: **read the stored value first.** If it is already
`MM/YYYY`, it is this frontend bug; if it is raw (`2023-07-01`) the normalization payload is at fault —
see `Infrastructure/form-data-normalization.md`. The two are independent and were both live at once.

**Candidate drawer went blank (white screen) on a `null` entry inside a skills array
(fixed 2026-07-30, UAT `ba4afa7f`).** `student.current_course.skills` can hold a **one-element array
containing `null`** — `[null]` — written by the ERP import path; 11 PROD students were in this state when
it was found. Every render site gated the block on `item?.skills?.length > 0` (true for `[null]`) and then
read `value.name` **without** optional chaining, so React threw
`Cannot read properties of null (reading 'name')` **inside render** and unmounted the whole tree — the
user sees an empty page, not a partial one. First reproduced on `prabha+erp90op012@pluginlive.com` in the
Roles → college → candidate drawer.

Fix is a single shared guard, `getNamedSkills()` in `corporate-react/src/utils/commonFunction.js`:

```js
export const getNamedSkills = skills => {
  return Array.isArray(skills) ? skills.filter(skill => skill?.name) : []
}
```

Both the heading gate **and** the `.map` now go through it, so the "Skills" heading disappears when
nothing survives the filter instead of leaving an empty grey pill. Applied at every unguarded `.name`
deref over a `skills` / `skill_set` array:

| Where | Field |
|---|---|
| `modules/Roles/Partials/ViewCollegeDetails/…/EducationSection` | `skills` |
| `modules/Students/…/ViewStudentDrawer/…/EducationSection` | `skills` (also had no React `key`) |
| `modules/Roles/ViewRole/ApplicantTrackingSystem/…/CandidateViewDrawer/Partials/{Internship,WorkExperience,Project}Section` | `skill_set` |
| `modules/InterviewerDashboard/…/CandidateViewDrawer/Partials/{Internship,WorkExperience,Project}Section` | `skill_set` |
| `components/ResumeDownload/Partials/DownloadFile.js`, `modules/Report/Styles/DownloadResume.js` | `skills` + `skill_set`, 5 blocks each |

The two `@react-pdf` renderers also had their `|` separators switched from `item?.skills?.length - 1` to
the filtered list length (the `map` third arg), so the last skill no longer gets a trailing pipe.

Sites already using `item?.name` (`ResumeDownload/Partials/Skills.js`, the `WorkExperienceSection`
drawers in `Students/` and `Roles/Partials/ViewCollegeDetails/`) never crashed — they degrade to empty
output — and were left alone.

**The write path is still unfixed:** something in the ERP `create-full` import writes `[null]` into
`current_course.skills`. The frontend guard stops the white screen everywhere, but bad rows keep
accumulating. To find them:
`SELECT count(*) FROM student.current_course WHERE skills::text LIKE '%null%';`
Related sibling bug on the backend (non-array `skill_set` crashing PDF generation) —
see `ATS/Student/Resume/README.md`.

## Documentation Structure

Each module folder contains a `README.md` covering:
- Overview & purpose
- Key UI components
- Redux actions & API endpoints
- Filters, sorting, pagination
- Related backend services
- [Assessment Dashboard](./assessment-dashboard.md) — /v2 cockpit, list, detail and schedule on corporate-node; accessLevel gate
- [Bulk candidate upload](./bulk-candidate-upload.md) — spreadsheet import with a confirmed column mapping; what the screening stage judges on
