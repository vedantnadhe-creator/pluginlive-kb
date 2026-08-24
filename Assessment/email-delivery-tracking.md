# Assessment Email Delivery & Candidate Journey Tracking

## What it is

Records what happened to every assessment invite/reminder email, and what the
candidate did between receiving it and starting the assessment. Surfaced to
admins as a **DELIVERY** column on the assessment detail candidate table and as a
**Delivery Status** column in the exported workbook.

Live on **DEV + UAT** (2026-07-31) and **PROD** (2026-08-22).

Both provider feeds — WhatsApp status callbacks and OCI Email Delivery logs —
are live on **DEV + UAT since 2026-08-20** and **PROD since 2026-08-22**, so
`delivered` / `bounced` are now written by the providers rather than being
statuses nothing ever set.

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
the recipient's mailbox, and since 2026-08-20 the provider feeds write them.
`accepted` is what the UI now calls **Processing**.

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

### Assignment-queue portal invites (fixed 2026-08-24)

The asynchronous assignment worker has two college portal-email paths: the
ordinary non-OTP notification and the terminal Mix & Match group invitation.
Both previously called `UserService.sendAssessmentReminder()` directly. The
mail was sent, but neither path wrote the initial `email_events` row, leaving
OCI's later relay/bounce callback with no Message-ID to match. The admin report
therefore showed **— / No info available** even when the candidate received the
message (PROD example: `ravi.kotadiya@pluginlive.com`, one-part Aptitude float,
2026-08-24 07:15 UTC).

`app/service/TrackedAssessmentReminderService.js` is now the shared choke point
for those two queue paths. It resolves the owning `assessment_assigned_id`,
sends the portal reminder, and records:

- `assessment_invite / accepted` with the provider Message-ID when the relay
  accepts the send; or
- `assessment_invite / failed` with the provider reason when the send throws.

The queue refuses to mark a normal notification emailed when its owning
assignment cannot be resolved. For a Mix & Match float, the single invitation
is recorded against the first successfully assigned part; the report already
aggregates delivery evidence across every part assignment ID.

Shipped: admin-node `c1fc921` on DEV and UAT merge `00e736b`, both deployed
2026-08-24. PROD is unchanged; the historical row is not fabricated or
backfilled by this code change.

Shared writers: `admin-node/app/service/TrackingService.js` and
`student-node/app/helpers/journeyTracking.js`. Both are **best effort** — they
never throw, so tracking can never fail a send, a redirect or an assessment
start. Failures are logged with context, not silently swallowed.

