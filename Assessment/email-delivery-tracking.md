# Assessment Email Delivery & Candidate Journey Tracking

## What it is

Records what happened to every assessment invite/reminder email, and what the
candidate did between receiving it and starting the assessment. Surfaced to
admins as a **DELIVERY** column on the assessment detail candidate table and as a
**Delivery Status** column in the exported workbook.

Live on **DEV + UAT** (2026-07-31). PROD pending.

## Why it exists

Before this, email delivery was completely untracked:

- The send helpers caught relay failures, logged to stdout and returned `false`.
  A candidate who never received their invite was indistinguishable from one who
  ignored it.
- `user-management-node`'s `sendEmail` resolved to `null` on relay failure but the
  `assessmentRemainder` handler still returned **200**, so a reminder that was
  never sent was recorded as a success.
- Nothing recorded whether a candidate clicked the invite or reached the
  instruction screen, so the admin funnel jumped from "Assessment Sent" straight
  to "In Progress" with no visibility into where candidates dropped off.

## Data model (`assessment` schema)

Migration: `DB-Scripts/Assessment Email Delivery Tracking/20260731T055936Z__email_and_journey_tracking.sql`
(**DEV applied 2026-07-31, UAT applied 2026-07-31, PROD pending**).

### `assessment.email_events`
One row per send **attempt** against the mail relay.

- `message_id` — RFC 5322 Message-ID minted by the relay. UNIQUE, nullable. This
  is the join key for a future provider delivery feed, so a `delivered`/`bounced`
  event can update the row instead of inserting a duplicate. NULL on a failed
  send (no message was ever minted) — and NULLs do not collide in a UNIQUE index,
  so repeated failures for one recipient each keep their own row.
- `assessment_assigned_id` — nullable; operational mail (assign-job summaries to
  admins) has no candidate assignment behind it.
- `category` — `assessment_invite | assessment_reminder | otp | job_summary`
- `status` — `accepted | failed | delivered | bounced`

**`accepted` means the relay handed the message to OCI and OCI took it — NOT that
it reached a mailbox.** `delivered`/`bounced` are the only statuses that describe
the recipient's mailbox, and nothing writes them yet (see Known gaps).

### `assessment.candidate_journey_events`
Append-only; one row per milestone occurrence.

- `event_type` — `invite_link_clicked | assessment_opened`
- `metadata` — non-PII only (`{automated: bool}` on clicks, `{status}` on opens).
  Never the raw IP or the invite token.

Not deduplicated by design: a candidate who opens the instruction page three
times is telling us something. All aggregates count DISTINCT assignments, so
repeats never inflate them.

## Write sites

| Event | Service | Where |
|---|---|---|
| invite send accepted/failed | admin-node | `app/helpers/assessmentInviteEmail.js` → `recordEmailEvent` |
| reminder send accepted/failed | admin-node | `app/models/Assessment.js` `sendRemindersToStudents` |
| `invite_link_clicked` | admin-node | `app/service/InviteShortLinkService.js` `recordClick` |
| `assessment_opened` | student-node | `app/handlers/assessmentHandler.js` `inviteReloadGuard` |

Shared writers: `admin-node/app/service/TrackingService.js` and
`student-node/app/helpers/journeyTracking.js`. Both are **best effort** — they
never throw, so tracking can never fail a send, a redirect or an assessment
start. Failures are logged with context, not silently swallowed.

### Why `inviteReloadGuard` is the "opened" signal
The OTP invite runner calls it exactly once per mount, so it is the truest
server-side "the candidate opened their assessment" signal available — **no
candidate-frontend instrumentation was needed**. It is recorded before the
guard's branching, so a reload landing on a terminal screen still counts as an
open: the candidate did come back and look.

### Automated-fetch filtering
Mail security gateways (Proofpoint, Mimecast, Outlook SafeLinks…) fetch every
link in a message before a human sees it. `InviteShortLinkService` classifies the
user-agent at write time and stores `metadata.automated`; the funnel counts only
non-automated clicks. Without this, every campaign reports near-100% engagement.
A scanner disguised as a browser is indistinguishable at this layer — which is
why *clicked* is a soft signal and *assessment_opened* is the one to trust.

## Read side

`admin-node/app/service/DeliveryFunnelService.js`:

- One SQL per entity type (college/corporate), returning `(stage, assignment_id, reason)`
  triples. Two complete literal queries rather than one with an interpolated column
  name, so there is no string building near SQL — the only variable is bound `$1`.
