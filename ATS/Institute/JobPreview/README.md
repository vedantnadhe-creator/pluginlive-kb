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
| `ViewResumeDrawer/` | Resume drawer | Student resume side drawer — renders `components/ResumePreview` (a PDF), see below |
| `ViewResumeDrawer/StudentResumeDetailsAction.js` | Resume actions | Resume-related API actions |
| `ViewResumeDrawer/StudentResumeDrawerContent/` | Resume content | **No longer rendered** — the HTML profile-section view the drawer used before 2026-08-19 |
| `components/ResumePreview/` | Resume viewer | Shared PDF viewer: `index.js` (source resolution) + `usePdfPages.js` (pdfjs rasteriser) + `style.js` |

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
- **Resume viewer:** Side drawer showing the student's resume as a **PDF** (see the section below)
- **Role status metrics:** Current status of the job role
- **Archive / restore from the preview header (2026-07-10):** The Job Preview header (`PageHeader/Components/InformationHeader.js`) now exposes **Archive** / **Restore** actions for institute-published roles — the same soft-hide flow as the Job Roles list (see `ATS/Institute/JobRoles` → Archive/Restore, backed by the global `job_roles.is_archived`/`archived_at`/`archived_by` columns and the `archiveJobRole`/`unarchiveJobRole` endpoints). Both use an antd `Modal.confirm` dialog and, on success, navigate back to `/jobRoles`.
- **Drive offer-status tags (2026-07-10):** the ATS candidate table (`ATS/Components/IndividualTable/DriveStatus.js`) now renders three additional `offerStatus` values — `JOINED` → **"Joined"**, `LEFTED` → **"Left"**, `NOT_RELEASED` → **"Intent to Offer"** — alongside the existing offer states.

---

## Resume drawer renders a PDF, not profile data (2026-08-19, DEV + UAT)

The drawer used to render `StudentResumeDrawerContent` — education, skills and
projects as HTML sections, i.e. a profile data dump rather than a resume. It now
renders `components/ResumePreview`, which shows an actual document using the
same treatment as the **JD attachment preview** in the role form
(`modules/JobRoles/NewJobRole/RolesForm/Partials/AutoJDFill`): pages rasterised
to images with pdfjs and stacked in a scrollable frame, so an attachment looks
the same wherever it appears in the product.

**Source order** (`components/ResumePreview/index.js`):

1. the CV the candidate uploaded, when a browser can render it
2. otherwise the **generated system resume**, fetched as a PDF from
   `POST /students/resume/bulkdownload` with `{ studentIds: [[id]] }` — the same
   endpoint the Download Resume action uses, so preview and download cannot
   disagree. Only `studentIds` is required, and a single-element batch is what
   makes student-node stream one PDF instead of a zip.

**Reaches four screens at once.** Role preview, Placement, Students and TPO
Requests all mount the same `ViewResumeDrawer` through
`components/UIComponents/PlacementHistoryWithResume`, so they changed together.
(`components/UIComponents/ResumeandPlacementDrawer` also wraps it but is never
imported — dead code.)

**No backend change was needed.** `cvUrl` was missing from institute-react's
*code*, not from the API: `Student.getById` uses a Prisma `findFirst` with
`include` and no `select`, so `student.cvUrl` (jsonb, mapped from `cv_url`) was
already in the `GET /students/:id` response and simply unused.

⚠️ **Most institute CVs cannot be rendered inline.** Of 14,618 student-level CVs
on UAT, **11,961 are `drive.google.com/open?id=…` links** — HTML pages behind an
auth redirect, not files, so neither pdfjs nor an iframe can display them; 183
are .doc/.docx. These are not dropped: the generated system resume is shown with
a notice and an **Open uploaded CV** button, so the original stays one click
away. Expect the generated resume to be the common case here. Corporate reads
the *role-scoped* `student_role_mapping."cvUrl"` instead, where the split is far
healthier (2,619 renderable PDFs, only 25 Drive links).

**Two URL shapes.** A role mapping stores `cvUrl` as a plain string; the student
record stores jsonb `{ url, name, size }`. `ResumePreview` normalises both, so
call sites do not repeat the ternary.

**`pdfjs-dist` is now declared.** The JD preview has been importing
`pdfjs-dist/webpack.mjs` directly while only receiving the package transitively
through `react-doc-viewer` — a bump of that dependency would have silently
broken both the JD preview and this viewer. Lockfiles are gitignored in this
repo, so it is a one-line `package.json` change pinned to the resolved 4.8.69.

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
