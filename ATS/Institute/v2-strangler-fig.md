# Institute Portal v2 — strangler-fig (LIVE on DEV + UAT since 2026-08-06)

The Institute (TPO) portal is being rebuilt screen-by-screen behind a
strangler-fig, the same pattern as `corporate-react-v2`. A second app sits
alongside the v1 CRA app on the **same origin**, so the JWT in `localStorage` is
shared and there is no re-login when crossing the seam.

| Repo | Checkout | Stack | Where it runs |
|---|---|---|---|
| `institute-react` (v1) | `~/frontend/institute-react` | CRA + AntD, webpack | DEV: bare node :3002 · UAT: docker `institutereact` :3002 |
| `institute-react-v2` | `~/frontend/institute-react-v2` | Next.js 16 App Router + TS + Tailwind v4, `basePath=/v2` | DEV: systemd :3011 · UAT: systemd :3012 |

Backend is the **existing** `institute-node` — v2 added new read endpoints, it
did not fork the API. Roughly zero business APIs were rewritten; the v2 Route
Handlers act as a BFF that reshapes existing responses.

## Topology

```
institute.<env>.pluginlive.com
  ├─ /            → v1 (CRA)          :3002
  └─ /v2          → institute-react-v2 :3011 DEV / :3012 UAT   (nginx location /v2)
```

**UAT runs v2 on :3012, not :3011** — 3011 on that box is already taken by
`pil-ai-learning`. The nginx block lives in `/etc/nginx/sites-available/inst-react.conf`
and must be declared **before** `location /`.

Service unit: `/etc/systemd/system/institute-react-v2.service` (`next start`,
`Restart=always`). It reads `.env.local` at runtime for the server-side BFF vars;
`NEXT_PUBLIC_*` and `basePath` are **baked into the bundle at build time**.

## Screens migrated so far

| Screen | v2 route | Notes |
|---|---|---|
| TPO Dashboard | `/v2/dashboard` | Single assessment view — see below |
| Manage Assessments | `/v2/assessments` | List + filters + type legend |
| Assessment detail | `/v2/assessments/:id` | Overview · Schedule · Student-wise performance |
| Full schedule | `/v2/schedule` | Month/Week agenda + mini calendar |

Everything else is still v1.

## Nav wiring (v1 → v2)

Since 2026-08-06 the v1 sidebar routes as follows:

- **Dashboard → `/tpoDashboard`** (stays in v1, the legacy placement analytics)
- **Assessment → `/v2/dashboard`** (the v2 cockpit is the assessment landing
  page; its own sidebar leads on to `/v2/assessments`)

Both live in `institute-react/src/modules/Nav/navItems.js`. Two `accessLevel`
gates in `modules/Nav/index.js` hard-code the v2 path — level 2 gets the entry,
level 1 does not — so they must be updated together with the navItem.

**`onItemClick` must hard-navigate for `/v2/` paths.** `navigate(path)` is
react-router's SPA navigate; it finds no match for `/v2/*` and renders v1's 404
inside the v1 shell. The handler checks `path?.startsWith('/v2/')` and sets
`window.location.href` so the request reaches nginx. After any nav flip users
must **hard-refresh once** — until then the old bundle's handler is running.

## v2 Dashboard — assessment only

The design shipped with three lens tabs (Overview / Assessment / ATS). **The tabs
and every ATS block were removed on 2026-08-06**: placement/ATS stays in the v1
portal, so the v2 cockpit covers assessments only. Removed with them: the
`/api/dashboard/ats` BFF route, its corporate-node calls, and the plan-based
upgrade lock.

Blocks now rendered: `b1` needs-attention + 3 season KPIs, `b4a` active
assessment schedules, `b4c` student at-risk, `b4d` department distribution,
`b4b` competency, `b6` year-on-year (only with 2+ years of data), plus the
"This week" rail.

## Auth

There is **no middleware auth check** — the JWT lives in `localStorage`, which
the server cannot read. `components/shell/AuthGate.tsx` gates on the client and
redirects to `NEXT_PUBLIC_LOGIN_URL` with `?next=<href>`. Every BFF route
independently derives `institute_id` from the bearer token and returns **401**
when absent, so the data boundary does not depend on the client gate.

## Env — and the DEV-URL trap

`.env.local` per box (never committed):

| Var | UAT value |
|---|---|
| `INST_API_URL` | `https://api-inst.uat.pluginlive.com/` |
| `AUTH_API_URL` | `https://api-auth.uat.pluginlive.com/` |
| `ADMIN_API_URL` | `https://api-admin.uat.pluginlive.com/` |
| `NEXT_PUBLIC_LOGIN_URL` | `https://auth.uat.pluginlive.com/` |
| `NEXT_PUBLIC_BASE_PATH` | `/v2` |

**Build on the target box.** `NEXT_PUBLIC_*` is inlined at build time, so a
DEV-built bundle carries `*.dev.pluginlive.com` and would silently send UAT users
to DEV. Verify before swapping:

```bash
grep -rho '[a-z-]*\.dev\.pluginlive\.com' .next/static .next/server | sort | uniq -c   # must be empty
```

Never add a `?? 'https://...dev...'` fallback for one of these vars — it is not a
runtime default, it is a literal baked into every bundle, and it defeats the grep
above. `src/lib/auth.ts` throws when `NEXT_PUBLIC_LOGIN_URL` is missing instead.

## Deploying v2

Not in `auto_deploy.sh` (that script only knows the numbered v1 services).

```bash
# on the target box
cd ~/frontend/institute-react-v2
git pull origin UAT
corepack prepare pnpm@10.33.0 --activate     # pnpm, NOT npm — the repo has pnpm-lock.yaml
pnpm install --frozen-lockfile
rm -rf .next && pnpm build
grep -rho '[a-z-]*\.dev\.pluginlive\.com' .next/static .next/server   # must be empty
sudo systemctl restart institute-react-v2
```

`npm ci` fails here — there is no `package-lock.json`.

## Order of operations when flipping a nav entry

v2 must be **up on the target environment before** the v1 nav change ships, or
every click on that entry 404s. Deploy order: `institute-node` → stand up v2 →
verify → flip v1 nav.
