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
| `closeApplication` | `/corporates/{corpId}/jobs/{jobId}/close` | POST | Close a role for applications (no body) |
| `CloseRole` (`modules/JobPreview/action.js`) | `/corporates/{corpId}/jobs/{jobId}/close` | POST | Same endpoint, but with a body — `{ status: 'RE_OPEN', isCompanyId: false }` is how a role is **re-opened**. Bound via `mapDispatchToProps`; see the Cancel / Re-Open note below |
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
| `getRoleLinks` | `/corporates/jobs/{jobId}/role-links` | GET | Role Links page: per-college rows (Tally form URL, POC details, `isEmailSent`, form status) with search/state/city/tier/hasPoc/emailSent/formStatus filters. Also used by the republish drawer (when the role already has published colleges) to load already-published colleges |
| `updateRoleLinksEmailSent` | `/corporates/jobs/{jobId}/role-links/email-sent` | PUT | Mark colleges as emailed — sets `isEmailSent=true` on `JobRoleInstituteMap` for the given `instituteCampusIds` |
| `sendRoleEmail` | `/gmail/sendRoleEmail` (user-management-node) | POST | Role Links "Send Email": per-college personalized Gmail send; on success the backend itself calls `role-links/email-sent` to flip `isEmailSent` |
| `regenerateTallyForm` | `/corporates/jobs/{jobId}/institute/{instituteCampusId}/regenerate-form` | POST | Re-create a single college's Tally form when the original creation failed |

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

- **Full role lifecycle:** Draft → Create → Publish → Active → Close → Re-Open
- **Cancel / Re-Open Role** (`JobPreview/index.js` → `onHandleClose`, button in
  `PageHeader/Components/InformationHeader.js`). One button, two branches off
  `previewData.roleStatus`; both hit the **same** endpoint
  `POST /corporates/{corpId}/jobs/{jobId}/close`:
  - **Cancel** (status is neither `ROLE_CLOSED` nor `COMPLETED`) → dispatches
    `closeApplication` (imported from `modules/Roles/actions`, an **unbound**
    thunk, so `dispatch(...)` is correct), then emails/WhatsApps every applied
    candidate the `RoleCancelledTemplate`.
  - **Re-Open** (status is `ROLE_CLOSED` or `COMPLETED`) → calls `CloseRole`
    with `{ status: 'RE_OPEN', isCompanyId: false }`. No candidate
    notifications — all of that is gated on `!shouldReopen`.
  - Both then call `fetchPreviewData(roleId)` → `getJobRolePreview` →
    `setJobRolePreviewData`, which is what flips the header button back.

  ⚠️ **Do not wrap `CloseRole` in `dispatch()`** — *fixed DEV + UAT 2026-08-19.*
  `CloseRole` reaches the component through `connect`'s `mapDispatchToProps`
  (`JobPreview/Container/index.js`), so it is **already bound**: calling it
  dispatches the thunk and returns that thunk's promise.
  `dispatch(CloseRole(...))` therefore dispatched a **Promise**, and with only
  `redux-thunk` + `authMiddleware` in the chain
  (`src/redux/configureStore.js`) it reached the base dispatch and threw
  *"Actions must be plain objects"*. The throw lands **after** the POST has
  gone out, which is why the symptom was so confusing: the role really did
  reopen in the database, but the exception skipped the
  `fetchPreviewData(roleId)` on the next line and `onHandleClose`'s `catch`
  logged it to the console and swallowed it — **server updated, screen frozen
  on the old status, no error shown**. The fix is to call the connected action
  directly: `await CloseRole(corpId, roleId, payload)`.

  The stale comment that used to sit there claimed `CloseRole` was an unbound
  thunk that "returns the inner function without ever firing the request" —
  true of an older version that imported it directly, and the `dispatch()`
  added to fix *that* is what caused this one. If a role action ever looks like
  it does nothing, first check whether it is a bound prop or a raw import.
