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
| DEV, UAT | Connects as **`pl_tester_ro`**, a role holding `SELECT` and nothing else, with `default_transaction_read_only=on`. Writes are refused **even if the read-only GUC is turned off** — they fail with `permission denied for table …`, not merely `cannot execute UPDATE in a read-only transaction`. |
| PROD | The PROD DB is only reachable from the jump host, so `ro-query.sh prod` delegates over SSH to the pre-existing `/home/ubuntu/scripts/prod-readonly-query.sh` (regex pre-flight + `BEGIN READ ONLY` wrapper). |

The two layers are independent, and both were verified per env: `INSERT`/`UPDATE`/`DELETE`/
`TRUNCATE`/`CREATE TABLE`/`DROP`/`CREATE ROLE` all rejected; `SELECT` unaffected.

**PROD caveat:** `prod-readonly-query.sh` connects as the write-capable `plproduction` and is
guarded only by the script. Running the migration below on `prod_pluginlive` and repointing that
helper at `pl_tester_ro` closes the gap. **Not yet done — PROD is pending.**

## The role

Created by `PluginLive-Technologies/DB-Scripts` →
`Tester Read-Only DB Access/20260803T104643Z__tester_readonly_role.sql`.

- `LOGIN`, `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`
- `GRANT USAGE` + `GRANT SELECT` on every non-system schema, current **and** future objects
  (via `ALTER DEFAULT PRIVILEGES` per table owner)
- `statement_timeout=120s`, `idle_in_transaction_session_timeout=60s` so an ad-hoc tester query
  can't pin a connection
- Applied: **DEV 2026-08-03, UAT 2026-08-03. PROD pending.**

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
