# Assessment Scheduling

> Assessment Scheduling enables **recurring, automated assessment assignments** for student groups. Admins configure a schedule with frequency dates, student lists, and assessment parameters. A cron job runs every 30 minutes to check for due schedules and auto-assigns assessments to students.

---

## Overview

| Property | Value |
|---|---|
| **Supported Types** | Communication, Aptitude (only these two use schedules) |
| **Frequency** | Admin-defined date list (specific dates in `YYYY-MM-DD`) |
| **Cron Interval** | Every 30 minutes |
| **Concurrency** | Database-level locking (`FOR UPDATE SKIP LOCKED`) |
| **Deduplication** | `lastRunAt` check prevents same-day re-runs |
| **Lock Timeout** | 5 minutes (stale locks auto-released) |

---

## End-to-End Flow

1. Admin creates a schedule via the frontend (assessment type, config, student list, frequency dates, validity period)
2. Schedule saved to `assessment_schedules` table with `frequencyValue` (array of `YYYY-MM-DD` dates)
3. Cron job runs every 30 minutes via `AssessmentScheduler.start()` → `dailySchedulingJob`
4. `AssessmentSchedulerService.processScheduledAssessments()`:
   - Fetches active schedules where today is within `[scheduleStartDate, scheduleEndDate]`
   - Acquires atomic DB lock per schedule (prevents concurrent processing)
   - Checks `lastRunAt` to skip already-processed schedules for today
   - Checks `frequencyValue` — if today's date is in the list, schedule is due
   - Assigns the assessment to all students in the student list
   - Sets validity: `startDate = today`, `endDate = today + assessmentValidityDays`
   - Updates `lastRunAt` and releases lock on success
5. Students receive the assessment in their active assessments list

---

## File Reference

### 1. Scheduler Entry Point

**File:** `admin-node/script/assessmentCronWorker.js`

```javascript
const AssessmentScheduler = require('./scheduler');
const scheduler = new AssessmentScheduler();
scheduler.start();
```

Simple entry point — instantiates the scheduler and starts cron jobs. Handles graceful shutdown on `SIGINT`.

---

### 2. Scheduler — `scheduler.js`

**File:** `admin-node/script/scheduler.js`

**`AssessmentScheduler` class** — manages all cron jobs. For scheduling:

```javascript
// Active cron — runs every 30 minutes
this.dailySchedulingJob = cron.schedule('* * * * *', async () => {
  const now = new Date();
  const isNow = now.getUTCMinutes() + 30;
  if (isNow % 30 !== 0) return;  // Only run every 30 min
  
  await this.assessmentSchedulerService.processScheduledAssessments();
});
```

Also includes a `testScheduledAssessments()` method for manual testing that lists all schedules and processes them.

---

### 3. Assessment Scheduler Service — `AssessmentSchedulerService.js`

**File:** `admin-node/script/AssessmentSchedulerService.js`

**`AssessmentSchedulerService` class** — core scheduling logic.

#### `processScheduledAssessments()`

Main processing loop:

1. **Fetch due schedules** via raw SQL with `FOR UPDATE SKIP LOCKED`:
   ```sql
   SELECT * FROM assessment_schedules
   WHERE is_active = true
     AND schedule_start_date <= today
     AND schedule_end_date >= today
     AND (processing_lock IS NULL OR lock_acquired_at < NOW() - '5 minutes')
   ORDER BY id
   LIMIT 10 OFFSET {offset}
   FOR UPDATE SKIP LOCKED
   ```

2. **Per-schedule processing:**
   - Acquire atomic lock (`processing_lock = instanceId`)
   - Check `lastRunAt` — skip if already ran today
   - Parse `frequencyValue` — check if today's date `YYYY-MM-DD` is in the array
   - Validate student list is non-empty
   - Route to type-specific handler

3. **Communication Assignment:**
   - Calls `assignCommunicationAssessment()` with full config (CEFR level, domain, proctoring, dates)
   - Links created `assessmentInstituteMap` back to the schedule via `scheduleId`

4. **Aptitude Assignment:**
   - Calls `assignAptitudeAssessment()` with full config (aptitude type, subtopics, difficulty, negative marking)
   - Handles multiple assessment maps (main + up to 2 diagnosis assessments)
   - Links all created maps to the schedule

5. **Post-processing:**
   - Updates `lastRunAt = now` and releases lock
   - Prints comprehensive summary (processed/skipped/failed/locked counts)

#### Soft-removed students — `is_active` flag on the roster (2026-07-03)

