# Banking Job Readiness: hosted Supabase → PluginLive PostgreSQL (UAT)

**Status (2026-08-11): DONE on UAT, with real production data. Deployed at commit `a91fbbc`.**
`banking.uat.pluginlive.com` runs entirely on PluginLive infrastructure. Verified in a real
browser: **zero requests to `*.supabase.co`**, zero 4xx/5xx from the API layer, admin login works
and the console renders live counts (61 candidates, 106 quizzes, 17 assessments taken).

Infrastructure cut over 2026-08-07. A CSV export of the hosted `public` schema was supplied on
2026-08-09 and loaded: **13,904 of 13,925 rows across 31 tables, 0 skipped**, giving 15,472 rows
across 46 tables with **all 51 foreign keys orphan-free**.

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
| Tables (public) | 119 |
| RLS-enabled | 119 / 119 |
| RLS policies | 343 public + 23 storage |
| Functions / FKs | 173 / 50 |
| Storage buckets | 10 (created by the migrations, **empty**) |
| Realtime publication | 17 tables, `REPLICA IDENTITY FULL` |
| Edge functions | **82** deployed, **82 boot clean** (81 until `request-password-reset` arrived 2026-08-10) |
| Rows | **16,106** across 48 populated tables |
| auth.users | 61 — 59 reconstructed from the export, **passwordless by design** |

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
| `merge-hosted-data.py` | merges the 8 anon-key-recovered rows by natural key |
| `make-auth-users.py [--apply]` | rebuilds the 59 auth identities the CSV export references |
| `load-csv-export.py [--dry-run]` | loads the hosted CSV export (staging + native `COPY`, FK-ordered) |
| `verify-load.py` | walks all 51 FKs looking for orphans |
| `set-user-password.sh <mobile\|email> '<pw>'` | enables one imported account |

Edge-function deviations live in `function-fixups/<name>/`, overlaid by `sync-functions.sh`:
`main` (the JWT gate), `live-session-rsvp` (unbalanced brace) and `mcp` (hosted OAuth issuer).

## Deployment 2026-08-11 — `a91fbbc`

Advanced UAT by 47 commits from `8877a68` to `a91fbbc`. Applied all 22 migrations from
`20260811014830` through `20260812021000` transactionally after a `pg_dump` backup. These repair
the schema contracts for learning paths, AI Coach/practice, coding challenges, RAG, videos,
projects, proctoring analytics, practice plans, student learning, and the merged admin module
catalog. Grants and the PostgREST schema cache were refreshed afterward.

The MCP fixup was rebased onto the new `@lovable.dev/mcp-js@0.26.2` / Zod 4 generated bundle;
without that, the whole-file overlay would have silently rolled the deployed MCP function back to
the older 0.23.0 implementation. It now changes only the OAuth issuer to the self-hosted origin.

Verification: 82/82 edge functions boot clean; no-auth function request returns 401; all 50 current
foreign keys have zero orphan rows; seven containers are running; anonymous and admin browser E2E
pass with no `*.supabase.co` traffic or API 4xx/5xx. Unit suite: 275/282 pass; the seven failures
are upstream test-catalog drift in `adminTabsAccessDenied` and `menuRbacReconciliation`, unchanged
by the self-hosted patches.

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

## The hosted CSV export (2026-08-09)

A CSV dump of the hosted `public` schema (44 tables) was supplied and loaded. **13,904 of 13,925
rows, 0 skipped for a missing FK parent.**

### `_table_index.csv` row_count is a LINE count, not a row count

It says `topics,15918`. The file has 15,919 physical lines but only **482 rows** — topic bodies are
markdown spanning many lines. Confirmed three ways: the CSV parses with zero malformed rows, all
482 ids are unique, and exactly 482 lines begin with a UUID. Same for `assessment_responses`
(11,241 rows, not 20,739) and `chat_history` (129, not 3,950). **Do not size work off that
manifest.**

### auth.users had to be reconstructed — and the accounts have no password

The export is `public`-only, but eight public tables FK to `auth.users`. 59 identities were rebuilt
with the auth email derived as **`<mobile>@bankready.app`** — that is what `Login.tsx` builds to
sign candidates in, so it reconstructs the real login identity rather than the contact email
(44 of 59 have a mobile; the rest get NULL).

**They carry no password and cannot sign in.** The hosted bcrypt hashes were never available.
Enable one deliberately with `./set-user-password.sh <mobile|email> '<password>'`, which goes
through GoTrue's admin API so the hash matches what sign-in verifies.

> **GoTrue gotcha:** `confirmation_token`, `recovery_token`, `email_change_token_new` and
> `email_change` are nullable in the schema but GoTrue scans them into non-nullable Go strings.
> Left NULL, every read of the row 500s with `Database error loading user` on both sign-in and the
> admin API. They must be `''`.

### Taxonomy is remapped, not duplicated

`domains.slug` is UNIQUE and 8 of 10 exported domains collide with migration-seeded rows under
*different* uuids; `subjects` is UNIQUE on `(domain_id, slug)` and 21 of 24 collide. Local ids stay
canonical (seed-only tables like `admin_modules` reference them) and incoming FKs are rewritten
through a remap table. Colliding rows still take hosted's attribute values.

### 21 rows hosted allowed and our schema does not

`user_module_access` arrived with 16 duplicate `(user_id, module_id)` and 5 duplicate
`(user_id, group_id)` pairs. Those partial unique indexes come from hand-written migrations **never
applied to hosted**, so hosted permitted the duplicates. Collapsed to the newest per key, 379 → 358.