- `deriveDeliveryStatuses()` collapses the stages into **one status per
  candidate**, most-advanced-wins:

  | precedence | stage | status | label | source |
  |---|---|---|---|---|
  | 1 | `attemptCompleted` | `opened` | **Opened** | assignment row |
  | 2 | `attemptStarted` | `opened` | **Opened** | assignment row |
  | 3 | `assessmentOpened` | `opened` | **Opened** | journey event |
  | 4 | `linkClicked` | `opened` | **Opened** | journey event |
  | 5 | `inviteAccepted` | `sent` | **Sent** | delivery event (any channel) |
  | 6 | `inviteFailed` | `failed` | **Failed** | delivery event (all channels) |
  | — | — | `untracked` | `-` | nothing recorded |

  **Both channels count (2026-08-03).** An assessment invite goes out over
  **email AND WhatsApp**, but only the email leg was recorded until now, so the
  column judged delivery on email alone — a candidate reached only by WhatsApp
  read as *untracked*, and a failed WhatsApp send was invisible. `email_events`
  gained **`channel`** (`email` | `whatsapp`, defaulted so every pre-existing row
  and writer keeps its meaning) and **`to_phone`**; WhatsApp sends are written by
  `TrackingService.recordWhatsappEvent()` from
  `assessmentInviteEmail.sendAssessmentInviteWhatsapp()`.

  One table rather than two, because the column asks a single question — was this
  candidate reached? — and two tables would mean a second query and a merge on
  every render. `to_email` stays populated on whatsapp rows: it identifies the
  candidate (and is what the assignment joins on), while `to_phone` records where
  the message actually went.

  The delivery stages therefore **do not filter on channel** — the two are
  interchangeable evidence, so one accepted send on either is enough for *Sent*,
  and *Failed* requires **every** channel to have failed. `emailAccepted` /
  `emailFailed` were renamed `inviteAccepted` / `inviteFailed` to match; they are
  internal to `DeliveryFunnelService` and nothing else reads them. Verified on DEV
  and UAT: WhatsApp-only → *Sent*; email failed + WhatsApp accepted → *Sent*; only
  WhatsApp failed → *Failed*.

  The failure reason is **prefixed with the channel** (`WhatsApp: …` / `Email: …`)
  because "Couldn't send invitation" is not actionable without knowing which leg
  broke. Note `messageId` is null on whatsapp rows — auth-node's bulk endpoint
  echoes the request rather than returning MSG91's `request_id`, and the column is
  UNIQUE so a placeholder would collide on the second send.

  Migration: `DB-Scripts/Assessment Email Delivery Tracking/20260804T101949Z__email_events_channel.sql`

  **Only three statuses exist: Sent, Failed, Opened (2026-08-03).** The column
  answers one question — did the invitation reach the candidate? — so attempt
  progress does not belong in it; that is the STATUS column's job, and carrying it
  in both made one row state the same fact twice in two vocabularies. The four
  engagement stages therefore **collapse into `opened`** rather than being dropped:
  sitting the assessment proves the candidate opened the link, so folding them up
  keeps those rows truthful instead of demoting them to a weaker status or to
  *untracked*. The precedence walk is unchanged — it just resolves to fewer
  distinct answers.

  Tooltips are plain statements of what happened, not of what the signal proves:
  *Sent — "Invitation was sent"*, *Failed — "Couldn't send invitation: &lt;reason&gt;"*,
  *Opened — "Clicked the link from Email/Whatsapp invite"*.

  **`deliveryStatusReason`** carries the latest `error` from the assignment's failed
  `email_events` so the Failed tooltip can name the cause. It is attached **only** to
  `failed`: a candidate who was handed the link after a bounce reads as *Opened* and
  must not carry the stale bounce text. The SQL gained a third column (`reason`,
  `NULL::text` on every branch except `emailFailed`) — keep the UNION arity in step
  when adding a stage.

  **Legacy statuses are aliased, not deleted.** `admin-react`'s `DeliveryStatusTag`
  maps `clicked`/`started`/`completed` → `opened`, because a rolling deploy can put
  a new bundle in front of an older API that still returns them; without the aliases
  those rows would fall through to the *not tracked* dash and wrongly read as having
  no delivery data. For an aliased status the local label wins, so an old
  *"Completed"* cannot leak through as text.

  A failed send followed by a successful resend reads as `sent`. A candidate whose
  send failed but who clicked anyway (given the link by hand via Copy Link /
  WhatsApp) correctly reads as reached, not failed.

  **Attempt state outranks every email signal (2026-07-31).** Sitting the
  assessment is itself proof the invite arrived. Without this the column
  contradicted the funnel outright — a candidate showing *Completed* above still
  read *"Opened — has not started the assessment yet"*, because the email tracking
  knows nothing about the attempt. The two attempt stages come from
  `assessment_assigned_students` (`submitted = true OR status = 'COMPLETED'`, and
  `status IN ('INPROGRESS','DROPOUT') OR attempted = true`) in the *same* query, so
  there is no extra round trip. Being sourced from the assignment rather than a
  tracking event, they stay correct for candidates predating tracking and for the
  portal-login flow, which has no `/s/<code>` click to record.

  Because the `sent` bucket contains every candidate (the other buckets are
  sub-states of it), the status must be derived per-assignment rather than per
  bucket — otherwise the same person would show a different tag depending on which
  bucket you were viewing.

  **Label naming (2026-07-31):** the DELIVERY column tells the *email's* story, so
  "Opened" belongs to the link click. The runner-mount stage is therefore
  "Assessment Opened" — two statuses sharing one label would be unreadable.

