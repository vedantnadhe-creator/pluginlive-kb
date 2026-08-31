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

---

## View Drive Report: how each round column is labelled (fixed 2026-08-31, DEV + UAT)

The header's **View Drive Report** export (`PageHeader/Components/InformationHeader.js`
→ `getOneRoleExports` → `POST /instituteReport/instituteCampusId/:id/export/role_wise_report`,
xlsx / csv / Google Sheet) produces one row per applied candidate and **one column per
round** of the role's `interview_workflow`, plus a trailing `Offer Status`. The
per-round cell comes from `manual_status`, built in the SQL in
`institute-node/app/models/iReports.js` → `roleWiseReport`. `INTERNSHIP` /
`APPRENTICESHIP` roles only change the summary header from **CTC** to **Stipend** —
the status logic is identical for every job category.

**The labels are derived from the round's `order` relative to the candidate's current
round** (`stage_orders.round_order`; `stage = 'offer'` counts as `rounds + 1`):

| Situation | Cell |
|---|---|
| Candidate has no `stage` yet (applied only) | *(blank)* |
| Round is **ahead** of the candidate's current round | *(blank)* — not reached |
| Round is **behind**, and `stage_history` mentions it (`to` or `from`) | `Shortlisted` |
| Round is **behind**, `stage_history` exists but omits it | `Skipped` |
| Round is **behind** and `stage_history` is NULL/empty | `Shortlisted` |
| Round **is** the candidate's current round | readable label for `_applyRoleStatus` |

Current-round labels: `ACTIVE` → **In Progress**, `SHORTLISTED`/`SELECTED` →
**Shortlisted**, `REJECTED`/`REJECT` → **Rejected**, `ABSENT` → **Absent**,
`SCHEDULED` → **Scheduled**, `TO_BE_SCHEDULED` → **To be scheduled**,
`RESCHEDULED` / `RESCHEDULE` / `RESCHEDULE_REQUESTED`, `HOLD`/`HOLD_TO_COMPARE`/
`HELD_TO_COMPARE` → **On hold**, `OFFER_RECEIVED` → **Offer received**; anything
else falls back to `INITCAP(REPLACE(status,'_',' '))`.

⚠️ **Two traps this replaced — do not reintroduce either.**

1. **Never emit `so.status::TEXT` directly.** The old query fell through to
   `COALESCE(so.status::TEXT, '')`, so TPOs downloaded cells reading literally
   `ACTIVE` and `SELECTED` — raw `_applyRoleStatus` enum values. Note `SKIPPED` is
   **not** a member of that enum, so every "Skipped" in this report is produced by
   the query, never read from the column.
2. **`Skipped` must not be the `ELSE` branch.** It used to be, which meant every
   round the candidate had simply *not reached yet* was reported as skipped — a
   candidate at round 2 of 4 showed `Skipped` for rounds 3 and 4, and a candidate
   who had only applied showed `Skipped` across the entire workflow.

**`stage_history` is not always populated, and the report must tolerate that.** On
UAT 229 of 3,377 staged mappings (and most of DEV's older test data) have
`stage_history` NULL — for those, absence of a round is *no evidence* of a skip, so
earlier rounds are credited as `Shortlisted`. Only mappings with a non-empty
`stage_history` can produce a `Skipped` verdict. A first pass of this fix ignored
that and turned the whole UAT `68d94ad5` drive into rows of `Skipped`.

**The corporate twin was already correct.** `corporateRoleWiseReport` in the same
file (`POST /instituteReport/corporateId/:id/export/role_wise_report`) maps its
labels and blanks unreached rounds, so it was not touched — but the two queries are
near-duplicates and drift easily; change them together.
