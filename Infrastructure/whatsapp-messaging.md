# WhatsApp Messaging (WABA + MSG91)

How PluginLive sends WhatsApp template messages, and why the sending path changed in June 2026.

## Two WABAs

PluginLive owns two WhatsApp Business Accounts (both under business "PluginLive Technologies"):

| | Legacy WABA | Current WABA |
|---|---|---|
| WABA ID | `114696961548335` | `36136604129316933` |
| Phone | `102162976151114` | `1207566512435100` (`+91 63804 85173`) |
| Connected Meta app | `PluginLive_Technologies` (`800145154548623`) — our own app | `Interakt ISV` (`256725303808337`), webhook → `whatsapp.phone91.com` |
| Sending path | Direct Graph API with our token | **MSG91 BSP API** |
| Template namespace | — | `ab150d99_86d0_4d64_a278_7f77da79ec0b` |

The current WABA was onboarded through **MSG91** (Walkover; its WhatsApp infra runs on `phone91.com`), which connects numbers via the "Interakt ISV" Meta tech-provider app. Because messaging on that number is owned by the MSG91/Interakt app — not our own Meta app — **our Graph API token cannot send from it** (returns `(#200) You do not have the necessary permissions to send messages on behalf of this WhatsApp Business Account`). Our token can still *manage* templates (business-asset permission), which is how all templates were migrated onto the current WABA via Meta's `migrate_message_templates` endpoint.

## Sending: MSG91

To deliver from the current WABA, send through MSG91's v5 outbound API instead of Graph API:

```
POST https://control.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/
headers: { authkey: <MSG91_AUTHKEY>, Content-Type: application/json }
{
  "integrated_number": "916380485173",
  "content_type": "template",
  "payload": { "type": "template", "template": {
    "name": "<template_name>",
    "language": { "code": "en", "policy": "deterministic" },
    "namespace": "ab150d99_86d0_4d64_a278_7f77da79ec0b",
    "to_and_components": [
      { "to": ["91XXXXXXXXXX"], "components": { "body_1": {"type":"text","value":"..."}, ... } }
    ]
  }}
}
```
Recipient numbers must include the country code (`91…`). Body variables `{{1}}…{{n}}` map to `body_1…body_n` in order.

### Recipient number normalization (country code)

A bare 10-digit recipient (no `91`) makes Meta reject the send with **error `131026` "Message undeliverable"** — its first listed reason ("the recipient phone number is not a WhatsApp phone number") is the one that actually fires, because Meta can't resolve a number without a country code to a WhatsApp account. The other `131026` reasons (India authentication-template block, ToS not accepted, old client version) are boilerplate and do **not** apply to utility templates like `tpo_application_create`.

Frontend flows were inconsistent: TPORequests / ATS sent the full `91…` number and worked, while the job-role-creation flows (`institute-react` `JobRoles/NewJobRole/RolesForm` and `JobPreview`) used `.slice(-10)` and stripped the country code, so every `tpo_application_create` / `tpo_application_updated` send failed `131026`.

Fix (June 2026): `user-management-node` `app/helpers/whatsapp.js` now normalizes the recipient at the single shared `sendWAmessage` chokepoint (covers both the MSG91 and Meta paths, so all callers are protected regardless of how the frontend formats the number):

```js
const normalizeRecipient = (to) => {
  let digits = String(to ?? "").replace(/\D/g, "");
  if (digits.length > 10 && digits.startsWith("0")) digits = digits.replace(/^0+/, "");
  if (digits.length === 10) digits = `91${digits}`; // default India country code
  return digits;
};
```

Numbers that already carry the country code pass through unchanged; a leading `0` is dropped before the check. The `91` default assumes Indian recipients — revisit if international numbers are onboarded.

## Where this is wired

- **WhatsApp Portal** (`~/tools/whatsapp-portal`, dev.pluginlive.com/whatsapp): template listing/create still use Meta Graph API (works with our token); **sending** goes through MSG91 (`src/lib/msg91.ts`, selected by `WA_PROVIDER`).
- **user-management-node** (PROD = `auth-node`): `app/helpers/whatsapp.js` has both a Meta and an MSG91 send path, selected by `WA_PROVIDER`. No caller changes; template-vs-text branching preserved.

