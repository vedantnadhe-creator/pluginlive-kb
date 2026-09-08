# Corporate Assessment Dashboard (LIVE on DEV + UAT since 2026-08-27)

The corporate portal's assessment surface: a cockpit dashboard, an assessments
list, a per-assessment detail page and a full schedule, all in
`corporate-react-v2` under `/v2`, backed by ten new read endpoints on
**`corporate-node`** (the v1 API), not `corporate-node-v2`.

**Creating** an assessment is a separate story: the Create-Assessment wizard
(`/v2/assessments/new`) does NOT go to corporate-node at all — it reuses
**admin-node's existing `/assessment/*` endpoints**. See
[Creating an assessment](#creating-an-assessment-the-float-wizard) below.

| Screen | Route | Feeds from |
|---|---|---|
| Dashboard | `/v2/dashboard` | `dashboard/v2/summary`, `dashboard/v2/assessment`, `dashboard/v2/filters` |
| Assessments | `/v2/assessments` | `assessments/v2/list`, `assessments/v2/candidates` |
| Assessment detail | `/v2/assessments/:id` | `assessments/v2/:id/{overview,candidates,candidates/report}` |
| Schedule | `/v2/schedule` | `dashboard/v2/schedule?from=&to=` |
| Usage widget (top bar) | both primary screens | `assessments/v2/usage` |

All are `GET`, namespaced `/corporates/:corporateId/...`, `isPrivate: true`.

## Why corporate-node and not corporate-node-v2

Corporate assessment data lives in the `assessment` schema, not `corporate`.
`corporate-node-v2` pins `search_path=corporate` and hand-authors its Kysely
types, so cross-schema analytics fight it. `corporate-node` already owns
corporate identity, the corporate JWT and `FeatureAccessService`, and already
reads across schemas (`FeatureAccessService` → `admin.feature_config`,
`JobRoles.js` → `student.education_profile`). The analytical SQL was ported in
from institute-node's TPO Dashboard v2 rather than reused in place.

## The feature gate is accessLevel, not feature_config

`corporate.corporates."accessLevel"` is the switch admin already sets on
**Feature Access → Corporates → ASSMT.** (`admin.<env>/assessmentAccess`):

| accessLevel | ATS | Assessment |
|---|---|---|
| 1 | yes | no |
| 2 | no | yes |
| 3 | yes | yes |

`FeatureAccessService.isAssessmentEnabledForCorporate` reads it and surfaces it
as `ASSESSMENT` on the existing `GET /corporates/:id/feature-access`. **No
`admin.feature_config` row and no schema change** — a second parallel switch
would let an admin turn the menu on for an account with no subscription. Fails
closed on any error.

### The v1 menu item needs BOTH gates, and RBAC had to be bypassed

`src/modules/Nav/navItems.js`'s Assessments entry carries
`requiresFeature: 'ASSESSMENT'` and points at `/v2/dashboard` when
`CORPORATE_V2_ASSESSMENTS_ENABLED === 'true'`.

**`PermittedNavItems` hid it for every corporate, forever.** That check passes
only when the user holds a permission whose `screenName` matches the item's
`navTitle`, and there is **no ASSESSMENTS screen in the CORPORATE journey** —
`admin.screens` has DASHBOARD, ROLES, USERS, REPORTS, SETTINGS, ACTIVITY LOG,
INTERVIEWER DASHBOARD and JOBROLES. Items declaring `requiresFeature` are now
exempt from the screen check (`src/utils/permissionsValidation.js`); their gate
is the subscription. To reintroduce per-user RBAC, add an ASSESSMENTS screen row
and drop `requiresFeature`.

`CORPORATE_V2_ASSESSMENTS_ENABLED` is **deliberately separate from
`CORPORATE_V2_ENABLED`** — one flag governing both is what previously dragged
Roles into v2 by accident. It lives in `.env` / `.env.uat`, which are gitignored,
so it must be set per box or the item falls back to the legacy `/assessments`
screen (the safe direction).

Roles now points back at v1 `/rolePage` on **both** ends — v2's sidebar bridges
to v1 too. Flip one without the other and the two sidebars point at each other.

## Data model traps

- **Corporate windows are IST wall-clock stored as UTC.** Compare against
  `NOW() + INTERVAL '5 hours 30 minutes'`, and emit dates re-tagged `+05:30`
  (`istIsoOf`). `.toISOString()` shifts every date by 5h30m in the UI.
- **A float is one row per type**, tied by `mix_match_group_id`. Identity is
  `COALESCE(mix_match_group_id, assessment_corporate_map_id)`; a one-part group
  keeps its own map id and type. `:id` resolves either form.
- **No `draft` or `cancelled` status exists** — a corporate assessment does not
  exist until floated and cannot be cancelled. Those tabs are removed from the
  list.
- **No schedules, departments, passing years or campuses.** Every float is
  `one_time`; the week rail and schedule key on the **open window**, not the
  start date, or an assessment open all week appears on no day.
- **"Taken" means COMPLETED — `submitted = true`. A dropout is not a take.**
  Two predicates in `helpers/corporateAssessmentSql.js` govern every v2 number,
  and which one you reach for is the single easiest thing to get wrong here:

  | predicate | SQL | use it for |
  |---|---|---|
  | `ATTEMPTED_PREDICATE` | `submitted OR attempted` | scores, times, reports |
  | `COMPLETED_PREDICATE` | `submitted` | **every completion count** |

  A DROPOUT row carries `attempted = true, submitted = false`, so anything
  counted off the attempt predicate credits people who opened the paper and
  walked away. These were **one** predicate (`TAKEN_PREDICATE = submitted OR
  attempted`) from 2026-09-01 to 2026-09-08, deliberately aligned to admin v1
  so the two screens would stop disagreeing — meesho/UAT read 40 against
  admin's 48, the gap being exactly its DROPOUT rows. That alignment made v2
  **wrong**: the dashboard's "Assessments taken" card read 72/165 (44%) for
  Sailesh Testing Sprint 25, whose candidates had actually finished 47 (28%),
  and every per-type ratio beneath it was inflated the same way (Aptitude 22 vs
  14, Communication 19 vs 13, AI Interview 19 vs 12, Role Based 12 vs 8). The
  same conflation inflated the assessments list's **Completed** column and the
  detail page's **completion funnel**. Split on 2026-09-08.

  **This now diverges from admin v1 on purpose.** Admin's corporate drill-down
  (student-node `TpoDashBoard.getAssessmentStatesForCorporate`) still counts
  `attempted = true` and therefore still over-reports; **admin v1 needs the
  same fix**. Until it gets one, v2 reads lower than admin for any corporate
  with dropouts — v2 is the correct number.

  Two things deliberately stay attempt-based, and neither is a bug:
  - **Scores and times.** A dropout is scored on what they did answer, so
    excluding them from an average discards real marks.
  - **The attempt-rate bands** ("80% or more attempted", "Yet to attempt") and
    the detail page's `started` count — opening a part *is* an attempt.
  - **Reminder recipients** (`getPendingRecipients`). Switching that to the
    completion predicate would start mailing every dropout on the roster; who
    gets contacted is a product decision, not a counting fix.
- **KPI counts are per (float, PART, candidate).** Folding to the float first
  and fanning its types back out credits every candidate with every type on the
  float the moment they submit any one part — that read AI Interview 26 taken
  on DEV where 12 interviews existed, under a headline that disagreed with its
  own tooltip.
- **`students.full_name` is empty on a large share of rows** — the real name is
  in `first_name` / `last_name` (every candidate on UAT's machine_learning
  fresher assessment is a "John Doe" or "Jane Smith" stored that way). Reading
  full_name alone falls through to the email fallback and the roster prints the
  address twice: bold as the name, muted as the email beneath it. Resolve names
  through `CANDIDATE_NAME_SQL` (helpers/corporateAssessmentSql.js), which tries
  full_name, then `CONCAT_WS(' ', first_name, last_name)`, then the email, and
  takes an optional aggregate for callers that GROUP BY the email. **Search must
  use the same expression** or typing a name the row is visibly displaying finds
  nothing.
- **Duplicate `student_personal_profile` rows fan every profile join out.** The
  same email can hold 2-4 profiles (a duplicate-creation race; four meesho
  candidates do). A plain `LEFT JOIN spp … LEFT JOIN students` therefore
  over-counts: the candidate list reported **75 candidates on a roster of 67**
  and printed those four twice, and the detail roster inflated
  `parts_held`/`parts_submitted` the same way. Join through
  `STUDENT_PROFILE_LATERAL` (helpers/corporateAssessmentSql.js) — newest
  profile, `LIMIT 1`, `LEFT JOIN LATERAL … ON TRUE` so an email with no profile
  is still listed.
- **Score breakdowns are NOT all in the `sections` table.** Communication and
  Role Based write one row per section there; **Custom Assessment** keeps its
  sections in `custom_assessment_scores.section_wise_stats` (jsonb OBJECT keyed
  by section name) and **Aptitude** keeps its categories in
  `aptitude_scores.statistics.categories`. Both were missed by the section
  union, so the report drawer showed "Breakdown unlocks once the attempt is
  scored" on fully scored attempts until 2026-09-01. Three traps when reading
  them: `statistics` is `json` on UAT but `jsonb` on DEV (cast `::jsonb`);
  `jsonb_each`/`jsonb_array_elements` error on the wrong type and a `WHERE`
  guard runs AFTER the lateral, so the type check must sit inside the call; and
  Aptitude uses negative marking, so clamp with a `CASE` — a bare
  `GREATEST(0, LEAST(100, …))` ignores NULL and scores a zero-mark category 100.
- **Communication totals use the report formula, never a flat section average.**
  `helpers/assessmentScoreSql.js` weights Speaking 0.4, Reading 0.2,
  Listening 0.1 and Writing 0.3; Writing is the mean of its four applicable
  subsections (Email Writing or Dictation according to `is_email_writing`). A
  restricted `enabled_sections` set renormalises the enabled group weights.
  Retakes replace the original attempt and duplicate section rows collapse with
  `MAX`. This is the same calculation used by the candidate PDF; the previous
  `AVG(communication_scores.score)` made one UAT attempt read 53% in the portal
  but 33.76/100 in the PDF.
- **A Communication CEFR rung is relative to the question set, not a percentage
  band.** The candidate endpoint returns `byType[].level`, preferring a stored
  `progression_history.assessment_cefr` and otherwise mapping the unrounded
  weighted score against `assessment_sets.cefr_level` with the report's ladder
  and cap. The detail doughnut, its level filter, and the candidate drawer use
  that server value. Other assessment types, and Communication sets without a
  CEFR value, continue to use their client-side score bands.
- **Custom Assessment and Aptitude carry real per-section weights**
  (`total_marks` per section/category), so their breakdown bars are weighted by
  marks. Every other type gets an equal split, because its scorer's weighting is
  not stored and an invented one would be a guess dressed as fact.
- **AI Interview scores are one row per SESSION** (up to 2 per assignment) —
  pre-aggregate or every count inflates. Its competency breakdown lives in
  `parameter_scores` (jsonb, 0-4 ratings, rescaled ×25) on ~2/3 of rows; the
  four `*_score` columns cover only the rest.
- **Behaviour has no score**, only levels — never in an average.
- **Never resolve a set with `MIN(created_at)`.** Stray assignments spawn sets;
  read the set actually served via `aas.assessment_set_id`.
- `role_name` / `seniority` come from `assessment_sets` at creation and exist
  only for Role Based and AI Interview. They are **not** the ATS `mapped_to`
  link, which is populated on ~2% of production floats. Aptitude and
  Communication carry a **level** instead of a role — Aptitude's `difficulty`
  tier, Communication's `cefr_level` — surfaced as `typeDifficulty`. The detail
  page's "Assigned level" and the Total Candidates card's "Assigned for …" read
  `assignedLevel` first and fall back to that map, so those two types show a
  level rather than a blank; the Role row is dropped entirely when there is no
  role.

## The type legend is subscription-scoped

The list's type legend and the Filters panel's **Assessment type** options show
only the types the corporate is SUBSCRIBED to, not all six the platform
supports. Before 2026-09-08 they enumerated the fixed six, so a corporate on
Communication + Aptitude was shown Role-Based, AI Interview, Behavior and
Custom sitting permanently at 0 and could filter by types it cannot float.

Subscriptions live in `assessment.subscribed_corporates` and already reach the
browser on the usage payload (`getUsageQuota` returns one `breakdown` entry per
subscribed type), so `visibleAssessmentTypes` in `lib/assessmentTypes.ts`
narrows the supported six to that set — no extra endpoint.

Two deliberate widenings, so the UI never claims LESS than the truth:

- An unanswered or failed usage call falls back to the full supported list. An
  empty legend reads as broken, and hiding types on a fetch failure is a worse
  lie than showing one too many.
- The set is unioned with the types the corporate's own assessments actually
  carry, so a lapsed subscription cannot hide a type whose rows are still
  listed under the legend.

Order always follows `CORPORATE_ASSESSMENT_TYPES` so the row never reshuffles.
Backend types the product has no UI for (`Cognitive`, `Tech_MCQ`,
`Tech_Coding` — real subscriptions on UAT) are still dropped by that list.

### The dashboard's level tabs use the same rule (DEV + UAT, 2026-09-08)

**Candidate Distribution by Levels** (`dashboard/_components/Competency.tsx`)
had the same bug one screen over: it enumerated all four *laddered* types, so
the UAT corporate "demo replica knack rcm" — subscribed to Aptitude (112/1000)
and Communication (113/1000) and nothing else — was given Role-Based and AI
Interview tabs that open onto a ladder which can never fill, directly beneath
a usage widget listing the two types it actually has.

Same helper, same two widenings. Two filters now stack:

1. the type must HAVE a ladder (`COMPETENCY_TYPES` — Custom and Behavior have
   no levels defined, so a tab could only ever be empty), and
2. the corporate must be subscribed to it (or have candidates on it).

**The active tab is derived, never stored.** The tab list only exists once the
usage call answers, so the default selection (`COMPETENCY_TYPES[0]`, Aptitude)
can name a type this corporate turns out not to have. It falls back at render
time — `tabs.includes(picked) ? picked : tabs[0]` — rather than being corrected
by an effect, which would render the wrong ladder for a frame first. When a
corporate has none of the laddered types the tab bar is not rendered at all.

Guarded by `scripts/check-competency-subscribed-tabs.mjs` (8 checks).

## Usage pack — live upstream, re-read on tab focus (DEV + UAT, 2026-09-08)

`assessments/v2/usage` reads `assessment.subscribed_corporates` on every call
and nothing on the path caches: `corporateNodeGet` and the widget's own fetch
both send `cache: "no-store"`, and corporate-node holds no cache. Verified end
to end on DEV — an admin `POST /assessment/assignSubscription` changing a
type's limit was visible on the very next read of both corporate-node and the
BFF.

The staleness was in the browser. `useUsageQuota` fetched once on mount, so an
admin editing the subscription in ANOTHER tab left the widget showing the cap
it had read when the page loaded — indistinguishable, to the recruiter, from
the platform ignoring the edit. It now also re-reads on `visibilitychange`,
i.e. when the tab comes back to the front.

Two ways an admin edit still legitimately shows nothing, both by design:

- **Types outside the corporate six.** `app/api/assessments/usage/route.ts`
  filters the backend catalogue through `isCorporateAssessmentType` and
  recomputes `used`/`total` from what survives, so editing `Cognitive`,
  `Tech_MCQ` or `Tech_Coding` counts can never move this card.
- **Unlimited types.** `is_unlimited` rows report `total: null` and render
  `∞`; their stored `token_limit` (1000 on every DEV row) is inert, so editing
  the number changes nothing on screen.

Two admin-side traps found while tracing this:

- `POST /assessment/assignSubscription` has `isPrivate: true` **commented out**
  in admin-node `app/routes/assessment.js` — it is unauthenticated, so anyone
  who can reach the admin API can rewrite any corporate's or college's
  subscription. Same for the neighbouring `featureAccess` and
  `getCorporateCompaniesByCity` routes.
- Editing a limit without also setting the contract window renews THAT row's
  `start_date`/`end_date` to now + `durationDays` (365). Only the changed row
  moves, so a corporate's types drift onto different expiry dates and the
  card's "ending on" (the latest `end_date`) jumps with them.

## Export Sheet

The roster's bulk-bar Export Sheet streams the SAME Excel the admin side
produces: `GET /corporates/:id/assessments/v2/:id/candidates/export` proxies
admin-node's `/assessment/exportStudentData` with `entityType=corporate`.
Columns: Session Name, Name, Email, ID, Phone, Sent/Start/End dates, Status,
Delivery Status, Delivery Issue, Overall Score, Verdict (plus a % column per
type on a Mix & Match float). It replaced a CSV the browser built from whatever
the table happened to be showing.

**Proxied, never called from the browser** — that admin route's `isPrivate` is
commented out, so it is unauthenticated and would export any assessment it was
asked for. `resolveParts` proves the float belongs to the caller first; another
corporate's id 404s (verified on UAT).

**Pass `status=sent`, not the upstream default of `completed`.** The default
silently drops everyone who has not finished — on a 3-candidate float on UAT it
returned 2, omitting the candidate sitting at 0% that the roster plainly lists.
`sent` is the bucket the v2 roster shows, so the sheet matches the table.

**The export is narrowed to the selected rows.** The browser sends the checked
candidate emails as `selectedEmails`; the BFF and corporate-node pass that JSON
list to admin-node, which intersects it (case-insensitively) with the already
tenant-guarded `sent` roster before it builds the workbook. The toast reports
the exported selection count. Omitting `selectedEmails` preserves the existing
full-roster export for other callers.

**Communication exports include both the assigned target and the result.**
`Assigned CEFR Level` is the level used to create the candidate's paper;
`CEFR Level` is the achieved level calculated from the candidate's enabled
communication sections. The Excel writer must trust the section-aware CEFR
already produced by `getAssessmentDetails`; re-checking a fixed Speaking +
Reading + Listening trio incorrectly blanks the result for assessments where
one of those sections is disabled.

**A Mix & Match float carries the CEFR pair too (DEV + UAT, 2026-09-08).** A
float has no single assessment type, so the export's per-type column chain is
skipped entirely and its Communication part came out as a bare
`Communication %` — the level the result is actually read as was missing. The
workbook now appends `Assigned CEFR Level` / `CEFR Level` for every
communication-type part of a float, after the per-part % columns. Detection
mirrors the per-type chain's own fallback (anything that is not Behaviour /
Aptitude / Role_Based / Custom / AI_Interview), so a Hinglish part keeps its
CEFR as well; when a float somehow holds more than one such part the headers are
prefixed with the part name.

