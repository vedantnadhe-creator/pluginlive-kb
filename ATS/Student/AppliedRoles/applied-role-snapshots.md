---
type: module
created: "2026-08-07"
last_verified: "2026-08-07 (UAT rollout)"
tags: [applied-roles, snapshots, student-node, corporate-node, feature-flag]
---

# Applied-Role Snapshots

Freezes a candidate's profile, education, and course data at the moment they apply
to a role, so later profile edits no longer retroactively change what recruiters
see on an already-submitted application.

**Services:** `student-node`, `corporate-node`
**Feature flag:** `APPLIED_SNAPSHOT_READS`
**Origin session:** OliBot `WA-mseb7293`

---

## Problem

Candidate data on an applied role was read live from `student`,
`student_personal_profile`, and `education_profile`. If a student updated their UG
score after applying, the already-submitted application silently showed the new
value. Recruiters had no way to see what the candidate actually looked like at
application time.

---

## Architecture

```
apply (is_applied -> 1 or -1)
   |
   v
DB trigger (synchronous, same transaction)
   |
   +--> student.role_application_*          snapshot captured "as of apply time"
   |
   +--> on failure: role_application_capture_backlog   (apply still commits)
                          |
                          v
              Node cron drains backlog every 5 min
              capture_source = 'recovered'
```

Two design rules drive most of the behaviour:

1. **A student must never be blocked from applying by a snapshot bug.** The
   trigger swallows capture errors and records the `(student_id, role_id)` pair
   in the backlog table. The apply itself always commits.
2. **Reads overlay rather than replace.** Rows with no snapshot degrade to live
   data instead of returning empty fields. This is what makes the flag safe to
   enable *before* a backfill has finished — an unbackfilled row simply behaves
   as it did before.

### Read behaviour

| `is_applied` | Meaning | Source |
|---|---|---|
| `1` / `-1` | Applied | **Snapshot** (falls back to live if absent) |
| `0` | Bookmarked / saved | **Live** — saving must not freeze data |

`Student.js` in `student-node` intentionally stays on live data.

---

## Database objects

All in the `student` schema.

| Object | Type |
|---|---|
| `role_application_student` | table |
| `role_application_personal_profile` | table |
| `role_application_education_profile` | table |
| `role_application_current_course` | table |
| `role_application_capture_backlog` | table |
| `capture_role_application_snapshot` | function |
| `trg_capture_role_application` | trigger function |
| `backfill_role_application_snapshots` | **procedure** (not a function — invoke with `CALL`) |
| `trg_capture_role_application_ins` / `_upd` | triggers on `student_role_mapping` |

The DDL is **PG14-safe** — no `MERGE INTO`, no `NULLS NOT DISTINCT`, nothing
beyond `ON CONFLICT`. There is no `pg_cron` dependency; retry/reconciliation run
as Node crons in `script/scheduler.js`.

---

## Key files

| File | Service | Purpose |
|---|---|---|
| `app/helpers/appliedSnapshot.js` | both | Flag gate, join/overlay helpers |
| `app/models/StudentRoleMapping.js` | student-node | Candidate reads repointed |
| `app/models/Student.js` | student-node | `getStudentWithQuestion` overlay (candidate drawer) — see the incident below |
| `script/appliedSnapshotBacklogCron.js` | student-node | Backlog drain + reconciliation sweep |
| `script/scheduler.js` | student-node | Registers both crons |
| `app/models/DriveRoleCandidateMap.js` | corporate-node | Recruiter candidate lists |
| `app/helpers/evaluationAssessmentOverlay.js` | corporate-node | Evaluation overlay |
| `prisma/schema-student.prisma` | student-node | 5 snapshot models |

Both crons are wrapped in `try/catch` and gated on the scheduler's global
`isDisabled`. In an environment without the tables they log an error rather than
crashing the service.

---

## Feature flag

```js
function isAppliedSnapshotReadsEnabled() {
  return String(process.env.APPLIED_SNAPSHOT_READS || '').toLowerCase() === 'true';
}
```

Identical in both services. **Unset means off.** Only the literal string `true`
(case-insensitive) enables it — `1` and `yes` do not.

### Gotcha: env files are baked into the image at build time

```dockerfile
ARG ENVIRONMENT
COPY .env.${ENVIRONMENT} /app/.env
```
```bash
docker buildx build --build-arg ENVIRONMENT=dev -t $APP_LOWER:$TYPE .   # deploy.sh
```

