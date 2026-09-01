# Corporate Assessment Dashboard (LIVE on DEV + UAT since 2026-08-27)

The corporate portal's assessment surface: a cockpit dashboard, an assessments
list, a per-assessment detail page and a full schedule, all in
`corporate-react-v2` under `/v2`, backed by ten new read endpoints on
**`corporate-node`** (the v1 API), not `corporate-node-v2`.

| Screen | Route | Feeds from |
|---|---|---|
| Dashboard | `/v2/dashboard` | `dashboard/v2/summary`, `dashboard/v2/assessment`, `dashboard/v2/filters` |
| Assessments | `/v2/assessments` | `assessments/v2/list`, `assessments/v2/candidates` |
| Assessment detail | `/v2/assessments/:id` | `assessments/v2/:id/{overview,candidates,candidates/report}` |
| Schedule | `/v2/schedule` | `dashboard/v2/schedule?from=&to=` |
| Usage widget (top bar) | both primary screens | `assessments/v2/usage` |

All are `GET`, namespaced `/corporates/:corporateId/...`, `isPrivate: true`.

## Why corporate-node and not corporate-node-v2

Corporate assessment data lives in the `assessment` schema, not `corporate`.
`corporate-node-v2` pins `search_path=corporate` and hand-authors its Kysely
types, so cross-schema analytics fight it. `corporate-node` already owns
corporate identity, the corporate JWT and `FeatureAccessService`, and already
reads across schemas (`FeatureAccessService` → `admin.feature_config`,
`JobRoles.js` → `student.education_profile`). The analytical SQL was ported in
from institute-node's TPO Dashboard v2 rather than reused in place.

## The feature gate is accessLevel, not feature_config

`corporate.corporates."accessLevel"` is the switch admin already sets on
**Feature Access → Corporates → ASSMT.** (`admin.<env>/assessmentAccess`):

| accessLevel | ATS | Assessment |
|---|---|---|
| 1 | yes | no |
| 2 | no | yes |
| 3 | yes | yes |

`FeatureAccessService.isAssessmentEnabledForCorporate` reads it and surfaces it
as `ASSESSMENT` on the existing `GET /corporates/:id/feature-access`. **No
`admin.feature_config` row and no schema change** — a second parallel switch
would let an admin turn the menu on for an account with no subscription. Fails
closed on any error.

### The v1 menu item needs BOTH gates, and RBAC had to be bypassed

`src/modules/Nav/navItems.js`'s Assessments entry carries
`requiresFeature: 'ASSESSMENT'` and points at `/v2/dashboard` when
`CORPORATE_V2_ASSESSMENTS_ENABLED === 'true'`.

**`PermittedNavItems` hid it for every corporate, forever.** That check passes
only when the user holds a permission whose `screenName` matches the item's
`navTitle`, and there is **no ASSESSMENTS screen in the CORPORATE journey** —
`admin.screens` has DASHBOARD, ROLES, USERS, REPORTS, SETTINGS, ACTIVITY LOG,
INTERVIEWER DASHBOARD and JOBROLES. Items declaring `requiresFeature` are now
exempt from the screen check (`src/utils/permissionsValidation.js`); their gate
is the subscription. To reintroduce per-user RBAC, add an ASSESSMENTS screen row
and drop `requiresFeature`.

`CORPORATE_V2_ASSESSMENTS_ENABLED` is **deliberately separate from
`CORPORATE_V2_ENABLED`** — one flag governing both is what previously dragged
Roles into v2 by accident. It lives in `.env` / `.env.uat`, which are gitignored,
so it must be set per box or the item falls back to the legacy `/assessments`
screen (the safe direction).

Roles now points back at v1 `/rolePage` on **both** ends — v2's sidebar bridges
to v1 too. Flip one without the other and the two sidebars point at each other.

## Data model traps

- **Corporate windows are IST wall-clock stored as UTC.** Compare against
  `NOW() + INTERVAL '5 hours 30 minutes'`, and emit dates re-tagged `+05:30`
  (`istIsoOf`). `.toISOString()` shifts every date by 5h30m in the UI.
- **A float is one row per type**, tied by `mix_match_group_id`. Identity is
  `COALESCE(mix_match_group_id, assessment_corporate_map_id)`; a one-part group
  keeps its own map id and type. `:id` resolves either form.
