# Assessment Assignment & Calculation Queues

Async, reliable, flag-gated pipelines that replace the old synchronous bulk-assign
and the cron-only score calculation. Live on **DEV** and **UAT** (flag-gated).

## Why

- **Assignment** used to run inline on the assign request — at 1000+ students it
  timed out, partially applied, and had no per-student retry. It is now an async
  pipeline with a job header + per-student work items, full retry, and live progress.
- **Calculation (scoring + progression)** used to be driven only by a once-a-minute
  cron scoring one assessment per tick. It is now queue-driven: enqueue-on-submit →
  parallel workers → deferred progression job. The cron becomes a check-only sweeper.

Both are **flag-gated** so the old paths stay reachable for instant rollback.

## Assignment queue (admin-node)

- Tables: `assessment.assessment_assignment_jobs` (one row per assign action) and
  `assessment.assessment_assignment_items` (one row per student — the unit of state
  & retry). A job may reference multiple maps (e.g. Aptitude diagnosis pair) via the
  `maps` jsonb.
- Stages per item: `provision → assign → notify` (BullMQ workers on Redis). Item
  status: pending → provisioning → provisioned → assigning → assigned → emailing →
  done | failed | skipped.
- Covers every type (Aptitude, Communication, Behavior, Role_Based, Custom,
  AI_Interview) and every flow (institute/corporate, one-time/scheduled, OTP/non-OTP).
  The scheduler routes through the same dispatch, tagged `trigger_source =
  schedule_run | schedule_create` (manual = `manual`).
- Idempotent: dup-email-as-success, `INSERT … WHERE NOT EXISTS` for assigned rows,
  `emailed_at` re-send guard, and an idempotency key that dedupes double-submits.
- **Flag:** `ASSIGNMENT_ASYNC_ENABLED=1` (all types) or `ASSIGNMENT_ASYNC_TYPES=<csv>`
  (per type). Empty/unset → old synchronous path. Workers run in a forked process
  (`script/startWorkers.js`); requires `REDIS_URL`.
- Uses raw `pg` (node-postgres), **not** Prisma, for worker DB writes — the Prisma
  engine panics under the workers' concurrent writes on ARM64.

### Emails (admin → creator)
- **Assignment started** — fired once at job creation (manual assigns only); gives the
  admin an immediate link to the live Activity page.
- **Summary** — on terminal state (complete / finished with failures); manual = always,
  scheduled = failure-only. Claim-once via `summary_emailed_at`.
- Both are email-client-safe (table/inline-CSS, bulletproof CTA) and deep-link to the
  job's real-time activity page: `${ADMIN_FE_BASE_URL}/assessment/activity/job/<jobId>`.

## Calculation + progression queue (student-node)

- Enqueue-on-submit: `submitAssessment` pushes a calc job keyed on
  `assessment_assigned_id` (type-agnostic — fires for every submit).
- `calcWorker` scores via the **same** `calculateAssessmentScore(...)` the cron used
  (so every type is covered), with a media-race guard (defer scoring until a Video
  Response `object_key` lands) and an AI-concurrency gate (Comm/Hinglish/Role_Based/
  AI_Interview → bounded, to avoid Gemini 429 / FastAPI 504 storms).
- `progWorker` runs deferred progression for the two types that have it —
  Communication (`updateCurrCERFlevelOfStudent`, full ordered replay) and Aptitude
  (`runAptitudeProgression`, incremental with a predecessor-integrity backfill on
  out-of-order / broken chains). Same functions and order as the inline path.
- DB flags on `assessment_assigned_students` (`scores_calculated`, `calculation_error`,
  `calculation_attempts`, `is_processing`, `processing_started_at`) are the **source of
  truth**. `calc_jobs` is an **optional** per-attempt audit log (worker writes are
  try/catch — scoring never depends on it). The cron, in async mode, becomes a
  check-only sweeper that re-enqueues any `scores_calculated=false` straggler.
- **No new required schema** — it reuses the existing scoring columns + `progression_history`.
- **Flag:** `CALCULATION_ASYNC=true` (default `false` = old inline cron). Requires
  `REDIS_URL`. Concurrency: `CALCULATION_CONCURRENCY` (4), `PROGRESSION_CONCURRENCY`
  (2), `AI_CALC_CONCURRENCY` (2).

### Retry model (Model A — sweeper-driven) + the stable-jobId gotcha

On a scoring failure the worker does **NOT** throw — it catches, increments
`calculation_attempts`, releases the row to pending (or sets `calculation_error`
once it hits the cap: 3 non-transient / 10 transient), and lets the **sweeper**
re-enqueue. The retry is therefore driven by the sweeper re-running the worker,
not by BullMQ's own `attempts` (which only cover hard crashes since the worker
never throws).

