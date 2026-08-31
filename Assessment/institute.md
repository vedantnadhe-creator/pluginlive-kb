# Institute Assessment (TPO View)

> Documents the institute-side assessment management — how TPOs view assessments, student lists, and scores. Covers `institute-node/StudentListInfo.js` (assessment schedules) and `student-node/TpoDashBoard.js` (student list API).

---

## Architecture

Institute assessments use a **two-API architecture**:

| Assessment Types | Backend API | Frontend Action |
|-----------------|-------------|------------------|
| Communication, Aptitude | student-node `specific-assessment-student-list` | `fetchSpecificAssessmentStudentListAction` |
| Role_Based, Custom, Behavior, AI_Interview, etc. | admin-node `getAssessmentDetails` | `fetchAssessmentDetailsAction` |

This split exists because Communication and Aptitude are "standard" types with schedules, progression tracking, and CEFR/aptitude levels. Other types are standalone assignments without scheduling infrastructure.

---

## Institute-Node: `StudentListInfo.js`

**File:** `institute-node/app/models/StudentListInfo.js`

### `getSchedulesInfo(instituteId, passingYear, ...)`

Fetches all assessment schedules and standalone assessments for the institute dashboard.

**Pagination:** Applied at **application level** after combining all three assessment source types. The SQL query for scheduled assessments does NOT use LIMIT/OFFSET — all results are fetched, combined with one-time and standalone assessments, sorted by `created_at DESC`, then sliced for the requested page. This is necessary because one-time and standalone assessments come from separate query branches and cannot be paginated at SQL level together with scheduled assessments.

```javascript
// After combining all results:
const finalTotalCount = result.length;
const totalPagesFinal = Math.ceil(finalTotalCount / pageSize);
const paginatedResult = result.slice(offset, offset + pageSize);
```

**Key logic in Step 4 SQL query:**
```sql
WHERE aim.schedule_id = ANY($1::uuid[])           -- scheduled assessments
   OR (aim.institute_id = $2 AND aim.is_one_time = true)  -- one-time assessments
   OR (aim.institute_id = $2 AND aim.schedule_id IS NULL
       AND (aim.is_one_time IS NULL OR aim.is_one_time = false)
       AND LOWER(at.type_name) NOT IN ('communication', 'aptitude'))  -- standalone other types
```

**Assessment type classification:**
- **Scheduled**: Communication/Aptitude with `schedule_id` set — belong to assessment schedules
- **One-time**: Any type with `is_one_time = true` — shown individually
- **Diagnosis**: Communication/Aptitude with `schedule_id = NULL` and `is_one_time = false` — these are auto-created diagnosis assessments that belong to schedules
- **Standalone other types**: Role_Based, Custom, Behavior, AI_Interview, etc. with `schedule_id = NULL` and `is_one_time = false` — these are NOT diagnosis; they never have schedules. Shown as individual rows.

> **This derivation is v1-institute-only, and it is the last one left.** The
> **v2** institute screens read the stored
> `assessment_assigned_students.is_diagnosis` flag (written by admin-node at
> assign time) rather than inferring it — since 2026-08-26 — and since
> **2026-08-31** so does the whole candidate path: student-node
> `getActiveAssessments`, the start guard and the reload guard, admin-node's
> TPO diagnosis-score queries and its duplicate-map scan, and both candidate
> frontends. See
> [candidate-frontend-v2.md](candidate-frontend-v2.md) → *What counts as a
> diagnosis* and `ATS/Institute/v2-strangler-fig.md` → "Diagnosis ownership is
> stored, not inferred".
>
> The two agree exactly **for Communication and Aptitude** (0 mismatches on DEV
> and UAT). They do **not** agree for anything else: the predicate above also
> matches every unscheduled Behavior / Role_Based / Custom / AI_Interview
> assignment and every standalone unscheduled Communication/Aptitude float —
> 2,532 rows on DEV, 740 on UAT — which the flag correctly leaves `false`. Do
> not reuse this derivation in new code.

