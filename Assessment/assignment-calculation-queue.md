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

### Set-generation gate (prepare-set)
- Before items fan out, `orchestrate` may dispatch **`prepare-set`** jobs (BullMQ
  `assessment-prepare-set`, conc 8) — one per required set spec. Types whose set is
  generated on the fly (e.g. Communication picks/creates a set via
  `Assessment.js` `assessmentSet.findMany`) gate here; the barrier resumes
  `orchestrate` only once every set is ready.
- **prepare-set is upstream of the per-student loop.** A permanent generator failure
  used to mark only the **job** `failed` and leave every item `pending` with no
  `last_error` — so the Activity UI showed **FAILED = 0** and a blank **REASON**
  (students looked like they were merely waiting). Fixed 2026-07-08 (admin-node
  `assignmentWorker.js`): on exhausted `prepare-set` retries we now propagate the
  generator error onto **every non-terminal item** (`getNonTerminalItems` →
  `setItemStatus(id,'failed',{lastError})`) before failing the job, so the UI
  surfaces them as **Failed with the real reason** (counts + REASON are derived from
  item status/`last_error`).
- **Schema-drift gotcha (accent):** the set-picker selects `assessment_sets.accent`
  (added for the Communication Listening-audio accent feature, `VARCHAR(10) NOT NULL
  DEFAULT 'en-IN'`). If that column is missing on an env (migration not applied there
  while the accent-aware admin-node is deployed), `prepare-set` throws
  `column assessment_sets.accent does not exist`, retries 5×, and the assign hangs
  with the invisible-failure symptom above. Fix = run the
  `Communication Listening Accent/…__assessment_sets_accent_column.sql` migration on
  that env. Applied DEV + UAT (2026-07-08); **PROD pending**.

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

### Abandoned attempts are scored too (2026-09-02, DEV + UAT; PROD pending)

Scoring used to be gated on `submitted = true` in **both** paths that feed the
worker — enqueue-on-submit (`submitAssessment`) and the sweeper's `where`. A
drop-off never submits, so a candidate who answered 23 of 30 Communication
questions and then closed the tab left those answers in `student_answers` with
**no score and no error**: `calculation_attempts` stayed `0` because nothing ever
looked at the row. AI Interview already had a way out (`finalizeAbandonedSession`
+ `runScoringForAssignment` in the dropout cron, so an abandoned interview still
produces a recruiter report); **every other type had nothing**.

`script/updateDropoutStatusCron.js` now also hands abandoned attempts to the
calculation queue. Nothing about the scorer changed, and nothing had to: neither
the calc worker's claim nor `calculateAssessmentScore` reads `submitted` — only
the two SELECTs that feed them did.

Four limits, all in `app/helpers/dropoutScoring.js` (`isScorableDropout`, unit
tests in `test/dropoutScoring.spec.js`):

| limit | why |
|---|---|
| `status = DROPOUT`, re-read from the DB | the flip's `updateMany` re-checks `status`/`submitted` in its WHERE, so a row that completed concurrently is not ours and must not be scored as an abandonment |
| at least one `student_answers` row | a row with nothing stored would get a 0 report for a paper the candidate never sat, indistinguishable from a genuine 0 |
| not `AI_Interview` | that type finalizes and scores itself; enqueuing it here too would race its own path |
| `dropped_at` within a **24h lookback** | stops the deploy that ships this from retroactively scoring the estate's whole drop-off history (the same call `retryAiInterviewDropoutScoring` makes), and bounds the sweep |

Runs at the **top** of each 2-min cron tick, before the DROPOUT flips, and selects
by committed state rather than by "flipped this tick". That is deliberate: it makes
the sweep **self-recovering** (an enqueue lost to a Redis blip, or a row the worker
released after a transient FastAPI 504, is retried on the next tick until it leaves
the window) and costs a row flipped this tick only one tick's wait. The ordinary
score sweeper cannot do this job — it selects `submitted: true`, which a drop-off
never is. Bounded at 200 rows/tick; no-ops when `CALCULATION_ASYNC` is off.

The row's `status` stays `DROPOUT` and `submitted` stays `false` — a partial attempt
is scored honestly, against the **full** paper, so unanswered questions count as
unattempted. A 14/30 aptitude drop-off scored 3/60 on PROD, not a pro-rated mark.

**Reading a dropout that still has no score:** `scores_calculated=false` with
`calculation_attempts=0` and `calculation_error=false` means it was never eligible
— almost always zero stored answers, or a `dropped_at` older than the lookback.

**The read side had the same gate, mirrored (admin-node, 2026-09-02, DEV + UAT;
PROD pending).** Writing the score was only half of it: three admin read paths
enriched a row with its scores only `if (is_submitted)`, so a scored drop-off came
back **identity-only** — `scoresCalculated: true` but `score: null`. The Mix & Match
float rendered a dash, the report drawer showed an unscored attempt, and Excel
exported blank cells, all while the scores sat in `communication_scores` /
`aptitude_scores`. Fixed by reading `scores_calculated` alongside `submitted` in
`app/models/Assessment.js` — the college list (~L1045), the corporate list (~L1808),
and `getStudentAssessmentScores` (~L19775, which serves **both** the float report and
the per-student drawer). The comment already above the college gate had said it:
*gating on flags cannot be made correct — the score row existing is the only signal
that matches what the report shows.* Submitted rows are unaffected; a row that is
neither submitted nor scored still returns early and still costs no lookup.

**So a drop-off needs BOTH halves deployed to show a score:** student-node to write
it, admin-node to render it. Either one alone looks like the feature does not work.

**And a third half on the drawer itself (admin-react, 2026-09-03, DEV + UAT; PROD
pending).** The report drawer worked out *which* report to draw purely from the data
on the row — `aptitudeScores`, or aptitude keys on `sectionScores`. A part carrying
neither (an unscored drop-off, a candidate who never started) fell through every
branch to the language one, so an **Aptitude** attempt was drawn as Total Score /
Reading / Listening / Speaking and carried the face-detection *Proctoring Status*
badge that aptitude does not use. In a Mix & Match float it is unmistakable: the
Aptitude tab rendered a communication report. The type is now the last word, the way
it already was for behaviour, role-based and custom — `isAptitudeReport(student,
type)` in `src/modules/Assessment/Partials/aptitudeSections.js`, covered by
`aptitudeSections.test.js` (`node src/modules/Assessment/Partials/aptitudeSections.test.js`).
Scored rows are unaffected: the scores still answer the question first.

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
- **Repairing rows spoiled *before* the gate:** the gate only prevents *new* wrong-level
  sets. Rows already spoiled (wrong-level set served → progression derived above the
  assigned level, e.g. assigned A1 but progression B1) are recovered with the
  **simulate backfill** — `POST /assessment/backfill-progression` with `{ simulate: true }`
  (preview first with `dryRun: true`). It re-derives each post-diagnosis assessment at
  the intended level (predecessor's `suggestedCefr`) instead of the served set level.
  See `communication.md` §8 Backfill API. (Communication only; aptitude has no simulate path yet.)

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
