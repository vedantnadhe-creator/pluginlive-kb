# Banking Job Readiness: hosted Supabase → PluginLive PostgreSQL (UAT)

**Status (2026-08-07): DONE on UAT.** `banking.uat.pluginlive.com` runs entirely on PluginLive
infrastructure. Verified in a real browser: **zero requests to `*.supabase.co`**, zero 4xx/5xx from
the API layer, admin login works and the console renders live data.

PROD is untouched and still on hosted Supabase project `kbwjokmmzkgjwiqelrdc`.

Full engineering write-up: `~/banking-pg-migration/MIGRATION-NOTES.md` on the DEV box.
SQL: `PluginLive-Technologies/DB-Scripts` → `Banking Supabase to Postgres/`.

## The constraint that shaped everything

**We never got access to the hosted project.** No `service_role` key, no database URL, no dashboard
membership — the Banking project sits in a Supabase account nobody on the platform team can reach.

So unlike EduSpeak there was **no `pg_dump` to restore**. The schema was rebuilt by replaying the
app repo's own 118 `supabase/migrations/*.sql`, and data was limited to what the public anon key
could read.

> **Correction to the previous version of this page.** It claimed the bundled migrations "create
> only 43 tables while the frontend queries 112" and that "the authoritative schema has to come
> from `pg_dump`". That is **wrong**. A clean replay produces **117 tables** — the full schema.
> The 43 figure came from counting `create table` in the first migrations only. The migrations are
> a complete schema source; they are *not* a complete **data** source.

## Result

| | |
|---|---|
| Tables (public) | 117 |
| RLS-enabled | 117 / 117 |
| RLS policies | 303 public + 23 storage |
| Functions / triggers / FKs / indexes | 173 / 26 / 51 / 844 |
| Storage buckets | 10 (created by the migrations, **empty**) |
| Realtime publication | 17 tables, `REPLICA IDENTITY FULL` |
| Edge functions | 81 deployed, **81 boot clean** |
| Rows | 1,584 seeded by migrations + 8 recovered from hosted |

## Architecture

```
browser (unchanged supabase-js)
  -> nginx banking.uat.pluginlive.com
       /      -> ~/bankingjobreadiness/dist   (static SPA)
       /sb/   -> banking-sb-gateway :8200
                  /rest/v1      -> postgrest    :8201
                  /auth/v1      -> gotrue       :8202
                  /storage/v1   -> storage-api  :8203
                  /functions/v1 -> edge-runtime :8204   (81 functions)
                  /realtime/v1  -> realtime     :8205
                       -> pgvector/pgvector:pg16 :5442  (wal_level=logical)
```

The `/sb/` locations live in `/etc/nginx/sites-available/banking-react.conf` (websocket upgrade for
realtime, 300s timeouts for LLM-backed functions, 500m body limit for storage).

**The DB image is `pgvector/pgvector:pg16`, not `postgres:16-alpine`** — three migrations need the
`vector` extension, which alpine does not ship.

Frontend cutover was 3 env vars, as planned: everything funnels through
`src/integrations/supabase/client.ts`.

## Scripts (`~/banking-sb/`, all idempotent)

| Script | Purpose |
|---|---|
| `rebuild.sh --yes-destroy-data` | full rebuild from nothing; **refuses without the flag** — the DB now holds auth users and recovered rows that are not reproducible from the repo |
| `provision.sh` | roles, schemas, extensions, publication ownership |
| `replay-migrations.sh` | replays the 118 migrations; `fixups/` override upstream by filename |
| `sync-functions.sh` | repo functions → stack, then overlays `function-fixups/` |
| `merge-hosted-data.py` | merges the recovered rows by natural key |

Upstream migration files are **never edited**. Deviations live as whole-file overrides in
`fixups/`, so a repo pull cannot conflict and `diff` shows every change.

## The replay: 3/118 → 119/119

The first run applied **3 of 118**, which looked catastrophic and was not. Each migration file is
replayed as a **single transaction**, so when the *first* file failed on `REFERENCES auth.users(id)`
(`banking_owner` lacked `USAGE` on `auth`), its `CREATE TABLE public.profiles` rolled back too and
115 files cascaded off that one root cause. Granting membership in `supabase_auth_admin` /
`supabase_storage_admin` (plus `INHERIT`) took it straight to 102/118.

> **Debugging lesson: on a cascading replay, read the FIRST failure, not the histogram.** The tail
> was 77 "relation does not exist" errors that all evaporated from one permissions fix.

Migrations run as `banking_owner`, **not** as superuser — 33 of them create `SECURITY DEFINER`
functions, and a superuser-owned definer function bypasses RLS entirely.

### The six fixups

1. **Drift columns** (`20260710130000_selfhost_drift_columns.sql`, a new file). Six columns are
   *read* by the migrations and *created by none of them* — added by hand on the hosted project and
   never captured: `candidate_menu_permissions.default_menu_key`, `menu_access_controls.is_core`,
   `admin_tab_permissions.role`, `assessments.module_id`, `assessments.difficulty`,
   `project_feedback.metadata`. It also adds `profiles.role` **nine migrations earlier** than
   upstream does, because `20260717140000` reads it and `20260726090100` creates it — an ordering
   that only ever worked because the hosted DB already had the column.
2. **`UPDATE … FROM` referencing the update target** (3 sites, 2 files) — PostgreSQL rejects
   referencing the target table inside a FROM-list join's `ON` clause. Invalid on *any* PostgreSQL.