Each student object in `assessment.student_lists.students_data` may carry an **`is_active`** boolean. It is a **soft-delete**: to stop a student from receiving *further* assessments without deleting their roster entry, scores, or history, set `is_active: false` on their object. **Absent or `true` = active; only `is_active === false` is skipped.**

The guard lives at the single choke point every assignment path funnels through — **`getAssessmentAssignedParticipants`** in `admin-node/app/models/Assessment.js` (and the byte-identical `admin-node-assignq` copy) — which filters `bulkUploadData` to `is_active !== false` before turning the roster into `assessment_assigned_students` rows. So it covers the **recurring scheduler**, the initial diagnosis assign on create, and add-students. The **end-date-extension** path (`updateAssessmentEndDate`) re-assigns directly and bypasses that choke point, so it has its own `is_active === false` skip in the roster filter.

- **Only assignment (write) paths filter.** All display/read paths (`getschedulesInfo`, the drill-in candidate list, scores, history) ignore the flag and show everyone — the roster keeps all students.
- **Role_Based and AI_Interview do NOT go through `getAssessmentAssignedParticipants`** (they build participants separately), so they are unaffected by the flag.
- Corporate and one-time/manual triggers pass freshly-uploaded students with no `is_active` field → the filter is a no-op for them.
- On DEV the recurring cron runs inside the unified `admin` container (same image as the API); on UAT likewise. There is no separate assignq container on DEV/UAT, so deploying `admin-node` covers both the API and the cron worker.

First use: PROD Naralkar Institute — 39 students soft-removed from its 2 passingYear-2026 Communication/Aptitude schedule lists (18 kept active) so future runs stop assigning them while their completed attempts/scores remain.

#### Concurrency Safety

- **Instance ID:** `instance-{PID}-{timestamp}` — unique per process
- **Atomic lock:** Single raw SQL `UPDATE ... WHERE lock IS NULL RETURNING id`
- **Stale lock release:** Locks older than 5 minutes are ignored
- **Batch processing:** 10 schedules per query, paginated with offset

#### `#isAssignmentDueToday(schedule, today)`

Simple date matcher: `frequencyValue.includes(today.format('YYYY-MM-DD'))`

---

### 4. Admin Frontend — Schedule Creation

**File:** `admin-react/src/modules/Assessment/Partials/CreateAssessment/AssessmentSelect.js`

The assessment creation form supports "Scheduled" distribution mode:

- **Schedule Name** — unique identifier for the schedule
- **Frequency Dates** — admin selects specific dates when the assessment should be assigned (stored as `frequencyValue` array)
- **Schedule Period** — `scheduleStartDate` and `scheduleEndDate` define the active window
- **Validity Days** — how many days students have to complete each assigned assessment (`assessmentValidityDays`)
- **Student List** — can use saved student lists or bulk upload
- **Assessment Config** — same type-specific config (CEFR level for communication, difficulty for aptitude, etc.)
- Supports both Communication and Aptitude assessment types

---

## Database Schema

### `assessment_schedules` Table

| Column | Type | Purpose |
|--------|------|--------|
| `id` | UUID | Primary key |
| `schedule_name` | String | Admin-defined name |
| `assessment_type` | String | `"Communication"` or `"Aptitude"` |
| `assessment_config` | JSON | Type-specific configuration (name, instructions, domain, CEFR level, difficulty, proctoring, etc.) |
| `entity_id` | UUID | Institute or corporate ID |
| `entity_type` | String | `"college"` or `"corporate"` |
| `frequency_value` | JSON (Array) | Array of `YYYY-MM-DD` date strings when assessments should be assigned |
| `schedule_start_date` | Date | Schedule active start |
| `schedule_end_date` | Date | Schedule active end |
| `assessment_validity_days` | Integer | Days students have to complete (used to set `endDate = today + validity`) |
| `student_list_id` | UUID | FK → `student_lists` table |
| `created_by` | String | Admin email or `"system-scheduler"` |
| `is_active` | Boolean | Schedule is active |
| `last_run_at` | DateTime | Last successful processing time (prevents same-day re-runs) |
| `processing_lock` | String | Instance ID holding the lock (null = unlocked) |
| `lock_acquired_at` | DateTime | When the lock was acquired (stale detection) |

### `student_lists` Table

| Column | Type | Purpose |
|--------|------|--------|
| `id` | UUID | Primary key |
| `list_name` | String | Name of the saved student list |
| `students_data` | JSON (Array) | Array of student objects `[{email, name, ...}]` |

### `assessment_institute_map` — Added Column