Editing an env file and **restarting is not enough** — the container re-runs the
same image with the same baked `.env`. The sequence is:

```
edit .env.<env>  ->  rebuild image  ->  redeploy container
```

Env files on these services use `export VAR=value` shell syntax. dotenv 16.x
parses the `export` prefix correctly, so match the existing style:

```
export APPLIED_SNAPSHOT_READS=true
```

To verify what the app actually resolves (not just the file contents):

```bash
docker exec -w /app <container> node -e \
  "require('dotenv').config({path:'.env'}); console.log(process.env.APPLIED_SNAPSHOT_READS)"
```

---

## Phases

| # | Phase | Scope |
|---|---|---|
| 0 | Snapshot foundation | Tables, capture function, Prisma models |
| 1 | Capture at application time | Triggers + backlog handling |
| 2 | Read from snapshots | Repoint candidate/application APIs, flag-gated |
| 3 | Backfill and recovery | Backfill, reconciliation sweep, backlog monitoring |
| 4 | UAT rollout | Migrations, backfill, deploy, enable, validate |
| 5 | Production rollout | Same, with monitoring and rollback readiness |
| 6 | Final cleanup | Remove flag fallback, retain monitoring |

Phases 0–3 are code-complete and merged. Phase 4 (UAT) is complete as of
2026-08-07; functional validation by testers is in progress. Phase 5 (PROD) has
not started.

---

## Repos and PRs

| Repo | Branch | PR | Merged |
|---|---|---|---|
| `student-node` | `feat/applied-snapshot` | #1518 | 2026-08-07 |
| `corporate-node` | `feat/applied-snapshot` | #1735 | 2026-08-07 |