## Config (env)

Provider switch is env-driven; `meta` (default) keeps the legacy Graph API path, `msg91` uses MSG91.

```
WA_PROVIDER=msg91
MSG91_AUTHKEY=<from MSG91 dashboard → Settings/API>
MSG91_BASE_URL=https://control.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/
MSG91_INTEGRATED_NUMBER=916380485173
WA_TEMPLATE_NAMESPACE=ab150d99_86d0_4d64_a278_7f77da79ec0b
```

In PROD these live in the `auth-api-config` ConfigMap (mounted at `/app/.env` on `auth-node`, namespace `api`); in DEV/UAT they are in the service's `.env`/`.env.<env>` (untracked, per-environment).

## Managing templates without the panel (MSG91 API)

`MSG91_AUTHKEY` alone is enough to create templates, submit them to Meta, and read
approval status — no MSG91 panel login and no Meta token. Our Meta token is dead for the
current WABA (`GraphMethodException` on phone-id `102162976151114`, which belongs to the
retired direct-Graph WABA), so Graph API is not an option for this.

The endpoint names are not guessable and the docs render client-side, so scrape them:
`curl -sL https://docs.msg91.com/whatsapp/<page> | grep -oE "api/v5/whatsapp[a-zA-Z0-9/_-]*"`.

**List templates + Meta approval status**

```bash
curl -s -H "authkey: $MSG91_AUTHKEY" \
  https://control.msg91.com/api/v5/whatsapp/get-template-client/916380485173
```

The number is a **path segment** — `?integrated_number=` returns 404. Response gives every
template's `status` (`approved` / `pending` / `rejected`), `rejection_reason`, `category`,
Meta `id`, and the literal approved body in `code[].text`. This is the only reliable way to
answer "is template X live?" — the answer is not in any repo.

**Create a template and submit it to Meta**

```bash
POST https://api.msg91.com/api/v5/whatsapp/client-panel-template/
{"integrated_number":"916380485173","template_name":"...","language":"en",
 "category":"UTILITY","button_url":false,
 "components":[{"type":"BODY","text":"...","example":{"body_text":[["sample1",...]]}}]}
```

GET on that path returns 405; it is POST-only. Returns `template_id` immediately with
"creation in process"; approval came back in well under an hour for UTILITY. Working script:
`/home/ubuntu/create_wa_templates.py` (validates ascending `{{n}}` and sample/variable count
before it sends anything).

## Assessment invites over WhatsApp (corporate, opt-in)

### Dynamic corporate deadline copy and invite/reminder intent (DEV + UAT, 2026-08-17)

Corporate assessment communications now calculate a short candidate-facing CTA
from the assessment map's deadline in the IST wall-clock frame. More than 36h
remaining renders `Complete it by tomorrow at 12 PM`; at or below 36h it uses
the real deadline with `today` / `tomorrow` and preserves non-zero minutes. An
expired deadline suppresses the send. The common formatter is
`admin-node/app/helpers/candidateDeadline.js`; do not compare the map value as an
honest UTC instant.

Invite and reminder are explicit intents in `assessmentInviteEmail.js`. Email
reminders now have reminder subjects/headings/body copy instead of reusing the
invite voice. AI Interview still reads `interview_duration` from its DB config,
converts seconds to minutes, and falls back to 25 only when the value is absent.

Four Meta UTILITY templates carry this copy. All four were submitted 2026-08-17
and **approved by Meta the same day**, category retained as `UTILITY`:

| Intent/type | Template | Meta ID |
|---|---|---|
| generic invite | `corporate_assessment_invite_deadline_v1` | 2547612762369170 |
| generic reminder | `corporate_assessment_reminder_deadline_v1` | 1070698069181721 |
| AI Interview invite | `corporate_ai_interview_invite_deadline_v1` | 2096031501050807 |
| AI Interview reminder | `corporate_ai_interview_reminder_deadline_v1` | 1075056545056176 |

