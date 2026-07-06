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
git pull origin main   # if package-lock.json is dirty from a prior install, `git checkout -- package-lock.json` first
nvm use 20 && npm install && npm run build
```

- nginx (`/etc/nginx/sites-enabled/banking-react.conf`) serves `dist/` as static files directly — no service/container restart needed, nginx picks up the new build immediately.
- `.env` holds Supabase keys for project `kbwjokmmzkgjwiqelrdc`; `VITE_*` vars are baked in at build time.

## Backend (Supabase) — separate deploy step, not covered by the frontend build

`supabase/functions/*` (Edge Functions, Deno) and `supabase/migrations/*` (SQL) live in the same repo but are **not** deployed by `npm run build` — they require the Supabase CLI (`supabase functions deploy <name>`, `supabase db push`) against project `kbwjokmmzkgjwiqelrdc`. As of 2026-07-06 the UAT checkout has pulled in a large batch of new functions/migrations (AI interview practice, admin LLM-provider config, proctoring analytics/report generation, taxonomy bulk management, cohort insights, bulk-export repair) that have not yet been pushed to Supabase from this box — treat backend deploy as a separate, explicit step.

**Known in-flight fix (uncommitted on the UAT box as of 2026-07-06):** `supabase/functions/bulk-create-users/index.ts` was patched locally to stop calling `rpc("has_role")` from the service-role client — that RPC lives in the locked-down `private` schema (migration `20260517025711`) and is only executable by `authenticated`, not `service_role`, so every caller (including real admins) was failing with "Not authorized". The fix authenticates the caller with a user-scoped client (anon key + caller's bearer token) and checks `user_roles` directly via the service-role client, mirroring the pattern already used in `admin-confirm-candidates` / `bulk-export-enqueue` / `assessment-report`. Not yet committed or deployed to Supabase.
