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

## A recurring schedule is invisible until it runs — unless you union it in

The scheduler writes `assessment_institute_map` rows only **when it fires**
(`assessment_schedules.last_run_at`). A schedule created for a future start date
therefore owns **zero occurrences**, and since the v2 list is built entirely
from `assessment_institute_map` it was missing from `/v2/assessments` outright —
while admin (`admin.<env>/assessment`) already listed it as **Upcoming**.

What the TPO saw instead were the **diagnosis** maps that sit alongside it
(`schedule_id` NULL, `is_one_time` false — see below), badged `ONE-TIME`. That
reads exactly like "my recurring assessment is showing as one-time", which is
how it was reported. The two are unrelated rows.

Fixed 2026-08-11 (`2cff4ee` institute-node, `40498dc` frontend). The list
`UNION ALL`s in schedules with no maps yet, straight from
`assessment_schedules`:

| list field | source |
|---|---|
| title | `schedule_name` |
| type | `assessment_type` (values match `assessment_type.type_name`) |
| scheduleType | always `recurring` |
| start / end | `schedule_start_date` / `schedule_end_date` |
| rec `[run, total]` | `[0, jsonb_array_length(frequency_value)]` — the planned run dates |
| assigned | `jsonb_array_length(student_lists.students_data::jsonb)` |

`students_data` needs the **`::jsonb` cast** — json on some environments, jsonb
on others, the same split as `aptitude_scores.statistics`.

Opening one used to 404: `AssessmentDetailV2.getOverview` returns null when
`loadOccurrences` is empty. It now falls back to `loadPendingSchedule`, which
serves the schedule's own plan and sets **`meta.pending`**; the detail view
lands on the **Schedule** tab, since an Overview of zeroed charts says nothing.
An id that is not this institute's schedule still returns null, so unknown ids
404 as before.

Verified on UAT against the schedule behind the report — "Communication -
Schedules", 12–31 Aug 2026, 20 runs, 4 candidates — matching admin's row, and
the row renders `RECURRING · 0/20 · Upcoming` and opens on Schedule.

### An Upcoming schedule still has a cohort to break down

`loadPendingSchedule` (the fallback for a recurring schedule the scheduler has
not fired yet — no `assessment_institute_map` rows) used to return
`departments: []` and `audience: []`, so **Completion analysis · By department**
was blank and the Summary's **Assigned to** read "—" on every Upcoming
assessment. It was reported as "Department wise Completion analysis is not
showing".

It has the data: `assessment.student_lists.students_data` carries each
candidate's degree, department and passing year — the same JSON the scheduler
will hand to the assign call — and the function already read that row to count
the cohort. Since 2026-08-11 it groups it: departments get the cohort size with
`completed: 0`, and audience rows are rebuilt the way the run path builds them.

