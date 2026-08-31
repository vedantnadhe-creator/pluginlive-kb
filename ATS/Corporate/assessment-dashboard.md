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
- **AI Interview scores are one row per SESSION** (up to 2 per assignment) —
  pre-aggregate or every count inflates. Its competency breakdown lives in
  `parameter_scores` (jsonb, 0-4 ratings, rescaled ×25) on ~2/3 of rows; the
  four `*_score` columns cover only the rest.
- **Behaviour has no score**, only levels — never in an average.
- **Never resolve a set with `MIN(created_at)`.** Stray assignments spawn sets;
  read the set actually served via `aas.assessment_set_id`.
- `role_name` / `seniority` come from `assessment_sets` at creation and exist
  only for Role Based and AI Interview. They are **not** the ATS `mapped_to`
  link, which is populated on ~2% of production floats.

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

UAT now carries open assessments (288 floats, 9 active as of 2026-08-31), so
the schedule's week view populates. The earlier "Nothing open" state was the
data being stale, not a bug.
