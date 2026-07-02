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