- **No `draft` or `cancelled` status exists** — a corporate assessment does not
  exist until floated and cannot be cancelled. Those tabs are removed from the
  list.
- **No schedules, departments, passing years or campuses.** Every float is
  `one_time`; the week rail and schedule key on the **open window**, not the
  start date, or an assessment open all week appears on no day.
- **"Taken" means `submitted OR attempted`** — the same rule admin v1 uses
  (student-node `TpoDashBoard.getAssessmentStatesForCorporate`, which admin's
  corporate drill-down calls, counts `attempted`). v2 counted submitted-only
  until 2026-09-01 and therefore read LOWER than the admin screen for the same
  corporate: meesho/UAT showed 40 against admin's 48, the gap being exactly its
  DROPOUT rows (opened the paper, walked away). One shared `TAKEN_PREDICATE` in
  `helpers/corporateAssessmentSql.js` governs every v2 count.
- **KPI counts are per (float, PART, candidate).** Folding to the float first
  and fanning its types back out credits every candidate with every type on the
  float the moment they submit any one part — that read AI Interview 26 taken
  on DEV where 12 interviews existed, under a headline that disagreed with its
  own tooltip.
- **Duplicate `student_personal_profile` rows fan every profile join out.** The
  same email can hold 2-4 profiles (a duplicate-creation race; four meesho
  candidates do). A plain `LEFT JOIN spp … LEFT JOIN students` therefore
  over-counts: the candidate list reported **75 candidates on a roster of 67**
  and printed those four twice, and the detail roster inflated
  `parts_held`/`parts_submitted` the same way. Join through
  `STUDENT_PROFILE_LATERAL` (helpers/corporateAssessmentSql.js) — newest
  profile, `LIMIT 1`, `LEFT JOIN LATERAL … ON TRUE` so an email with no profile
  is still listed.
- **Score breakdowns are NOT all in the `sections` table.** Communication and
  Role Based write one row per section there; **Custom Assessment** keeps its
  sections in `custom_assessment_scores.section_wise_stats` (jsonb OBJECT keyed
  by section name) and **Aptitude** keeps its categories in
  `aptitude_scores.statistics.categories`. Both were missed by the section
  union, so the report drawer showed "Breakdown unlocks once the attempt is
  scored" on fully scored attempts until 2026-09-01. Three traps when reading
  them: `statistics` is `json` on UAT but `jsonb` on DEV (cast `::jsonb`);
  `jsonb_each`/`jsonb_array_elements` error on the wrong type and a `WHERE`
  guard runs AFTER the lateral, so the type check must sit inside the call; and
  Aptitude uses negative marking, so clamp with a `CASE` — a bare
  `GREATEST(0, LEAST(100, …))` ignores NULL and scores a zero-mark category 100.
- **Custom Assessment and Aptitude carry real per-section weights**
  (`total_marks` per section/category), so their breakdown bars are weighted by
  marks. Every other type gets an equal split, because its scorer's weighting is
  not stored and an invented one would be a guess dressed as fact.
- **AI Interview scores are one row per SESSION** (up to 2 per assignment) —
  pre-aggregate or every count inflates. Its competency breakdown lives in
  `parameter_scores` (jsonb, 0-4 ratings, rescaled ×25) on ~2/3 of rows; the
  four `*_score` columns cover only the rest.
- **Behaviour has no score**, only levels — never in an average.
- **Never resolve a set with `MIN(created_at)`.** Stray assignments spawn sets;
  read the set actually served via `aas.assessment_set_id`.
- `role_name` / `seniority` come from `assessment_sets` at creation and exist
  only for Role Based and AI Interview. They are **not** the ATS `mapped_to`
  link, which is populated on ~2% of production floats. Aptitude and
  Communication carry a **level** instead of a role — Aptitude's `difficulty`
  tier, Communication's `cefr_level` — surfaced as `typeDifficulty`. The detail
  page's "Assigned level" and the Total Candidates card's "Assigned for …" read
  `assignedLevel` first and fall back to that map, so those two types show a
  level rather than a blank; the Role row is dropped entirely when there is no
  role.

## Candidate PDF report

The detail drawer's download serves the **same PDF the admin side does**:
`corporate-node` proxies student-node's `POST /students/assessments/generatePDFReport`.
Proxied, not called from the browser, because that endpoint is unauthenticated
and the tenant guard must run first. It is rendered on demand (~10s), one PDF
per submitted part.

