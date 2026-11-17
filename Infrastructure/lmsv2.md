# lmsv2 — the separate v2 LMS app at `/v2` (DEV, UAT, PROD — 2026-11-16)

`lmsv2` is a **separate application**: its own repo, its own self-hosted Supabase stack, its own database and
its own file prefix. It started on 2026-11-16 as a full copy of Banking Job Readiness (code, data and files), and
the two now evolve independently. It is served under `/v2/` on the same host as the banking app, so it needs no
DNS or TLS of its own.

| Env | URL | Branch (repo `PluginLive-Technologies/lmsv2`) | Box |
|---|---|---|---|
| DEV | https://banking.dev.pluginlive.com/v2/ | `Development` | DEV box |
| UAT | https://banking.uat.pluginlive.com/v2/ | `UAT` | UAT box |
| PROD | https://lms.pluginlive.com/v2/ | `release/prod-v1.1` (tag/cherry-pick model, same as banking) | `Pl-Prod-Banking` VM |

The PROD branch is the banking PROD release (v1.1.14) plus the `/v2` base-path commit. The banking holds apply
to lmsv2 too: the LMS v2 student UI and designer work, and the lesson-video watch gate / AI video checker, are
not on `release/prod-v1.1`.

## What is separate and what is shared

| | banking (v1, `/`) | lmsv2 (`/v2/`) |
|---|---|---|
| Repo | `bankingjobreadiness` | `lmsv2` (full mirror of all branches + tags on 2026-11-16, not a GitHub fork) |
| Stack dir | `~/banking-sb` (PROD `/opt/banking-sb`) | `~/lmsv2-sb` (PROD `/opt/lmsv2-sb`) |
| Containers | `banking-sb-*` | `lmsv2-sb-*` |
| Ports (127.0.0.1) | db 5442/5443, gateway 8200, rest 8201, auth 8202, storage 8203, functions 8204, realtime 8205, metabase 8210 | db **5444**, gateway **8220**, rest 8221, auth 8222, storage 8223, functions 8224, realtime 8225, metabase **8230** |
| Database | `banking_dev` / `banking_uat` / `banking_prod` | `lmsv2_dev` / `lmsv2_uat` / `lmsv2_prod` (+ own `metabase_app`) |
| JWT secret, anon + service keys, realtime secret | own | **own** (new, generated at clone; v1 keys get 401 on `/v2/sb` and vice versa) |
| Files (OCI bucket, same buckets) | prefix `banking/` (`TENANT_ID: banking`) | prefix `lmsv2/` (`TENANT_ID: lmsv2`); objects copied server-side on 2026-11-16 |
| Browser session key | default (`sb-<host>-auth-token`) | `sb-lmsv2-auth-token` (`VITE_AUTH_STORAGE_KEY`) — same origin, so the two logins must not share a key |
| Shared, not copied | — | mail relay (172.17.0.1:5010), third-party keys in `functions-secrets.env` (MSG91, Gemini, ElevenLabs, Google OAuth client), DB role passwords, `CERT_LINK_SECRET`, Metabase embed secret, `cert-renderer:2` image |

Bucket lifecycle rules only match `verification/`, `proctor/`, `videos/`, `audio/`, `_expired/`, so `lmsv2/`
objects are never auto-deleted (checked 2026-11-16 on `pl_dev_poc`, `pl-uat-assessment`, `pl-prod-assessment`).

## How `/v2` works

- Build: `VITE_BASE_PATH=/v2/ npx vite build` (vite `base`). The router gets `basename` from
  `import.meta.env.BASE_URL`; redirects and absolute links go through `src/lib/appPath.ts`
  (`appUrl`, `absoluteAppUrl`, `BASE`). Root builds (`VITE_BASE_PATH` unset) behave exactly as before.
  Commits: `bbada66dd` (Development), `5e734a098` (UAT), `99933b2ac` (release/prod-v1.1, hand port).
- Backend URL: `https://<host>/v2/sb`. Stack config: `SITE_URL=https://<host>/v2`,
  `API_EXTERNAL_URL=https://<host>/v2/sb`, functions `SITE_URL`/`PUBLIC_BASE_URL`/`SUPABASE_PUBLIC_URL`/`METABASE_URL`
  under `/v2`, `MB_SITE_URL=https://<host>/v2/metabase/`. Stored URLs in the DB were rewritten to `/v2`.
