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

The Filters popover (Type / Schedule / Dept / Year) now filters Student-wise
too, as of 2026-08-10 (`c3ce9d8` institute-node, `3fe44d8` frontend). `Schedule`
is hidden in that view — recurring/one-time describes an assessment, not a
student — everything else runs as a real SQL predicate against
`/institutes/assessments/v2/students`, not a client-side re-filter of the
page: the page and its `total` are already server-side, so filtering the
returned rows in the browser would leave the count and paging lying about how
many students actually match.

- `depts` → the student's degree, or degree + one department
- `years` → the student's passing year
- `types` → sent at least one assessment of that type by this institute
  (`EXISTS` against `assessment_assigned_students`, type name compared
  letters-only so the UI's "AI Interview" matches the DB's "AI_Interview"
  without a hand-maintained lookup)

Encoding matches the dashboard's existing cohort params — `depts` a JSON array
of `{deg, sec?}` (degree names can contain commas), `years`/`types`
comma-separated — so both screens read the same query-string shape.

Known gap: the popover's per-option counts are still ASSESSMENT counts (e.g.
"2028 · 6" means 6 assessments), which reads oddly against a student roster,
and a zero-assessment-count option is disabled — hiding a cohort that has
students but no assessment of that shape. Not yet scoped per view.

### `statistics` is `jsonb` on DEV but `json` on UAT

`assessment.aptitude_scores.statistics` holds the Aptitude sub-section
breakdown under `.categories`, and the two environments disagree on its column
type. `json->'categories'` yields `json`, so `jsonb_array_elements()` over it
dies with *"function jsonb_array_elements(json) does not exist"* — which passed
every DEV test and then 500'd the whole endpoint on UAT for any institute with a
scored Aptitude attempt. Queries touching this column must cast explicitly:
`jsonb_array_elements((ap.statistics::jsonb)->'categories')`. Assume the same
split for any other json column until checked on both boxes.

### `LEAST`/`GREATEST` ignore NULL — unscored attempts read as 100%

Fixed 2026-08-11 (`af3fe69` institute-node). The shared score expression in
`app/helpers/assessmentScoreSql.js` clamped with
`GREATEST(0, LEAST(100, COALESCE(...)))`. Postgres' `LEAST`/`GREATEST` **skip
null arguments**, so when no per-type score row existed the COALESCE returned
NULL and the clamp returned **100**, not NULL.

Every attempt still sitting in the calculation queue therefore scored a perfect
100. On UAT a Communication attempt submitted at 12:02 IST showed **100% /
CEFR C2** in the TPO dashboard until the scores landed a few minutes later, and
until then it dragged the cohort's average score, median, avg-top-score,
competency ladder and performance risk bands with it — students who had never
sat the assessment at all also returned `pct = 100`.

`SCORE_EXPR` now guards the COALESCE explicitly (`CASE WHEN <raw> IS NULL THEN
NULL ELSE GREATEST(0, LEAST(100, <raw>)) END`). It is shared by
`AssessmentDetailV2`, `DashboardV2` and `StudentWiseV2`, so all three were
affected and all three are fixed by the one change. **Never clamp a nullable
value with bare `LEAST`/`GREATEST`.**

### `total_time_taken` is 0 on ~⅓ of submitted attempts

The assessment player writes `assessment_assigned_students.total_time_taken`
(seconds) and frequently writes 0 — 276 of 738 submitted attempts on UAT as of
2026-08-11. "Avg time taken" and the per-student time column rendered a dash as
a result.

`TIME_TAKEN_EXPR` (same helper file) falls back to the wall clock between
`assessment_started_at` and `submitted_at`, which tracks the recorded value
closely wherever both exist. It stays NULL when neither source has anything, so
a dash still means *unknown*, not *instant*. The underlying player bug is not
fixed — read models compensate.

### Communication reports speak in four skills, not eight exercises

`communication_scores` holds one row per exercise (Audio Question, Dictation,
Email Writing, Paragraph Reading, Question Based Response, Sentence Build,
Sentence Completion, Video Response). Every report surface — v1's TPO dashboard,
admin-node's PDF, the v2 student column and now the v2 student report drawer —
displays the four language skills instead.

The mapping and the roll-up live in `app/helpers/assessmentBands.js`
(`COMM_SKILLS`, `groupCommSkills()`), imported by both `StudentWiseV2` and
`AssessmentDetailV2` so the two cannot drift on what "Writing" contains:

- **Reading** ← paragraph reading
- **Writing** ← question based response, email writing, dictation, sentence
  completion, sentence build
- **Speaking** ← video response
- **Listening** ← audio question

A skill with no scored member section is omitted rather than shown as zero. Note
v2 averages the *present* member sections, while student-node and admin-node
divide the Writing components by a fixed 4 when computing their weighted
composite — the composite weighting is deliberately not replicated in the
breakdown display.

