# Automated candidate assessment reminders (24h cadence, capped)

> A candidate who is invited to an assessment and never starts it is now chased
> automatically — every 24h while the assignment is still `PENDING` and the
> window is open, capped at 3 sends. Previously this only happened if an admin
> pressed **Send Reminders** by hand.
>
> **Status:** DEV + UAT (2026-08-06; cap hardened 2026-08-19). PROD pending.
> **Ships disabled** in every environment — see "Enabling it" below.

## Cadence

| Reminder | Fires |
|---|---|
| #1 | 24h after the candidate's invite (falls back to the assessment `start_time` if no invite email is on record) |
| #2 | 24h after #1 |
| #3 | 24h after #2 — then never again for that assignment |

**The cap of 3 is a hard ceiling, not a default.** `AUTO_REMINDER_MAX_COUNT` is
clamped to `[0, 3]`, so an environment may ask for *fewer* nudges but can never
raise the ceiling — a stray ConfigMap value of `10` resolves to 3, not 10. It is
enforced in three places: the claim query's `auto_reminder_count < maxCount`, a
re-assertion inside the claiming `UPDATE`'s own `WHERE` (the CTE's predicates are
not re-evaluated once the row lock is taken), and the clamp itself.

A reminder occurrence costs **one** nudge regardless of how many channels it uses:
email + WhatsApp for the same occurrence share a `reminder_number` and increment
`auto_reminder_count` once. Queue retries reuse that same occurrence and never
spend extra budget.

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
            └─ transaction: claim + durable email_events channel rows
                 └─ ReminderDispatchService
                      ├─ assessment-reminder (email, 20/sec)
                      └─ assessment-reminder-whatsapp (WhatsApp, 5/sec)
```

| File (admin-node) | Role |
|---|---|
| `script/scheduler.js` | Registers job `assessment_auto_reminder` |
| `app/service/AutoReminderService.js` | Due-query and atomic claim + channel staging transaction |
| `app/service/ReminderDispatchService.js` | Durable `email_events` dispatch and stale-row recovery |
| `app/service/ReminderSendService.js` | Independent email and WhatsApp send functions |
| `app/queues/reminderWorker.js` | Email BullMQ worker and rate limit |
| `app/queues/reminderWhatsappWorker.js` | WhatsApp BullMQ worker, retries and rate limit |
| `app/queues/setup.js` | Email and WhatsApp reminder queues |
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

**Durable channel dispatch (2026-08-13).** The cursor and one `email_events`
dispatch row per eligible channel are committed in the same transaction. Redis
enqueue happens afterwards. If Redis or a worker is unavailable, the pending or
stale row is re-enqueued by the worker process; the unique key
`(assignment, category, reminder_number, channel)` prevents duplicate logical
jobs. Email and WhatsApp retry independently, so retrying one never resends the
other. The old fire-and-forget WhatsApp call is explicitly suppressed for this
automated path.

## Load bounding

| Control | Default | Env var |
|---|---|---|
| Rows per DB round-trip | 200 | `AUTO_REMINDER_BATCH_SIZE` |
| Rows per hourly tick | 2000 | `AUTO_REMINDER_MAX_PER_TICK` |
| Emails/sec (global, Redis-backed) | 20 | `REMINDER_RATE_MAX` |
| Worker concurrency | 10 | `REMINDER_CONCURRENCY` |
| WhatsApp/sec (global, Redis-backed) | 5 | `REMINDER_WHATSAPP_RATE_MAX` |
| WhatsApp concurrency | 5 | `REMINDER_WHATSAPP_CONCURRENCY` |

One job per **candidate**, not per assessment — that is what makes the BullMQ
limiter a true emails/sec ceiling across all pods. Per-assessment jobs would
make the limiter count batches, and one institute with 8,000 candidates would
still go out as a single burst.

20/sec is deliberately under the assignment pipeline's `NOTIFY_RATE_MAX` (50/sec)
so a reminder backlog never starves a live invite-on-assignment, which a
candidate is actively waiting for.

Other tunables: `AUTO_REMINDER_MAX_COUNT` (3, clamped to a maximum of 3), `AUTO_REMINDER_GAP_HOURS` (24),
`AUTO_REMINDER_FINAL_CALL_HOURS` (12), `AUTO_REMINDER_FINAL_CALL_GAP_HOURS` (6),
`AUTO_REMINDER_MAX_ASSESSMENT_AGE_DAYS` (30), `AUTO_REMINDER_QUIET_START_HOUR`
(9), `AUTO_REMINDER_QUIET_END_HOUR` (20).

## Budget refund on a dead occurrence

The cron **claims** a reminder — spending one of the three nudges — before either
channel has sent anything. So an occurrence whose every channel failed
permanently used to cost a nudge nobody received: a candidate with one broken
send effectively got two reminders instead of three.

`ReminderDispatchService.finalizeFailure()` (called by both workers when a job
exhausts its attempts) now gives that nudge back. It is deliberately narrow:

- every sibling channel row of the same `(assessment_assigned_id, reminder_number)`
  must be terminally `failed` — a `completed` one means the candidate *was*
  reached, so the nudge was spent legitimately, and a live one still owns the
  occurrence;
- the refund `UPDATE` is guarded on `auto_reminder_count = reminder_number`, which
  is what makes it idempotent: a second failing channel, or a replayed job, finds
  the count already decremented and no-ops instead of rewinding twice;
- the assignment must still be `PENDING`.

`last_auto_reminder_at` is intentionally **not** rewound. The refunded nudge comes
back on the normal 24h cadence rather than immediately, so a flapping relay cannot
turn into a retry storm against the same candidate.

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

For an eligible corporate OTP/no-login reminder, the cron stages two durable
rows: email and WhatsApp. Institute, portal-login, unsubscribed, and no-phone
candidates stage email only. Queue lifecycle (`pending`, `queued`, `processing`,
`retrying`, `completed`) and retry metadata live on the durable row; each actual
provider attempt remains an ordinary accepted/failed audit row.

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
-- Occurrences that failed on every channel (candidates whose budget was refunded)
SELECT assessment_assigned_id, reminder_number, count(*) AS channels
FROM assessment.email_events
WHERE category = 'assessment_reminder'
GROUP BY assessment_assigned_id, reminder_number
HAVING bool_and(status = 'failed');

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

- **DEV** — channel-queue code on `Development` at `a487a27e`; `email_events`
  migration applied and verified 2026-08-13. Cap clamp + budget refund pushed to
  `Development` as `956e21a0` on 2026-08-19 (no migration; code-only).
- **UAT** — channel-queue code promoted as `7b856cf6`, migration applied, and
  admin-node deployed 2026-08-13. Cap clamp + budget refund promoted as
  `d17ccd34` and deployed 2026-08-19; `/health` 200 and both workers verified
  running: `[Reminder] ... rate=20/1000ms` and
  `[Reminder:WhatsApp] ... rate=5/1000ms`. No `AUTO_REMINDER_*` override is set
  on the container, so the effective cap is 3.
  Cron `assessment_auto_reminder` was enabled `2026-08-13 15:42:07 UTC` and
  **disabled again `2026-08-14 07:29:51 UTC` — it is currently OFF on UAT.**
- **PROD** — pending. `release-v1.37` carries only the original single-queue
  reminder commit (`f01e392`); the channel-queue code, the `email_events`
  migration, this cap hardening, and the `assessment_auto_reminder` row in
  `CRON_JOBS` / Question Manager's `JOB_ORDER` are all still missing. The live
  PG16 cluster (`10.0.6.104`) does have the `cron_config` row, disabled.