The assigned level is read from the candidate's `assessment_sets.cefr_level`,
now joined into `getStudentAssessmentScores`'s per-assignment query and stamped
on the report ABOVE its early return for unscored rows — so it exports for
candidates who have not attempted the part yet, matching the standalone
Communication export. That join also replaced a redundant per-candidate
`findUnique` for the same column. The achieved level is the part report's own
section-aware `cefrLevel`, so a float and the part's standalone export always
agree (verified on real UAT floats: assigned `A2` → achieved `A1`, and pending
rows showing the assigned level with `-`).

**A zero section no longer erases a real level (DEV + UAT, 2026-09-08).**
`getAssessmentDetails` and `getStudentAssessmentScores` blank the achieved CEFR
whenever ANY enabled section scored 0. The candidate's own PDF report, the
corporate dashboard and `corporate-node/helpers/communicationCefr` do not — they
band the attempt's score against the CEFR of the SET it sat. So a UAT candidate
who scored 83% Listening and 85% Writing but 0 on Reading and Speaking (33.76%
overall on a B1 set) read as **A1** on every screen and exported as `-`.

The Excel writer now bands a scored attempt itself, through admin-node's own
`mapCEFRBasedOnQuestionSetAndScore` — the same table those surfaces use — for
both a float's communication parts and a standalone Communication sheet, so the
two can never disagree. It only falls back to that when the upstream level is
blank, so an ungated level still wins. `-` now means exactly one of two things:
the set has no `cefr_level`, or the attempt has no score. The level is never
guessed.

