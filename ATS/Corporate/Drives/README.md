# Drives Module

**Routes:**
- `/drives/role/:roleId` — Drive for a specific role (fresher)
- `/drives/:driveId/role/:roleId` — Specific drive for a role (fresher)

**Frontend:** `corporate-react-1/src/modules/Drives/`

## Overview

The Drives module manages placement drives — the scheduled evaluation events where corporates interview candidates from institutes. It provides drive-level candidate management, interview scheduling, evaluation forms, result uploads, offer management, conflict resolution, and bulk actions. This is the execution layer of the hiring pipeline.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main listing | Drive listing per role |
| `Container/individualDrive.js` | Individual drive | Single drive details |
| `Container/individualDriveRole.js` | Drive role | Drive-role combination view |
| `Components/DrivePage/` | Drive page | Drive overview page |
| `Components/DriveStatus/` | Status | Drive status display |
| `Components/DriveTable/` | Table | Drive data table |
| `Components/EvaluationForm/` | Eval form | Candidate evaluation form |
| `Components/ResolveConflict.js` | Conflicts | Resolve scheduling conflicts |
| `ViewDrive/DriveDetails/` | Drive details | Detailed drive information |
| `ViewDrive/DriveRightPart/` | Right panel | Drive detail right section |
| `ViewDrive/DriveTimeDrawer/` | Time drawer | Schedule time management |
| `ViewDrive/AddInterviewerDrawer/` | Interviewer | Add interviewer to drive |
| `ViewDriveRole/` | Drive role view | Role-specific drive view |
| `ViewDriveRole/IndividualDriveTable/` | Individual table | Per-candidate drive table |
| `ViewDriveRole/IndividualDriveTable/SelectAssessmentDrawer/` | Assessment mapping | Map an assessment to selected candidates in a round |
| `ViewDriveRole/GroupDiscussionTable/` | GD table | Group discussion table |
| `ViewDriveRole/BulkActionDrawer/` | Bulk actions | Bulk status updates |
| `ViewDriveRole/Header/` | Header | Drive role page header |
| `DownloadAndUpload/` | Upload/Download | Bulk operations hub |
| `DownloadAndUpload/DownloadCandidateDrawer/` | Download | Download candidate data |
| `DownloadAndUpload/UploadResultDrawer/` | Results | Upload evaluation results |
| `DownloadAndUpload/UploadShortlistedDrawer/` | Shortlist | Upload shortlisted candidates |
| `DownloadAndUpload/UploadOfferDrawer/` | Offers | Upload offer details |
| `DownloadAndUpload/UploadAssessmentDrawer/` | Assessment | Upload assessment results |

---

## Redux Files

| File | Purpose |
|------|---------|
| `actions.js` | Drive API action creators |
| `reducers.js` | Drive state reducer |
| `selectors.js` | Drive state selectors |
| `utils.js` | Drive utility functions |

---

## Key Features