Both merged into `Development`, then promoted to `UAT` (student-node via PR
#1519; corporate-node via a `Development` -> `UAT` merge).

---

## Environment state — as of 2026-08-07

| | DEV | UAT | PROD |
|---|---|---|---|
| Postgres | 17.10 | 16.14 | **14.22** |
| Snapshot tables | yes | yes | **no** |
| Triggers (ins/upd x 2 tables) | 4 enabled | 4 enabled | — |
| Snapshots captured | 598 | **13,012** | — |
| Applied rows missing a snapshot | 0 | **0** | — |
| Capture backlog (unresolved) | 0 | 0 | — |
| Code deployed | yes | yes | no |
| `APPLIED_SNAPSHOT_READS` | **true** | **true** | unset |
| Applied rows to backfill | done | done | **63,347** |

DEV and UAT are both fully deployed with reads enabled. UAT backfill wrote 13,012
snapshot rows against exactly 13,012 applied applications, all `capture_source =
'backfill'`. Functional validation by testers is in progress.

### UAT rollout notes (2026-08-07)

- Both `student-node` and `corporate-node` containers verified running the new
  image with the flag resolving to `"true"` at runtime, and no Prisma
  `Unknown field` errors in the logs — confirming the generated client includes
  the snapshot models.
- **Deploy the two services together.** For roughly an hour UAT ran
  corporate-node on the new code while student-node was still on a 33-hour-old
  image. The result is a split-brain: recruiter Drives screens read the frozen
  value while student-node-served views (candidate lists, TPO screens, candidate
  drawer) read live. It looks like a feature bug and is not one.
- After a deploy, confirm the container was actually recreated before concluding
  anything — compare `docker inspect <c> --format "{{.State.StartedAt}}"` against
  the image's `{{.Created}}`. A `docker ps` "Up N hours" older than the image
  means the image was rebuilt but the container was not replaced.

---

## Rollout runbook (UAT / PROD)

1. Apply DDL in order:
   - `*__applied_role_snapshot_tables.sql`
   - `*__applied_role_snapshot_capture.sql`
2. Add `export APPLIED_SNAPSHOT_READS=true` to the environment's env file.
3. Rebuild and deploy both `student-node` and `corporate-node` from `Development`.
4. Run `*__applied_role_snapshot_backfill.sql`, then invoke the procedure it
   creates (see below).

Steps 3 and 4 are interchangeable — the overlay design means enabling reads
before the backfill completes is safe. Deploy **both** services in the same
window, though; see the split-brain note above.

### Running the backfill

It is a database call, not an API call. Two constraints, both of which will
otherwise fail the run:

- **Use a write-capable role.** The tester helper `scripts/ro-query.sh <env>`
  connects as `pl_tester_ro`, which is SELECT-only with
  `default_transaction_read_only=on`; the `CALL` returns permission denied. On
  UAT the write role is `pluatadmin` (credentials in the services' `.env.uat`).
- **Do not wrap it in a transaction.** No `psql -1`, no `--single-transaction`,
  no explicit `BEGIN`. The procedure issues a `COMMIT` per batch so a large
  backfill does not hold one long-running transaction open, and errors out if it
  finds itself inside one. Plain `psql` is autocommit and works as-is.

```bash
psql -h <host> -p <port> -U <write-role> -d <db> --no-psqlrc -v ON_ERROR_STOP=1 \
     -c "CALL student.backfill_role_application_snapshots();"
```

Re-running is safe and resumable: each batch selects only applications that still
lack a snapshot, so a run killed partway resumes rather than duplicating. It also
**never overwrites an existing `capture_source = 'apply'` row** — a genuine
as-of-apply capture is never downgraded to a backfilled one.

Orphan applications (mapping rows whose `student.students` record is gone) are
skipped by design and reported in the `NOTICE` output. DEV and UAT each carry
~11,106 of these; PROD has none. The `student.students` join is load-bearing, not
tidiness — without it those rows would permanently "lack a snapshot" and the
batch loop would never terminate.

### Testing caveat

Until the backfill finishes, applied roles **without** snapshots behave exactly as
they did before. A tester checking an *old* application pre-backfill will see the
original bug and report a false failure. Test with a **freshly created**
application, or wait for the backfill.

### Verification queries

```sql
-- coverage: must be 0. Unions BOTH mapping tables (PROD has applied rows in
-- each with no counterpart in the other) and joins student.students to exclude
-- orphans, which can never be snapshotted.
SELECT count(*) AS missing FROM (
  SELECT student_id, role_id FROM student.student_role_mapping   WHERE is_applied IN (1,-1)
  UNION
  SELECT student_id, role_id FROM corporate.job_role_student_map WHERE is_applied IN (1,-1)
) a
JOIN student.students st ON st.id = a.student_id
LEFT JOIN student.role_application_student s
       ON s.id = a.student_id AND s.role_id = a.role_id
WHERE s.id IS NULL;

-- how snapshots were captured
SELECT capture_source, count(*) FROM student.role_application_student GROUP BY 1;

-- backlog should be 0 in normal operation
SELECT count(*) FROM student.role_application_capture_backlog WHERE resolved_at IS NULL;
```

Note the key column: `role_application_student` mirrors `student.students` via
`LIKE`, so the student identifier is `id`, not `student_id`. The other three
snapshot tables do use `student_id`.

### Rollback

Set `APPLIED_SNAPSHOT_READS` to anything other than `true` (or remove it) and
redeploy. All read paths revert to live data. The tables and triggers can stay —
capture is harmless on its own.

---

## Incident: the Phase 2 overlay duplicated every new student (2026-08-10 → 2026-08-11, UAT)

Phase 2 (`ac842702`) put the candidate-drawer overlay in the wrong function of
`student-node/app/models/Student.js`. It landed in `create()` instead of
`getStudentWithQuestion(id, roleId)`:

```js
const student = await prisma.student.create(buildCreateArgs(OPTIONAL_CREATE_SECTIONS));
const withSnapshot = await appliedSnapshot.overlayStudentRecord(prisma, student, roleId); // no roleId in scope
```

`create()` has no `roleId`, so **every** student create threw
`ReferenceError: roleId is not defined` — *after* the insert had already
committed. `create()`'s `catch` cannot tell a failed insert from a failed
post-insert step, so it fell into its degraded fallback and created the account a
**second** time without `currentCourse`, `resume` or `educationProfile`. Result,
per candidate:

- a complete but **orphaned** student row (has `current_course`, no auth user), and
- a **degraded twin** that `createPublicStudent` returns, so the auth user, the
  system resume and every downstream assignment bind to it.

Symptom seen by testers: a scheduled assessment's candidate list
(`POST /assessment/getDiagnosisDataForASchedule`, admin **Assessment → Diagnosis**)
showed **Degree & Department as `-`** for some candidates and correct for others.
The list keys students by email; with two rows per email, whichever twin the
Prisma `findMany` returned last won the map. The uploaded roster was never at
fault — `assessment.student_lists.students_data` had the degree, `degreeId` and
`streamId` all along. Excel export, filters and anything else reading
`currentCourse` are affected the same way.

Nothing enforces this at the DB level: **`student.student_personal_profile.primary_email`
has no unique index**, which is why two accounts per email are possible at all
and why the `P2002` branch in `Student.create()` never fires.

- **Blast radius:** UAT only, ~20 students created between 2026-08-10 06:33 (when
  the build reached UAT) and 2026-08-11. DEV ran the same code with no student
  creations in the window; PROD never had it.
- **Fix:** `student-node` `b998c122` — overlay removed from `create()` (a student
  being created has no applied-role snapshot, so it was a no-op even when it did
  not throw) and moved into `getStudentWithQuestion`, where `roleId` exists.
  Keeping `create()`'s `try` around the insert alone is what makes the degraded
  fallback safe. Deployed DEV + UAT 2026-08-11.
- **Data repair:** `~/scripts/backfill_tpoduat_twins_uat.sql` — per email, move
  `current_course` and `resume` from the orphan onto the live account, then delete
  the drained orphan (its `student_personal_profile` goes with it via
  `ON DELETE CASCADE`, which frees the duplicate email). Guarded: aborts unless
  the live twin owns exactly one auth user, the orphan owns none, and the orphan
  carries nothing beyond `current_course`/`resume`. Run so far for campus
  `442b8476-…` (Jay Jalaram Talimi Snatak Mahavidyalaya) only — 4 students.
  The remaining ~16 UAT students from other campuses are still duplicated.

**Detection query** — degree-less students that have a same-email twin with a course:

```sql
SELECT p.primary_email, s.id, s.institute_campus_id, s.created_at
FROM student.students s
JOIN student.student_personal_profile p ON p.student_id = s.id
LEFT JOIN student.current_course c ON c.student_id = s.id
WHERE c.student_id IS NULL AND s.deleted_at IS NULL
  AND EXISTS (SELECT 1 FROM student.student_personal_profile p2
              JOIN student.current_course c2 ON c2.student_id = p2.student_id
              WHERE lower(p2.primary_email) = lower(p.primary_email)
                AND p2.student_id <> s.id);
```

Note the flag is irrelevant here: `overlayStudentRecord` returns early when
`APPLIED_SNAPSHOT_READS` is off, but the `ReferenceError` fires while *evaluating
the argument*, so the crash happened with the feature disabled too.

---

## Known gaps

1. **DDL is not in version control.** The three SQL files live at
   `/home/ubuntu/db-scripts-staging/applied-role-snapshot/` on the dev host
   (copied out of `/tmp`, which is cleared on reboot). That directory is not a
   git repo. Pushing them to DB-Scripts was **deliberately deferred** at the UAT
   stage; it should happen before the PROD rollout, since
   `grep -rl "PROD — pending"` over DB-Scripts is how the PROD migration order is
   derived, and this feature is currently invisible to it. Function and procedure
   bodies are also recoverable from a live DB via `pg_get_functiondef()`.
2. **No Prisma migration.** `prisma/schema-student.prisma` declares the five
   models with nothing in `prisma/migrations/`. `student-node`'s Dockerfile runs
   `npx prisma migrate deploy`, which will **not** create these tables — they
   must come from the DB-Scripts SQL. This also means `prisma migrate dev` will
   report drift and propose a reset. Consider generating a migration for the five
   tables; triggers and functions must stay raw SQL either way.
3. ~~**`corporate-node` has no `.env.uat`.**~~ **Resolved 2026-08-07.**
   `.env.uat` now exists on the UAT box at `~/api/corporate-node/.env.uat` with
   `export APPLIED_SNAPSHOT_READS=true` at line 49, and the UAT image built from
   it. Note it is **untracked** — env files are box-local in both services, so it
   exists only on that host and must be created again for any new environment.
4. **PROD is on PG14.22** while dev/UAT are 17/16. Not a blocker for this feature
   (the DDL is PG14-safe), so the planned PG16 upgrade and this rollout are
   independent — do not couple them.

---

## Related

- `ATS/Student/AppliedRoles/README.md` — Applied Roles module
- Unrelated but adjacent: `corporate-node` requires `prisma/generated-audit` from
  the audit-trail feature. Its Dockerfile passes `--ignore-scripts` to
  `npm install`, skipping the `postinstall` that generates that client. If a
  corporate-node deploy crash-loops with
  `Cannot find module '../../prisma/generated-audit'`, add
  `npx prisma generate --schema=./prisma/schema-audit.prisma` to the Dockerfile.
