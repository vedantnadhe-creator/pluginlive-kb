# PROD PostgreSQL 14 → 16 Major Upgrade Runbook

Runbook for upgrading the **production** PostgreSQL server from **14.17 to 16.x**.
Production-truth as of 2026-07-06. This is a **user-driven, maintenance-window**
operation — never run against PROD without an explicit go-ahead and a scheduled
window. Rehearse the whole thing on a clone first.

## Why this exists — version drift across environments

As of 2026-07-06 the three tiers are on **different major versions**:

| Env  | Host                              | Version                       | Build            |
|------|-----------------------------------|-------------------------------|------------------|
| DEV  | `pl-database.dev.pluginlive.com:5441` | **17.10**                 | aarch64, Alpine (musl) |
| UAT  | `140.238.245.202:5441`            | **16.14**                     | aarch64, Debian  |
| PROD | `10.0.2.105:5432`                 | **14.17 "OCI Optimized"**     | x86-64           |

A DEV→17 cutover happened but never propagated; UAT was cut to 17 then rolled
back to 16 on 2026-06-16 (PG16 cannot `pg_restore` a PG17 `-Fc` dump — see
`prisma-engine-and-uat-performance.md`). PROD was never upgraded. The goal here
is to bring **PROD onto 16 to match UAT** (forward 14→16 restores are
compatible, so this direction is safe).

## Target server facts (measured 2026-07-06)

- **Standalone self-managed PostgreSQL VM** — `prod_pluginlive @ 10.0.2.105:5432`,
  superuser `plproduction`. It is **not** the OCI managed Database service and it
  is **not** the app box (`140.245.25.134`); it's a separate host on the private
  `10.0.2.0/24` subnet (no SSH from the app box on port 22 — reach it from
  wherever the DBA/ops keys land).
- **DB size ≈ 7.2 GB** — small; logical dump/restore is only ~15–30 min.
- **~150 live connections**, `max_connections = 450`.
- **`shared_buffers = 6656MB`** — the server is *properly tuned*. **This is the
  #1 landmine:** a prior PG17 cutover shipped with the 128 MB default and caused
  a production slowdown (see `project_pg17_shared_buffers_regression`). The new
  16 instance **must** reproduce these values.
- **SSL is enforced** — `pg_hba` on PROD is `hostssl`-only. The admin-node
  assignment-queue uses a raw `pg` pool that defaults to plaintext and will fail
  against PROD unless SSL is configured; keep `hostssl` rules on 16.

## Read-only recon (safe, no downtime)

Run everything through the sanctioned helper on the app box:
`ssh ubuntu@140.245.25.134 -> /home/ubuntu/scripts/prod-readonly-query.sh '<SQL>'`

```sql
-- size, version, key knobs
SELECT pg_size_pretty(pg_database_size('prod_pluginlive')),
       version(), current_setting('shared_buffers'),
       current_setting('max_connections');

-- every non-default GUC (copy ALL of these onto the new server)
SELECT name, setting, unit FROM pg_settings
WHERE source NOT IN ('default','override') ORDER BY name;

-- extensions (must exist on 16 BEFORE restore)
SELECT extname, extversion FROM pg_extension ORDER BY 1;

-- databases to migrate (not just prod_pluginlive — check the whole cluster)
SELECT datname, pg_size_pretty(pg_database_size(datname))
FROM pg_database WHERE datistemplate = false ORDER BY 2 DESC;
```

## Choose a method

Because this is a **self-managed VM**, both paths are available:

| Method | Downtime | Risk | When to use |
|--------|----------|------|-------------|
| **A. Dump & restore into a fresh 16 instance** | ~15–30 min | Low, easy rollback (old server untouched) | **Recommended default** at 7 GB |
| **B. `pg_upgrade --link` in place** | ~2–5 min | Higher — mutates the data dir; needs full FS backup | Only if a >15-min window is unacceptable |
| **C. Native logical replication 14→16** | seconds | Highest complexity | Only if near-zero downtime is a hard requirement |

Below is **Method A** in full, with B and C summarized after.

---

## Method A — New 16 instance + logical dump/restore (recommended)

### Phase 0 — Prep (days before, no downtime)
1. **Stand up PostgreSQL 16** — either a second instance on a different port on
   `10.0.2.105`, or (preferred) a fresh VM/volume so 14 stays fully intact for
   rollback. Match the OS/arch already in use.
2. **Reproduce ALL tuning** in the 16 `postgresql.conf` from the `pg_settings`
   dump above — at minimum:
   - `shared_buffers = 6656MB`
   - `max_connections = 450`
   - plus `work_mem`, `maintenance_work_mem`, `effective_cache_size`,
     `random_page_cost`, `wal_*`, autovacuum overrides — whatever recon listed.
3. **Reproduce `pg_hba.conf`** with the same `hostssl` rules + server SSL certs.
4. **Install matching extensions** on 16 (`pg_trgm`, `uuid-ossp`, etc. — from
   recon) so the restore's `CREATE EXTENSION` calls resolve.
5. **Copy globals** (roles + passwords) so every app role exists on 16:
   ```bash
   pg_dumpall -h 10.0.2.105 -U plproduction --globals-only \
     | grep -v '^--' > globals.sql
   ```