**CANDIDATES = active roster count (`is_active`), 2026-07-03:** For scheduled rows, `totalCandidates` is the count of **active** students in the schedule's list — roster students whose `students_data` object is **not** flagged `is_active === false` (absent/`true` = active), scoped by `passingYear`. Soft-removed students stay in the list and in all history/stats but are excluded from this count because they receive no further assessments (see `schedule.md` → "Soft-removed students"). The row also returns `activeCandidates` (= `totalCandidates`), `inactiveCandidates` (soft-removed count), and `totalListCandidates` (full roster size for the passing-year scope). Diagnosis (`diagnosisCompleted`/`totalDiagnosisTaken`/`diagnosisStatus`) is scoped to the **full roster** (`studentEmails`), NOT the active subset — diagnosis was sent to everyone historically and the drill-in shows all of them, so the row must match (fixed 2026-07-09; a prior build wrongly narrowed it to active, making the Diagnosis row show `taken/active×2` e.g. `34/36` while the drill-in showed 57). The diagnosis state itself is read from `assessment_assigned_students` by `primary_email` via the pre-computed `diagnosisCountMap`. The **frontend** Diagnosis sub-row (`ExpandableContent.js`) computes `assessmentsSent = (totalListCandidates ?? totalCandidates) * 2` — full roster × 2. **Sent / taken / expired and the per-run "Schedule N" sub-rows remain assigned-table based** (`assignedByMapId[map_id]`) — so historically-assigned-but-now-inactive students still appear in run counts and the drill-in. (One-time/standalone rows keep their own `totalCandidates = studentEmailsSet.size` from assigned students and do not carry the active/inactive breakdown.)

**Anomalous-run guard (2026-07-09):** `regularMaps` now excludes any run whose `end_time − start_time > ~2 years`. Stray single-student maps created with a ~10-year validity (start 2025 → end 2035) otherwise rendered as bogus `Schedule N` rows (`0/1`, ending 2035). Diagnosis maps (`schedule_id NULL`) legitimately have far-future ends but are never in `regularMaps`, so they're unaffected. Seen on Naralkar Institute: 4 duplicate 10-year Aptitude maps for one soft-removed student under schedule `0fef81af`.

> **Gotcha — standalone/one-time rows carry `scheduleId = the map id`:** for one-time and standalone rows, `getschedulesInfo` sets the result `scheduleId` field to `assessment_institute_map_id` (there is no real schedule). Any consumer that forwards `assessment.scheduleId` to a schedule-keyed API will look up a non-existent schedule. See the filter-option dropdown fix below.

### Filter-option dropdowns (degree / department / specialization)

The detail-page filter dropdowns are populated by student-node `getDomain` / `getDegree` / `getDepartment` / `getSpecialization` → `TpoDashBoard._getFilteredStudentCourseData`. These accept **`assessmentId`** (the assessment_institute_map id) OR `scheduleId`; for non-scheduled / one-time assessments the frontend passes `assessmentId`, so no `scheduleId` is required.

This dropdown had **three independent "No data" bugs**, all fixed 2026-06-12. The recurring one (reported repeatedly as "still not coming") was the **redundant-instituteId** bug — the others were real but masked it.

**Primary "No data" fix — bogus scheduleId:** `getschedulesInfo` returns one-time and standalone (Role_Based/Custom/etc.) rows with **`scheduleId = the assessment_institute_map id`** (there is no real schedule). The detail page's option-fetch effects passed `assessment.scheduleId` to `getDomain`/`getDegree`/…, and `_getFilteredStudentCourseData` **prefers its `scheduleId` branch** (`if (scheduleId) { ...AssessmentSchedule.findUnique(id=scheduleId)... }`). With a map id there, the schedule lookup returns nothing → 0 emails → empty `["No data"]` dropdown — even though the table (which uses the `assessmentId`/`assessmentInstituteMapId` path) shows degrees fine. Fix is in the **frontends**: `InstituteAssessmentDetails.js` (admin-react) and `AssessmentDetails/index.js` (institute-react) now suppress `scheduleId` for non-standard / one-time / standalone assessments (`(isOtherType || assessment?.isOneTime || assessment?.isStandalone) ? '' : assessment?.scheduleId`), so the **`assessmentId` branch** is used — the same method scheduled (real-schedule) assessments rely on. Verified: `getDegree?scheduleId=<mapId>&assessmentId=<mapId>` → `degrees:[]`; `getDegree?assessmentId=<mapId>` → the real degree.

