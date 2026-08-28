---
type: reference
tags: [service, frontend, uat, supabase, lovable]
---

# Banking Job Readiness (Candidate Job Readiness Journey)

**Repo:** `PluginLive-Technologies/bankingjobreadiness`, branch `main`
**UAT path:** `/home/ubuntu/bankingjobreadiness` (on the UAT box, directly under `~/`)
**Live URL:** `https://banking.uat.pluginlive.com/`
**Stack:** Vite + React + shadcn/ui SPA — not part of the PluginLive Node/Prisma stack.

> **UAT moved off hosted Supabase on 2026-08-07.** UAT now talks to a self-hosted
> Supabase-compatible stack on the same box (`~/banking-sb/`, proxied at
> `https://banking.uat.pluginlive.com/sb`) backed by our own PostgreSQL. The browser still speaks
> `supabase-js`; only the origin changed. **PROD is still on hosted project
> `kbwjokmmzkgjwiqelrdc`.** See `Infrastructure/banking-postgres-migration.md` — read it before
> touching UAT `.env`, migrations or edge functions.

## Why it's off the standard deploy path

This app (and its sibling `ailearning.uat.pluginlive.com`) came in as a Lovable-generated SPA cloned straight into the UAT box's home directory, not under `~/frontend/`. It is **not managed by `auto_deploy.sh`** — deploys are manual.

## Deploying (frontend)

```bash
cd ~/bankingjobreadiness
cp -a dist ../bankingjobreadiness-dist-backup-$(date +%Y%m%d-%H%M%S)   # nginx serves dist/ live; keep a rollback
git pull origin main   # if package-lock.json is dirty from a prior install, `git checkout -- package-lock.json` first
nvm use 20 && npm install && npm run build
```

### Deploy log

| Date | Commit | Migration applied | Notes |
|---|---|---|---|
| 2026-08-09 | `6c0429b` | `20260808045623` (as idempotent fixup) | 41 commits; date-fns repin removed the need for `--legacy-peer-deps` |
| 2026-08-10 | `8877a68` | `20260810100000_admin_subscription_rbac_menu_access` | 18 commits; adds **Subscriptions & Access** and **RBAC & Reports** to the admin nav; edge functions 81 → 82 (`request-password-reset`) |
| 2026-08-12 | `bade695` | **none** | 9 commits; multilingual AI coach; edge functions 82 → 83 (`elevenlabs-tts`). Ships **three upstream defects** — see *Upstream defects in the 2026-08-12 release*. One needed a local patch to avoid data loss. |
| 2026-08-24 | `6815d28` | `20260824183000_interview_proctoring_lifecycle` (additive, no fixup) | 6 commits; admin password reset across roles, auth-lock re-entry, assessment question dedup, interview proctoring lifecycle. `interview_sessions` 19 → 48 columns. Unit suite 291/301 → **335/335**. |
| 2026-08-25 | `423fd65` | `20260824220000_assessment_question_canonical_uniqueness` (0 rows deleted, no fixup) | 9 commits; raises `LLM_PROVIDER_TIMEOUT_MS` 15000 → 45000 and widens provider failover to 400/404/422 (fixes generation timeouts), adds a DB-level unique index rejecting duplicate prompts per assessment, fixes a detached-ArrayBuffer bug in Gemini TTS. Unit suite 340/341 (1 stale test literal, not a regression — see below). |
| 2026-08-27 | `5b4b5f2` | none (161 migrations unchanged, no new files) | 7 commits (`423fd65`→`5b4b5f2`); fixes taxonomy 400 errors, bulk-created-candidate OTP compatibility (`bulk-create-users` now writes `Otp_<mobile>_1234`, matching the login policy fix from 2026-08-21). No `supabase/migrations` or fixed-up edge function touched. Unit suite 348/349 (same stale `LLM_PROVIDER_TIMEOUT_MS = 15000` literal from 2026-08-25, still not a regression). |

`20260810100000` needed **no fixup** — it is `ALTER COLUMN … SET DEFAULT` plus a distinct-union
`UPDATE`, so it is naturally idempotent. Effect on UAT: per-admin `allowed_tabs` went 56 → 58 and
15 → 54 rows, and every row now carries `subscriptions`, `rbac-reports` and
`admin-journey-payment-verification`.

**On UAT, the frontend build is only step 3 of 4.** Since the self-hosted move, a pull that brings
new migrations or edge functions needs those applied too, or the new UI calls tables/functions that
do not exist yet:

```bash
# 1. preserve the self-hosted patches across the pull. As of 2026-08-12 there are FOUR files,
#    not two -- see "Local patches carried on the UAT checkout" below. `git stash push` with an
#    incomplete list silently drops the omitted patch on the next pull.
git stash push -- .env src/lib/adminErrorLogger.ts \
  src/components/pil-admin/LearningPathsManager.tsx src/hooks/useLearningPaths.ts \
  && git merge --ff-only origin/main && git stash pop
# 2. any NEW migration -> add an idempotent copy in ~/banking-sb/fixups/ and apply just that file,
#    then re-run sql/03_grants.sql and SIGUSR1 banking-sb-rest to reload PostgREST's schema cache.
#    Do NOT re-run the whole replay: it would re-execute data backfills against real data.
# 3. ~/banking-sb/sync-functions.sh          # edge functions + fixup overlay
# 4. npm install && npx vite build           # frontend
```