- **Institute publishing:** Select institutes by location, tier, specialisation
- **TPO notification on publish:** After a successful publish (Select Colleges drawer), the portal auto-sends the role to each eligible college's POCs — email (`/notification/bulkEmail`, `RoleDetailsToTPOTemplate`) + WhatsApp (`/notification/bulkWhatsapp`, `corporate_role_share_tpo` template). A college is eligible when it has a Tally form URL, at least one POC, and `isEmailSent` is not already true. These sends are **fire-and-forget (not awaited)** so they never block the publish flow. Both payloads are built **in the browser**, so unlike every other ATS WhatsApp path this one is **not** gated on the corporate's `WHATSAPP_NOTIFICATION` subscription — see `Infrastructure/whatsapp-messaging.md`.
- **Bulk "Invite Candidates" upload:** `corporate_role_invite` goes only to candidates of a corporate subscribed to `WHATSAPP_NOTIFICATION` (`admin.feature_config`, fails closed). A `Phone` column on the sheet is still parsed and stored, but no longer implies consent to message. The email leg is unconditional.
- **Email-sent status:** After the auto-notify, the portal calls `role-links/email-sent` (also fire-and-forget) to set `isEmailSent=true` for the colleges that actually had a POC email. The **Role Links page** shows this status and lets recruiters re-send manually via "Send Email" (the `/gmail/sendRoleEmail` path, which marks `isEmailSent` on its own). Colleges with POCs but no email address are not flagged.
- **Republish drawer awareness:** Whenever the "Publish role to" drawer (`SelectCollegesDrawer`) opens with a saved `jobId`, it loads the colleges the role is already published to via `getRoleLinks(jobId)` (no backend change — reuses the existing `role-links` endpoint). The republish UI is **purely data-driven (gated on `publishedCount > 0` from `role-links`), NOT on the `isEditRoleOnView` redux flag** — that flag is only set when editing an *active* role in-session (`RolesTable.onEditClick`, `roleStatus == 'active'`) and **resets to false on page refresh / direct URL load**, so gating on it made the UI vanish on reload. Behaviour:
  - **Banner + read-only drawer:** shown when `publishedCount > 0`. Banner reads *"This role is already published to N institutes"* with an **Already Published (N)** button opening a read-only drawer (`PublishedCollegesDrawer.js`) listing those colleges.
  - **Locked rows:** already-published colleges render **pre-selected + disabled** (antd `rowSelection.getCheckboxProps`) with an *"Already published"* tag, so they can't be unchecked or re-selected.
  - **Payload exclusion:** already-published colleges are filtered out of the republish payload (`instituteCampusIds`) so republishing never re-floats / re-notifies them.
  - **Skip button** (left of "Publish Role"): shown only when `publishedCount > 0` (the role is already published) — never shown for a not-yet-published role. Lets a recruiter who only edited role details finalize without selecting any new college — no publish call, no new TPO notifications. Its confirmation popup makes clear that already-published colleges stay unchanged.
  - First-time create/publish (draft `jobId` with no `role-links`) shows none of the above — no banner, no locked rows, no Skip.
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

## Candidate resume drawers show the uploaded resume, and only that (2026-08-19, DEV + UAT)

Every corporate surface that shows a candidate's resume used to render
`StudentDrawerContent` — education, skills and projects as HTML sections, i.e. a
profile data dump. They now render `components/ResumePreview`, an actual
document, using the same treatment as the **JD attachment preview** in
institute-react's role form (`AutoJDFill`): pages rasterised to images with pdfjs
and stacked in a scrollable frame.

**Seven surfaces, one component:**

| Screen | Component | Before |
|---|---|---|
| Role preview → candidate | `modules/JobPreview/ViewResumeDrawer` | uploaded PDF via `<object>`, else HTML sections |
| Role preview → Institute Info | same, via `PlacementHistoryWithResume` | as above |
| Drives → drive role → candidate | `Drives/…/ViewCandidateInfoDrawer` | as above |
| Exp-Candidates → drive role → candidate | `Exp-Candidates/…/ViewCandidateInfoDrawer` | as above |
| Interview details → candidate | `Page/…/InterviewDetails/CandidateInfo` | as above |
| Role → ATS pipeline → candidate | `Roles/ViewRole/ApplicantTrackingSystem/…/CandidateViewDrawer` | **HTML only — no CV preview at all** |
| Interviewer dashboard → candidate | `InterviewerDashboard/…/CandidateViewDrawer` | **HTML only — no CV preview at all** |