**Secondary source fix:** once on the `assessmentId` branch, the options query also reads **`COALESCE(current_course, education_profile)`** — the same source the student-list table uses. Previously it read **only `current_course`** and `return students.map(s => s.currentCourse).filter(Boolean)`, which **dropped every student lacking a `current_course` row**. It now fetches both relations and coalesces field-by-field (current_course preferred). Returned option values are UPPER-cased — `getAssessmentDetails` matches them case-insensitively (see `Assessment/admin.md`).

**Passing-year scoping fix — the broadcast "No data" case:** `_getFilteredStudentCourseData` now applies the **passing-year window ONLY on the schedule-roster path (`scheduleId`)** and the institute-wide path (no `assessmentId`). For a **specific assessment** (`assessmentId`, no `scheduleId`) the assigned students ARE the scope, so it does **not** year-filter — matching `getAssessmentDetails`, which never filters the table by year. Without this, a (broadcast) Role_Based assessment whose candidates graduated e.g. 2024 showed degrees in the table but an empty dropdown because the dashboard passed `passingYear=2026`. Pattern is the reverse relation: **assigned students → join current_course/education_profile → distinct degrees/departments** (scales with student count, not a year guess). Verified on UAT: `getDegree?assessmentId=<roleBasedMapId>&passingYear=2026` returns the real degree.

**Redundant-instituteId fix — THE one that kept reproducing:** in the `assessmentId` (non-schedule) branch, `_getFilteredStudentCourseData` scoped the assignment lookup by **both** `assessmentInstituteMapId` **and** `assessmentInstituteMap.instituteId`. The frontend passes `instituteId` from the currently-selected institute, and after **navigating between institutes** that prop goes **stale** — so it sent e.g. `instituteId=4eb177ed` for an assessment that belongs to `8b4d7b0a`. The `AND` then matched **zero rows** → empty dropdown, even though the assessment had ~1000 students with degrees. Because the `assessment_institute_map_id` **already uniquely identifies** the map (and its students), the institute filter is redundant; it's now dropped whenever `assessmentId` is present: `assignmentsWhere = assessmentId ? { assessmentInstituteMapId } : (instituteId ? { assessmentInstituteMap: { instituteId } } : {})`. Verified DEV+UAT: `getDegree?assessmentId=<mapId>&instituteId=<WRONG-id>` now returns the real degree.

### Performance: assessment indexes (`tpo_dashboard_indexes.sql`)

`getschedulesInfo`, `getAssessmentDetails`, and `getStudentListForTpoAssessment` all filter `assessment.assessment_assigned_students` by `assessment_institute_map_id` (20k+ rows on DEV, more on PROD). The canonical migration `DB-Scripts/tpodashboard optimizations/tpo_dashboard_indexes.sql` adds the supporting indexes — notably `idx_aas_aim_practice (assessment_institute_map_id, is_practice)` (its leading column serves the map-id-only lookups) and `idx_aim_institute_id`. **Applied to DEV + UAT (2026-06-12); PROD pending.** All are `CREATE INDEX CONCURRENTLY IF NOT EXISTS` (safe/idempotent, no table lock). The admin-react list page also caches the `getschedulesInfo` response for ~12s and persists its filters across in-app navigation, so returning from an assessment doesn't refire the query.

### Status computation (Ongoing / Expired / Upcoming)

Status is **computed at request time** against `now = new Date()` — it is NOT stored in any DB column. There are **two distinct levels**, computed independently:

1. **Parent schedule row** (the top-level "Communication"/"Aptitude" row) — uses `assessment_schedules.schedule_start_date` / `schedule_end_date`:
   - `now < start_date` → `Upcoming`
   - no `end_date`, or `now <= end_date` → `Ongoing`
   - `now > end_date` → `Expired - Lapsed` (if `taken < sent`) or `Expired - Completed`

