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

### Open gap on PROD (PG14 `public` schema)

PROD is **PostgreSQL 14**, where schema `public` still grants `CREATE` to `PUBLIC`. The migration
runs there as `plproduction`, which is `CREATEROLE` but **not** superuser and does **not own**
schema `public` (owner: `oci_superuser`), so it cannot revoke that grant — expect two harmless
`no privileges were granted/could be revoked for "public"` warnings on every PROD run.

Consequence: on PROD, `pl_tester_ro` **cannot modify any existing object in any schema**, but
**can create its own scratch objects in `public`**. DEV (PG15+) and UAT (PG16) are unaffected —
PG15 removed that default, and `CREATE TABLE public.x` is refused there.

To close it, someone with the OCI master role (`pluginliveprd`, member of `oci_admin_role`; its
credential is **not** on the jump host) runs:

```sql
GRANT CREATE ON SCHEMA public TO plproduction;  -- keep app migrations working
REVOKE CREATE ON SCHEMA public FROM PUBLIC;     -- this is the PG15+ default
```

The `GRANT` first is not optional: `plproduction`'s own `CREATE` on `public` also comes from the
`PUBLIC` grant (it owns the four tables there but not the schema), so revoking without it would
break any future migration that creates a `public` table.

## The role

Created by `PluginLive-Technologies/DB-Scripts` →
`Tester Read-Only DB Access/20260803T104643Z__tester_readonly_role.sql`.

- `LOGIN`, `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`
- `GRANT USAGE` + `GRANT SELECT` on every non-system schema, current **and** future objects
  (via `ALTER DEFAULT PRIVILEGES` per table owner)
- `statement_timeout=120s`, `idle_in_transaction_session_timeout=60s` so an ad-hoc tester query
  can't pin a connection
- Applied: **DEV, UAT and PROD — all 2026-08-03.**

Each grant in the schema loop is wrapped in its own exception block. That is what makes the same
file runnable on PROD, where the running role owns the tables but not every schema: an
un-grantable statement is skipped with a `NOTICE` instead of aborting the run and discarding the
grants that already succeeded.

**Re-run the migration after adding a new schema** — the grant loop covers schemas that exist at
run time, and default privileges only cover new tables in already-granted schemas. It is
idempotent (re-running also resets the password).

The password lives in `scripts/ro-query.sh` on the DEV box; the SQL takes it via
`PGOPTIONS="-c pl.ro_password=…"` so it is never committed.

## Related

- Tester sessions are pointed at this helper by `TESTER_PROMPT` in
  `whatsapp-engineer/claude_manager.js`.
- The global `postgres` MCP server is a separate path: DEV only, connects as the admin
  `pldevadmin`, but the MCP server itself wraps every query in a read-only transaction
  (verified — a `SET TRANSACTION READ WRITE` escape attempt creates nothing).