3. **`min(uuid)`** — no such aggregate; `(array_agg(id ORDER BY id))[1]` is equivalent.
4. **`rbac_role_permissions.menu_label` NOT NULL** — 51 of 115 seeded menu rows have no label.
5. **Duplicate storage policies** — made every `CREATE POLICY` idempotent.
6. **`auth.config` does not exist** — a Supabase *platform* table with no open-source equivalent
   (see below).

## Gotchas worth remembering

**`GOTRUE_JWT_DEFAULT_GROUP_NAME` — the bug that broke every authenticated request.** Unset, GoTrue
stores an **empty** role on new users and mints JWTs with `role: ""`. PostgREST then runs
`SET ROLE ""` and *every* authenticated call fails with `400 role "" does not exist` — while
anonymous browsing looks perfectly healthy, so it survives a smoke test. The hosted platform sets
this for you. Set it explicitly and backfill `auth.users.role = 'authenticated'`.

**`auth.config` is hosted-only.** `20260728150000_fix_security_vulnerabilities` sets the password
policy by `UPDATE auth.config`. Open-source GoTrue has no such table; the equivalents are env vars:
`GOTRUE_PASSWORD_MIN_LENGTH`, `GOTRUE_PASSWORD_REQUIRED_CHARACTERS`, `GOTRUE_PASSWORD_HIBP_ENABLED`.
HIBP is reachable from the UAT box (~60ms, k-anonymity — no password leaves the box).

**`GRANT USAGE ON SCHEMA storage` — a 42P01 that is really a permissions problem.** storage-api
reported `relation "buckets" does not exist` even though it existed: when a role lacks USAGE on a
schema, PostgreSQL says "does not exist" rather than "permission denied". **On a 42P01 from a
Supabase service, check schema USAGE before touching `search_path`** — much time was lost on
`PGOPTIONS`, `?options=`, `ALTER ROLE … SET search_path` and `DATABASE_SEARCH_PATH`, all red
herrings.

**Realtime tenant wiring.** `TenantNotFound` → set `SELF_HOST_TENANT_NAME: realtime` so the tenant
`external_id` matches `APP_NAME`. `(ArgumentError) non-alphabet character found: "_"` →
`_realtime.tenants.jwt_secret` is stored **encrypted with `DB_ENC_KEY`**; let the seeder write it
rather than hand-inserting plaintext. Realtime's role needs `REPLICATION`.

## Two genuine upstream defects in edge functions

* **`live-session-rsvp` does not parse.** The `if (action === "rsvp")` block is never closed, which
  orphans the `catch`. The same missing brace makes its `cancel` branch unreachable (nested inside a
  block already requiring `action === "rsvp"`). **Still in the repo** — a pull reintroduces it.
* **`mcp`** — the *committed* version imports `npm:C:\Users\Prakash\Downloads\...`, a Windows path
  that cannot resolve anywhere. The working tree holds a correct Lovable-regenerated bundle; only
  its OAuth issuer was hardcoded to the hosted project and now reads from the environment.

## Data: 8 rows, and why that is all there is

All **117** tables were probed on the hosted project with the public anon key. Exactly **three**
return rows: `domains` (10), `subjects` (24), `testimonials` (3). The other 114 return 0 — Banking's
RLS is correctly locked down, and notably it does **not** have the anon-writable `user_roles` hole
found on EduSpeak.

Merging by `id` **fails**: the migrations seed these tables with *different UUIDs for the same
logical rows* (`retail-banking` exists in both), so an id-merge hits a duplicate-slug violation, and
skipping the parents then orphans every hosted subject. `merge-hosted-data.py` merges by **natural
key** instead — same-slug rows keep the seeded id (the rest of the seed references it), new rows are
inserted, and an inserted subject's `domain_id` is remapped to the local domain with the matching
slug. Net: **2 domains, 3 subjects, 3 testimonials**. Idempotent, 0 orphaned FKs.

Real candidates, attempts, progress, storage objects and auth users **remain unrecoverable without
hosted credentials.**

## App change

`src/lib/adminErrorLogger.ts` hardcoded `https://kbwjokmmzkgjwiqelrdc.supabase.co`. Those constants
are `startsWith` matchers for a fetch interceptor, so they never *sent* anything to Supabase — but
left as-is they silently stop matching after cutover and admin error logging quietly records
nothing. Now derived from `VITE_SUPABASE_URL`.

## Known inert remnant

`src/components/admin/AdminSecurityMigration.tsx` still references `api.supabase.com` and defaults a
"Project Reference" field to `kbwjokmmzkgjwiqelrdc`. It is an admin tool for the Supabase
**Management** API, fires only on click, and is non-functional post-migration. Left in place —
removing an admin feature is a product decision.

## Still open

* **PROD pending.** Every SQL header says `PROD — pending`.
* **`functions-secrets.env` is empty.** The 14 third-party keys (ELEVENLABS, JDOODLE, MSG91, TWILIO,
  YOUTUBE, LOVABLE, GITHUB, …) live in the hosted project. Functions needing them fail at *call*
  time, not boot time. **MSG91 / SMS / Twilio send real messages** — confirm before enabling.
* **Storage buckets are empty.** Hosted objects were never readable.
* Nobody can currently back up the hosted Banking project. Worth resolving regardless of this
  migration.

## Rollback

Pre-cutover `dist/` and `.env` are kept on the UAT box as
`~/bankingjobreadiness/dist.bak-premigration-*` and `.env.bak-premigration-*`; the nginx conf as
`banking-react.conf.bak-premigration-*`. Restore those three and reload nginx to go back to hosted
Supabase. To remove the new infrastructure entirely: `cd ~/banking-sb && docker compose down -v`.
