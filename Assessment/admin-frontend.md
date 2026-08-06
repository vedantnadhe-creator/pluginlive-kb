# Admin-React Assessment Frontend

> Documents the admin-react Assessment module (`src/modules/Assessment/`), covering institute and corporate assessment management, student reports, NPS scoring, and the unified assessment table.

> **Add Candidate field requirement (current):** In the "Add Candidates Manually" / bulk-upload drawers (`CreateAssessment/Drawers/EnhancedBulkUploadDrawer.js` and `BulkUploadDrawer.js`), **only First Name and Email are mandatory — Last Name is optional**. The `*` on Last Name is removed, the "Add Candidate" button is no longer disabled on a blank last name, the submit-time guard doesn't require it, and the Excel-file row parser no longer drops rows that have a blank last name. Backend: `admin-node` `Assessment.saveStudentList`/`updateStudentList` no longer list `lastName` in `requiredFields` and trim it null-safely.

> **Candidate mobile country code (current):** In `EnhancedBulkUploadDrawer.js`'s manual Add Candidate form, mobile number has its own country-code `Select` next to the number input, backed by `utils/candidateMobile.js` (`COUNTRY_DIAL_CODES`, `DEFAULT_COUNTRY_CODE = '+91'`). It defaults to **+91 pre-selected**, not blank — the drawer-open reset must explicitly set `countryCode: DEFAULT_COUNTRY_CODE` (and clear `phone`) alongside the other fields, since an omitted key there renders the Select empty even though the initial `useState` has the default. When a recruiter adds several candidates in a row, the last-chosen country code is intentionally carried over to the next blank form rather than reset each time. **The Edit Assessment drawer has the same field** — see *Edit Assessment Drawer → Mobile number* below.

> **Save as List is entity-scoped, college *and* corporate (2026-08-06).** In `EnhancedBulkUploadDrawer.js`, the saved-candidate-list feature used to key every list on `assessmentData.instituteCampusId`. That value comes from `CreateAssessment/index.js`'s `handleEntitySelect` → `option.campusId`, which **only exists for a college** — so creating a *corporate* assessment and clicking "Save as List" failed with `Institute campus ID not found`. The drawer now derives the owning entity once: `listEntityType = entityType === 'corporate' ? 'corporate' : 'college'` and `listEntityId = assessmentData?.entityId || assessmentData?.instituteId`, and sends `{ entityType, entityId }` to both `assessment/saveStudentList` and `assessment/getStudentLists`. **Save and fetch previously used different keys** — save sent the *campus* id while `loadExistingLists` queried the *institute* id — so a list saved from this dialog never reappeared under "Select from Existing Lists", for college either; using one derived value fixes both. The corporate **Add Candidate** drawers (`ActiveCorporateList/CorporateAssessmentDashboard.js`, `Assessment/index.js`) passed no entity at all and now pass `entityId`. Backend scoping: see *Student List Management* in `Assessment/admin.md`.

