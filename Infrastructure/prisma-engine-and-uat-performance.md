# Prisma Query Engine & UAT Performance

How the Node services run Prisma, and the root cause + fix of the 2026-06-15 UAT
"corporate/student portal is slow (15–150s)" incident. Production-truth as of
2026-06-16.

## Node services using Prisma (PostgreSQL)

`student-node`, `corporate-node`, `institute-node`, `admin-node` against
**PostgreSQL 16** on UAT (`140.238.245.202:5441`, db `uat_pluginlive`).
History: PG13→17 cutover 2026-06-09, then **PG17→16 downgrade 2026-06-16**
(see below). `user-management-node` is Mongo (Prisma 4.x), unrelated.

**Prisma client versions on UAT (as of 2026-06-16, post-rollback):**
- `student-node` (release-v1.33-hotfix-1 baseline), `corporate-node`
  (release-v1.33), `institute-node` (release-v1.30) → **`@prisma/client` 4.x**
  (4.10.1 / 4.16.2 / 4.11.0 respectively).
- `admin-node` → still **6.19.x** (was not part of the rollback).

### 2026-06-16 Prisma-6.19 + perf rollback on UAT (student/corporate/institute)
The Prisma `4.x → 6.19` migration + the perf-refactor stack (binary→library
engine switch, `serializeRawMethods`, ARM64 engine-restart retry, async
candidate/drive metrics, parallelized `getStudent`, dedicated read lanes,
slow-query logging) was **reverted in place on the UAT branch** of these three
services, returning their Prisma layer to the fast release baseline while
**keeping all functional commits** (TPO, AI-interview, exports, OTP, CEFR
chain-replay, Safari audio, ai-match BullMQ, etc.) so those can still promote to
PROD without dragging the unvetted migration along.

Reason: after deploying the UAT branch (Prisma 6.19) UAT was slow, and an A/B
showed the **release branches (Prisma 4.x) ran fine on the same DB** — so the
6.19 + perf cluster was rolled back to unblock the PROD-bound functional work.

**Open tension (resolve before any PROD promotion):** the engine analysis below
attributes the original slowness to the *binary* engine (IPC overhead) and says
the *library* engine on 6.19.3 is fast — i.e. it argues *against* a Prisma
downgrade. Two confounders muddy which fix actually mattered: (a) the same UAT
window also had the **PG16 `shared_buffers` 128 MB regression** (below), a
DB-side slowdown independent of Prisma; (b) it's unconfirmed whether the "slow"
UAT build was running binary or library at the time. Net: the 4.x rollback is a
pragmatic unblock for UAT/PROD promotion, not a proven refutation of the
library-engine fix. Re-measure on PROD-like config before deciding the
long-term Prisma target. **Rollback handle:** each repo has a git tag
`uat-backup-prisma-2026-06-16` at the pre-revert UAT tip; `git push
--force-with-lease origin uat-backup-prisma-2026-06-16:UAT` restores Prisma 6.19.

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

### 2026-08-10: the panic came back on institute-node (still Prisma 4.16.2)

The 2026-06-16 rollback returned institute-node to Prisma 4.x **and removed
`serializeRawMethods` + the engine-restart retry with it** (they were part of
the reverted perf stack). 6.19.3 fixes the panic; 4.16.2 does not. So the
service went back to panicking on concurrent `$queryRaw` — with nothing left to
absorb it.

Symptom: **~8 parallel requests to any DB-backed route killed the process**
(`malloc(): unaligned fastbin chunk detected`, or a silent exit 0), docker
restarted the container, and every in-flight request returned 502. Non-DB
routes at the same concurrency were fine. The v2 TPO dashboard fans out four
calls on load, so it tripped this on essentially every visit and the whole
screen failed — taking the v1 portal down with it for ~20s each time.

Fix (institute-node `aab8a12`): restored `serializeRawMethods` +
`retryOnEngineRestart` in `app/helpers/utils.js`, **keeping `engineType =
"library"`**. Measured on the load that used to kill it every time:

| config | result | dashboard fan-out |
|---|---|---|
| library, no serialization | **crashes every time** | — |
| binary + serialize | 168/168 ok, 0 restarts | 0.33 / 0.95 / 1.08 / 1.10s |
| **library + serialize** | 168/168 ok, 0 restarts | **0.33 / 0.82 / 0.94 / 0.96s** |