- nginx: one line `include snippets/lmsv2-v2.conf;` in the banking site (`banking-dev.conf`,
  `banking-react.conf` on UAT, `banking-prod.conf`), before `location /assets/`. The snippet holds every `/v2/`
  location (`^~` prefixes so the v1 regex locations never catch them): `/v2/sb/` → 8220 (realtime and stt-stream
  as WebSockets, functions unbuffered for SSE), `/v2/metabase/` embed paths → 8230, static app from
  `<root>/v2` with SPA fallback to `/v2/index.html`. Static roots: DEV `/var/www/lmsv2-dev`,
  UAT `/home/ubuntu/lmsv2-www`, PROD `/opt/lmsv2/www`. Backups of each site conf: `*.bak-20261116T*-pre-lmsv2`.

## Deploying

| Env | Command | Notes |
|---|---|---|
| DEV | `bash ~/lmsv2-sb/deploy.sh` (on DEV) | Fetches `github/Development` into `~/lmsv2-dev-app` (→ `/data/lmsv2/dev-app`), snapshot to `/data/lmsv2/snapshots/`, migrations (fixup-aware), grants, functions, build `/v2/`, publish to `/var/www/lmsv2-dev/v2/`. |
| UAT | `bash ~/lmsv2-sb/deploy.sh` (on UAT) | Fetches `origin/UAT` into `~/lmsv2`, publishes to `~/lmsv2-www/v2/`. |
| PROD | `bash ~/lmsv2-setup/prod-deploy.sh [ref]` (on DEV) | Archives `github/release/prod-v1.1`, snapshot to `/data/backups/lmsv2/`, builds on the VM into `/opt/lmsv2/app-<sha>` (symlink `/opt/lmsv2/app`, last 3 kept), publishes `/opt/lmsv2/www/v2/`, writes `/opt/lmsv2/DEPLOYED`. **Stops if the release adds migrations** — apply them first with the banking PROD procedure. PROD only on an explicit go. |

The app env is the deploy's local `.env` (DEV `~/lmsv2-dev-app/.env`, UAT `~/lmsv2/.env`, PROD
`/opt/lmsv2/app.env`). `VITE_STUDENT_LMS_V2_ENABLED` mirrors banking today: DEV `true`, UAT `false`, PROD unset.

Checks (on DEV): `~/lmsv2-setup/checks/v2load.cjs <base> /v2/ /v2/login …` (headless: no page errors, every API
call under `/v2/sb`, none to v1 `/sb`), `~/lmsv2-setup/checks/authcheck.sh <backend> <service> <anon>`
(throwaway-user password sign-in round trip, cleans up). Setup scripts: `~/lmsv2-setup/` (`clone-stack.sh`,
`copy-storage.sh`, `rehost.sh`, `install-nginx.sh`, `lmsv2-v2.nginx.tmpl`).

## Not carried over / open

- **Google sign-in** on `/v2` needs `https://<host>/v2/sb/auth/v1/callback` added as an authorised redirect URI on
  the Google OAuth client (same client as banking). Until then Google sign-in on `/v2` fails; OTP and password work.
- **Daily college parent alerts cron** (`college-alerts-daily.sh`, UAT + PROD) is NOT installed for lmsv2: the
  copied data has the same real parents/students, so it would send them every alert twice.
- **PROD backup**: `/usr/local/bin/lmsv2-backup` nightly 20:45 UTC (`/etc/cron.d/lmsv2-backup`), 14 days in
  `/data/backups/lmsv2/daily`. DEV/UAT: deploy snapshots only (like banking).
- Same origin as banking: `sessionStorage`/`localStorage` keys other than the auth session (e.g. the LMS tab
  cache `lms-cache:v2:<uid>`) are shared between `/` and `/v2` in one browser; user ids are the same in both
  copies. Harmless for different users; one person using both apps in one tab can see the other app's cached
  course list until it expires (5 min).
- Capacity: each stack adds ~2.3 GB RAM (Metabase ~1.3 GB). The DEV root disk was ~1.9 GB free on 2026-11-16;
  lmsv2 DEV lives on `/data` for that reason.