Consequence worth knowing: an attempt scored **0** now bands as A1 rather than
`-`, because that is what the dashboard and the PDF already show for it.

The admin-side assessment-details table still applies the zero-section gate and
will keep showing `-` for these candidates; only the export was changed.

**The Status column speaks the roster's words (DEV + UAT, 2026-09-08).** The
sheet labelled the not-yet-started bucket `Pending`, while every v2 dashboard
chips that same candidate as `Not started` — the row read as two different
states depending on where you looked at it. The export's four labels now match
the chips exactly: `Completed` / `In progress` / `Dropped off` / `Not started`.
Bucket membership is untouched (only the wording), and the export's
completed-only test keys off the same constant so score cells do not shift with
it. The legacy v1 institute and admin candidate lists still say "Pending";
every current app says "Not started". Nothing parses these strings back — the
ATS drive-stage labels in `corporate-node/helpers/evaluationAssessmentOverlay`
are an unrelated vocabulary.

**Deployment correction (2026-09-08):** this feature spans all three services.
The first promotion moved only admin-node, which added the workbook column and
server-side intersection but left the live browser unable to send
`selectedEmails`. The complete DEV/UAT deployment includes corporate-react-v2
(selection query), corporate-node (forwarding), and admin-node (filtering +
workbook). After deploying all three, a real DEV Communication export from a
three-candidate roster with one selected produced one data row and included
both CEFR headers.

## Candidate drawer — General Details and Proctoring

Both tabs render REAL columns only, via
`GET /corporates/:id/assessments/v2/:id/candidates/profile`. Until 2026-09-07
they rendered stand-ins: the mobile was a hash of the email formatted as a
plausible `+91 9…`, and Current location / Highest qualification / Graduation
year were one hardcoded `"Bengaluru, Karnataka / B.Tech, Computer Science /
2025"` shown for EVERY candidate. The whole Proctoring tab was synthesized,
down to a summary claiming *"the candidate switched tabs twice and lost webcam
focus once"* — something a recruiter could reject a candidate over.

Sources, all nullable so the UI shows a dash rather than an invention:

| field | source |
|---|---|
| mobile | `student_personal_profile.contact_number` |
| location | `corr_city` + `corr_state` |
| qualification | `current_course.degree` + `department` |
| graduationYear | `current_course.ended_on` |
| proctoring | `assessment.proctoring_reports` (band, score, summary, timeline) |

**Coverage is genuinely sparse and that is the honest picture** — UAT: mobile
11%, city 5%, degree 9%, and 475 of 782 submitted corporate attempts (61%) have
a proctoring report at all. The stand-ins were filling ~80% of it with fiction.

Three data traps, all live in this data:

- `ended_on` is epoch MILLIS of an **IST wall-clock** date and every Postgres
  here runs `TimeZone=UTC`, so reading the year without
  `AT TIME ZONE 'Asia/Kolkata'` buckets a 2027 batch as 2026 — it differs on
  ~half of UAT's rows. See [[passing-year IST off-by-one]].
- `ended_on = 0` means "not set" (1,819 rows) and renders as **1970**; junk
  years exist too (UAT holds a **3989**), so the year is range-guarded.
- **20%** of non-empty `contact_number` values are a bare `"+91"` with no
  number, so a mobile needs ≥10 digits to count as one.

A failed fetch is rendered as "could not be loaded", NOT as "no details on
file" — a network error is not a claim about the candidate's record.

## Candidate reminders ("Nudge")

The roster's bulk bar sends the SAME reminder the admin side sends:
`POST /corporates/:id/assessments/v2/:id/candidates/reminders` proxies
admin-node's `POST /assessment/sendReminders` with `entityType: "corporate"`.

**Proxied, never called from the browser.** That admin route has `isPrivate`
commented out, so it is unauthenticated and will mail any address in the
`selectedStudents` array it is handed. Two guards run in corporate-node first:

- `assertCorporateScope` proves the float is the caller's (another corporate's
  id resolves to nothing and 404s).
- `getPendingRecipients` intersects the requested emails with THIS float's
  pending roster, so a corporate cannot use its assessment as a mail relay and
  cannot chase someone who already finished. An empty intersection returns 200
  with `sent: 0` rather than an error.

Mix & Match needs nothing extra: given the GROUP id the upstream resolves the
parts itself (`mixMatchPartMapIds`) and sends ONE email naming only the parts
the candidate has not finished, instead of one mail per part.

`resendInvites` is the sibling endpoint (same payload shape). **Wired 2026-09-07**
(was a stub toast). The BFF (`POST /api/assessments/:id/candidates/resend`)
proxies it the same way Nudge is proxied, behind `assertOwnsAssessment`.

**`selectedStudents` is a FILTER over admin-node's own `droppedOff` list, not
the set of people to mail.** `resendInvitesToStudents` only ever resends to
candidates it already classifies as dropped off (attempted, then abandoned —
`Assessment.js` `droppedOff` builder). Selecting someone who has not started
yet intersects to nothing and the call answers `successCount: 0` with "No
dropped candidates found to resend invites to" — 200 OK, zero mail sent. The
BFF passes admin-node's real `successCount` through rather than echoing the
size of the selection, and the UI says so explicitly when it is 0, pointing at
Nudge instead. **Resend and Nudge are not interchangeable**: Nudge reaches
anyone still pending, Resend only reaches candidates who dropped mid-attempt.

## Year-on-year panel: an empty series blanked the whole dashboard

**Fixed DEV + UAT 2026-09-07.** Landing on `/v2/dashboard` as a corporate with
no scored attempts threw `TypeError: Cannot read properties of undefined
(reading 'value')` and the error boundary replaced the ENTIRE dashboard with
"Something went wrong".

`yoy` is always a one-element array, but its `series` is built by skipping every
year without a scored attempt — so a corporate that has never had one gets a
series carrying **zero points**. `YearOnYear`'s `if (!series.length) return null`
guard only covers the OUTER array, so that payload reached the map, where
`pts[pts.length - 1]` is undefined.

**It was not an edge case: 15 of 25 UAT corporates** — every one yet to have a
submitted attempt, which includes every brand-new customer on their first login.

Guarded on BOTH sides on purpose: corporate-node no longer emits a series with
no points, and the component filters them before rendering, so a stale bundle
cannot reproduce the blank page. A chart with no data must degrade to a hidden
panel, never a dead screen.

## Attempt status on the roster (DEV + UAT, 2026-09-07)

The detail roster carries `attemptStatus` — `pending` | `inProgress` |
`dropped` | `completed` — rendered as a **Status** column and used to gate both
bulk actions. Send Reminder targets `pending` only, Resend Assessment `dropped`
only; each disables at zero and carries its count in the label, so a recruiter
sees what a click will reach instead of reading "sent to 0" afterwards.

It is counted off `assessment_assigned_students.status`, **the same enum
admin-node switches on** (`Assessment.js` categorises DROPOUT/INPROGRESS/
COMPLETED/PENDING off that column, falling back to a 20-minute rule only when
it is null). Deriving it in the UI instead is what the old code did — it keyed
on `fit`, a PERFORMANCE band whose `notAttempted` value also covers a drop-off,
so reminders were offered for candidates who had already started.

Two traps, both found against real UAT rows:

- **Derive it from the status enum, not from attempt flags.** The roster query
  counts `dropped_parts` / `inprogress_parts` / `completed_parts` off
  `aas.status` for exactly this reason. Historically this was derived from a
  `parts_submitted` column built on `submitted OR attempted`; since a DROPOUT
  row carries `attempted = true`, `parts_submitted = parts_held` held for a
  candidate who dropped *every* part, which labelled all 219 UAT dropouts
  "Completed". The overview query now exposes `parts_attempted` and
  `parts_completed` separately — `completed` uses the latter, `started` the
  former.
- **`dropped` outranks everything**, and partial progress is `inProgress`, not
  `pending`. One UAT candidate holds 5 parts as COMPLETED+DROPOUT, and 76 hold
  COMPLETED+PENDING — calling the latter "not started" invites a reminder they
  have already acted on.

UAT corporate rows: PENDING 5398 / COMPLETED 594 / DROPOUT 219 / INPROGRESS 4.

## The closing countdown counts in the unit that is left (DEV + UAT, 2026-09-08)

