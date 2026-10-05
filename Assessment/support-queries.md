# Support queries — the Support button → email + #platform-activity

> A candidate who hits **Support** mid-assessment types a message; the team gets
> an email (reply goes straight to the candidate) and a PLBOT post in Slack
> **#platform-activity** (`C09TA5PNZC5`).
>
> **Status:** LIVE on **DEV** and **UAT** (2026-09-30; delivery-recovery + atomic throttle fix DEV `54d713f` / UAT `f3299e7`; owner name DEV `34e19d6` / UAT `ddd6322`, 2026-10-05). **PROD pending.**
> Frontends: only **assessment-react-v2** has the button today. The backend already
> accepts every portal's login, so institute-react-v2 / corporate-react-v2 / etc.
> only need a button + a `/api/support` route (deferred).

## Flow

```
assessment-react-v2  ⋯ menu → Support → SupportDialog (name, read-only email, message)
  → POST /api/support                      (Next.js BFF route, forwards the exam token)
  → admin-node POST /support/query         (validates, stores, enqueues, answers 202)
  → BullMQ queue "support-query"           (worker in admin-node's startWorkers process)
       1. email  → mail relay (EMAIL_ENDPOINT), from EMAIL_SENDER (mandate@pluginlive.com)
                   to every active row in assessment.quota_alert_recipients,
                   Reply-To = the sender
       2. Slack  → #platform-activity via SLACK_ACTIVITY_WEBHOOK_URL
       3. row status = sent — only once BOTH channels are stamped
```

The candidate never waits on the mail relay or Slack: the row is written and the job
queued, then the dialog shows "Your message has been sent to the team."

## What the team sees

Both the email and the Slack post name the **college or company that owns the
assessment** — `institute.institutes.name` (via `assessment_institute_map.institute_id`)
or `corporate.corporates.name` (via `assessment_corporate_map.corporate_id`), resolved
from the in-exam token's assignment. If no name is on file it falls back to
"Institute" / "Corporate".

| | Shows |
|---|---|
| Email subject | `Support query from <name> · <owner> (<source>)` |
| Email body | From, Role, Raised from, Page, Assessment, **Assessment owner** (the name), Attempt status, Assignment ID, Query ID, then the message |
| Slack | `[ENV] 🆘 Support query · <name> (<email>)`, then `*<owner>* · <assessment> · <source>`, the quoted message, and query/assignment ids |

## Who is asking (auth)

`/support/query` is **not** `isPrivate` — the handler verifies the token itself,
because two kinds reach it:

| Token | Signed with | Identity used |
|---|---|---|
| Portal login JWT (`{ user }`) — candidate, college, company, admin | shared login secret (`JWT_SECRET_KEY` = user-management `LOGIN_SECRET_KEY`) | email + name looked up from `user_management.users` / `admin.admin_users` by `_id` |
| In-exam `assessment:run` token (`scope`, `sub`, `email`) | user-management's chain: `ASSESSMENT_SCOPED_SECRET` → `AI_INTERVIEW_SCOPED_SECRET` → invite secrets → **login secret** | the token's email; `sub` pins the assignment |

**Gotcha:** UAT sets none of the dedicated scoped secrets, so its in-exam tokens are
signed with the login secret. admin-node follows the same fallback chain (fix
`d4e3727` / UAT `8cce780`); if an env ever sets `ASSESSMENT_SCOPED_SECRET` in
user-management, admin-node must get the same value or every in-exam Support
submit answers 401.

The typed email is only a fallback for a token that carries none, and the body can
never override the assignment pinned by an in-exam token.

## Data

`assessment.support_queries` (raw SQL, not in Prisma — like `quota_alert_recipients`).
DB-Scripts: `Support Queries/20260930T082149Z__support_queries.sql`.