2. **Per-run sub-rows** (`assessmentDetails[]` — the expandable "Schedule 1", "Schedule 2", … weekly runs) — uses each run's own `assessment_institute_map.start_time` / `end_time` (NOT the parent schedule dates):
   - `now < start_time` → `Upcoming`
   - `now > end_time` → `Expired - Lapsed` / `Expired - Completed`; `expiredCount` = assigned students who never submitted/attempted
   - otherwise → `Ongoing`

   Each sub-row is **one weekly run = one `assessment_institute_map`** (the `regularMaps` in `start_time ASC` order). `takenCount` / `assignedCount` / `expiredCount` are counted over **that map's assigned students** (`assignedByMapId[nthMap.assessment_institute_map_id]`, with the same passing-year filter), so the row matches the drill-in detail view, which counts by `assessment_institute_map_id`. `attemptNumber` is just the run ordinal (1-based position in `regularMaps`), used for the "Schedule N" label.

A `WEEKLY` schedule normally has a parent that runs for months (e.g. `30 May 2026 → 30 Apr 2027`, correctly `Ongoing`) while individual weekly runs (e.g. `30 May → 7 Jun`, `6 Jun → 8 Jun`) have already lapsed. The two levels are expected to differ.

**Bug fixed (2026-06-09):** Per-run sub-rows in `assessmentDetails` hardcoded `status: "Ongoing"` and `expiredCount: 0` — they never compared the run's own `end_time` to `now`. Lapsed weekly runs (seen on Christ University, Lavasa Communication: Schedule 1 ending 7 Jun, Schedule 2 ending 8 Jun) showed "Ongoing" next to the run name even though the row's right-side badge (frontend-derived from `endTime`) correctly read "Expired". `StudentListInfo.js` now computes each run's status/`expiredCount` from `start_time`/`end_time`, matching the one-time and standalone code paths. DB data was correct; this was purely an API display bug.

**Bug fixed (2026-06-16):** Per-run sub-rows bucketed students by `attempt_number === n` instead of by the weekly run's map. `assessment_assigned_students.attempt_number` is a **per-student completion ordinal** (a student's 1st/2nd/3rd completion within the schedule), NOT "which weekly run" — so a student whose first completion happened on the 3rd run carried `attempt_number = 1` and was counted under "Schedule 1". The list row "Schedule N" therefore diverged from its drill-in (which counts by `assessment_institute_map_id`). Seen on Christ University, Lavasa Communication: **Schedule 3 showed `9 taken / 82 sent` while the run's detail view listed 23** (PROD `attempt_number` of the 23 who took run 3: 7×`1`, 7×`2`, 9×`3` — only the nine `3`s landed in the row). Fix: the `assessmentDetails` loop now iterates `regularMaps` and counts each row over that map's assigned students (`assignedByMapId[nthMap...]`), so list and drill-in agree (~27 / 24 / 23). Passing-year filter preserved; the unused `attempt_number` column was dropped from the assigned-students query. Pure API count bug; DB data was correct.

**Bug fixed (2026-07, `hotfix/assessment-tz-sync`):** `StudentListInfo.getCorporateAssessmentsInfo`
computed corporate assessment status/expiry against a **raw** `NOW()` (SQL `total_expired`) and
`new Date()` (JS status), with no `+5.5h` compensation — so corporate assessments read as
`Ongoing`/`Upcoming` ~5.5h **past** their true IST expiry (the opposite direction from the
early-expiry write bug, but the same root convention). `getschedulesInfo` was already correct
(`IST_OFFSET_MS = 330*60*1000; now = Date.now()+IST_OFFSET_MS`). Fix mirrors it: SQL uses
`NOW() + INTERVAL '5 hours 30 minutes'`, JS uses `new Date(Date.now() + IST_OFFSET_MS)`. See
`Assessment/admin.md` → *Timezone convention*. **institute-react** display was fixed in the same
hotfix (schedule dates render UTC in `UnifiedAssessmentTable`/`ExpandableContent`/`StudentsTable`/
`AssessmentNavBar`/`FullStudentReport`; `CustomDateCalendarDrawer` deferred).

### Gotcha: `students_data` column type differs by environment (json vs jsonb)

