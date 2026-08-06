# Banking Job Readiness: hosted Supabase → PluginLive PostgreSQL (UAT)

**Status (2026-08-06):** infrastructure stood up and verified; **data migration blocked on Supabase
credentials**. The live site at `banking.uat.pluginlive.com` is **untouched** and still served
statically from `~/bankingjobreadiness/dist` against hosted Supabase project `kbwjokmmzkgjwiqelrdc`.

Plan document:
<https://bmv2bqg5gpcd.compat.objectstorage.ap-mumbai-1.oraclecloud.com/pl-uat-public-docs/prds/PRD-banking-supabase-to-postgres.html>

## What exists now

Compose project on the UAT box at `~/banking-sb/`. Ports 820x, clear of EduSpeak's 810x.

```
banking-sb-db         127.0.0.1:5442   PostgreSQL 16, wal_level=logical, max_connections=200
banking-sb-gateway    127.0.0.1:8200   nginx, routes the Supabase wire protocol
banking-sb-rest       127.0.0.1:8201   PostgREST 12.2.3
banking-sb-auth       127.0.0.1:8202   GoTrue v2.158.1
banking-sb-storage    127.0.0.1:8203   storage-api v1.11.13
banking-sb-functions  127.0.0.1:8204   edge-runtime v1.58.2, 80 functions
banking-sb-realtime   127.0.0.1:8205   realtime v2.34.7
```

All six services verified: gateway/auth/rest/storage/functions return 200, realtime returns **101
Switching Protocols**, and **all 80 edge functions load and respond**.

## Why Banking gets its own PostgreSQL, unlike EduSpeak

EduSpeak shares the UAT cluster. Banking does not, for three reasons:

1. **Realtime is load-bearing.** 12 `postgres_changes` subscriptions drive live proctoring,
   candidate notifications, bulk-export progress and video-lesson admin. That needs
   `wal_level = logical`, which on the shared cluster means restarting `uat_pluginlive`.
2. The shared cluster caps `max_connections` at 100 across every UAT service.
3. Its `idle_session_timeout` silently killed pooled connections and caused 500s on EduSpeak
   sign-in. The dedicated instance does not set it, and the roles pin it to 0 anyway.

## Measured coupling (release bundle `a5a6b62`, 2026-08-05)

| Surface | Banking | EduSpeak |
|---|---|---|
| Files importing the client | 210 | 165 |
| `.from()` calls | 946 | 655 |
| Distinct tables queried | 112 | 164 |
| Edge functions invoked / shipped | 65 / **80** | 89 / 111 |
| `supabase.auth.*` calls | 30 | 66 |
| Realtime `postgres_changes` | 12 | 8 |
| Storage buckets | **12** | 1 (empty) |

Chokepoint is `src/integrations/supabase/client.ts` (210 importers), reading
`VITE_SUPABASE_URL` / `VITE_SUPABASE_PUBLISHABLE_KEY` with **no hardcoded fallback** — cleaner than
EduSpeak's. Three `src/lib/mcp/tools/*` files build their own client from `process.env`, server-side
only, so they do not affect the browser bundle.

## Two new gotchas, not seen on EduSpeak

**`GRANT USAGE ON SCHEMA storage` — a 42P01 that is really a permissions problem.** storage-api
returned `DatabaseError ... select "id", ... from "buckets"` with SQLSTATE **42P01
(relation does not exist)** even though `storage.buckets` existed and
`supabase_storage_admin` could read it in psql. The cause is that storage-api `SET ROLE`s to the
request role, and **when a role lacks USAGE on a schema, PostgreSQL reports objects in it as
"does not exist" rather than "permission denied"**. Fixed by
`GRANT USAGE ON SCHEMA storage TO anon, authenticated, service_role` in `03_grants.sql`.