The amber caution line under **Valid till** — on the assessments list and on the
dashboard's Active Assessments schedule — was
`Math.ceil(ms / 86_400_000)` days. Every window still open therefore rounded up
to at least a day: an assessment closing in **five minutes** said `1 days left`,
the same words as one closing tomorrow evening, and a recruiter deciding whether
to chase anybody read a day of slack that did not exist.

`timeLeftLabel(iso, now)` in `lib/assessments/format.ts` now renders it: days
while there are whole days, hours inside the last day, minutes inside the last
hour, `"Less than a minute left"` below that, and **null once the window has
closed** (which also removed the `0 days left` a just-lapsed row used to show,
since `Math.ceil` of a small negative is `-0`). Rounded DOWN at every step —
understating what is left is the safe direction for a deadline. `1 day left` is
also no longer written `1 days left`.

**`daysUntil` is unchanged and still decides WHETHER to warn** (`<= CAUTION_DAYS`,
5). Rounding up is right for that bucket and wrong only for the words a
recruiter reads — the two questions are now answered by two functions.

Both rows re-read the clock **once a minute**; they used to read it once on
mount, which a minutes-granularity label makes visibly wrong on a tab left open.
The clock is still read only after mount (never during SSR) or the prerender
would bake in the build's date and mismatch on hydration.

Verified against the deployed UAT bundle with the browser's clock frozen, on a
real float closing at 21:36 IST: 5 min before → `5 minutes left`, 59 min →
`59 minutes left`, 30 s → `Less than a minute left`, 1 min after the end → no
countdown at all. On the real clock, DEV showed `4 hours left` and UAT
`2 hours left` for floats that both used to say `1 days left`.

## The detail roster is loaded IN FULL, not one page (DEV + UAT, 2026-09-08)

Everything that narrows the detail page's roster — the search box, the Filter
panel, the levels doughnut's multi-select, the sortable columns and the row
counts — is **client-side**, over the rows `useAssessmentDetail` holds. It held
`page=1&limit=100`. corporate-node clamps `limit` to 100
(`Math.min(100, ...)` in the handler, correctly), so on a **999-candidate float
on UAT** (and a 1,000-candidate one on DEV) all of those controls were quietly
answering about the top 100 by average score: searching for a candidate ranked
650th returned "No candidates match this search", and a level wedge counted a
tenth of the roster.

The hook now walks the remaining pages behind the first and merges them:

- The first page still paints immediately; the rest arrive behind it (10 pages
  ≈ 20s on UAT for 999 candidates) — verified headlessly against
  `corporate.uat.pluginlive.com`: 10 requests, all 200, 999 rows in the table,
  no page errors, and a page-7 candidate now found by search.
- **Sequential**, not parallel: each page is a grouped scan plus its per-type
  and proctoring lookups upstream.
- Capped at **50 pages (5,000 candidates)** so a future huge roster cannot turn
  one page visit into a thousand requests.
- Keyed on a run counter, so a fill still in flight cannot append its rows onto
  a different assessment's roster after a navigation or a retry.
- While it fills, an empty result reads "Still loading the roster…" rather than
  "No candidates match this search" — the second is a claim about the roster
  that cannot be made until all of it is held.

The KPI cards and the doughnut's own totals were never affected: they come from
`/overview`, which aggregates server-side over every candidate.

## The roster carries the candidate's mobile (DEV + UAT, 2026-09-08)

The Add-candidates drawer lists the standing roster beside the queue with the
same three columns, but the feed had no mobile for the third — the roster query
selected name and `student_id` off the student-profile lateral and nothing else,
so every row read an em dash.

`getCandidates` now returns one, through `CANDIDATE_MOBILE_SQL`:

- **The number given on THIS invite wins** over the student profile's. It is
  the more specific fact and often the only one there is — a candidate a
  corporate invited by email may never have built a profile. Same precedence
  admin-node's report query uses.
- **A bare country code is not a phone number.** 20% of UAT's non-empty
  `contact_number` values are junk like `"+91"`, so the same `>= 10 digits after
  stripping non-digits` rule the candidate drawer applies decides what counts.