6. **Full dry run**: dump → restore → smoke-test against the 16 box with no
   cutover. Time it. Diff row counts. Run the heaviest known queries.
7. **Schedule the window**, announce, and **freeze deploys** (CI auto-deploys to
   Development; make sure nothing promotes mid-migration).

### Phase 1 — Cutover (in the window)
1. **Stop writers** so no writes are lost during the dump. Scale the K8s app
   deployments that write to the DB to 0:
   ```bash
   PATH=~/bin KUBECONFIG=<prod-kubeconfig> kubectl -n api scale deploy \
     --replicas=0 <student-node auth-node corporate-node institute-node admin-node ...>
   ```
   (`user-management-node` deploys as `auth-node`; see `reference_prod_kubectl_authnode`.)
2. **Final parallel dump from 14** (run from a host that can reach `10.0.2.105:5432`):
   ```bash
   pg_dump -h 10.0.2.105 -U plproduction -d prod_pluginlive \
     -Fd -j 4 --no-owner --no-privileges -f /data/pgmigrate/prod_$(date +%F)
   ```
3. **Load globals, then restore into 16:**
   ```bash
   psql   -h <NEW16_HOST> -U plproduction -d postgres -f globals.sql
   createdb -h <NEW16_HOST> -U plproduction prod_pluginlive
   pg_restore -h <NEW16_HOST> -U plproduction -d prod_pluginlive \
     -Fd -j 4 --no-owner --no-privileges /data/pgmigrate/prod_$(date +%F)
   ```
4. **Post-restore fixups:**
   ```sql
   ANALYZE;   -- planner stats do NOT carry over; skipping this = slow prod
   SELECT extname, extversion FROM pg_extension;   -- parity check
   ```
   - Verify **row counts** on the top ~15 tables against source.
   - Re-check known type quirks — e.g. `assessment.student_lists.students_data`
     is **`json`** on PROD and must stay `json`, not become `jsonb`
     (see `project_students_data_json_vs_jsonb`).
   - Spot-check a few **sequences** are at `max(id)`.

### Phase 2 — Repoint apps
1. Change **only the DB host** in app config (`10.0.2.105` → new 16 endpoint);
   db name / user / SSL stay identical. Runtime env for the Node services lives
   in the box/secret `.env`, **not** docker `-e` (CI bakes `.env.dev` and would
   clobber `-e`; see `project_admin_node_queue_flag_clobbered_by_ci`). If 16 runs
   on the **same host/port**, no app change is needed at all.
2. Scale writers back up; wait for pods `Ready`.
3. **Smoke test**: login, run an assessment, trigger a scored flow, and confirm
   the **assignment queue** (raw `pg` SSL path) works.

### Phase 3 — Verify & keep rollback
- `SELECT version();` → 16, and `shared_buffers` / `max_connections` match the
  14 values (guard the slowness regression).
- Watch Grafana DB CPU + p95 latency for a few hours.
- **Keep the old 14 server running, read-only, for 48–72 h.** Rollback = repoint
  the app host back to `10.0.2.105`.

---

## Method B — `pg_upgrade --link` in place (fast, riskier)
Only with root on the DB VM and a **full filesystem backup / volume snapshot**
taken first.
1. Install the 16 binaries alongside 14 (both `bin` dirs on the box).
2. `initdb` a new 16 data dir with the **same tuning + `pg_hba` + SSL**.
3. Stop 14, then:
   ```bash
   /usr/lib/postgresql/16/bin/pg_upgrade \
     -b /usr/lib/postgresql/14/bin -B /usr/lib/postgresql/16/bin \
     -d /var/lib/postgresql/14/main -D /var/lib/postgresql/16/main \
     --link --check          # run --check first; drop --check to execute
   ```
4. Start 16, run the generated `analyze_new_cluster.sh` (or `vacuumdb --analyze-in-stages`).
5. `--link` hard-links files, so the old cluster is **destroyed** on success — the
   FS snapshot is your only rollback. Take a `pg_dump` safety net anyway.

## Method C — logical replication (near-zero downtime)
Stand up 16 as a **subscriber**, `CREATE PUBLICATION` on 14, let it catch up
live, then flip the app host during a brief pause. Watch for tables without a
replica identity, sequence sync, and DDL freeze during the copy. Only worth it
if minutes of downtime is a hard no — at 7 GB, Method A usually is fine.

## Gotchas checklist (all bitten before)
- [ ] **`shared_buffers` = 6656MB on 16** — not the 128 MB default.
- [ ] **`max_connections` = 450.**
- [ ] **`hostssl`-only `pg_hba` + SSL certs** carried over (assignment queue).
- [ ] **`ANALYZE`** after restore (stats don't migrate).
- [ ] **Extensions installed before restore.**
- [ ] **`students_data` stays `json`**, not `jsonb`.
- [ ] **All app roles/passwords** present (globals dump).
- [ ] **Deploy freeze** during the window (CI auto-deploys).
- [ ] **Old 14 kept read-only 48–72 h** for rollback.

## After a successful PROD upgrade
- Update this doc + the env-version table above to production-truth.
- Any schema/enum touch-ups made during migration → push via the `db-script-push`
  skill (mark PROD as applied).
