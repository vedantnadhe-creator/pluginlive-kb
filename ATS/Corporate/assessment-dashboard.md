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
- **"Taken" means `submitted OR attempted`** — the same rule admin v1 uses
  (student-node `TpoDashBoard.getAssessmentStatesForCorporate`, which admin's
  corporate drill-down calls, counts `attempted`). v2 counted submitted-only
  until 2026-09-01 and therefore read LOWER than the admin screen for the same
  corporate: meesho/UAT showed 40 against admin's 48, the gap being exactly its
  DROPOUT rows (opened the paper, walked away). One shared `TAKEN_PREDICATE` in
  `helpers/corporateAssessmentSql.js` governs every v2 count.
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

**The export cannot be narrowed to selected rows.** The upstream takes a status
bucket plus an optional `searchQuery`, not a list of people, so Export Sheet
covers every candidate on the assessment however many rows are ticked. The
toast says so.

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

- **Do NOT derive it from `parts_submitted`.** That count uses
  `TAKEN_PREDICATE` (`submitted OR attempted`) and a DROPOUT row carries
  `attempted = true`, so `parts_submitted = parts_held` holds for a candidate
  who dropped *every* part. Testing that first labels all 219 UAT dropouts
  "Completed".
- **`dropped` outranks everything**, and partial progress is `inProgress`, not
  `pending`. One UAT candidate holds 5 parts as COMPLETED+DROPOUT, and 76 hold
  COMPLETED+PENDING — calling the latter "not started" invites a reminder they
  have already acted on.

UAT corporate rows: PENDING 5398 / COMPLETED 594 / DROPOUT 219 / INPROGRESS 4.

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

## Candidate PDF report

The detail drawer's download serves the **same PDF the admin side does**:
`corporate-node` proxies student-node's `POST /students/assessments/generatePDFReport`.
Proxied, not called from the browser, because that endpoint is unauthenticated
and the tenant guard must run first. It is rendered on demand (~10s), one PDF
per submitted part.

## Tenant scoping

`verifyToken` proves the JWT is signed; it does **not** check that
`:corporateId` is the caller's. `app/helpers/assertCorporateScope.js` does, and
every one of these handlers calls it first (403 on mismatch). Every other
`/corporates/:corporateId/*` route in the service still has that gap — worth a
separate audit.

## Loading states

All three screens (dashboard, assessment-wise, candidate-wise) show **skeleton
loaders**, not text. Two rules make them worth the code:

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

**Rows show both ends of the window.** They used to show only `closes <date>`,
so the day an assessment OPENED could only be inferred from which day-group the
row sat under — and not at all for a float spanning several days, which is most
of them. Rows now read `<starts> → closes <ends>`.

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
