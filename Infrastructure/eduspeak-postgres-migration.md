# EduSpeak: hosted Supabase → PluginLive PostgreSQL (UAT)

**Status:** UAT live on PluginLive PostgreSQL since 2026-08-05. DEV still on hosted Supabase. PROD does not exist yet.

EduSpeak (`eduspeak.uat.pluginlive.com`, repo `PluginLive-Technologies/eduspeak-india`) was a
Lovable-generated app whose real backend was a hosted Supabase SaaS project. UAT now runs entirely
on our own infrastructure: data in our OCI PostgreSQL, auth/REST/storage/functions in our own
containers. **Nothing in the app makes a request to `*.supabase.co` any more.**

## Why not a rewrite

The whole frontend reaches Supabase through **one module**, `src/integrations/supabase/client.ts`,
imported by 165 files, and `src/lib/databaseConfig.ts` already carried a provider switch
(`supabase | supabase_compatible | external_api`). So rather than rewriting 655 `.from()` queries,
89 `functions.invoke()` calls, 66 `supabase.auth.*` calls and 8 realtime channels, we kept the
supabase-js wire protocol and swapped the origin. The frontend diff was **3 environment variables**.

The Supabase pieces are open source, so self-hosting them removes the SaaS dependency without
removing the compatibility. If we later want EduSpeak on standard Express+Prisma, the
`external_api` provider allows a vertical-by-vertical strangler-fig with no big-bang cutover.

## Architecture

```
Browser  (unchanged @supabase/supabase-js)
  |
nginx eduspeak.uat.pluginlive.com   (/etc/nginx/sites-available/eduspeak-uat.conf)
  |-- /            -> eduspeakreact  :3008   Vite static
  |-- /api/        -> eduspeaknode   :8086   pre-existing Node adjunct, unchanged
  '-- /sb/         -> eduspeak-sb-gateway 127.0.0.1:8100  (nginx container)
                        |-- /rest/v1      -> postgrest      v12.2.3
                        |-- /auth/v1      -> gotrue         v2.158.1
                        |-- /storage/v1   -> storage-api    v1.11.13
                        |-- /functions/v1 -> edge-runtime   v1.58.2  (106 Deno fns)
                        '-- /realtime/v1  -> 501, not deployed
                                |
                    OCI PostgreSQL 16.14  140.238.245.202:5441
                         database: eduspeak_uat
```

Compose project lives on the UAT box at `~/eduspeak-sb/` (`docker compose ps` to inspect).
Ports 3000/4000/5000 were already taken on that box, so services are remapped to 810x and only
the gateway is published, on loopback.

## What was migrated

| Object | Count |
|---|---|
| Tables | 205 |
| RLS policies | 438 (199 tables with RLS enabled) |
| Foreign keys | 108 (103 validated, 5 grandfathered — see below) |
| Triggers | 82 |
| SQL functions | 28 |
| Edge functions | 108 deployed (100 were live on Supabase; the repo carries 8 extra) |
| `auth.users` | 2, bcrypt hashes intact, nobody forced to reset |
| Storage | bucket `pilvidya`, 0 objects |

Schema/roles/grants scripts are in `PluginLive-Technologies/DB-Scripts` under
**`EduSpeak Postgres Migration/`** (UTC-timestamp order, PROD marked pending).

## How RLS survives without Supabase

The 438 policies call `auth.uid()` 318 times. That is not proprietary: it reads the request's JWT
claims out of a session GUC. PostgREST verifies the JWT, sets `request.jwt.claims`, then `SET ROLE`s
to `anon` / `authenticated` / `service_role`. The database enforces the policies exactly as before.

GoTrue's own migrations install an `auth.uid()` that reads **both** the legacy singular
`request.jwt.claim.sub` GUC and the modern `request.jwt.claims` JSON, so it works with PostgREST
v12 (`PGRST_DB_USE_LEGACY_GUCS=false`). Do not hand-write a singular-only version over it.

Verified by negative tests (8/8), not just positive ones: two real users cannot read each other's
`student_profiles`; `anon` reads 0 rows from `student_profiles`, `student_test_history`,
`student_question_history`.

## Gotchas hit during the migration

**Roles are cluster-wide.** `anon`, `authenticated`, `service_role` are load-bearing names — the
restored policies say `TO authenticated` — so they cannot be prefixed. They now exist on the shared
UAT cluster but hold no privileges outside `eduspeak_uat`.