`assessment.student_lists.students_data` is **`jsonb` on DEV** but **`json` on UAT and PROD**. The `passingYear` filter in `getschedulesInfo` runs an `EXISTS (SELECT 1 FROM jsonb_array_elements(sl_filter.students_data::jsonb) ...)` subquery. Without the `::jsonb` cast, `jsonb_array_elements(json)` raises Postgres `42883` (`function ... does not exist`) and the **entire endpoint 500s** — but only when a `passingYear` filter is applied (no filter → subquery skipped → no error). This passed on DEV (jsonb) and broke on UAT/PROD (json).

**Bug fixed (2026-06-09):** added the `::jsonb` cast so the query works regardless of the column's declared type. Any new SQL touching `students_data` with `jsonb_*` functions MUST cast `::jsonb`. Long-term cleanup: align the column type across environments (UAT/PROD → `jsonb`).

### Per-student assessment status label (TpoDashBoard.js)

The per-student status column maps the DB `AssessmentStatus` enum (`PENDING`, `INPROGRESS`,
`COMPLETED`, `DROPOUT`) to display labels: **Completed / In Progress / Dropout / Pending**.
`submitted && scoresCalculated` is treated as the source of truth for **Completed** (in case the
enum lags). The `statusFilter` input still uses the raw enum values, so it's unaffected.

**Bug fixed (2026-06-11):** the mapper previously derived `"Attempted"` from the `attempted` flag —
which mislabeled `DROPOUT` rows (and could even hide a real Completed row when a student had both a
completed and a dropped assignment for the same assessment). There is **no "Attempted" status**.
Both mappers (`getStudentListForAssessment` ~L2588 and `getStudentListForCorporateAssessment` ~L3138)
now map the enum directly. Note: after diagnosis the schedule legitimately assigns **2 assessments**
(2 institute-maps under one schedule), so a student can have one `COMPLETED` + one `DROPOUT` row.

### Diagnosis Count Query (Step 5 — `diagnosisCompleted` / `totalDiagnosisTaken`)

Counts how many students completed diagnosis (submitted >= 2 assessments of the same type for the institute).

**Critical:** The query MUST use `INNER JOIN` on `assessment_institute_map` and filter by `aim.institute_id` to prevent corporate assessments from leaking into the count. Corporate assessments have `assessment_institute_map_id = NULL`, so a `LEFT JOIN` with `aim.is_one_time IS NULL` would match them (NULL evaluates to true).

```sql
SELECT aas.primary_email, COUNT(*) as submitted_count
FROM assessment.assessment_assigned_students aas
JOIN assessment.assessment_sets aset ON aas.assessment_set_id = aset.assessment_set_id
JOIN assessment.assessment_institute_map aim ON aas.assessment_institute_map_id = aim.assessment_institute_map_id
WHERE aas.primary_email = ANY($1::text[])
  AND aset.assessment_type_id = $2::uuid
  AND aas.submitted = true
  AND aim.institute_id = $3::text
  AND (aim.is_one_time IS NULL OR aim.is_one_time = false)
GROUP BY aas.primary_email
```

**Bug fixed (2026-03-12):** Previously used `LEFT JOIN` without `institute_id` filter — corporate assessment submissions were counted toward institute diagnosis totals.

### TPO Student List: Communication/Aptitude Taken/Sent

**File:** `student-node/app/models/TpoDashBoard.js` — `getStudentListForTpoDashboard()`

The per-student communication/aptitude taken/sent counts shown in the "Total Candidates" list are correctly isolated. All four queries (commSent, commTaken, aptSent, aptTaken) filter by:
```javascript
assessmentInstituteMap: { instituteId: instituteId, isOneTime: false }
```
This ensures corporate assessments are excluded.

### `getCorporateAssessmentStudents(instituteId, assessmentMapId, ...)`

Fetches student list for a specific assessment (used by corporate view). Includes scores for all types.

---

## Student-Node: `TpoDashBoard.js`

**File:** `student-node/app/models/TpoDashBoard.js`

### `getStudentListForAssessment()` (TPO method, lines ~1014-2235)

Returns student list with scores for Communication and Aptitude assessments. Also includes scores for other types when accessed via institute view.

**Prisma includes for score fetching:**
```javascript
behaviorScores: true,
roleBasedScores: { include: { section: { select: { sectionName: true } } } },
customAssessmentScores: true
```