> **+91 is the default in every country-code picker (2026-08-06).** Five pickers outside the Assessment module used to open blank, so a user who never touched them submitted `countryCode: undefined` (or tripped a `required` rule): Onboarding → Add New Corporate (`Corporates/.../AddNewCorporateDrawer/Partials/ContactDetails`), Onboarding → Add Institute (`Institutes/.../AddInstDrawer/Partials/InstContactDetails`), both Add-User drawers (`User/Partials/AddUserDrawer`, `User/Partials/UsersView/AddUserDrawer`), and Onboarding → Add New Institute (`Corporates/.../AddNewInstituteDrawer`, which *displayed* `+91` from `useState('+91')` but never wrote it to the form because its picker is not wrapped in a `Form.Item`). **Two different value formats, and the seed must match the picker's options or antd shows a value with no matching option:** the API-driven pickers (options from `/search/countries?groupBy=phone_code`) use **bare digits `'91'`**, while the hardcoded-array pickers use **`'+91'`**. Seeding pattern: a mount-time `form.setFieldValue('countryCode', …)` guarded by `if (!form.getFieldValue('countryCode'))` so an edit flow's value is never overwritten; where a `resetFields()` runs (AddNewInstituteDrawer's `addContent` branch) the default must be re-seeded in the same `setFieldsValue` block. `InstContactDetails` additionally needed `Form.useWatch('countryCode', form)` — it read `form.getFieldValue(['countryCode'])` inline, which is `undefined` on first render and never re-reads, so the seeded default would have stayed invisible.

---

## File Reference

**Module Root:** `admin-react/src/modules/Assessment/`

| File | Purpose |
|------|--------|
| `index.js` | Main Assessment page -- tabs for institutes/corporates, routes to dashboards, handles assessment/diagnosis click routing |
| `actions.js` | Redux action creators for fetching institutes, corporates, assessments, student data |
| `reducers.js` | Redux reducer for assessment state |
| `selectors.js` | Redux selectors for assessment state |
| `Style/style.js` | Shared styled-components (CustomStyledTable, SearchSection, TableTop, ShowingText, AssessmentName, etc.) |

### Partials

| File | Purpose |
|------|--------|
| `Partials/ActiveCollegeList/index.js` | Institute list with AntdAvatar, search, pagination. Clicking opens InstituteAssessmentDashboard |
| `Partials/ActiveCollegeList/InstituteAssessmentDashboard.js` | Per-institute assessment dashboard -- info cards, UnifiedAssessmentTable, Add Candidate drawer |
| `Partials/ActiveCollegeList/InstituteAssessmentDetails.js` | Charts + cascading filters for a specific institute assessment |
| `Partials/ActiveCollegeList/UnifiedAssessmentTable/index.js` | Main assessment table -- supports both institute and corporate records, expandable rows, search, pagination, Add Candidate button |
| `Partials/ActiveCollegeList/UnifiedAssessmentTable/ExpandableContent.js` | Expanded row content showing assessment schedule details |
| `Partials/ActiveCollegeList/TpoStudentListTable.js` | Student list table with sortable columns including NPS scores |
| `Partials/ActiveCollegeList/CandidateList/index.js` | Student candidate list within an assessment -- clicking opens StudentReportModal |
| `Partials/ActiveCollegeList/DiagnosisList/index.js` | Diagnosis assessment student list |
| `Partials/ActiveCorporateList/index.js` | Corporate list with AntdAvatar, search, pagination |
| `Partials/ActiveCorporateList/CorporateAssessmentDashboard.js` | Per-corporate assessment dashboard -- reuses UnifiedAssessmentTable |
| `Partials/StudentReport/index.js` | Student report drawer -- shows scores, personal details, download report |

### Assessment detail & list behavior (updated 2026-06-12)

`InstituteAssessmentDetails.js` powers the per-assessment detail page for **every** assessment type. Two data paths:
- **Scheduled** communication/aptitude → `fetchSpecificAssessmentStudentList` (student-node).
- **Everything else** (one-time, Role_Based, Custom, Behavior, technical, AI_Interview) → `fetchStudentsByStatus` → admin-node `getAssessmentDetails`. This call now passes the CandidateList filters (degree/department/specialization + `status`) and `paginate: true`, so the detail shows the **Status column + Degree/Department/Specialization/Status filters for all types** (CEFR/Aptitude/Consistency remain communication/aptitude-only). Server pagination via `pagination.totalCount` fixes the old "Showing 10 of 10" on a 15-student assessment (all students reachable + pager restored).
- **Export** (`CandidateList` → `exportStudentData`) reflects the active degree/dept/spec/status/search filters and exports the full filtered list (status `'sent'`), not just the visible page.

`CandidateList` status-filter popover: the checkbox previously toggled twice (row `onClick` + `Checkbox onChange` both fired) so only the **label** click registered; fixed with `onClick={e => e.stopPropagation()}` on the checkbox.

`InstituteAssessmentDashboard.js` (the institute's assessment list): the assessment-type filter, passing year, and column filters now **persist across in-app navigation** (module-level store, reset on full page reload), and the `getschedulesInfo` response is **cached ~12s** keyed by the request params — returning from an assessment within that window restores the list without refiring the request. Mutations (Add Candidate, schedule update) force-refresh and clear the cache.

> **institute-react parity:** the same fixes are mirrored there, except its other-type detail keeps its existing **status-tab** UX (All/Pending/In Progress/Dropped Off/Completed) instead of the status-filter popover; it therefore does **not** send `paginate` (it buckets the full result client-side).

### Per-row "Copy Link" (manual fallback for failed email delivery)

The assessment detail **StudentsTable** (Pending / In-Progress / Dropped-Off tabs for both institute and corporate) has a **Copy Link** action in the `ACTIONS` column. It copies the exact same URL that would be sent in the invite/reminder email, so admins can share it via WhatsApp/SMS when email delivery fails.

| Entity type | What is copied | Backend endpoint | Candidate experience |
|---|---|---|---|
| **Corporate** | `assessment.<env>.pluginlive.com/assessment/start/<JWT>` | `admin-node` `GET /assessment/invite-link/:assessment_assigned_id` | Email OTP → lands on that specific assessment. Reuses the existing corporate OTP-invite flow. |
| **Institute** | `student.<env>.pluginlive.com/onboarding/activate/<studentId>` | `user-management-node` `GET /user/invite-link?email=` | Activation page decides: set password + SMS OTP if not active, or login if already active. |

Important frontend detail: `StudentsTable` rows set `record.id` to the candidate **email** for both entity types; the real `assessment_assigned_id` lives in `record.assessmentAssignedId`. The corporate path therefore uses `record.assessmentAssignedId` (with `record.id` as fallback) to avoid 404s. Implemented 2026-07-08; live on UAT.

### Column sorting on the assessment detail candidate table (2026-07-31)

Every sortable column in `StudentsTable` (all five attempt tabs, institute and corporate)
had `sorter: true` but the table had no `onChange` handler, so the arrows were decorative
and clicking did nothing. Sorting is now wired up **client-side**.

Why client-side: this screen calls `fetchStudentsByStatus` **without** `paginate`, so
`getAssessmentDetails` returns every candidate of the assessment, bucketed into the five
tabs, and `StudentsTable` pages it in the browser (`slice`). antd therefore only ever sees
the ten rows of the current page — if antd did the sorting it would reorder *those ten*
instead of the whole list. So:

- Columns keep `sorter: true` (antd draws the affordance and reports the click, but does
  not reorder) and add `sortValue` / `sortKind`.
- `sortOrder` is controlled from component state, so exactly one column reads as sorted.
- The full list is sorted in `src/modules/Assessment/Partials/studentSorters.js`
  (`sortRows`) **before** the page slice, and the pager resets to page 1.
- Switching attempt tabs keeps the sort when the new tab has that column (name, sent date)
  and silently drops it otherwise.

`studentSorters.js` normalises values first, because raw cell values are not comparable:

| Value kind | Rule |
|---|---|
| Dates | Parsed with moment against the formats admin-node emits (`DD MMM YYYY, h:mm A`, `DD MMM YYYY`, ISO). These are **pre-formatted strings**, so a lexical sort puts `01 Aug` before `30 Jul`. |
| Scores | Only real finite numbers count. While `scores_calculated` is false the backend puts the **status string** ("Pending") in the score fields, and those rows render `-`. |
| Behaviour proficiency | Ranked on the ladder (Beginner → Apprentice → Practitioner), not alphabetically. |
| Proctoring | Good → Poor → Evaluating, via `getProctoringLabel`, which the cell renderer also uses so the sorted value cannot drift from the shown label. |
| Blanks | Sort **last in both directions** — an unscored candidate never outranks a scored one. |
| Ties | Break by name then email, so the page slice is deterministic. |

Covered by `studentSorters.test.js` (framework-free: `node src/modules/Assessment/Partials/studentSorters.test.js`).

**Gotchas — why a sort can look broken when it is not:**
- **`ASSMT. SENT DATE` (fixed August 2026, see admin.md
  [Sent date](Assessment/admin.md#sent-date-created_at--invite_sent_at-august-2026))** used
  to be identical for every candidate on a given assessment — derived from the assessment's
  own `start_time`, not a per-candidate value, so a student added to an existing assessment
  showed the original window start as their send date. It now reads a per-assignment
  `invite_sent_at`/`created_at`, so sorting this column is meaningful again — except for rows
  from before the fix, which still fall back to the shared `start_time` and sort identically
  to each other.
- **`ASSMT. STARTED DATE & TIME` is often blank or visually identical.** ~45% of `COMPLETED`
  rows on DEV have `assessment_started_at` NULL, and candidates from one broadcast typically
  start within the same minute — the cell truncates to minutes, so seven rows can all read
  `Jul 29, 2026 05:04 AM` while their underlying timestamps differ.
- A tab with a single candidate obviously cannot reorder.

Verified on DEV 2026-07-31 against a 7-candidate Completed tab: OVERALL PERCENTAGE sorts
24.56 → 77.19 ascending and reverses on the second click, with the two rows tied at 57.89
holding name order in both directions.

`CandidateList` (the server-paginated institute/corporate-dashboard table) is a **different
component** with its own sorters and is unaffected.

> Known limitation: because the whole list is fetched, `getAssessmentDetails` runs 2–4
> sequential per-candidate queries (CEFR lookup, score fetch, proctoring logs) for every row.
> Moving bucketing/sorting/pagination into SQL is tracked as follow-up work.

### Shared Components

| Component | File | Purpose |
|-----------|------|--------|
| `AssessmentProgressBar` | `components/AssessmentProgressBar.js` | Progress bar showing sent vs taken counts (active assessments) |
| `CompletedAssessmentProgressBar` | `components/CompletedAssessmentProgressBar.js` | Progress bar for completed assessments |
| `InfoCardsUpdate` | `components/InfoCardsUpdate/cardDetails.js` | Dashboard info cards (total candidates, sent, taken, expired) |
| `AntdAvatar` | `components/Avatar/index.js` | Avatar component with letter fallback via `IconName` prop |
| `TreeSelect` | `components/TreeSelect/index.js` | Cascading tree select for filters |
| `CollegeCard` | `components/CollegeCard/index.js` | Institute card with logo and letter avatar fallback |

---

## UnifiedAssessmentTable

The core assessment listing table used by both institute and corporate dashboards.

### Props

| Prop | Type | Purpose |
|------|------|--------|
| `activeAssessments` | Array | Currently active assessments |
| `completedAssessments` | Array | Completed assessments |
| `loading` | Boolean | Spinner state |
| `filters` | Object | Current filter state |
| `onFilterChange` | Function | Called when filters change |
| `onPageChange` | Function | Called on pagination |
| `onAssessmentClick` | Function | Called when assessment name is clicked |
| `onAddCandidate` | Function | Called when "Add Candidate" button is clicked |
| `stateCityPairs` | Array | State/city pairs for geographic filters |

### Institute vs Corporate Record Handling

The table handles both institute and corporate assessment records with different field names:

| Field | Institute Record | Corporate Record |
|-------|-----------------|------------------|
| Map ID | `latestAssessmentInstituteMapId` | `latestAssessmentCorporateMapId` |
| Assessment ID | `assessmentInstituteMapId` | `assessmentCorporateMapId` |
| Name | `scheduleName` | `name` |
| Schedule details | `assessmentDetails[]` array | No assessment details (flat record) |
| Schedule ID | `scheduleId` | N/A |
| Row key | `scheduleId` | `assessmentCorporateMapId` |

### Click Flow

1. **Corporate assessments**: Passes record directly with `id = assessmentCorporateMapId` to `onAssessmentClick`
2. **Institute diagnosis** (no `latestAssessmentInstituteMapId`): Passes record with `isDiagnosis: true`
3. **Institute regular**: Finds matching detail from `assessmentDetails`, passes with `assessmentInstituteMapId` and `scheduleNumber`
4. **Upcoming with map ID**: Click blocked (greyed out)

### Parent Routing (Assessment/index.js)

- `handleDashboardAssessmentClick`: Routes institute clicks to `InstituteAssessmentDetails` (charts), corporate clicks to existing `AssessmentDetails`
- `handleDiagnosisClick`: Opens diagnosis view
- `handleAssessmentClick`: Direct assessment detail view

### Edit Assessment Drawer (EditAssessmentDrawer.js) — end-date must be parsed as UTC

`UnifiedAssessmentTable/EditAssessmentDrawer.js` lets an admin edit an assessment's
name, end date **and time**, and student list (`GET`/`PUT /assessment/details`).

**Mobile number on the add-student row (2026-08-06).** The drawer's inline "add student"
row captured only first name / last name / email — there was **no mobile field at all**,
so every student added from Edit Assessment landed with `contact_number = NULL` and
silently got an **email-only OTP** on their `/s/` invite (the resolver mints the phone
claim from `COALESCE(aas.contact_number, spp.contact_number)`). The gap ran the full
depth of the stack, so all three layers had to change:

- **Frontend** — the row is now three lines (First/Last · Email · Mobile + Add) and the
  mobile is a country-code `Select` + national-number `Input` reusing
  `utils/candidateMobile` (`countryCodeOptions`, `DEFAULT_COUNTRY_CODE`,
  `parseCandidateMobile`, `nationalNumberLength`, `formatMobile`, `splitFullMobile`) —
  the same components as `EnhancedBulkUploadDrawer`, not a second implementation.
  Mobile is **optional**, but a number that *is* typed must parse or the add is
  rejected (a mangled number is worse than none — the SMS bills and goes nowhere).
  The chosen country code persists across adds; it resets to `+91` on drawer close.
  The staged/existing student table gained a **Mobile** column. The save payload sends
  `mobile_number` + `country_code`, **omitted entirely when blank**.
- **Request schema** — `updateAssessmentDetailsSchema.body.addStudents.items` now
  declares `mobile_number` and `country_code`.
- **Model** — `updateEditableAssessmentDetails`'s `addStudents → bulkUploadData` mapper
  builds each row from an **explicit field list**, so anything it doesn't name is
  dropped before `addStudentsToExistingAssessment` ever sees it. That is what silently
  ate the mobile. It now passes the raw code + number pair through; the add path already
  normalizes it (`pickPhone` → `contact_number`, `pickNationalNumber`/`pickCountryCode`
  → `createPublicStudent`). `getEditableAssessmentDetails` also returns each row's stored
  `contactNumber` as `mobile` so the drawer can render the new column on load.

Regression cover: `admin-node/test/editAssessmentAddStudentsMobile.spec.js` locks down the
schema keys, the mapper (source-level — the method is too Prisma-heavy to run without a
DB), and the exact payload the drawer sends, including a non-Indian code and the
no-mobile case. Deployed DEV + UAT 2026-08-06. **Forward-only** — no backfill; the edit
drawer does not persist a roster, so pre-fix additions are unrecoverable.

> The separate **Add Candidate** flow (`EnhancedBulkUploadDrawer`, reachable from the
> same table row and from the three dashboards) already carried the mobile end-to-end —
> only this drawer's inline row was missing it.

**End date + time picker (June 2026):** the End field is an Ant `DatePicker` with
`showTime` (12-hour `hh:mm A`, `format="DD/MM/YYYY hh:mm A"`) — admins can pick the exact
end time, not just the date. On save the drawer sends the full wall-clock value
`endDate.format('YYYY-MM-DDTHH:mm:ss')` (no timezone), and change-detection compares at
**minute** granularity (`isSame(moment.utc(original.endTime), 'minute')`). The backend
(`updateEditableAssessmentDetails`) parses the `hh:mm[:ss]` and stores `…T${time}Z` under
the same IST-wall-clock-as-UTC convention; date-only payloads still default to `23:59:59Z`.

**Timezone gotcha (fixed June 2026):** the backend stores assessment end times as
**IST wall-clock written as UTC** (e.g. choosing 18 Jun is saved as
`2026-06-18T23:59:59Z` — see `Assessment/admin.md` → *Timezone convention*). The drawer
prefilled the DatePicker with `moment(data.endTime)`, which parses that timestamp in the
**browser's IST** and rolls it to **19 Jun** (`05:29 AM`); re-saving then sent the wrong
date and the drift compounded each edit. Fix: prefill and change-detection use
**`moment.utc(...)`** (`moment.utc(data.endTime)` for the picker value;
`moment.utc(original.endTime)` in the `isSame(..., 'day')` diff) so the displayed/saved
date matches the stored convention.

**Same gotcha in the list/table display (also fixed June 2026):** the assessment
list renders these dates **client-side**, not server-side. The `formatDate` helpers in
`UnifiedAssessmentTable/index.js`, `UnifiedAssessmentTable/ExpandableContent.js`, and
`CompletedAssessmentTable/index.js` used `new Date(x).toLocaleDateString('en-GB', …)`
in the browser's IST, so `2026-06-22T23:59:59Z` displayed as **23 Jun**. Fix: pass
`timeZone: 'UTC'` to `toLocaleDateString`. The inline `EndDateEditPopover` (in
`ExpandableContent.js`, edits a schedule run's end date via
`PUT /assessment/schedule/assessment-enddate`) likewise had its prefill switched to
`moment.utc(currentEndDate)`.

**Schedule-row end-date popover now has a time picker (July 2026, `hotfix/assessment-tz-sync`):**
the inline `EndDateEditPopover` in `ExpandableContent.js` (the pencil next to each
assessment run in an expanded schedule row) was previously **date-only** and its backend
forced `23:59:59` in **server-local (IST)** time — i.e. it re-introduced the exact
`…T18:29Z` early-expiry bug for any run whose end date was edited there. Now the picker
uses `showTime` (12-hour `hh:mm A`, default `23:59`, `format="DD/MM/YYYY hh:mm A"`) and
sends the full wall-clock value `newEndDate.format('YYYY-MM-DDTHH:mm:ss')`. The backend
(`updateAssessmentEndDate`, admin-node `Assessment.js`) now parses the optional
`hh:mm[:ss]` and stores `${date}T${time}Z` (date-only still defaults to `23:59:59`),
matching every other assign/edit path; the schema (`updateAssessmentEndDateSchema`) was
relaxed from `format: "date"` (which would reject a datetime) to a plain string. The
past-date guard was swapped for a `newEnd <= startTime` check.

**More spots fixed July 2026 (`hotfix/assessment-tz-sync`):** the June pass missed several
renderers. Now also UTC: `ActiveAssessmentTable/index.js` `formatDate`, `AssessmentNavBar.js`
schedule-item date, and `EndDateEditPopover`'s `onOpenChange` (it re-seeded the picker with
bare `moment(currentEndDate)`, undoing the correct `useState` init). In `StudentsTable`,
`formatDateOnly` now renders sent/start/end in UTC, but a **new `formatEventDateOnly`** keeps
`startedDateTime` / `droppedOffDateTime` in **browser-local** time — those are genuine event
instants (real UTC timestamps of when the student acted), NOT the wall-clock-as-UTC schedule
convention, so they must be shown local, not UTC. (institute-react's `StudentsTable`,
`UnifiedAssessmentTable` index/`ExpandableContent`, `AssessmentNavBar`, `FullStudentReport`
got the same treatment; its `CustomDateCalendarDrawer` was deferred — its calendar-cell
compare logic needs reworking as a unit.)

**Rule:** any code that renders assessment map `start_time`/`end_time` client-side must
parse/format in **UTC** (`moment.utc(...)` or `timeZone: 'UTC'`), never browser-local.
**But real event timestamps** (`assessment_started_at`, dropped-off time, `submittedAt`,
proctoring capture times) are true UTC instants → render **local**, not UTC. (Schedule
`scheduleStartDate`/`scheduleEndDate` are stored at **midnight UTC**, so `moment(...)`
doesn't roll them — `EditScheduleDrawer` is unaffected.)

### Published-assessment configuration in the edit drawer (August 2026)

The drawer now shows the **configuration the assessment was published with** — CEFR level
and accent, aptitude topics and difficulty, the Role_Based job brief, the AI_Interview
interview brief, Custom_Assessment section weights — and re-opens the subset of it that
still has an effect. It sits between "End Date & Time" and "Student List".

**Backend:** `admin-node/app/service/AssessmentConfigService.js`, surfaced on the existing
`GET /assessment/details` as a `configuration` object and accepted back on
`PUT /assessment/details` as a `configuration` patch.

**The response is field-descriptor shaped, not a per-type DTO:**

```
configuration: {
  assessmentType, contentLocked, lockedReason,
  groups: [ { key, title, fields: [ { key, label, value, type, editable, help?, options?, min?, max?, unit? } ] } ]
}
```

`type` is one of `text | textarea | number | select | boolean | tags | list`. The React
side (`UnifiedAssessmentTable/AssessmentConfigurationSection.js`) names **no assessment
type at all** — it renders whatever groups the server sends, so a new assessment type
appears in the UI without a frontend change. Editability rules live only in the service,
where they are also enforced on write.

**What is editable, and why — question papers are generated AT PUBLISH TIME.** Editing the
inputs that produced them (CEFR level, accent, aptitude topics, difficulty, custom section
weights) would change nothing about the paper candidates already hold; it would only make
the record lie. So those are read-only, and the drawer shows `lockedReason` explaining it.
Three things ARE read after publish and stay editable:

| Scope | Editable fields | Why it still applies |
|---|---|---|
| **All types** (map row) | `allowProctoring`, `allowVerification`, `instructions` | Read when the candidate opens the assessment |
| **Role_Based** (`assessment_config`) | `jobDescription`, `skills`, `industryDomain`, `region`, `durationMinutes` | `durationMinutes` drives the attempt-time timer; the rest feed subjective scoring (student-node `RoleBasedCalculations.calculateSubjectiveScore`) |
| **AI_Interview** (`ai_interview_config`) | `jobDescription`, `skills`, `industryDomain`, `region`, `interviewDurationMinutes`, `maxQuestions`, `resumePolicy`, `enableFollowUp`, `questionGuidance`, `scoringGuidance` | Nothing is pre-generated — the interviewer reads this row live for every candidate |

Read-only everywhere else, including Communication, Hinglish, Aptitude, Custom_Assessment
and Behavior, plus `roleName`/`seniority`/`aiModel`/`conversationRubric`/
`evaluationParameters` (the rubric is authored in the AI Interview builder, not here).

**Gotchas worth knowing:**
- **Writes fan out to every set on the map**, not just the representative one. One
  Communication map can reach ~70 sets and one Role_Based map ~13 (one per batch of
  students); updating only the first would leave candidates scored against different job
  briefs. `assessment_config` is **upserted** per set because older Role_Based sets predate
  the table and an update-only write would silently drop the edit.
- **The config patch is applied FIRST**, before name/end-date/roster, so a rejected value
  (bad interview length, out-of-range question count) aborts the save with everything else
  untouched.
- **`interview_duration` is stored in seconds** but shown and edited in minutes (10–30);
  `max_questions` is clamped 8–15, matching the create form.
- **Unknown keys are ignored, not rejected** — a stale tab must not fail an otherwise valid
  save. The drawer also diffs against the loaded values
  (`UnifiedAssessmentTable/assessmentConfigDiff.js`) and sends only touched fields, so an
  untouched drawer can never overwrite a job description.
- **Clearing "Candidate instructions" deletes the `communication_instructions` row** — the
  column is `NOT NULL`, so "no instructions" means no row.
- **Config loading is wrapped in try/catch** in `getEditableAssessmentDetails`: it is
  additive, so an assessment whose config tables predate a column drops the section rather
  than failing the whole drawer.
- **Aptitude topics** come from `assessment_sets.selected_sub_section_ids` when recorded,
  falling back to deriving them from the generated paper for sets created before that
  column existed.

---

## Student Report Drawer (StudentReport/index.js)

### Props

| Prop | Type | Purpose |
|------|------|--------|
| `visible` | Boolean | Drawer visibility |
| `student` | Object | Student data with scores |
| `isDiagnosis` | Boolean | Whether this is a diagnosis report |
| `onClose` | Function | Close handler |

### Score Format Handling

The component handles two data formats:

**New format** (`sectionScores` object):
```javascript
student.sectionScores = {
  reading: { average: 75 },
  listening: 80,
  critical: { average: 65 },
  quantitative: 70,
  logical: { average: 60 }
}
```

**Old format** (flat fields):
```javascript
student.englishVerbalScore = 75
student.readingAbilityScore = 80
```

The `getScore(newKey, oldKey)` helper checks `sectionScores` first, falling back to flat fields.

### Assessment Type Detection

- **Communication**: Default when not aptitude, role-based, or custom
- **Aptitude**: Detected if `student.aptitudeScores` exists OR `sectionScores` contains keys like `critical`, `quantitative`, `logical`
- **Role_Based**: Detected if `student.roleBasedScores` exists OR `student.assessmentType` contains `role_based`/`rolebased`
- **Custom_Assessment**: Detected if `student.customAssessmentScores` exists OR `student.assessmentType` contains `custom`
- **Behavior**: Detected if `student.behaviorScores` exists OR `student.assessmentType` contains `behavior`

### Aptitude Score Cards

Priority order for aptitude data:
1. `student.aptitudeScores` object (has `criticalReasoningPercentage`, `quantitativePercentage`, `logicalReasoningPercentage`)
2. `student.sectionScores` mapped: `critical` -> Critical Reasoning, `quantitative` -> Quantitative Ability, `logical` -> Logical Reasoning
3. Fallback to empty

### Diagnosis Report

When `isDiagnosis = true`:
- Checks `assessmentAssignedId1` and `assessmentAssignedId2` for report availability
- Shows dropdown button with "Assessment #1" / "Assessment #2" options
- `handleDownloadReport(assignedId)` downloads the specific assessment report

---

## NPS Score Columns

NPS (Net Promoter Score) columns are displayed in `TpoStudentListTable`:

| Column | Field | Source |
|--------|-------|--------|
| COMM. NPS | `communicationNPS` | `student-node/app/models/TpoDashBoard.js` |
| APT. NPS | `aptitudeNPS` | `student-node/app/models/TpoDashBoard.js` |

Both columns are sortable. Backend sorting is server-side (sorts ALL students before pagination, not just current page). Any sort field except 'name' triggers global processing — all matching students are sorted before pagination.

## Assessment Student List Columns

When viewing a specific assessment's student list (`CandidateList`), the backend (`getStudentListForAssessment` in `TpoDashBoard.js`) returns these key fields:

| Column | Field | Source | Notes |
|--------|-------|--------|-------|
| **Progression Level** | `currentLevel` / `currentLevelDisplay` | `ProgressionHistory.assessmentCefr` or `assessmentAptitudeLevel` | Scoped by `assessmentAssignedId` — shows level for THIS assessment, not latest. A2 record preferred, fallback to A1 |
| **Assigned Level** | `assignedLevel` | Communication: previous `ProgressionHistory.suggestedCefr` or `assessmentSet.cefrLevel`. Aptitude: `assessmentSet.difficulty` | For non-diagnosis communication, uses `suggestedCefr` from previous A2 progression record to reflect what actually drove the test set assignment |
| **NPS** | `communicationNPS` / `aptitudeNPS` | `ProgressionHistory` scores | Same scoping as progression level |
| **Status** | `status` | `assessmentAssignedStudent.status` | Pending, Attempted, Completed |
| **Proctoring** | `proctoring` | `proctoringLog.isValid` | Good/Bad based on face detection |

### Backend (student-node)

In `TpoDashBoard.js`, the NPS fields are included in the formatted student response:
```javascript
communicationNPS: nps.communicationNPS != null ? Math.round(nps.communicationNPS * 100) / 100 : null,
aptitudeNPS: nps.aptitudeNPS != null ? Math.round(nps.aptitudeNPS * 100) / 100 : null,
```

---

## Pagination

The student list API (`student-node/TpoDashBoard.js`) returns flat pagination fields:
```javascript
{
  students: [...],
  totalCount: 150,
  pageNumber: 1,
  pageSize: 10
}
```

Frontend extracts these directly (NOT nested under `data.pagination`):
```javascript
setPagination({
  pageNumber: data?.pageNumber || page,
  totalCount: data?.totalCount || 0,
  pageSize: data?.pageSize || 10,
})
```

---

## Institute & Corporate List Avatars

Both institute and corporate lists use the same `AntdAvatar` component from `components/Avatar`:
```jsx
<AntdAvatar
  src={record.logoUrl}
  IconName={record.name?.charAt(0)?.toUpperCase()}
  size={40}
/>
```

This provides an image avatar with letter fallback when no logo URL is available.

---

## API Endpoints Used

| Endpoint | Method | Purpose | Source |
|----------|--------|---------|--------|
| `/assessment/admin/institutes` | GET | List subscribed institutes | admin-node |
| `/assessment/admin/corporates` | GET | List corporates | admin-node |
| `/assessment/admin/active` | GET | Active assessments for entity | admin-node |
| `/assessment/admin/completed` | GET | Completed assessments for entity | admin-node |
| `/assessment/admin/details` | GET | Assessment student details | admin-node |
| `/assessment/tpo/students` | GET | TPO student list with NPS | student-node |
| `/assessment/report/download` | GET | Download student report PDF | student-node |
| `/assessment/addStudentsToAssessment` | POST | Add candidates to existing assessment | admin-node |
| `/assessment/backfill-progression` | POST | Backfill progression data | student-node |
| `/assessment/details` | GET | Edit-drawer payload: name, end date, roster **and published `configuration`** | admin-node |
| `/assessment/details` | PUT | Edit name / end date / roster / whitelisted `configuration` fields | admin-node |

---

## Add Candidate on the global Active Assessments list (July 2026)

The **Add Candidate** action — previously only in the per-institute / per-corporate drill-down (`UnifiedAssessmentTable`) — is now also on the **global Active Assessments list** (`admin-react` `Partials/ActiveAssessmentTable/index.js`, rendered from `Assessment/index.js` when `activeTable === 'active-assessment'`), for **both** the College and Corporate entity toggles.

- **Where:** a new `ACTIONS` column with a `UserAddOutlined` icon-button (same style as the drill-down). It calls `onAddCandidate({ ...record, entityType })`, where `entityType` is the parent's current College/Corporate toggle (authoritative — the list shows one entity type at a time).
- **Reuse:** the parent (`Assessment/index.js`) reuses the exact same `EnhancedBulkUploadDrawer` (`mode="addCandidate"`) + `utils/bulkAddStudentsToAssessment` → `POST /assessment/addStudentsToAssessment` as the dashboards. No new UI or endpoint.
- **Payload:** college → `{ entityType: 'college', assessmentInstituteMapId: record.id }`; corporate → `{ entityType: 'corporate', assessmentCorporateMapId: record.id }` (each row's `id` **is** the map id).
- **Origin routing is fully backend-driven.** `admin-node` `addStudentsToExistingAssessment` resolves the flow from the map id alone: college map with a `scheduleId` → `_addStudentsToScheduledAssessment` (added to the schedule roster + schedule invite); college map without → `_addStudentsToOneTimeAssessment` (institute portal activation); corporate → one-time honoring the map's `is_otp_invite` flag (OTP no-login vs email+password portal). The frontend never branches invite logic.
- **Schedule dialog (schedule rows only):** for a **college** row whose `scheduleId` is non-null, `handleActiveAddCandidate` shows an `antd` `Modal.confirm` ("added to the schedule roster…") **before** opening the drawer; all other origins open the drawer directly. This needs the `scheduleId`/`instituteId`/`instituteCampusId` fields added to `getActiveAssessments` (college branch) — see `Assessment/admin.md`. The degree picker in the drawer is fed by `instituteId`/`instituteCampusId` from the row.

---

## Passing Year Race Condition (yearLoaded Pattern)

Both `InstituteAssessmentDashboard.js` (admin-react) and `Assessment/index.js` (institute-react) use a `yearLoaded` state gate to prevent API calls before the passing year is fetched and set.

**Problem:** React 17 does NOT batch setState in async callbacks. Without guards, effects fire with `selectedYear=''`, fetching all years' data and mixing results.

**Pattern:**
```javascript
const [selectedYear, setSelectedYear] = useState('')
const [yearLoaded, setYearLoaded] = useState(false)

// 1. fetchYearList sets selectedYear AND yearLoaded (no selectedYear in useCallback deps)
const fetchYearList = useCallback(async () => {
  const years = await fetchYears()
  setSelectedYear(defaultYear)  // set BEFORE yearLoaded
  setYearLoaded(true)           // gate opens
}, [instituteCampusId])          // NO selectedYear in deps

// 2. Reset on institute change
useEffect(() => {
  setYearLoaded(false)
  fetchYearList()
}, [instituteCampusId])

// 3. ALL API-calling effects AND callbacks guard on BOTH yearLoaded AND selectedYear
useEffect(() => {
  if (instituteId && yearLoaded && selectedYear) { fetchData() }
}, [instituteId, selectedYear, yearLoaded, fetchData])

// 4. Callbacks also guard internally (belt-and-suspenders for React 17)
const fetchData = useCallback(async () => {
  if (!instituteId || !selectedYear) return  // internal guard
  // ... API call with passingYear: selectedYear
}, [instituteId, selectedYear])
```

**Key rules:**
- `fetchYearList` must NOT have `selectedYear` in its useCallback deps (causes infinite loop)
- `setYearLoaded(true)` must be in the `finally` block (after `setSelectedYear`)
- Every effect and callback that uses `selectedYear` must guard on both `yearLoaded` AND `selectedYear`
- Internal guards inside callbacks prevent calls with empty year even if effects fire unexpectedly

---

## CandidateList — Dynamic Columns for Non-Standard Types

Both `admin-react` and `institute-react` `CandidateList/index.js` dynamically generate table columns for assessment types beyond Communication/Aptitude:

### Column Extraction
- **Role_Based**: Columns are the sections **SELECTED at creation** (per-section question count > 0), not a fixed MCQ/Subjective/Video/Coding set. The backend returns this list as `assessmentInfo.roleBasedSections` (`[{ key, label, sectionName }]`, canonical order MCQ → Subjective → Video → Coding); a section configured with 0 questions never gets a column, and a selected section **always** shows a column — even before scores are calculated (renders `-`). Shared resolver `src/modules/Assessment/Partials/roleBasedColumns.js` (`resolveRoleBasedSectionColumns`) is used by both `StudentsTable` and `CandidateList`; it falls back to the role-based score keys present on the rows (ignoring `overallScore` and the `videoDetailedScores`/`videoTotalQuestions` metadata keys) when the API list is absent.
- **Behavior**: still fully dynamic — extracts competency column keys from `sectionScores`/`roleBasedScores` across all rows (excludes `overallScore`).
- **Custom_Assessment**: Uses fixed columns: `Gained Marks`, `Total Marks`, `Percentage`.
- Role-based values render from `r.roleBasedScores?.[key]` (number → shown, `null` → `-`).

### Total Score Column
Falls back across multiple sources:
```javascript
r.totalScore ?? r.totalAvgScore ?? r.roleBasedScores?.overallScore ?? r.customAssessmentScores?.percentage
```

### Charts / Graphs
- **Only shown for Communication and Aptitude** assessment types
- `admin-react/InstituteAssessmentDetails.js`: guards `<AssessmentCharts>` with `['communication', 'aptitude'].includes(assessmentType)`
- `institute-react/AssessmentDetails/index.js`: uses `isStandardType` flag (same check)

### Assigned Difficulty & Progression Level
- **Only shown for Communication and Aptitude** assessment types
- For Role_Based, Custom, Behavior, AI_Interview, etc. these columns are hidden in the table
- Controlled by `isStandardType` check in CandidateList column definitions

### Data Sources
- **Communication/Aptitude**: student-node `specific-assessment-student-list` API → returns `sectionScores`, `totalScore`
- **Other types (Role_Based, Custom, Behavior)**: admin-node `getAssessmentDetails` API → returns `roleBasedScores`, `customAssessmentScores`, `behaviorScores`
- Admin-node returns different field names than student-node (e.g., `roleBasedScores: { mcqScore, subjectiveScore, videoScore, overallScore }` vs `sectionScores: { mcq, subjective, video }`)

---

## Assessment Heading Display

Both `admin-react/InstituteAssessmentDetails.js` and `institute-react/AssessmentDetails/index.js` construct the page heading differently for standard vs non-standard assessment types:

```javascript
{(assessment.isOneTime || assessment.isStandalone || !isStandardType)
  ? (assessment.scheduleName && assessment.scheduleName !== 'N/A'
      ? assessment.scheduleName : assessment.name || 'Assessment')
  : `${assessment.scheduleName}-schedule-${assessment.scheduleNumber || 1}`}
```

- **Standard types** (Communication/Aptitude): Shows `{scheduleName}-schedule-{scheduleNumber}` format
- **Non-standard types** (Role_Based, Custom, etc.): Shows assessment name directly (no schedule suffix)
- **One-time assessments**: Shows assessment name directly
- **Fallback chain**: `scheduleName` -> `name` -> `'Assessment'`

---

## Subscription Filtering on Institute/Corporate Lists

The Assessment module's institute and corporate lists only show **subscribed** entities.

### ActiveCollegeList (`Partials/ActiveCollegeList/index.js`)

Uses admin-node API (NOT ElasticSearch):
```javascript
const params = { pageNo: page, pageLimit, searchBy, order, sort, type_name, isSubscribed, isTrial, states, cities }
const response = await axios.get(`${baseUrl}/assessment/getSubscribedInstitutes`, { params })
```

**ID mapping:** The response maps to `instituteCampus` array with `id` field set to `institute_campus_id || institute_id` — this `id` is required for the dashboard's API calls to fire correctly.

**Pagination with search:** Uses `data.currentCount` (filtered count) for pagination total, falling back to `data.count` (unfiltered total). This ensures "Showing X of Y" reflects search results, not total count.

### ActiveCorporateList (`Partials/ActiveCorporateList/index.js`)

Uses admin-node API:
```javascript
const response = await axios.get(`${baseUrl}/assessment/getSubscribedCorporates`, { params })
```

### Admin-Node Subscription Endpoints
- `GET /assessment/getSubscribedInstitutes` — fetches institutes with assessment subscriptions (deduplicated by `institute_id`)
- `GET /assessment/getSubscribedCorporates` — fetches corporates with assessment subscriptions (deduplicated by `corporate_id`)
- `GET /assessment/getSubscribedAssessmentByInstitute` — assessments for a specific subscribed institute
- `GET /assessment/getSubscribedAssessmentByCorporate` — assessments for a specific subscribed corporate

### Institute ID vs Institute Campus ID

**Critical distinction:** The admin API returns both `institute_id` and `institute_campus_id`. These serve different purposes:
- `institute_id` — used for API calls to fetch assessments (`getSubscribedAssessmentByInstitute`, `getschedulesInfo`)
- `institute_campus_id` — used as the `id` in `instituteCampus` array for dashboard navigation

In `InstituteAssessmentDashboard.js`, ID extraction follows this pattern:
```javascript
const instituteId = institute?.institute_id || institute?.id          // For API calls
const instituteCampusId = institute?.instituteCampus?.[0]?.id || institute?.id  // For dashboard display
```

---

## ExpandableContent — Diagnosis Row Guard

**File:** `UnifiedAssessmentTable/ExpandableContent.js`

Diagnosis rows in expandable assessment schedule content are **only shown for Communication and Aptitude** types:
```javascript
const hasDiagnosis = ['communication', 'aptitude'].includes(normalizedType)
```
Other assessment types (Role_Based, Custom, etc.) skip the diagnosis row entirely since they don't use the scheduling/diagnosis infrastructure.

---

## Key Design Patterns

- **Unified Table**: `UnifiedAssessmentTable` handles both institute and corporate records by checking for entity-specific field names
- **Dual Score Format**: Student reports support both `sectionScores` (new) and flat score fields (old) for backward compatibility
- **Multi-Type Score Sources**: CandidateList checks `sectionScores`, `roleBasedScores`, and `customAssessmentScores` for compatibility across both APIs
- **AntdAvatar Pattern**: Both institute and corporate lists use the same avatar component with letter fallback
- **Redux + Connect**: Module uses `connect()` pattern with `actions.js`, `reducers.js`, `selectors.js`
- **Styled Components**: Shared styles in `Style/style.js` (CustomStyledTable, SearchSection, etc.)
- **Server-Side Sorting**: NPS and other column sorts send `sortBy` to API; backend sorts all records before pagination
- **yearLoaded Gate**: See "Passing Year Race Condition" section above

---

## Corporate Assessment Dashboard (`Partials/ActiveCorporateList/CorporateAssessmentDashboard.js`)

This is a **separate stack** from the institute candidate list — it does NOT use admin-node `getAssessmentDetails`. Its candidate list is fetched from **student-node** `POST /students/assessments/corporate/student-list/:corporateId` (`getStudentListForCorporateAssessment` in `TpoDashBoard.js`), and it builds its own table columns inline.

- **Role-based columns**: the table shows a column per section **selected at creation** (question count > 0), keyed by the lowercase section name (`mcq question` / `subjective question` / `video response` / `coding question`). The endpoint returns `roleBasedSections` (`[{ key, label }]`) via the helper `app/helpers/roleBasedCorporateSections.js` (`selectedCorporateRoleBasedSections`, from `assessment_config.question_config`; fallback to sections present in `role_based_scores`). The frontend renders those columns (fallback: row `sectionScores` keys) so they show — including **Coding** — even before scoring (`-`). Per-row scores live on `r.sectionScores` (only populated when scored), NOT `roleBasedScores` (that's the institute/admin-node shape).
- **Status filter**: a multi-select (Completed / In Progress / Pending / Dropout) sends `statusFilter` (array) in the POST body; student-node filters server-side by the assignment `status` enum (NULL → submitted/attempted fallback) **before pagination** (helper `app/helpers/corporateStatusFilter.js`).
- **Export**: reuses admin-node `GET /assessment/exportStudentData?entityType=corporate` (the same Excel builder as institute, so it includes the role-based section columns incl. Coding). One selected status exports that bucket; otherwise exports all (`status=sent`).

## AssessmentNavBar — visibility for expired schedules

`Partials/ActiveCollegeList/components/AssessmentNavBar.js` is the switcher that lets you move between the assessments in a schedule (Diagnosis + each run) from the detail view, gated by `navList.length > 1` in `InstituteAssessmentDetails.js`. Its internal `isItemVisible` filter hides only **`Upcoming`** runs and shows ongoing/completed/**expired** runs (`Expired - Completed` / `Expired - Lapsed`). It previously allowed only `completed`/`ongoing`, which hid the entire bar once a schedule's runs had expired (all runs filtered out → only Diagnosis left → `visibleItems.length <= 1` → renders `null`). Backend run statuses come from institute-node `StudentListInfo.js` (`Upcoming` / `Ongoing` / `Expired - Lapsed` / `Expired - Completed`).

## Gotcha: assessment start/end dates showed a bogus "6:30 PM" (fixed 2026-07-09)

In the Active Assessment student table (`admin-react` `Partials/Assessment/StudentsTable`), the **ASSMT. START & END DATE** / **ASSESSMENT SENT DATE** columns rendered e.g. `Jul 12, 2026 06:30 PM – Jul 20, 2026 06:30 PM`. The DB window was correct (`start 00:01Z`, `end 23:59Z` = the intended IST full-day window). Two-layer bug:

1. **Backend** `admin-node getAssessmentDetails` built the strings with `moment(assessment.startTime/endTime).format("DD MMM YYYY")`. `start_time`/`end_time` are **IST-wall-clock-labelled-UTC**, so the server's IST render pushed the end **+1 day** (`23:59Z` → `"21 Jul"`). Fixed by using **`moment.utc(...)`** for those assessment start/end dates (real-instant fields — started/dropped/attempted — keep local `moment`). Sort (which parses `sentDate` as `"DD MMM YYYY"`) and the Excel export are unaffected — still get date strings.
2. **Frontend** `StudentsTable.formatDateOnly` then re-parsed the bare `"21 Jul 2026"` via `new Date()` (browser-IST midnight) and rendered with `timeZone:'UTC'` → shifted **−5:30** → `"Jul 20, 2026 06:30 PM"`. Fixed: render the already-formatted string **as-is**; only genuine ISO timestamps get UTC date formatting.

Result: `13 Jul 2026 – 20 Jul 2026`. "Everywhere else was fine" because other tables receive **raw ISO timestamps** (`00:01Z`) that the UTC render handles correctly — only this endpoint pre-formats the dates as strings.