**GoTrue and storage-api expect roles we do not have.** Their migrations `GRANT` to `postgres`,
`supabase_admin`, `dashboard_user`, `supabase_realtime_admin`. Our superuser is `pluatadmin`, so
those are created NOLOGIN purely to let the vendor migrations resolve.

**GoTrue must own `auth.uid()`.** If you pre-create it as another role, GoTrue's
`CREATE OR REPLACE FUNCTION auth.uid()` fails with `must be owner of function uid`.

**storage-api needs `DB_INSTALL_ROLES=false`.** With `true` it tries `CREATE ROLE` and dies with
`permission denied to create role`. Both it and GoTrue also need `GRANT CREATE ON DATABASE`.

**5 foreign keys cannot be validated.** The source project bulk-loaded rows with
`session_replication_role = replica`, so it holds the same orphans while *claiming*
`convalidated = true`. Ours are honest: created `NOT VALID`, so the constraint is declared and
enforced for new writes while legacy rows are grandfathered. Do **not** delete the orphans —
all 57 `curriculum_content` rows are orphaned and the app renders them.

- `assessment_assignments_assessment_id_fkey`, `curriculum_content_curriculum_topic_id_fkey`,
  `student_profiles_user_id_fkey`, `student_progress_user_id_fkey`, `user_roles_user_id_fkey`

**`_shared/` is not downloadable.** `supabase functions download` returns only each function's own
entrypoint, so 73 of the 100 functions had unresolved `../_shared/*.ts` imports. The repo carries
`supabase/functions/_shared/` — use the repo as the source of truth; it is a strict superset of what
was deployed.

**There are TWO checkouts of this repo on the boxes, at different commits.** Deploy functions from
`~/frontend/eduspeak-india-react/supabase/functions` (commit `7370534`), **not**
`~/api/eduspeak-india-node/supabase/functions` (commit `a3e2935`, an ancestor). The older one is
missing `admin-dashboard-data` and `database-dump`, and without them the Admin Dashboard renders
all-zero stats plus a banner reading `function 'database-dump' not found`. Both are admin-gated
(anon gets 403) and need only `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`.

**Realtime is deliberately not deployed.** It needs cluster-wide `wal_level = logical`, currently
`replica`. Changing it restarts the cluster shared with `uat_pluginlive`, so it was not done. The
gateway returns **501** on `/realtime/v1/` so supabase-js fails fast instead of hanging on a
WebSocket that will never upgrade. 8 subscriptions are affected and fall back to refresh/poll.

**`public/schema.sql` leaked the DEV project.** That static admin-export artifact had 3
`cron.schedule` URLs pointing at `bniueuuegrsgrhjlybga.supabase.co` with a DEV anon key embedded.
The app never executes it, but it shipped in the bundle. Rewritten to the gateway with the key
placeheld. **Grep the built bundle for `supabase.co` before every cutover.**

## Security findings

**Fixed here.** The hosted project grants `anon` full `DELETE/INSERT/TRUNCATE/UPDATE` on 185 tables,
and 6 tables carry no RLS at all (`institute_users`, `institutes`, `profiles`, `question_bank`,
`student_progress`, `user_roles`). Net effect on the hosted project **today**: anyone holding the
public anon key can read and write `user_roles`, i.e. grant themselves `teacher`, or truncate it.
Verified live — `GET /rest/v1/user_roles` with only the anon key returns 200 with rows.

On our stack `anon` is **SELECT-only**. No app path writes as `anon`: student registration calls
`ensureAuthSession()` (anonymous GoTrue sign-in, which yields role `authenticated`) before writing,
and the signup-time `profiles`/`user_roles` inserts run against the session `signUp()` just returned.

**Also fixed.** `student_profiles.password_hash`, `student_profiles.active_session_token` and
`parent_profiles.active_session_token` were SELECT-able through the API. Replaced table-level SELECT
with column-scoped SELECT. Reads of those columns now 403; inserts and updates still work.
This required one app change: `AdminDashboard.tsx` used `.select("*")` on `student_profiles` and now
names its 5 columns. **If you add a `select("*")` on `student_profiles` or `parent_profiles` it will
403** — name the columns.

**Still open, pre-existing.** `integration_webhooks.secret` and `status_webhooks.secret` remain
readable, because admin screens read those tables with `select("*")`. Closing them needs the same
column-naming treatment first.

**Still open, upstream.** The 6 RLS-less tables above are unchanged from the source project.
`question_bank` being anon-readable is intentional; the other five deserve review.

## Function secrets

