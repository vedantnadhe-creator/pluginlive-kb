# Automated candidate assessment reminders (24h cadence, capped)

> A candidate who is invited to an assessment and never starts it is now chased
> automatically — every 24h while the assignment is still `PENDING` and the
> window is open, capped at 3 sends. Previously this only happened if an admin
> pressed **Send Reminders** by hand.
>
> **Status:** DEV + UAT (2026-08-06). PROD pending.
> **Ships disabled** in every environment — see "Enabling it" below.

## Cadence

| Reminder | Fires |
|---|---|
| #1 | 24h after the candidate's invite (falls back to the assessment `start_time` if no invite email is on record) |
| #2 | 24h after #1 |
| #3 | 24h after #2 — then never again for that assignment |

Why the invite timestamp is preferred over `start_time`: a candidate added three
days into a running assessment would otherwise be "already 3 days overdue" and
get mailed within the hour of being added. The baseline is the earliest
non-failed `assessment_invite` row in `email_events` for that assignment.

**Final call.** Inside 12h of `end_time` the 24h gap relaxes to 6h, so a
remaining reminder is spent while it can still change the outcome. Without this,
a candidate reminded 20h before a window that closes in 6h would never hear from
us again.

## Who is eligible

All of these must hold:

- `status = 'PENDING'` (not started). `INPROGRESS` and `DROPOUT` are **not**
  chased — a deliberate scope choice, worth revisiting.
- `is_practice = false`
- `auto_reminder_count < 3`
- The assessment window is open (`start_time <= now < end_time`)
- The assessment started within the last **30 days**
- No `email_events` row for the assignment with `status = 'bounced'`

The 30-day guard is what stops a first enable on an environment with a long
stale `PENDING` backlog from mailing the entire backlog in one tick.

The bounce guard matters at PROD scale: there are a few hundred hard-bounced
addresses, and without it each one would take 3 more sends straight into the
suppression list and drag sender reputation down with it.

## Architecture

```
scheduler.js  (hourly, '0 * * * *')
  └─ cron_config gate → cron_locks mutex
       └─ AutoReminderService.sweepDueReminders()
            ├─ claimDueBatch()   — atomic claim, 200 rows per round-trip
            └─ enqueue           — one job per candidate
                 └─ queue: assessment-reminder
                      └─ reminderWorker  (concurrency 10, limiter 20/sec)
                           └─ ReminderSendService.sendReminder()
```

| File (admin-node) | Role |
|---|---|
| `script/scheduler.js` | Registers job `assessment_auto_reminder` |
| `app/service/AutoReminderService.js` | Due-query, atomic claim, batched enqueue |
| `app/service/ReminderSendService.js` | Render + send (no queue import — unit testable) |
| `app/queues/reminderWorker.js` | BullMQ transport, rate limit |
| `app/queues/setup.js` | `assessment-reminder` queue |
| `app/models/Assessment.js` | Resets the cursor on re-invite |

Hourly rather than daily so each candidate's 24h clock runs from *their* last
reminder — a candidate invited at 15:00 is due at 15:00 the next day, not
whenever a nightly batch happens to run. Most ticks claim nothing and cost one
indexed query per entity type (~2ms).

**Quiet hours:** sends only between **09:00 and 20:00 IST**. Outside the window
the tick claims nothing. The effective interval is therefore *"at least 24h"*,
never less.

## Why a reminder cannot double-send

Three layers, because a duplicate here is a duplicate email to a real candidate:

1. **`cron_locks`** — only one pod runs the sweep. `index.js` forks the cron
   worker inside *every* admin-node replica, so this is load-bearing on PROD.
2. **`FOR UPDATE ... SKIP LOCKED`** in the claim CTE — if two sweeps ever do
   overlap they take disjoint row sets rather than blocking or colliding.
3. **Re-check in the `UPDATE`'s own `WHERE`** — READ COMMITTED does *not*
   re-evaluate the CTE's predicates once the row lock is taken, so `status` and
   `auto_reminder_count` are asserted again on the row actually being written.

**Claim-then-enqueue.** The cursor advances in the *same statement* that selects
the row, before any job exists. That makes a reminder **at-most-once**: a crash
between claim and enqueue costs one nudge. The inverse (send, then record) would
re-mail everyone after any crash. For candidate-facing email, a missed nudge is
much cheaper than looking like spam.

If the enqueue itself fails, the claim is already spent — the affected
`assessment_assigned_id`s are logged explicitly, because resetting
`auto_reminder_count` for those ids is the only way to recover them.

## Load bounding

| Control | Default | Env var |
|---|---|---|
| Rows per DB round-trip | 200 | `AUTO_REMINDER_BATCH_SIZE` |
| Rows per hourly tick | 2000 | `AUTO_REMINDER_MAX_PER_TICK` |
| Emails/sec (global, Redis-backed) | 20 | `REMINDER_RATE_MAX` |
| Worker concurrency | 10 | `REMINDER_CONCURRENCY` |

One job per **candidate**, not per assessment — that is what makes the BullMQ
limiter a true emails/sec ceiling across all pods. Per-assessment jobs would
make the limiter count batches, and one institute with 8,000 candidates would
still go out as a single burst.

20/sec is deliberately under the assignment pipeline's `NOTIFY_RATE_MAX` (50/sec)
so a reminder backlog never starves a live invite-on-assignment, which a
candidate is actively waiting for.