## Tenant scoping

`verifyToken` proves the JWT is signed; it does **not** check that
`:corporateId` is the caller's. `app/helpers/assertCorporateScope.js` does, and
every one of these handlers calls it first (403 on mismatch). Every other
`/corporates/:corporateId/*` route in the service still has that gap — worth a
separate audit.

## Loading states

All three screens (dashboard, assessment-wise, candidate-wise) show **skeleton
loaders**, not text. Two rules make them worth the code:

- The skeleton reuses the **real structural classes** — `.kpi-grid`/`.kpi`,
  `.panel`, `.aa-split`, `.rail` on the dashboard; the real `<table class="ma-tbl
  ma-tbl--assessments">` shell on the lists. Only the content atoms become
  `.skeleton` spans. So the card chrome, the grid and the fixed column widths are
  already final and nothing reflows when data lands.
- `CockpitSkeleton` must carry `data-block="attempt"|"competency"|"yoy"`. That
  attribute is what the rule `.content-col > [data-block=…] { grid-column: span 1 }`
  keys off. Without it those blocks inherit `grid-column: 1 / -1`, render
  full-width, then re-flow into pairs — the exact shift the skeleton exists to
  prevent.

Counts that are not known yet shimmer rather than render `0` (status tabs, type
legend, candidate total, the `Updated` stamp). A `0` and "we have not loaded it"
look identical, and the first claims the corporate has nothing.

Two gotchas found building this:

- `.cal` (the rail's mini calendar) sits on `--bg-surface`, which is **also the
  `.skeleton` base colour** — placeholders inside it vanish into one solid grey
  block. `dashboard.css` steps the ramp up inside `.cal` only.
- The DS `.skeleton-overlay` is `position: absolute` and collapses to a strip
  with no real layout behind it. These skeletons are deliberately **in-flow**
  instead.

## Deploy

- `corporate-node` → `./auto_deploy.sh corporate-node UAT` (docker, container `corporate`).
- `corporate-react-v2` → systemd `:3014`; build **on the box** (`npm run build`),
  then `sudo systemctl restart corporate-react-v2`. Needs `CORPORATE_API_URL`
  in `.env.local` pointing at that env's corporate-node.
- `corporate-react` → `./auto_deploy.sh corporate-react UAT`. **Must be built on
  the UAT box**: env values are inlined at build time, so a DEV-built bundle
  sends UAT users to DEV. Verify with the DEV-URL grep in
  [v2-strangler-fig.md](./v2-strangler-fig.md).
- DB: one expression index, `student.student_personal_profile
  (LOWER(TRIM(primary_email)))` — the join every candidate view makes. 82ms →
  32ms on DEV. Applied DEV + UAT; **PROD pending**. See DB-Scripts
  `Corporate Assessment Dashboard/20260825T173221Z__spp_email_lower_trim_index.sql`.

## Status

DEV and UAT: live. PROD: not deployed, and the index is not applied there.

**2026-09-01 (later)** — the candidate report drawer build-out and the whole
`/v2/reports/*` report-v2 section were **reverted from DEV and UAT** on request
(6 revert commits, tip `43cd239`). Those routes now 404 by design. The work is
preserved in full on branch **`feat/candidate-report-drawer-report-v2`**, which
also carries two later Mix N Match fixes that never reached Development/UAT.
Re-landing it is not a plain merge: git will not reapply a commit the target has
reverted, so merge that branch **and then revert the reverts**.

**2026-09-01** — counts aligned to admin v1 and both missing score breakdowns
shipped (DEV + UAT). Verified against meesho on UAT, which now matches the
admin screen exactly: **11 active / 160 sent / 48 taken / 67 candidates**.
Same release adds the Aptitude + Communication "Assigned level", and promotes
the trimmed sidebar (Dashboard · Assessments · **Back to ATS**) that brings
corporate v2 to parity with the institute TPO shell. Corporate's back link
targets `v1("/dashboard")`, not `v1("/")` like institute: corporate-react's
`AuthRouter.js` redirects `/` to `/signin` unconditionally, so bridging to the
root bounces a signed-in recruiter to the login screen.

UAT now carries open assessments (288 floats, 9 active as of 2026-08-31), so
the schedule's week view populates. The earlier "Nothing open" state was the
data being stale, not a bug.