⚠️ **There is no generated-resume fallback, deliberately.** The first cut of this
viewer fell back to the **system-generated** resume whenever there was no usable
upload, which meant a recruiter could not tell a real submission from a document
we had built. That fallback was removed the same day. `ResumePreview` now shows
the uploaded CV or nothing:

| Candidate has | Drawer shows |
|---|---|
| an uploaded CV a browser can render | its pages |
| an upload that cannot be shown inline — Drive link, `.doc`/`.docx`/`.rtf`, or a PDF that fails to parse | **"Unable to display this resume"**, naming the reason, plus an **Open uploaded resume** button (new tab) |
| no upload | **"No resume found"** |

Do not re-add a fallback to `POST /students/resume/bulkdownload` here. The
**Download Resume** actions still call that endpoint and still produce the
generated resume — that is what they are for; the *preview* is the candidate's
own document.

**Two URL shapes.** The role mapping stores `cvUrl` as a plain string
(`student.student_role_mapping."cvUrl"`); the student record stores jsonb
`{ url, name, size }`, and that jsonb is frequently `{"url": ""}` rather than
NULL — `toUrl` normalises both and treats the empty string as absent.
`getUploadedCvUrl` (exported from the same file) gates on
`isSystemResume === false && cvUrl` for the role-scoped surfaces; the two drawers
driven off the student record have no such flag and read
`candidateDetails?.cvUrl` directly.

**Expect "No resume found" to be the common state**, measured on UAT:

| Source | No usable upload | Renderable | Drive link | .doc/.docx |
|---|---:|---:|---:|---:|
| `student_role_mapping` (5 role-scoped surfaces) | 12,386 of 15,442 | 2,842 | 25 | 189 |
| `students.cv_url` (ATS pipeline + Interviewer dashboard) | 26,017 of 40,636 | 2,476 | **11,961** | 182 |

Google Drive links are HTML pages behind an auth redirect, not files, so they can
neither be fetched by pdfjs nor framed — hence the Open-in-new-tab path rather
than a render attempt. On the student-record surfaces they are the *majority* of
uploads, which is why institute-react reverted its equivalent viewer entirely
(see `ATS/Institute/JobPreview`).

⚠️ **`pdfjs-dist` needs its own splitChunks cacheGroup here.** It is ~2 MB and is
imported dynamically, but `config/webpack.prod.js` has a vendor group
(`test: /node_modules/`, `chunks: 'all'`) that sweeps async chunks in too — so
without a dedicated group it lands in the always-loaded `vendors` bundle and the
lazy import buys nothing. The `pdfjs` group uses **`chunks: 'async'`** and
priority 20 (must beat vendor's 10). Verified on a production build: pdfjs emits
as its own 1.56 MiB chunk and is absent from the `main` entrypoint. Its `canvas`
dependency is *optional*, so the image build will not fail on it.

⚠️ **Do not `npm install --legacy-peer-deps` in this repo.** That flag stops npm
installing peer dependencies and silently prunes `react-is` (peer of
styled-components) and `date-fns` (peer of react-date-range), after which the
build dies with ~15 unrelated `Module not found` errors. The Dockerfile uses
`npm install -f`, which does install peers — use that locally too. Note the repo
tracks `yarn.lock` while `package-lock.json` is gitignored and the image builds
with npm; running npm against the yarn lockfile rewrites it with merged ranges
and stray additions, which should not be committed.

---

## Sub-Modules

| Sub-Module | Folder | Description |
|------------|--------|-------------|
| Google Form | `GoogleForm/` | Application Form feature for ITI/Diploma roles — Google Forms integration, templates, per-college form creation |
