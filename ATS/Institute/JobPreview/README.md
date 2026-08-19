# Job Preview Module

**Route:** `/jobRoles/jobPreview/:roleId`
**Frontend:** `institute-react/src/modules/JobPreview/`

## Overview

The Job Preview module provides a detailed view of a specific job role. It displays job details, candidate lists, placement history, role status, and student resume viewing capabilities. Accessed from the Job Roles listing.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Job preview page orchestration |
| `PageHeader/` | Header | Job preview header with actions |
| `PageHeader/Components/` | Header components | Reusable header sub-components |
| `Components/JobDetails.js` | Job details | Full job role details display |
| `Components/JobCandidateList.js` | Candidate list | Candidates applied/shortlisted for the role |
| `Components/PlacementHistory.js` | Placement history | Historical placement data for the role |
| `Components/PlacementTable.js` | Placement table | Tabular placement data |
| `RoleStatus/` | Role status | Current role status and metrics |
| `ViewResumeDrawer/` | Resume drawer | Student resume side drawer — renders `StudentResumeDrawerContent` (profile sections), see below |
| `ViewResumeDrawer/StudentResumeDetailsAction.js` | Resume actions | Resume-related API actions |
| `ViewResumeDrawer/StudentResumeDrawerContent/` | Resume content | The HTML profile-section view — education, skills, projects. **This is what the drawer renders.** |

---

## Redux Files

| File | Purpose |
|------|---------|
| `action.js` | API action creators |
| `reducer.js` | State reducer |
| `selector.js` | State selectors |
| `constant.js` | Module constants |

---

## Key Features

- **Role detail view:** Comprehensive job role information
- **Candidate tracking:** View candidates and their status for the role
- **Placement history:** Historical placement data
- **Resume viewer:** Side drawer showing the student's profile sections (see the section below — the PDF viewer trialled on 2026-08-19 was reverted the same day)
- **Role status metrics:** Current status of the job role
- **Archive / restore from the preview header (2026-07-10):** The Job Preview header (`PageHeader/Components/InformationHeader.js`) now exposes **Archive** / **Restore** actions for institute-published roles — the same soft-hide flow as the Job Roles list (see `ATS/Institute/JobRoles` → Archive/Restore, backed by the global `job_roles.is_archived`/`archived_at`/`archived_by` columns and the `archiveJobRole`/`unarchiveJobRole` endpoints). Both use an antd `Modal.confirm` dialog and, on success, navigate back to `/jobRoles`.
- **Drive offer-status tags (2026-07-10):** the ATS candidate table (`ATS/Components/IndividualTable/DriveStatus.js`) now renders three additional `offerStatus` values — `JOINED` → **"Joined"**, `LEFTED` → **"Left"**, `NOT_RELEASED` → **"Intent to Offer"** — alongside the existing offer states.

---

## Resume drawer: the PDF viewer was shipped and reverted the same day (2026-08-19, DEV + UAT)

**Current state: the drawer renders `StudentResumeDrawerContent`** — education,
skills and projects as HTML sections. That is the intended behaviour on the
institute side. If you are looking for the PDF viewer, it lives **only in
corporate-react** (`ATS/Corporate/Roles` → "Resume drawers show the uploaded
resume"); this repo has no `components/ResumePreview`.

History, so nobody re-does it: on 2026-08-19 the drawer was switched to a pdfjs
document viewer (`065cf832`) and reverted hours later on the same day
(`7d878cf1`, merged to UAT as `3fde2b7b`). TPOs want the structured profile view
here — they are looking at their own students' data, not screening a submission.

⚠️ **Why a document viewer is a bad fit for this repo specifically.** Institute
screens read the *student-level* CV (`student.students.cv_url`, jsonb
`{ url, name, size }`), and on UAT **11,961 of 14,618 of those are
`drive.google.com/open?id=…` links** — HTML pages behind an auth redirect, not
files, so neither pdfjs nor an iframe can display them; another 183 are
.doc/.docx. A viewer here would show a fallback for the overwhelming majority.
Corporate reads the *role-scoped* `student_role_mapping."cvUrl"` instead, where
the split is far healthier (2,842 renderable PDFs, only 25 Drive links).

**Four screens share this drawer.** Role preview, Placement, Students and TPO
Requests all mount `ViewResumeDrawer` through
`components/UIComponents/PlacementHistoryWithResume`, so any change here hits all
four at once. (`components/UIComponents/ResumeandPlacementDrawer` also wraps it
but is never imported — dead code.)

**`cvUrl` is available but unused.** It was missing from institute-react's
*code*, not from the API: `Student.getById` uses a Prisma `findFirst` with
`include` and no `select`, so `student.cvUrl` is already in the
`GET /students/:id` response.

**`pdfjs-dist` stays declared in `package.json`** — that line was kept through
the revert on purpose. `JobRoles/NewJobRole/RolesForm/Partials/EligibiltyCriteria/CommonFunctions.js`
imports `pdfjs-dist/webpack.mjs` directly for the **JD attachment preview** while
only receiving the package transitively through `react-doc-viewer`; a bump of
that dependency would silently break the JD preview. Lockfiles are gitignored in
this repo, so it is a one-line pin to the resolved 4.8.69.

---

## Placed count: two sources, one definition (fixed 2026-08-12, UAT)

The **Job Roles listing** and this page count placements from different columns of
the same `corporate.job_role_candidates_metrics` row:

| Screen | Source |
|---|---|
| Job Roles listing — "Placed students" | `jrcm.placed_candidates` (int), selected in `corporate-node/app/models/JobRoles.js` → `getRolesForCampus` |
| Job Preview — "placed students" tile and its tab list | `jrcm.closed_role_count->'placedCandidateIds'`, read by `student-node` → `Student.candidateMetricsCount` (list for a closed role: `ClosedRoleCandidateList`) |

Both are written from the same rebuild, so they only diverge when the *definition* of
placed differs from what the counter was incremented for.

- **A `JOINED` candidate vanished from this page while the listing still counted them.**
  Placed was matched as `_offerStatus = 'ACCEPTED'` **exactly** — in
  `corporate-node/app/models/EligiblityUpdate.js` → `findPlacedCandidates` (which
  rebuilds `placedCandidateIds`), in the drive-based rebuild in
  `corporate-node/app/helpers/jobRoles.js`, and in `student-node`'s live queries
  (`findManyCandidateList`, `manyJobCandidateMetricsCount`). `JOINED` and `LEFTED` can
  only be reached *from* `ACCEPTED`, so the moment a corporate marked a candidate
  joined they stopped matching and were dropped from the ids on the next rebuild —
  the tile fell back to 0 and the PLACED tab went empty, while the int counter kept
  the number it had been incremented to. Seen on DEV as 26 metric rows with
  `placed_candidates > 0` and an empty `placedCandidateIds`.
- **Fixed** by making placed mean the post-acceptance offer states —
  `('ACCEPTED', 'JOINED', 'LEFTED')` — via a shared `PLACED_OFFER_STATUSES` constant in
  both repos. `CandidateListByRole`'s `status === 'PLACED'` filter is deliberately left
  ACCEPTED-only: that is the corporate ATS view, which has a separate explicit `JOINED`
  filter.
- **Existing rows self-heal, they are not backfilled.** `placedCandidateIds` is only
  rewritten when a metrics rebuild runs for that role/campus (offer and evaluation
  actions trigger `POST /corporate/metrics/update/trigger`); the rebuild also realigns
  the int counter to `placedCandidateIds.length`, which clears counters that had
  drifted above the real count.