**Score calculation by type:**

| Type | Score Source | Total Score | Section Scores |
|------|------------|-------------|----------------|
| Communication | `communicationScores` | Percentage from sections | reading, listening, speaking, writing |
| Aptitude | `aptitudeScores` | Percentage from sections | critical, quantitative, logical |
| Behavior | `behaviorProficiencyScores` | **null — Behavior has no score** | none; awarded levels come back as `proficiencyLevels` |
| Role_Based | `roleBasedScores[]` | Average of section scores | Dynamic from `section.sectionName` (e.g., mcq, subjective, video) |
| Custom | `customAssessmentScores[0]` | `percentage` field | `gainedMarks`, `totalMarks`, `percentage`, `sectionWiseStats` |

> **Behavior carries no total score (2026-08-20, DEV + UAT, PROD pending).** This row
> previously averaged `behaviorScores[0].totalScores`, which is not a score table — it is
> the raw answer tally (`{"Empathy":{count,total}, …, "grandTotal":350}`). Reducing its
> values with `+` concatenates objects, so every Behavior row here and in the Excel export
> printed **`NaN`**. There is no percentage to substitute: `behavior_competency_scores.score`
> is a weighted T-score (mean 50, SD 10), and the assessment never rolls the nine
> competencies into one figure — the candidate's own PDF prints no number at all. So
> `totalScore` is `null` and `helpers/behaviorDashboardScore.js` returns the awarded levels
> as `proficiencyLevels` (`{competencyName: "Practitioner"}`) for callers that can render a
> profile. The v1 screen currently leaves the score column blank for Behavior and needs a
> level column to be useful; the v2 TPO drawer shows the full competency profile — see
> `ATS/Institute/v2-strangler-fig.md`.

**Response includes:** `assessmentType` field (`mapData.assessmentType.typeName`) for frontend type detection, and `timeTakenSeconds` — the attempt's `total_time_taken` (seconds) selected as `totalTakenTime` alongside the assignment. Null when the candidate never submitted.

### `exportExcelOfStudentListForAssessment()` (Excel export of the above)

Re-runs `getStudentListForAssessment` with `pageSize: 'NA'` (all rows, no pagination) and builds the sheet with ExcelJS. Base columns mirror the on-screen table (Candidate Name, Email, Degree, Department, Progression Level, Assmt. Taken On, Taken / Sent, Total Score), then type-specific columns, then Proctoring.

For **Aptitude** the type-specific block opens with **Time Taken** (`mm:ss`) before Critical / Quantitative / Logical. It is filled from `timeTakenSeconds` via the `_fmtMmSs()` helper on `TpoDashBoard`, and is set **independently of `sectionScores`** — the clock lives on the assignment, not the score row, so gating it on scores would blank it. Unattempted candidates render `-`, matching the rest of that sheet. Only Aptitude gets the column; Communication and AI Interview keep their existing section/parameter columns.

> The equivalent column in the admin results export renders a **blank** cell rather than `-` for a non-attempt — each export follows its own sheet's convention. See `Assessment/admin.md`.

### `getStudentListForCorporateAssessment()` (Corporate method, lines ~2237-2658)

Same as TPO method but for corporate assessments. Already had all score types from the beginning.

---

## Frontend: Institute-React

### Assessment Details (`AssessmentDetails/index.js`)

- Uses `isStandardType = ['communication', 'aptitude'].includes(assessmentTypeLower)` to guard:
  - Charts/graphs: only shown for standard types
  - Assigned difficulty column: only shown for standard types
  - Progression level column: only shown for standard types
  - Page heading: standard types show `{scheduleName}-schedule-{scheduleNumber}`, non-standard types show assessment name directly

### CandidateList (`CandidateList/index.js`)