- The candidate drawer's own Mobile now reads the invite's number too (scoped
  to this float's parts), so the row and the drawer it opens cannot disagree.

Coverage is genuinely sparse: 861 of 4,218 corporate roster emails on UAT (20%),
33 of 3,514 on DEV.

## List order

The assessments list is ordered **newest-created first**, on
`COALESCE(created_at, start_time) DESC`. `created_at` was added part-way
through `assessment_corporate_map`'s life: 521 of 902 UAT rows are NULL and
every one predates the earliest real value (latest such `start_time`
2026-08-13, earliest real `created_at` 2026-08-14), so the fallback orders the
backfill era among itself and keeps it below everything with a true creation
date rather than collapsing most of the list into one NULLS-LAST blob. DEV has
no NULL rows. The client re-sorts on the returned `createdAt`; it previously
sorted by end date, which buried a newly created assessment with a distant
window.

## Promote corporate-node WITH corporate-react-v2 (UAT, 2026-09-08)

The detail roster crashed to the bare full-page **"Something went wrong"** on
UAT while DEV was fine, for one reason: `corporate-node` was one commit behind.
That commit adds `proctoring` to each roster row; without it the key is absent
entirely, and the table's guard read

```tsx
{c.proctoring === null ? <dash/> : <chip cls={PROCTORING_CHIP[c.proctoring].cls}/>}
```

`undefined` is not `null`, so the guard misses, `PROCTORING_CHIP[undefined]` is
`undefined`, and `.cls` throws **during render**. Nothing in the assessments
segment has an `error.tsx`, so a render throw goes all the way to
`app/global-error.tsx` — which replaces `<html>` and paints the shell-less
"Something went wrong / Try again" page. That blank-looking error is the
signature of a render-phase throw, NOT of a failed fetch; a failed fetch shows
an in-shell "We could not load…" state instead.

Two rules follow:

- **These two deploy together.** The v2 frontend is a BFF over corporate-node;
  shipping the frontend to an env whose corporate-node is older ships a
  contract mismatch. Check `git log origin/UAT..origin/Development` in
  `corporate-node` before deploying `corporate-react-v2`.
- **Index the chip maps, do not assert them.** Render only when the value is
  present AND known to the map (`c.proctoring && PROCTORING_CHIP[c.proctoring]`),
  falling back to the em dash. `ATTEMPT_STATUS_CHIP[c.attemptStatus]` in the
  same row is still an unguarded lookup — one unknown enum value from the
  backend takes the page down the same way.

## List state survives a detail-page round trip (DEV + UAT, 2026-09-08)

Opening an assessment and coming back used to drop the recruiter on a
freshly-mounted list: tab back to **All**, filters and search cleared, the
infinite-scroll reveal snapped to the first batch, scrolled to the top. On a
filtered, scrolled list that reads as the work being thrown away.

`assessments/_hooks/assessmentsListPersistence.tsx` holds a snapshot of
view (assessment-wise / candidate-wise), status tab, search, filter state, the
infinite-scroll reveal count **per view**, and the scroll position. Three
things about it are load-bearing:

- **It is not React state.** The snapshot is a plain mutable object behind a
  stable ref; `useAssessmentFilters` and `AssessmentsView` read it once via lazy
  `useState` initializers and write back in effects. A scroll-position write
  must not re-render the list it is scrolling.
- **It is scoped to `assessments/layout.tsx`, not the app shell.** That scope
  IS the reset behaviour: navigating to Dashboard or Roles unmounts the
  assessments segment and the snapshot goes with it, so coming back later
  starts clean. `/v2/assessments` ⇄ `/v2/assessments/[id]` stays inside the
  layout and keeps it. There is no reset code.
- **`useInfiniteScroll` skips its reset-to-page-size effect on the mount run.**
  That effect fires on mount like every effect; without the guard it stamps the
  restored reveal count straight back down to `PAGE_SIZE` before the browser
  paints. The hook takes an optional `persist` handle
  (`{ initialLimit, onLimitChange }`) — absent everywhere else it is used.

Earlier shapes of this hook crashed the list into the error boundary's
**"Something went wrong"**. The provider hands consumers a *stable* value whose
`snapshot` getter only reads `.current` later, from an effect or a lazy
initializer — never during a render. Touching the ref during render, or handing
down a fresh object each render, is what breaks it.

## Candidate PDF report

The detail drawer's download serves the **same PDF the admin side does**:
`corporate-node` proxies student-node's `POST /students/assessments/generatePDFReport`.
Proxied, not called from the browser, because that endpoint is unauthenticated
and the tenant guard must run first. It is rendered on demand (~10s), one PDF
per submitted part.

### Custom has no PDF — its report is the Excel sheet

`generatePDFReport` branches per assessment type (behavior, communication /
hinglish, aptitude, role-based, ai_interview) and **throws
`Unsupported assessment type: custom_assessment`** for Custom. The platform has
never rendered a Custom PDF; student-node's own `checkReportAvailability`
returns `available: false` for `Custom_Assessment` outright, which is why the
admin dashboard greys the button out for it.

Corporate v2 did not apply that rule, so the drawer's menu listed Custom
alongside the other parts and picking it surfaced as a **502 "Failed to fetch
the report"** — an infrastructure-shaped error for something that simply does
not exist. Because "Download all reports" stops at the first failure and the
parts are ordered by `at.type_name` (**Aptitude → Custom_Assessment →
Role_Based**), the parts queued behind Custom never downloaded either: a
"3 PDFs" click delivered one.

Fixed 2026-09-08 (DEV + UAT; PROD pending):

- `corporate-node` `downloadCandidateReport` rejects `type=Custom_Assessment`
  with a **404** naming the sheet, and drops Custom from the untyped path too,
  so a Custom-only candidate 404s instead of being silently handed a different
  part's PDF via `targets[0]`.
- `corporate-react-v2` `ReportDownloadMenu` routes the Custom row to
  **`GET /candidates/export?selectedEmails=["<email>"]`** — the existing
  admin-node `exportStudentData` proxy, whose float export carries a
  `Custom Assessment %` column — and saves it as `.xlsx`. Rows name their
  format (`PDF` / `Excel`) only on a mixed float, and the footer reads
  "N files" rather than "N PDFs" when the two are mixed.

Verified on UAT against a live Aptitude + Role_Based + Custom float: Custom
→ 404, Aptitude → 240 KB PDF, Role_Based → 169 KB PDF (the part that used to be
lost), Excel → 7 KB xlsx, untyped → the Aptitude PDF.

### A drop-off with nothing scored says so, and does not block the other parts

The same shape of bug as Custom above, from the other direction. A candidate who
walked out of a part before anything was scored still had that part offered in
the menu; asking for it made student-node render a PDF it had no scores for, it
threw, and corporate-node's catch answered **502 "Failed to fetch the report"** —
an outage-shaped error for an ordinary state. And because "Download all" stopped
at the first failure, the part that DID have a report never downloaded: on the
UAT float `Reg details (Apt & Comm)`, candidate `jershini.y+ohufwrgg@…` (both
parts DROPOUT — Aptitude unscored, Communication scored) got nothing at all.

**Submission is not the test — being SCORED is.** A drop-off is scored (the
dropout cron writes scores and leaves `submitted = false`), so a scored drop-off
has a real report and always did.

Fixed 2026-09-08 (DEV + UAT; PROD pending):

- `corporate-node` `getReportTargets` carries a `renderable` flag per part,
  mirroring student-node's own `checkReportAvailability`: not Custom, attempted
  or submitted, and `scores_calculated` — with AI Interview's fallback of "a
  finalized `ai_interview_scores` row exists", because that PDF renders straight
  off the score row and the flag can lag. Mirrored as SQL rather than asked over
  HTTP because that endpoint is JWT-private and corporate-node holds no student
  token; SOURCE OF TRUTH is `student-node app/handlers/common.js`.
- `downloadCandidateReport` 404s an unrenderable part with the REASON — "did not
  finish X, and the attempt was never scored" or "X is still being scored" — and
  the untyped path now picks the first part that HAS a report rather than the
  first part.
- The BFF (`/api/assessments/[id]/candidates/report/download`) passes a 4xx
  message through instead of flattening every 404 to "No report available for
  this candidate".
- `ReportDownloadMenu`'s "Download all reports" treats a 404 as a skip, keeps
  going, and reports what it skipped ("Downloaded 1 of 2. No report for
  Aptitude."). A real failure still stops the run.

Verified on UAT with that candidate: Aptitude → 404 + reason, Communication →
353 KB PDF, untyped → the Communication PDF. Same on DEV against float
`c7da1478…`. The "still being scored" wording has no data to exercise it on
either env (no `submitted = true, scores_calculated = false` rows).

## Bulk report bundle — every selected candidate's PDF, zipped

The bulk-bar's "Download Performance Report" used to write a **CSV of the
drawer's numbers**. A recruiter forwarding a candidate's performance sends the
report, so they went back and fetched the PDFs one at a time afterwards. Since
2026-09-08 (DEV + UAT; PROD pending) it queues the **real PDF reports** for the
whole selection and returns one zip — a folder per candidate, one PDF per
assessment type they attempted, so a Mix & Match float yields both their
Communication and their Aptitude report.

**It lives in `admin-node`, not `corporate-node`.** admin-node owns the
`assessment` schema, the BullMQ workers, the archiver bundle pattern
(`exportInstitutesBundle`), the OCI storage helper and the mail relay.
corporate-node reading `assessment.*` for this would have been cross-service
database access, and it had to re-derive "which parts does this float have" to
do it.

| Piece | Where |
|---|---|
| Start | `POST /assessment/reportBundle` `{corporateId, assessmentId, emails[]}` -> `{exportId, topic, reportCount, candidateCount, deliverTo, skipped[]}` (202) |
| Status | `GET /assessment/reportBundle/:exportId?corporateId=` |
| File | `GET /assessment/reportBundle/:exportId/file?corporateId=` -> a **signed 5-minute URL**, not the bytes |
| Progress | the EXISTING `GET /events/subscribe?topic=report-bundle:<exportId>` |
| Queue / worker | `report-bundle` (`app/queues/setup.js`), `app/queues/reportBundleWorker.js` |
| Record | Redis hash `report-export:<exportId>`, 24h TTL |

### One export is one BullMQ flow

A `render` child per PDF under a single `bundle` parent. BullMQ will not run the
parent until every child has finished and hands it their return values via
`getChildrenValues()`, so **"are all the PDFs done" is not bookkeeping this code
does** — a counter of our own would be the same idea with our own races.

Children return object-storage **keys, never PDF bytes**: a job's return value
lives in Redis, and a large export as base64 would be hundreds of MB of it. Each
child uploads its part under `report-bundles/<exportId>/parts/`; the parent
streams them into the archive (`zlib level 0` — the entries are already
compressed PDFs) straight into a multipart upload, then deletes the parts.

A child that exhausts its retries **returns** `{failed}` rather than throwing:
a thrown final attempt fails the flow parent, which would discard every other
candidate's report over one that would not render.

### Delivery: mail unless downloaded

There is no "watch or email?" choice for the caller. Fetching the file marks it
collected; a **delayed job** (60s) emails a signed, 7-day link if nothing ever
did. An earlier cut tracked live viewers to decide, and a pod dying with a
stream open would have suppressed the mail **forever** — a failure that loses
the user's work and logs nothing.

The recipient is the **address on the JWT**, never the request body: otherwise a
valid session is a way to have a bundle of candidate reports mailed anywhere.

`ReportBundleDialog` (corporate-react-v2) counts the reports as they land and
names which way the zip is coming — keep it open and the browser downloads it,
press **"Email it to me instead"**, close the tab, or pass the 3-minute ceiling
and the mail takes over. It flips to the mail wording the moment that becomes
true, and names the address rather than implying one. The export keeps running
server-side whatever the dialog does.

### The selection is uncapped

A whole roster is a legitimate ask; the queue is what makes it safe. Every
render is a **Puppeteer page inside student-node** — the same process serving
candidates who are mid-assessment — so `REPORT_BUNDLE_CONCURRENCY` (default 3)
is a **safety limit, not a throughput dial**. A large export is slow, not
dangerous, and arrives by email, which is the right shape for work that takes an
hour. Set `RUN_REPORT_BUNDLE_WORKER`-style gating per pod if PROD ever needs to
keep total render concurrency below what student-node can absorb.

### Gotchas

- **Progress events carry counts only.** `/events/subscribe` is topic-based and
  **unauthenticated**, so no email, name or score is ever published on it. The
  BFF builds the topic itself and never accepts one from the client — passing a
  caller-supplied topic through would let a recruiter subscribe to an admin's
  assignment-job stream.
- **The login JWT carries no email — the delivery address comes from the BFF.**
  `createLoginToken` (user-management-node) signs exactly
  `{ role, _id, corporate_id | institute_id | student_id }`. The first cut read
  `res.locals.user.userEmail` and so refused **every real session** with "this
  session has no email address on it" (fixed 2026-09-08, DEV + UAT). The
  corporate BFF now resolves it with `lib/api/creatorEmail` — token first, then
  the auth service's profile for that `_id`, the same resolver behind
  create-assessment and add-candidates — and passes `requestedBy`. It travels in
  the body because admin-node has no other way to learn it, but it is
  server-derived, so the browser still cannot choose where a bundle of candidate
  reports is mailed. An address that cannot be resolved is refused up front:
  the fallback delivery IS the email.
- **Ownership is enforced in the BFF**, via `assertOwnsAssessment` — the same
  boundary the assessment-creation routes use, because admin-node's
  `/assessment/*` endpoints are admin-scoped by design.
- **Redis pub/sub has no replay.** A small export can reach READY before the
  browser's stream is open, so the client also probes
  `GET .../report/exports/:exportId` once on attach.
- **Custom and never-attempted candidates** are named with a reason in
  `skipped-candidates.csv` inside the zip, so a short bundle explains itself
  rather than leaving a recruiter to count 7 PDFs against 10 ticked rows.
- **admin-node UAT has its own Redis** (`172.17.0.1:6379`) while DEV points at
  `129.154.231.72:6377`, so the unnamespaced `report-bundle` queue name cannot
  collide across environments the way corporate-node's queues would (those use
  `QUEUE_ENV` because DEV and UAT share one Redis).

## Tenant scoping

`verifyToken` proves the JWT is signed; it does **not** check that
`:corporateId` is the caller's. `app/helpers/assertCorporateScope.js` does, and
every one of these handlers calls it first (403 on mismatch). Every other
`/corporates/:corporateId/*` route in the service still has that gap — worth a
separate audit.

## Loading states

Every screen (dashboard, assessment-wise, candidate-wise, and the per-assessment
L2 detail page) shows **skeleton loaders**, not text. Two rules make them worth
the code:

- The skeleton reuses the **real structural classes** — `.kpi-grid`/`.kpi`,
  `.panel`, `.aa-split`, `.rail` on the dashboard; the real `<table class="ma-tbl
  ma-tbl--assessments">` shell on the lists. Only the content atoms become
  `.skeleton` spans. So the card chrome, the grid and the fixed column widths are
  already final and nothing reflows when data lands.
- `CockpitSkeleton` must carry `data-block="attempt"|"competency"|"yoy"`. That
  attribute is what the rule `.content-col > [data-block=…] { grid-column: span 1 }`
  keys off. Without it those blocks inherit `grid-column: 1 / -1`, render
  full-width, then re-flow into pairs — the exact shift the skeleton exists to
  prevent.

Counts that are not known yet shimmer rather than render `0` (status tabs, type
legend, candidate total, the `Updated` stamp). A `0` and "we have not loaded it"
look identical, and the first claims the corporate has nothing.

Two gotchas found building this:

- `.cal` (the rail's mini calendar) sits on `--bg-surface`, which is **also the
  `.skeleton` base colour** — placeholders inside it vanish into one solid grey
  block. `dashboard.css` steps the ramp up inside `.cal` only.
- The DS `.skeleton-overlay` is `position: absolute` and collapses to a strip
  with no real layout behind it. These skeletons are deliberately **in-flow**
  instead.

The L2 detail page (`assessments/[id]/_components/DetailSkeleton.tsx`, wired in
`AssessmentDetailView` where a one-line "Loading assessment…" panel used to be)
follows the same rule: it renders the real `PageHeading` band, the four-card
`.kpis` row and the `.panel.ad-merge` card with its `.aa-split` donut/roster
halves, with only the content atoms as `.skeleton` spans. Its sizes live in
`assessment-detail.css` under `.ad-sk-*`.

One difference from the list screens' `TableSkeleton`: the roster's **column
headers are skeleton blocks, not real labels**. The detail table's columns
depend on the assessment's own types (one "Overall Performance" column for a
single-type assessment, one per type for a mix-n-match float), and the types are
exactly what is still being fetched — naming them would be a guess that reflows
half the time.

## Deploy

- `corporate-node` → `./auto_deploy.sh corporate-node UAT` (docker, container `corporate`).
- `corporate-react-v2` → systemd `:3014`; build **on the box** (`npm run build`),
  then `sudo systemctl restart corporate-react-v2`. **`rm -rf .next` first if a
  route was deleted since the last build.** `next build` does not prune a
  removed route's artifacts, so an incremental build over a deletion leaves a
  route entry whose client reference manifest is gone and that path answers
  **500, not 404** (`InvariantError: The client reference manifest for route
  "…" does not exist`). Hit exactly this on DEV after the report-v2 revert. Needs `CORPORATE_API_URL`
  in `.env.local` pointing at that env's corporate-node.
- `corporate-react` → `./auto_deploy.sh corporate-react UAT`. **Must be built on
  the UAT box**: env values are inlined at build time, so a DEV-built bundle
  sends UAT users to DEV. Verify with the DEV-URL grep in
  [v2-strangler-fig.md](./v2-strangler-fig.md).
- DB: one expression index, `student.student_personal_profile
  (LOWER(TRIM(primary_email)))` — the join every candidate view makes. 82ms →
  32ms on DEV. Applied DEV + UAT; **PROD pending**. See DB-Scripts
  `Corporate Assessment Dashboard/20260825T173221Z__spp_email_lower_trim_index.sql`.

## Status

DEV and UAT: live. PROD: not deployed, and the index is not applied there.

**2026-09-07** — the corporate-v2 assessment work was promoted to UAT (27
commits: the create-assessment wizard, the Manage/Cancel/Share detail actions,
Add-candidates from the detail page, and a batch of validation fixes). Rules
worth knowing from that batch:

- **`cancelled` is now a REAL corporate status.** The detail page has a Cancel
  action and the list has its own Cancelled tab, so it must appear in the status
  filter. `draft` is still unreachable — a corporate assessment does not exist
  until it is floated — and remains filtered out.
- **`min`/`max` on a number or date input is advisory in this wizard.** It
  advances on a button click, not a form submit, so the browser never runs
  constraint validation: a negative question count, a 0-minute exam and a
  back-dated start all had to be enforced in code. `isTypeConfigValid` is, per
  its own docstring, the ONLY gate between the config panels and a floated
  assessment — anything a panel exposes has to be range-checked there.
- **Optimistic roster rows must reconcile on the lowered email.** The roster is
  grouped by it upstream (`getCandidates`), so concatenating an optimistic row
  onto the fetched list showed the same candidate twice, and Total Candidates
  counted both, until a refresh corrected it.
- **The report-v2 pages stay reverted.** `reportRouteFor` /
  `REPORT_ROUTE_BY_TYPE` were dropped with them; `hashSeed` lived in that block
  and is still needed by the dummy candidate fields, so it survives on its own.
  Both promotions conflicted here — resolve by keeping the routing OUT.

**2026-09-01 (latest)** — the candidate drawer's download button now lets the
recruiter **pick which report**. The PDF is rendered per ASSIGNMENT, so a Mix N
Match float has one per submitted part, and the endpoint falls back to
`targets[0]` from a query ordered by `at.type_name` when no `?type=` is given.
On a Communication + Aptitude float that is always Aptitude, and the
Communication PDF was unreachable from the UI. One part still downloads on a
single click; several open a menu of the parts plus "Download all reports",
fetched SEQUENTIALLY because each PDF is rendered on demand (~10s) and firing
them together turns one click into several concurrent render jobs. `?type=`
matches the RAW column value, so the display name's spaces go back to
underscores ("AI Interview" -> "AI_Interview").

**Stacking trap:** the menu is portaled to `<body>` and must out-stack the
drawer it opens from. `.acct-menu` (the container it reuses) sits at
`--z-overlay` (50) because the sidebar's account menu has nothing above it, but
`.drawer-sheet` uses a **raw** `z-index: 69` and its panel is opaque, so the
menu first shipped rendering at the correct coordinates *underneath* the drawer
and clicking Download looked like nothing happened. `--z-tooltip` (70) is the
only token above that raw 69. Anything else portaled out of a drawer has the
same trap — `.batch-pop` (ValuePopover) is still at 50 and would be invisible
if it were ever used inside one.

**2026-09-01** — "Mix N Match" is now a real option in the Filters
panel's **Assessment type** list, not just a legend entry. The legend had been
counting multi-type floats with their own colour swatch while the filter offered
only the four real types, so there was no way to narrow to them. It is a
sentinel value (`MIX_MATCH_FILTER_VALUE`, deliberately not a real type name so
it cannot collide with `a.types`) that the predicate reads as
`types.length > 1`; Assessment-wise view only, because `mixMatchCount` is
undefined in the Candidate-wise view.

**2026-09-01 (later)** — the candidate report drawer build-out and the whole
`/v2/reports/*` report-v2 section were **reverted from DEV and UAT** on request
(6 revert commits, tip `43cd239`). Those routes now 404 by design. The work is
preserved in full on branch **`feat/candidate-report-drawer-report-v2`**, which
also carries two later Mix N Match fixes that never reached Development/UAT.
Re-landing it is not a plain merge: git will not reapply a commit the target has
reverted, so merge that branch **and then revert the reverts**.

**2026-09-01** — counts aligned to admin v1 and both missing score breakdowns
shipped (DEV + UAT). Verified against meesho on UAT, which now matches the
admin screen exactly: **11 active / 160 sent / 48 taken / 67 candidates**.
Same release adds the Aptitude + Communication "Assigned level", and promotes
the trimmed sidebar (Dashboard · Assessments · **Back to ATS**) that brings
corporate v2 to parity with the institute TPO shell. Corporate's back link
targets `v1("/dashboard")`, not `v1("/")` like institute: corporate-react's
`AuthRouter.js` redirects `/` to `/signin` unconditionally, so bridging to the
root bounces a signed-in recruiter to the login screen.

UAT now carries open assessments (288 floats, 9 active as of 2026-08-31), so
the schedule's week view populates. The earlier "Nothing open" state was the
data being stale, not a bug.


## Creating an assessment — the float wizard

*(LIVE on DEV + UAT since 2026-09-05.)*

`/v2/assessments/new` is a 4-step wizard (Setup → Configuration → Send →
Review and Float), a port of admin-react-v2's float flow. The **UI shipped
before the backend did**: for a while every one of its BFF routes was a dummy
stub returning fixed data. They are now wired to the real service.

**No new backend was written.** The wizard reuses admin-node's `/assessment/*`
endpoints verbatim — the same ones admin-react-v2's wizard calls — rather than
duplicating several hundred lines of assign/provision/invite logic into
corporate-node-v2:

| BFF route (`corporate-react-v2`) | admin-node endpoint |
|---|---|
| `GET /api/entities/assessment-types` | `getSubscribedAssessmentByCorporate` + `getInstituteSubscriptionQuota` |
| `GET /api/assessments/aptitude-topics` | `getAptitudeTopics` |
| `POST /api/assessments/ai-interview/suggest-parameters` | `/ai-interview/suggest-parameters` |
| `POST /api/candidates/parse-sheet` | `parseCandidateSheet` |
| `GET/POST /api/entities/recipient-lists` | `getStudentLists` / `saveStudentList` |
| `POST /api/assessments/mix-match` (the float) | `createSectionquestions` (Custom only), then `assignMixMatchAssessment` |

### Why a corporate JWT is allowed to call admin-node

`assignMixMatchAssessment` is `isPrivate: true` — it needs *a* valid PluginLive
JWT, but has **no per-entity role check**; it reads `entityType`/`entityId`
from the request BODY. A corporate recruiter's token is a valid token, and on
both DEV and UAT **`corporate-node`'s `LOGIN_SECRET_KEY` and `admin-node`'s
`JWT_SECRET_KEY` are the same secret**, so it verifies.

Because admin-node trusts the body, **the BFF is the security boundary**: every
route above derives the corporate from the forwarded JWT
(`corporateIdFromRequest`) and pins `entityType: "corporate"`. The browser
sends a stand-in `entityId` of `"me"`, which is ignored for scope — a recruiter
cannot float for another corporate.

**Auth asymmetry worth knowing:** corporate-node verifies `issuer`/`audience`
(`pluginlive.com`); admin-node does not pass those options at all. A token
minted without `iss`/`aud` works against admin-node but 401s on corporate-node
with `jwt audience invalid`.

### Corporate floats only

`broadcast` and `recurring` schedules are college-only
(`unschedulableSelectionReason` refuses any non-college segment), so the wizard
never offers them here. `mix-match` implements only the one-time corporate path
and rejects the other two explicitly, since the draft is client input. There is
no degree/department cohort — a corporate candidate needs none.

### Config gotcha — `ADMIN_API_URL`

The wizard needs **`ADMIN_API_URL`** in `corporate-react-v2`'s environment
(DEV `https://api-admin.dev.pluginlive.com/`, UAT
`https://api-admin.uat.pluginlive.com/`). It lives in `.env.local`, which is
**gitignored** — so it does NOT arrive with a branch merge and must be set on
each box by hand. Without it every wizard route 502s and the log says
`ADMIN_API_URL is not configured`. This is exactly what happened on the first
UAT rollout.

### Known parity quirk

admin-node answers the float with **`mixMatchGroupId`**, but
`StepReviewAndFloat` reads `result.groupId` for its redirect, so the `groupId`
query param is never set. Harmless (the confirmation dialog keys off
`floated`/`name`/`count`) and **admin-react-v2 behaves identically** — parity,
not a regression.

### The float confirmation is one-shot (DEV + UAT, 2026-09-08)

After a float the wizard hard-navigates to
`/v2/assessments?floated=1&name=&count=…` and the list opens the "<name>
created" dialog off those params. They used to be stripped only when the
recruiter dismissed the dialog, which left `floated=1` sitting in that history
entry — so opening a row and pressing Back, refreshing, or reopening the tab
all replayed a confirmation over a list already read. It hit new corporates
hardest: floating is the first thing they do, so that URL is the entry they
keep returning to, while anyone arriving from the sidebar gets a clean URL and
never sees it.

`AssessmentsView` now consumes the notice ONCE on arrival — reads the params
into state and `history.replaceState`s them off the entry immediately — so the
dialog renders from state and there is nothing left in the URL to replay.
`history.replaceState`, not `router.replace`: the page arrives via a full
document load and replacing to the same pathname never propagated to
`useSearchParams`. admin-react-v2's `ManageAssessmentsView` still has the
original URL-driven version and the same replay exposure.

### Ports differ per environment

`corporate-react-v2` listens on **:3012 on DEV** but **:3014 on UAT** (where
:3012 is `institute-react-v2`). nginx `corp-react.conf`'s `location /v2`
proxies to the right one; check the unit's `Environment=PORT` before curling a
box directly.


## Managing a floated assessment (LIVE on DEV + UAT, 2026-09-07)

The detail page's write actions all go to admin-node's `PUT /assessment/details`
(the one exception is Add candidates, which uses `addStudentsToAssessment`).
Every one of them takes the **mix-match group id** — what this page calls the
assessment id — and applies across every part of the float.

| Action | Endpoint |
|---|---|
| Add candidates | `POST /assessment/addStudentsToAssessment` |
| Manage — name, end date/time, proctoring | `PUT /assessment/details` |
| Remove Candidate | `PUT /assessment/details` `{removeAssignedIds}` |
| Cancel assessment | `PUT /assessment/details` `{endTime: now, closeNow: true}` |

**The BFF is the tenant boundary.** admin-node reads the float id straight off
the request body and does NOT check who owns it — it was built for admins, who
legitimately act on every entity. So every corporate write first passes
`assertOwnsAssessment()`, which re-reads the assessment through corporate-node's
corporate-scoped overview. A foreign id 404s.

### Cancelled is its own status (DEV + UAT, 2026-09-07)

Cancelling closes the window — but so does a natural expiry, so the dates alone
cannot tell the two apart and a cancelled float used to read as **Expired**.
A nullable **`cancelled_at`** on both assessment map tables now records the
intent alongside the effect (DB-Scripts
`Corporate Assessment Cancellation/20260907T111359Z__assessment_map_cancelled_at.sql`;
DEV+UAT applied, **PROD pending — apply it BEFORE deploying corporate-node there,
or `statusOf` selects a column that does not exist**).

admin-node stamps it when `closeNow` is used; corporate-node's `statusOf` checks
it first and returns `"cancelled"`. Wired through all four readers (list, detail,
dashboard) so the status cannot disagree between screens, and the list has a
**Cancelled** tab that self-disables at zero.

**No backfill.** Rows cancelled before the column read NULL and keep saying
Expired.

### Reopen has to CLEAR the cancellation (DEV + UAT, 2026-09-08; PROD pending)

Reopening a cancelled assessment did nothing you could see. The call returned
`{ok: true}`, the end date moved — and the assessment stayed **Cancelled** on
the list, in the header and on the dashboard, while a candidate opening the
invite was still told *"This assessment has been cancelled and is no longer
available."*

Two separate holes, both in `PUT /assessment/details`:

1. **`cancelled_at` was never cleared.** `closeNow` stamps it (above) and
   nothing unstamped it. `statusOf` answers `"cancelled"` off that column
   **before it compares any dates**, and student-node's `assignmentWindowState`
   reports `cancelled: cancelled_at != null` — so no amount of moving the window
   could undo it. There is now a `reopen: true` flag, the mirror of `closeNow`,
   which sets it back to NULL. Explicit rather than implied by a new window, so
   an ordinary Manage save on a cancelled assessment cannot silently un-cancel
   it (verified: a plain PATCH leaves it Cancelled).
2. **`startTime` was accepted by every caller and applied by none.** The Reopen
   dialog and the Manage drawer both send it; it was neither declared in
   `updateAssessmentDetailsSchema` nor destructured in
   `updateEditableAssessmentDetails`, so a reopened assessment kept the start it
   was cancelled with. It is now applied on the same wall-clock convention as
   `endTime` (a date with no time means the START of that day, mirroring its
   end-of-day default), and the end-after-start check compares against the start
   being set in the same call rather than the stored one.

Verified on a real cancelled float on both environments: `cancelled` →
`scheduled`, the start actually moves, `cancelled_at` is NULL on every part, and
student-node then tells the candidate *"This assessment opens on 12 Sept 2026,
9:00 am IST"* instead of the cancellation notice. The corporate BFF's
`/reopen` route sends `reopen: true`; nothing else does.

| Action | Endpoint |
|---|---|
| Reopen assessment | `PUT /assessment/details` `{startTime, endTime, reopen: true}` |

### Cancel means the window closes

There is no `cancelled` column anywhere on the assessment maps, so cancelling
moves the float's end time to now. That is also exactly what stops candidates:
student-node re-checks the window in `getAssessmentQuestions` and answers
**410 `ASSESSMENT_WINDOW_CLOSED`**, so starting, resuming and stale open tabs
are all refused, and the float drops out of the candidate's active list.

Two backend fixes were needed to make it honest:

- **admin-node `closeNow`** — the existing guard rejects `endTime <= startTime`,
  so an assessment cancelled BEFORE it started could only get a one-second
  window. `closeNow:true` opts out of that guard; ordinary edits keep it.
- **corporate-node `statusOf` precedence** (`helpers/corporateAssessmentSql.js`)
  — it asked "starts later?" before "already ended?", so a float cancelled
  before its start still read `scheduled`. Ended is checked first now.

**Known gap:** `submitAssessment` is NOT window-gated, so a candidate who
already had the questions loaded can still submit that in-flight attempt. This
is pre-existing — the same is true of any assessment whose window simply
expires mid-attempt.

### Expired keeps Manage (DEV + UAT, 2026-09-08)

The detail page used to hide Share AND Manage together once a float was
"closed" — where closed meant completed, cancelled, OR expired. That's wrong
for expired: admin-node's `updateEditableAssessmentDetails` deliberately
allows moving `endTime` to a future date on an expired float (past end dates
are intentionally editable; the only guard is `newEnd > startTime`, `closeNow`
bypasses that), so expired is the one closed state that is still recoverable —
and the Manage drawer's End date field is the only UI that can reach it. A
recruiter with an expired float and unfinished candidates had no path back in.

Frontend now splits what was one `closed` boolean into two:

- **`finished`** — completed, cancelled, or cancel-in-flight. Genuinely done;
  no verb reopens it. Neither Share nor Manage renders.
- **`closed`** — `finished` OR expired. Share, Add candidates and Cancel all
  still gate on this (a link into a shut window, or adding candidates to one,
  is still wrong).

Only Manage gates on `finished` instead of `closed`, so it alone survives into
the expired state, and `ManageDrawer`'s `editable` prop follows it (`!finished`,
was `!closed`) so the End date field is actually writable when it renders. A
contextual hint appears in the drawer only when editing an expired assessment
("Moving the end date past today reopens it…"). Purely a frontend gating
change — no new endpoint, no schema change.

