# Tester read-only DB access (`pl_tester_ro`)

QA testers have **SELECT-only** database access to **DEV, UAT and PROD**. This exists so a
tester can verify data-level behaviour ("how many students have an active BE degree on UAT?")
without stalling to ask a developer for admin credentials, and without any ability to change data.

## The entry point

On the DEV box (where agent sessions run):

```bash
/home/ubuntu/scripts/ro-query.sh <dev|uat|prod> "SELECT ..."
/home/ubuntu/scripts/ro-query.sh uat -f /path/to/query.sql
echo "SELECT ..." | /home/ubuntu/scripts/ro-query.sh dev
```

`PSQL_EXTRA` forwards psql flags — e.g. `PSQL_EXTRA="-t -A"` for bare values,
`PSQL_EXTRA="-A -F','"` for CSV. Discover the layout with `"\dt <schema>.*"`.

Schemas: `admin`, `assessment`, `corporate`, `institute`, `student`, `user_management`,
`ai_interviewer`, `search_engine`, `mandate`, `public`, plus `analytics` and `anand-group` on DEV
and `candidate_ingestion_schema` on UAT.

## How read-only is actually enforced

**Not by the wrapper script.** Tester agent sessions keep the Bash tool, so any credential on
disk can be used directly with `psql` — a check inside the script would be trivially bypassed.
The limit therefore lives server-side:

| Env | Mechanism |
|---|---|
| DEV, UAT, PROD | Connects as **`pl_tester_ro`**, a role holding `SELECT` and nothing else, with `default_transaction_read_only=on`. Writes are refused **even if the read-only GUC is turned off** — they fail with `permission denied for table …`, not merely `cannot execute UPDATE in a read-only transaction`. |
| PROD only | The PROD DB is reachable only from the jump host, so `ro-query.sh prod` delegates over SSH to `/home/ubuntu/scripts/tester-ro-query.sh` there — same `pl_tester_ro` role, just a network hop. |

Verified per env with the GUC explicitly disabled at connection level
(`PGOPTIONS="-c default_transaction_read_only=off"`), which is what proves the *grants* are doing
the work rather than the bypassable GUC: `INSERT`/`UPDATE`/`DELETE` → `permission denied for
table …`, `CREATE TABLE <appschema>.x` → `permission denied for schema …`; `SELECT` unaffected.

`/home/ubuntu/scripts/prod-readonly-query.sh` on the jump host still exists and still connects as
the **write-capable `plproduction`** behind a regex pre-flight + `BEGIN READ ONLY` wrapper. It is
for **admin/ops** use and is no longer on the tester path — do not point testers at it.

### PROD host replacement breaks the password (fixed 2026-09-07)

PROD Postgres was cut over to a new PG16 instance (`10.0.6.104`) on 2026-08-03. `pl_tester_ro`
came across in the restore, but **with a different password than the one in `ro-query.sh` /
`tester-ro-query.sh`**, so every tester PROD query failed for a month with:

```
FATAL:  password authentication failed for user "pl_tester_ro"
```

A restored, forked or otherwise replaced instance keeps roles but not their passwords. **After any
DB host change, re-run the migration against the new host** — it resets the password and re-grants
SELECT in one pass:

```bash
ssh ubuntu@140.245.25.134
PGPASSWORD=<plproduction pw> PGOPTIONS="-c pl.ro_password=<pw from ro-query.sh>" \
  psql -h 10.0.6.104 -p 5432 -U plproduction -d prod_pluginlive -f pl_tester_ro.sql
```

Done on PROD 2026-09-07: 492 tables/views across 11 schemas (`admin`, `ai_usage`, `assessment`,
`audit`, `candidate_ingestion_schema`, `corporate`, `institute`, `public`, `search_engine`,
`student`, `user_management`) — **0 unreadable**.

### `public` schema CREATE gap on PROD — closed 2026-09-07

Until then, PROD's schema `public` still granted `CREATE` to `PUBLIC` (a PG14-era default carried
forward through the restore), so `pl_tester_ro` could create its own scratch objects there — it
could never touch an existing object in any schema. It was genuinely unfixable on the old PG14
host, where `public` was owned by `oci_superuser`.

On the PG16 host `public` is owned by `pg_database_owner` and `plproduction` owns the database, so
`plproduction` **can** revoke it. Step 5 of the migration now does:

```sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC;   -- the PG15+ default
```

Verified live afterwards: `CREATE TABLE public.x` as `pl_tester_ro` (with the read-only GUC forced
off) → `permission denied for schema public`, while `plproduction` can still create and drop
tables in `public`, so app migrations are unaffected. It keeps `CREATE` through its
`pg_database_owner` membership — no separate `GRANT` is needed, and the OCI master role
(`pluginliveprd`) is no longer required to close this.

## The role

Created by `PluginLive-Technologies/DB-Scripts` →
`Tester Read-Only DB Access/20260803T104643Z__tester_readonly_role.sql`.

- `LOGIN`, `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`
- `GRANT USAGE` + `GRANT SELECT` on every non-system schema, current **and** future objects
  (via `ALTER DEFAULT PRIVILEGES` per table owner)
- `statement_timeout=120s`, `idle_in_transaction_session_timeout=60s` so an ad-hoc tester query
  can't pin a connection
- Applied: **DEV, UAT and PROD — all 2026-08-03**; re-applied on PROD 2026-09-07 against
  the PG16 host `10.0.6.104` (password reset + step 5).

Each grant in the schema loop is wrapped in its own exception block. That is what makes the same
file runnable on PROD, where the running role owns the tables but not every schema: an
un-grantable statement is skipped with a `NOTICE` instead of aborting the run and discarding the
grants that already succeeded.

**Re-run the migration after adding a new schema, or after the DB host is replaced** — the grant
loop covers schemas that exist at run time, default privileges only cover new tables in
already-granted schemas, and a restored instance carries the role over without its password. It is
idempotent (re-running also resets the password).

The password lives in `scripts/ro-query.sh` on the DEV box; the SQL takes it via
`PGOPTIONS="-c pl.ro_password=…"` so it is never committed.

## Related

- Tester sessions are pointed at this helper by `TESTER_PROMPT` in
  `whatsapp-engineer/claude_manager.js`.
- The global `postgres` MCP server is a separate path: DEV only, connects as the admin
  `pldevadmin`, but the MCP server itself wraps every query in a read-only transaction
  (verified — a `SET TRANSACTION READ WRITE` escape attempt creates nothing).
