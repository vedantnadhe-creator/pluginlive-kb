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

## Activity UI (admin-react)

- **Manage Assessments → Assignment Activity** tab: a server-paginated list of all
  assignment jobs (scoped to the institute/corporate tab). Each row has a **Detail**
  button (and is row-clickable) → the per-job activity page.
- **Per-job activity page** `/assessment/activity/job/:jobId` — real-time (polls until
  terminal): a progress header (Total / Assigned / Notified / Failed + %), a
  server-paginated per-student table (Failed / Pending / Done / All filter), and
  per-student retry (incl. edit-and-retry for data errors).
- **Assignment | Calculation toggle** on the detail page. The **Calculation** view
  shows scoring counts (Submitted / Scored / Pending / Failed) + a per-student scoring
  table with **Retry scoring** (admin-node resets the calc flags; student-node's
  sweeper re-enqueues — no cross-service call). ATTEMPTS shows only in the Failed view
  (it's a failure-retry counter, reset to 0 on success).

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

Flags must live in the box `.env` / `.env.<env>` (the CI/auto_deploy bakes it), **not**
docker `-e` — a `-e`-only flag is silently dropped on the next rebuild. **Rollback** =
set the flag back to off + restart; the old synchronous/cron path is unchanged.

nginx (fast-api): role-based generation needs a `location /role_based/ { proxy_read_timeout
300; … }` block — without it the default 60s cuts dual-model generation with a 504.