### The report download is gated on a scored attempt

`GET /institutes/assessments/v2/:id/students/report` returns
`headline.reportAttemptId` — the latest attempt that is submitted **and** scored,
else null. The drawer's download button generates from that id, is disabled
while it is null, and explains why in its tooltip.

Before 2026-08-11 the button was always live and fell back to
`history.at(-1)`, so a TPO could download a PDF for a student who never sat the
assessment (it rendered "not attempted") or for one whose scores had not been
calculated yet. `.iconbtn` also had no `:disabled` style, so a dead action
looked identical to a live one.

Related: `headline.submitted` used to count *scored* attempts rather than
submitted ones, and the drawer's Attempts block listed "Submitted" and
"Attempted" — which for anyone who finished read "1 of 1" twice and implied a
drop-off that never happened. The second row is now **Dropped off** (started,
never submitted), matching the completion funnel's `droppedCount()`.

## Nav wiring (v1 → v2)

Since 2026-08-06 the v1 sidebar routes as follows:

- **Dashboard → `/tpoDashboard`** (stays in v1, the legacy placement analytics)
- **Assessment → `/v2/dashboard`** (the v2 cockpit is the assessment landing
  page; its own sidebar leads on to `/v2/assessments`)

Both live in `institute-react/src/modules/Nav/navItems.js`. Two `accessLevel`
gates in `modules/Nav/index.js` hard-code the v2 path — level 2 gets the entry,
level 1 does not — so they must be updated together with the navItem.

### Going the other way: v2's "Back to ATS"

v2's sidebar has a **Back to ATS** link (`components/shell/Sidebar.tsx`,
`data-v1-bridge`) — a plain same-origin hard nav out of `/v2`, no session
change. It must point at **v1's ROOT (`/`)**, never a fixed page.

"The ATS home" is **access-level dependent, and only v1 knows the level**:

- `routes/Components/AuthPage.js` sends `/` to `/tpoDashboard` for
  `accessLevel` 1 or 3, and to `/students` otherwise.
- `modules/Nav/index.js` drops `/tpoDashboard` from the rail entirely for
  levels 0 and 2 — and level 2 is precisely the level that *gets* the v2
  Assessment entry, so a large share of v2 users have no `/tpoDashboard` in
  their nav at all. For them **`/students` is the correct ATS home.**

So hard-coding either page strands half the users on something outside their
nav. Two wrong targets were tried before landing on `/` (both 2026-08-10):
`/dashboard` — the internal placement/drive view (`modules/Dashboard`, sibling
of `/dashboard/roles/:corpID`), absent from v1's sidebar — and `/tpoDashboard`,
which is right only for levels 1|3. Delegating to `/` keeps one source of truth
in v1 and survives any change to the access rules.

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

## The dashboard must survive a failed BFF call

`/api/dashboard/filters` used to answer its error fallback as **200** with
`{ departments, years }` while the client contract is `{ degrees, years }`.
`useDashboardFilters` only guards on `res.ok`, so it stored that body verbatim,
left `degrees` undefined, and DashboardView's `for (const d of
filterOptions.degrees)` threw **"degrees is not iterable"** — escaping to
`app/global-error.tsx` and rendering a bare, unstyled "Something went wrong"
with no shell. Any institute-node blip therefore blanked the whole screen
instead of showing the cockpit's own "Couldn't load the dashboard / Retry".

Fixed 2026-08-10: the shape lives in `lib/types/dashboard` as
`DashboardFilterOptions` + `EMPTY_FILTER_OPTIONS`, imported by **both** the BFF
and the hook so they cannot drift again, and the hook normalises the response
(`Array.isArray(...) ? ... : []`) so no payload can crash the render.

Telling the two apart when debugging: the cockpit's own failure is styled and
inside the shell; a bare white page with a "Try again" button is the ROOT error
boundary, i.e. something **threw during render** — a 502 alone never does that.

## The cohort filter must reach every block, including the rail

The dashboard toolbar's Degree-Dept / Passing-year selection is applied
**server-side** — `institutes/dashboard/v2/*` take `depts` (JSON array of
`{deg, sec?}`) and `years` (comma-separated), and `DashboardV2.buildCohort`
turns them into one shared SQL predicate so every block agrees.

`useSchedule(from, to, cohort)` takes the cohort as a **`&`-leading** fragment
(it is appended after `from`/`to`), while `cohortQuery()` returns a `?`-leading
standalone query string — hence the `.replace(/^\?/, "&")` at both call sites.

The "This week" rail (`WeekRail`) silently omitted it until 2026-08-11, so the
rail listed every occurrence while the blocks beside it were scoped to one
cohort — the same screen showing two different answers. Verified after the fix:
23 items → 2 on DEV, 26 → 6 on UAT when a passing year is applied. If another
consumer of `useSchedule` appears, pass the cohort.

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
