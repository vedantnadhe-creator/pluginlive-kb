# Admin Assessment Workflow

> All admin-facing assessment management is handled by the `Assessment` class in `admin-node/app/models/Assessment.js` (13,739 lines, 105 methods). This covers the full lifecycle: dashboard stats, listing, assignment, communication, reporting, proctoring review, student list management, subscriptions, and analytics.

---

## File Reference

**Primary File:** `admin-node/app/models/Assessment.js`

---

## Dashboard & Counts

These are the top-level stats shown on admin dashboards.

| Function | Purpose | Supports |
|----------|---------|--------|
| `getTotalCollegeCount(entityType)` | Count of all active institutes in `institutes_campuses` | college, corporate |
| `getTotalCompanyCount(entityType)` | Count of all active corporates | corporate |
| `getActiveAssessmentCount(entityType)` | Count of institute/corporate assessment maps where `end_time >= now` | college, corporate |
| `getAssessmentSentCount(entityType)` | Total number of student assignments created (across all assessments) | college, corporate |
| `getAssessmentCompletedCount(entityType)` | Count of assessment maps where `end_time < now` | college, corporate |

---

## Assessment Listing

### `getActiveAssessments({ pageNo, pageLimit, searchBy, order, sort, type_name, isSubscribed, isTrial, states, cities, entityType, instituteId })`

Lists all **currently active assessments** (end_time >= now) for the admin dashboard.

**Returns per row:**
- `id` — assessmentInstituteMapId
- `assessmentType`, `assessmentName`
- `assessmentSent`, `assessmentCompleted` — student counts
- `collegeName`, `collegeLogoUrl`, `collegeCity`, `collegeState`
- `assessmentSubDate`, `endDate`
- `subscription_type` — subscribed / trial
- `allowProctoring`, `allowVerification`
- **College branch only (added July 2026 for the Active Assessments "Add Candidate" action):** `scheduleId` (`aim.schedule_id` — non-null ⇒ the row is one run of a schedule), `instituteId` (`aim.institute_id`), `instituteCampusId` (`MIN(ic.id)` — aggregated so the `GROUP BY` cardinality is unchanged). These are SELECT-only additions (no DB migration). The frontend uses `scheduleId` to gate a schedule-info confirmation dialog and `instituteId`/`instituteCampusId` to feed the Add-Candidate drawer's degree picker. Unquoted aliases fold to lowercase in the raw result and are re-mapped to camelCase in the `formattedData` loop. The **corporate branch was not changed** — its row `id` is already `assessment_corporate_map_id`, which is all the corporate Add-Candidate path needs.

**Filters:**
- `searchBy` — searches assessment name + college name
- `type_name` — filter by assessment type
- `states`, `cities` — comma-separated geographic filters
- `isSubscribed`, `isTrial` — subscription type filters
- `instituteId` — filter for a specific institute
- `sort` (`asc`/`desc`) + `order` — sort field. Recognised `order` values: `endDate`, `startDate`, `assessmentName`; **any other value (the frontend sends `createdAt`) falls through to the creation-time branch** `COALESCE(aaudit.createdat, <map>.start_time)`. **Default is `order=createdAt`, `sort=desc` → newest-created first** (set July 2026; was `endDate`/`asc`). The admin-react default lives in the `SubscribedInstitutes.filters` reducer (`order: 'createdAt', sort: 'desc'`), which always wins over the `?? 'createdAt'` fallback in `fetchActiveAssessments`.
  - **Creation time comes from the `assessment_audit` join, not the map table.** `assessment_institute_map`/`assessment_corporate_map` have **no `created_at` column** — the created timestamp is `assessment_audit.createdat`, reached via `<map>.audit_id → assessment_audit.audit_id`. Both branches `LEFT JOIN assessment.assessment_audit aaudit` (corporate branch got this join + `COALESCE` fallback in July 2026 to match the college branch, which already had it).
  - **`audit_id` is nullable** (older rows created before the audit table was wired). For those, the sort `COALESCE`s to `start_time`, so created-time ordering is exact for rows with an audit link and start-time-approximate for the rest. PROD footprint at rollout: college ~3.4% of active rows null-audit; **corporate ~55%** null-audit (so corporate created-sort ≈ start-time sort until backfilled). A dedicated `created_at` column on both map tables is planned for a later sprint to remove the audit-join dependency.

**Also returns:** `totalCount`, `subscribedCount`, `trialCount` for tab-level badge counts

**Supports:** College and Corporate (separate query branches)

---

### `getCompletedAssessments({ pageNo, pageLimit, searchBy, order, sort, type_name, isSubscribed, isTrial, states, cities, entityType, instituteId })`

Lists **past assessments** (end_time < now) in the Completed tab.

Same parameters and return structure as `getActiveAssessments`. Separate internal handlers per entity type:
- `handleCollegeAssessments()` — queries `assessment_institute_map`
- `handleCorporateAssessments()` — queries `assessment_corporate_map`

**Sorting differs from Active:** this endpoint **ignores `order`** — both branches hardcode `ORDER BY <map>.end_time ${sort}` (only `sort` asc/desc is honoured). So the shared `createdAt` default (from the `SubscribedInstitutes.filters` reducer) has **no effect on the Completed tab** — it stays end-date-ordered. Only the Active tab respects the `createdAt` created-time default.

---

### `getAssessmentDetails({ assessmentInstituteMapID, entityType, filters, pageNo, pageLimit, searchQuery, paginate })`

The most complex admin function — fetches the **student-level details** for a specific assessment.

**Purpose:** Powers the assessment detail/drill-down page, showing each assigned student with full status, scores, and profile info. Used for **all non-scheduled types** (Role_Based, Custom, Behavior, AI_Interview, technical, and one-time communication/aptitude) on both admin-react and institute-react.