The hosted UAT project has **no third-party secrets set at all** — `supabase secrets list` returns
only the 7 auto-injected `SUPABASE_*` values. So Razorpay, WhatsApp, Resend, VAPID, YouTube and
Lovable-backed functions already fail on UAT and our deployment matches that. `functions-secrets.env`
in `~/eduspeak-sb/` is intentionally empty and documents this. Values are staged in
`~/eduspeak-uat-migration/env.sh` (`UAT_FUNCTION_SECRETS`) but were never applied; enabling them
would make UAT start sending real WhatsApp messages and minting real payment links, so it is a
product decision rather than a migration step.

## Verification performed

- 106/106 edge functions respond; status spread 67×200, 26×400 (payload validation), 12×401, 1×500.
  The 500 is `security-regression-scan` reporting findings, and the hosted project returns 500 too.
- Headless browser over `/`, `/auth`, `/student`, `/teacher`, `/status`: all 200, non-empty `#root`,
  **zero** `pageerror`, zero failed requests, and the only external hosts contacted are Google Fonts.
- Signup → `profiles` insert → `user_roles` insert → sign-in → wrong-password rejection → anonymous
  sign-in all pass. Student registration replayed exactly as `StudentEntry.tsx` issues it
  (`insert(...).select("id, display_name").single()`) returns 201.
- Row counts reconciled: `question_bank` 2233, `student_profiles` 28, `user_roles` 45.

## Rollback

Cheap while the hosted project still exists:

```bash
ssh ubuntu@uat.pluginlive.com
cd ~/frontend/eduspeak-india-react/frontend
cp .env.uat.pre-pg-migration.bak .env.uat
docker rm -f eduspeakreact
docker run -d --name eduspeakreact --restart unless-stopped -p 3008:3008 eduspeakreact:pre-pg-migration
```

`eduspeakreact:pre-pg-migration` is the pre-cutover image. Keep the hosted Supabase project alive
and unfrozen for the whole soak; rollback stops being possible once it is deleted.

## UAT test accounts (created 2026-08-05)

EduSpeak has **two unrelated login mechanisms** — do not confuse them.

**Admin** — GoTrue email/password (`supabase.auth.signInWithPassword`) at `/admin/login`.
Dashboard entry is granted by `getAdminAccess()`, which allows either a hardcoded address in
`PLATFORM_ADMIN_EMAILS` (`src/lib/adminAccess.ts`, currently only
`prakash.chinnadurai@gmail.com`) **or** a `staff_ops_roles` row with `ops_role = 'ops_admin'`.
The second route is the one to use for new admins; the allow-list is compiled into the bundle.

| Email | Password | Grants |
|---|---|---|
| `eduspeak.admin@pluginlive.com` | `EduSpeak@Admin#2026` | `user_roles.admin` + `staff_ops_roles.ops_admin` |

**Students** — *not* GoTrue email/password. `/student-entry` takes **mobile + password**: the client
opens an anonymous GoTrue session, then calls the `student_authenticate(p_mobile, p_password_hash)`
RPC. The hash is computed client-side in `src/lib/studentSession.ts` as
`sha256("pilvidya:v1:" + password)` hex, so any seeded row must use exactly that:

```sql
-- python3 -c "import hashlib;print(hashlib.sha256(b'pilvidya:v1:Student@001').hexdigest())"
INSERT INTO public.student_profiles
  (display_name, mobile_number, password_hash, board, class_level, school_name, location, user_id)
VALUES ('Aarav Sharma','9000000001','<sha256 hex>','CBSE','8','Scott School','Chennai', NULL);
```

| Mobile | Password | Name | Class | Board |
|---|---|---|---|---|
| `9000000001` | `Student@001` | Aarav Sharma | 8 | CBSE |
| `9000000002` | `Student@002` | Diya Patel | 9 | CBSE |
| `9000000003` | `Student@003` | Rohan Iyer | 10 | ICSE |
| `9000000004` | `Student@004` | Ananya Nair | 11 | State Board |
| `9000000005` | `Student@005` | Kabir Menon | 12 | CBSE |

Seeding gotchas:
- `password_hash`, `board` **and** `class_level` must all be non-NULL. If any is NULL,
  `student_authenticate` takes the "incomplete profile" branch and returns success *without
  checking the password*.
- Leave `user_id` NULL. The RPC binds it to the caller's anonymous uid on first login and rebinds
  on later logins, so a row bound to a stale uid is not locked out — but seeding it NULL is cleanest.
- `mobile_number` is UNIQUE.

These are UAT-only credentials on non-production data. Rotate or delete before any production use.