### No mail leaves a closed window (DEV + UAT, 2026-09-08)

`helpers/assessmentInviteEmail.js` refuses **every** candidate-facing send once
the assessment's deadline has passed:

```js
if (deadlineResult?.expired) return false;   // sendAssessmentInviteEmail
```

`sendFloatInvites` treats that `false` as "skip this candidate", so a reminder
or resend on an expired float walks the whole roster, mails nobody and returns
`successCount: 0` — a plain zero with no reason attached.

The detail page used to report that zero as **"No reminders sent — everyone
selected has already attempted it"**, with a *Not started* candidate visible in
the same table. Nobody had attempted anything; the window was shut. Two fixes:

- **Both mail actions disable once the window shuts** (expired OR cancelled —
  cancelling moves the end time to now), and their tooltips name the closed
  window and point at the end date in Manage, which is what reopens the float.
  A doomed send no longer leaves the browser.
- **Where a zero can still arrive**, the toast reports what is known instead of
  asserting a cause: "already attempted" is claimed only when the client can
  see it is true (`nudgeCount === 0` / `resendTargets.length === 0`).

**Resend was the worse half of the same bug.** `resendInvitesToStudents` runs
with `deferEmail: true` and resets each part's attempt state BEFORE
`sendFloatInvites` is called — so on an expired float it wiped a drop-off's
attempt, then the mailer refused, then the toast said nothing had happened. The
UI gate closes that path, but **the endpoint itself is still unguarded**: a
direct call to `/assessment/resendInvites` on an expired assessment will still
reset attempts and mail nobody. A backend guard is the remaining work.