**Filters available:**
- `degree`, `department`, `specialization` — education filters. **Matched case-insensitively** (`UPPER(COALESCE(cc.degree, ep.degree)) IN (...)`): the option lists from `getDomain`/`getDegree`/`getDepartment`/`getSpecialization` come back UPPER-cased, while stored course data is mixed-case, so a plain `IN` matched nothing.
- `status` — array of `COMPLETED` / `INPROGRESS` / `PENDING` / `DROPOUT`. Applied in SQL (mirrors the displayed-status derivation: raw `aas.status` enum first, then `submitted`/`attempted` fallback for legacy rows) so paginated counts stay correct.
- `CEFR` — filter by assigned CEFR level (communication)
- `aptitude_level` — filter by student aptitude level
- `assessment_intitude_map_id` — sub-map filter
- `consistency.assessment_type` + `consistency.level` — filter by attendance pattern (`highConsistency >= 80%`, `moderateConsistency 60–80%`, `inconsistent < 60%`)
- `searchQuery` — searches name, email, phone

**Pagination is opt-in (`paginate=true`).** Without it the endpoint returns **every** matching row (all status buckets fully populated) — required by callers that bucket the result client-side (institute-react's status tabs) and by the Excel export. With `paginate=true` (admin-react's `CandidateList` via `fetchStudentsByStatus`) the `sent` bucket is `OFFSET/LIMIT`-paginated and `pagination.totalCount` reflects the filtered total. NOTE: pagination gates on `pageLimit` presence, not truthiness — the old `(pageNo && pageLimit)` check wrongly skipped pagination on page 1 (`pageNo=0`) and returned all rows, which surfaced as "Showing 10 of 10" with no pager on a 15-student assessment.

The per-student `status` field ("Completed" / "In Progress" / "Pending" / "Dropout") is always returned, so the admin-react Status **column** populates for every type (previously empty for one-time/role-based).