| Column | Notes |
|---|---|
| `user_id`, `user_role` | from the login token; role `candidate` for in-exam tokens |
| `assessment_assigned_id` | from the in-exam token |
| `source` | frontend, e.g. `assessment-v2` |
| `page_url` | path only (query strings can hold invite tokens) |
| `name`, `email`, `message` | message ≤ 4000 chars |
| `status` | `queued` → `sent` (email **and** Slack stamped) / `failed` (retries exhausted). Slack unconfigured → stays `queued` with `last_error`, retried later |
| `email_sent_at`, `slack_sent_at` | stamped per channel — a retry skips stamped channels. Delivery is **at-least-once**: a worker crash between a send and its stamp re-sends that one channel (neither the mail relay nor Slack takes an idempotency key) |
| `last_error` | set when all retries are exhausted, or when Slack was skipped (not configured) |

**Recipients** = `assessment.quota_alert_recipients WHERE is_active` (shared with
the scheduler's quota alerts). Edit that table to change who gets support email —
no deploy.

## Reliability and abuse

- Queue: 5 attempts, exponential backoff from 10 s. Job id `support__<id>`.
- Reconciler (central recovery sweep), rows created in the last **3 days**:
  - `queued` with no `last_error`, untouched 5 min → lost enqueue, re-enqueued;
  - `failed`, or `queued` with `last_error` (Slack skipped) → retried every 30 min.
  Same job id `support__<id>`: a live job is left alone; a finished (completed/failed)
  BullMQ job is removed first, since `add()` ignores a jobId BullMQ still retains.
  Rows older than 3 days stay `failed`/`queued` for manual follow-up.
- Throttle: 5 messages per sender email per 10 min → 429 with a readable message,
  which the dialog shows verbatim. Count + insert run in one transaction under a
  per-email `pg_advisory_xact_lock`, so a parallel burst cannot exceed 5
  (verified on DEV: 10 parallel submits → 5 stored, 5 refused).
- Slack's `chat.postMessage` answers HTTP 200 with `ok:false` on failure; that is
  turned into a thrown error so the job retries.

## Configuration (admin-node)

| Var | Purpose |
|---|---|
| `SLACK_ACTIVITY_WEBHOOK_URL` | #platform-activity incoming webhook (`…/B0AHHAQHEKZ/…`). Webhooks are **channel-locked** — a `channel` field in the body is ignored. |
| `SLACK_ACTIVITY_ENV` | `DEV`/`UAT` prefix posts with `[DEV]`/`[UAT]`; `PROD` = no tag |
| `SLACK_BOT_TOKEN` + `SLACK_ACTIVITY_CHANNEL` | optional alternative (bot `xoxb-` token + channel id, like InfraHub); preferred over the webhook when both are set |
| `EMAIL_ENDPOINT`, `EMAIL_SENDER`, `AUTH_KEY` | existing mail relay settings |

Unset Slack = email only (logged, not an error).

Frontend: assessment-react-v2 needs `ADMIN_API_URL` pointing at **its own env's**
admin-node — the UAT/PROD build must not carry the DEV URL.

## Code

- admin-node: `app/routes/support.js`, `app/handlers/supportHandler.js`,
  `app/service/SupportQueryService.js`, `app/models/SupportQuery.js`,
  `app/helpers/slackActivity.js`, `app/queues/supportQueryWorker.js`,
  `test/supportQuery.spec.js`. Commits `69df231`, `f6aee07`, `d4e3727`, `54d713f`, `34e19d6`
  (UAT `9d36abb`, `2ceb885`, `8cce780`, `f3299e7`, `ddd6322`).
- assessment-react-v2: `src/app/api/support/route.ts`, `src/lib/supportRequest.ts`,
  `src/app/_components/exam/SupportDialog.tsx`. PR #10 (`7cdb3f7`), UAT `95c7290`.

## PROD checklist

1. Run the DB script on PROD.
2. admin-node PROD config: `SLACK_ACTIVITY_WEBHOOK_URL`, `SLACK_ACTIVITY_ENV=PROD`;
   check which scoped secret PROD user-management signs with (see the gotcha above).
3. Deploy admin-node **before** assessment-react-v2.
