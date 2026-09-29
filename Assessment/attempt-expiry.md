# Attempt expiry & the dropout cron (`expires_at`)

**Status:** LIVE on DEV + UAT 2026-09-29 (student-node `1f7106bf` DEV / `362bd43d` UAT,
assessment-react-v2 `7c32003` DEV / `3dfaf6d` UAT). **PROD pending** — the SQL below must be
applied on PROD *before* the student-node image that reads it.

## What decides that an attempt was abandoned

Every open attempt carries its own deadline in
**`assessment.assessment_assigned_students.expires_at`** (TIMESTAMPTZ, nullable):

```
expires_at = sitting start + Σ over the sitting's UNFINISHED parts of (part duration + 5 min grace)
```

- **Part duration** = the number the candidate's clock shows, from
  `MixMatchJourney.getSummary` → `helpers/attemptDuration.resolveDurationMinutes`:

  | Type | Duration |
  |---|---|
  | Aptitude | from question count: 25 → 30 min, 30 → 45, 40 → 60 |
  | Communication / Hinglish | summed from the enabled sections (full paper = 30) |
  | Role_Based | `assessment_config.duration_minutes` (1–240) or estimated from question counts |
  | Custom_Assessment | Σ `custom_assessment_config.time_in_minutes` |
  | Behavior | 20 |
  | AI_Interview | `ai_interview_config.interview_duration` (seconds → minutes) |

  If no duration resolves, the old flat timeouts are the fallback (Aptitude / AI Interview 60,
  everything else 22).
- **A Mix & Match float shares one deadline** across all its unfinished parts (opening a float
  claims every part at once, so a part's own start says nothing). A single assignment is a
  sitting of one part.
- **5 min grace per part**: the runner auto-submits at zero, so the grace only covers the last
  upload and the submit landing.

## Who writes it

- **On start** — `helpers/attemptExpiry.stampSittingExpirySafely`, called after the atomic
  `PENDING → INPROGRESS` claim (and the dropped-diagnosis reclaim) in
  `assessmentHandler.getAssessmentQuestions`, and after the AI Interview start flip in
  `aiInterviewHandler`. It re-stamps every INPROGRESS part of the sitting. A failure is logged
  (`[ATTEMPT EXPIRY]`) and never blocks the start; adds ~15–35 ms per start.
- **Repair** — the cron stamps any INPROGRESS row with `expires_at IS NULL` (started before the
  column shipped, by an old pod mid-rollout, or a failed stamp) from its own
  `assessment_started_at`, ≤50 per tick. A row whose sitting can't be resolved gets
  `started_at + 60 min` so it is never retried forever.
- **Cleared** when a diagnosis is reset to PENDING.

## The cron (`script/updateDropoutStatusCron.js`, every minute)

`script/scheduler.js` runs it `* * * * *` with an in-process overlap guard (plus once on boot).
Each tick:

1. Retry unscored AI Interview drop-offs; enqueue scorable drop-offs (unchanged).
2. Stamp missing deadlines (above).
3. `WHERE status='INPROGRESS' AND submitted=false AND expires_at < now()` (≤500, partial index
   `idx_aas_open_attempt_expires_at`):
   - **Diagnosis** (`is_diagnosis = true` — *not* the map name "Assessment #1/#2") → back to
     **PENDING**: `attempted=false, startedAt=NULL, expiresAt=NULL, droppedAt=NULL`. A diagnosis
     is never a drop-off.
   - **Everything else** → **DROPOUT** (`attempted=true, droppedAt=now()`), audit row, AI
     Interview finalize + score as before.
   - Both writes re-check `status='INPROGRESS' AND submitted=false AND expires_at < now` in the
     WHERE, so a sitting that submitted or was re-started between SELECT and UPDATE is untouched.

Log lines to grep: `[DROPOUT] stamped a deadline on N open attempt(s)`,
`Found N open attempt(s) past their deadline`, `Reset diagnosis for …`, `Updated student … to DROPOUT`.

## Why (the bugs this replaced)

- The old cron timed every type with a flat **60 min (Aptitude) / 22 min (everything else)**: a
  90-min Role_Based paper was dropped at minute 22 while the candidate was still on the clock;
  a 30-min Aptitude paper sat "In progress" for an hour.
- The diagnosis reset filtered `attempted = true`, which **PLG-590 (2026-05-08) stopped writing
  at start** — so every abandoned diagnosis stayed INPROGRESS forever, and re-entry got a 409
  "already been completed" (shown as "We hit a snag"). At rollout: UAT 14 such rows (oldest
  2026-05-08), DEV 1, PROD 8 — all reset on the first tick after deploy.
- `helpers/mixMatchDropout.js` (`splitMixMatchParts`) is **deleted**; the sitting rule now lives
  in `attemptExpiry.sittingExpiresAt`. Difference: a float's deadline is fixed from the (latest)
  claim; a part submit does not push it forward.

## Candidate-facing refusal (409)

A diagnosis runs in one place at a time. While it is INPROGRESS every other tab/device — and a
candidate who closed the tab — is refused until `expires_at`:

- `POST /students/assessments/:id/session` and the questions start guard return
  `409 { message, data: { code, retryAt? } }` with `code` ∈ `ALREADY_IN_PROGRESS`
  (`retryAt` = `expires_at`, diagnosis only), `ALREADY_COMPLETED`, `NOT_STARTABLE`
  (`helpers/assessmentStartGuard.resolveSessionConflict` / `conflictResponseData`).
  Previously `/session` answered every case "This assessment has already been completed".
- `GET` mix-match summary returns `expiresAt` per part.
- **assessment-react-v2** `/assessment` overview (`src/lib/attemptConflict.ts`) shows
  **"Already in progress"** — "open in another tab or on another device … Continue it there. If
  you closed it by mistake, you can start again after <local time>" + *Check again* — instead
  of "We hit a snag". Completed / no-longer-available get their own copy.

## Migration

DB-Scripts `Assessment Attempt Expiry/20260929T063113Z__assessment_assigned_students_expires_at.sql`
(column + `COMMENT` + partial index `WHERE status='INPROGRESS' AND submitted=false`).
DEV applied 2026-09-29, UAT applied 2026-09-29, **PROD pending**. Prisma field `expiresAt` in
`schema-assessment.prisma` (student-node, admin-node).

**Deploy order per env: SQL → student-node → assessment-react-v2.** A student-node image without
the column errors in the cron every minute (no drop-offs recorded) until the SQL lands.