Time was wasted first chasing `search_path`, which was a red herring: `PGOPTIONS`, a connection
string `?options=`, `ALTER ROLE ... SET search_path`, `ALTER DATABASE ... SET search_path` and the
supported `DATABASE_SEARCH_PATH` were all tried, and the DB log confirmed
`SET search_path TO storage,public,extensions` was already being issued. **On a 42P01 from a
Supabase service, check schema USAGE before touching search_path.**

**Realtime tenant wiring.** Two distinct failures:
- `TenantNotFound: Tenant not found: realtime` → requests resolve the tenant by `external_id`,
  falling back to `APP_NAME` (`realtime`), but `SEED_SELF_HOST` seeds `realtime-dev`. Set
  **`SELF_HOST_TENANT_NAME: realtime`** so they match.
- `(ArgumentError) non-alphabet character found: "_"` → `_realtime.tenants.jwt_secret` is stored
  **encrypted with `DB_ENC_KEY`**. Hand-inserting the plaintext JWT secret breaks its base64 decode
  at connect time. Let the seeder write it: delete the tenant rows and restart the container.
  A correctly seeded secret is 108 chars.

Realtime also needs the connecting role to hold `REPLICATION`; `supabase_admin` is created with it
in `00_provision_roles.sql`.

## EduSpeak lessons applied on day one

Rather than rediscovered: `idle_session_timeout = 0` pinned on all five pooled roles;
`cpuTimeSoftLimitMs` / `cpuTimeHardLimitMs` set in the edge-runtime main router alongside
`workerTimeoutMs`; `auth.uid()` created then handed to `supabase_auth_admin` to own, and written to
read both the legacy singular GUC and the modern claims JSON; `DB_INSTALL_ROLES=false` on
storage-api; `GRANT CREATE ON DATABASE` for GoTrue, storage-api and Realtime; publication
`supabase_realtime` created **empty** so it can be scoped to the 12 subscribed tables rather than
`FOR ALL TABLES`.

## Blocked: we do not hold the Supabase credentials

Verified by probing `kbwjokmmzkgjwiqelrdc` directly:
- The anon key from `~/bankingjobreadiness/.env` is valid and unexpired (to 2036); table reads
  return `200 []` because RLS correctly refuses anonymous access.
- `/rest/v1/` returns `"Only the service_role API key can be used for this endpoint"`.
- `supabase projects list` for the org we hold a token for shows only `eduspeak-uat` and
  `ucat-prod`. **The Banking project is in a different Supabase account.**

Needed to proceed: an access token (`sbp_…`), the `service_role` key, and the database connection
string. Without them there is no schema dump, no data, no storage inventory, no auth users, and no
way to read the 14 third-party function secrets. Worth resolving regardless of this migration:
nobody on the platform team can currently back this project up.

**The bundled migrations are not a substitute.** The 118 files in `supabase/migrations/` create only
43 tables while the frontend queries 112 — they are incremental on a Lovable-created base. The
authoritative schema has to come from `pg_dump`, exactly as with EduSpeak.

## Next steps once credentials arrive

1. Dump schema + data; inventory all 12 buckets (object count and bytes — this sizes the timeline).
2. Restore pre-data → data → post-data with FKs `NOT VALID`, then validate individually.
3. Re-run `03_grants.sql` (new tables arrive ungranted).
4. Import `auth.users` / `auth.identities` with bcrypt hashes intact.
5. Populate publication `supabase_realtime` with the 12 subscribed tables only.
6. Copy storage objects; reproduce the 53 storage RLS policy statements.
7. Load the 14 function secrets — note MSG91 / SMS / Twilio send real messages; EduSpeak
   deliberately left its equivalents unset.
8. Repoint `.env`, **rebuild on the UAT box**, grep the bundle for `supabase.co`, swap `dist/`.
   Keep a tarball of the pre-cutover `dist/` plus the old `.env` for rollback.

## Rollback today

Nothing to roll back: the live site was never modified. To remove the new infrastructure entirely,
`cd ~/banking-sb && docker compose down -v`.
