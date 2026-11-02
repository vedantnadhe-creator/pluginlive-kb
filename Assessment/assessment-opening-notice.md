# Future-start assessments: "opens at" copy + "now open" notice (corporate OTP)

**Status:** LIVE on DEV (admin-node `9aad2a8`) and UAT (admin-node `8b0d195`), 2026-11-02. **PROD pending.**
**Scope:** corporate **OTP / no-login** invites and **AI Interview** only (the
`isCorporateOtpInviteCampaign` rule: `is_otp_invite = true` OR type `AI_Interview`).
The college/portal ("simple") flow is unchanged — its email already prints
`Start Date` / `End Date` (user-management-node `assessmentRemainder`).

## Problem it solves

An assessment floated now with `start_time` tomorrow 6 PM sent its invite
immediately (nothing defers invites) with no start information, and nothing told
the candidate when it opened. Worse, the deadline rule could print
`Complete it by tomorrow 12 PM` — six hours before the assessment opened.
Clicking early was (and is) blocked by student-node: 410 `ASSESSMENT_NOT_STARTED`,
"This assessment opens on <date>. Please use this link again then."

## 1. "Opens at" in every invite/reminder sent before start

`admin-node/app/helpers/candidateDeadline.js` → `formatCandidateDeadline({ deadline, start, now })`.
When `start` is in the future (and before the deadline) it returns bucket
`not_open`:

| Opens | Closes | Text (`{{5}}` + email bold line) |
|---|---|---|
| tomorrow 6 PM | tomorrow 11:59 PM | `Opens tomorrow at 6 PM. Complete it by 03 Nov 2026 11:59 PM` |
| tomorrow 6 PM | in 8 days | `Opens tomorrow at 6 PM. Complete it by 04 Nov 2026 12 PM` |
| 05 Nov 9:30 AM | 10 Nov | `Opens on 05 Nov 2026 at 9:30 AM. Complete it by 06 Nov 2026 12 PM` |
| today 6 PM | today 10 PM | `Opens today at 6 PM. Complete it by 02 Nov 2026 10 PM` |

The completion target is the **existing 36-hour rule measured from the opening
moment** (so the stakeholder's "don't expose a distant end date → next-day noon"
nudge still holds), rendered as an absolute date. Once open, the old buckets
apply unchanged. Times are IST wall-clock digits (map columns), no `IST` suffix,
matching the existing deadline copy.

`sendAssessmentInviteEmail` resolves `{ start, deadline }` centrally
(`resolveAssignmentWindow`, one query) whenever the caller does not pass `start`,
so every invite/resend/reminder call site gets it. Before opening, the email CTA
reads **View Assessment / View AI Interview** instead of Start. WhatsApp needs no
template change: all `*_deadline_v1` bodies hold `{{5}}` as its own sentence.

## 2. "Your assessment is now open" notice

`admin-node/app/service/OpeningReminderService.js`, cron in `script/scheduler.js`
**every 5 min**, switch `assessment.cron_config.assessment_opening_reminder`,
lock `assessment.cron_locks.assessment_opening_reminder`. **No quiet hours** —
product decision 2026-11-02: an assessment opening at night is announced at night
and read in the morning.

Eligible (one notice ever, per candidate):
- corporate map, OTP flow (above), not cancelled, not on-call AI Interview;
- `aas.status = 'PENDING'`, not practice, `opening_notified_at IS NULL`;
- window open now, and `start_time` within the last **6 h**
  (`OPENING_REMINDER_MAX_LATE_HOURS`) — first-enable / outage guard;
- a non-failed `assessment_invite` email_event **created before `start_time`**
  (an invite sent after opening already is the "it's open" message). For a Mix &
  Match float any of the candidate's parts counts, since the float invite is
  recorded on one part;
- no hard bounce; one row per float (earliest PENDING part), stamp mirrored to
  the siblings.

Claim = `UPDATE … SET opening_notified_at = NOW()` over a `FOR UPDATE SKIP
LOCKED` CTE with a re-check, so overlapping sweeps cannot double-send. Send =
`sendAssessmentInviteEmail(intent: "opened", category: "assessment_open")`, which
sends email + WhatsApp (WhatsApp still gated by the corporate's
`WHATSAPP_NOTIFICATION` feature) and writes `email_events` rows, so the Delivery
column shows it. Email subject `Your assessment for <Company> is now open` /
`Your AI Interview for <Role> is now open`.

**Not retried** (`ponytail:` in the service): a send that fails after the claim
stays failed in `email_events`; the candidate still has the invite + auto
reminders. Upgrade path: durable rows via `ReminderDispatchService`.

Auto-reminders: the 24h baseline is now
`COALESCE(last_auto_reminder_at, GREATEST(invited_at, opening_notified_at), start)`
so reminder #1 lands 24h after the opening notice, not an hour after it.

## WhatsApp templates (MSG91 WABA 916380485173, submitted 2026-11-02)

Same param order as the matching reminder template, so the fallback is safe.

| Intent | Template | Category | Env var | Unset → |
|---|---|---|---|---|
| generic | `corporate_assessment_open_v1` | UTILITY, approved | `WA_ASSESSMENT_OPEN_TEMPLATE` | `WA_ASSESSMENT_REMINDER_TEMPLATE` |
| AI Interview | `corporate_ai_interview_open_v1` | UTILITY, approved | `WA_AI_INTERVIEW_OPEN_TEMPLATE` | `WA_AI_INTERVIEW_REMINDER_TEMPLATE` |
| Mix & Match | `corporate_multi_assessment_open_v1` | **MARKETING** (Meta re-categorised it) | `WA_MIX_MATCH_OPEN_TEMPLATE` — **left unset** | `WA_MIX_MATCH_REMINDER_TEMPLATE` |

The Mix & Match one is deliberately not switched on: MARKETING templates are
silently dropped/throttled (see `Infrastructure/whatsapp-messaging.md`). Resubmit
as a UTILITY `_v2` before enabling. Env lives in the box env file
(`admin-node/.env` DEV, `.env.uat` UAT) — set on DEV and UAT.

## DB

DB-Scripts `Assessment Auto Reminders/20261102T085752Z__opening_reminder.sql`:
column `assessment_assigned_students.opening_notified_at timestamptz`, index
`idx_acm_start_time`, lock + cron_config rows (seeded **disabled**). DEV + UAT
applied and **enabled** 2026-11-02; PROD pending.

**PROD order:** SQL first (both `OpeningReminderService` and the edited
auto-reminder claim reference the column — admin-node before the SQL breaks the
auto-reminder sweep), then admin-node, then the two env vars, then flip
`cron_config.assessment_opening_reminder` on.

## Checks

- Unit: `test/candidateDeadline.spec.js`, `test/openingReminder.spec.js`.
- Real DB, always rolled back: `node scripts/check-opening-reminder.js` (inside the
  container: `docker exec -w /app admin node scripts/check-opening-reminder.js`) —
  claim, stamp, no double send, invite-after-open skipped, one notice per float.
  Passed on DEV and UAT 2026-11-02.

## Not covered

- College/scheduled assessments: no "now open" notice, no WhatsApp (college has
  none). Separately, `createAssessmentSchedule` assigns the diagnosis at schedule
  creation with start = today, not `schedule_start_date` (unchanged; see
  `schedule.md`).
- Corporate **portal-login** (non-OTP) invites keep `assessmentStudentCorporate2`
  with date-only Start/End.