Other tunables: `AUTO_REMINDER_MAX_COUNT` (3), `AUTO_REMINDER_GAP_HOURS` (24),
`AUTO_REMINDER_FINAL_CALL_HOURS` (12), `AUTO_REMINDER_FINAL_CALL_GAP_HOURS` (6),
`AUTO_REMINDER_MAX_ASSESSMENT_AGE_DAYS` (30), `AUTO_REMINDER_QUIET_START_HOUR`
(9), `AUTO_REMINDER_QUIET_END_HOUR` (20).

## Which email goes out

Same two paths as the manual **Send Reminders** action, so templates stay in sync:

- **Corporate OTP campaigns** → the scoped OTP invite link
  (`sendAssessmentInviteEmail`). These candidates have no portal account.
- **Everything else** → the portal reminder via user-management-node
  (`/user/student/sendAssessmentReminder`).

The OTP branch is chosen with the shared `isCorporateOtpInviteCampaign`
predicate, **not** the raw `is_otp_invite` column. AI Interview corporate maps
are OTP campaigns that leave that flag `false` (assign keys off entity type
instead), so reading the column alone mails portal login credentials to
candidates who have no account. See `otp-invite.md`.

> The manual path (`Assessment.sendRemindersToStudents`) still reads the raw
> flag and appears to carry this same latent bug. Not yet fixed.

Every outcome is written to `email_events` with category `assessment_reminder`,
in the same shape the manual reminder writes — so the DELIVERY column and the
candidate funnel treat automated and manual sends identically. See
`email-delivery-tracking.md`.

## Schema

`assessment.assessment_assigned_students` gains two columns:

| Column | Meaning |
|---|---|
| `auto_reminder_count` | `INTEGER NOT NULL DEFAULT 0`. Reset to 0 on re-invite. |
| `last_auto_reminder_at` | `TIMESTAMPTZ NULL`. **True UTC instant.** |

Plus `idx_aas_institute_map_status` and `idx_aas_corporate_map_status`.

The cursor lives on the assignment row rather than in a new log table because
`email_events` is already the send audit trail; these two only answer "is this
candidate due, and have they had enough?", which the claim `UPDATE` must read
and write atomically in one statement.

**Manual admin reminders deliberately do not increment the counter** — an admin
nudging someone by hand must not burn an automated slot, and vice versa.

Migration: DB-Scripts `Assessment Auto Reminders/20260806T081516Z__auto_assessment_reminders.sql`.

### ⚠ Timezone — read before touching the query

`assessment_institute_map.start_time` / `end_time` store **IST wall-clock digits
as UTC**, not the true instant (see `admin.md` → Timezone). So:

- comparing "now" against those columns → `NOW() + INTERVAL '5:30'`
- converting one of them to a true instant → `column - INTERVAL '5:30'`

`last_auto_reminder_at` is an honest `timestamptz` and needs neither. Mixing the
two frames silently shifts every reminder by 5h30m.

### Re-invite resets the cursor

`resendInvites` sets `auto_reminder_count = 0`, `last_auto_reminder_at = NULL`
alongside the existing `dropped_at` clear. Without this, anyone who had
exhausted their reminders on the first invite would never be chased on the
second — the exact candidates a re-invite exists to recover.

## Enabling it

Ships with `cron_config.is_enabled = false`. The job registers with `node-cron`
either way and no-ops each tick while off, so deploying the code changes nothing.

Turn it on from **Question Manager → Manage Cron** (job `assessment_auto_reminder`),
per environment. Takes effect on the next tick, no redeploy. See `manage-cron.md`.

**Prerequisite: `AUTH_KEY` must be set in that environment.** The cron has no
inbound request to borrow a bearer token from, so it authenticates as a service —
`RestClient` falls back to the `auth-key` header when no `Authorization` header
is supplied. `AUTH_TOKEN` is a *user* token and is empty in most environments;
relying on it would 401 everywhere.

`sweepDueReminders()` refuses to claim anything when `AUTH_KEY` is missing. That
guard matters more than a normal config check: claiming *spends* each
candidate's reminder budget, so claiming into a 401 would silently consume
everyone's nudges without any of them being sent.

Recommended first enable on PROD: lower `AUTO_REMINDER_MAX_PER_TICK` for the
first day and watch `email_events`.

## Operational queries

```sql
-- How many candidates would the next tick chase?
SELECT count(*) FROM assessment.assessment_assigned_students
WHERE status = 'PENDING' AND is_practice = false AND auto_reminder_count < 3;

-- Reminders sent in the last 24h
SELECT status, count(*) FROM assessment.email_events
WHERE category = 'assessment_reminder' AND created_at > now() - interval '24 hours'
GROUP BY status;

-- Reset a candidate's reminder budget (e.g. after a failed enqueue)
UPDATE assessment.assessment_assigned_students
SET auto_reminder_count = 0, last_auto_reminder_at = NULL
WHERE assessment_assigned_id = '<uuid>';
```

> **Gotcha for anyone smoke-testing `claimDueBatch`:** it resolves the global
> Prisma client, so wrapping a call in `prisma.$transaction(...)` and throwing
> does **not** roll the claim back — the query runs outside the transaction and
> the rows really are claimed. Reset them with the query above afterwards.

## Per-environment status

- **DEV** — deployed 2026-08-06, cron disabled.
- **UAT** — deployed 2026-08-06, cron disabled. DB migrated, worker running
  (`[Reminder] worker started (concurrency=10, rate=20/1000ms)`).
- **PROD** — pending (code + migration).