**Critical gotcha (fixed 2026-06-30):** re-enqueue uses a **stable jobId**
(`calc__<id>`), and since the worker's job lands in BullMQ `completed` (it didn't
throw) and is retained (`removeOnComplete` count), a same-jobId `add()` was a
**silent no-op** → released-pending rows **never actually retried** (stuck at
attempts=1, never reaching `calculation_error`, so no Retry affordance), and an
admin/drawer recalc that only reset flags also went nowhere. Fix = **remove the
job before re-adding** everywhere we re-enqueue:
- **sweeper** (`script/calculatePendingAssessmentCron.js`) — `remove(jobId)` then
  `add(jobId)` (rows it selects are `is_processing=false`, so removing is safe);
- **drawer recalc** (`resetForRecalculation`, Communication/AI_Interview/Role_Based)
  now re-enqueues **immediately** (remove-then-add) instead of only resetting flags
  and waiting on the sweeper (Aptitude still recalcs inline);
- the student-node retry handler (`calcQueueHandler`) already did remove-then-add.

**Admin Retry-scoring** (admin-node `assignmentDb.retryCalc`) resets `failed` rows
**and** stuck `pending` rows that already tried (`calculation_attempts > 0`, not
yet scored) — earlier it only reset `calculation_error=true`, so a stuck-pending
row couldn't be recovered. The Activity UI shows the **Retry** button for `failed`
**or** `pending`-with-attempts>0 (was `failed`-only), and the ATTEMPTS column now
shows in the Pending view too. DEV ✅ · UAT ✅ · PROD pending.

## Activity UI (admin-react)

- **Manage Assessments → Assignment Activity** tab: a server-paginated list of all
  assignment jobs (scoped to the institute/corporate tab). Each row has a **Detail**
  button (and is row-clickable) → the per-job activity page.
- **Per-job activity page** `/assessment/activity/job/:jobId` — real-time (polls until
  terminal): a progress header (Total / Assigned / Notified / Failed + %), a
  server-paginated per-student table (Failed / Pending / Done / All filter), and
  per-student retry (incl. edit-and-retry for data errors).
- **Submit-and-go progress modal** (`AssignmentProgressModal.js`) — the popup shown
  right after an async assign returns `{ jobId }` (live `assigned/total` + Continue).
  It is **SSE-first with a REST hydrate on open**: on mount it calls
  `getAssignmentStatus(jobId)` once for the current snapshot, then subscribes to
  `GET /events/subscribe?topic=assessment-assignment:<jobId>` for deltas, and falls
  back to `pollAssignmentStatus` only if the stream errors. **The hydrate is required
  (fix 2026-07-03):** a fast/small job (e.g. 1 candidate) reaches a terminal state
  *before* the SSE subscription lands; server SSE (`admin-node SSEService`) has **no
  backlog/replay** and drops events published to a topic with zero subscribers, and
  only sends a `CONNECTED` frame on connect. A cleanly-opened-but-silent stream never
  fires `onerror`, so the poll fallback never starts — without the hydrate the modal
  stayed stuck at **0/total** even though the job had finished (item `done`, summary
  email sent). Large batches never showed it (assign takes long enough that subscribe
  lands first).
