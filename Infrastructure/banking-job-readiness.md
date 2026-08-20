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