> **Loader lesson:** `pg_constraint` does **not** contain `CREATE UNIQUE INDEX … WHERE …`. Read
> `pg_index` or partial unique indexes are invisible. And when de-duplicating against one, apply
> its **predicate** — `profiles` has `UNIQUE(mobile) WHERE mobile <> ''`, and matching on `mobile
> IS NOT DISTINCT FROM mobile` silently deleted two admin rows that both had `''`, rows the index
> does not even cover.

## ⚠ Edge functions were reachable with NO auth header (fixed 2026-08-10)

The self-hosted `functions/main/index.ts` router dispatched **without verifying anything**. The
hosted platform verifies a JWT on every function unless `config.toml` sets `verify_jwt = false`,
and this repo sets it nowhere — so hosted requires a token and our stack required none.

Verified exploitable: `POST /sb/functions/v1/seed-admin-user` with **no Authorization header**
returned `200 {"ok":true}` and reset `admin@bankready.app` to a password **hardcoded in the repo**
(`seed-admin-user/index.ts` lines 16-17). Anyone who could reach the host could take an admin
session on a box holding 59 real people's PII.

This is also how that account came to exist here at all: the 81-function boot test POSTs `{}` to
every function, and `seed-admin-user` has no guard of its own, so the smoke test created it.

**Fixed** in `function-fixups/main/index.ts`: HS256 signature + `exp` verification against
`SUPABASE_JWT_SECRET` (added to the `functions` service in compose), default-deny, with a
`PUBLIC_FUNCTIONS` allowlist kept in sync with `config.toml` (currently empty). Fails closed if the
secret is unset. After the fix: no header → 401, forged signature → 401, all 81 functions still
reachable with the app's own key.

> **Parity, not a complete fix.** The anon key is itself a valid JWT and is public — it ships in the
> JS bundle. Functions doing privileged work still need their own guard, the way `admin-bootstrap`
> checks `x-bootstrap-token`. **`seed-admin-user` has no such guard and should be deleted or gated
> upstream** — and because hosted also accepts the anon key, it is callable on PROD today.

## ⚠ Any signed-in user can read every profile (pre-existing)

Three app policies grant **every authenticated user** read access to all rows:

```
profiles        "Authenticated can view all profiles for leaderboard"        USING (true)
module_progress "Authenticated can view all module progress for leaderboard" USING (true)
quiz_attempts   "Authenticated can view all quiz attempts for leaderboard"   USING (true)
```

RLS policies are OR'd, so these override the narrower "own row" ones. Verified against the live
site: a plain `candidate` reads other people's **name, mobile, email and institute**.

**Not introduced by the migration** — the policies come from Lovable migration
`20260316070317_bc5a1b1a-…`, which *is* applied on hosted, so PROD behaves identically. What is new
is that UAT now holds 59 real people's PII.

`20260728150000_fix_security_vulnerabilities.sql` is meant to fix exactly this and **does nothing**:
it drops `"Authenticated can view all progress"` while the real policy is `"Authenticated can view
all module progress for leaderboard"`. `DROP POLICY IF EXISTS` on a non-existent name succeeds
silently. Same for `quiz_attempts`; `profiles` it never attempts.

The pattern is app-wide: **78 tables** carry a `USING (true)` SELECT policy for `authenticated`,
including `students`, `payment_requests`, `trainers` and the `proctoring_*` tables.

**Deliberately not fixed here.** `/leaderboard` is a shipped page backed by these policies; the
right fix exposes only display fields (a view or column-scoped policies) and is a product decision.

## Data recovered before the export: 8 rows

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

## 2026-08-14 — redeployed to `3b12b94`

Advanced Banking UAT by 22 commits from `bade695` to `3b12b94`. Applied the two new migrations
(`20260813131604` and `20260813163337`) transactionally as `banking_owner`, refreshed grants, and
synced 83 edge functions with all three self-hosted overlays (`main`, `live-session-rsvp`, `mcp`).
The release adds the AI Coach thread/message persistence RPCs and tightens leaderboard/profile
read policies. The AI Coach tables were already present, so their idempotent migration refreshed
the surrounding functions, privileges, and indexes without changing existing data.

The MCP overlay was rebased onto the newly regenerated upstream bundle and now changes only its
OAuth issuer to the public self-hosted `/sb/auth/v1` origin. The ElevenLabs secret remained in the
server-side functions environment. A full DB dump, `dist/`, and `.env` rollback snapshot were
saved with stamp `20260814T044019Z`.

Verification: production build passed under Node 20; all seven stack containers are up; both the
site and self-hosted APIs respond; unauthenticated `seed-admin-user` remains 401; browser checks
passed anonymous and authenticated/admin routes with zero `*.supabase.co` traffic and zero `/sb`
4xx/5xx after login. The only `supabase.co` string in the bundle is the previously documented,
click-only `api.supabase.com` management tool.

### 2026-08-14 — ElevenLabs primary + Gemini TTS fallback enabled

`ELEVENLABS_API_KEY` and `GEMINI_API_KEY` are set server-side in
`~/banking-sb/functions-secrets.env` (mode `600`). The functions container was force-recreated so
Compose reloaded the env file. Verified ElevenLabs directly (`audio/mpeg`, non-empty MP3) and
forced an ElevenLabs failure with an invalid per-request voice id; the same endpoint automatically
returned Gemini `audio/wav` with non-empty audio. Secret values are not stored in this repo.