So **serializing the raws is the fix, not the binary engine** — the panic needs
raw queries running *concurrently*, and the queue removes that. Library stays
~10-13% faster because it skips the IPC this doc already blames for the June
UAT slowness. Binary was tried first and reverted for exactly that reason.

Cost to accept: raw queries are serialized process-wide (institute-node has 24
model files using raw SQL), so one slow raw query briefly blocks the others,
bounded by `RAW_QUERY_TIMEOUT_MS` (default 30s). Also **array-form
`$transaction([...])` containing raw queries now throws** ("All elements of the
array need to be Prisma Client promises") because the wrapper returns a plain
promise — all current call sites use the interactive `$transaction(async (tx)
=> …)` form, which is unaffected and verified working.

**Real exit:** upgrade institute-node to `@prisma/client` 6.19.3, where the
panic is fixed and the serialization queue can be dropped. Until then, do not
remove `wrapPrismaInstance` from `getPrismaInstance` — and check
student-node / corporate-node, which were rolled back the same way and are
likely carrying the same live defect.

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

## PostgreSQL 16 config (UAT) — and the 2026-06-16 PG17→16 downgrade

UAT now runs **PostgreSQL 16.14** (`pgvector/pgvector:pg16`) on `5441`. The DB VM
(`pluginlive-uat-database`, `140.238.245.202`) runs the live DB as a Docker
container `UAT-Pluginlive-PG16` (bind mount `~/Database/db16-staging`).

**Downgrade procedure used (PG17 → PG16, 2026-06-16):** a major-version downgrade
is **not in-place** — it is dump→restore into a separate PG16 instance, then a
port-swap. Key gotcha: **PG16's `pg_restore` cannot read a PG17 custom-format
(`-Fc`) dump** ("unsupported version (1.16) in file header"). Use a **plain SQL
dump** (`pg_dump | gzip`, restored via `psql`) — it is version-agnostic. Steps:
stop UAT backend containers + freeze PG17 (`ALTER DATABASE … SET
default_transaction_read_only=on` + terminate client backends) → fresh plain dump
→ drop+recreate `uat_pluginlive` in PG16 + `psql` restore → per-table rowcount
parity gate (must be 0-diff) → stop PG17 (`--restart no`, kept as rollback),
recreate the PG16 container bound to host port `5441`. The lone harmless restore
error is `unrecognized configuration parameter "transaction_timeout"` (a PG17-only
GUC in the dump header). **Rollback:** PG17 container `UAT-Pluginlive` is retained
stopped; to revert, clear its read-only lock (`SET default_transaction_read_only
= off;` in-session, then `ALTER DATABASE … RESET …`), stop PG16, rebind PG17 to
`5441`. App-server `psql`/`pg_dump` client tools were also bumped **14 → 16**.

**Tuning must be re-applied on every fresh data dir** (the recurring trap): a fresh
container defaults `shared_buffers` to **128 MB**. The PG16 instance was given the
same tuning PG17 had (lives in `postgresql.auto.conf` on the DB VM):
`shared_buffers = 4GB`, `maintenance_work_mem = 1GB`, `effective_cache_size = 11GB`
(15 GB box), `work_mem = 16MB`, `random_page_cost = 1.1`,
`effective_io_concurrency = 200`, and `pg_stat_statements` enabled (added to
`shared_preload_libraries`). Post-restore there was **no collation drift** and
parity was exact (8,169,122 rows across 263 tables), so `REINDEX` /
`VACUUM ANALYZE` were not needed.

## PROD follow-up (pending)

Note: UAT standardized on **PG16** (2026-06-16), not 17 — revisit the PROD target
version before its upgrade so PROD/UAT stay aligned. Whatever the target, when PROD
does its major upgrade and engine promotion, repeat all three:
1. Set `shared_buffers` to ~25% RAM (do not leave the 128 MB default).
2. Promote `engineType = "library"` (binary→library PRs: student #1513, corporate
   #1720) through Development → UAT → release → PROD.
3. Verify PROD app-host core count vs load (these endpoints are CPU-bound).