| Column | Type | Purpose |
|--------|------|--------|
| `schedule_id` | UUID (nullable) | FK → `assessment_schedules`. Links scheduled assignments back to their source schedule |

---

## Key Concepts

- **Date-Based Frequency** — unlike traditional cron patterns, schedules use an explicit array of dates. This allows irregular/custom scheduling (e.g., every Monday, specific exam dates, etc.)
- **Atomic Locking** — database-level `FOR UPDATE SKIP LOCKED` prevents double-processing even with multiple scheduler instances
- **Self-Healing Locks** — stale locks (> 5 minutes) are automatically ignored, preventing stuck schedules
- **Validity Window** — each assignment gets `startDate = today` to `endDate = today + validityDays`, giving students a fixed window
- **Student List Reuse** — student lists are saved separately and referenced by schedule, allowing the same list to be reused across multiple schedules
- **Instance Tracking** — each scheduler process gets a unique `instance-{PID}-{timestamp}` ID for lock attribution and logging
- **Comprehensive Logging** — each run prints a detailed summary with processed/skipped/failed/locked counts per schedule
- **Late-Added Student Assignment** — when new students are added to a schedule's student list via "Add Candidate", they are automatically assigned to all previously triggered assessment maps that have >24 hours remaining before expiry (via `assignStudentsToActiveScheduleAssessments`). This ensures new students get access to active assessments without waiting for the next scheduled trigger
- **Run/Schedule Status is IST-based (TPO dashboard)** — the institute TPO dashboard's schedule list (`institute-node` `getScheduleInfo` in `StudentListInfo.js`) labels each run **Upcoming / Ongoing / Expired** by comparing the map's `start_time`/`end_time` against "now". Assessment map `start_time`/`end_time` are stored as **IST wall-clock with a `+00` offset** (e.g. a run opening 00:01 IST is stored `…00:01:00+00`; the client renders them via `moment.utc`). `getScheduleInfo` therefore builds `now` in that same frame — `new Date(Date.now() + 330*60*1000)` — otherwise a run opening at 00:01 IST is mislabelled **Upcoming until 05:31 IST** each day and **Expired** fires 5.5h late. Any new timestamp comparison in this function must use the IST-shifted `now`, not a bare `new Date()`.
- **TPO schedule list keys maps off `assessment_institute_map_id`, not `audit_id`** — `getScheduleInfo` groups a schedule's runs from its assessment maps. It **must** filter/key on the real `assessment_institute_map_id` (which every map has), **not** on `audit_id`. Historically the sync assignment path always wrote an `AssessmentAudit` bookkeeping row and stamped `audit_id` on each map, so an `audit_id`-based filter was an incidental no-op — until the **async assignment queue** went live and created maps **without** an `AssessmentAudit`, leaving `audit_id` NULL. Those valid, fully-assigned runs were then silently dropped and rendered as empty "Upcoming" placeholders. `audit_id` is audit-trail bookkeeping only (who/when created the map — `operation_type`, `created_by`, `created_at`); nothing in scoring, the student flow, reports, or the drill-in depends on it.
- **Async assignment queue writes `AssessmentAudit` + sets `audit_id` (parity with sync)** — `admin-node` `Assessment.js` async assign paths (`assignBehaviorAssessmentAsync`, `assignCommunicationAssessmentAsync`, `assignAptitudeAssessmentAsync`, `assignAIInterviewAssessmentAsync`) now create one `CREATE` `AssessmentAudit` inside the job transaction (via `this.createAuditEntry(..., tx)`, metadata `{ status: "assessment mapped", source: "assignment-queue" }`) and stamp `audit_id` on every `assessment_institute_map` / `assessment_corporate_map` they create. This restores parity with the legacy sync path so queue-created maps are no longer NULL-`audit_id`. (Complementary to the `getScheduleInfo` fix above — that guards the reader, this fixes the writer. Existing pre-fix async maps with NULL `audit_id` would still need a one-off backfill if audit-trail completeness matters.)
- **`is_diagnosis` is derived from `schedule_id IS NULL`; the async assign paths were stamping `schedule_id` onto diagnosis maps too (fixed 2026-07-10)** — `student-node` computes `is_diagnosis: !isCorporate && !assessmentInstituteMap.scheduleId` on `getActiveAssessments` (`schedule_id IS NULL` = diagnosis convention, since `fb895dda`/`7cb72da` Mar-2026). In `assignCommunicationAssessmentAsync` / `assignAptitudeAssessmentAsync` (`admin-node/app/models/Assessment.js`), the shared `mkMap()` helper creates **both** the main scheduled map and the diagnosis #1/#2 maps, and it unconditionally applied `scheduleId: args.scheduleId` when the assign was triggered from `createAssessmentSchedule` — so diagnosis maps got a non-null `schedule_id` and `is_diagnosis` flipped to `false`. Assessment-React's `DiagnosisSection` (filters `is_diagnosis === true`) and `AssessmentTable`'s legacy title filter (drops rows named `"Assessment #1"/"#2"`) then **both** excluded those rows — the diagnosis pair silently vanished from the student's active-assessments list (empty "No active assessments available."). The **sync** assign path never had this bug — it always creates diagnosis maps with `schedule_id` omitted. Fix: `mkMap()` now takes an `isDiagnosisMap` flag and only applies `scheduleId` to the main map. Existing broken rows need a one-off backfill: `UPDATE assessment.assessment_institute_map SET schedule_id = NULL WHERE name IN ('Assessment #1','Assessment #2') AND is_one_time = false AND schedule_id IS NOT NULL` (applied to DEV: 1 row, UAT: 9 rows on 2026-07-10).
- **`allowNegativeMarking` is preserved as a true/false boolean end-to-end (fixed 2026-07-16)** — the schedule form's "Negative Marking System" Yes/No control writes `assessmentConfig.allowNegativeMarking: true|false` into the `assessment_schedules.assessment_config` JSON. That boolean must be carried all the way to the `isMinusSystem` column on the `assessment_assigned_students` row, which the student take-flow reads to decide whether to apply negative scoring. **`createAssessmentSchedule` (admin-node `Assessment.js`) had a long-standing `|| true` coercion** on `assessmentConfig.allowNegativeMarking` at the immediate-diagnosis-when-schedule-is-created call site (line 10698), which silently flipped the user's explicit `false` ("No") into `true` and enabled negative marking on the diagnosis assignment. The nightly `AssessmentSchedulerService` and the manual `assignAptitudeAssessment` callers were already passing the boolean through correctly — only the post-commit diagnosis path was wrong. **Fix:** changed line 10698 to `?? true` (nullish coalesce) so an explicit `false` is preserved; this matches the pattern already used at line 16865 of the same file. **Lesson for new code:** when defaulting an optional boolean config field, prefer `?? defaultValue` over `|| defaultValue` — `||` will overwrite an explicit `false`/`0`/`""` with the default, which silently inverts user intent. The same caution applies to `allowProctoring`, `allowVerification`, and any future boolean toggle. No data backfill needed: only newly-created schedules going through the diagnosis-immediate path were affected; existing `isMinusSystem` rows already reflect the value the user picked.
- **The immediate diagnosis assign now honours `assessmentValidityDays` — it used to hard-code a 10-year window (fixed 2026-08-26)** — a schedule assigns its first assessment **immediately** at create time (the post-commit diagnosis assign in `createAssessmentSchedule`) and again whenever candidates are added to an existing schedule (`_sendDiagnosisForSchedule`), both in `admin-node/app/models/Assessment.js`. Both call sites computed `diagnosisEndDate = moment().add(10, "years")`, ignoring the admin's **Assessment Validity** selection entirely — so the very first assessment every corporate/college candidate received was effectively **never-expiring**, and the configured validity only appeared from the **second** (nightly-generated) run onwards. Because the admin only ever looks at that first assignment, the UI symptom was "whatever validity we set, it gives the default". The nightly path (`AssessmentSchedulerService`) and the backfill path (`AssessmentBackfillService._invokeAssignment`) were already correct, so a single schedule produced **two different windows**. **Fix:** both diagnosis call sites now compute `moment().add(assessmentValidityDays, "days")` (from the function argument at create; from `schedule.assessmentValidityDays` on add-candidate), matching `_invokeAssignment`'s `startDate + validityDays` arithmetic — so the diagnosis window is identical to every later run of the same schedule. `assessment_validity_days` is a **required non-null Int** (`schema-assessment.prisma`, JSON-schema `minimum: 1`), so no fallback default is needed. **No backfill applied:** existing maps created before the fix keep their ~10-year `end_time`; they can be corrected per-schedule with the same batch `UPDATE` that `updateAssessmentSchedule` already runs when validity is edited (`end_time = start_time + validity days + 23:59:59` for `start_time > now()`), or by simply editing the validity on the schedule. This is the **third** bug of the same shape at this exact call site (see `allowNegativeMarking` and `enabledSections` above) — **any new schedule config field must be threaded through the immediate diagnosis assign as well as the nightly scheduler**, or it silently applies from run 2 onwards only.