- `annotateWithDeliveryStatus()` stamps `deliveryStatus` + `deliveryStatusLabel`
  onto candidate rows in **both** branches of `getAssessmentDetails`. The table
  and the Excel export read the same field, so they cannot disagree.

`getAssessmentDetails` also returns campaign totals as `deliveryFunnel`
(`emailAccepted`, `emailFailed`, `linkClicked`, `assessmentOpened`,
`hasTrackingData`). The internal `statusByAssignment` Map is stripped before
serialisation.

Counts and `hasTrackingData` deliberately cover the **email/journey stages only**,
not the attempt stages: they describe delivery, and a pre-tracking campaign full
of completed attempts still has no delivery data to show. Such a campaign
correctly reports `hasTrackingData: false` while its candidates still carry a
truthful `Completed` tag.

## Admin UI

- **`admin-react` `Partials/DeliveryStatusTag.js`** — antd `Tag` with a tooltip
  per status. Colour carries urgency, not stage: only `failed` is red, `opened`
  (assessment) is green. Untracked candidates render a muted `—`, never a tag
  asserting something never observed.
- Column sits next to CONTACT DETAILS, because it answers a question about the
  address on the left.
- Excel: `Delivery Status` column in `exportStudentData`.

### Design history (do not re-litigate)
The four stages were first rendered as extra cards in the assessment funnel
strip. That was wrong and was reverted the same day: **Assessment Sent is the
assigned population, Email Sent is how each of those people was contacted** —
two different axes drawn as one sequence. It produced three adjacent cards all
reading the same number, pushed nine cards into a horizontal scroller, and
clipped "Dropped Off" and "Completed" off-screen. Delivery is a property of a
candidate, so it lives in the table. The funnel strip is back to its original
five attempt cards.

## Mail relay

`Mail-Server/app.py` (`PluginLive-Technologies/mail-server`, branch `main`) now
mints an explicit `Message-ID` header per send and returns it as `messageId` in
the 200 body. `user-management-node`'s `assessmentRemainder` echoes it through and
returns **502** when the relay rejects the message.

## Known gaps

- **`delivered` / `bounced` are never written.** That needs OCI Email Delivery
  outbound logging into OCI Logging and/or a Return-Path bounce mailbox, plus a
  small ingest worker keyed on `message_id`. The schema is ready for it.
- **OCI auto-suppresses hard-bounced addresses.** Suppressed candidates silently
  receive nothing forever after, and we have no visibility into that list.
- **`messageId` is NULL on DEV and UAT.** `admin-node/.env` has no
  `EMAIL_ENDPOINT`, so it falls back to the hardcoded **production** relay
  (`https://mail.prod.pluginlive.com/send-email`) — a DEV/UAT container without
  that var sends real mail through the prod relay. The relay change is pushed but
  not deployed to that host (it is PROD infra). Everything else tracks fine.
- **Email opens are deliberately NOT tracked.** A tracking pixel was considered
  and rejected: Apple Mail Privacy Protection pre-fetches images for every iOS
  Mail user (false positives), Outlook blocks remote images by default (false
  negatives), and security gateways produce phantom opens. The honest ladder is
  **delivered → clicked → opened (runner) → started**.
- **No delivery tracking for the portal-login flow's links.** College reminder
  emails link straight to the student FE with no `/s/<code>` redirect, so they
  produce `email_events` but never `invite_link_clicked`.
- Campaigns predating 2026-07-31 have no rows and correctly render `—`.