Guarded by `scripts/check-closed-window-mail-actions.mjs` (16 checks).

### Status vocabulary: Upcoming and Finished (DEV + UAT, 2026-09-08)

`scheduled` IS "Upcoming" — the state already existed under a scheduling name,
so it is relabelled rather than joined by a second status. `displayStatus()`
derives Live from it once the start instant passes, because nothing server-side
flips the stored value at that moment; `now` is passed in as a parameter so the
server's clock never renders into HTML the browser then disagrees with.

**"Completed" is now "Finished"** in the chip, the status label and the list's
tab strip. Chip hues moved with it: Live is info blue plus the red "right now"
dot, Finished takes the green Live used to wear, Upcoming is brand/accent,
Expired grey, Cancelled red. Every hue is a chip class, so it stays a token
lookup.

The **Overall Performance and time-taken columns are gone** from the candidates
table, the CSV export, the list's band filter and the candidate drawer's KPI —
header and cell commented out together, with the `score` / `time` sort keys left
wired in `sortValue` so restoring a column is an uncomment rather than a
re-derivation. Communication's breakdown now reads by competency area
(Reading / Writing / Listening / Speaking) instead of by question type.

### What is NOT editable

**Per-assessment validity.** It lives on `assessment_schedules`, i.e. on
recurring schedules, and a one-time corporate float has no schedule row to hold
it. The field on the Manage drawer is vestigial for corporate.