## Sign-in through auth.<env>.pluginlive.com (DEV + UAT 2026-11-17, PROD pending)

LMS people sign in on the PluginLive sign-in page, with a password or a one-time code (see
`ATS/auth-react-login-app.md`). The LMS's own login pages send signed-out visitors there
(`PluginLiveLoginGate`, on when `VITE_PLUGINLIVE_AUTH_URL` is set), and sign-out returns there.

| Env | LMS address | Callback |
|---|---|---|
| DEV | admins https://admin.dev.pluginlive.com/lms, candidates https://corporate.dev.pluginlive.com/lms/candidate (moved off `/v2` on 2026-11-17) | `<address>/oauth/callback#code=…` |
| UAT | https://banking.uat.pluginlive.com/v2 (one address for admins and candidates) | `https://banking.uat.pluginlive.com/v2/oauth/callback#code=…` |

How it fits together:
- user-management-node `app/services/lmsProvider.js` calls the LMS edge function **`pluginlive-oauth`**
  server to server (header `x-client-secret`): `/verify` (email + LMS password), `/lookup` (where to send a code),
  `/signin` (after user-management-node checked the code), `/issue` + `/check` + `/grant` + `/revoke` (LMS tab /
  LMS access for PluginLive admins — UI on DEV only). Every route answers 401 without the secret.
- A match comes back with a one-time **LMS code** (`oauth_login_codes`, SHA-256 stored, 5 min, single use).
  Picking the LMS account redirects to `<LMS>/oauth/callback#code=`; the LMS trades it at `pluginlive-oauth/token`
  for its own session. No PluginLive token or cookie is issued for an LMS pick.
- `/signin` for a trainer or candidate runs the same account set-up as the LMS's own code login
  (`_shared/login-otp-session.ts`, shared with `candidate-otp-login`): trainer-row backfill, find/create the Auth
  user (mobile identity `<mobile>@bankready.app`), link records, institute plan sync, email confirm.
- With `PLUGINLIVE_AUTH_URL` set in the functions env, every LMS email links to auth.<env> and new admins get the
  code steps instead of a temporary password (`_shared/login-links.ts`, `onboarding-email.ts`).

Configuration (box-local, not in git):

| Where | DEV | UAT |
|---|---|---|
| user-management-node `.env.<env>` | `LMS_PROVIDER_URL=http://172.17.0.1:8240/functions/v1/pluginlive-oauth`, `LMS_PROVIDER_CLIENT_SECRET`, `LMS_PROVIDER_ANON_KEY`, `LMS_ADMIN_FE_URL`, `LMS_CANDIDATE_FE_URL` | same keys; both FE URLs = `https://banking.uat.pluginlive.com/v2` |
| `~/lmsv2-sb/docker-compose.yml` gateway | extra port `172.17.0.1:8240:80` so the `auth` container reaches the LMS | same (added 2026-11-17) |
| `~/lmsv2-sb/functions-secrets.env` | `PLUGINLIVE_OAUTH_CLIENT_SECRET`, `PLUGINLIVE_AUTH_URL=https://auth.dev.pluginlive.com` | same, `https://auth.uat.pluginlive.com` |
| LMS app `.env` | `VITE_PLUGINLIVE_AUTH_URL=https://auth.dev.pluginlive.com` | `https://auth.uat.pluginlive.com` |

Gotcha: `docker restart lmsv2-sb-functions` does **not** reload `functions-secrets.env`; use
`docker compose up -d --no-deps functions`.

UAT commits (cherry-picked, lmsv2 `UAT` `407d67b44`): auth.pluginlive sign-in + `/oauth/callback`, no LMS landing
page / sign-out to auth, LMS tab handoff (backend only), LMS access check/grant/revoke, code sign-in. The LMS's
own code login (`candidate-otp-login`, `request-login-otp`) still exists and is reachable only by direct URL;
removing it is open. Migration `20261117090000_pluginlive_oauth_codes` (DB-Scripts `LMS v2 PluginLive Sign-in/
20261117T060901Z__oauth_login_codes.sql`) applied on DEV + UAT.