**Per-student data returned:**
- Basic: name, email, phone, degree, department, specialization, photo
- Dates: sentDate, startDate, endDate, startedDateTime, droppedOffDateTime
  (see [Drop-off timestamp](#drop-off-timestamp-dropped_at-august-2026) — `droppedOffDateTime`
  is an **ISO instant** from `aas.dropped_at`, or absent. `sentDate` is now per-candidate —
  see [Sent date](#sent-date-created_at--invite_sent_at-august-2026) — and, like the other
  dates here, ships as a pre-formatted IST string)
- Status: `scoresCalculated`, `assignedCefr`, `resultingCefr`
- **Type-specific scores:**

| Assessment Type | Score Fields |
|----------------|-------------|
| Communication | Per-section scores (reading/listening/speaking/writing), overall CEFR level, dictation score, sentence completion score |
| Aptitude | `overallPercentage`, `criticalReasoningPercentage`, `quantitativePercentage`, `logicalReasoningPercentage` |
| Behavior | `behaviorProficiencies` (by competency), `behaviorScores`, `overallScore`, `keyStrengths` |
| Role-Based | `mcqScore`, `subjectiveScore`, `videoScore`, `overallScore` |
| Custom | Custom assessment report data |

**Also returns:** `totalCount`, `cefrLevel`, `allowProctoring`, `instituteCampusId`, `sections`, assessment start/end times

---

### `exportStudentData({ assessmentInstituteMapID, entityType, status, searchQuery, filters })`

Generates an **Excel (.xlsx) export** of all student data for a given assessment using ExcelJS.
Returns a buffer for download.

**Reflects the on-screen CandidateList filters.** It calls `getAssessmentDetails` **without** `paginate` (so all matching rows are exported, not just the visible page) and forwards `filters` (degree/department/specialization/status, JSON string) + `searchQuery`. `status` selects which bucket to export — the frontends pass `'sent'` (the full list) for non-scheduled types so the export matches the table; status/degree/dept/spec filtering is applied in SQL by `getAssessmentDetails`. (Previously it ignored all filters and exported only the `completed` bucket.)

**Supports:** College and Corporate

**Columns are per assessment type.** A fixed base block (Session Name, Name, Email, ID, Phone, Sent Date, Start Date, End Date, Status, Delivery Status, Delivery Issue) is followed by type-specific score columns, then Proctoring Status when proctoring is enabled.

For **Aptitude**, the first type-specific column is **Time Taken** (`mm:ss`), ahead of Overall % / Critical Reasoning % / Quantitative % / Logical Reasoning %. It is read from `assessment.assessment_assigned_students.total_time_taken` — seconds, stamped by `submitAssessment` in student-node *before* score calculation — selected in both the college and corporate candidate queries and carried through each row as `totalTimeTakenSeconds`. Formatted by the shared `_fmtMmSs()` helper, which renders a **blank cell** (not `00:00`) for anyone who never submitted, so an empty cell means "no attempt" rather than "instant attempt". Same format as the `Time Taken` column in the institute schedules workbook (`_scheduleSheetColumns`).

Other types record time on the same column but do not surface it here; only Aptitude has the export column.

---

## Subscription Management

| Function | Purpose |
|----------|--------|
| `getSubscribedInstitutes({ pageNo, pageLimit, searchBy, order, sort, type_name, isSubscribed, isTrial, states, cities })` | Lists institutes with subscriptions. Deduplicated by `institute_id` using GROUP BY (not subscription_id). Returns aggregated tokens: `SUM(tokens_used)`, `SUM(token_limit)`, `MIN(start_date)`, `MAX(end_date)`. Uses `COUNT(DISTINCT institute_id)` for pagination counts. Also returns `institute_campus_id` for frontend navigation |
| `getSubscribedCorporates(...)` | Lists corporates with subscriptions. Deduplicated by `corporate_id` using GROUP BY (same pattern as institutes). Uses `COUNT(DISTINCT corporate_id)` for pagination counts |
| `getSubscriptionRenewalInstitutes(...)` | Lists institutes whose subscriptions are expiring soon |
| `getSubscribedInstitutesStates()` | All distinct states of subscribed institutes (for filter dropdown) |
| `getSubscribedInstitutesCities({ state })` | Cities within a state for subscribed institutes |
| `getSubscribedInstitutesByCity({ city })` | Institute list for a specific city |
| `getSubscribedAssessmentByInstitute({ institute_id })` | Assessments + subscription info for a specific institute |
| `getSubscribedAssessmentByCorporate({ corporate_id })` | Same for corporate |
| `getSubscribedCorporateStates()` | States for subscribed corporates |
| `getSubscribedCorporateCities({ state })` | Cities for subscribed corporates |
| `getSubscribedCorporateCompaniesByCity({ city })` | Corporate companies by city |
| `assignSubscription(entityId, assessmentTypes, entityType, subscriptionType, tokenLimit, durationDays, accessLevel, practiceDegreeSets)` | Creates or updates a subscription record. Sets per-type `tokenLimit` (via a `tokenLimits` map), `durationDays`, `subscriptionType` (trial/subscribed), `accessLevel`, `practiceDegreeSets`. **Skips the update for any type whose limit/tier is unchanged**, so editing one type's quota no longer rewrites `start_date`/`end_date` for every other subscribed type. |

---

## Assessment Quota Enforcement

Quota is stored per entity **and per assessment type** in `assessment.subscribed_institutes` / `assessment.subscribed_corporates` (`token_limit`, `tokens_used`). `remaining = max(token_limit - tokens_used, 0)`.

- **No subscription row for a type ⇒ unlimited** (all guards are a no-op).
- **`token_limit = 0` ⇒ explicitly blocked** (0 remaining), **not** unlimited. (Previously `0` was misread as unlimited — fixed at all three enforcement sites.)

**Consumption is at ATTEMPT time** — the central gate in student-node (`app/helpers/assessmentQuota.js`) decrements when a student starts a one-time or scheduled assessment. **Practice attempts are never counted.** Role_Based one-time broadcast is the bind-time exception (charged when the set is bound).

**Assign-time pre-flight guard** — `admin-node/app/helpers/assessmentQuota.js` → `assertAssignQuota` throws `QUOTA_EXHAUSTED` (HTTP 400, with structured `code / remaining / required / assessmentType`) when `batchSize > remaining`. It does **not** decrement (the per-student attempt-time cap is the hard limit); it only refuses to over-assign a batch. Wired at every chokepoint, before any rows/jobs are created:
  - `assignAssessment` (all direct types — Aptitude, Communication, Behavior, Custom, …).
  - `assignRoleBasedAssessment` (Role_Based uses its **own** endpoint — it needs its own guard).
  - `AssessmentSetGroupService` (Role_Based async queue, before `createJob`/enqueue).
  - `scheduleAssessment` (schedule creation — rejects immediately instead of failing silently at night).
  - Nightly `AssessmentSchedulerService` (re-checks at trigger time).

**Reading saved quota (prefill on revisit)** — `GET /assessment/getInstituteSubscriptionQuota` returns the stored `token_limit`/`tokens_used` per type. It takes **either** `institute_id` (campus id is resolved to the parent institute) **or** `corporate_id` (used directly — corporates have no campus). Omit `assessment_type` to get all types (`{ quotas[], totalLimit, totalUsed, totalRemaining }`); pass it for a single type. Reads `subscribed_institutes` or `subscribed_corporates` accordingly. (Corporate support was added so the Feature Access screen prefills saved limits/usage on revisit for corporates, not just institutes.)

**Frontend** — admin-react `CreateAssessment` catches the 400 and renders a **"Assessment Quota Exhausted"** popup (`Modal.error`) showing Type / Remaining / Required when `error.code === 'QUOTA_EXHAUSTED'`; a generic error popup otherwise. The Feature Access → institute/corporate screen shows one mandatory per-type limit table (Role_Based merged in) and prefills existing limits/usage on revisit for **both** institutes and corporates.

**Selectable types in Feature Access** — Behavior, Communication, Cognitive, Tech_MCQ, Tech_CODING, Aptitude, Role_Based, Custom_Assessment and **AI_Interview**. The list is declared in **two places that must stay in sync**: the admin-react picker (`AssignSubscription/index.js`, `assessmentTypes` memo) and the **Fastify body schema** `assignSubscriptionSchema.body.properties.assessmentTypes.items.enum` in `admin-node/app/schemas/assessment.js`. Adding a type to the picker alone makes the save fail at the route boundary with `400 FST_ERR_VALIDATION — body/assessmentTypes/<n> must be equal to one of the allowed values`, before the handler ever runs — exactly what happened to AI_Interview (picker updated 2026-08-05, schema enum fixed 2026-08-06, DEV+UAT). **No DB change is involved:** `assessment.assessment_type` is a **table**, not a Postgres enum, it already carries an `AI_Interview` row, and `assignSubscription` resolves types by name with `mode: "insensitive"`, then writes the raw array into `corporate.corporates."subscriptionType"` (jsonb). The schema enum is the only allow-list. `Hinglish` is in the schema enum but deliberately **not** in the picker.

**Known gap — de-selecting a type does not revoke it.** `assignSubscription` only creates/updates rows; it never deletes or expires rows for types the admin un-ticked. Un-ticking a type in Feature Access therefore leaves the `subscribed_institutes`/`subscribed_corporates` row in place and the Create-Assessment picker keeps offering it. Applies to **all** types, not just AI_Interview. A proper fix has to **expire** rather than delete, so `tokens_used` survives.

**Scheduler quota-exhausted alerts** — when the nightly scheduler hits an exhausted quota it emails the schedule creator **plus** all active rows in `assessment.quota_alert_recipients` (`email`, `is_active`) — editable in DB, no code deploy needed. The loader never throws (returns `[]` on error) so alerting can't break a run.

---

## Geographic Filters (for Admin UI Dropdowns)

| Function | Purpose |
|----------|--------|
| `getAllInstituteStates()` | All states with active institutes |
| `getAllInstituteCities({ state })` | Cities in a given state |
| `getAllInstitutesByCity({ city })` | Institutes in a city |
| `getCorporateStates()` | All corporate states |
| `getCorporateCities({ state })` | Cities with corporates |
| `getCorporateCompaniesByCity({ city })` | Corporates in a city |

---

## Assessment Assignment

All assignment functions follow the same pattern:
1. Validate inputs
2. Resolve student data (fetch existing / create new)
3. Create `assessmentInstituteMap` or `assessmentCorporateMap`
4. Create `assessmentSet` + question mapping
5. Create `assessmentAssignedStudent` records
6. Send invitation emails via `StudentService`

### Drop-off timestamp (`dropped_at`, August 2026)

`assessment.assessment_assigned_students.dropped_at` (`TIMESTAMPTZ`, nullable) is the
instant an assignment was flipped to `status='DROPOUT'`. It is the source of the admin
dashboard's **"ASSMT. DROPPED OFF DATE & TIME"** column.

**What it replaced.** Nothing recorded the drop-off moment, so `getAssessmentDetails`
aliased the assessment window's deadline — `aim.end_time` / `acm.end_time AS dropped_at` —
into `droppedOffDateTime`. Every dropped-off candidate on an assessment therefore showed the
**same value, routinely weeks in the future** (invite sent 04 Aug, "dropped off"
02 Sep 11:59 PM). There was no other truth to read: the table has only
`assessment_started_at` / `submitted_at`, `audit_id` is NULL on these rows, and
`candidate_journey_events` records only `assessment_opened`.

**Who writes it** (student-node, all three paths that create a `DROPOUT`):
- `app/handlers/assessmentHandler.js` — reload of a live non-diagnosis attempt.
- `app/handlers/aiInterviewHandler.js` — restart of an already-started AI Interview
  (raw SQL: `SET status = 'DROPOUT', dropped_at = NOW()`).
- `script/updateDropoutStatusCron.js` — the timeout sweep (60 min aptitude / AI Interview,
  22 min everything else). Here it is **detection time**, not the last keystroke.

**Who clears it:** the cron's Assessment #1/#2 reset branch and admin-node's resend-invites
reset (`droppedAt: null` alongside `status: 'PENDING'`), so the timestamp never outlives the
status it describes.

**Two clocks, do not mix them.** `dropped_at` is a **genuine UTC instant**, unlike
`start_time`/`end_time` which store IST wall-clock in a UTC column (next section). The
admin-node container runs in UTC, so `moment().format()` on a real instant prints **IST minus
5:30** — which is why admin-node ships `dropped_at` to the browser as **ISO**
(`app/helpers/candidateTimestamps.js` → `toInstantIso`) and admin-react's
`formatEventDateOnly` renders it in the viewer's zone.

**No backfill.** Rows that dropped out before 2026-08-05 have `dropped_at IS NULL` and
admin-react renders `-`. There is no trustworthy historical source, and inventing one would
re-create the class of bug this removed. Applied DEV + UAT 2026-08-05; **PROD pending**
(`DB-Scripts/Assessment Dropout Timestamp/20260805T120510Z__assessment_assigned_students_dropped_at.sql`).

> Still unfixed nearby: `startedDateTime` is formatted with `moment()` on a real UTC instant,
> so the In-progress "STARTED DATE & TIME" column reads 5:30 behind IST; and the **corporate**
> path builds it from `aas.submitted_at` (aliased `attempted_at`), so it shows the submit
> time, not the start. The college path uses `assessment_started_at` correctly.

### Sent date (`created_at` / `invite_sent_at`, August 2026)

`assessment.assessment_assigned_students.created_at` (`TIMESTAMPTZ`, DB-defaulted `now()`)
and `.invite_sent_at` (`TIMESTAMPTZ`, nullable) are the source of the admin dashboard's
**"ASSESSMENT SENT DATE"** column. Both are per-assignment.

**What it replaced.** `getAssessmentDetails` derived `sentDate` from the assessment's own
`start_time` (`aim.start_time` / `acm.start_time`) — a property of the **map**, shared by
every candidate under it. `addStudentsToExistingAssessment` (see above) maps new students
onto that same `assessment_institute_map_id` / `assessment_corporate_map_id`, so a student
added weeks after the assessment was created still showed the original window start as
their send date. The same field was independently re-derived two more ways in student-node's
`TpoDashBoard.js`: the college-list branch read `assessmentData.createdAt`, a field the model
never had (always `undefined`), and the corporate-list branch fell back to
`startedAt || submittedAt`.

**Who writes `created_at`:** nobody in application code — it is a DB column default, so
every one of the ~19 `assessment_assigned_students` insert sites in admin-node (bulk
`createMany`, single `create`, the raw `INSERT` in `aiInterviewHandler.js`, and the
assignment queue worker) gets it for free.

**Who writes `invite_sent_at`:** `admin-node/app/service/TrackingService.js`
`recordEmailEvent()` — the single chokepoint every invite dispatch already passes through,
for both the email and WhatsApp channels. Stamped only when `category === 'assessment_invite'`
and the send was accepted/delivered; guarded on `invite_sent_at IS NULL` so a reminder or a
re-invite never moves the original date.

**Read order** (`candidateTimestamps.js` → `resolveSentDate`, mirrored in student-node's
`candidateSentDate.js` for the TPO dashboard): `invite_sent_at`, then `created_at`, then the
map's `start_time` — so every row from before this shipped renders exactly as it did before.

**Two clocks, do not mix them** — same convention as `dropped_at` above: `created_at` /
`invite_sent_at` are genuine UTC instants (converted to the IST calendar date for display),
while `start_time` stores IST wall-clock in a UTC column (next section) and is still read
with `moment.utc`.

**Backfill.** Populated only from `email_events` (`category='assessment_invite'`,
`status IN ('accepted','delivered')`) — exact evidence a send happened. Deliberately not
guessed from `assessment_started_at`: for the common case (added at creation, attempted
mid-window) that would replace a correct window-start date with the attempt date, a
regression on far more rows than it would fix. Rows with no `email_events` match stay NULL
and keep rendering the map `start_time`. Applied DEV + UAT 2026-08-06 (10 of 27,489 rows on
DEV, 35 of 20,196 on UAT); **PROD pending**
(`DB-Scripts/Assessment Sent Date Per Candidate/20260806T095536Z__assignment_sent_date_per_candidate.sql`).

### Timezone convention for `start_time` / `end_time` (IST)

The admin picks start/end **date + time in IST**. `assessment_institute_map` and
`assessment_corporate_map` store `start_time` / `end_time` as `timestamptz`, but the
platform does **not** store the true IST instant. The stored convention is
**"IST wall-clock numbers written as UTC"** — e.g. an admin choosing `18:00` is stored
as `…T18:00:00Z`, not `…T18:00:00+05:30`.

This is intentional and **must stay consistent on both sides**:
- **Write** — every assignment path builds the Date with a trailing `Z`
  (`new Date(\`${date}T${time}:00Z\`)`). This applies to all assign flows
  (Communication, Aptitude, Hinglish, Behavior, Role-based, Custom, AI_Interview,
  diagnosis) and to the edit-end-date paths (`updateEditableAssessmentDetails` and the
  schedule-row `updateAssessmentEndDate`, `PUT /assessment/schedule/assessment-enddate`).
  As of June 2026 the edit path **honors an exact end time**: it parses an optional
  `hh:mm[:ss]` component from the incoming `endTime`/`newEndDate` and stores `…T${time}Z`;
  date-only callers still default to end-of-day (`…T23:59:59Z`), so older/other callers are
  unaffected. `updateAssessmentEndDate` got this same treatment in July 2026
  (`hotfix/assessment-tz-sync`) — it previously did `new Date(newEndDate).setHours(23,59,59)`
  in **server-local (IST)**, re-introducing the ~5.5h-early bug for edited schedule runs.
- **Read** — `student-node` `getActiveAssessments` computes `now` via `getNowForDB()`
  = `new Date() + 5.5h`, then compares `startTime <= now` / `endTime >= now`. The +5.5h
  cancels the wall-clock-as-UTC storage, so an assessment opens/closes at the selected
  **IST** time. `institute-node` mirrors this: `StudentListInfo.getschedulesInfo` **and**
  (as of July 2026) `getCorporateAssessmentsInfo` add `+5.5h` (`330 min`) before computing
  Ongoing/Upcoming/Expired status; the admin-node back-assign window
  (`assignStudentsToActiveScheduleAssessments`) also adds +5.5h to its `now+24h` cutoff.

**Gotcha (Communication/Behavior/Hinglish fixed June 2026; Aptitude/Role_Based/AI_Interview
fixed July 2026):** these assign helpers previously built the Date with `+05:30` /
local-time `new Date(y, mo, …)` (true IST instant). Because the reader still added +5.5h,
those assessments **opened and expired ~5.5h early in IST**. The June fix only reached
Communication/Behavior/Hinglish (which share a `formatDateTime(date,time)` `:00Z` helper);
**Aptitude, Role_Based and AI_Interview had no such helper and stayed buggy** — this caused
PROD incidents (Christ University Aptitude, 29 Jun & 6 Jul 2026, expiring at 6:29 PM instead
of 11:59 PM IST). The July 2026 `hotfix/assessment-tz-sync` routed Aptitude (sync+async),
Role_Based (`script/generateRoleBasedQuestions.js`) and AI_Interview (sync+async) through
the same `:00Z` helper. Fix: store as `Z` so all writes match the read-side offset. No
DB/schema change. Rows created *before* the fix remain stored as true-instant and stay ~5.5h
early until re-created — editing the assessment's end date, or `UPDATE … SET end_time =
end_time + interval '5 hours 30 minutes'`, re-writes it under the correct convention.

> Note: this is a fragile "store-as-UTC + read-side +5.5h" convention that assumes the Node
> containers run in UTC and that every reader applies the +5.5h. The durable fix is
> true-instant storage everywhere + a one-time data backfill (deferred — would require a DB
> migration).

### Assessment invite/reminder email date format (July 2026)

The assessment **invite** email (`assessmentStudentCorporate2` in
`user-management-node` `src/utils/emailTemplates/inviteStudent.js`) and the
**reminder** email (`assessmentRemainder.js`) render the `Start Date` / `End Date`
lines. Upstream callers (admin-node broadcast handler, `customAssessment`, the
assignment worker, direct `req.body`) each formatted these differently
(`toLocaleDateString()`, `DD MMM YYYY, hh:mm A`, ISO, …), so the emails were
inconsistent. A shared helper `emailTemplates/formatMailDate.js` now normalizes any
of those shapes — parsed as **UTC** (`moment.utc`) so the wall-clock digits show
verbatim — into **`Do MMMM, YYYY`** (e.g. `7th July, 2026`). Both templates call
`formatMailDate(start_date)` / `formatMailDate(end_date)` at the interpolation point
(single choke point, caller-agnostic). Non-date strings ("No end date",
"Available now") and unparseable values pass through unchanged.

### `assignCommunicationAssessment(create, entityId, name, instructions, assessmentType, startTime, endTime, startDate, endDate, bulkUploadData, email, assessmentDomain, entityType, allowProctoring, cefrLevel, isOneTime)`

- Selects from pool of available question sets matching `cefrLevel` and `assessmentDomain`
- Tracks set assignment per student to avoid repeating sets (`trackSetAssignment`)
- Gets available fresh sets for each student (`getAvailableSets`)
- Handles both Institute and Corporate entity types
- `isOneTime = true` → no schedule linkage
- Creates/updates students that don't exist

### `assignAptitudeAssessment(create, entityId, name, instructions, assessmentType, startTime, endTime, startDate, endDate, assessmentDomain, bulkUploadData, email, entityType, allowProctoring, aptitudeType, aptitudeSubtopics, difficultyLevel, difficultySettings, allowNegativeMarking, isOneTime)`

- Selects questions per subtopic + difficulty from pool
- Supports "pegging" (same student always gets same question set) via `global.peggingMaps`
- Creates main assessment + optionally two diagnosis assessments
- Runs student creation with concurrency control (`runWithConcurrency`)

### `selectAptitudeQuestionsForAssessment(aptitudeTypes, subtopics, difficultySettings, studentEmails, isPegging, excludeQuestionIds)`

- Core question selection logic for aptitude
- Selects only **unassigned** fresh questions per subtopic per difficulty
- Supports pegging: if `isPegging = true`, reuses previously assigned questions for the same student
- Excludes already-used `questionIds`

### `assignBehaviorAssessment(create, entityId, name, instructions, assessmentType, startTime, endTime, startDate, endDate, assessmentDomain, bulkUploadData, email, entityType)`

- Standard behavior assessment assignment
- No question generation required — uses existing behavior question bank

### `assignRoleBasedAssessment(create, entityId, name, instructions, assessmentType, startTime, endTime, startDate, endDate, assessmentDomain, bulkUploadData, email, entityType, allowProctoring, roleName, skills, seniority, jobDescription, industry_domain, generatedQuestions)`

- If `generatedQuestions` is null, calls `generateRoleBasedQuestions()` first
- Delegates to `createRoleBasedAssessment()` in `script/generateRoleBasedQuestions.js`

### `addStudentsToExistingAssessment({ assessmentInstituteMapId, assessmentCorporateMapId, scheduleId, bulkUploadData, entityType, email })`

Adds new students to an **already-live** assessment. Accepts `assessmentInstituteMapId` (one-time), `assessmentCorporateMapId` (corporate), or `scheduleId` (scheduled). At least one is required.

**Two flows based on `is_one_time`:**

#### One-Time Flow (`_addStudentsToOneTimeAssessment`)
1. Gets `assessmentSetId` from existing assigned students
2. Creates/resolves student records in batches of 10 (via `runWithConcurrency`)
3. **`degreeStreamMap` requirement:** student-node's `POST /students` API requires `degreeStreamMap: { degreeId, streamId }` as a **separate top-level body field** (not just inside `currentCourse`). The validation at `common.js:471-528` checks `req.body.degreeStreamMap?.degreeId && req.body.degreeStreamMap?.streamId` and returns 400 if both are missing. The `_addStudentsToOneTimeAssessment` method resolves degree/stream IDs with case-insensitive property access (handles both `DegreeId`/`degreeId` patterns from bulk upload data) and sets `userData.degreeStreamMap` before calling `StudentService.createPublicStudent()`.
4. Batch inserts `assessmentAssignedStudent` records using `createMany({ skipDuplicates: true })`
5. Sends reminder emails (non-critical — failures logged but don't fail the operation)

#### Scheduled Flow (`_addStudentsToScheduledAssessment`)
1. **Duplicate check** — batch raw SQL query checks if students already exist in any non-one-time assessment of the same type
2. **Diagnosis first (atomic)** — sends diagnosis via `_sendDiagnosisForSchedule()` BEFORE any writes. If diagnosis fails, nothing is written (natural atomicity via ordering)
3. **Student list update** — appends new students to `student_lists.students_data` JSON
4. **Active map assignment** — calls `assignStudentsToActiveScheduleAssessments()` to assign students to previously triggered assessment maps with >24 hours remaining before expiry. This step is non-critical (failures logged, don't roll back student list update)

### `assignStudentsToActiveScheduleAssessments({ scheduleId, newStudentsData, assessmentTypeRecord })`

Assigns newly added students to **already-triggered** assessment maps for a schedule. Called automatically after adding students to a scheduled assessment.

- Fetches all `assessmentInstituteMap` records for the schedule where `endTime > now + 24 hours`
- Per map: filters out already-assigned students, gets `assessmentSetId` from existing assignments
- Batch inserts with `createMany({ skipDuplicates: true })`
- Returns `{ assignedCount, mapCount }`

**24-hour filter rationale:** Assessments expiring within 24 hours are too close to deadline for new students to meaningfully participate.

### Frontend: Add Candidate Button

The "Add Candidate" button appears in the **ACTIONS column** of the main assessment table (`UnifiedAssessmentTable/index.js`), NOT in expanded schedule rows.

- Clicking opens `EnhancedBulkUploadDrawer` (reused from create assessment, `mode = 'addCandidate'`)
- Supports manual entry and Excel upload
- Calls `POST /assessment/addStudentsToAssessment`
- Frontend integration in `InstituteAssessmentDashboard.js`

**Three assessment routing paths (institute side):**
- **Standalone/One-time** (`isStandalone || isOneTime || assessmentInstituteMapId`): Passes `assessmentInstituteMapId` in payload
- **Scheduled** (`scheduleId`): Passes `scheduleId` in payload
- **Corporate**: Always passes `assessmentCorporateMapId` directly

The Add Candidate button in `UnifiedAssessmentTable` detects standalone/one-time records and passes `assessmentInstituteMapId` (not `scheduleId`) to the parent's `onAddCandidate` handler.

Supports: Communication, Aptitude, Behavior, Role_Based

---

## Question Generation (Admin-Triggered)

| Function | Purpose |
|----------|--------|
| `generateCommunicationQuestions(cefrLevel, assessmentDomain)` | Triggers `AssessmentSetGenerator` to generate a new communication question set for a given CEFR level |
| `generateAptitudeQuestions({ aptitudeType, aptitudeSubtopics, difficultySettings })` | Calls FastAPI to generate new aptitude questions for given types/subtopics/difficulties |
| `generateRoleBasedQuestions({ jobRole, skills, seniority, jobDescription, industry_domain })` | Calls FastAPI to generate role-based assessment questions. Returns the full question data structure |

---

## Student Communication

| Function | Purpose |
|----------|--------|
| `sendRemindersToStudents(assessmentInstituteMapID, entityType, selectedStudents, bulkUploadData, instituteId)` | Sends reminder emails to unattempted students. Accepts specific student emails or bulk data. Normalizes emails before sending |
| `resendInvitesToStudents(assessmentInstituteMapID, entityType, selectedStudents)` | Re-triggers the invitation email for dropped-off students and resets their attempt (clears answers/scores, status back to `PENDING`). Also hands out a **different assessment set** — but only for question-bank types (Aptitude, Communication, Hinglish, Behavior). `CONFIG_BOUND_SET_TYPES` (AI_Interview, Role_Based, Custom_Assessment) keep their assigned set, because for those the set carries the campaign config (job role, language) — see `Assessment/ai-interview.md` |
| `sendRoleBasedAssessmentEmails(assessmentId, entityType, selectedStudents, bulkUploadData, instituteId)` | Sends role-based specific invitation emails |

---

## Student List Management (CRUD)

Admins can save reusable candidate lists ("Save as List" in the bulk-upload
drawer), referenced by schedules and reusable from "Select from Existing Lists".

**Scoping — a list belongs to an entity, college or corporate.**
`assessment.student_lists` carries both `institute_campus_id` and `corporate_id`
plus `entity_type`. `_resolveStudentListScope({ entityType, entityId, instituteCampusId })`
picks the column: `corporate_id` when `entityType === 'corporate'`, otherwise
`institute_campus_id`. This is the same convention `AssessmentSetGroupService`
uses for role-based set groups, so both writers agree. `entityId` is the
**selected entity's id** (institute id for college, corporate id for corporate) —
not the campus id. Callers may still send the legacy `instituteCampusId` field;
it is treated as a college-scoped `entityId`.

| Function | Purpose |
|----------|--------|
| `saveStudentList({ entityType, entityId, listName, studentsData, createdBy })` | Creates a new saved list, scoped to the institute or the company |
| `getStudentLists({ entityType, entityId, searchQuery })` | Returns the lists for that entity (with search) |
| `updateStudentList({ listId, instituteCampusId, listName, studentsData, updatedBy })` | Updates name and/or student data of an existing list |
| `deleteStudentList({ listId, instituteCampusId })` | Deletes a student list |

Notes / gotchas:
- The persisted student keeps `countryCode` + `phone`. Dropping them silently
  downgrades a reused list's candidates to an **email-only OTP** invite (see the
  `pickPhone` note in `Assessment.js`).
- There is **no unique index** on (scope, `list_name`); duplicates are rejected
  by an explicit lookup returning **409**, not by a constraint violation.
- `deleteStudentList` and `updateStudentList` have **no caller in any frontend**
  and are known-broken (`deleteStudentList` references an undefined `tx`/`listName`
  and has inverted 409/404 logic; `updateStudentList` writes a non-existent
  `updatedBy` column). Fix before wiring either to the UI.

---

## Practice Assessment Management

| Function | Purpose |
|----------|--------|
| `savePracticeAccess(practiceData)` | Grants a student practice access (sets allowed assessment types and degree sets) |
| `assignPracticeAssessment(studentEmail, assessmentType, cefrLevel, selectedTopics, entityType)` | Routes to Communication or Aptitude practice assignment |
| `assignPracticeAssessmentCommunication(studentEmail, cefrLevel, entityType)` | Assigns a communication practice session using a fresh unassigned set matched to the student's CEFR level |
| `assignPracticeAssessmentAptitude(studentEmail, selectedTopics, entityType)` | Selects questions from `selectQuestionsForPractice()` based on student's weak topics |
| `selectQuestionsForPractice(subSectionIds, studentEmail)` | Picks fresh unattempted questions prioritizing student's weakest sub-sections |
| `calculateAptitudePracticeTopicPriority(studentEmail)` | Calculates which aptitude topics to focus on for practice based on past performance |
| `getStudentAttemptedQuestions(studentEmail)` | Returns IDs of all questions the student has previously attempted (for exclusion) |

---

## Assessment Scheduling

| Function | Purpose |
|----------|--------|
| `createAssessmentSchedule(scheduleName, assessmentType, assessmentConfig, scheduleStartDate, scheduleEndDate, frequencyType, frequencyValue, assessmentValidityDays, listName, studentsData, instituteCampusId, entityType, createdBy)` | Creates a recurring assessment schedule. Saves the student list + schedule config. See `schedule.md` for details |

---

## Proctoring Review (Admin-Side)

| Function | Purpose |
|----------|--------|
| `getProctoringDetails(assessment_assigned_id)` | Fetches full proctoring log for a student's assessment: all snapshots with face detection results (`faceDetected` count per snapshot), `isValid` final result, timestamps |
| `getAudioVideoProctoring(assessment_assigned_id)` | Returns audio-video proctoring event log for a student's session |

---

## Analytics & Reporting

### CEFR (Communication) Analytics

| Function | Purpose |
|----------|--------|
| `getPiChartDataForCefr(assessmentInstituteMapId)` | Returns CEFR level distribution (count per level: A1–C2) for all students in an assessment |
| `getSetOfstudentsForCefrPieChart(assessmentInstituteMapId, cefrLevel)` | Returns the list of students in a specific CEFR slice of the pie chart |
| `getCommunicationAssessmentGroupsWithNormalizedScores(assessmentInstituteMapId, passingYear)` | Groups students by assessment set/schedule, returns normalized scores per group. Powers the grouped score comparison graph |
| `getParticularCommunicationAssessmentStudentDetails(assessmentInstituteMapId)` | Returns per-student section scores for a communication assessment group |
| `_getCommunicationDiagnosisScores(studentEmails, commTypeId)` | Internal — fetches diagnosis-specific communication scores for a list of students |

### Aptitude Analytics

| Function | Purpose |
|----------|--------|
| `getPiChartDataForAptitude(assessmentInstituteMapId)` | Returns aptitude level distribution (Beginner/Learner/Competent/Advanced) |
| `getSetOfStudentsForAptitudePieChart(assessmentInstituteMapId, aptitudeLevel)` | Returns students in a specific aptitude level slice |
| `getAptitudeAssessmentGroups(assessmentInstituteMapId, passingYear)` | Groups students by schedule/passing year, returns per-group aptitude level stats |
| `getParticularAptitudeAssessmentStudentDetails(assessmentInstituteMapId)` | Per-student aptitude scores for a group |
| `_getAptitudeDiagnosisScores(studentEmails, aptitudeTypeId)` | Internal — diagnosis scores for aptitude per student list |
| `getAptitudeTopics()` | Returns all available aptitude sections + sub-sections with IDs |

### Consistency Analytics

| Function | Purpose |
|----------|--------|
| `getConsistencyData(assessmentInstituteMapId, assessmentType)` | Returns consistency distribution: percentage of students in High (≥80%), Moderate (60–80%), and Inconsistent (<60%) attendance categories |
| `getStudentsByConsistencyCategory(assessmentInstituteMapId, assessmentType, category)` | Returns the list of students in a specific consistency category |
| `getStudentsByScheduleAndPassingYear(scheduleId, passingYear)` | Returns students matching a schedule + passing year combination |

---

## Participant & Eligibility

| Function | Purpose |
|----------|--------|
| `getAssessmentAssignedParticipants({ bulkUploadData, entityId, entityType })` | Pre-checks which students in a bulk upload are already assigned to assessments. Returns existing assignments map |
| `getDegreeStreamMapId(degreeId, streamId)` | Resolves a degree-stream combination to a `degreeStreamMapId` |
| `getBatchDegreeStreamMapIds(students)` | Batch resolves degree-stream map IDs for multiple students (returns a `Map`) |

---

## Audit & Activity

| Function | Purpose |
|----------|--------|
| `createAuditEntry(operationType, changeDescription, metadata, email, transaction)` | Inserts a record into `assessment_audit` table. Links to assessment maps for traceability |
| `updateAuditEntry(auditId, changeDescription, metadata, email)` | Updates an existing audit entry (e.g., on completion of a generation job) |
| `getTopActivityLogs()` | Returns the latest audit entries for admin activity feed |

---

## Role-Based Assessment Helpers

| Function | Purpose |
|----------|--------|
| `getRoleBasedSectionId(sectionName)` | Looks up section ID by name (MCQ/Subjective/Video) |
| `selectRoleBasedQuestionsForAssessment(mcqSectionId, subjectiveSectionId, studentEmails)` | Selects fresh unassigned role-based questions for students |
| `getRoleBasedAssessmentWithConfig(assessmentSetId)` | Fetches assessment set + config (role name, sections, questions) |
| `updateRoleBasedAssessmentConfig(assessmentSetId, configData)` | Updates config for an existing role-based set |
| `createRoleBasedAssessment({ entityId, name, instructions, ... })` | Internal helper to orchestrate full role-based assessment creation (maps, sets, question mappings, assignments) |
| `getCefrProgression(currentLevel)` | Returns the next/previous CEFR level for progression tracking |

---

## TPO Dashboard Sent Count — Diagnosis Inclusion

**File:** `student-node/app/models/TpoDashBoard.js`

The TPO dashboard's "sent" count uses `_getAssessmentMapsUpToCurrent()` to determine which assessment maps to count for a given assessment position.

**`_getAssessmentMapsUpToCurrent({ assessmentInstituteMapId, instituteId, assessmentTypeId })`:**
- Fetches all non-one-time maps for the institute+type, ordered by `startTime`
- Includes all maps up to and including the current assessment's position
- Also includes diagnosis/standalone maps (where `scheduleId` is null) that appear AFTER the current position
- This ensures students added to an existing assessment via diagnosis get counted in "sent"

**Why diagnosis maps appear after current position:** When students are added to an existing scheduled assessment, `_sendDiagnosisForSchedule()` creates diagnosis maps with `startTime = today` (which may be after the current assessment's `startTime`) and without a `scheduleId`.

**CEFR/Aptitude pie chart filter fix:** The candidate list pie chart filters (CEFR level, aptitude level) only return students who have actually attempted the assessment. The filter checks `assignedIdMap[email]` with a truthy check (not just `|| {}`) so students without attempt data are excluded.

---

## Key Design Patterns

- **Entity Duality:** Almost every function supports both `entityType = "college"` (→ `assessment_institute_map`) and `entityType = "corporate"` (→ `assessment_corporate_map`) with separate query branches
- **Concurrency Control:** `runWithConcurrency()` limits parallel student processing to avoid DB overload during bulk assignments
- **Pegging:** The "pegging" system (`global.peggingMaps`) ensures a student always receives the same aptitude questions, preventing question pool gaming
- **Batch Queries:** `getBatchDegreeStreamMapIds()` and similar functions use batch lookups to avoid N+1 queries during bulk operations
- **Audit Trail:** All major operations (assignment, generation, schedule creation) create `assessmentAudit` entries for traceability
- **ExcelJS Export:** `exportStudentData()` uses ExcelJS to generate formatted XLSX files for download without a temp file
