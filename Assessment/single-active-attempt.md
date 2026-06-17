# Single Active Attempt (device concurrency)

> Shipped to UAT June 2026. Prevents the same assessment from being taken on two
> devices/tabs at once, and makes most assessments single-shot (no resume after a
> refresh / tab-leave). Frontend: **Assessment-React**. Backend: **student-node**.

## Problem it solves

Previously an attempt was tracked only by `status` / `startedAt` / `attempted` /
`submitted` on `assessment.assessment_assigned_students`, with nothing tying the
live attempt to one device. `getAssessmentQuestions` returned the question set
for any non-completed assignment and only set `INPROGRESS` when `startedAt` was
null — so a second device (or a refresh) could fetch the questions and run a
parallel attempt, and two devices could even write answers to the same
assignment.

## Backend — the atomic start guard

`student-node` `app/handlers/assessmentHandler.js` → `getAssessmentQuestions`
(the single start entry used by all 7 runtimes):

1. **Atomic claim** — conditionally flip the row PENDING → INPROGRESS:
   `updateMany({ where: { id, status: 'PENDING' }, data: { status: 'INPROGRESS', startedAt: now } })`.
   The conditional update is the serialization point: if two devices press
   Start at the same instant, exactly one matches `status: 'PENDING'` and wins
   (`count === 1`); the other gets `count === 0` and is rejected. Verified live:
   first call → 200, immediate second call → 409 `ALREADY_IN_PROGRESS`.
2. **On a lost claim** (`count === 0`) it reads the current row and calls the
   pure decision in `app/helpers/assessmentStartGuard.js`
   (`resolveAssessmentStartConflict`), which returns `null` (serve) or a
   `{ code, message }` 409.
3. **Rollback** — if the question fetch throws *after* we won the claim, the
   status is reverted to PENDING so a failed start can't strand the attempt.

`getActiveAssessments` now also returns each assignment's `status` (added to the
Prisma `select` and the returned objects) so the frontend can render the button
state.

### Resume rule — diagnosis only

Resume is gated on whether the assessment is a **diagnosis** assessment:
`isDiagnosis = !assessmentCorporateMapId && !assessmentInstituteMap.scheduleId`
(institute-assigned, no schedule — same definition used for `is_diagnosis` in
`getActiveAssessments`).

`resolveAssessmentStartConflict({ status, isPractice, isResume, isDiagnosis })`:

| State | Result |
|---|---|
| `isPractice` | `null` — practice can always be retaken |
| `INPROGRESS`, not a resume (no marker) | **409 `ALREADY_IN_PROGRESS`** — "already in progress on another device" |
| `INPROGRESS`, resume, **diagnosis** | `null` — same-tab resume allowed |
| `INPROGRESS`, resume, **non-diagnosis** | **409 `RESUME_NOT_ALLOWED`** — single-shot, can't resume after refresh / tab-leave |
| `COMPLETED` | **409 `ALREADY_COMPLETED`** |
| `DROPOUT` / unknown | **409 `NOT_STARTABLE`** (fail safe) |

So: **diagnosis** assessments are resumable on the owning tab; **every other
type (institute-scheduled, corporate) is single-shot** — once started, a refresh
or tab-leave cannot get the candidate back in. Unit tests:
`student-node/test/assessmentStartGuard.spec.js`.

## Frontend — Assessment-React

- `src/utils/assessmentSession.js` — **per-tab** in-progress marker in
  **`sessionStorage`** (key `pl_assessment_inprogress_<assigned_id>`). Set on a
  successful start, cleared on submit and on terminal 409s
  (`ALREADY_COMPLETED`, `RESUME_NOT_ALLOWED`). `sessionStorage` is chosen on
  purpose: it survives a refresh / tab-leave within the **same tab** (so a
  diagnosis attempt can resume) but is **not shared** with other tabs, windows,
  or devices — so a second tab/window/device has no marker and is blocked.
  (`localStorage` would be shared across tabs of one browser, which wrongly let
  a second tab resume a diagnosis.) This is not a security boundary — the
  server's atomic claim is.
- `actions.js` `fetchAssessmentQuestions` — appends `&resume=true` when this tab
  holds the marker; on a 409 it shows an antd warning modal (guaranteed visible
  across every runtime) and does **not** start the assessment.
- `AssessmentTable.js` — in-progress assessments still appear in the Active tab,
  but the action button is a **disabled "In Progress"** unless
  `is_diagnosis === true && this tab holds the marker` (only then is it an
  enabled "Take Assessment" for resume).

## Notes / limitations

- The marker is per-tab: closing the tab, or opening the assessment in a new
  tab / window / device, looks like "someone else" and is blocked. For a
  non-diagnosis attempt that means it's then stuck INPROGRESS — recovery is an
  admin/assessment reset.
- DEV `assessment-react` is **not** a container: it is served by bare
  `node server.js` from `/home/ubuntu/frontend/Assessment-React/build` on port
  3006, so a DEV update requires `npm run build` there (webpack `webpack.prod.js`
  bakes from `.env`) — the push-to-Development auto-deploy does **not** rebuild
  it. UAT/PROD use the Docker image via `auto_deploy.sh`.
- No DB schema change — the existing `AssessmentStatus` enum
  (`PENDING / INPROGRESS / COMPLETED / DROPOUT`) carries the lock.
