---
type: module
created: "2026-08-07"
last_verified: "2026-08-07"
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
| `backfill_role_application_snapshots` | function |
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

Phases 0–3 are code-complete and merged.

---

## Repos and PRs

| Repo | Branch | PR | Merged |
|---|---|---|---|
| `student-node` | `feat/applied-snapshot` | #1518 | 2026-08-07 |
| `corporate-node` | `feat/applied-snapshot` | #1735 | 2026-08-07 |

Both merged into `Development`.

---

## Environment state — as of 2026-08-07

| | DEV | UAT | PROD |
|---|---|---|---|
| Postgres | 17.10 | 16.14 | **14.22** |
| Snapshot tables | yes | **no** | **no** |
| Snapshots / applied rows | 598 / 590 | — | — |
| Capture backlog | 0 | — | — |
| Code deployed | yes | no | no |
| `APPLIED_SNAPSHOT_READS` | **true** | unset | unset |
| Applied rows to backfill | done | **13,008** | **63,347** |

DEV is fully deployed with reads enabled. Functional validation is pending —
testers will verify in UAT.

---

## Rollout runbook (UAT / PROD)

1. Apply DDL in order:
   - `*__applied_role_snapshot_tables.sql`
   - `*__applied_role_snapshot_capture.sql`
2. Add `export APPLIED_SNAPSHOT_READS=true` to the environment's env file.
3. Rebuild and deploy both `student-node` and `corporate-node` from `Development`.
4. Run `*__applied_role_snapshot_backfill.sql`.

Steps 3 and 4 are interchangeable — the overlay design means enabling reads
before the backfill completes is safe.

### Testing caveat

Until the backfill finishes, applied roles **without** snapshots behave exactly as
they did before. A tester checking an *old* application pre-backfill will see the
original bug and report a false failure. Test with a **freshly created**
application, or wait for the backfill.

### Verification queries

```sql
-- coverage
SELECT (SELECT count(*) FROM student.role_application_student) snapshots,
       (SELECT count(*) FROM student.student_role_mapping
         WHERE is_applied IN (1,-1)) applied_rows;

-- backlog should be 0 in normal operation
SELECT count(*) FROM student.role_application_capture_backlog;
```

### Rollback

Set `APPLIED_SNAPSHOT_READS` to anything other than `true` (or remove it) and
redeploy. All read paths revert to live data. The tables and triggers can stay —
capture is harmless on its own.

---

## Known gaps

1. **DDL is not in version control.** The three SQL files live at
   `/home/ubuntu/db-scripts-staging/applied-role-snapshot/` on the dev host
   (copied out of `/tmp`, which is cleared on reboot). They need a home in the
   DB-Scripts repo. Function bodies are also recoverable from a live DB via
   `pg_get_functiondef()`.
2. **No Prisma migration.** `prisma/schema-student.prisma` declares the five
   models with nothing in `prisma/migrations/`. `student-node`'s Dockerfile runs
   `npx prisma migrate deploy`, which will **not** create these tables — they
   must come from the DB-Scripts SQL. This also means `prisma migrate dev` will
   report drift and propose a reset. Consider generating a migration for the five
   tables; triggers and functions must stay raw SQL either way.
3. **`corporate-node` has no `.env.uat`.** Only `.env`, `.env-sample`,
   `.env.dev`, `.env.sandbox` exist. A UAT build with `ENVIRONMENT=uat` will fail
   on the `COPY`. Recruiter-side reads live entirely in corporate-node, so this
   blocks the main test scenario.
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