- Dynamic column extraction for Role_Based/Behavior: scans all student rows for keys in `sectionScores` OR `roleBasedScores`
- Total Score column: `r.totalScore ?? r.totalAvgScore ?? r.roleBasedScores?.overallScore ?? r.customAssessmentScores?.percentage`
- Assigned Difficulty and Progression Level hidden for non-standard types
- **Status column** renders `student.status` directly (label, not the DB enum): green for `Completed`/`Attempted`, orange for `In Progress`, blue for `Sent`, red otherwise.
- **"Assmts. taken / sent" column** renders the `skipCount` string (`"taken/sent"`) verbatim; it also accepts explicit `assessmentsTaken`/`assessmentsSent`. Despite the legacy field name `skipCount`, this column shows **taken/total**, not skips. Same contract in admin-react's CandidateList.
- **Status filter / tabs (non-standard types):** institute-react keeps a **status-tab** UX (All / Pending / In Progress / Dropped Off / Completed) driven by `currentActiveStatus` + `onStatusChange`, bucketing the full `getAssessmentDetails` result **client-side** — so it does NOT pass `paginate`. (admin-react instead uses a server-side status-filter popover with `paginate=true`; see `Assessment/admin-frontend.md`.) The status-filter popover checkbox double-toggle (row `onClick` + `Checkbox onChange` both firing) was fixed here too. Export reflects the active status tab + degree/dept/spec/search filters.

### admin-node `getAssessmentDetails` per-candidate fields (Role_Based / Custom / Behavior list)

The non-standard-type candidate list is served by **admin-node `Assessment.getAssessmentDetails`** (`/assessment/getAssessmentDetails`, `formatStudent`). Two fields the frontend depends on:

- `status` — **display label** mapped from the DB `assessment_assigned_students.status` enum: `COMPLETED→Completed`, `INPROGRESS→In Progress`, `DROPOUT→Dropout`, `PENDING→Pending`, with a `submitted`/`attempted` fallback for legacy rows where the enum is NULL.
- `skipCount` / `assessmentsTaken` / `assessmentsSent` — `taken = COUNT(submitted OR attempted)`, `sent = COUNT(*)` per email for the map. `skipCount` is the `"taken/sent"` string the column renders.

**Bug fixed (2026-06-11):** `formatStudent` previously never set a `status` field (so the frontend Status column rendered blank/red even for COMPLETED submissions), and `skipCount` was computed as **skipped/total** (`attempted=false AND end_time<NOW()`) — so a completed attempt showed `0/1` under the "taken/sent" column. Seen on UAT for `testing-br-3` (Role_Based): a submitted/COMPLETED candidate displayed blank status + `0/1`. Now status is mapped and the count is taken/total. Backend-only fix; no consumer reads `skipCount` as skips.

### StudentReport (`StudentReport/index.js`)

- Renders type-specific score cards:
  - `renderRoleBasedScoreCards()`: shows MCQ, Subjective, Video scores from `roleBasedScores` or `sectionScores`
  - `renderCustomAssessmentScoreCards()`: shows gained/total marks and percentage
  - `renderBehaviorScoreCards()`: existing behavior score display
- Report download routes to type-specific PDF generator
- Download/Export triggers across institute-react (CandidateList, DiagnosisList, StudentsTable, Reports `ExportPopup`) are rage-click guarded since August 2026 — see `download-button-guard.md`. `StudentReport`'s own download keeps its pre-existing `downloadingReport` state.

---

## Data Format Differences Between APIs

The two APIs return scores in different formats:

| Field | student-node (Communication/Aptitude) | admin-node (Other types) |
|-------|---------------------------------------|-------------------------|
| Section scores | `sectionScores: { reading: 75, ... }` | `roleBasedScores: { mcqScore: 80, ... }` |
| Total score | `totalScore: 75` | `roleBasedScores.overallScore: 80` |
| Custom scores | N/A | `customAssessmentScores: { percentage, gainedMarks, totalMarks }` |

Frontend CandidateList handles both formats by checking multiple score sources.

---

## PDF Report Performance

**Optimization:** All PDF report methods use a shared Puppeteer browser pool (`getSharedBrowser()` in `student-node/app/models/Assessment.js`) instead of launching a new Chromium instance per report. This significantly reduces PDF generation time for concurrent requests.

```javascript
// Singleton browser pool — reuses one Chromium instance
const browser = await getSharedBrowser();
const page = await browser.newPage();
try {
  // ... generate PDF
} finally {
  await page.close(); // close page, NOT browser
}
```
