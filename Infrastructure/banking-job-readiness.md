---
type: reference
tags: [service, frontend, uat, supabase, lovable]
---

# Banking Job Readiness (Candidate Job Readiness Journey)

**Repo:** `PluginLive-Technologies/bankingjobreadiness`, branch `main`
**UAT path:** `/home/ubuntu/bankingjobreadiness` (on the UAT box, directly under `~/`)
**Live URL:** `https://banking.uat.pluginlive.com/`
**Stack:** Vite + React + shadcn/ui SPA, backend on **Supabase** (Postgres + Edge Functions, project `kbwjokmmzkgjwiqelrdc`) — not part of the PluginLive Node/Prisma stack.

## Why it's off the standard deploy path

This app (and its sibling `ailearning.uat.pluginlive.com`) came in as a Lovable-generated SPA cloned straight into the UAT box's home directory, not under `~/frontend/`. It is **not managed by `auto_deploy.sh`** — deploys are manual.

## Deploying (frontend)

```bash
cd ~/bankingjobreadiness
cp -a dist ../bankingjobreadiness-dist-backup-$(date +%Y%m%d-%H%M%S)   # nginx serves dist/ live; keep a rollback
git pull origin main   # if package-lock.json is dirty from a prior install, `git checkout -- package-lock.json` first
nvm use 20 && npm ci --legacy-peer-deps && npm run build
```

If that `git pull` 403s, the org GitHub token has expired — see `Infrastructure/github-access.md` (the checkout's `origin` URL carries its own token, so the credential store alone is not enough).

- nginx (`/etc/nginx/sites-enabled/banking-react.conf`) serves `dist/` as static files directly — no service/container restart needed, nginx picks up the new build immediately. Because there is no container swap, a failed build leaves a **half-updated live site** — back `dist/` up before building.
- `.env` holds Supabase keys for project `kbwjokmmzkgjwiqelrdc`; `VITE_*` vars are baked in at build time.

### `--legacy-peer-deps` is mandatory (as of 2026-08-04)

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
grep -rhoE 'https://[a-z0-9]+\.supabase\.co' . | sort | uniq -c        # expect only kbwjokmmzkgjwiqelrdc
grep -rhoE '([a-z0-9-]+\.convex\.(cloud|site)|[a-z-]+\.dev\.pluginlive\.com)' . | sort -u   # expect empty

# 2. Site actually renders (SPA — a 200 on index.html proves nothing)
curl -s https://banking.uat.pluginlive.com/ | grep -o 'assets/index-[A-Za-z0-9_-]*\.js'   # must match dist/index.html
```

Then headless-load the page (`playwright-core` lives in `~/browser-mcp/node_modules`, browser at `/usr/bin/chromium-browser`) and expect **no `pageerror`** and a non-empty `#root`.

A `localhost:9999` string in the bundle is expected — it comes from vendor code (`undici`'s mock-agent and the `supabase-js` UMD build), not app code.

**Expected-noise gotcha:** on load you will see three Supabase REST calls to `/rest/v1/{assessments,profiles,modules}` report `net::ERR_ABORTED` in devtools. They are **not** failures — each returns HTTP 200 first and is then aborted by the app's own `AbortController`/React StrictMode cleanup. Log the `response` event, not just `requestfailed`, before chasing these.

## Backend (Supabase) — separate deploy step, not covered by the frontend build

`supabase/functions/*` (Edge Functions, Deno) and `supabase/migrations/*` (SQL) live in the same repo but are **not** deployed by `npm run build` — they require the Supabase CLI (`supabase functions deploy <name>`, `supabase db push`) against project `kbwjokmmzkgjwiqelrdc`.

**The frontend deploy and the Supabase deploy have drifted apart — treat the backend as a separate, explicit step.** As of 2026-08-04 the UAT checkout carries **81 edge functions and 118 migrations** (newest: `20260801000000_interview_proctoring_settings.sql`, `20260728150000_fix_security_vulnerabilities.sql`). Successive frontend-only deploys have never pushed these from this box, so a fresh `npm run build` ships UI that may call functions/tables not yet present in the Supabase project. If a newly-deployed screen 404s or errors on a `/functions/v1/...` call, this drift is the first thing to check — not the frontend build.

**Resolved:** the `bulk-create-users` "Not authorized" bug (service-role client calling `rpc("has_role")`, which lives in the locked-down `private` schema and is executable only by `authenticated`) was previously carried as an uncommitted local patch on the UAT box. It has since **landed upstream** — `supabase/functions/bulk-create-users/index.ts` now authenticates the caller with an anon-key client and reads `user_roles` directly via the service-role client, matching `admin-confirm-candidates` / `bulk-export-enqueue` / `assessment-report`. No local patch to preserve across pulls anymore. It still needs to be *deployed* to Supabase per the drift note above.