**Meta rejects a body whose `{{n}}` do not first appear in ascending order.**
Two PRD sentences had to be reworded to satisfy this — the generic invite now
reads "You have been invited to complete the {{2}} for the {{3}} role at {{4}}"
(the PRD led with the company) and the AI reminder reads "your AI-powered
interview with {{2}} for the {{3}} role". Neither moved a parameter: the
positional contract still matches `WHATSAPP_TEMPLATES` exactly. If a future
template needs reordering, reword the sentence — renumbering the params
silently scrambles the delivered message with no error anywhere.

Rollout variables are `WA_ASSESSMENT_INVITE_TEMPLATE`,
`WA_ASSESSMENT_REMINDER_TEMPLATE`, `WA_AI_INTERVIEW_INVITE_TEMPLATE`, and
`WA_AI_INTERVIEW_REMINDER_TEMPLATE`, **now set on DEV and UAT**. Unset means the
legacy templates stay selected with their date-only parameter contract; the full
CTA sentence goes only to the four names above, gated by the
`usesFullDeadlineSentence` set in `assessmentInviteEmail.js`. Rollback is
commenting out the affected line and restarting — per intent and per assessment
family, no rebuild. Do not edit or replace the legacy Meta templates in place;
they are the rollback floor.

Env lives in the **box** env file that the deploy bakes (`admin-node/.env` on
DEV, `.env.uat` on UAT), not in `docker run -e` — a `-e`-only flag is dropped by
the next rebuild.

**PROD is not switched.** The templates are WABA-scoped so they already exist
there; only the four env vars are missing.

Code: admin-node `242a36a` (UAT) / `c80c79a` (Development), user-management-node
`3d404a7` (UAT) / `0261107` (Development).

Corporate assessment invites send a **WhatsApp reminder alongside the invite email**
(admin-node; DEV + UAT as of 2026-08-03, PROD pending).

The send is hooked into `app/helpers/assessmentInviteEmail.js` `sendAssessmentInviteEmail`.
Every caller of that function is already the corporate no-login OTP invite flow, so one hook
covers all nine assign/clone/add/resend call sites and is inherently corporate-only. It is
best-effort: a failure never blocks or fails the email.

**Opt-in per corporate.** Gated on `admin.feature_config` — one active row per
`(journey, feature)`, with `journey_ids` listing the subscribed entity ids and `is_enabled`
as the feature-wide kill switch. The feature key is `CORPORATE / WHATSAPP_NOTIFICATION`.
`FeatureAccessService` **fails closed**: a missing table, missing row, unknown corporate or
any query error all mean "not subscribed" → email only. Reads are cached 60s, so a toggle
takes up to a minute to apply (the setter invalidates its own key, so a UI save is instant).

> `admin.feature_config` was created 2026-04-06 and dropped 2026-04-27 (admin-node `85ee7a4`,
> "remove feature enable/disable config setup") because nothing consumed it. It was restored
> by DB-Scripts `20260803T102935Z__feature_config_whatsapp_notification.sql` — apply that
> before expecting the toggle to work in an environment (it 409s otherwise).

**Admin UI.** Feature Access → Service Type has a corporate-only **WhatsApp Notifications**
toggle (admin-react `Assessment/Partials/AssignSubscription`). It reads
`GET /assessment/featureAccess?entityId=&entityType=corporate` and saves via
`POST /assessment/assignSubscription` with `whatsappNotificationEnabled`. **Omitting that
field leaves the flag untouched** — only an explicit boolean writes, so existing callers and
the whole college path are unaffected.

**Phone resolution.** Four of the nine call sites never pass `phone` (Aptitude's sync assign,
`addStudentsToAssessment`, and the two resend/extend paths), so the reminder used to be
silently skipped for those flows for every type. `sendAssessmentInviteWhatsapp` now falls back
to `COALESCE(aas.contact_number, spp.contact_number)` — the same source the `/s/` resolver uses
for the SMS OTP phone claim. No phone anywhere → silently skipped, by design.