- **Drive pipeline:** Create drive → Schedule interviews → Evaluate → Upload results → Offer
- **Fresher evaluation:** Route prefix indicates this is for fresher candidate drives
- **Bulk uploads:** CSV-based uploads for results, shortlists, offers, and assessments
- **Interviewer assignment:** Add interviewers to drives with time scheduling
- **Group discussion:** Dedicated GD round management
- **Conflict resolution:** Resolve scheduling conflicts across drives
- **Candidate downloads:** Export candidate data from drives
- **Select Assessment:** In `IndividualDriveTable`, the `+ Select Assessment` button (rendered by `TableStatusIcon`) opens `SelectAssessmentDrawer` to map an assessment onto the selected candidates. The button and drawer are available on **every evaluation round** where the stage is not `all_candidates` or `offer` — i.e. Assessment, Group Discussion, Interview, etc. (Previously the drawer only mounted for `selectedRoundType.type === 'ASSESMENT'`, so the button did nothing on GD/Interview rounds — fixed so the drawer mounts wherever the button is shown.)
- **Assessment Status column & filter:** When the round being viewed has an assessment mapped to it, the evaluation table shows an **Assessment Status** column and a matching multi-select filter (`AssessmentStatusBadge` + `AssessmentStatusFilter` partial). Statuses: **Invite Pending** (mapped but invite not sent yet — no `assessment_assigned_students` row), **Pending** (invited, not started — also covers in-progress), **Dropped Off** (`DROPOUT`), **Completed** (submitted / scores calculated). Per-candidate status is sourced live from the Assessment DB via admin-node: corporate-node `getCandidateListForHR` → `AdminService.getCellStatusBundle` → admin-node `POST /corporate/:corporateId/cell-statuses` (model `Assessment.getCellStatusBundle`). For a round mapped to multiple assessments the status rolls up to the **most-progressed** one, so a single meaningful status surfaces: **Completed** wins over every lesser state. This matters because candidates are frequently invited to only *one* of the mapped assessments — the un-invited assessment has no `assessment_assigned_students` row and would otherwise yield a phantom **Invite Pending** that, under the old least-progressed rule, masked a real **Completed** (the candidate read "Invite Pending" and the score column showed `NA` — see below). Most-progressed-wins ensures a candidate who finished any one of the mapped assessments reads **Completed** and their score shows. The response carries `assessment_status` per row plus a top-level `assessmentStatusColumn` flag that gates the column + filter. Filtering is server-side across all pages (handler resolves selected labels → allowed `student_id` list → SQL `AND jrsm.student_id IN (...)`, mirroring the Round Score filter). The flag is also set on the empty-result (`No candidate found`) early-return path — so filtering to a status with zero matches (e.g. `Completed` when nobody has completed) keeps the Assessment Status filter tab/column instead of dropping it and showing "No content".
- **NA assessment scores until Completed:** For an assessment-mapped round, the per-topic assessment **score columns render `NA`** until the candidate's `assessment_status === 'Completed'` (previously they showed a misleading `0` for candidates who had not started/finished). Completed candidates show real scores, including a genuine `0`. Sheet/manual (non-assessment) rounds keep their existing `0`-default behavior. Gate in `IndividualDriveTable` score-cell render: `candidateDeatils.assessmentStatusColumn && originalTopic === stage && row.assessment_status !== 'Completed'`.
- **Filtered evaluation export:** The evaluation-table export (XLSX / Google Sheet / CSV, `ViewDriveRole` → `handleExportClick`) honours the **candidates currently in view** — the active stage/filter/search and any explicit row selection — instead of dumping every applied candidate for the role. Resolution order in `handleExportClick`: explicit row selection (`selectedCandidateId`, the table `rowKey = student_id`) wins; otherwise `fetchBulkStudentIds()` resolves the full filtered set via the **same list source** the table uses (`getNewDriveFreshersList` → corporate-node `getCandidateListForHR` with `bulkDownload: true`, same payload as the displayed list). The resolved IDs are sent as `studentIds` to student-node `POST /students/role/:roleId/corporate/:corporateId/candidates/:downloadType/export`. This **resolve-then-export** design (rather than re-sending the raw filter object to the export endpoint) guarantees the export matches the displayed list 1:1 for **every** filter — including the ones resolved only inside corporate-node (Assessment Status, Round Score, Qualifying/Custom Questions, Work Experience) which the student-node export path does not re-implement. Backend: handler `exportCandidateList` already read `req.body.studentIds` and filters `getStudentDetailsForExport` by `id IN studentIds`, but the `candidateExportBody` schema was `additionalProperties: false` without `studentIds`, so the field was rejected — schema now declares `studentIds` (array of strings).
- **Export disabled when zero candidates:** The export icon (`AtsExportIcon`) is disabled when there are no candidates to export — either the stage is empty (`getStageCount() === 0`) **or** the active filter/search narrowed the current view to zero (`count` / `notDisabledCount` / `totalCount` on `candidateDeatils` all `0`/absent). Click is a no-op while disabled (`if (isDisabled) return`).