**Settings come from `assessment_config` before the first run.** The same
fallback hardcoded `proctoring: false` and `sections: []`, so the Schedule tab
reported **Proctoring: Off** on a schedule created with it **On** — on UAT that
was every one of the 32 not-yet-run college schedules, all of which have
`allowProctoring = true`. Once a run exists the value is dynamic
(`Boolean(head.allow_proctoring)` off the occurrence's map); before it there is
no map to read, so `loadPendingSchedule` now reads `allowProctoring` and
`enabledSections` from `assessment_schedules.assessment_config` — what admin
stored at creation and what the scheduler will stamp onto each map. The column
is jsonb everywhere, but the value is parsed defensively: one driver handing
back text should not silently blank the whole panel.

**Roster entries are not one shape.** The scheduler writes objects
(`degree: { degreeName }`, `department: { streamName }`); older and
bulk-uploaded lists write plain strings. `pickName` in `AssessmentDetailV2.js`
accepts either — a shape mismatch should cost one label, not the whole
breakdown.

The frontend had the mirror-image bug: `DeptPie` sized its slices by `completed`
and showed "No completed attempts to break down by department yet" whenever
every department was at zero — i.e. every assessment nobody has sat yet. A pie
of zeros has no geometry, so it now falls back to the **cohort** spread until
the first completion lands, with the cap label naming which of the two is on
screen. The empty state now means only what it says: nobody is assigned.

### Diagnosis maps fold into their schedule (2026-08-11)

`abc15aa`/`589a466` institute-node, `6ab1a89` frontend. Shared helper
`app/helpers/assessmentGrouping.js` holds the grouping so the assessments list
and the dashboard cannot drift — both resolve the same group key.

- Grouping key is **`(institute_id, assessment_type)`** — there is no FK, admin
  deliberately withholds `scheduleId` from diagnosis maps, and this is the same
  key admin uses to find and reuse them. `DISTINCT ON (type)` picks the newest
  schedule when a type has several, so a shared diagnosis map is not counted
  under every one.
- No schedule of that type → the map keeps its own row, badged **`diagnosis`**
  (a third `ScheduleType`) instead of the wrong `one_time`. This matters: 342
  diagnosis maps exist on UAT and many institutes have no matching schedule, so
  folding blindly would have deleted real, student-bearing assessments from the
  UI.
- The detail payload gains **`diagnosis`** — the Schedule tab's first child,
  above the runs. Counted in **UNITS (map x student)**, not distinct students:
  the same 4-student cohort sits on Assessment #1 and #2, which admin reports
  as **8**, not 4. `status` is derived — ongoing until every unit is submitted.

Three traps this hit, all worth remembering:

1. **`GROUP BY akey, schedule_id` splits the group.** A folded group mixes
   diagnosis maps (`schedule_id` NULL) with the series' occurrences, so grouping
   by both produced two rows — one taking its title from a diagnosis map. That
   is why the dashboard showed "Assessment #2" as a live one-time. Group by
   `akey` alone and use `BOOL_OR(schedule_id IS NOT NULL)`.
2. **Join the schedule on the GROUP key, not `schedule_id`.** When the parent
   schedule hasn't run, the group is that schedule but every member has
   `schedule_id` NULL, so joining on `schedule_id` lost the name and window.
3. **A diagnosis map's ~10-year end date swallows the series window**, and its
   presence makes the group exist so the not-yet-run branch must skip it
   (`NOT EXISTS (SELECT 1 FROM occ WHERE occ.akey = sch.id)`) or the schedule
   appears twice. `total_occ` falls back to
   `jsonb_array_length(frequency_value)` so an unrun series still reads 0/20.

**The roster must fold too.** `getStudents` still resolved the group with
`loadOccurrences` alone, so a schedule whose runs hadn't fired had no maps and
the Student-wise performance tab 404'd — "Couldn't load the student roster" —
while the list beside it showed 4 students from the diagnosis maps. It now uses
`loadGroupMaps` (occurrences + folded diagnosis), with diagnosis appended last
so the series' own runs keep the 1..N numbering the trend sparkline depends on.
If another consumer resolves a group, use `loadGroupMaps`, not
`loadOccurrences`.

Verified on UAT for the institute behind the report: the list collapses to one
row (`Communication - Schedules`, Recurring, 0/20, 12–31 Aug, 4 students) and
its Schedule tab opens on **Diagnosis · Ongoing · Assessment #1 1/4 ·
Assessment #2 0/4 · 1/8** — matching admin exactly.

### Superseded: diagnosis maps were badged ONE-TIME

`schedule_id` NULL **and** `is_one_time` false means a **diagnosis** map — the
practice assessment auto-created beside a real send (`StudentListInfo.js`
states this outright; admin's `Assessment.js` deliberately withholds
`scheduleId` from them). They are recognisable by the "Assessment #N" name and a
~10-year window.

v1 excludes them from its list. v2 keeps the ones that have assigned students
(the `EXISTS` branch in the list SQL) and, because `scheduleType` is derived
solely from `schedule_id IS NOT NULL`, badges them **One-time** — contradicting
their own `is_one_time = false`. Platform-wide that is **565 maps** (vs 900
genuinely recurring and 90 genuinely one-time). Unresolved: either hide them
like v1, or badge them "Diagnosis".

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
  (`EXISTS` against `assessment_assigned_students`); the UI sends **display
  labels**, resolved to the DB `type_name` by `dbTypeFor()` — see below

Encoding matches the dashboard's existing cohort params — `depts` a JSON array
of `{deg, sec?}` (degree names can contain commas), `years`/`types`
comma-separated — so both screens read the same query-string shape.

#### The Type filter sends display labels, not DB type names

Fixed 2026-08-11 (`337950c` institute-node, `b61ac1d` frontend). The filter's
options come from the assessments list's own `TYPE_LABEL` map
(`lib/assessments/format.tsx`), so the value that reaches the API is what the
TPO sees on screen. Comparing those letters-only against `type_name` is a
**coincidence** that holds for `Role-based`/`Role_Based` and fails silently
otherwise:

| UI label | letters-only | DB `type_name` | letters-only | matched? |
|---|---|---|---|---|
| Custom | `custom` | `Custom_Assessment` | `customassessment` | **no** |
| AI mock | `aimock` | `AI_Interview` | `aiinterview` | **no** |
| Role-based | `rolebased` | `Role_Based` | `rolebased` | yes |

Filtering by Custom or AI mock therefore returned an **empty roster with no
error**. Verified on UAT institute `1f78e8f3`: `types=Custom` → 0 where
`types=Custom_Assessment` → 20.

`dbTypeFor()` in `StudentWiseV2.js` now resolves a label to its `type_name`
first, via a map derived from `TYPE_LABELS` so a new bucket stays in sync
automatically, plus one explicit alias for **"AI mock"** — the assessments list
labels `AI_Interview` "AI mock" while Student-wise labels the same type
"AI Interview", and both must filter. Unknown values fall through to their own
letters-only form, so `Behavior` / `Hinglish` / `Tech_*` and any type added
later keep working without an entry.

#### Doughnut buckets (`TYPE_KEYS`)

`Aptitude · Communication · AI Interview · Role-based · Custom`. Custom was
added 2026-08-11 — a student sent one saw it counted in taken/sent but absent
from the breakdown, while the list's legend directly above already read
"Custom 1". Colours must be kept in step in **three** places: `TYPE_KEYS` /
`TYPE_LABELS` (institute-node `StudentWiseV2.js`), `AssessmentType`
(`lib/types/studentWise.ts`) and `TYPE_COLORS`
(`assessments/_components/StudentWiseTable.tsx`, matching
`lib/assessments/format.tsx`). Types outside the set still count toward
taken/sent, they just get no slice.

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

**`b1`'s action queue ("Needs attention today") is hidden as of 2026-08-11**, at
the TPO's request while its Alert/Remind/Info rules are re-agreed. It is behind
`SHOW_ACTION_QUEUE` in `NeedsAttention.tsx`, not deleted — the summary payload,
the queue rules and the row rendering are all intact, so restoring it is a
one-word edit. The season KPI cards that share the section stay visible
(`.top-split` is a single-column grid, so they simply move up), and the
section's `aria-label` switches to "Season summary" so assistive tech does not
announce an action list that is not on the page.

Blocks now rendered: `b1` needs-attention (queue hidden) + 3 season KPIs, `b4a` active
assessment schedules, `b4c` student at-risk, `b4d` department distribution,
`b4b` competency, `b6` year-on-year (only with 2+ years of data), plus the
"This week" rail.

### Student at-risk bands only judge windows that have CLOSED

Both at-risk surfaces — the dashboard's `b4c` donut and the assessment detail
page's Overview panel/KPI — used to band attendance on `taken / assigned`. A
student invited an hour ago, window still open, nothing yet possible to miss,
therefore landed in the same band as one who skipped two of three: a freshly
invited college read **"High risk 4 | 100%"** while the performance card beside
it correctly read **0 at risk**.

Since 2026-08-11 attendance is judged only against occurrences whose window has
ended, and there is a fourth, neutral band:

Bands are reported in the platform's **Consistency** vocabulary — the same words
and cutoffs the Student-wise tab's consistency chip already used, so one student
cannot read "Inconsistent" on one screen and "Moderate" on another:

| band | rule | label · sub | colour |
|---|---|---|---|
| `high` | attended ≥80% of what closed | **High Consistency** · ≥80% attended | green |
| `moderate` | attended 60–79% of what closed | **Moderate Consistency** · 60–79% attended | amber |
| `inconsistent` | attended <60% of what closed | **Inconsistent** · <60% attended | red |
| `pending` | nothing closed yet, no attempt | **Yet to attempt** · window still open | neutral |

`pending` carries **no sub-label** — "Yet to attempt" already says it, and the
donut legend omits an empty sub rather than rendering a stray dash.

`pending` is orthogonal to that table rather than a fourth level of it: a student
with no closed window has no attendance percentage at all. Dropping it would put
a just-invited cohort straight back into red, which is the report this whole
thread started from. Sitting a still-open window early counts as `high`.

All four bands share the tracked denominator so the donut sums to 100%. The
at-risk KPI counts the **red** band (`inconsistent`) — under this vocabulary
`high` is the good one, so counting `high` would report the healthiest students
as at risk.

**`high` means opposite things in the two modes** — high RISK (red) on
performance, high CONSISTENCY (green) on attempt rate. The frontend therefore
keys colours per mode (`PERFORMANCE_COLORS` / `CONSISTENCY_COLORS` in
`assessments/[id]/_constants.ts` and `dashboard/_components/StudentAtRisk.tsx`);
the single shared `BAND_COLORS` map it replaced would paint the good band red.
`pending` renders `--color-neutral-300` — without that entry it falls through to
primary blue and reads as a level.

One helper owns this: `app/helpers/assessmentBands.js`
(`attemptBandOf` / `attemptRiskBands`), used by **both** `DashboardV2.js` and
`AssessmentDetailV2.js`, which previously carried two copies of the arithmetic.
`AssessmentDetailV2` also derives each student's `consistency` chip from that
same helper (it used to run its own 80/60 arithmetic over a different
denominator) and sends the band as `attemptBand`, because the
analytics drawer was banding attendance client-side on entirely different
cutoffs (`<40` / `<80`) — clicking a donut slice listed a different population
than the slice counted. The same drawer filtered performance slices with the
donut's key names (`moderate`/`safe`) against the student rows' own
(`medium`/`low`), so that drill-down matched **nothing**; `PERF_BAND_KEY` maps
them.

**The Student-wise tab carried the same premise until 2026-08-11.** Its
per-student `risk` escalated `notStarted && windowOpen && sent > 0` to High
risk, so a candidate invited that morning sat flagged red beside a genuine low
scorer — and diagnosis maps have ~10-year windows, so "still open" is close to
permanent. Risk is a judgement about PERFORMANCE and needs a score or a missed
window to stand on: those rows now return `risk: null`, which the UI already
renders as "—" and counts under the Risk filter's "Not assessed" (`s.risk ?? "na"`).
`absent` — sent, window closed, never sat — stays High risk.

**Gotcha — `assessment_institute_map` has no `is_active` column.** Cancellation
lives on `assessment_schedules`. Reading `aim.is_active` in the window_closed
predicate 500'd the entire Assessment lens with Prisma **P2010 / SQLSTATE
42703**; the fix joins the schedule and reads `COALESCE(sch.is_active, true)`
(a standalone one-time map has no schedule row, hence the default). A cancelled
schedule's runs must never count as missed.

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