If that `git pull` 403s, the org GitHub token has expired — see `Infrastructure/github-access.md` (the checkout's `origin` URL carries its own token, so the credential store alone is not enough).

### Local patches carried on the UAT checkout

These live **only** on the UAT box as uncommitted working-tree changes. `git status` is the
inventory; every one is marked with a comment naming the reason.

| File | Why | Drop when |
|---|---|---|
| `.env` | self-hosted backend URL + locally-signed keys | never (UAT-specific) |
| `src/lib/adminErrorLogger.ts` | hardcoded hosted URL broke the fetch-interceptor matchers | upstream derives it from env |
| `src/components/pil-admin/LearningPathsManager.tsx` | upstream `2e0fdfb` deletes the learning path on save | upstream fixes the remap |
| `src/hooks/useLearningPaths.ts` | same remap, read side | upstream fixes the remap |

`package-lock.json` also shows modified after an install; that one is disposable
(`git checkout -- package-lock.json`).

### `ELEVENLABS_API_KEY` — SET on UAT since 2026-08-12; AI coach speaks in real voices

`~/banking-sb/functions-secrets.env` (mode `600`) now holds `ELEVENLABS_API_KEY`. It is the **first
and only** third-party secret populated on this stack; the other 13 are still absent.

**`env_file` is read at container create, so `docker restart` does NOT pick up a new secret.** Use:

```bash
cd ~/banking-sb && docker compose up -d functions   # recreates the container
docker exec banking-sb-functions sh -c 'echo $ELEVENLABS_API_KEY' | cut -c1-7   # verify, masked
```

Verified end to end with the exact payload `ttsClient.ts` sends
(`{text, language: lang.code, voiceId: lang.voiceId}`): **15/15 languages return real MP3**
(`ID3` header, ~30–50 KB for a short line, 225 KB for a paragraph), each with its own voice from
`src/lib/indianLanguages.ts`. Every voice id in that file is valid on this account. Distinct
sha256 per request — no caching artefacts.

No frontend rebuild is needed for this: the key is server-side only.

**Cost note:** ElevenLabs bills per character, so every spoken AI-coach reply now draws credits.
Before this key existed the function returned `503 {"error": "ElevenLabs is not connected to this
project"}` and `ttsClient.ts` fell back to `window.speechSynthesis` — that fallback is still the
behaviour if the key is removed or the account runs out of credits, so the feature fails soft.

- nginx (`/etc/nginx/sites-enabled/banking-react.conf`) serves `dist/` as static files directly — no service/container restart needed, nginx picks up the new build immediately. Because there is no container swap, a failed build leaves a **half-updated live site** — back `dist/` up before building.
- `.env` holds the backend URL + anon key; `VITE_*` vars are baked in at build time. **On UAT these
  now point at `https://banking.uat.pluginlive.com/sb` and the keys are signed with the self-hosted
  stack's `JWT_SECRET`, not the hosted project's** — the two sets are not interchangeable.

### `--legacy-peer-deps` — NO LONGER NEEDED (as of 2026-08-09)

Upstream repinned `date-fns` from `^4.4.0` to `3.6.0`, which satisfies
`react-day-picker@8.10.1`'s `^2||^3` peer range. Plain `npm install` now succeeds; verified on the
UAT box at commit `6c0429b`. Keep the note below for context on older checkouts.

### (historical) `--legacy-peer-deps` was mandatory (2026-08-04 → 2026-08-09)

Plain `npm install` **and** `npm ci` both fail with `ERESOLVE`: `react-day-picker@8.10.1` declares `peer date-fns@"^2.28.0 || ^3.0.0"` but the repo pins `date-fns@4.4.0`. This is stale peer metadata in `react-day-picker`, not a real incompatibility. Use `npm ci --legacy-peer-deps` — `ci` keeps the install lockfile-exact, `--legacy-peer-deps` just skips the peer check.

### The repo now ships a tracked `.env.local` — check it before every build

As of the 2026-08-04 pull, `.env.local` and `.env.example` are **committed to the repo** (`.gitignore` has no env entries), left over from a Lovable/vly scaffold. `.env.local` contains dead Convex vars (`VITE_CONVEX_URL`, `CONVEX_DEPLOYMENT="dev:quaint-gecko-803"`) plus `VITE_VLY_APP_ID` / `VITE_VLY_MONITORING_URL`.

**Vite loads `.env.local` at higher priority than `.env`.** Today this is harmless because `.env.local` defines no `VITE_SUPABASE_*` keys, so the Supabase config in `.env` still wins — but it is a live landmine: if anyone ever commits a `VITE_SUPABASE_*` value into `.env.local`, it will **silently override the UAT `.env` and repoint the built bundle at another backend**, with no build error. Diff `.env.local` after every pull.

The app is still entirely Supabase — 229 source files reference Supabase, zero reference Convex, there is no `convex/` directory and no `convex` dependency. The Convex vars are dead weight, not a migration in progress.

### Verifying a build before you walk away

`dist/` is live the instant it's written, so verify in place:

```bash
# 1. Correct backend baked in, no stray envs
cd ~/bankingjobreadiness/dist
# On UAT since 2026-08-07 this must be EMPTY — any hit means a stale, pre-migration
# build that would send UAT traffic back to the hosted project.
grep -rhoE 'https://[a-z0-9]+\.supabase\.co' . | sort | uniq -c        # expect NONE on UAT
grep -rhoE 'https://banking\.uat\.pluginlive\.com/sb' . | sort -u      # expect this instead
grep -rhoE '([a-z0-9-]+\.convex\.(cloud|site)|[a-z-]+\.dev\.pluginlive\.com)' . | sort -u   # expect empty

# 2. Site actually renders (SPA — a 200 on index.html proves nothing)
curl -s https://banking.uat.pluginlive.com/ | grep -o 'assets/index-[A-Za-z0-9_-]*\.js'   # must match dist/index.html
```

Then headless-load the page (`playwright-core` lives in `~/browser-mcp/node_modules`, browser at `/usr/bin/chromium-browser`) and expect **no `pageerror`** and a non-empty `#root`.

A `localhost:9999` string in the bundle is expected — it comes from vendor code (`undici`'s mock-agent and the `supabase-js` UMD build), not app code.

**Expected-noise gotcha:** on load you will see three Supabase REST calls to `/rest/v1/{assessments,profiles,modules}` report `net::ERR_ABORTED` in devtools. They are **not** failures — each returns HTTP 200 first and is then aborted by the app's own `AbortController`/React StrictMode cleanup. Log the `response` event, not just `requestfailed`, before chasing these.

## Upstream defects in the 2026-08-12 release (`bade695`)

Three separate problems shipped in these 9 commits. All were found during the deploy; one was
patched locally, two are reported and left as upstream's call.

### 1. `2e0fdfb` "Fix database schema errors" DELETES learning paths — patched locally

The commit remapped `learning_path_assignments` → `learning_paths` in four places. Assignments are
a **different entity**, and one of those places is the edit-save path:

```js
// upstream, LearningPathsManager.tsx handleSave()
await supabase.from("learning_paths").update({...}).eq("id", pathId);   // update the path
await supabase.from("learning_path_modules").delete().eq("path_id", pathId);
await supabase.from("learning_paths").delete().eq("id", pathId);        // ...then DELETE it
```

Editing and saving any learning path deletes it. It fails **silently**: there is no FK from
`learning_path_modules`, and neither that call nor the follow-up assignment insert checks `.error`,
so the code reaches `toast.success("Learning path updated")` with the row already gone. 11 real
learning paths on UAT were exposed to this, one admin click each.

Reverted on the UAT checkout in `LearningPathsManager.tsx` (2 spots) and `useLearningPaths.ts`
(2 spots), each marked `LOCAL PATCH (2026-08-12)`. `learning_path_assignments` exists here with
exactly the columns the code inserts (`path_id, college, department, degree`). **Drop the patch
once upstream fixes it.**

### 2. The same commit points 4 admin queries at columns that do not exist

Also part of `2e0fdfb`, but read-only, so it was **left as shipped**. It remaps `rbac_*` → `admin_*`
and `quiz_question_bank` → `assessment_questions`, and **23 of the selected columns do not exist**
on the new tables. Every column the *old* code selected does exist on the *old* tables, so this is a
regression against this schema, not a fix:

| Frontend now queries | Result | What it replaced |
|---|---|---|
| `admin_tab_permissions(id, role_code, menu_key, menu_label, actions, scope)` | **400** | `rbac_role_permissions` — **142 rows** |
| `admin_tab_permissions(id, user_id, menu_key, action, effect, reason, created_at)` | **400** | `rbac_user_permission_exceptions` — 0 rows |
| `admin_audit_log(id, actor_name, action, entity_type, entity_id, reason, occurred_at)` | **400** | `rbac_audit_log` — 2 rows |
| `admin_audit_log(id, user_id, tenant_name, menu_key, …)` | **400** | `rbac_menu_access_log` — 0 rows |

`admin_tab_permissions` really has `(user_id, allowed_tabs, updated_by, updated_at, created_at, role)`;
`admin_audit_log` has `(id, actor_user_id, action, target_user_ids, details, created_at)`.

Visible effect: **Admin → RBAC & Reports → Permission Matrix renders empty** (the header counts come
from `profiles`/`user_roles`, which still work). `rowsOrEmpty()` swallows the error into `[]`, so
there is no crash and no toast — only a `console.warn` and a 400 in the nginx log. `QuestionBankViewer`
is hit the same way via the non-existent `assessment_questions.metadata`.

These four 400s are the **only** non-2xx `/sb/` responses in a full authenticated admin walkthrough.
Expect them until upstream fixes the mapping; don't chase them as a stack problem.

### 3. `bade695` "Update MCP function bundle" cannot run anywhere — pinned via fixup

Upstream replaced the 174-line inlined `supabase/functions/mcp/index.ts` with an 8-line stub whose
entry import is a **Windows absolute path** passed as an `npm:` specifier:

```ts
import mcp from "npm:C:\\Users\\Prakash\\OneDrive\\Documents\\Default Project\\bankingjobreadiness\\src\\lib\\mcp\\index.ts";
```

The Lovable Vite plugin regenerated it on a Windows dev machine and baked in that machine's local
path. Proof it cannot resolve on any other host:

```
$ docker exec banking-sb-functions edge-runtime bundle --entrypoint .../mcp/index.ts
Error: failed to create the graph
Caused by: npm package 'C:\Users\Prakash\...\index.ts' does not exist.
```

**But this file is a build artifact, not source.** `vite.config.ts` loads `mcpPlugin()` from
`@lovable.dev/mcp-js/stacks/supabase/vite`, which **regenerates
`supabase/functions/mcp/index.ts` on every `npm run build`** from `src/lib/mcp/index.ts`, baking
`projectRef` in from `VITE_SUPABASE_PROJECT_ID`. Two consequences:

* Our own build **overwrites** the Windows stub with a correct inlined bundle, so the committed
  breakage never reaches the stack — *provided you build before syncing functions*. The documented
  4-step order (functions at 3, frontend at 4) is backwards for this one file; run
  `sync-functions.sh` again after the build, or accept the fixup below as the thing that ships.
* That file showing as `modified` in `git status` after a build is **normal**, not a hand patch.
  Do not add it to the stash list.

`~/banking-sb/function-fixups/mcp/index.ts` pins a known-good bundle and wins over both versions.
Note the general hazard: `function-fixups/` entries are *whole files*, so a fixup that outlives its
reason silently reverts upstream work on the next `sync-functions.sh`. Diff each fixup against the
repo after a pull that touches it.

### `edge-runtime bundle` is the side-effect-free way to check all functions

Better than probing endpoints, which can fire real work (`seed-admin-user` resets the admin
password; MSG91/Twilio send real messages). `bundle` builds the full module graph without executing
anything, and it is what caught defect 3:

```bash
docker exec banking-sb-functions sh -c '
for d in /home/deno/functions/*/; do
  edge-runtime bundle --entrypoint "$d/index.ts" --output /tmp/b.eszip -q >/tmp/err 2>&1 \
    || { echo "FAIL: $(basename $d)"; tail -3 /tmp/err; }
done'
```
83/83 resolve as of 2026-08-12. Note `OPTIONS` is **not** a boot probe — the dispatcher
short-circuits it before spawning a worker.

## `mcp` is broken on the self-hosted stack (not fixable in the app)

Independent of the bundle regression above, the `mcp` function cannot serve on this stack.

`@lovable.dev/mcp-js` rejects a non-https `auth.issuer` at module init. The fixup derived it from
`Deno.env.get("SUPABASE_URL")`, which inside `banking-sb-functions` is the **internal** origin
`http://gateway:80` — so every call died with `500 function worker failed`
(`auth.issuer must use https://`). This had been broken since the migration; earlier "all functions
boot clean" checks did not catch it because a resolvable module graph is not a working function.

Repointed to the public origin (`SUPABASE_PUBLIC_URL`, defaulting to
`https://banking.uat.pluginlive.com/sb`). The worker crash is gone, but it now returns a clean
`500 {"error":"oauth configuration error"}`, because **self-hosted GoTrue serves no OAuth discovery
document** — both `/.well-known/oauth-authorization-server` and `/.well-known/openid-configuration`
404, and our GoTrue mints tokens with **no `iss` claim** at all (`GOTRUE_JWT_ISSUER` unset). Hosted
Supabase provides those endpoints; that is the gap.

Fixing it means serving a discovery document at that well-known path (e.g. a static JSON via nginx)
— a deliberate change, not a redeploy step. The app UI does not use `mcp`; nothing else is affected.

## Backend (Supabase) — separate deploy step, not covered by the frontend build

`supabase/functions/*` (Edge Functions, Deno) and `supabase/migrations/*` (SQL) live in the same repo but are **not** deployed by `npm run build`.

> **On UAT this is no longer a Supabase-CLI step.** Since 2026-08-07, functions deploy with
> `~/banking-sb/sync-functions.sh` (rsync + fixup overlay + restart the edge runtime), and all
> **119** migrations are applied to `banking_uat` via `~/banking-sb/replay-migrations.sh`. The
> drift described below is **resolved on UAT** and applies only to the hosted project, which still
> backs PROD. See `Infrastructure/banking-postgres-migration.md`.

**The frontend deploy and the Supabase deploy have drifted apart — treat the backend as a separate, explicit step.** As of 2026-08-04 the UAT checkout carries **81 edge functions and 118 migrations**. A fresh `npm run build` ships UI that calls tables and functions which do not exist in the Supabase project. If a newly-deployed screen 404s or errors on a `/functions/v1/...` call, this drift is the first thing to check — not the frontend build.

### Half the migrations have NEVER been applied — split by who authored them (verified 2026-08-04)

**Scope: the hosted project only (which now backs PROD). On UAT all 119 are applied.**

The 118 migrations fall into two groups, and **only one group is live on hosted**:

| Filename style | Author | Count | Applied to Supabase? |
|---|---|---|---|
| `<ts>_<uuid>.sql` (e.g. `20260727022209_774a0969-…`) | Lovable editor | 57 | **Yes** — Lovable applies these automatically when created |
| `<ts>_<description>.sql` (e.g. `20260728000000_module_prerequisites_…`) | hand-written by a developer | 61 | **No — never** |

Nobody has ever run `supabase db push` from this box, so every hand-written migration from **`20260630073000_llm_provider_configs.sql` (2026-06-30) through `20260801000000_interview_proctoring_settings.sql` (2026-08-01)** exists only in git. The date is *not* the discriminator — a Lovable migration from 2026-07-27 is live while a hand-written one from 2026-07-10 is not.

Verified by probing PostgREST with the anon key (a missing table returns `404 PGRST205`, an RLS-blocked one returns `200 []`) — 8/8 sampled hand-written tables missing, 6/6 sampled Lovable tables present:

```bash
KEY=$(grep '^VITE_SUPABASE_PUBLISHABLE_KEY=' ~/bankingjobreadiness/.env | cut -d= -f2- | tr -d '"')
curl -s "https://kbwjokmmzkgjwiqelrdc.supabase.co/rest/v1/<table>?select=*&limit=1" \
  -H "apikey: $KEY" -H "Authorization: Bearer $KEY"
```

Confirmed **missing**: `students`, `payment_requests`, `ai_practice_sessions`, `rbac_role_permissions`, `ai_coach_threads`, `module_group_assignments`, `admin_modules`, `module_prerequisites`, `module_live_sessions`, `live_session_rsvps`, `student_module_topic_progress`, `module_analytics`, `trainer_module_assignments`, and the column `interview_sessions.proctoring_settings` (`42703`).

Confirmed **present**: `agent_threads`, `domains`, `module_taxonomy_history`, `institutes`, `coding_submissions`, `module_trainers`, `assessments`, `profiles`, `modules`.

**Consequence:** any feature delivered by a hand-written migration — payments/journey access, admin RBAC entitlement reports, AI coach threads, tech AI-practice sessions, domain/module group visibility, module prerequisites, live sessions, trainer assignments, AI-interview proctoring settings — is **dead on UAT** no matter how many times the frontend is rebuilt. Applying them needs the Supabase CLI (not installed on the box) plus project credentials, and should be reviewed first: several are `resync`/`seed`/`backfill` scripts that mutate data, and `20260728150000_fix_security_vulnerabilities.sql` changes RLS.

**Resolved:** the `bulk-create-users` "Not authorized" bug (service-role client calling `rpc("has_role")`, which lives in the locked-down `private` schema and is executable only by `authenticated`) was previously carried as an uncommitted local patch on the UAT box. It has since **landed upstream** — `supabase/functions/bulk-create-users/index.ts` now authenticates the caller with an anon-key client and reads `user_roles` directly via the service-role client, matching `admin-confirm-candidates` / `bulk-export-enqueue` / `assessment-report`. No local patch to preserve across pulls anymore. It still needs to be *deployed* to Supabase per the drift note above.

## 2026-08-20 — redeployed to `4a67e19`

Advanced Banking UAT by 14 commits from `6119771` to `4a67e19`. Applied the one new migration,
`20260821000000_assessments_schema_cache_repair.sql`, which preserves the existing
`assessments.assigned_colleges` default and requests a PostgREST schema reload. PostgREST was then
fully restarted, the changed `generate-assessment-questions` edge function was synced, and the
frontend rebuilt with the self-hosted `/sb` configuration.

Verification: site and both REST/Auth API roots return 200; unauthenticated `seed-admin-user`
returns 401; all Banking stack containers are up; function logs contain no new boot/worker errors;
browser E2E passed landing, admin login, protected modules, and the authenticated admin console
with zero page errors, hosted-Supabase requests, or API errors. Snapshot:
`~/banking-predeploy-20260820T092104Z/`.

## 2026-08-20 (second run) — redeployed to `a79370c`

Advanced Banking UAT by 4 commits from `4a67e19` to `a79370c` (`6c46066` Sync remote mcp index
changes, `b5a3e13` Work in progress, `06213f7` Changes, `a79370c` Removed stale vite config file).
Clean fast-forward, **no new migrations**, so this was a function sync plus a frontend rebuild.

### The release is a near no-op, and its one real change is a type regression

The four commits look substantial per-commit (±171 lines in `supabase/functions/mcp/index.ts`, a
stray `vite.config.ts.timestamp-*.mjs` added then deleted), but they add and revert each other.
The **net** `git diff 4a67e19..a79370c` is three deleted lines in
`src/integrations/supabase/types.ts`: `assigned_colleges: string[]` removed from the `assessments`
`Row`/`Insert`/`Update` types.

That removal is wrong, and it directly contradicts the migration applied the day before:

* `banking_uat.public.assessments.assigned_colleges` **exists**, `ARRAY`, default `'{}'::text[]`
  — put there by `20260821000000_assessments_schema_cache_repair.sql`.
* PostgREST serves the column fine (`/rest/v1/assessments?select=id,title,assigned_colleges` → 200
  with `"assigned_colleges":[]`).
* The app reads and writes it in four places — `useAssessments.ts`, `AssessmentCreator.tsx`
  (`assigned_colleges: assignedColleges` on save) and `StudentAssessmentTaker.tsx`
  (`a.assigned_colleges.length === 0 || a.assigned_colleges.includes(studentCollege)`, i.e. the
  college-scoping rule for which assessments a student may see).

**It is inert for the deployed bundle** only because `npm run build` is plain `vite build` with no
`tsc` step — Vite strips types without checking them. So the shipped JS is unchanged. The cost is
that the generated types now lie about the schema: anyone running `tsc`, relying on IDE
type-checking, or regenerating from these types will be told a live column does not exist. If a
typecheck is ever added to the build, this breaks it. Fix belongs upstream (regenerate types
against the current DB), not on the box.

### Local patches on the UAT checkout survived the pull — re-verify after every deploy

The UAT checkout carries four **uncommitted** local patches. The pull was done as
`git stash push -- src/ supabase/ package-lock.json` → `git merge --ff-only origin/main` →
`git stash pop`, which kept all four:

| File | Patch |
|---|---|
| `src/components/pil-admin/LearningPathsManager.tsx` | edit-save deletes `learning_path_assignments`, **not** `learning_paths` |
| `src/hooks/useLearningPaths.ts` | assignments read points at `learning_path_assignments` |
| `src/lib/adminErrorLogger.ts` | `SUPABASE_URL` from `import.meta.env.VITE_SUPABASE_URL`, not the hosted project |
| `supabase/functions/mcp/index.ts` | `projectRef = "banking-uat-selfhosted"` |

**Upstream still has not fixed the learning-path data-loss bug** (`2e0fdfb`), so the patch is still
load-bearing: without it, editing and saving any learning path deletes it while the UI reports
success. Verified in the *built bundle*, not just the source — the only
`from("learning_paths").delete()` in `dist/` is the explicit "Learning path deleted" button; the
edit-save path emits `from("learning_path_modules").delete()...from("learning_path_assignments").delete()`.
`learning_paths` still holds its 11 rows.

### Verification

Site 200; `/sb/rest/v1`, `/sb/auth/v1/settings`, `/sb/storage/v1/bucket` all 200; unauthenticated
`seed-admin-user` → 401; 83 edge functions synced with 3 fixups (`live-session-rsvp`, `main`,
`mcp`), dispatcher intact, zero boot errors; all 7 stack containers up.

* **AI coach** — 200, first byte **51 ms**, streamed SSE chunks from real `gemini-2.5-flash`
  (not the built-in fallback). Both earlier fixes still hold: the `llm_provider_configs` gemini key
  and `proxy_buffering off` in nginx.
* **TTS** — 200, `provider: elevenlabs`, `mimeType: audio/mpeg`, 28,465 bytes of real MP3 (`ID3`).
* **Payments RPC** — `submit_payment_request` resolves in the PostgREST schema cache and its
  ownership check fires (`42501 Not allowed to submit payment for this student` for a bogus
  student). `payment_requests` still 0 rows — the probe wrote nothing.
* **Browser E2E** — 6 anonymous routes and the authenticated admin console (User Management,
  Institutes, Subscriptions): **0 page errors, 0 hosted `*.supabase.co` requests, 0 `/sb` 4xx/5xx**.
* **Unit tests** — 291 passed / 10 failed (301). Identical at the previous commit `4a67e19`
  (run in a throwaway worktree), so this release adds **no** test regressions.
* **Data** — 121 public tables, 62 profiles, 62 auth users, 13 assessments, 11 learning paths.

Backups: `~/banking-sb/banking_uat_predeploy_20260820T113939Z.dump`,
`~/banking-sb/functions-predeploy-20260820T113939Z.tar.gz`,
`~/bankingjobreadiness/dist.bak-predeploy-20260820T113939Z/`, `.env.bak-predeploy-20260820T113939Z`.

## 2026-08-21 — candidate OTP login policy fix (`2a2a477`)

Candidate `9820065335` appeared correctly in the admin candidate list but candidate login returned
"Account not found". The data was not missing: `profiles.user_id` matched the confirmed
`auth.users.id`, the profile was active/approved, and the auth email was the expected
`9820065335@bankready.app`.

The actual defect was the demo OTP password contract in `Login.tsx`. It generated
`otp_<mobile>_1234`, while self-hosted GoTrue requires at least one lowercase letter, uppercase
letter and digit. GoTrue rejected that value as `weak_password`, and existing imported identities
could not authenticate with the password the UI always submitted. Changed the internal derived
password to policy-compliant `Otp_<mobile>_1234`; the visible OTP remains `1234`.

Reset only `9820065335@bankready.app` through GoTrue's admin API using
`set-user-password.sh`, rebuilt the frontend, and pushed the source fix. Verification: the exact
password-grant request now returns HTTP 200 with the expected user UUID and an access token; the
served bundle contains the new contract; the linked profile remains active and approved. Rollback
frontend copy: `~/bankingjobreadiness-dist-backup-loginfix-20260821T*`.

Follow-up browser verification used a fresh Chromium context against `/login/candidate`: mobile
`9820065335` + visible OTP `1234` submitted the new `Otp_` credential, authenticated successfully,
redirected to `/candidate/home`, and rendered the student console. An already-open tab from before
the build continued executing the old in-memory JavaScript and produced one more 400 until reloaded;
GoTrue logs distinguished that stale-client attempt from the fresh successful flow.

## 2026-08-21 — redeployed to `251f18a`

Advanced two commits from `2a2a477` (one feature commit plus its merge). Applied the one new
migration, `20260822000000_module_group_id_columns.sql`, transactionally as `banking_owner`; no
self-hosted fixup was needed. It adds nullable `module_group_id uuid` foreign keys to both `modules`
and `admin_modules`, referencing `module_groups(id) ON DELETE SET NULL`, plus indexes on both
columns. Existing data was unchanged: `modules` has 51 rows and `admin_modules` has 65, with zero
mapped values until admins begin assigning groups.

Reapplied grants, fully restarted PostgREST, rebuilt the frontend with the UAT environment, then
resynced all 83 edge functions with the three standing fixups. Verification: site and auth settings
200; both new columns return 200 through PostgREST; both foreign keys and indexes exist; all seven
containers are up and the database is healthy; zero new function boot errors; no hosted Supabase
data-plane URL in the bundle. A fresh Chromium candidate login for `9820065335` using OTP `1234`
successfully redirected to `/candidate/home` and rendered the student console.

Rollback assets use stamp `20260821T071010Z`: database dump and functions archive under
`~/banking-sb/`, frontend copy at `~/bankingjobreadiness-dist-backup-20260821T071010Z`, and the
checkout-local `.env` backup in `~/bankingjobreadiness/`.

## 2026-08-21 (third run) — redeployed to `5add773`

Advanced two frontend-only commits from `251f18a`: improved password-recovery session/error
handling and added missing dialog descriptions to admin domains, module groups, RBAC and admin
dialogs. There were no new migrations and no edge-function source changes, so no database work was
required. Preserved all four standing UAT source patches and the self-hosted `.env`, rebuilt the
frontend, then resynced the generated MCP bundle and the three function fixups.

Verification: new `index-UREdX1mg.js` asset is served; site and auth settings 200; all seven stack
containers up with the database healthy; zero function boot errors; no hosted Supabase data-plane
URL in the bundle. Fresh Chromium loads of `/reset-password` and `/login/candidate` had zero page
errors and zero `/sb` API errors. Candidate `9820065335` with OTP `1234` still authenticates and
lands on `/candidate/home`. Frontend and `.env` rollback copies use stamp `20260821T110647Z`.

## 2026-08-21 (fourth run) — deployed `f56a5d5`, repaired to `e44a897`

The incoming commit changed `ai-assessment` to use the shared multi-provider LLM path and added a
deterministic fallback; there was no migration. It also committed the recurring invalid Windows-path
MCP artifact. The build regenerated MCP and the standing UAT fixup overlaid it, so that artifact was
not deployed.

An authenticated live generation probe found two independent upstream API-contract defects that a
static bundle check did not catch: `fallbackJsonForFeature` existed in `_shared/llm.ts` but was not
exported, causing a worker boot error; after exporting it, both call sites destructured a nonexistent
`response` property even though `callLlmChatCompletion` returns `Response` directly. Fixed and pushed
as `b502309` and `e44a897`, then resynced all 83 functions with three fixups.

Final verification: an authenticated `ai-assessment` generation request returns HTTP 200 with one
MCQ and no error; site and auth settings 200; all seven containers up with the database healthy;
clean post-fix function logs; deployed MCP has no Windows path; candidate `9820065335` still logs in
with OTP `1234` and reaches `/candidate/home`. No database migration was required. Rollback assets
use stamp `20260821T153931Z`: function archive under `~/banking-sb/`, frontend and `.env` copies in
the usual Banking paths.

### Probing the stack with a minted JWT — the `session_id` trap

To test authenticated paths without touching anyone's password, mint an HS256 token with the stack
`JWT_SECRET` (claims: `sub`, `aud`/`role` = `authenticated`, `email`, `iat`, `exp`).

**Do not add a `session_id` claim.** GoTrue validates it against `auth.sessions`, so an invented one
makes `/auth/v1/user` return **403**; supabase-js then tries to refresh, fails, and every following
request 401s. That produces a browser run full of `/sb` 4xx that look like a broken deploy but are
purely an artefact of the probe. Confirmed by running both tokens side by side: with `session_id`,
`/auth/v1/user` → 403; without it, `/auth/v1/user`, `/rest/v1/institute_subscriptions` and
`/functions/v1/admin-candidate-auth-status` all → 200.

Two more gotchas when probing:

* `ai-personal-coach` takes `{studentId, messages:[{role,content}]}` — `message` is rejected, and
  `studentId` must be the **auth user id** or a `students.id` the caller owns; `profiles.id` is a
  different key (`profiles.user_id` is the auth link) and yields `403 Student does not belong…`.
* The stack database is **`banking_uat`**, not `postgres`. `psql -U postgres` with no `-d` lands in
  an empty database and reports 0 public tables — not a wiped stack.

## 2026-08-24 — redeployed to `63d9eb3` (13 commits, 2 migrations)

Advanced Banking UAT from `c8a66c9` to `63d9eb3`. The five standing UAT source patches were stashed
across the pull and restored intact (two `LOCAL PATCH` blocks each in `LearningPathsManager.tsx` and
`useLearningPaths.ts`, the `import.meta.env` derivation in `adminErrorLogger.ts`, the
`banking-uat-selfhosted` MCP project ref, and the self-hosted `.env`). None of the 13 incoming
commits touched a patched file, so the pull was conflict-free.

### Both migrations were partially pre-applied — replay was still required

`20260823105238` creates `student_module_progress`, `student_assessment_scores` and
`proctoring_defaults`. **All three tables already existed** and held live data (123 / 18 / 1 rows),
so every `CREATE TABLE IF NOT EXISTS` was skipped. What the file did add was a **second, wider set of
RLS policies** on tables that already had narrower ones. Postgres OR-combines permissive policies, so
on `student_module_progress` the pre-existing `student_module_progress owner write` policy is now
superseded by the migration's `FOR ALL TO authenticated USING (true) WITH CHECK (true)` — **any
authenticated user can now write any student's progress row**. This is the same widening pattern
already recorded for `public.students`; it is upstream's shipped migration, applied as-is.

`20260824015329` adds `provider_key` to `llm_provider_configs` and keeps it in sync with `provider`.
The **column already existed** but the trigger, the unique index and the `provider` `DROP NOT NULL`
did not — the file was genuinely half-applied. Replaying it completed the other three steps. Checked
for duplicate `(provider_key, application_feature)` pairs first; there were none, so the unique index
built cleanly. Both files replayed under `--single-transaction -v ON_ERROR_STOP=1` with no errors.

PostgREST was **fully restarted** (not `HUP` — see the 2026-08-18 note). Logs confirm the reload:
128 Relations, 52 Relationships, 32 Functions. All four affected tables and the `provider_key`
column return 200 through `/sb/rest/v1`.

### Candidate `9820065335` was locked out again — by a deliberate password change, not a regression

The OTP login broke again between deploys. The auth row was intact (confirmed, `role=authenticated`,
not banned), but `extensions.crypt()` proved the stored bcrypt hash **did not match** the derived
`Otp_<mobile>_1234`, and `updated_at` was `2026-08-23 10:49:58` — **58 seconds after a successful
login at 10:49:00**. `recovery_sent_at` is NULL, so this was not the forgot-password flow: it was
`PasswordChangeForm.tsx` (`supabase.auth.updateUser({password})`) from inside the candidate
dashboard.

**This is a product defect, not a deploy problem.** The candidate login screen is **OTP-only** — it
derives the password from the mobile number and has no password field — yet the candidate dashboard
ships a change-password form. Any candidate who uses it permanently locks themselves out of the only
candidate login path. `ResetPassword.tsx` and the candidate "Forgot Password?" link have the same
end state. Either remove the candidate change-password affordance or give the candidate tab a real
password field.

The credential was restored with `~/banking-sb/set-user-password.sh 9820065335 'Otp_9820065335_1234'`.
Note this **overwrites whatever password the account holder set on 08-23**; that profile is
`Prakash Chinnadurai`, `role=admin`, so if that password was deliberate for the Admin tab it must be
set again.

Scope check across all 46 `@bankready.app` users: **51 auth users have no password at all**
(the imported-CSV accounts described under `set-user-password.sh`), and 10 have a password that is
not the derived OTP one. Only `9820065335` was repaired.

### Verification

Site 200 (89 ms); `/sb/rest/v1` and `/sb/auth/v1/settings` 200; `student_module_progress`,
`student_assessment_scores`, `proctoring_defaults`, `llm_provider_configs` and the new `provider_key`
column all 200; 83 functions synced with the three standing fixups; zero function boot errors; all
seven stack containers up with the database healthy. The bundle contains **no hosted
`*.supabase.co` data-plane URL** and 19 self-hosted `/sb` references. The deployed `mcp` bundle has
no Windows path. `ai-personal-coach` streams SSE from a real `gemini-2.5-flash` (200, TTFB 50 ms);
`elevenlabs-tts` returns 200 with a 39 KB base64 MP3 (`ID3`). Candidate `9820065335` with OTP `1234`
returns a 200 token and reads its profile 200. A Chromium load of `/login/candidate` rendered the
full candidate tab with no page errors.

Rollback assets use stamp `20260824T035130Z`: `~/banking-db-20260824T035130Z.sql.gz`,
`~/banking-functions-20260824T035130Z.tar.gz`, `~/banking-localpatches-20260824T035130Z.patch`,
`~/bankingjobreadiness-dist-backup-20260824T035130Z`, and the checkout-local
`.env.bak-predeploy-20260824T035130Z`.

## 2026-08-24 (second run) — redeployed to `2492621` (3 commits, 1 migration)

Advanced from `63d9eb3`: `0755fd7` fixes the domain/tech assessment lifecycle, `8effba9` adds an
end-to-end curriculum assessment journey test, `2492621` tightens that test's types. None of the
three touched a locally patched file, so the stash/pull/pop cycle was clean and all five standing
UAT patches were verified back in place afterwards.

### The migration is destructive — pre-count it before applying

`20260824143000_assessment_lifecycle_integrity.sql` starts with a **`DELETE`** of duplicate
`assessment_questions` rows (same `assessment_id`, same case-folded/trimmed prompt, higher `id`),
then adds a partial unique index on `(assessment_id, md5(lower(btrim(prompt))))`, a
`sync_assessment_question_totals()` function plus an AFTER INSERT/UPDATE/DELETE trigger, and finally
backfills totals for every assessment.

**`assessment_responses.question_id` has `ON DELETE CASCADE`**, so that opening `DELETE` can silently
take student answers with it. Always quantify first:

```sql
-- rows the DELETE will remove, and the responses that would cascade
select count(*) from public.assessment_questions d
join public.assessment_questions r
  on d.assessment_id = r.assessment_id and d.id > r.id
 and lower(btrim(coalesce(nullif(d.question,''), d.question_text,''))) =
     lower(btrim(coalesce(nullif(r.question,''), r.question_text,'')))
where btrim(coalesce(nullif(d.question,''), d.question_text,'')) <> '';
```

Here it was **5 rows across 1 assessment** ("Banking Domain Readiness Assessment", 10 → 5 questions)
with **0 attached responses**, so nothing cascaded. Applied under `--single-transaction -v
ON_ERROR_STOP=1`: `DELETE 5`, index and both functions created, trigger created, backfill ran.
`assessment_questions` 734 → 729; `assessment_responses` unchanged at 11241. PostgREST reloaded to
128 Relations / 52 Relationships / **33** Functions (was 32 — the new `sync_assessment_question_totals`).

The `assessments` table has no `coding_count` column; the migration only uses `coding_count` as a
local record field inside `question_mix`, so it does not fail. Verified before applying.

### Verification

Site 200 (53 ms), REST and auth settings 200; served bundle `index-BQ1ZYkOP.js` matches the freshly
built `dist`; no hosted `*.supabase.co` in the bundle, 19 self-hosted `/sb` refs; 83 functions synced
with the three fixups; deployed `mcp` has no Windows path; zero function boot errors; all seven
containers up with the database healthy.

Both edge functions changed by this release were probed live, since a previous release shipped
runtime defects that only a live call caught. `generate-assessment-questions` and
`grade-assessment-attempt` both return 401 unauthenticated and validate correctly when authenticated.
A real generation call (`{topic_or_skills, track, difficulty, mix:{mcq:1,…}}` — note it is `mix` and
`topic_or_skills`, not `questionMix`/`topic`) returned **HTTP 200 in 2.7 s with a valid MCQ**, and
`assessment_questions` stayed at 729, confirming the probe does not persist.

**Full browser login run, not just a token check:** filled `9820065335`, Send OTP, `1234`, Verify →
landed on `/candidate/home` with the whole student console rendered and **zero page errors**; the
`/assessments` page then listed all 64 assessments with the migration's resynced counts
(e.g. the deduped assessment now correctly reads "5 questions 5 marks 5 MCQ"). API-level: correct OTP
200, wrong OTP 400, unknown mobile 400.

One pre-existing data oddity the totals backfill made visible: **"Axis Securities Assessment" shows
0 questions / 0 marks yet still renders a Start Assessment button.** Not caused by this release —
the assessment genuinely has no questions — but it is now plainly wrong in the UI.

Rollback assets use stamp `20260824T084231Z`: `~/banking-db-20260824T084231Z.sql.gz` (taken *before*
the destructive migration), `~/banking-functions-20260824T084231Z.tar.gz`,
`~/banking-localpatches-20260824T084231Z.patch`,
`~/bankingjobreadiness-dist-backup-20260824T084231Z`, and `.env.bak-predeploy-20260824T084231Z`.

---

## 2026-08-24 (third run) — redeployed to `6815d28` (6 commits, 1 migration)

`2492621` → `6815d28`: `e4bd2c8` + `6815d28` fix admin password reset across account roles,
`2044488` fixes Supabase auth-lock re-entry, `5e36e1a` fixes duplicate assessment question
generation, `11ccdb0` adds the interview proctoring lifecycle, `ead7b42` reformats the practice
plan widget. 28 files, +1060/−218.

All five local patches (`.env`, `LearningPathsManager.tsx`, `useLearningPaths.ts`,
`adminErrorLogger.ts`, `functions/mcp/index.ts`) survived the pull untouched — none of the six
commits touches those files, so no stash dance was needed.

### Migration `20260824183000_interview_proctoring_lifecycle.sql`

Purely additive and already idempotent (`add column if not exists` ×30, `create index if not
exists` ×2, then `notify pgrst`). **No fixup needed.** `public.interview_sessions` went
**19 → 48 columns** (one of the 30 already existed), both indexes created, all 3 rows preserved.

One thing to know about the backfill: `started_at` is added `not null default now()`, so the three
pre-existing sessions now claim a `started_at` of the migration timestamp rather than their real
start. Harmless at 3 rows, but do not read `started_at` as truth for anything created before
2026-08-24.

The migration's trailing `notify pgrst, 'reload schema'` worked — the new columns
(`proctoring_score`, `object_detections`, `attention_pct`) were reachable over PostgREST
immediately, with **no restart needed**. That is the reliable path; contrast with the
`kill -HUP 1` failure documented under the payment-request incident.

### Verification

Site / REST / auth all 200 (49 ms). Served bundle `index-BWuAW6Kb.js` matches the freshly built
`dist`; **no hosted `*.supabase.co` in the bundle**, 19 self-hosted `/sb` refs. 83 functions synced
with the three fixups, **zero boot errors**. All seven containers up, database healthy.
123 tables, 62 profiles, 62 auth users, 25 assessments, 3 interview sessions.

**Unit suite: 335/335 passing across 30 files** — up from 291/301 at `2492621`, so this release
also repaired the ten tests that were failing before it.

Both behavioural fixes were probed live rather than trusted from the diff:

- **`ai-assessment` dedup (`5e36e1a`)** — note the real contract is
  `{action:"generate", topicContent, assessmentTitle, mcqCount, descriptiveCount, videoCount,
  excludedQuestions[]}`; calling it with `{feature, topic, count}` silently returns
  `{"questions":[]}` with HTTP 200, which reads like a broken deploy but is just a bad payload.
  A correct call returned 3 MCQs; re-calling with the first question in `excludedQuestions`
  returned 3 **different** questions, so the `uniqueQuestionResult` filter works end-to-end.
- **`admin-reset-password` (`e4bd2c8`/`6815d28`)** — tested against a throwaway auth user rather
  than a real account: reset returned `{"success":true, userId, email}` (the new echo fields),
  login with the new password 200, with the old password 400, and the probe user was deleted
  afterwards (0 remaining). The new 404 branch also fires correctly: an unknown UUID returns
  *"The selected account is not linked to a valid login user."* Both admin functions still return
  401 unauthenticated.

The `resolveAuthUserId` change is the actual fix — it now checks `auth.admin.getUserById` **first**
for anything UUID-shaped, so a missing optional table in PostgREST can no longer block a reset for
a Student / Trainer / Institute / Admin account.

**Browser E2E** (`~/e2e-banking.cjs` on the DEV box, now extended with a candidate-OTP leg since
that is the path `2044488` rewrote): anon routes 200 with non-empty `#root`; candidate
`9820065335` / OTP `1234` → `/candidate/home` with the full student console; admin sign-in →
`/admin` with the full admin console. **0 page errors, 0 hosted-Supabase requests, 0 `/sb` 4xx/5xx.**

Note the candidate mobile field is `#loginMobile`, not `#mobile` — the latter does not exist and
the leg times out on it.

Rollback assets use stamp `20260824T150630Z`:
`~/bankingjobreadiness/dist.bak-predeploy-20260824T150630Z`,
`.env.bak-predeploy-20260824T150630Z`, and
`~/banking-localpatches-20260824T150630Z.patch`. No pre-migration DB dump was taken this time —
the migration is additive-only and destroys nothing. Disk on the UAT box is at **90 % (13 G free)**;
the accumulated `dist.bak-*` / `.env.bak-*` directories are the obvious thing to prune.

---

## 2026-08-25 — redeployed to `423fd65` (9 commits, 1 migration)

`6815d28` → `423fd65`: `8927a13` fixes the domain/tech assessment lifecycle, six `Changes` commits,
`69a244c` enforces unique assessment question generation, `423fd65` ("Fixed generation failures &
bugs") reworks the shared LLM helper's timeout and failover behaviour. 19 files, +478/−51. All five
local patches survived — none of the nine commits touches them.

### Migration `20260824220000_assessment_question_canonical_uniqueness.sql`

Same shape as the 2026-08-24 lifecycle migration (delete duplicates by canonicalised prompt, then
add a matching unique index) but this run **deleted 0 rows** — the earlier migration had already
cleaned every duplicate, so this one only added the permanent guard:
`assessment_questions_unique_prompt_idx`, a unique index on
`(assessment_id, md5(canonicalized prompt))`. Verified live by inserting an exact duplicate of an
existing row inside a rolled-back transaction — Postgres correctly rejected it with
`duplicate key value violates unique constraint "assessment_questions_unique_prompt_idx"` before the
rollback discarded the probe.

### The actual bug fix in `_shared/llm.ts`

`LLM_PROVIDER_TIMEOUT_MS` went **15000 → 45000**, which is the real content of "Fixed generation
failures & bugs" — AI question/content generation was being aborted at 15s before providers like
Gemini could finish a longer completion. Provider failover was also widened from
`[401,402,403,...retryable]` to also cover `400/404/422` ("model not available on this provider"
should fail over, not abort the whole request), `elevenlabs`/`youtube` were excluded from the
chat-provider pool via a new `NON_CHAT_PROVIDERS` set, and Gemini TTS now copies its decoded audio
into a fresh `Uint8Array` before returning it (fixes a detached-ArrayBuffer class of bug).

**One test was not updated to match:** `llmFallbackCoverage.test.ts` still asserts the shared
source contains the literal `"LLM_PROVIDER_TIMEOUT_MS = 15000"`; it now reads `45000`, so that one
assertion fails (340/341 passing). This is a stale test, not a regression — the 45000 value is the
deliberate fix. Not corrected locally since it's upstream's file to fix and doesn't affect runtime
behaviour.

### Verification

Site / REST / auth 200/200/200. Served bundle `index-DzQ1eYgD.js` matches the freshly built `dist`;
no hosted `*.supabase.co`, 19 self-hosted `/sb` refs. 83 functions synced, 3 fixups, **0 boot
errors**. All seven containers up, database healthy. 123 tables, 62 profiles, 62 auth users,
25 assessments, 729 assessment questions (unchanged by the migration).

**`generate-assessment-questions` probed live twice** — once cold, once with the first returned
question passed back in `excludedQuestions` — both HTTP 200 in ~8s with real Gemini-generated MCQs
on "KYC norms and AML compliance", and the second call's three questions were all distinct from the
excluded one, confirming semantic dedup still works with the new timeout/failover logic layered on
top of it.

**Browser E2E** (`~/e2e-banking.cjs`, same candidate + admin legs as the prior release): anon routes
200 with non-empty `#root`; candidate `9820065335` / OTP `1234` → `/candidate/home`; admin → `/admin`
with full console. **0 page errors, 0 hosted-Supabase requests, 0 `/sb` 4xx/5xx.**

Rollback assets use stamp `20260825T015122Z`:
`~/bankingjobreadiness/dist.bak-predeploy-20260825T015122Z`,
`.env.bak-predeploy-20260825T015122Z`, `~/banking-localpatches-20260825T015122Z.patch`. No DB dump
taken — the migration deleted 0 rows and is otherwise additive. **Disk remains at 90% (13G free)** —
now three releases running without a prune of the accumulated `dist.bak-*`/`.env.bak-*` directories;
worth clearing on the next deploy.

## 2026-08-26 — repaired candidate OTP login for `9769440000`

Candidate **Himanshu Bhagat** (`9769440000`) received the candidate-login toast "Account not
found" after entering the correct demo OTP `1234`. The public profile was present, active and
approved, and its reconstructed auth identity (`9769440000@bankready.app`) was confirmed, but
`auth.users.encrypted_password` was empty. This is one of the imported identities documented in
`banking-postgres-migration.md`; the hosted password hash was unavailable during reconstruction.

Provisioned the app's policy-compliant derived credential with
`~/banking-sb/set-user-password.sh 9769440000 'Otp_9769440000_1234'`. No source change, frontend
deployment or migration was required. Exact fresh-browser verification against the live candidate
form — mobile `9769440000`, Send OTP, OTP `1234`, Verify — redirected to `/candidate/home`, rendered
Himanshu's full student console, and produced **0 page errors and 0 `/sb` API errors**.

## 2026-08-27 — redeployed to `5b4b5f2` (7 commits, no migrations)

`423fd65` → `5b4b5f2`: `1240e26` work in progress, `426ed22` fixes module creation with schema
drift, `83fab4d` fixes bulk-candidate mobile login compatibility, two `Changes` commits, `77e9d0a`
`Changes`, `5b4b5f2` fixes taxonomy 400 errors. `supabase/migrations` stayed at 161 files (`git diff
--stat` between the two commits shows no path under `supabase/migrations`), so this release is a
functions + frontend deploy only — no `replay-migrations.sh` or `sql/` fixup step needed.

`83fab4d` changes `supabase/functions/bulk-create-users/index.ts`'s derived password from
`otp_<mobile>_1234` to `Otp_<mobile>_1234`, i.e. it upstreams the same policy-compliant capitalization
fix that was hand-patched into `Login.tsx` on 2026-08-21 (see "candidate OTP login policy fix"
above) — new bulk-imported candidates now get a GoTrue-acceptable password on creation instead of
needing a follow-up `set-user-password.sh` repair.

### Local patches — verified as five, matching the standing inventory

`git status` after the pull showed exactly the five expected dirty files (`.env`,
`src/components/pil-admin/LearningPathsManager.tsx`, `src/hooks/useLearningPaths.ts`,
`src/lib/adminErrorLogger.ts`, `supabase/functions/mcp/index.ts`) plus the disposable
`package-lock.json`. None of the 7 incoming commits touched a patched file, so `git pull` fast-forwarded
cleanly with zero stash/merge dance required. Deployed edge functions are unaffected by the working-tree
`mcp/index.ts` diff either way — `sync-functions.sh` always overlays `~/banking-sb/function-fixups/mcp/`
on top of whatever the repo ships (verified: deployed `banking-sb/functions/mcp/index.ts` and
`banking-sb/functions/live-session-rsvp/index.ts` byte-match their fixup-dir source both before and
after this sync).

### Verification

Site / REST / auth-health all 200. Served bundle `index-4Krcghy0.js` matches the freshly built `dist`
(confirmed via the live page's script tag). No hosted `*.supabase.co` data-plane URL in the bundle (the
one `api.supabase.co`-shaped grep hit is the documented inert `AdminSecurityMigration.tsx` Management-API
remnant, not a data-plane leak) and no `.dev.pluginlive.com` leak. 83 edge functions synced with the
three standing fixups (`live-session-rsvp`, `main`, `mcp`); functions container restarted clean with zero
new boot errors. All seven `banking-sb-*` containers up, `banking-sb-db` healthy.

**Browser E2E**, two independent candidate accounts plus admin, via a fresh headless Chromium context
each: mobile `9820065335` (task-specified) and `9100000021` (standing demo account) both Send OTP →
`1234` → Verify → `/candidate/home` with the full student console, **0 page errors, 0 `/sb` API
errors**. Trainer `9100000022` → `/journey/trainer`. Admin `demo.admin@bankready.app` /
`Demo@Admin2026` signs in with 0 errors, landing on `/` — the guarded `/admin` console route is
separate, per the existing note above.

Unit suite: 348 passed / 349 (1 failing — the same stale `llmFallbackCoverage.test.ts` literal
documented under the 2026-08-25 release; not touched by this release's commits, not a regression).

Rollback assets use stamp `20260827T023655Z`: `~/bankingjobreadiness/dist.bak-predeploy-20260827T023655Z`.
No DB dump or functions-predeploy archive was taken — no migration and no fixed-up function changed, so
there was nothing destructive to snapshot beyond the frontend `dist/`.

## 2026-08-28 — admin login for `prakash.chinnadurai@gmail.com`: two distinct causes

Reported as `POST /sb/auth/v1/token?grant_type=password` → **400 Bad Request**, "Login failed /
Invalid credentials", on the Admin tab. Two independent problems, neither a deploy regression.

**1. The Admin tab cannot accept a personal email that has no auth user.** `handleAdminLogin` in
`src/pages/Login.tsx` passes the User ID straight through as the GoTrue email, only appending the
domain when there is no `@`:

```js
const email = adminId.toLowerCase().includes("@") ? adminId : `${adminId.toLowerCase()}@bankready.app`;
```

There is **no auth user with email `prakash.chinnadurai@gmail.com`** (`auth.users` has exactly one
non-`@bankready.app` address, `banking.admin@pluginlive.com`). So GoTrue correctly returns 400. The
gmail address only exists as a **`public.profiles.email` value**, on profile
`6f18325e-5f93-4499-87bd-74d77086054a` → user `ce86d36b-8987-4d0e-b685-3d3ebf953761`, whose auth
identity is the mobile-derived `9820065336@bankready.app`. **`profiles.email` is display data and is
never consulted at sign-in** — do not read a profile email as a usable login.

**2. That account's password hash did not match the app-derived password.** `ce86d36b` holds
`admin` + `trainer` + `candidate` roles, but was part of the **2026-08-09 04:46:48 import batch** —
the same batch as `9769440000` (repaired 2026-08-26). Both `Otp_9820065336_1234` and the legacy
lowercase `otp_` variant returned `invalid_grant`, and `last_sign_in_at` was NULL, i.e. the account
had **never once been able to log in**, by any route — admin *or* mobile OTP.

Repaired in place, matching the earlier fix:

```sql
update auth.users
   set encrypted_password = extensions.crypt('Otp_9820065336_1234', extensions.gen_salt('bf')),
       updated_at = now()
 where id = 'ce86d36b-8987-4d0e-b685-3d3ebf953761';
```

Note `pgcrypto` lives in the **`extensions` schema** on this DB — bare `gen_salt()`/`crypt()` fail
with `function gen_salt(unknown) does not exist`; schema-qualify them.

Setting this password is **not** a side-effect-free admin reset: the mobile OTP path
(`src/lib/candidateMobileAuth.ts`) signs in with exactly `Otp_<mobile>_1234`, so the admin password
and the OTP-derived password are the same secret. Setting it to anything else would silently break
that user's Candidate/Trainer OTP login. Here it was already broken, so this restored both.

Verified live: password grant returns an access token; through the real UI, Admin tab User ID
`9820065336` + password `Otp_9820065336_1234` signs in as **Prakash** and `/admin` renders the full
console (67 candidates, all sidebar groups), 0 page errors.

**Working admin logins on UAT:** `9820065336` (Prakash, above), `demo.admin@bankready.app` /
`Demo@Admin2026`, `banking.admin@pluginlive.com`. If a gmail-addressed admin login is genuinely
wanted, it needs a **new** auth user — renaming `ce86d36b`'s auth email would break mobile OTP for
`9820065336`, since that path looks up `<mobile>@bankready.app`.

## 2026-08-28 — the four source local patches are now upstream (`d6b9e0c`)

The long-standing "five local patches carried on the UAT checkout" inventory is **now one**. The four
*source* patches were committed and pushed to `origin/main` as `d6b9e0c`, so a fresh clone builds
correct code and there is nothing to reapply after a pull:

| File | What it fixes |
|---|---|
| `src/components/pil-admin/LearningPathsManager.tsx` | saving an existing path ran `delete from learning_paths where id = pathId` — **it deleted the path being saved**, silently, while the UI said "Learning path updated" |
| `src/hooks/useLearningPaths.ts` | both assignment reads selected from `learning_paths`, so every path rendered as an unscoped assignment |
| `src/lib/adminErrorLogger.ts` | `SUPABASE_URL` was the hardcoded hosted project URL, so post-migration none of the `startsWith()` prefix checks matched and admin error logging **recorded nothing** |
| `supabase/functions/mcp/index.ts` | pins `@lovable.dev/mcp-js` to `0.26.3` so the function boots |

**`.env` remains the one deliberate local patch** and must never be committed — it holds the UAT
self-hosted keys. `package-lock.json` also shows as modified on the box; that is npm-version noise
(`libc` fields dropped by the older npm on the UAT host), not a real change — leave it uncommitted.

So the post-pull check is now: **`.env` intact, and `git status` shows only `.env` +
`package-lock.json`** (plus the `*.bak-predeploy-*` / `dist.*` rollback dirs, which are untracked by
design). Anything else appearing modified means a patch regressed.

Also note the earlier inventory table in this doc that lists only four patch files is stale — it
predates the `mcp/index.ts` entry. The authoritative list is the one above.

## 2026-08-28 — admin "Reset Password" bricked every mobile/OTP account (fixed, `3a4d977`)

**The bug.** Candidates and trainers sign in with mobile + OTP on a screen that has **no password
field** — `src/lib/candidateMobileAuth.ts` calls `signInWithPassword` with a password *derived from
the mobile number* (`Otp_<mobile>_1234`, with a legacy lowercase `otp_` fallback). That derived value
is the account's only usable credential. So the admin console's **Reset Password** action, which
stored an admin-chosen password via `admin.auth.admin.updateUserById`, left the account in a state
where the OTP screens could no longer authenticate it **and there was nowhere to type the new
password** — locked out of every route, silently, while the UI reported success.

Worse, the natural reaction to the lockout is to reset the password again, which re-breaks it. The
audit log shows exactly that loop: resets on **2026-08-18, 08-21, 08-23, 08-24** and four more on
**08-28 05:35–05:36**, across five accounts, every one of them an attempt to fix the previous one.
Five logins were dead at the time of the fix (`9820065335`, `9820098200`, `5555555555`,
`7777777777`, and `9820065336`).

**The fix** (`supabase/functions/_shared/otp-login.ts` + both reset paths): look the target up first
and **refuse** when its auth email matches a 10-digit mobile at `bankready.app`, returning 400 with a
message that names the mobile and points at OTP 1234. The lookup was moved *ahead of* password
validation so the admin sees the real reason instead of a password-strength complaint.

Two details that matter:

- **`admin-reset-password` needed the same guard.** `src/lib/adminPasswordReset.ts` calls
  `admin-user-actions` first and falls back to `admin-reset-password`; that function is also callable
  directly. Guarding only one leaves the hole open.
- **The match is anchored** (`^(\d{10})@bankready\.app$`, case-insensitive) so real email accounts —
  `demo.admin@bankready.app`, `banking.admin@pluginlive.com` — stay resettable, and a lookalike
  domain like `...@bankready.app.evil.com` is not mistaken for an OTP login.

Verified live against the deployed functions with a real admin token: resetting `9820065336` is
refused on **both** endpoints with the OTP message; a throwaway email user
(`guardprobe@example.com`) still resets successfully and logs in with the new password (probe
deleted afterwards, 0 rows left). Unit tests `src/lib/otpLoginGuard.test.ts` (6 cases) cover
detection, the lookalike domain, and the derived-password format. Full suite 360 passed / 361 — the
one failure is the long-standing stale `LLM_PROVIDER_TIMEOUT_MS` literal in
`llmFallbackCoverage.test.ts`, untouched by this change.

**Data repair.** The five already-bricked accounts were restored to the derived credential:

```sql
update auth.users
   set encrypted_password = extensions.crypt('Otp_' || substring(email,1,10) || '_1234',
                                             extensions.gen_salt('bf')),
       updated_at = now()
 where email in ('9820065335@bankready.app', ...);
```

All five now return 200 on a password grant, and `9820065335` was driven through the real UI —
Send OTP → `1234` → Verify → `/candidate/home` as "Prakash Chinnadurai", zero page errors.

Deployed by copying the three files into `~/banking-sb/functions/` and restarting
`banking-sb-functions` (zero boot errors). No frontend rebuild was needed: `adminPasswordReset.ts`
already surfaces the function's `error` string, and a 400 does not trigger its
`shouldTryDedicatedReset` fallback (that requires status >= 500).