**Template — selected per assessment type _and intent_.** Since 2026-08-17 `resolveTemplateName(assessmentType, intent)` picks on both axes; the table below is the
legacy/rollback set, and DEV+UAT now resolve to the four
`corporate_*_deadline_v1` names documented above. Param order is pinned to the template name in
`WHATSAPP_TEMPLATES` (Meta fixes the `{{n}}` count per template, so the two must travel
together). An unknown name falls back to the 6-param builder rather than sending a malformed
message.

| Type | Template | Params |
|---|---|---|
| AI_Interview | `aiinterview_access_link` | 7 — name, **company**, role, **duration**, deadline, **email**, link |
| everything else | `student_online_assessment_email_link` | 7 — name, **assessment label**, role, company, deadline, link, **email** |
| (fallback) | `student_online_assessment` | 6 — as above, no email |

Note the two 7-param templates are **not interchangeable**: the AI one puts company in `{{2}}`
and email *before* the link, the generic one puts the assessment label in `{{2}}` and email
last. Selecting the wrong one silently renders a scrambled message, which is the whole reason
name and param-builder are defined as one unit.

AI Interview has its own template because its copy is interview-specific ("This is an
AI-powered interview… approximately `{{4}}` minutes"), which reads wrong for an Aptitude or
Communication candidate. `{{4}}` is also why it cannot be the global default: `durationMinutes`
comes from the interview config and is null for every other type (it defaults to 25 rather than
emitting a blank param, which Meta rejects).

**The deadline param must be supplied by the caller.** Meta rejects a blank body param, so a
missing `endDate` becomes the literal string `"the scheduled date"` — which renders to the
candidate as *"has been scheduled with Acme on the scheduled date"*, i.e. indistinguishable
from a broken template. It is a last resort, **not** a substitute for passing a real label:
every call site is expected to pass one formatted `DD MMM YYYY, hh:mm A`. Role_Based shipped
this placeholder to real candidates until 2026-08-13 because its assign flow read the deadline
from a nullable config field instead of the assessment map — see
`Assessment/rolebased.md`. The fallback now logs a warning when it fires, so the next
occurrence is greeted by a log line rather than a screenshot. The same missing value also
blanks the invite email's "Please complete the assessment by …" line, since `buildHtml`
renders `deadlineLine` as `""` when it is falsy.

Overrides: `WA_ASSESSMENT_TEMPLATE` for the default, `WA_ASSESSMENT_TEMPLATE_AI_INTERVIEW` for
the AI Interview slot — so one type can be rolled back without touching the others. Templates
are **WABA-scoped** and DEV/UAT/PROD share one WABA, so an approved template is usable in every
environment at once; the env vars exist only to switch back without a deploy.

Verified on UAT 2026-08-03 across **AI_Interview, Aptitude, Communication, Custom_Assessment
and Role_Based** — five assigns, five `POST /notification/bulkWhatsapp` calls, all HTTP 200,
no MSG91 errors. Hinglish and Behavior have no corporate-OTP maps on UAT to exercise.
The per-type AI Interview template was verified separately on DEV and UAT the same day.

### Extra env this needs (per environment)

```
AUTH_TOKEN=<long-lived system JWT>              # admin-node -> auth-node
WA_ASSESSMENT_TEMPLATE=student_online_assessment_email_link
```

`AUTH_TOKEN` is the one that bites: admin-node had **no** `AUTH_TOKEN` in any environment, and
auth-node's `/notification/*` routes are `isPrivate` (JWT-only), so without it every send 401s
— caught and logged, so it looks like "WhatsApp just doesn't fire". Mint it with auth-node's
own `LOGIN_SECRET_KEY`, `role: system`, issuer/audience `pluginlive.com` (mirrors auth-node's
existing `SYSTEMJWT`). Mint it **on the target box** so the secret never moves.

## ATS (corporate-node) WhatsApp sends — same opt-in gate

The ATS has its own WhatsApp senders, entirely separate from the assessment-invite leg above.
Until 2026-08-04 **none of them checked anything**: presence of a phone number was the only
condition, so candidates of corporates that had never been subscribed to `WHATSAPP_NOTIFICATION`
received WhatsApp anyway. All three now resolve the owning corporate and go through the same
`admin.feature_config` gate (corporate-node `app/services/FeatureAccessService.js` — a
**read-only** mirror of admin-node's; admin-node still owns the write side, so one row keeps
one writer). DEV + UAT as of 2026-08-04, PROD pending.

| Flow | Template | Corporate id from |
|---|---|---|
| Bulk "Invite Candidates" upload on a role (`bulkUploadInviteCandidates`, `app/handlers/common.js`) | `corporate_role_invite` | `jobRoles.corporateId` via `getJobRoleById` |
| Lapsed approval request (`app/helpers/notification.js` `createNotifications`) | `approval_lapsed_uti` | `notification.companyId` |
| Assessment round scheduled, `EXTERNAL_LINK` mode (`NotificationService.triggerNotificationWhenAssesmentSchedualed`) | `assesment_invite_link` | `role.corporateId` |

The **email and in-app legs are untouched** — only the WhatsApp leg is gated, so an unsubscribed
corporate loses nothing it had before WhatsApp existed. The `Phone` column on the invite sheet is
still parsed and stored on the invite row; it just no longer implies consent to message.

Two implementation notes worth keeping:

- `FeatureAccessService` is required **directly** (`require("./FeatureAccessService")`), not off
  the `app/services` barrel, inside `NotificationService.js`. `index.js` loads NotificationService
  before it assigns `FeatureAccessService`, so a destructure off `"."` there resolves to
  `undefined` at call time — the classic silent-`undefined` circular-require in this repo (the
  same warnings appear at boot for `JobRoleInstituteMap`, `Drive`, etc.).
- Prisma is resolved per call (`require("../helpers/utils").getPrismaInstance()`) rather than
  bound at module load, matching admin-node — keeps the lookup stubbable and avoids pulling
  `helpers/utils`' dependency chain into a unit test (`test/featureAccess.spec.js`).

### Still ungated: TPO share-on-publish (frontend sender)

One WhatsApp path is **not** covered by the above and still fires for every corporate:
`corporate_role_share_tpo`, sent to each college's TPO POC numbers when a role is published from
the Select Colleges drawer. It is built and dispatched **in the browser** —
`corporate-react/src/modules/Roles/NewRoleCreation/Partials/SelectCollegesDrawer/index.js`
(~line 1142) calls `sendNotificationBulkEmailWhatsapp` straight at
`/notification/bulkWhatsapp` — so there is no server-side choke point to gate, and a client-side
check would not be a real control anyway. Gating it properly needs a corporate-facing
feature-access endpoint on corporate-node (admin-node's `/assessment/featureAccess` is
admin-authed) plus a corporate-react rebuild. Note this one targets **TPO staff at colleges**,
not candidates, which is why it was left out of the 2026-08-04 fix rather than rushed.

corporate-node reads `admin.feature_config` over its own Prisma client on the shared database.
That is cross-schema, which the coding standard normally forbids, but it matches existing
practice in the repo (`JobRoles.js` already `$queryRaw`s `student.*` directly) and the table has
a single writer in admin-node.

## Gotcha

Do **not** "just swap `WA_PHONE_ID`" to the current WABA in a Graph-API sender — sends fail `#200`. The current number can only be sent to through MSG91 (or by moving the number's Cloud API registration onto our own Meta app, which would disconnect MSG91).

### Template param values must be single-line (no `\n` / tab / 4+ spaces)

WhatsApp/Meta reject any **template variable value** that contains a newline, tab, or more than 4 consecutive spaces. Via MSG91 this surfaces as a **synchronous HTTP 400** (`ERR_BAD_REQUEST`) on `POST …/whatsapp-outbound-message/bulk/` — the whole bulk call fails, not just one recipient. (This is distinct from the **async** `132000` "localizable_params (N) does not match expected (M)" placeholder-count error, which returns a `{status:"success", …"in process"}` synchronously and only fails later in the delivery report.)

This bit the corporate Schedule drawer: the recruiter's multi-line **Note/Instructions** (a textarea) is sent as the last body param of `corporate_online` / `corporate_offline`, so any note with line breaks 400'd the send. Fix (`user-management-node` `app/helpers/whatsapp.js`): `buildMsg91Components` runs every param through `sanitizeParamValue`, the single choke point every MSG91 template send flows through, so all callers/templates are covered. Any new free-text template param is safe by default — don't re-add newlines downstream.

`sanitizeParamValue` splits on `\r?\n`, squeezes tabs/4+ spaces and trims **per line**, drops blank lines, then joins the surviving lines with a bullet separator `" • "` (`LINE_SEPARATOR`). So a 3-line note renders as `Line1 • Line2 • Line3` — each item stays visually distinct instead of collapsing into one run-on paragraph (the earlier fix joined with a plain space). A single-line note is unchanged (no stray bullet).

**True per-line stacking is impossible inside a template variable.** Meta's block is on `\n`/`\r`/`\t` specifically; the `U+2028` LINE SEPARATOR char passes the 400 check but renders as a broken glyph (`�`) on WhatsApp clients, so it's not a usable substitute — verified on UAT. The only way to get real line breaks is to bake them into the **static** template body text in Meta Business Manager (static text may contain newlines; `{{n}}` values may not) using a fixed number of separate variables, which requires a template edit + Meta re-approval. Bullet-separator is the shipped approach.

### A MARKETING-category template is silently dropped

A template in Meta's **MARKETING** category is **accepted by MSG91 and then never delivered**.
MARKETING sends are gated behind per-recipient marketing opt-in plus Meta's marketing-message
limits; UTILITY sends are not. Transactional templates (assessment invites, interview
reminders) **must be UTILITY**.

This is expensive to diagnose because every layer reports success: MSG91 returns HTTP 200
`{"status":"success","hasError":false,"data":"Your request is in process, check delivery
reports for status"}` — acceptance, **not** delivery, and identical for delivered and dropped
messages — so `sendWAmessage` returns normally and the caller logs a success. WABA and phone
health also look perfect (`ACTIVE` / `APPROVED` / `CONNECTED` / `GREEN`).

Check the category first when WhatsApp "stops working":

```bash
TOKEN=$(grep '^WA_ACCESS_TOKEN' ~/api/user-management-node/.env | cut -d'"' -f2)
curl -s "https://graph.facebook.com/v17.0/<template_id>?fields=name,status,category,rejected_reason" \
  -H "Authorization: Bearer $TOKEN"
```

Meta can **re-categorise a template it previously approved as UTILITY into MARKETING** on its
own review, so a template that worked can start failing with no code change on our side.

**Verifying delivery at all** — the only trustworthy signal is Meta's own WABA analytics
(our token has business-management access). Note the daily bucket is timezone-offset (today's
sends can land in yesterday's bucket) and `granularity(HOUR)` returns nothing on this WABA, so
compare `sent`/`delivered` **deltas** on `granularity(DAY)` rather than looking for today's row:

```bash
START=$(date -u -d '2 days ago 00:00' +%s); END=$(date -u -d tomorrow +%s)
curl -s "https://graph.facebook.com/v17.0/36136604129316933?fields=analytics.start($START).end($END).granularity(DAY)" \
  -H "Authorization: Bearer $TOKEN"
```

This WABA is shared by DEV/UAT/PROD, so on a busy day the delta includes other traffic — for a
single test send, prefer auth-node's own logs (`POST /notification/bulkWhatsapp` → `statusCode`).

**Creating templates via the Graph API:** wording that mentions a *verification/OTP code* is
instant-`REJECTED` with `rejected_reason: INCORRECT_CATEGORY` (it reads as AUTHENTICATION).
Phrase it like the approved `aiinterview_with_link`: "You can also check your registered email
({{n}}) for additional instructions." Our token can create and list templates but **cannot
delete** them (`#100`), and every MSG91 management endpoint (templates, balance, delivery
reports) **404s** with our authkey — it is send-only, so delivery logs need the MSG91 dashboard
(account `pluginlive5`).
