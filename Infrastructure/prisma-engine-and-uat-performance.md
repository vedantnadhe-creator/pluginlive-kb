# Prisma Query Engine & UAT Performance

How the Node services run Prisma, and the root cause + fix of the 2026-06-15 UAT
"corporate/student portal is slow (15–150s)" incident. Production-truth as of
2026-06-15.

## Node services using Prisma (PostgreSQL)

`student-node`, `corporate-node`, `institute-node`, `admin-node` — all on
`@prisma/client` 6.19.x against PostgreSQL 17 (PG13→17 cutover 2026-06-09).
`user-management-node` is Mongo (Prisma 4.x), unrelated.

Prisma 4.x is **not supported on PG17**, which is why the ORM was bumped 4.16→6.19
during the PG17 cutover. **Do not downgrade Prisma** — it would reintroduce an
unsupported combo and would not fix performance.

## Query engine: use `engineType = "library"` (NOT "binary")

As of 2026-06-15 all Postgres Node services use `engineType = "library"` (the
in-process Node-API engine) in their `schema*.prisma` generator blocks.

History:
- The **library** engine used to **panic on ARM64 under concurrent `$queryRaw`**
  (`Promise.all` over raw queries crashed Node — "Engine is not yet connected").
- Workaround was `engineType = "binary"` (out-of-process Rust engine) +
  process-wide raw-query serialization.
- The panic is **fixed in @prisma/client 6.19.3** — verified on aarch64 with
  **5000 concurrent `$queryRaw`, 0 failures, 710ms**.
- The binary engine costs **CPU per query** (every query is IPC to the Rust
  subprocess). That overhead, multiplied by the portal's request fan-out, was the
  dominant cause of the UAT slowness. Switching to **library** (in-process, no IPC)
  cut per-request CPU dramatically.

If you ever see `engineType = "binary"` reintroduced, it should only be a
temporary ARM64-panic mitigation — prefer library on 6.19.3+.

## UAT app server is CPU-bound for portal fan-out endpoints

UAT app host = OCI `VM.Standard.A1.Flex` (Ampere ARM), **8 OCPU / 32 GB** (raised
from 4 OCPU on 2026-06-15). DEV is 8 cores. The DB is a **separate VM**
(`140.238.245.202:5441`, db `uat_pluginlive`).

The expensive endpoints — corporate `ruleEligibility`, `roleFloatedforStudent/lists`,
`roleMetrics/count`, `ruleEngine`, and student-node `GET /students/:id` — are
**CPU-bound, not DB-bound**. One portal page load fans out: corporate fires 5–7
endpoints, each calls student-node several times, each request runs ~10 sequential
Prisma queries. On a 4-core box with the binary engine this saturated CPU and
collapsed into 15–150s responses; on 8 cores + library engine the same load is
~1s.

### Diagnostic rule
When corporate/student portal is slow, **it is almost never the database.** During
every reproduction Postgres was idle (`pg_stat_activity` active≈1, no query >300ms,
`pg_stat_statements` max ~1.6s). Check, in order: app-server core count/load, the
Prisma engine type, and the request fan-out — not the DB.

## PostgreSQL 17 config (UAT)

The PG13→17 cutover restored into a fresh data dir and left **`shared_buffers` at
the 128 MB default** while other params were tuned via `ALTER SYSTEM`. Fixed
2026-06-15 (lives in `postgresql.auto.conf` on the DB VM):
`shared_buffers = 4GB`, `maintenance_work_mem = 1GB`, `effective_cache_size = 11GB`
(15 GB box), and `pg_stat_statements` enabled (added to `shared_preload_libraries`).
Post-restore there was **no collation drift** and stats were already analyzed, so
`REINDEX` / `VACUUM ANALYZE` were not the fix.

## PROD follow-up (pending)

When PROD does its PG13→17 upgrade and engine promotion, repeat all three:
1. Set `shared_buffers` to ~25% RAM (do not leave the 128 MB default).
2. Promote `engineType = "library"` (binary→library PRs: student #1513, corporate
   #1720) through Development → UAT → release → PROD.
3. Verify PROD app-host core count vs load (these endpoints are CPU-bound).
