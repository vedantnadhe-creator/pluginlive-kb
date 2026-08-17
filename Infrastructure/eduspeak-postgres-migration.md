# EduSpeak: hosted Supabase → PluginLive PostgreSQL (UAT)

**Status:** UAT live on PluginLive PostgreSQL since 2026-08-05, updated 2026-08-06 to app commit `deacd151`
(410 commits + 141 migrations). DEV still on hosted Supabase. PROD does not exist yet.

**UAT hostname is `pilvidya.uat.pluginlive.com` since 2026-08-06** — see
[Hostname rename](#2026-08-06--uat-hostname-renamed-to-pilvidya) at the bottom. `eduspeak.uat.*`
still resolves but only 301-redirects. Older sections below still say `eduspeak.uat.*`; read the
host as `pilvidya.uat.*` throughout.

EduSpeak (`pilvidya.uat.pluginlive.com`, repo `PluginLive-Technologies/eduspeak-india`) was a
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
nginx pilvidya.uat.pluginlive.com   (/etc/nginx/sites-available/pilvidya-uat.conf)
  |-- /            -> eduspeakreact  :3008   Vite static
  |-- /api/        -> eduspeaknode   :8086   pre-existing Node adjunct, unchanged
  '-- /sb/         -> eduspeak-sb-gateway 127.0.0.1:8100  (nginx container)
                        |-- /rest/v1      -> postgrest      v12.2.3
                        |-- /auth/v1      -> gotrue         v2.158.1
                        |-- /storage/v1   -> storage-api    v1.11.13
                        |-- /functions/v1 -> edge-runtime   v1.58.2  (111 Deno fns)
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
| Edge functions | 111 deployed (100 were live on Supabase; the repo carries the rest) |
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

## 2026-08-06 update — app rolled forward to `deacd151`

Pulled 410 commits (`7370534` → `deacd151`) and rolled the database forward with the repo's
141 `supabase/migrations/*.sql`.

**Migrations.** There is no `supabase_migrations.schema_migrations` ledger in our database (the
original dump was `--schema=public` only), so the migrations were replayed in filename order and
judged by their errors. 69 applied clean, 72 raised only `already exists` (204 such errors) meaning
they were already reflected in the dump. The only non-benign errors are structural and expected:

| Error | Count | Why it is fine |
|---|---|---|
| `schema "cron" does not exist` / `pg_cron is not available` | 7 | We do not run pg_cron. Those migrations only schedule jobs. |
| `publication "supabase_realtime" does not exist` | 5 | Realtime is not deployed here. |
| `pg_net is not available` | 2 | Only used by the cron HTTP calls above. |
| `no unique or exclusion constraint matching the ON CONFLICT` | 1 | `20260709143000` seeding `admin_notification_settings`; the 8 default rows already exist, so it was a no-op. |

Net schema change: 205 → **210 tables**, 438 → **494 policies**, 28 → **35 functions**.
Take a `pg_dump -Fc` backup before replaying (one is at
`~/eduspeak-pg-migration/backups/` on the DEV box).

**Re-run `03_grants.sql` and `05_sensitive_columns.sql` after any migration batch** — new tables
arrive without grants, and the column-scoped SELECT has to be re-applied.

**The student auth flow changed.** `20260713093000_student_mobile_auth_without_anonymous.sql`
moves student login off the "anonymous GoTrue session + direct table write" model onto
`SECURITY DEFINER` RPCs (`student_register_profile`, `student_authenticate`,
`student_complete_profile`, `student_claim_device_session`, `student_verify_device_session`),
each `REVOKE`d from `PUBLIC` and granted `EXECUTE` to `anon, authenticated, service_role`.
Students now authenticate as plain `anon`; no anonymous session is minted. This is a better model
and it did **not** reopen the `user_roles` write hole — `anon` remains SELECT-only there. The only
tables `anon` can now write are `assessment_alt_submissions` and `assessment_imports`, both
intentional upstream. Seeded accounts kept working unchanged.

**Upstream bug found and patched locally: blank `/student` page.** Commit `019db980`
("Restore lovable student landing") uses `GraduationCap` at `StudentDashboard.tsx:275` and `:322`
but never adds it to the `lucide-react` import, so the whole route died with
`ReferenceError: GraduationCap is not defined` and rendered an empty `#root`. Vite does not fail
the build on this, and `npm run typecheck` does not catch it either — only loading the route does.
Patched on the UAT checkout by adding `GraduationCap` to the line-9 import. **This fix is not yet
upstream**; a `git pull` will reintroduce the bug until it is committed.

**`mcp` function returns 500 and that is not a regression.** It is a Lovable auto-generated MCP
server (`npm:@lovable.dev/mcp-js`), never deployed on the hosted project (which 404s it), and not
called by the frontend.

**Verification after the roll-forward:** 22/22 routes render with zero page errors and zero
`supabase.co` requests; RLS negative suite 8/8; 111 functions probed (66×200, 27×400 validation,
13×401, 2×403 admin-gated); admin and all student logins pass end to end.

### Two runtime defects found during the 2026-08-06 roll-forward

**Sign-in 500s after an idle period — `idle_session_timeout`.** The shared UAT cluster sets
`idle_session_timeout = 600000` (10 min). PostgREST, GoTrue and storage-api hold long-lived pooled
connections that sit idle far longer than that on a low-traffic box, so PostgreSQL closes them and
the pool hands out a dead socket on the next request. Symptom: the **first** sign-in after a quiet
period returns `500: Database error querying schema`, and an immediate retry succeeds. The GoTrue
log is definitive:

```
error finding user: FATAL: terminating connection due to idle-session timeout (SQLSTATE 57P05)
```

Fixed by disabling the timeout for the four EduSpeak service roles only
(`authenticator`, `supabase_auth_admin`, `supabase_storage_admin`, `eduspeak_owner`). It is a
per-role setting, so the cluster default and every `uat_pluginlive` role are untouched. Script is in
DB-Scripts as `*__eduspeak_pg_service_role_idle_timeout.sql`. **Restart the pools after applying.**
Watch for this on any other service pooling against this cluster.

**Long functions killed mid-flight — edge-runtime supervisor limits.** The supervisor enforces CPU
and wall-clock limits *independently* of the `workerTimeoutMs` passed to
`EdgeRuntime.userWorkers.create`. With only `workerTimeoutMs` set, `principal-morning-brief` (called
from `PrincipalDashboardPanel.tsx`) logged `CPU time soft limit reached` then
`wall clock duration reached`, and the request hung until the gateway returned 502:

```
worker failure in 'principal-morning-brief': WorkerRequestCancelled: request has been cancelled by supervisor
```

Fixed in `functions/main/index.ts` by also passing `cpuTimeSoftLimitMs: 180_000` and
`cpuTimeHardLimitMs: 300_000` (and raising `memoryLimitMb` to 512). The function then returns 200.

It still takes **~172 s**, which is an upstream inefficiency rather than a migration problem: the
run issues **205 REST calls, 170 of them repeated `app_secrets` lookups** from
`_shared/llm-resolver.ts`. Individual queries are fast (~3 ms) and container egress is fine
(<0.5 s to the LLM providers), so the cost is purely the call count. Caching the secret lookups
would take it to a few seconds. The hosted project answers the same endpoint in 11.5 s only because
it still runs a much older build of that function.

## 2026-08-06 — UAT hostname renamed to `pilvidya`

`eduspeak.uat.pluginlive.com` → **`pilvidya.uat.pluginlive.com`**. The old host still resolves and
**301-redirects** to the new one (it is not a second copy of the app); remove it once nothing
references it.

DNS is **OCI Cloud DNS**, zone `uat.pluginlive.com` (not Route53 — the apex `pluginlive.com` is on
Route53, but this subzone is delegated to OCI). Added an `A` record `pilvidya` →
`129.154.248.225`, the same UAT box IP `eduspeak` already pointed at.

The hostname was baked into four places — all four had to change, and the frontend one needs a
**rebuild**, not a restart, because Vite inlines `VITE_*` at build time:

| Where | Change |
|---|---|
| `/etc/nginx/sites-available/pilvidya-uat.conf` | new vhost, copied from the eduspeak one (`/` → :3008, `/api/` → :8086, `/sb/` → :8100) |
| `/etc/nginx/sites-available/eduspeak-uat.conf` | reduced to a 301 to pilvidya on both :80 and :443 |
| `~/eduspeak-sb/.env` | `SITE_URL`, `API_EXTERNAL_URL` → pilvidya; `docker compose up -d auth` |
| `~/frontend/eduspeak-india-react/frontend/.env.uat` | `VITE_SUPABASE_URL`, `VITE_SITE_URL` → pilvidya; rebuild image |

Cert: `sudo certbot certonly --webroot -w /var/www/html -d pilvidya.uat.pluginlive.com` (expires
2026-11-04, auto-renew registered). The webroot flow needs a plain `:80` vhost answering
`/.well-known/acme-challenge/` **before** the cert exists — that block is kept in the final config
so renewals keep working.

**Gotcha — `vite preview` host allow-list.** `vite.config.ts` has
`preview.allowedHosts: [...]`. It did not include the new host, so the first rebuild served
**HTTP 403 on every route** while `/sb/*` (proxied straight past the Vite server) answered 200 —
i.e. the backend looks perfectly healthy and only the app shell is dead. Add the host there and
rebuild. This file is **committed source**, not env, so the fix belongs in the repo.

**Not a problem, but checked:** `public/schema.sql` still contains three
`https://eduspeak.uat.pluginlive.com/sb/functions/v1/...` URLs in `cron.schedule` calls
(`wellbeing-followup-reminders`, `learning-alert-scan`, `outbox-dispatch`). Those would break on a
301 — `pg_net` does not follow redirects on POST — but **neither `pg_cron` nor `pg_net` is installed
on `eduspeak_uat`**, so no such job exists. If those extensions are ever enabled, fix the URLs first.
No function body in the database references the old host.

Do **not** rename `VITE_SUPABASE_PROJECT_ID` / the JWT `ref` claim (both still `eduspeak-uat`) —
they are baked into the anon and service-role keys and the GoTrue/PostgREST `JWT_SECRET` pairing.

Verified after the rename: `/`, `/auth`, `/student`, `/teacher`, `/status` all 200 with non-empty
`#root`; headless Chromium reports **zero** `pageerror` and zero failed requests; the only hosts the
browser contacts are Google Fonts and `pilvidya.uat.pluginlive.com` (no `eduspeak.*`, no
`*.supabase.co`); anon REST read 200; GoTrue sign-in returns a token and a wrong password is still
rejected; `outbox-dispatch` edge function 200; `eduspeak.uat.*` 301s.

Rollback: `/etc/nginx/sites-available/eduspeak-uat.conf.bak-*`, `~/eduspeak-sb/.env.bak-*`,
`~/frontend/eduspeak-india-react/frontend/.env.uat.bak-*` on the UAT box, plus the previous image
`eduspeakreact:deacd151-fix`.

---

## 2026-08-12 — Convex curriculum master catalogue loaded into `eduspeak_uat`

pilvidya was handed a "Supabase SQL dump" that is in fact a **Convex JSONL export**
(`static-masters-data-dump.zip` and `prod-export-final.zip`, byte-identical for the six master
collections). It carries the curriculum catalogue that the Supabase-derived schema never had a
place for.

### What the export actually contains

| Collection | Rows | Notes |
|---|---|---|
| `boards` | 13 | CBSE, ICSE, NIOS + 10 state boards; each with `classes[]` and `subjects[]` |
| `subjects` | 942 | board × class × subject, with chapter count and weightage |
| `topics` | 5,075 | real NCERT chapter names, learning objectives, prerequisites |
| `questions` | 24,000 | 4,800 each of MCQ / TRUE_FALSE / FILL_BLANK / SHORT_ANSWER / LONG_ANSWER |
| `questionSets` | 600 | 120 each of PRACTICE / QUIZ / UNIT_TEST / MOCK_TEST / BOARD_EXAM |
| `videos` | 30,450 | 5,075 topics × 2 languages (`en-IN`, `hi-IN`) × 3 |
| **total** | **61,080** | 100% referential integrity, zero duplicate `_id` |

The other 21 collections in `prod-export-final` (assessments, subscriptions, practiceSessions,
paymentHistory, streaks, topicMastery, messages, …) are **all empty**. The only non-master rows are
7 Convex auth users — 4 anonymous, 3 email-OTP (`prakash.chinnadurai@gmail.com`,
`alwar.consulting.services@gmail.com`, `prakash@example.com`) — with no password material and no
associated data. They were deliberately **not** imported: they would be dead identities in GoTrue.

### Where it landed

Six additive tables in `public`, one per collection, every source field preserved —
`boards`, `subjects`, `topics`, `questions`, `question_sets`, `videos`. Schema:
`DB-Scripts/EduSpeak Postgres Migration/20260812T171000Z__pilvidya_curriculum_masters.sql`.
Loader: `~/pilvidya-data-import/load_masters.py` on the DEV box.

Primary keys are **`uuid5(6f1b4d2a-1f4e-5c8b-9a3d-70f2c1e4b8a1, convex_id)`**. That is the trick
that makes this cheap: cross-collection references resolve in the loader with no lookup round-trip,
and the upsert is on `convex_id`, so re-running the load updates instead of duplicating (proven —
a second run left all six counts identical). `boards` went 210 → 216 public tables; ~80 MB on disk,
almost all of it `questions` (40 MB) and `videos` (34 MB).

RLS is on for all six: read for `authenticated` only (**`anon` revoked**), write for admins via the
existing `has_role(auth.uid(),'admin')`. Verified through PostgREST, not just in SQL — anon **401**
on every table, non-admin SELECT 200 / INSERT **403**, admin INSERT 201 / DELETE 204.

Field-level verification: all 61,080 rows compared attribute-by-attribute against the source JSONL
(`~/pilvidya-data-import/verify_masters.py`) — 0 missing, 0 extra, **0 field mismatches**. All six
foreign-key relationships (including `question_sets.topic_ids[]`) have 0 orphans.

### What was deliberately NOT done, and why

The two live application tables were left untouched: `question_bank` (2,238 rows) and `topic_media`
(52 rows). Projecting the export into them is a one-command follow-up, held back because the
**content is template-generated placeholder data**, and both surfaces are user-facing:

- All 24,000 `correct_answer` values are literally `"Option 1 for <topic> (MCQ)"` /
  `"Answer for <topic> (LONG_ANSWER)"`; `source` is `"AI Generated"` on every row. `TeacherPortal`
  loads the bank as `order(created_at desc).limit(50)` with no `validation_status` filter, so
  24,000 new rows would **take over the teacher's default view** of a 2,238-row real bank.
- All 30,450 `video_url` values are YouTube **search** links (`youtube.com/results?search_query=…`),
  only **341 distinct**, and every `thumbnail_url` is literally `.../vi/placeholder/...`.
  Projection would create ~10,150 `topic_media` rows against a table that currently holds 52.
- `question_bank.board` is filtered by the app through `normalizeBoard()`, whose `BoardType` is only
  `cbse | icse | state | ib`. All 10 state boards **and NIOS** collapse into one bucket the app
  cannot tell apart — so board fidelity survives only in `public.boards`.

Related pre-existing bug worth knowing: `normalizeBoard()` returns `"state"`, but 75 existing
`question_bank` rows are stored as `"state board"` — those rows are unreachable by the app's own
board filter today.

Backup taken before the load:
`~/pilvidya-data-import/backups/eduspeak_uat-pre-masters-20260812T170953Z.dump`.

---

## 2026-08-13 — app rolled forward to `0f347d74` (111 commits)

Pulled `deacd151` → `0f347d74`. Backups first: `pg_dump -Fc` on the DEV box at
`~/pilvidya-data-import/backups/eduspeak_uat-predeploy-20260813T055338Z.dump`, image tagged
`eduspeakreact:predeploy-20260813T055338Z`, and `.env.uat` + the local-patch diff saved to
`~/pilvidya-predeploy-20260813T055338Z/` on the UAT box.

### Local patches: one retired, two still needed

- **`StudentDashboard.tsx` `GraduationCap` import — now fixed upstream.** The patch documented in
  the 2026-08-06 section can be dropped; upstream imports it correctly. Nothing to re-apply.
- **`vite.config.ts` `allowedHosts` still does NOT list `pilvidya.uat.pluginlive.com`** upstream —
  it lists only the dev and old `eduspeak.uat` hosts. This patch **must** be re-applied on every
  pull or the vite preview server 403s every route while `/sb/*` still looks healthy.
- **`public/schema.sql` still ships DEV URLs** upstream; patch re-applied. (The three remaining
  `eduspeak.uat.pluginlive.com` strings in that file are `cron.schedule` URLs and are inert —
  neither `pg_cron` nor `pg_net` is installed here.)

### Upstream shipped a build-breaking missing file

`AdminDashboard.tsx:42` does `import RolePlanAssignmentView from "@/components/admin/RolePlanAssignmentView"`
and renders it at `:1349` for the `role-plans` tab, but **that file has never existed in any commit
or branch** — `git log --all -- 'frontend/src/components/admin/RolePlanAssignmentView*'` returns
nothing and `git ls-files` has no match. `vite build` fails outright with
`Could not load .../RolePlanAssignmentView: ENOENT`, so **no bundle is produced at all** — this is a
hard stop, not a runtime bug like the `GraduationCap` one.

Unblocked with a local placeholder component at the same path that renders a "not available in this
build" card. It is **not upstream**; delete it as soon as the real file is committed. The admin
`role-plans` tab therefore shows that notice instead of the role/plan assignment UI. Everything
else in the console is unaffected — the backing edge function (`admin-manage-users`, which gained
`ASSIGNMENT_ROLES` / `normalizeAssignmentFilters` / `pickAssignmentRole` in this release) is
deployed and waiting for the real view.

### Database

All **8 new migrations applied clean, zero failures**, in filename order. Pre-checks that mattered:

| Migration | Risk | Pre-check result |
|---|---|---|
| `20260812152243` | bare `CREATE TABLE topic_practice_progress` (no `IF NOT EXISTS`) | table absent → safe |
| `20260812160816` | new `plan_menu_catalog_role_check CHECK (role IN ('student','teacher','parent'))` | existing roles are exactly those three → safe |
| `20260813040037` | `ALTER TYPE app_role ADD VALUE 'parent'` inside a `DO` block | PG16 allows it in a transaction → applied |

Net: 210 → **217 tables**, 494 → **523 policies**, 35 functions. New: `topic_practice_progress`,
`student_curriculum_progress`, `assessment_assignments.due_at`, `parent_profiles.plan_override`,
`app_role.parent`.

**Re-ran `03_grants.sql` and `05_sensitive_columns.sql`** after the batch, as required. Note that
`03_grants.sql` is blanket and re-grants `anon SELECT` on every public table — including the six
curriculum master tables added on 2026-08-12, which must stay anon-free. They were re-revoked
immediately afterwards. **Any future migration batch must repeat that re-revoke.**

**Restart the pools after a migration batch.** The first admin sign-in straight after the batch
returned `Database error querying schema` even though `idle_session_timeout=0` is set on all four
service roles; the immediate retry succeeded. Stale pooled connections, same class of symptom as
the 2026-08-06 finding, different cause.

### Upstream re-opened permissive RLS — harmless here, dangerous on hosted

`20260812000000_fix_missing_columns_and_rpc_access.sql` adds five policies with unrestricted
`true` predicates and no `TO` clause, all **new in this release**: `Public can read/insert/update
student profiles` and `Anyone can insert/update progress`. The app's own
`security-regression-scan` edge function flags them (53 criticals total).

On our stack they are **not exploitable**, because grants — not policies — are the binding
constraint. Verified live with the anon key:

| Probe | Result |
|---|---|
| `GET student_profiles.password_hash` | **401** |
| `GET student_profiles.active_session_token` | **401** |
| `PATCH student_profiles` | **401** |
| `POST user_roles` (role escalation) | **401** |
| `GET boards / topics / questions` (masters) | **401** |

`anon` holds only *column-level* SELECT on `student_profiles` (19 columns, excluding the two
sensitive ones) — that is `05_sensitive_columns.sql` doing its job. On the hosted project, where
`anon` gets blanket table grants, those same policies would be wide open.

The other 6 criticals (`rls_disabled` on `user_roles`, `profiles`, `institutes`, `institute_users`,
`question_bank`, `student_progress`) are **pre-existing, not caused by this deploy** — confirmed by
diffing `ENABLE ROW LEVEL SECURITY` in the pre-deploy dump. `anon` has SELECT-only on all six, so
the exposure is read, not write; writes are refused.

### Verification

| Check | Result |
|---|---|
| Migrations | **8/8 clean** |
| Edge functions | 112 synced, **0 boot failures** (66×200, 28×400, 14×401, 2×403) |
| Bundle | no `*.supabase.co`, no `*.dev.pluginlive.com`, `/sb` base baked in |
| Routes (headless Chromium) | 5 anon + 3 authed, all render |
| Page errors / failed requests | **0 / 0** |
| Requests to hosted Supabase | **0** |
| `/sb` responses ≥ 400 | **0** |
| Admin login | works → `/dashboard`, console renders live data (33 students with names, boards, scores) |
| Student login (`student-authenticate-profile`) | `ok:true` for 9000000001 and 9000000003 |
| Curriculum masters | 24,000 questions / 30,450 videos / 5,075 topics intact, 0 FK orphans |

The snap `chromium` on both boxes refuses to launch from an ssh cgroup
(`is not a snap cgroup for tag snap.chromium.chromium`). Use playwright's own build at
`~/.cache/ms-playwright/chromium-1208/chrome-linux/chrome`. Harness:
`~/pilvidya-data-import/e2e.cjs` on the DEV box.

Rollback: `docker run` `eduspeakreact:predeploy-20260813T055338Z` on port 3008; the previous
container is still on the box, stopped, as `eduspeakreact-old-20260813T055338Z`.

## 2026-08-14 — Pilvidya redeployed to `84d5a78b`

Advanced Pilvidya UAT by 21 commits from `0f347d74` to `84d5a78b`. Upstream now includes the real
609-line `RolePlanAssignmentView`, so the temporary placeholder was retired. The three remaining
UAT patches (`vite.config.ts` allowed host, `public/schema.sql` self-hosted URLs, and the
`DashboardHub.tsx` local adjustment) reapplied cleanly.

Applied `20260813050000_security_hardening_school_scoped.sql` transactionally with one self-hosted
compatibility correction: PostgreSQL has no `min(uuid)`, so `MIN(sp.school_id)` was replaced in the
deployment copy by `(array_agg(sp.school_id ORDER BY sp.school_id))[1]`. Upstream was not edited.
The migration scopes student progress and transport access by user/school and restricts security-
definer helpers. Re-ran `03_grants.sql` and `05_sensitive_columns.sql`, then re-revoked anon access
to all six curriculum-master tables. The 61,080 imported master rows remain intact.

Synced the TTS, translation, question-generation and secret-management functions. Important
operational correction: a raw `rsync --delete` removed the stack-only `functions/main` dispatcher,
causing temporary 502s. It was restored from the predeploy functions snapshot and must be excluded
from future syncs, like Banking's sync script does. After restoration, recent function logs show
zero boot errors and `status-public-api` returns 200.

Verification: image `eduspeakreact:84d5a78b` built with route-manifest checks passing and is live;
both sites return 200; all Pilvidya stack containers are up. Browser E2E passed five anonymous
routes, admin login, and three authenticated routes with 0 page errors, 0 failed requests, 0
hosted Supabase requests, and 0 `/sb` responses >=400. Full DB backup:
`~/pilvidya-data-import/backups/eduspeak_uat_predeploy_20260814T044541Z.dump` on the DEV box.
Rollback image: `eduspeakreact:predeploy-20260814T044541Z`; prior container retained as
`eduspeakreact-old-20260814T044541Z`.

### 2026-08-14 — ElevenLabs primary + Gemini TTS fallback enabled

`ELEVENLABS_API_KEY`, `ELEVENLABS_PIL_API_KEY`, and `GEMINI_API_KEY` are set server-side in
`~/eduspeak-sb/functions-secrets.env` (mode tightened from `664` to `600`). The global
`public.app_secrets.GEMINI_API_KEY` row was also updated because Pilvidya resolves database secrets
before environment variables. The functions container was force-recreated after the changes.

Verified ElevenLabs directly (`audio/mpeg`, non-empty MP3) and Gemini directly through
`ai-coach-tts` with `provider: "gemini"` (`audio/wav`, non-empty audio). During validation an older
invalid Gemini key in `app_secrets` initially masked the valid environment value and caused a
silent fall-through to ElevenLabs; updating the database-level secret resolved it. Secret values
are not stored in this repo.

## 2026-08-17 — redeployed to `3cf91104`

Advanced Pilvidya UAT by 110 commits from `84d5a78b` to `3cf91104`, applying five new migrations
and syncing 115 edge functions. Image `eduspeakreact:3cf91104` built on the UAT box with
`--build-arg ENVIRONMENT=uat`; route-manifest check passed all five required routes. Prior
container retained as `eduspeakreact-old-20260817T083719Z`, rollback image
`eduspeakreact:rollback-20260817T083719Z`, DB dump and `.env.uat`/functions snapshot in
`~/pilvidya-predeploy-20260817T083719Z/`.

The three local patches (`vite.config.ts` `preview.allowedHosts`, the `DashboardHub` role-badge
guard, `public/schema.sql`) survived the pull; `vite.config.ts` auto-merged because upstream only
touched the PWA icon hunk. The stack-only `functions/main` dispatcher was again excluded from the
`rsync --delete`, per the 2026-08-14 lesson.

**Dumping this database needs `pluatadmin`, not `eduspeak_owner`.** All 217 public tables are owned
by `pluatadmin`, so `pg_dump` as `eduspeak_owner` fails at `LOCK TABLE ... IN ACCESS SHARE MODE`.

### A privilege gap between two of the new migrations broke student approval reads

`20260815033259` (security hardening) **replaces** `student_profiles`' table-level SELECT for
`authenticated` with a fixed column allow-list, to keep `password_hash` and session tokens out of
reach. `20260817031435` then adds five approval columns — and they were never added to that
allow-list. The result on this stack:

```
set role authenticated; select approval_status from public.student_profiles;
ERROR:  permission denied for table student_profiles     -- 42501
```

`teacher_profiles` is unaffected because it kept table-level SELECT, so its later approval columns
were covered automatically. The client cannot degrade around this: `isMissingStudentApprovalColumn`
in `StudentEntry.tsx` only recognises `42703`/`PGRST204` *missing column* errors, and a 42501
permission denial mentions neither the column nor a schema-cache miss — so the student entry flow
hard-errors instead of falling back. Fixed by granting SELECT on the five approval columns
(`approval_status`, `approval_requested_at`, `approved_at`, `approved_by_role`, `approval_note`) to
`authenticated`. Any future migration adding a `student_profiles` column must extend that grant.

### The other four migrations

`20260816053411` adds `assessments.due_at`, backfills `student_question_history.created_at` from
`answered_at` (61 rows), and adds two indexes — fully idempotent. `20260817031435` /
`20260817082618` add the student/teacher approval columns, defaulting existing rows to `approved`.
`20260816124641` **resets a real account's password** (`prakash.chinnadurai@gmail.com`) to a value
committed in plaintext upstream; it needs `pgcrypto` in the `extensions` schema, which this stack
has. That account exists here, so the reset took effect — it is the platform-admin login, and its
new password now matches what upstream publishes.

### Edge-function auth posture

The self-hosted `functions/main` dispatcher performs **no JWT verification**, unlike hosted
Supabase, where `verify_jwt` defaults to true. Sensitive functions guard themselves and were
confirmed to return 401 unauthenticated: `database-dump`, `admin-manage-users`,
`admin-dashboard-data`, `teacher-register`, `udise-plus-export`. `parent-dashboard` is also safe —
it uses its own `requireParentSession` token check rather than the JWT.

Seven LLM-backed generators have **no auth check at all** and are callable by anyone who can reach
the host: `curriculum-generate`, `iep-goal-suggest`, `lesson-plan-generate`, `mock-test`,
`rubric-generate`, `rubric-mastery-suggest`, `timetable-generate`. On hosted Supabase the platform's
default JWT gate covers them; self-hosted, that protection is simply absent. The exposure is LLM
spend rather than data. Not changed in this deploy — adding a dispatcher-level gate (as Banking has)
risks breaking the pre-session student/parent auth flows and should be done deliberately.

Verification: all Pilvidya containers up; `/sb/rest/v1` and `/sb/auth/v1/settings` 200; zero
function boot errors; both new functions (`teacher-register`, `student-question-history-record`)
load and return 401 unauthenticated. Admin login succeeds with the migration-set password, and
authenticated reads of `student_profiles.approval_status`, `teacher_profiles.approval_status` and
`assessments.due_at` all return 200 through PostgREST. `ai-coach-tts` returns a 495 KB ID3/MPEG
MP3 (ElevenLabs). Browser E2E passed `/`, `/student`, `/teacher`, `/admin`, `/status` with 0 page
errors, 0 hosted Supabase requests, and 0 `/sb` 4xx/5xx. The bundle's only `supabase.co` match is
the literal input placeholder `https://project.supabase.co` in `DatabaseConfigPanel.tsx`.

### 2026-08-17 (later) — redeployed to `94a80e32`

Advanced Pilvidya UAT by 8 commits from `3cf91104` to `94a80e32`. **No migrations in this
release** — it is a frontend change plus one new edge function, so this was a function sync and a
frontend rebuild only. Image `eduspeakreact:94a80e32` built on the UAT box with
`--build-arg ENVIRONMENT=uat`; route-manifest check passed all five required routes. Rollback image
`eduspeakreact:rollback-20260817T110924Z`, prior container retained as
`eduspeakreact-old-20260817T110924Z`, DB dump and `.env.uat`/functions snapshot in
`~/pilvidya-predeploy-20260817T110924Z/`.

The release adds bulk student upload: `AdminStudentBulkUpload` at `/admin/students/bulk`,
`AdminBulkStudentUploadView`, a reworked `TeacherPortal`, and the edge function
`teacher-bulk-upload-students` (116 functions now deployed). The three local patches survived the
pull unchanged and the stack-only `functions/main` dispatcher was again excluded from the
`rsync --delete`.

`teacher-bulk-upload-students` is **not** affected by the `student_profiles` column allow-list
documented above: it requires an `Authorization` header, verifies the caller holds the `teacher`
role via `user_roles`, then performs every `student_profiles` read and insert through a
`service_role` client, which bypasses RLS and column privileges. It inserts `display_name`,
`mobile_number`, `class_level`, `school_name`, `location`, `board` and `school_id` only — note it
sets **no `password_hash`**, so bulk-uploaded students cannot sign in through
`student-authenticate-profile` until a password is set separately. `approval_status` falls to its
`approved` default.

Verification: unauthenticated call returns 401 `Missing Authorization header`; authenticated as
`teacher@pilvidya.in`, an empty roster returns 400 and a malformed row returns
`{"inserted":0,"duplicates":0,"invalid":1}`, so validation and the dedupe path work without writing
test rows — `student_profiles` still holds 37 rows. All Pilvidya containers up, zero function boot
errors, `/sb/rest/v1` and `/sb/auth/v1/settings` 200, and the 2026-08-17 approval-column grant
still resolves. Browser E2E passed `/`, `/student`, `/teacher`, `/admin`, `/status` and the new
`/admin/students/bulk` with 0 page errors, 0 hosted Supabase requests, and 0 `/sb` 4xx/5xx.
