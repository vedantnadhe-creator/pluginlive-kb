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
| Manage Assessments | `/v2/assessments` | Schedule-wise / Student-wise toggle — see below |
| Assessment detail | `/v2/assessments/:id` | Overview · Schedule · Student-wise performance |
| Full schedule | `/v2/schedule` | Month/Week agenda + mini calendar |

Everything else is still v1.

## Manage Assessments — the two views

A segmented control above the table swaps **two separate table components**
(not one table with conditional columns):

- **Schedule-wise** — one row per assessment. Backed by
  `/institutes/assessments/v2/list`, which returns the FULL list; the screen
  filters, counts and paginates client-side because an institute has only
  hundreds of assessments.
- **Student-wise** — one row per *student of the institute*, across every
  assessment they were sent: current active assessments, taken/sent with a
  by-type doughnut, Communication and Aptitude (latest score, delta vs their
  first attempt, sub-section breakdown on hover) and overall progress/level.

**Student-wise is paged and searched in SQL, unlike the rest of v2.** A single
institute already carries 10k students on DEV, so the "fetch everything, filter
in the browser" pattern used elsewhere would ship megabytes and render 10k DOM
rows. `GET /institutes/assessments/v2/students?instituteId&search&limit&offset`
→ `{ students, total, limit, offset }`; the BFF route is
`/v2/api/assessments/students`. Model: `app/models/StudentWiseV2.js`.

Roster definition: the institute's campus students (`students.institute_campus_id`
→ `institutes_campuses.institute_id`) **UNION** every email the institute has
assigned an assessment to. The union matters both ways — a student whose profile
was never campus-linked still appears if something was sent to them, and a fresh
student with no assessments still appears as a real row.

The status tabs are **not** rendered in Student-wise. `.mc-header` is
`justify-content: space-between`, so with the tabs gone the search/Filters group
became the header's only child and got parked on the left (throwing the
right-aligned Filters panel off the card edge); `.mc-header-right:only-child`
carries a `margin-left: auto` to hold it on the trailing edge.

Known gap: the Filters popover is assessment-scoped (Type / Schedule / Dept /
Year, counted over *assessments*) and feeds the Schedule-wise table only, so
selecting values there does nothing to the student rows.

### `statistics` is `jsonb` on DEV but `json` on UAT

`assessment.aptitude_scores.statistics` holds the Aptitude sub-section
breakdown under `.categories`, and the two environments disagree on its column
type. `json->'categories'` yields `json`, so `jsonb_array_elements()` over it
dies with *"function jsonb_array_elements(json) does not exist"* — which passed
every DEV test and then 500'd the whole endpoint on UAT for any institute with a
scored Aptitude attempt. Queries touching this column must cast explicitly:
`jsonb_array_elements((ap.statistics::jsonb)->'categories')`. Assume the same
split for any other json column until checked on both boxes.

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

Two traps worth naming, both hit on 2026-08-10:

- **`node -v` is 16.19.0 over a non-interactive SSH command.** nvm is only
  sourced by a login shell, so `ssh box "npm run build"` fails with *"Node.js
  version >=20.9.0 is required"* while leaving the previous `.next/BUILD_ID` in
  place — so it looks like it worked. Export the path explicitly:
  `export PATH=$HOME/.nvm/versions/node/v20.20.2/bin:$PATH`, and confirm
  `BUILD_ID` actually *changed*.
- **Restart via systemd, never `nohup next start`.** The unit is
  `Restart=always`; a hand-started process grabs the port and leaves
  `systemctl status` stuck in `activating` with `MainPID 0` forever — the app
  serves fine but is unsupervised and will not come back after a reboot.

## Order of operations when flipping a nav entry

v2 must be **up on the target environment before** the v1 nav change ships, or
every click on that entry 404s. Deploy order: `institute-node` → stand up v2 →
verify → flip v1 nav.