- **Assignment | Calculation toggle** on the detail page. The **Calculation** view
  shows scoring counts (Submitted / Scored / Pending / Failed) + a per-student scoring
  table with **Retry scoring** (admin-node resets the calc flags; student-node's
  sweeper re-enqueues — no cross-service call). ATTEMPTS shows only in the Failed view
  (it's a failure-retry counter, reset to 0 on success).

## Scheduler → queue (gotcha)

When `ASSIGNMENT_ASYNC_ENABLED` is on, the scheduler (`AssessmentSchedulerService`)
routes through the same dispatch and passes `{ triggerSource:'schedule_run', scheduleId }`
as **asyncOptions**. The async slice writes `assessment_institute_map.schedule_id` only
`if args.scheduleId` is truthy, and tags the job `schedule_run`.

A positional-arg bug (fixed 2026-06-27) had the scheduler passing `asyncOptions` into the
`isOtpInvite` slot (off by one), so `scheduleId`/`triggerSource` were dropped → scheduled
queue assigns saved `schedule_id = NULL` on the map (lost schedule linkage) **and** the job
tagged `manual`, **and** `isOtpInvite` became truthy (treated as OTP). Fix = pass
`isOtpInvite=false` before `asyncOptions` in both the Communication and Aptitude scheduler
calls. Any maps already created with NULL `schedule_id` from a scheduled run need backfill
(match by entity + assessment_type + name → schedule).

## Progression gate (scheduled assessments)

Blocks a student from **starting** an institute **scheduled** assessment until the
**previous assessment of the same type** has been fully scored **and** its
`progression_history` row (CEFR / aptitude level) has landed. This kills a race where
set-selection reads the latest progression to pick the next CEFR/level set, but the
predecessor's progression hadn't been written yet → wrong-difficulty set.

- **Scope:** only institute, **scheduled** (`assessment_institute_map.schedule_id != NULL`),
  non-practice, non-one-time assessments of **Communication + Aptitude** (the only types
  whose set is chosen from prior progression). Diagnosis (no `schedule_id`), corporate,
  practice, one-time, and other types are never gated. Diagnoses can be taken **in any order**.
- **Order-independent logic** (`student-node/app/helpers/progressionGate.js`): block unless
  (1) no same-type predecessor is still mid-scoring (`submitted && !scoresCalculated &&
  !calculationError`), (2) none permanently failed (`calculationError`), and (3) the
  latest-submitted scored predecessor has a `progression_history` row with the field the
  set-selector reads (`suggested_cefr` for Communication, `assessment_aptitude_level` for
  Aptitude). For the 1st scheduled (3rd overall), the predecessor is the 2nd diagnosis.
- **Freshness window:** only blocks while the latest same-type submission is within
  `PROGRESSION_GATE_MAX_WAIT_MIN` (default 30m). Beyond that the chain is "settled"
  (progression landed, or it's a permanent data gap the profile-CEFR fallback covers) →
  never permanently lock a student.
- **Hard gate** (`getAssessmentQuestions`, before the PENDING→INPROGRESS claim, first-start
  only — resumes never blocked): HTTP **409** `PROGRESSION_PENDING` (transient) or
  `PROGRESSION_FAILED` (predecessor scoring failed). **Soft flag** `progressionLocked` on
  each `getActiveAssessments` row → Assessment-React disables **Take Assessment** with a
  "Processing previous result" tooltip; on start, `PROGRESSION_PENDING` shows an info
  "Almost ready" modal (vs a warning for `PROGRESSION_FAILED`).
- **No new schema** — reuses `progression_history` existence + calc flags.
- **Flag:** `PROGRESSION_GATE_ENABLED=1` + `PROGRESSION_GATE_TYPES=Communication,Aptitude`
  (student-node). Off → gate inert.

## Video upload-wait optimization (scoring)

Communication/Hinglish video scoring used to wait **3 × 60s for every missing video** —
including ones the student never recorded — adding ~3 min to a calc even for a reading-only
submission. Now (`student-node/app/helpers/videoUploadWait.js`,
`resolveAttemptedVideoUrl`): only wait when the student **attempted** the video (a
`student_answers` row exists but its `object_key` upload is still landing → short bounded
retry, default **3 × 10s**, env `VIDEO_UPLOAD_WAIT_RETRIES` / `VIDEO_UPLOAD_WAIT_INTERVAL_SEC`).
A **skipped** video (no answer row) is scored 0 **immediately**. Mirrors the skip
optimization already in `RoleBasedCalculations`. The frontend already awaits all audio/video
uploads before calling submit, so by enqueue time attempted media is saved.

## Schema (apply per env, idempotent)

- admin-node migrations: `assignment_queue_001_jobs_and_items.sql`,
  `assignment_queue_002_summary_emailed_at.sql`.
- `calc_jobs` (optional): `(assessment_assigned_id, kind)` PK + state/attempts/last_error/finished_at.
- DEV ✅ · UAT ✅ · PROD pending.

## Config / rollback

| Service | Flag | Other env |
|---|---|---|
| admin-node | `ASSIGNMENT_ASYNC_ENABLED=1` (or `ASSIGNMENT_ASYNC_TYPES`) | `ADMIN_FE_BASE_URL`, `REDIS_URL` |
| student-node | `CALCULATION_ASYNC=true` | `REDIS_URL` |
| student-node | `PROGRESSION_GATE_ENABLED=1` (gate) | `PROGRESSION_GATE_TYPES=Communication,Aptitude`, `PROGRESSION_GATE_MAX_WAIT_MIN` (30) |
| student-node | video-wait (always on) | `VIDEO_UPLOAD_WAIT_RETRIES` (3), `VIDEO_UPLOAD_WAIT_INTERVAL_SEC` (10) |

**DEV ✅ · UAT ✅** for the progression gate (flag on) and the video upload-wait
optimization. PROD pending.

Flags must live in the box `.env` / `.env.<env>` (the CI/auto_deploy bakes it), **not**
docker `-e` — a `-e`-only flag is silently dropped on the next rebuild. **Rollback** =
set the flag back to off + restart; the old synchronous/cron path is unchanged.

nginx (fast-api): role-based generation needs a `location /role_based/ { proxy_read_timeout
300; … }` block — without it the default 60s cuts dual-model generation with a 504.