**Side effect (August 2026):** `TrackingService.recordEmailEvent()` also stamps
`assessment_assigned_students.invite_sent_at` when the row it just wrote is an
accepted/delivered `assessment_invite` — first-send-wins, so a reminder or
re-invite never moves it. This is what the admin dashboard's per-candidate
**ASSESSMENT SENT DATE** now reads; see admin.md
[Sent date](Assessment/admin.md#sent-date-created_at--invite_sent_at-august-2026).

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

  **Per-channel breakdown on the hover (2026-08-05, DEV + UAT).** Collapsing both
  channels into one answer is right for the tag but loses the detail an admin acts
  on: a row reading *Sent* because WhatsApp got through gives no sign the email
  bounced, and nobody chases a bounce they cannot see. Each candidate therefore
  also carries **`deliveryChannels`** — `[{channel, status, reason}]` — which
  `DeliveryStatusTag` renders under the summary line on hover:

  | situation | tag | hover |
  |---|---|---|
  | both got through | **Sent** | Invitation was sent · Email — Sent · WhatsApp — Sent |
  | email failed, WhatsApp accepted | **Sent** | Invitation was sent · **Email — Failed: 550 mailbox unavailable** · WhatsApp — Sent |
  | every channel failed | **Failed** | Couldn't send invitation · Email — Failed: … · WhatsApp — Failed: template not approved |
  | WhatsApp only attempted | **Sent** | Invitation was sent · WhatsApp — Sent |

  A channel is judged by the **same rule as the tag** — reached if it ever had an
  accepted send, failed only if it never did — so the two can never contradict
  each other: the tag reads *Failed* exactly when every channel line does. This is
  also why a channel that failed and was then successfully resent reads *Sent*
  rather than showing stale bounce text.

  **A channel that was never attempted is absent, not "Failed."** An unsubscribed
  corporate or a candidate with no phone on file has no WhatsApp leg to chase, and
  printing one would invent work. Historical rows predating channel tracking
  therefore hover with a single Email line.

  The breakdown is attached to **every** status, not just `failed` — the whole
  point is that a *Sent* row can still be hiding a bounced leg. The single
  `deliveryStatusReason` stays failed-only (it is what the tag itself says), and
  the UI suppresses it when channel lines are present so the reason is not printed
  twice; with no channel data it falls back to the old appended-reason hint.

  SQL: a `channel_state` CTE (`bool_or(status IN ('accepted','delivered'))` per
  `(assignment, channel)`) feeds two extra stages, `channelSent` / `channelFailed`.
  The UNION gained a **fourth column** (`channel`, `NULL::text` on every
  non-channel branch) — keep the arity in step when adding a stage. Those two
  stages are collected outside `assignmentIds` on purpose: they are detail hung off
  a candidate, not funnel stages, and counting them would double-count anyone
  reached on both channels. No migration — the existing
  `email_events_assigned_channel_status_idx` already covers the grouping.

  Verified on DEV and UAT by inserting probe rows for all four situations against a
  real campaign, running the deployed `getDeliveryFunnel`, and deleting them again.

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

- `annotateWithDeliveryStatus()` stamps `deliveryStatus` + `deliveryStatusLabel` +
  `deliveryStatusReason` + `deliveryChannels` onto candidate rows in **both**
  branches of `getAssessmentDetails`. The table and the Excel export read the same
  field, so they cannot disagree. `deliveryChannels` is always an array (empty for
  an untracked candidate), so the UI can map over it without a guard.

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
  (assessment) is green. Untracked candidates render a muted `—` with the tooltip
  **"No info available"**, never a tag asserting something never observed.

### The four states (since 2026-08-20)

| Tag | Colour | Means | Row state behind it |
|---|---|---|---|
| **Opened** | green | clicked the link, or started/completed the attempt | `candidate_journey_events` / attempt state |
| **Sent** | blue | **a provider confirmed delivery** on at least one channel | any channel at `delivered` |
| **Processing** | grey | submitted somewhere, confirmed nowhere — still in flight | any channel at `accepted`, none `delivered` |
| **Failed** | red | every attempted channel failed | all channels `failed`/`bounced` |
| **—** | muted | no `email_events` rows at all | — |

Before this split, **Sent meant two different things** — a confirmed delivery and
a message merely handed to the provider — which is precisely how a bounced invite
sat there reading Sent. The distinction only became possible once both providers
started reporting back.

**Processing outranks Failed in the precedence list.** A candidate whose email
bounced while the WhatsApp leg is still in flight has not been declared
unreachable yet; reporting Failed would send an admin chasing someone who is
about to receive the invite. The failed leg is still named in the tooltip, so the
softer tag hides nothing.

The per-channel tooltip uses the same three words (`delivered` → Sent,
`accepted` → Processing, `failed` → Failed), so a Processing tag can say which
leg it is waiting on. The old `sent` channel key is kept as an alias of
`delivered` for rolling deploys.

Funnel stages behind it: `inviteDelivered` (Sent), `inviteAccepted`
(Processing), `inviteFailed`, plus per-channel `channelDelivered` /
`channelAccepted` / `channelFailed` in
`admin-node/app/service/DeliveryFunnelService.js`.
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

## The email leg's provider feed (OCI Email Delivery, since 2026-08-20)

Until this shipped, **email had no provider feed at all**: a row was written at
`accepted` and nothing ever moved it, so a bounced or suppressed address read
**Sent forever**. For scale, PROD suppresses ~2,774 and hard-bounces ~291
addresses a month, none of which reached the DELIVERY column.

OCI Email Delivery has no webhook, but it emits per-message service logs, and
those can be **pushed rather than polled**: Connector Hub reads the log group and
hands each batch to a Notifications topic, whose HTTPS subscription posts to
`POST /delivery-feedback/email/oci`. So there is **no scheduled sweep and no OCI
API credentials in the application**.

### What maps to what

Only what the DELIVERY column can act on:

| OCI log | Written |
|---|---|
| `relay` | `delivered` |
| hard bounce | `bounced`, carrying the bounce code and SMTP status |
| accept **with** an `errorType` (e.g. `Recipient suppressed`) | `failed` |
| clean accept | **nothing** — it only repeats what the row already says |
| **soft** bounce | **nothing, deliberately** — OCI retries for hours and the message commonly lands, so writing it would show an admin a dead candidate who is about to be reached |
| complaint | nothing — delivered then marked spam is a deliverability question, not a delivery one |
| opens / clicks | nothing — `candidate_journey_events` already records the click on our own link |

### Correlation strips the angle brackets

Matching is on the `Message-ID` Mail-Server mints for exactly this purpose, but
**OCI logs it without its angle brackets**, so `applyFeedback` matches a *set* of
forms rather than the literal string. Without that, every email event matches
nothing and the whole feed looks like traffic for another service.

### The subscription handshake is answered, but narrowly

The handler completes the Notifications subscription confirmation itself,
**restricted to a confirmation URL on `oraclecloud.com`** — otherwise an
authorised caller could turn the endpoint into a request-forgery tool. When the
confirming fetch fails it logs the URL so it can be completed by hand.

### The OCI resources (built 2026-08-20, PROD added 2026-08-22)

| Resource | Name / detail |
|---|---|
| Email domain logs | `pluginlive.com` (PluginLivePROD compartment) **and** `prod.pluginlive.com` (PluginLiveDEV), both categories, 30-day retention |
| Log groups | `Default_Group` (PROD compartment), `Dev-Uat-Mail-Track` (DEV compartment) |
| Connectors | `pl-email-logs-prod` — the two PROD logs → `pl-email-delivery-prod`.<br>`pl-email-logs-dev` — all four logs → `pl-email-delivery-dev`. |
| Topics | `pl-email-delivery-prod` (PROD compartment), `pl-email-delivery-dev` (DEV compartment) |
| Subscriptions | `CUSTOM_HTTPS` → PROD on the prod topic; DEV and UAT on the dev topic |
| Policies | `pl-email-log-connector-prod` (PROD connector reads PROD logs + publishes to PROD topic), `pl-email-log-connector-dev` (DEV), `pl-email-log-connector-read-prod-logs` (lets the DEV connector read the shared PROD-compartment mail logs) |

**PROD has its own dedicated pipeline** — own connector, topic, subscription,
policy and secret. Nothing PROD depends on is shared with a lower environment.

**But the source log stream cannot be separated per environment**, and this is
the trap. Every environment sends through `mail.prod.pluginlive.com` as
`mandate@pluginlive.com`, so *all* mail — DEV, UAT and PROD — lands in the
PROD-compartment `pluginlive.com` logs. `Dev-Uat-Mail-Track` is effectively dead:
over 7 days it carried **8 events against 5,902** in the PROD group on a single
day. Removing the PROD log sources from `pl-email-logs-dev` therefore does not
"unshare" anything — it silently kills DEV and UAT tracking, because that is
where their own mail is logged. This was tried and reverted on 2026-08-22.
Genuine per-environment separation needs DEV/UAT to send through their own
relay and email domain, with `EMAIL_ENDPOINT` differing per environment.

**One log stream serves every environment.** Mail-Server sends every
environment's mail as `mandate@pluginlive.com`, so DEV, UAT and PROD invites all
land in the same `pluginlive.com` logs and there is no env discriminator in the
record. Each environment is therefore subscribed to the same topic and applies
only the `message_id`s it recognises; everything else is counted as unmatched
and dropped. Nothing about another environment is *stored* — `applyFeedback`
only writes rows it can match.

**Env vars:** `OCI_LOG_WEBHOOK_SECRET` guards the email endpoint,
`DELIVERY_WEBHOOK_SECRET` the WhatsApp one. Both fail closed: unset means the
route rejects everything rather than running open.

**Watch out:** on DEV the CI deploy rewrites `.env.dev`, which silently dropped
`OCI_LOG_WEBHOOK_SECRET` once and turned real pushes into 401s. Connector Hub
does **not** redeliver an event it has already handed over, so events lost that
way are lost for good.

### WhatsApp: MSG91 sends `eventName`, not `event`

The WhatsApp callback leg was reading a field MSG91 does not send, so those
callbacks applied to nothing. Fixed 2026-08-20 (`c0e4f43`).

MSG91 posts a flat body, not Meta's envelope. The fields that matter:
`eventName` (`sent` → `delivered` → `read`, or `hold`), `requestId` — which is
exactly the id `recordWhatsappEvent` already stores, so correlation needed no new
field — `uuid` (Meta's wamid, fallback only), `customerNumber`, and `reason`.

| `eventName` | Written |
|---|---|
| `delivered`, `read` | `delivered` |
| `failed`, `undelivered`, `rejected` | `failed` |
| `hold` **with** a `reason` (e.g. `131026: Message undeliverable`) | `failed` |
| `hold` with no reason | **nothing** — MSG91 also uses hold for queued-behind-something, and marking a live send dead would be wrong |
| `sent` | **nothing** — the row already reads `accepted`, and there is no legal transition into it |

### Failure reasons are rewritten for the reader (2026-08-20)

MSG91 forwards Meta's numeric code and Meta's wording — `131026: Message
undeliverable` — which is written for the API caller, not for the admin chasing
one candidate. `admin-node/app/helpers/whatsappErrorCodes.js` maps the codes an
assessment invite can realistically produce, **grouped by who has to act**:

| Group | Codes | Reads as |
|---|---|---|
| Candidate unreachable | `131026`, `131021`, `133010` | "This number is not on WhatsApp… reach the candidate by email" |
| Candidate opted out | `131050` | "opted out — do not retry, use email" |
| Retry later | `131049`, `131056`, `131047` | "retry after 24 hours" / "wait before retrying" |
| **Our** template/config | `132000`, `132001`, `132005`, `132007`, `132012`, `132015`, `132016`, `131008`, `131009`, `100` | "needs a fix on our side" |
| **Our** account | `368`, `131031`, `130497`, `131042`, `131048`, `130429`, `80007`, `0`, `10`, `190`, `404` | "contact the platform team" |
| Provider wobble | `1`, `2`, `131000`, `131016`, `131057`, `133004`, `500` | "try resending" |

Source: <https://msg91.com/help/whatsapp/error-codes-for-whatsapp>

Three rules that matter if you touch this:

- **The provider code stays in the text**, in parentheses. The admin does not
  need it; whoever they escalate to does, and without it the tooltip can no
  longer be matched against the MSG91 dashboard.
- **An unmapped code keeps the provider's own wording, untouched.** A new code is
  rare and its original text is at least searchable, where a generic apology
  destroys the only clue anyone has.
- **The rewrite happens on the read side** (`deriveDeliveryStatuses`), never at
  write time. `email_events.error` keeps exactly what the provider said — that
  row is the audit trail support quotes back to MSG91, and rewriting in place
  would mean a mapping change could never be applied to history, nor a bad
  mapping undone. Both the hover and the Excel `Delivery Issue` column read
  through that path, so they cannot disagree.

Email reasons pass through untouched: OCI already writes close to plain English
(`5.1.1 550 mailbox unavailable`).

Webhooks are configured per environment in MSG91 (`pluginlive5`) as three events
each — On Outbound Report Received, On Failed Events, On API Failed Events — all
pointing at that environment's `/delivery-feedback/whatsapp?token=…`. The WABA
(`916380485173`) is shared, so every environment receives every environment's
callbacks and ignores the ids it does not own.

## Known gaps

- ~~**`delivered` / `bounced` are never written.**~~ **Closed 2026-08-20** by the
  OCI Email Delivery ingest — see below.
- ~~**OCI auto-suppresses hard-bounced addresses**, with no visibility into that
  list.~~ **Closed 2026-08-20**: a suppressed recipient now announces itself, per
  message, as an accept carrying `errorType: Recipient suppressed`, so no
  suppression-list snapshot is needed.
- ~~**`messageId` is NULL on DEV and UAT.**~~ **Closed**: Mail-Server mints and
  returns the id, and DEV/UAT rows carry it. But **DEV and UAT still send through
  the production relay** — `EMAIL_ENDPOINT` is
  `https://mail.prod.pluginlive.com/send-email` in every environment, and that
  relay sends as `mandate@pluginlive.com`. That is why one log stream carries all
  three environments.
- **PROD went live 2026-08-22** with a dedicated topic, connector and
  subscription, and `OCI_LOG_WEBHOOK_SECRET` added to the `admin-api-config`
  ConfigMap (the `.env` is mounted by subPath, so a `rollout restart
  deployment/admin-node` is required — it does not hot-reload). Verified end to
  end: a probe mail relayed at 14:54:54Z and the Connector Hub push reached both
  PROD pods at 14:56:49Z with `200`.
- **Rows sent before the subscription existed stay Processing forever.**
  Connector Hub only forwards logs from the moment the connector is created and
  cannot replay history, so every pre-2026-08-22 PROD invite is permanently
  unconfirmed. Whether those should fall back to the `—` / "No info available"
  state instead is still undecided.
- **Confirmation lags 35–80s** behind actual delivery, because Connector Hub
  batches on its own ~60s flush and the Notifications target exposes no batching
  controls. A freshly sent invite legitimately reads Processing for about a
  minute after the candidate already has the mail.
- **Email opens are deliberately NOT tracked.** A tracking pixel was considered
  and rejected: Apple Mail Privacy Protection pre-fetches images for every iOS
  Mail user (false positives), Outlook blocks remote images by default (false
  negatives), and security gateways produce phantom opens. The honest ladder is
  **delivered → clicked → opened (runner) → started**.
- **No delivery tracking for the portal-login flow's links.** College reminder
  emails link straight to the student FE with no `/s/<code>` redirect, so they
  produce `email_events` but never `invite_link_clicked`.
- Campaigns predating 2026-07-31 have no rows and correctly render `—`.