Proctoring IS editable: `allow_proctoring`/`allow_verification` are plain columns
on the map row, so they ride the same `updateMany` as the end time and therefore
work for a mix-match float — unlike admin-node's `configuration` patch, which
only runs for a single-part assessment.

## Public assessment link — Share (LIVE on DEV + UAT, 2026-09-07)

Share hands out a **candidate** link, not the recruiter's dashboard URL:

```
https://assessment.<env>.pluginlive.com/candidate-assessment-journey/v2?publicToken=<jwt>
```

The candidate opens it, types their own email, gets a one-time code and lands on
the assessment — no account. Everything after the email box is the existing
emailed-invite flow, untouched.

| Endpoint (admin-node) | Auth |
|---|---|
| `POST /assessment/public-link` | private — recruiter mints the link |
| `POST /assessment/public/resolve` | **public** — names the assessment |
| `POST /assessment/public/join` | **public** — email in, invite token out |

- The link is a **signed token naming the float**, not a raw id, so it cannot be
  forged from an assessment id, and it is minted with the time left on the
  assessment window so it can never outlive the door it opens. No schema change.
- **Join is find-or-create**: reopening the link or retyping the same address
  does not assign the same person twice, which keeps the roster honest and stops
  refreshes from burning quota. Joining also re-checks the window, so a
  cancelled or finished assessment refuses new joiners.
- Join happens on **submit, not on open** — a link that enrolled everyone who
  merely opened it would fill the roster with people who never took the test.

**Residual risk to accept:** anyone holding the link can enrol themselves and
consume assessment quota. There is no join cap or domain restriction yet.

**Fixed 2026-09-07 — 404'd for most single-part assessments.** All three
endpoints resolve the float by querying `assessment_corporate_map` on
`mix_match_group_id`. That column is only populated for a **multi-part float**;
a single-part corporate assessment is identified by its bare
`assessment_corporate_map_id` instead (`corporate-node`'s
`corporateAssessmentSql.js` picks between the two on purpose — its own `:id`
resolver already accepts either). Matching the group id alone made the window
query return an all-NULL row for every single-part assessment, which the
handler read as "not found" — **635 of 895 corporate assessments on UAT**, i.e.
Share worked only for the multi-part floats it happened to be built and tested
against. All three lookups (`publicLinkWindow`'s mint/resolve path and
`joinPublicAssessment`'s `findAssigned`) now match on EITHER id. DEV + UAT.

### Config + deploy traps

- **`ADMIN_API_URL` is gitignored** and does NOT ride a branch merge. It is
  needed by BOTH `corporate-react-v2` (`.env.local`) and `assessment-react-v2`
  (`.env.prod`, baked into the image) and must be set by hand on every box.
  Without it the wizard routes 502 with `ADMIN_API_URL is not configured`.
- **Ports differ per env:** `corporate-react-v2` is **:3012 on DEV** but
  **:3014 on UAT** (where :3012 is institute-react-v2). Check the unit's
  `Environment=PORT` before curling a box.
- `assessment-react-v2` on both boxes is a **docker container**
  (`candidate-assessment-journey-v2`, :3015), not systemd.
- A Fastify request's `headers` is a prototype getter, so `{...req}` silently
  drops it. Build synthetic requests field by field — this broke public join's
  student provisioning with `headers.authorization` undefined.


## Candidate drawer — what is real and what is not

Only the **email** and the score KPIs (overall performance, level, time taken)
come from real data. Everything else in that drawer is synthesized:

- The whole **Proctoring** tab (`dummyProctoring`) — the tick, "No concerns" and
  every count is derived from a hash of the candidate id. Real proctoring signals
  exist (`assessment.proctoring_events`, `proctoring_reports`) but this tab does
  not read them. A recruiter is currently told an attempt was clean when nothing
  checked it.
- General Details' location, qualification and graduation year. Agreed sources
  when it is wired: `student_personal_profile.corr_city`, and
  **`student.current_course`** (`degree`/`department`, `ended_on` for the year).

**Notice period and current/expected CTC were removed outright** — neither has any
source for an assessment candidate. Notice period exists only on
`drive_role_candidate_map` (an ATS drive context) and CTC has no column anywhere
in the `student` schema, so the drawer was showing invented numbers.

### UAT reverted this drawer — mind the merge

UAT carries a deliberate revert of the candidate report drawer
(`43cd239 Revert "feat(candidate report drawer): … Performance/Proctoring tabs,
report-v2"`), and `src/app/reports/**` does not exist there. A Development→UAT
merge that resolves `CandidateReportDrawer.tsx` to the branch puts the tabs back
over that revert — and if `assessment-detail.css` or `src/lib/assessments/report.ts`
resolve to the reverted side, the markup ships with no rules or missing helpers.
That is exactly how the Proctoring tab shipped with an unconstrained tick filling
the card.

**A clean `tsc` does not catch this — CSS has no type checking.** When resolving a
component to one side of a merge, take its stylesheet and its helpers from the
same side, and check whether the target branch reverted the feature first.

### Deploy trap: a locked `.next` fails the build silently

`next build` on the UAT box compiled and typechecked, then died with
`ENOENT … .next/required-server-files.json`, leaving `.next` without a `BUILD_ID`.
`auto_deploy.sh` restarted the service onto that partial output and reported
success, so every BFF route answered **500** while the unit read `active`.
Fix: `systemctl stop corporate-react-v2 && rm -rf .next && npm run build && systemctl start`.
Always check `.next/BUILD_ID` exists after deploying this app.


## Schedule page — window and Mix & Match (DEV + UAT, 2026-09-07)

`/v2/schedule` reads `dashboard/v2/schedule?from=&to=`.

**Rows show the open date only (2026-09-08).** Briefly showed both ends
(`<starts> → closes <ends>`, 2026-09-07) so the open date wasn't only inferable
from the day-group a row sat under — but the close date is already carried
twice over, by the row's own status chip (Live/Completed/Expired) and by the
day groups the float spans, so spelling out both ends made the one date a
recruiter scans for compete with one they can already infer. Rows now read
`Starts <date>` — labelled, not bare, because a multi-day float repeats under
every day heading it covers (`coversDay`, `lib/schedule/dates.ts`), so an
unlabelled date next to a day heading it doesn't start on would be ambiguous
about which end of the window it is.

**A multi-part float is named Mix & Match.** It previously borrowed its first
type's name and hid the rest behind `+N more`, so a Mix & Match read as an
Aptitude test that happened to have extras, and the legend — built from
`items.flatMap(i => i.types)` — had no way to surface one at all. A float of
several assessments is ONE sitting for the candidate, so it is now labelled as
one, carries a neutral dot (picking one constituent type's colour is what caused
the confusion) and has its own legend entry and filter.

`MIX_TYPE` (`schedule/_constants.tsx`) is a **shape, not a type name** — there is
no "Mix & Match" row in `assessment_type`, so it cannot collide with a real one;
its filter selects `types.length > 1`.

Deliberate: the per-type legend rows still count a mix float under EACH
assessment it contains, so "how many floats include Aptitude" stays true. Mix &
Match adds a way to find them rather than moving them — no existing count shifts.
