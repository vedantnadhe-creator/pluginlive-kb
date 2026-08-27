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

**PROD is different: it runs as a container in K8s**, not systemd — deployment
`institute-react-v2` in the `frontend` namespace, port 3000 behind a ClusterIP
service, mounted at `institute.pluginlive.com/v2` by a `/v2` path on
`institute-react-ingress`. The server-only vars (`INST_API_URL`, `AUTH_API_URL`,
`ADMIN_API_URL`, `CORPORATE_API_URL`, `STUD_API_URL`) resolve over **in-cluster
DNS** and are set on the Deployment as well as in
`repositories/envs/ui/institute-react-v2.env`, because Next reads them at
runtime rather than baking them.

The `Dockerfile`, `.dockerignore` and `output: "standalone"` that make this
possible lived **only on the release branches** until 2026-08-21 — every release
cut from UAT lost them and the prod build failed on a missing Dockerfile. They
are now on `Development`, `UAT` and `release-v1.38` alike. See
[Infrastructure/uat-deploy-traps.md](../../Infrastructure/uat-deploy-traps.md).
A UAT *image* still cannot be built until a UAT env file exists — UAT runs this
app under systemd, so it has never needed one.

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

### "End date" was blank until the series' first run fired

The Schedule tab's **End date** card used to read the LAST occurrence's `end`
(its attempt-window close) — since 2026-08-17 it reads `meta.end`, which since
2026-08-24 is the latest of the minted ends, the projected close of the last
run still to fire, and `schedule_end_date`; see "…and so is the DETAIL page's
Schedule tab" and "…and now the LIST reads the plan too" below for why. The rest of this section still applies. But
`loadPendingSchedule` set every occurrence's `end: null` before the scheduler
had fired a single run, so the card had nothing to read and showed "—" on every
Upcoming series regardless of how far out its real close date was. Same root
cause put "—" on each timeline row too ("12 Aug 2026 — —").

Fixed by projecting `end` on unfired occurrences the same way the scheduler
computes a real map's `end_time` (admin-node `Assessment.js`
`updateAssessmentSchedule`): `start + assessment_validity_days`, end of day.
(Since 2026-08-24 that projection lives in `helpers/assessmentPlan.js` and is
built in IST rather than the container's local time.)
Verified on "Communication - Schedules" (20 daily runs from 12 Aug 2026,
14-day validity) — last occurrence now projects to **14 Sep 2026** instead of
"—".

### Diagnosis maps fold into their schedule (2026-08-11)

> **Superseded on 2026-08-26.** The `(institute_id, assessment_type)` +
> `DISTINCT ON (type)` key described here was an *inference*, and the detail
> page inferred differently — see "Diagnosis ownership is stored, not inferred"
> below for the rule in force now. The three traps below still apply verbatim;
> they are properties of a folded group, not of how the group is resolved.

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
   **This one recurred** — `getSchedule` (the "This week" rail / full Schedule
   page) selected `sch.assessment_validity_days` (joined on `aim.schedule_id`)
   without the `gsch` fallback title/`is_recurring` already use, so every
   diagnosis-folded row's window silently read NULL and the rail's figure slot
   fell through to "N assigned" instead — reported as "add assessment duration
   here" against a recurring Communication series where most visible rows
   *were* its diagnosis baseline. Fixed `2063568` (2026-08-13):
   `COALESCE(sch.assessment_validity_days, gsch.assessment_validity_days)`.
   **Any new field read off `sch` in one of these grouped queries needs the
   same `gsch` fallback, or it will quietly break for every diagnosis-folded
   row** — this is the second time this exact shape of bug has shipped.
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

### Diagnosis ownership is stored, not inferred (2026-08-26)

`c62d619` admin-node, `28666db` + `a18f4d8` institute-node, `3eacaf9`
institute-react-v2, DB-Scripts `20260826T072914Z__aas_is_diagnosis_flag.sql`.

Folding (2026-08-11) had to **guess** which schedule owned a diagnosis map,
because there is no FK to guess from. The dashboard and the detail page guessed
differently, so one schedule reported two sets of numbers:

| Screen | Old rule | On UAT's `acsac` |
|---|---|---|
| Dashboard + Assessments list | `DIAG_PARENT_CTE` — `DISTINCT ON (assessment_type) ORDER BY created_at DESC`, so the **newest** schedule of a type absorbed **every** diagnosis map in the college | 80 units / 36 students / Avg progress **64 (B1)** |
| Detail page (all 3 tabs) | `DIAG_OWNER_CTE` — re-derived the owner by matching each map's assigned students against every schedule's roster | 6 units / 1 student / **18.30 (A1)** |

`acsac` was merely the newest of that institute's 38 Communication schedules,
so it inherited 76 foreign diagnosis maps and reported the cohort average of
nine *other* schedules' students. `DIAG_OWNER_CTE` was right but expanded every
roster in the institute on every call — **19.5s** on PROD's largest.

**Both are gone.** `assessment.assessment_assigned_students.is_diagnosis`
(`NOT NULL DEFAULT false`, partial index `ix_aas_diagnosis` on
`(lower(btrim(primary_email)), is_diagnosis) WHERE is_diagnosis`) now stores the
fact at write time, and membership is an indexed join.

**The rule, evaluated identically on every screen:** a diagnosis belongs to the
**student**, so a schedule shows **the diagnosis attempts of its own students,
of its own type**.

- `MEMBER_CTE` in `app/helpers/assessmentGrouping.js` replaces both old CTEs and
  is consumed by `DashboardV2`, `AssessmentV2`, `AssessmentDetailV2` and
  `StudentWiseV2` — one definition, so the screens cannot drift again.
- **Membership is per ATTEMPT (`assessment_assigned_id`), not per map.** It has
  to be: one diagnosis map can carry students belonging to different schedules
  (the largest on UAT carries 1,000), so the map cannot be attributed as a unit.
- **A student in N schedules of a type contributes their diagnosis to all N.**
  That is the rule working, not a bug — but it means an institute-wide total
  must count **DISTINCT attempts**, never a sum of per-group subtotals
  (`getSummary` in `DashboardV2.js`).
- **An orphan diagnosis still lists.** A student in no schedule of that type (a
  manual send) keeps their map's own id as the group key, so the map heads its
  own row instead of vanishing. `folded_diag` / `LISTABLE` excludes only maps
  that *found* a home, so nothing is listed twice.
- `sched_roster` is built from the schedule's **own assigned students**, not
  `student_lists.students_data` — the planned roster can name students who were
  never assigned, and it is that jsonb expansion that cost the old owner
  inference 19.5s.

**Gotchas worth keeping:**

- **Deploy order is not optional: admin-node before institute-node.** Diagnosis
  created in the gap would be written `is_diagnosis = false` and disappear from
  every institute screen. Honoured on DEV and UAT.
- **`assessment_institute_map.schedule_id` is still deliberately NULL on
  diagnosis maps.** Stamping it would flip student-node's own
  `is_diagnosis: !assessmentInstituteMap?.scheduleId`
  (`student-node/app/models/Assessment.js:1676`) and drop the pair out of the
  student's assessment list. That contract is untouched; the flag is a side
  fact, not a replacement for it.
- The flag also retires the *three* different derivations that used to exist —
  institute-node's `schedule_id IS NULL AND NOT is_one_time AND type IN
  (comm, aptitude)`, student-node's `!assessmentInstituteMap.scheduleId`, and
  the student app's `"Assessment #N"` title match.

**Backfill reproduces the old derivation exactly, so nothing moved on landing
day:** DEV 3,777 / 27,790 rows flagged, UAT 4,117 / 21,314 — **0 mismatches**
against the old predicate on both. PROD pending.

Verified on UAT after deploy: `acsac` now reports **6 units / 1 student / 2
diagnosis units** on every screen (the detail page's figure, not the dashboard's
80), and the institute invariant holds — **302 distinct attempts in `member` ==
302 non-practice assignments**, nothing double-counted and nothing dropped.
`test/assessmentGrouping.spec.js` (7 cases) pins the rule.

#### The other half: an orphan diagnosis is not a schedule (same day)

`eb7e267` institute-node, `c13d746` institute-react-v2.

Refusing the wrong parent left the orphans with nowhere to go, so they began
heading rows of their own **on the cockpit** — where the old
`DIAG_PARENT_CTE` had been hiding them by gluing them onto the newest schedule.
On UAT institute `1f78e8f3` the "Active Assessment Schedules" panel showed
**53 active rows where only 7 are real schedules**: 46 single-student
`Assessment #1` / `Assessment #2` rows at 0%, each also filing its own "needs
attention" chip. They were badged **ONE-TIME**, because `DashboardV2` emits only
`recurring | one_time` and has no word for a diagnosis.

New shared predicate **`IS_DIAGNOSIS_MAP`** in `assessmentGrouping.js`, applied
to **both** dashboard row-heading sites — `getAssessmentBlocks` (the panel) and
`getSummary` (the "Active assessments" KPI + action queue). **Both, or neither:**
patching one alone puts the KPI card back in disagreement with the panel
directly beneath it, which is a self-contradiction the cockpit has already been
fixed for once.

- **Safe by construction, verified on UAT:** 0 maps carrying a `schedule_id`
  hold any diagnosis attempt, and 0 maps mix diagnosis with ordinary rows — so
  the predicate can never drop a real schedule. A diagnosis that found a home is
  already excluded by `LISTABLE`, so among listable maps this matches exactly
  the orphans.
- **KPI totals are unaffected:** "Assessments sent / taken" comes from
  `totalsSql`, which is built on `member`, not on `occ`.
- **`getSchedule` (week rail) is deliberately untouched** — it is a calendar, it
  already renders diagnosis as its own `kind`, and an orphan diagnosis is a real
  dated event.
- **The assessments list is deliberately untouched** — it is an inventory, and
  hiding them there would delete real student-bearing assessments from the UI
  (the original 2026-08-11 concern). Instead the **Schedule filter gained a
  `Diagnosis` option** (`_constants.ts` `SCHEDULE_OPTIONS`): the rows already
  badged themselves "Diagnosis" but could be neither selected nor excluded.
  `valueLabel` in `lib/assessments/filters.ts` had to lose its
  recurring/else ternary too, or the applied-filter chip read "One-time" over
  rows badged "Diagnosis".

Verified live on UAT after deploy, institute `1f78e8f3`: the cockpit returns
**7 rows, 0 titled `Assessment #N`** (was 53), while the assessments list still
returns all **236** — `{one_time: 124, diagnosis: 55, recurring: 57}` — with the
55 now filterable. Spec is 9 cases, one of which pins that the LIST does *not*
get the exclusion.

#### The Progress trend: baseline first, and on the ladder scale (2026-08-26)

`d0e0949` institute-node, `d14c5c7` institute-react-v2.

The Overview contradicted itself on UAT's `acsac`: **Average progress 18.30**
sat beside a Progress trend reading *"A trend appears once attempts across runs
are scored."* Both were right, about different populations — all four of the
series' own runs have **0 attempts**, and the 18.30 **was the diagnosis**, which
the trend did not plot. The Completion rate trend beside it has always drawn the
baseline as its first point (`CompletionAnalysis.tsx` prepends a `"D"` point).

It was also **the one screen the NPS sweep (`3eacaf9`) missed**. It plotted
`occurrences[].avgScore`, a RAW PERCENT, under a card named for a progress
score. For `acsac` the pair averages **35.05%** raw against **18.30** curved —
the same "53 here, 21 there" mismatch that commit existed to kill.

Both fixed:

- `occurrences[]` gain **`progressScore`** — the page's scale, curved once at
  presentation. `avgScore` stays a raw percent for anything that wants one.
- `diagnosis` gains **`progressScore`** and **`avgScore`**, averaged **across
  both maps** and curved once. Per-map scoring would be wrong twice over: the
  first paper of a Communication pair carries **no NPS until its partner lands**,
  so a per-map point plots a null and half a baseline instead of the real
  starting rung. (`acsac`: #1 raw 15.96 / no NPS, #2 raw 54.13 / linear 8.56 A1
  → curved **18.30**, byte-identical to the KPI.)
- `meanOf` / `present` are **hoisted** in `getOverview` so the trend, the
  baseline and the KPI cards pass through ONE presentation — npsScale.js THE ONE
  RULE (aggregate linear, curve last, curve once) is now applied in one place on
  this page instead of three.

**The fallback, and why it is not optional.** NPS coverage is **partial** — on
UAT, of submitted attempts: Aptitude runs **51.8%**, Aptitude diagnosis 86.1%,
Communication runs **55.2%**, Communication diagnosis 40.3% (low because
first-of-pair never has one). So both scales are collected per map, and a ladder
series holding scores but **no progression rows anywhere** keeps the raw-percent
trend it has always drawn. Verified on DEV: `e40b0d01` has 9 scored runs and
zero NPS — without the fallback its chart would have gone **blank**, trading one
empty-state complaint for a worse one. The fallback is **all-or-nothing per
series**; the two scales are never mixed inside one chart.

Verified live on UAT: `acsac` returns `kpis.avgScore 18.3` and
`diagnosis.progressScore 18.3` (raw would have been 35.05), so the trend now
draws its baseline instead of an empty state. On DEV `3fbb2b11` plots
baseline 2.91 → runs 4.71, 1.91, and its latest point equals `kpis.avgScore`
exactly.

**`ScheduleTab`'s diagnosis row deliberately carries `progressScore: null`** —
that row reports attendance, not attainment, and never showed a score.

**Trap for next time:** `institute-node` has a **dead** `getAssessmentsList`
(pagination, `scheduleType` filter, `SCHEDULE_TYPES = ["recurring","one_time"]`).
The `/institutes/assessments/v2/list` route calls **`getAssessmentsFull`**
instead, and all list filtering is **client-side**. Do not "fix" the filter in
that model — nothing calls it.

**Known inconsistency, not yet consolidated:** `AssessmentV2.js` and
`DashboardV2.js` (`getSchedule`) still carry their own inline copies of the
diagnosis-map EXISTS, and those copies **omit `is_practice = false`**. Harmless
today (0 practice rows are flagged `is_diagnosis`), but if one ever appears
those screens would classify it differently from the cockpit — the same
two-screens-disagree shape this whole entry is about. Fold them onto
`IS_DIAGNOSIS_MAP` when next in the file.

### Counting: assessments, not people (2026-08-12)

`5fa5787` `0f64d52` institute-node, `2889378` `06a49ae` frontend. Three screens
each reported "sent / taken" as a headcount and disagreed with one another.
The rule now, everywhere: **one `assessment_assigned_students` row is one
assessment sent**, and `taken` counts a started-but-unsubmitted attempt, which
is what v1's `assessmentsTaken` does.

- **Assessments list · Completion** counted students who had attempted at
  least once, so a 46-run series read 90% eight runs in. Now `units_taken /
  units_sent` — 52% (430/820) for the PROD row that read 89%.
- **Dashboard · Assessments sent / taken** summed each assessment's DISTINCT
  STUDENT count *across assessments*, which is neither figure: a student in
  five assessments counted five times, and a 78-run series counted once per
  student rather than 78. Swadha Foundation read **684** against **10,089**
  actually sent. That is also why the card never matched the table under it.
- **Dashboard · Active Assessment Schedules completion** moved with it, so the
  rows sum toward the card. The headcount survives on the cell's hover.

Expect percentages to FALL wherever a long series runs (Swadha 79% → ~24%).
That is the honest number; the old one measured "students who ever showed up".

**The dashboard column was deleted by accident on 2026-08-13 and restored on
2026-08-17** (`92d413f`). `44fc75b` — "align dropdown behavior with design
system" — touched five files; four were genuine dropdown work and the fifth
stripped the `<th>` and the whole `<td>` (mini bar, percentage, `taken / sent`
sub-line) out of `ActiveAssessments.tsx`. Nothing in that commit's subject
relates to this table.

The tell that a UI element was dropped rather than retired: the CSS survives
with nothing to style. `dashboard.css` still carried `.ar-tbl .comp`,
`.mini-bar` and `.a-sub`, the `ActiveAssessment` type still declared
`completionPct` / `unitsTaken` / `unitsSent` / `completed` / `assigned`, and
institute-node still returned every one of them — so nothing but the markup had
been removed. Restoring was a straight revert of that file's hunk, and the
result is byte-identical to `44fc75b^` because that commit was the last to
touch the file. **Check `git log -S"<label>" -- <file>` before rebuilding a
"missing" column from scratch.**

### A series is described by its schedule, not by what has fired (2026-08-12)

`5fa5787` institute-node. The scheduler writes an `assessment_institute_map`
per run *as it fires*, and every figure on the list row was derived from those
rows alone — so a 46-run series eight runs in looked like a finished 8-run
series that closed on run 8.

  end_time   `GREATEST(schedule_end_date, last occurrence end)`. GREATEST, not
             the schedule date alone: the final run's attempt window
             legitimately closes after `schedule_end_date`. NULLs are ignored
             by GREATEST, so one-time and diagnosis groups fall through to
             their own maps. Since 2026-08-24 the projected close of the last
             PLANNED run is folded in on top of this, in JS — see "…and now the
             LIST reads the plan too" below.
  total_occ  `GREATEST(fired, planned)` — 8 fired of 46 read "8/8 sent", which
             contradicts an end date eight months out.

PROD's two 46-run series at `fed210db` read *30 May 2026 → 11 Aug 2026,
Expired, 9/9*; they run to **30 Apr 2027**. v1's `getschedulesInfo` reports
`endDate 2027-04-30` and 46 runs for the same schedules, which is the check to
use if this ever looks wrong again.

Also `e236443`: an assessment **nobody was ever assigned** is dropped from the
list and therefore from every count on the screen (they are all derived
client-side from that one payload). Exactly two exist on PROD, both at
`9c6c42d5`, both reading "0 students · 0/0 · 0%".

### …and so is the DETAIL page's Schedule tab (2026-08-17)

`a0bae26` institute-node, `3ea00ea` institute-react-v2. The correction above
was made on the **list** only. The detail page kept deriving its Schedule tab
from the minted `assessment_institute_map` rows, so PROD's `80ac6fb1` Aptitude
series — **45 planned runs to 30 Apr 2027**, nine minted — read *Total
scheduled 9 · Current schedule 9/9 · 0 still to run · End date 11 Aug 2026*.

`AssessmentDetailV2.loadPlannedRuns` now reads the rest of the plan off
`assessment_schedules.frequency_value` and appends it to `occurrences` as
**projected** upcoming runs, dated by the same `projectedRunEnd` (start +
`assessment_validity_days`, end of day) the scheduler uses for a real map:

- **Matched on the IST day**, not the instant. One series carries both
  `18:31Z` (IST midnight, older runs) and `00:01Z` (newer) start times, so
  only the day a run lands on is comparable to a bare plan date.
- **Only runs after the last one that fired AND not already past.** A plan
  date the scheduler passed over is never going to run; DEV has several
  stalled series (76 planned, 51 minted, plan ended April) that would
  otherwise sprout dozens of "upcoming" runs dated months ago.
- **Skipped entirely when the schedule is inactive** — a cancelled series has
  no runs ahead of it whatever its plan still says.
- **Projected runs are excluded from the unit totals.** They have assigned
  nobody, and counting their target cohort would sink the completion KPI by
  the length of the plan.
- `meta.end` folds in `schedule_end_date` (same `GREATEST` semantics as the
  list), and the frontend's End date card reads `meta.end` rather than the
  last occurrence's `end`.

The two Overview trends (`ProgressTrend`, `ScheduleWiseTrend`) plot **minted
runs only** — ~45 empty future points squeezed the runs that had happened into
the left fifth of the axis.

Verified on UAT `0cc47667` (Communication - Schedules): 6 minted + 14
projected = 20, `cycle [6,20]`, status **live**, completion still `0/24` units
off the minted runs alone.

### …and now the LIST reads the plan too (2026-08-24)

`1e19f0a` institute-node. The two corrections above were made separately, and
they left the list and the detail page dating the same series differently:

  list    GREATEST(schedule_end_date, last MINTED occurrence end)
  detail  latest(minted ends, PROJECTED planned-run ends, schedule_end_date)

PROD's `41824d34` **Communication - Staff** (weekly, 14-day windows, 25 of 26
runs minted) therefore read *7 Mar 2026 → 6 Sept 2026* on the list and
*7 Mar 2026 → 12 Sept 2026* inside. The list was right about the last run that
had FIRED (opened 22 Aug, closes 5 Sept) and wrong about the series: run 26 is
planned for 29 Aug and its attempt window closes 12 Sept. Because the list chip
is derived from that same date, every live recurring series also flipped
**Ongoing → Expired** up to one attempt window early.

`app/helpers/assessmentPlan.js` now owns the projection for both screens:

  projectedRunEnd(start, validityDays)   start's IST day + validityDays, 23:59 IST
  plannedSeriesEnd({planDates, ...})     close of the LAST run still to fire, or null
  latestDate(values)                     max, ignoring nulls

`plannedSeriesEnd` keeps the same "still to run" rule the Schedule tab already
applied — after the last run that fired, not already past, nothing at all for
an inactive series — so a stalled plan cannot claim a future end date.
`AssessmentV2.getAssessmentsFull` reads `frequency_value` per institute in one
extra query and folds the result into both `end` and `status`;
`loadPendingSchedule` got the same close, because its summary card showed
`schedule_end_date` while its own timeline already ran past it.

**`projectedRunEnd` used to read the container clock.** It built the close with
local `setHours(23,59,59)`, so the same schedule projected one day later on
DEV/UAT (containers on UTC) than on PROD (IST). It is now built explicitly in
IST via `Date.UTC(...) - 5.5h`, which is also the frame a TPO reads the date
in. Note this is the *plan's* frame — minted maps written by the newer
scheduler still carry `00:01Z`/`23:59Z` (see [[Assessment/schedule.md]] on the
IST wall-clock storage), so a projected run's date shifts by a day once it
actually fires. That is the scheduler's storage bug, not this projection's.

Verified by comparing `getAssessmentsFull` against `getOverview` for every
assessment of several institutes: **DEV 185 compared, 2 mismatched → 0**;
**UAT 308 compared, 0 mismatched**. That comparison is the check to use if the
two screens ever disagree on a date again.

### Achieved Level is the graded level, not a score band (2026-08-12)

`57e317b` institute-node. The column never read `resulting_cefr`. It
re-derived a level from the AVERAGE SCORE through the CEFR ladder, so a
student averaging 76.87% printed **C1** while every attempt they submitted was
graded **B2**. The ladder is a difficulty scale over a percentage; it is not a
progression level and must not be shown as one.

`levelOf(ladder, cefr, pct)` in `assessmentBands.js` reports the graded level
when there is one and falls back to the band only when there is not, so
Aptitude and Role_Based — which have no CEFR — are untouched. It takes the
most recent **graded** attempt, not the most recent attempt: not every
submission is graded, and a student whose final sitting is ungraded must not
lose the level they hold. Levels get LOWER for graded students; that is the
correction, not a regression.

The report drawer had the same bug plus its own: it read `cefr` off `profile`,
which is picked for the student's NAME and lands on an arbitrary occurrence,
so `student.cefr` came back null even for students who hold a grade.

### Proctoring is usually absent, and that is the data (2026-08-12)

Measured before changing anything, and worth re-measuring before anyone
"fixes" this again: the earliest proctored submission platform-wide is
**2026-07-01**. For `fed210db` — May 226 submissions / **0** reports, June 380
/ **0**, July 258 / **258**. Reading only the latest attempt hides **nothing**
(0 of 1503 student-series pairs on PROD), so there is no verdict to recover
for anything older; the pipeline simply was not filing them.

The roster therefore also returns `proctored` (was the run set to proctor at
all), and the drawer says **"No report"** vs **"Not proctored"** instead of one
ambiguous dash. Deliberately not "Awaiting review" — for a May attempt nothing
is coming.

### The hover cards had CSS but no driver (2026-08-12)

`3e398c0` frontend. `assessment-detail.css` and `manage-assessments.css` have
carried the full `.tt` atom from the start — card, caret, `--tt-arrow-x`,
`data-flip`, `.tt-proc` — with a comment reading *"JS reads the target's
`data-tip` and positions this pill next to the trigger"*. **That JS was never
ported.** Every hover card in v2 rendered nothing: the Score breakdown, the
proctoring card, the list's completion bar.

`Tip.tsx` is that missing half — portalled, `position: fixed` so the drawer's
scroll container and the table's `overflow:auto` cannot clip it, flips
above/below, closes on scroll/resize/Escape, works on keyboard focus. It takes
ReactNode rather than the design's `data-tip` HTML string, because that string
would mean injecting student names and emails as HTML.

Alongside it: Communication's score breakdown reports the **four language
skills** rather than the eight raw exercises it is stored as — which also
repaired the Student-wise tab's expandable columns, since
`SCORE_SUB_CATEGORIES` already expected exactly
`["Speaking","Listening","Reading","Writing"]` and had been matching against
exercise names, showing "—" for everyone.

`sentAt` is per student now (the merged Diagnosis row spans several maps and
has no single window, so Sent read "—" for every row), and the drawer sorts on
Sent/Taken and on Score — rows with no value sink to the bottom in BOTH
directions, since an unscored student is "no result yet", not a zero.

### Progress trend shows improvement only (2026-08-11)

`8b6dfa3` frontend. The Student-wise table's **Progress trend** column drew a
red sparkline and a negative delta for any student whose score had gone
backwards. Product decision: the column reports improvement and stays silent
otherwise — a declining student now renders the same neutral `—` as one
without enough history (`Sparkline.tsx`, `(delta ?? 0) < 0`).

Deliberate boundaries, so nobody "restores" the wrong thing later:

- `trendDelta` in the payload is **unchanged**. Sorting by Progress trend still
  orders on the real figure, and no student leaves the table — the row, score
  and risk band are all still there. Only the cell is suppressed.
- The column is **not** re-coloured to claim improvement that didn't happen.
  Hiding a decline is a product call; reporting it as a gain would be false.

With nothing red reachable, the two-colour branch and the `.spark-delta.down`
variant were deleted rather than left as dead code — `down` no longer appears
in the shipped bundle, which is the quickest way to verify a deploy took.

### One merged Diagnosis row, matching v1 (2026-08-11)

`fd520a2` institute-node, `977aa5c` frontend. The Schedule tab rendered a
`DIAGNOSIS ASSESSMENTS` sub-header plus one row per map (`Assessment #1`,
`#2`). **Production v1 shows one row.** Read the legacy payload before
changing this — diagnosis is *not* in `assessmentDetails` at all:

```
GET /institutes/studentListInfo/getschedulesInfo?entityType=college&instituteId=…&type_name=Communication
  totalCandidates: 6,  totalListCandidates: 6,
  diagnosisCompleted: 6,        <- distinct STUDENTS
  totalDiagnosisTaken: 12,      <- UNITS (6 × 2)
  diagnosisStatus: "Completed",
  assessmentDetails: [ {attemptNumber:1, assigned:6, taken:2}, … ]   <- runs only
```

`ExpandableContent.js` synthesises the row from those three scalars —
`totalDiagnosisTaken / (totalListCandidates × 2)` = **12 / 12**, no date, no
children — and `assessmentDetails` supplies `Schedule 1  2/6`, `Schedule 2
4/6`. v2 now renders the same shape.

The count stays in **units**, which is why 6 candidates read 12; a trailing
`6 students × 2` explains it. Derive that from `sent / students`, **not**
`maps.length` — a group can hold four maps that each student sat only two of
(real DEV case: 99 students, 4 maps, 198 units), and it stays silent when the
division isn't exact rather than rounding.

Two API changes this needed:

- `loadDiagnosis` returns `students` / `studentsDone` (distinct people) beside
  `sent` / `taken` (units) — the same split v1 carries as `diagnosisCompleted`
  beside `totalDiagnosisTaken`. The drawer lists one row per person, so without
  it the header read "Showing 6 of 12 assigned".
- `getStudents` accepts a **comma-separated** `occurrence`, so the merged row
  opens the union of its maps. A single id behaves exactly as before.

### The detail page scopes diagnosis by cohort, not by type (2026-08-11)

`f81cf64` institute-node. The section above describes the **list's** grouping,
which is `DISTINCT ON (assessment_type)` by construction. The assessment
**detail page** inherited that key and it is wrong there: a college with several
recurring assessments of one type has one diagnosis pair *per send*, and keying
on type alone showed **all of them on every series**. On UAT, "Prabhakar Apt
Testing Medium Diff" listed ~16 `Assessment #1/#2` rows spanning 29 Jun – 11 Aug
— seven other aptitude series' baselines — and the units headline counted them
all (`8 / 32`).

`DIAG_OWNER_CTE` in `assessmentGrouping.js` recovers the missing link. There is
still no FK, so the **cohort is the evidence**: admin creates the diagnosis pair
in the same operation as the send and assigns it the send's students, so a map
belongs to the schedule whose `student_lists.students_data` roster its assigned
students came from. Ties (the same cohort re-sent) break on creation proximity —
`ABS(schedule.created_at − map.start_time)`, since a map's `start_time` is
midnight of the day it was created. `loadDiagnosis` (the panel) and
`loadGroupMaps` (the roster) both join through it.

Conservation is the invariant to check: across DEV's 61 college
Communication/Aptitude schedules, rendered diagnosis rows went **1902 → 545**,
and 545 is exactly the number of diagnosis maps that carry students — every map
appears under exactly one series, none lost. The UAT college above holds 14
aptitude diagnosis maps and its 7 schedules now show 2 each.

Two things this deliberately does **not** do:

- **A map matching no roster is attributed to nothing** and shows on no series.
  Guessing a parent is what this replaces.
- **One owner per map, not many.** Attributing a map to every schedule whose
  roster it matches would keep the panel alive when admin *reuses* an existing
  pair for a re-sent student (1 of 61 DEV schedules loses its panel this way),
  but it collapses straight back into the original bug when a TPO sends to the
  same full student list every month — the normal usage pattern.

Still on the old key: the **assessments list and dashboard** (`DIAG_PARENT_CTE`
/ `GROUP_KEY`), so the newest series of a type still counts every diagnosis map
of that type in its list row. Same helper can be swapped in there.

The durable fix is a real `parent_schedule_id` on `assessment_institute_map`,
written by admin-node when it creates the pair, backfilled with the rule above —
at which point the whole inference can be deleted.

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

#### Switching view clears search and filters (2026-08-17)

`80bf3e8` frontend. The two views share **one** search box and **one** Filters
popover, but not their meaning: Schedule-wise searches assessment *titles* in
the already-loaded list, Student-wise searches *names and emails* server-side
against a different resource. Carrying a query across the toggle asked "which
students are named Aptitude" and showed an empty table with nothing to explain
it. Filters had the mirror problem — the popover hides fields the target view
does not offer (`schedule`), so a condition could outlive the switch with its
chip no longer on screen.

`AssessmentsView.changeView` calls `clearAll()` and then switches, **only when
the view actually changes** — re-clicking the tab you are already on must not
wipe work in progress.

`clearAll()` also resets `debounced`, not just `search`. Student-wise queries
the server on the debounced value, so leaving it set for the remaining 200ms
fired one request for the search being abandoned, with a flash of the wrong
rows before the real query landed.

The **status tabs are deliberately not reset** — they are a separate control,
exist only in Schedule-wise, and are visibly highlighted when you return, so
the current selection explains itself.

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
`b4b` competency, `b6` year-on-year (renders from ONE year — it states how much
history it has rather than vanishing), plus the
"This week" rail.

### `b6` year-on-year is per type, one series at a time

The panel used to plot a single mean across every assessment type, labelled
`/100`. That averaged a Communication progress score against an Aptitude one
against a Role_Based percentage — scales that mean different things.

`getYoy` now returns **one series per type**, longest-history-first, each with
its own `unit` and `isProgressScore`. The panel shows **one at a time** behind a
type tab strip, reusing the `.ar-typebar` control from `b4b` directly above it.

The first attempt at this rendered a card per type. Do not go back to it: three
cards in a panel sized for one collapse each chart to a third of the width,
where the line is a smudge and the axis labels are unreadable, and three copies
of the same footnote fill the rest. The `[data-block="b6"]` CSS is written for a
single full-width card (`flex: 1 1 0`, `min-height: 200px` on the chart).

The "N-year" chip reads the SELECTED series, not `series[0]` — they differ.

See `Assessment/nps-scale-and-curve.md` for the scale rules.

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

As of 2026-08-12 (`120fff9` Development, `0efa419` UAT), the dashboard's
Performance and Attempt-rate populations are restricted to the institute's
**current, non-deleted student roster** through student → campus → institute
membership. Assessment assignment rows are historical and survive student
deletion or campus moves; using their distinct emails directly made the donut
larger than Student-wise (Swadha Foundation showed 180 tracked against 177
students). Attempt rate now uses the current roster members who have assessment
history, and Performance is the scored subset of that same population. The
historical Assessments-sent/taken KPIs deliberately retain assignment history.

### The cohort filters had to join that roster too (2026-08-26)

Fixed 2026-08-26 (`038b99c` Development, `7f19eb6` UAT). The same roster rule
now governs the cockpit topbar's **Degree-Dept / Passing-year** filters, which
were still resolving an assessed email to a student profile **platform-wide**.
Assessment rows key on `institute_id` and carry only an email, so that lookup
answers with whichever college the person actually belongs to — and an
institute that assesses outsiders inherits that college's degree, department
and passing year.

Swadha Foundation was offered a **2024 Passing-year pill it has no batch for**:
one invitee of 181 belongs to a different college and carries placeholder
course dates (1 Jan 2023 -> 1 Jan 2024 on a three-year B.Com). 12 of Swadha's
181 assessed emails resolve off-roster; the other 11 happen to be 2026, so only
this one surfaced as a phantom year. The roster-scoped screens — student-node's
`GET /students/institutes/:campusId/yearOfPassing`, which the v1 Placement page
reads — only ever showed 2026 and 2027.

`app/helpers/cohortSql.js` now exports **`rosterScopeJoin(studentAlias,
campusAlias)`**, the join the risk block above already applied
(`institute.institutes_campuses` by `institute_id = $1`, minus deleted
students). `DashboardV2` applies it at BOTH filter sites, which have to agree
or the pills disagree with the rows behind them:

- `getFilterOptions` — which years/degrees are **offered**
- `buildCohort` — which students a chosen year **keeps**

Swadha's pills go from `2027·100 / 2026·78 / 2024·1` to `2027·100 / 2026·69`.
Checked across every institute with >20 assessed candidates: none loses its
filters.

The two per-assessment `audienceSql` blocks ("Assigned to") are deliberately
left unscoped — they describe who an assessment was **sent** to, and scoping
them would silently shrink sent counts. They inherit the fix whenever a filter
is applied.

Side effect: `buildCohort`'s subquery previously carried no institute predicate
at all and parallel-seq-scanned `current_course` on every filtered query. On
PROD data that subquery goes **21.1ms -> 2.16ms**, now index-driven from
`idx_ic_institute_id` -> `idx_students_institute_campus_id`.

The underlying record is untouched: that student's course still reads 2024. The
fix stops it leaking into a college it does not belong to.

### Competency axes cannot be summed into a headcount

Fixed 2026-08-13 (`f729856` Development, `fa3a4e7` UAT; frontend `7042ee1`).
The `b4b` **Distribution by Competency** radar carries one axis per assessment
type, and each axis's `students` is the count of DISTINCT students with a
scored attempt of that type. The "All types" caption added those three numbers
together, which counts anyone assessed on two types twice — Swadha Foundation
read **312 students** against a roster of 177.

`buildCompetency` now also returns `competency.students`: one count per student
with at least one scored attempt, so it equals `risk.totalAssessed` by
construction and the two cards on the same screen finally agree. Verified on
DEV — an institute whose axes sum to 39 has 23 distinct students.

The per-type ladders are unaffected: a ladder's rows partition that one type's
students, so those DO sum. The frontend hides the caption when `students` is
absent rather than falling back to the old sum, so an older institute-node
shows no figure instead of a wrong one — deploy the API first or together.

The radar's number is the cohort's **mean score, 0–100**, on that type (the
mean of each student's per-type average). The tooltip used to print a bare
`Current 45`; it reads `Avg. score 45/100` with a matching legend, because the
panel is titled "competency" and an unlabelled 45 reads as a level.

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

### "Active" had two definitions on the same screen

The season KPI card and the Active Assessment Schedules panel are served by
different methods of `DashboardV2.js`, and they disagreed about the word:

| surface | rule |
|---|---|
| KPI card (`getSummary`) | `is_active AND start <= now AND end >= now` |
| Panel (`getAssessmentBlocks`) | `is_active AND end >= now` |

So the same college ("Auguest college list fall", UAT) read **Active
assessments 3** beside a donut of **7 active sent** — the four in the gap were
all due to open later the same day.

Both now share `isActiveAssessment(row, now)` = **not expired and not
cancelled**, which is the definition the assessments **list screen already
shipped**: its `STATUS_GROUP` map (`assessments/_constants.ts`) files
`scheduled` — the design's "Upcoming" — under the `active` tab beside `live`
and `aboutToExpire`, which is why that college reads "All 7 / Active 7 /
Expired 0" there.

**Whether a window has opened yet is a STATUS (Ongoing vs Upcoming), not what
makes an assessment active.** Worth remembering — the first pass at this
unified on the stricter rule and moved the panel 7 -> 3, which contradicted the
list; the correction went the other way (`ba61301` then `161d114`). Verified:
panel, donut and KPI all read 7 for that college, matching the list's Active
tab.

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

## A lazily-enabled fetch hook must not report "no data" as failure

`useAssessmentStudents(id, enabled)` is lazy — the roster is only fetched once
the Student-wise tab is opened. It seeded its state with `loading: enabled`, but
**`useState`'s initialiser only runs on mount**, and on mount the tab is still
Overview, so `loading` was pinned to `false` for the life of the component.

Opening the tab flips `enabled` to true, yet the effect that starts the fetch
runs only *after* that render paints. That frame therefore reported "not
loading, no data", and `AssessmentDetailView`'s ternary
(`loading ? skeleton : error || !data ? errorCard : table`) took its only
remaining branch: **"Couldn't load the student roster" was shown for the WHOLE
fetch**, then swapped for the real table once it landed. Reported from PROD
mobile as "shows this for few seconds and then shows data". Nothing had failed;
the state had no way to say *not yet*, and the skeleton branch sitting right
there was unreachable.

Fixed 2026-08-12 (`6b42580`) — anything unresolved while enabled IS loading:

```ts
if (enabled && !state.data && !state.error) return { ...state, loading: true };
```

Seeding `loading: true` in the effect instead would still leave one painted
frame on the error card, so derive it on the way out, not inside the effect.
The loading `<section>` also carries `aria-busy` + a label, so the state is
announced rather than visual-only.

The sibling hooks (`useAssessments`, `useDashboardSummary`,
`useDashboardAssessment`) are always-enabled and seed `loading: true`, so they
never had this. **Any new lazily-gated hook does** — treat "unresolved while
enabled" as loading, or the consumer will paint an error for a healthy fetch.

Still open: `AnalyticsDrawer` receives only `data`, so while the roster loads it
renders an empty table reading "Showing 0 of 0 assigned" instead of a loading
state. Thread `loading` into it when that component is next touched.

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

## Passing year is derived in IST, never UTC

`student.current_course.ended_on` is epoch **millis of an IST wall-clock date**.
A 2027 batch is stored as midnight IST on 1 Jan 2027 = `1798741800000` =
**2026-12-31 18:30 UTC**. Every Postgres in the estate runs `TimeZone = UTC`, so
the year must be read back in the timezone it was written in:

```sql
-- WRONG (shipped until 2026-08-12): renders the instant in UTC
to_char(to_timestamp(cc.ended_on / 1000), 'YYYY')
-- CORRECT
to_char(to_timestamp(cc.ended_on / 1000) AT TIME ZONE 'Asia/Kolkata', 'YYYY')
```

The UTC form bucketed every batch whose `ended_on` landed on a 1 Jan **one year
early** — PROD's TPO Dashboard offered "2026" in the Passing-year filter for
students who are the 2027 batch (679 students on that boundary, ~3.9k on the
2026 one). Nothing looked broken because `buildCohort`'s **predicate** used the
same expression, so picking a year matched the same wrong bucket and the counts
were self-consistent; only the label was wrong. Only 1-Jan-IST rows move — IST
is ahead of UTC and never crosses back over 31 Dec, so a daytime `ended_on`
keeps its year either way.

The expression lives once in `institute-node/app/helpers/cohortSql.js` as
`PASSING_YEAR_EXPR` and is imported by all four v2 models (`DashboardV2`,
`AssessmentV2`, `AssessmentDetailV2`, `StudentWiseV2`) — filter options, the
cohort predicate and every row's displayed `year` must stay on the same
definition. Fixed 2026-08-12 (`22b54f3`), DEV + UAT; **PROD pending**.

The legacy v1 institute surfaces still carry the UTC form — `Reports.js:185`,
`iReports.js` (584/695/763/998) — and `StudentListInfo.js` filters by a raw
epoch range instead of a year expression, so v1 reports can disagree with v2 by
a year for the same student.

## The student report drawer is type-aware, because the assessments are

`1849b06` institute-node, `f557091` frontend (DEV backend + UAT both, 2026-08-12).

The drawer was assembled from generic `.panel` / `.drawer-stats` blocks while the
design's own vocabulary — `.rj-grid` / `.rj-cell` / `.rep-card` / `.brk-row` /
`.sch-row` / `#procPop` — was **already ported into `assessment-detail.css` and
simply unused**. Check that file before writing new markup for any v2 drawer;
the class is usually already there.

**The breakdown card is per type, and each type stores its parts elsewhere.**
`AssessmentDetailV2.loadBreakdown(type, attemptId)` returns
`{name, score, weight}`:

| Type | Components | Source | Weight |
|---|---|---|---|
| Communication | Reading / Writing / Speaking / Listening | section rows → `groupCommSkills` | share of RAW sections |
| Aptitude | Quantitative / Logical Reasoning / Critical Reasoning | `aptitude_scores.statistics->'categories'` | share of the paper's marks |
| Custom_Assessment | its own sections | `custom_assessment_scores.section_wise_stats` | share of marks |
| Role_Based | its own sections | `role_based_scores` | equal per section |
| Behavior | its nine competencies, as **levels** | `behavior_proficiency_scores` | none — no score to weight |
| AI_Interview | **none** | — | card is dropped |

The old query only ever hit `communication_scores`/`role_based_scores`, so
**Aptitude and Custom silently had no breakdown at all**.

The weights are real, not an even split. Communication and Role_Based headlines
are `AVG(score)` over section rows (`SCORE_JOINS`), so a component's weight is
its share of those rows — Writing rolls up five exercises and genuinely
outweighs Reading's one (63% vs 13% on a full paper). Aptitude and Custom weight
by marks. `apportion()` rounds largest-remainder so they sum to exactly 100, and
`Σ(weight × score)` lands on the headline: verified against PROD attempts at
69.44 vs 69.53 and 31.96 vs 32.20, the gap being integer rounding. **If you add
a type, give it a weight that reproduces its headline** — the card prints both,
so an invented weight is a visible lie.

**`timeline[]` is every occurrence, not just the ones sat.** `history` only has
rows the student was ASSIGNED, which cannot distinguish "sat 3 of 6" from "only
invited to 3". The timeline walks `occRows` and folds the attempt on:
`not_enrolled` (no assignment row — the run predates them joining the batch, NOT
a miss), `upcoming`, `in_progress`, `missed` (window closed, no attempt),
`completed`.

**The Diagnosis row is scoped to the pair THAT student sat (2026-08-27).**
`cd93091` institute-node. **DEV + UAT. PROD pending** (PROD runs
`release-v1.38-hotfix-1`, which carries the same block).

The merged Diagnosis milestone folded in every occurrence `loadGroupMaps`
returned, and a group owns every cohort's baseline pair — **124 diagnosis maps
on the PROD Communication series `e2af2c73`** (62 batches × 2 papers), of which
a student holds two. The other 122 came back `not_enrolled` and broke both
aggregates the row is built from: `statuses.every(=== "completed")` failed, so
it fell through to `some(completed)` and **every student in the series read "In
progress"**, and `every(score !== null)` failed, so **score and time blanked to
"—"** beside a trend chart that was already plotting the diagnosis point from
`history` (which was correct all along — it only ever held the student's own
attempts). Verified on PROD: `sivanandinipolu73@gmail.com` had both papers
`attempted=t submitted=t` on 2025-12-21 and still read "In progress · — · —".

`ownDiagnosisOccurrences` (`app/helpers/assessmentTimelineStatus.js`) now drops
the `not_enrolled` siblings before the fold, and every aggregate on the row —
`startTime`, `endTime`, `status`, `score`, `timeSec`, `cohortAvg` — reads the
scoped set. It falls back to the full set only so a student who sat NO diagnosis
still reports `not_enrolled` rather than losing the row. Partial baselines are
unchanged: one of two papers submitted still reads `in_progress`.

The same fix drops the **`Current` badge from a completed baseline**. Diagnosis
windows are minted ten years wide (see "Diagnosis maps stay open for roughly ten
years" below), so `phase === "current"` is true for the rest of the decade and
badged a finished 2025 baseline as the run being sat right now.

**`getStudentReport` never bound `npsType`** — the attempt query has read it
since `2d72c04` moved achieved levels onto progression history, but nothing in
that scope declared it, so every call threw `npsType is not defined` before
reaching the database and **the drawer 500d for every student on Development**.
Bound the same way `getSummary`/`getStudents` do. PROD predates NPS in this
file and was never affected.

**Ladder labels are shared, so they move everywhere at once.** `headline.level`
and the new `headline.levelBand` ("90+", "60–75") both come from
`assessmentBands` — the drawer, the roster's Achieved Level column and the
Competency ladder are one label set by design. Two ladder changes shipped with
this: Communication now reads `C2 (Advanced)` rather than a bare `C2`, and the
DEFAULT ladder (Role_Based / AI_Interview / Custom) takes the
design's **40/55/70/85** cutoffs instead of an even 20-point split, under which
35% read as "Developing" while the same 35 is a fail everywhere else. Nothing
filters on the level string (the column sorts by score), so this is display-only
— but it is not drawer-local.

### A Behavior assessment has NO score — it reports levels (2026-08-20)

`b2d883d`/`1b38586` institute-node, `65f5fda`/`aec3c93` institute-react-v2,
`48b4e2b2`/`155e707c` student-node. **DEV + UAT. PROD pending.**

A fully graded Behavior attempt showed **"Not yet scored"**, a dash for Achieved
Level and no breakdown card, while the legacy v1 TPO list and both Excel exports
printed **`NaN`** for the same attempt. The data was never the problem — the
PROD attempt behind the report had 9 competency scores, 9 proficiency rows and
14 report rows. Every symptom was read-side.

**The rule: a Behavior assessment has no score, and none can be invented.** The
candidate's own PDF ("Campus to Corporate Assessment Report") contains no number
anywhere — nine competencies each carry a proficiency level (**Beginner /
Apprentice / Practitioner / Master / Expert**, plotted 1-5), fourteen
sub-component behaviours carry Low / Medium / High, then a strengths vs
areas-for-improvement split and suggested job roles. No total, no average, no
percentage.

Two numbers exist and **both are wrong to report as a score**:

- `behavior_scores.total_scores` is the raw ANSWER TALLY —
  `{"Empathy":{count,total}, …, "grandTotal":350}`. Four sites in student-node
  `TpoDashBoard.js` averaged it with `Object.values(...).reduce((a,b)=>a+b,0)`,
  which **concatenates objects** → `NaN` on the institute list, the corporate
  list and both workbook exports.
- `behavior_competency_scores.score` is a weighted **T-score** (mean 50, SD 10 —
  student-node `BehaviorCalculations.calculateCompetencyScores`). Averaging the
  nine and printing "45.6%" put a candidate holding a **Master**-level Critical
  Approach into the "Developing / moderate risk / below 55%" band. **Do NOT add
  it to `assessmentScoreSql` `SCORE_JOINS`.** Every numeric v2 widget reading
  "—" for Behavior is correct, not a gap.

Per-competency band edges differ (`behavior_competency_levels`), so a row's
level must be **read** from `behavior_proficiency_scores`, never re-derived from
the number: 40.65 is "Apprentice" for Project Management and "Beginner"
elsewhere.

**Levels appear in the report drawer and nowhere else.** No roll-up on the
roster's Achieved Level column and none on the Overview Competency ladder — the
assessment awards one level PER COMPETENCY and no overall one, so any single
level would be the dashboard's invention, the same mistake as the score. In the
drawer the "Score breakdown" card becomes a **"Competency profile"** card grid
(`.cmp-cards` / `.cmp-card`, ported from v1 `StudentReport`
`renderBehaviorScoreCards`, on DS subtle surfaces so it survives dark mode, red
for Beginner only); the Achieved Level cell is hidden via `showLevel &&
!levelled`, the same way Role_Based already hides it; the score cell stays and
reads "—" with `scoreSub` = "Reported as levels, not a score", because a TPO
hunting for a percentage is owed the reason there isn't one. The Overview
Competency panel gets a Behavior-specific empty note instead of its default
"once the first attempts are scored", a promise this type never keeps.

Note v1 `institute-react` spreads these levels as **one table column per
competency** (`StudentsTable/index.js`) — nine extra columns. v2 deliberately
does not.

**Two traps if you touch this path:**

1. `latest` (the attempt a report describes) resolved as *latest SCORED*.
   Behavior has no score, so it resolved to nothing: no competency profile, and
   `headline.reportAttemptId` stayed null, which **disabled the PDF download**
   for an attempt that was fully graded. It now resolves by *latest submitted*
   for Behavior.
2. A recurring Behavior schedule skips `loadSeriesBreakdown`. The components are
   ordinal levels, and "the mean of Apprentice and Master" is not a level the
   platform can name.

Captions moved server-side with this: `headline.scoreSub` and
`headline.levelSub` are now the API's words. The frontend used to append
`"% band"` to whatever `levelBand` it was handed, which cannot describe a type
that has no band.

Still open: institute-node `StudentListInfo.js` (the **corporate** ATS list)
still averages competency T-scores into `totalScore` — same fabrication,
untouched because it sits outside the TPO dashboard.

### "How long is this assessment?" has no single answer

`79095d2` institute-node, `37de5e6` frontend (2026-08-13). The schedule card's
figure is the **sit-time** ("45 / min"), NOT the attempt window
(`assessment_validity_days`, how many days it stays open) — the two were
conflated before this. `app/helpers/assessmentDuration.js` resolves it, and it
has to ask a different question per type:

| Type | Source |
|---|---|
| Aptitude | the set's question count: **30 Q → 45 min, 40 Q → 60 min** (admin-node's own `difficultyConfigsByLength`) |
| Communication | **fixed 30 min** |
| AI_Interview | `ai_interview_config.interview_duration` — **SECONDS**, the only genuinely per-assessment value in wide use |
| Role_Based | `assessment_config.duration_minutes` — set for a few sets, null for most |
| Custom_Assessment, Behavior | not resolved → null |

Two things to know before touching it:

- **Aptitude and Communication are platform CONSTANTS**, enforced by the student
  player's own instruction screens (`Assessment-React`
  `.../aptitudeassmt/instruction.js` "Duration - 45 mins",
  `.../Communicationassmt/instruction.js` "Duration - 30 mins"). They are
  duplicated in the helper because the TPO app cannot reach the player's
  constants — **if the player's numbers change, the helper must change with
  them.** On PROD 5033 of 5067 aptitude maps carry the standard 30 questions, so
  45 min is right for almost all of them.
- **`assessment_config.duration_minutes` does not exist on PROD** — the
  migration never ran there (DEV and UAT have it). It is read as
  `(to_jsonb(ac) ->> 'duration_minutes')::int`, which yields NULL where the
  column is absent instead of erroring, so one env's schema drift cannot take
  the endpoint down. **Use that idiom for any column that is not on every env.**

Custom_Assessment is deliberately unresolved: its `time_in_minutes` sits on
`custom_assessment_config` per SECTION (`custom_section_id`), and
`custom_sections.entity_id` is the INSTITUTE, not the set — so a total means
summing only the sections a set actually uses. Not worth chasing for 39 PROD
maps, and a plausible-but-wrong duration is worse than none.

Anything unresolved returns null and the rail falls back to the window, then to
the assigned count, so no card loses its figure.

### The calendar is milestones, not open windows

`7616f3f` institute-node, `0280293` frontend (2026-08-13). The dashboard rail
and Full schedule used to place a map on **every day its attempt window
covered**. Diagnosis maps stay open for roughly ten years, so the two baseline
maps appeared twice on every day, both renamed to the parent schedule. A
five-run schedule that had not fired yet had the opposite problem: it appeared
zero times because future runs do not have `assessment_institute_map` rows yet.

Calendar placement is now event-based:

- the two baseline maps collapse to one **Diagnosis** milestone on their
  creation/start date;
- every scheduled run appears once, on its own start date;
- future runs are projected from `assessment_schedules.frequency_value`, the
  concrete ordered run-date list the scheduler itself uses;
- the recurring figure is the event's position in that full list (`1 of 5`,
  `2 of 5`, ...), not the number of map rows that happen to have fired so far;
- a real map replaces its projected row by `(schedule_id, calendar date)`, so
  the cron firing cannot create a duplicate;
- `end` remains the run's close time for card metadata, but it no longer drives
  which day groups render the event.

Follow-up `cd6ea8e`/`bb6350d`: projected rows have no map yet, but Communication
and Aptitude sit-times are platform constants, so they must still carry **30
min** and **45 min** respectively. The full agenda's left figure reads
`durationMinutes` first (then window as fallback), matching the dashboard rail.
Student-list roster values are master objects in many schedules — use
`degreeName` / `streamName`, not `String(value)`, or the audience chip literally
renders `[object Object]`. A folded Diagnosis keeps the parent schedule name in
its title and carries `kind: diagnosis` for the separate Diagnosis tag.

### Diagnosis results average the baseline PAIR

`66cabbb` institute-node, `49fa524` frontend (2026-08-13). The Diagnosis drawer
is one row per student across both baseline maps, so its result must also be one
combined diagnosis result. Do not use `SCORE_EXPR` here: that averages the raw
Communication section rows, and do not take the latest attempt's breakdown.
Use the canonical formula already shipped by student-node `Reports.js`:

- Writing = average of four applicable exercises: Email Writing **or**
  Dictation, plus QBR, Sentence Completion and Sentence Build;
- attempt total = Reading 20% + Listening 10% + Speaking 40% + Writing 30%;
- each displayed skill and the total are averaged across the two submitted
  diagnosis attempts;
- Assigned level is `assessment_sets.cefr_level`; Progression level is the
  stored `assessment_assigned_students.resulting_cefr`, widened through the
  shared Communication ladder;
- Diagnosis proctoring retains the legacy operational contract: any invalid
  `proctoring_logs` row makes the pair Bad; all logs valid makes it Good.

Verified on UAT schedule `0d4c315a`: A1, 52.43%, A1 (Beginner), Reading 46.97%,
Listening 75%, Speaking 39.5%, Writing 65.79%, Good. The diagnosis-only table
keeps the established compact columns: the combined score is one **Avg score
(%)** cell and its existing hover contains Assigned Level, Avg Score,
Progression Level and the four skills. Do not expand those metrics into table
columns. The only diagnosis-specific visible column is **Diagnosis Status**,
shown as submitted baselines out of assigned baselines (`0/2`, `1/2`, `2/2`).
Ordinary occurrence drawers keep their existing Status column.

### Aptitude roster score hover comes from `statistics.categories`

`3fa8731` institute-node (2026-08-13). The occurrence drawer's hover is shared,
but it only renders when `StudentRow.sections` is populated. Communication and
Role_Based have section-score tables; Aptitude does not, so its icon was absent.
`loadAttemptSections` now also unnests
`aptitude_scores.statistics::jsonb->'categories'` and returns each category's
clamped `100 * gained_marks / total_marks` percentage. Keep the explicit
`::jsonb`: the column is json on UAT and jsonb on DEV. This supplies Critical
Reasoning, Logical Reasoning and Quantitative to the existing hover without a
frontend-specific Aptitude path.

### Recurring student reports use report points, not raw attempts

`255302c` institute-node, `6393db5` frontend (2026-08-13; UAT merges
`08568e0` / `60095b4`). The student report drawer represents a recurring
series, so its arithmetic must use the same units the TPO sees:

- the two raw diagnosis papers are one **Diagnosis** point; its score, time and
  component scores are averaged only after both papers are submitted;
- scheduled occurrences remain `#1`, `#2`, ... and are never renumbered by the
  hidden diagnosis maps;
- the headline and score breakdown average report points, so the diagnosis
  pair receives one vote rather than two;
- Aptitude breakdowns average Quantitative / Logical Reasoning / Critical
  Reasoning from `statistics.categories`; Communication averages Reading /
  Writing / Speaking / Listening through the existing type-aware resolver;
- both the trend and Schedule-wise performance consume the consolidated
  timeline, so `Diag` and `Diag 2` can never reappear as separate rows.

The Download button keeps the legacy student-node, single-attempt PDF for
one-time assessments. Recurring Aptitude and Communication use a dedicated
series PDF generated by the v2 BFF from the consolidated report payload. It
contains the series headline, aggregated breakdown, Diagnosis + `#N` trend,
schedule table and proctoring summary. The request is keyed by group id and
student email, never a latest `assessment_assigned_id`.

PDFKit must stay in `next.config.ts#serverExternalPackages`. Bundling it with
Turbopack rewrites its built-in AFM font path to `/ROOT/...` and UAT returns
502 even though `next build` succeeds. Keep footers above PDFKit's printable
bottom margin as well; drawing them below it silently adds blank pages.

Live UAT verification on group `5b64952a` / student
`prabha+scustor444rr4@pluginlive.com`: timeline is exactly **Diagnosis, #1,
#2**; the series Quantitative score is **18.19%** (the latest run alone was
0%); the download returns HTTP 200, `application/pdf`, two A4 pages, with all
three report points present in extracted text.

#### Recurring PDF follows the established PluginLive report pattern

`7a1fd11` frontend (2026-08-13; UAT merge `832a2bb`) restyles the dedicated
series PDF to match the existing one-time assessment report supplied as the
visual reference. The calculation and consolidated timeline are unchanged.

- the real PluginLive logo leads the A4 document;
- assessment title, type, candidate metadata and date use the same centered
  hierarchy as the established report;
- the overall score sits in a large pale-grey panel with the blue headline;
- proctoring uses a bordered status panel and compact signal cells;
- Aptitude or Communication component averages use red score cards and
  progress rules;
- the performance trend and schedule table continue on printable pages with
  a restrained PluginLive footer and page count.

Keep the footer at `y <= 774` with the current A4 margin. PDFKit applies the
bottom margin even when text has an explicit coordinate; placing the footer at
`y = 786` generated two additional blank pages containing only page numbers.
The checked preview is two A4 pages and preserves the consolidated Diagnosis
plus `#N` schedule sequence.

Do not revert the date filter to window overlap (`start < to AND end >= from`)
or use `coversDay` in the calendar views. Those are valid for answering "what
can a student still take today?", but this UI answers "what was scheduled on
this date?". The API payload carries `kind: diagnosis | run` so both calendar
surfaces render the Diagnosis tag without guessing from a map name.

### Degrees are abbreviated on lists, never in filters

`8134844` institute-node, `6153322` frontend (2026-08-13). Lists show
"B.COM"; filters keep "Bachelor Of Commerce".

The short form comes from **`institute.degrees.short_form`** — the same column
the legacy TPO report exports use, so v2 abbreviates a degree exactly the way
admin and the downloads already do. Do NOT derive an acronym in code: an
algorithm reads "Bachelor Of Commerce" as "BOC" and everyone else reads it as
"B.COM".

**The degree string is a LABEL and a KEY.** `DashboardV2.buildCohort` (and
`StudentWiseV2`) match `DEGREE_EXPR` against the full name, and the Degree-Dept
filter sends that name back as its value — shorten the value and the filter
silently matches nothing. So the map is served once from
`GET /institutes/dashboard/v2/degree-short-forms` and applied by the client at
**render time**; payloads keep sending full names. That is also why it is not
stamped onto each row: one map cannot be mistaken for a key, nine extra row
fields eventually would.

The dashboard's **Active Assessment Schedules** row was the one list that kept
truncating after the change (`534d2b1`): it rendered the payload's server-built
`audienceLabel`, which carries the full name. It now builds its own label from
`audience[0]`, like every other "Assigned to". `audienceLabel` is marked
**@deprecated rather than deleted** — dropping a payload field would blank that
cell for the minutes between the backend and frontend restarts. Render from
`audience`, never from it.

Worth knowing when reading that column: the label is `degree + " " + department`,
so "Master Of Human Resource Development Management" is NOT one degree — it is
`Master Of Human Resource Development` + `Management`, and it now reads
"MHRD Management". A tooltip that looks like an unmatched degree may just be the
two fields run together.

Filters deliberately keep full names for a second reason: a dropdown is where a
TPO goes to *find* a degree, and "BAF" / "BAFI" / "BBI" are far harder to scan
than the words.

Coverage: the master is polluted (~4.4k rows, mostly junk from the
self-appending create path) but only ~213 carry a short form, and only exact
lowercased-name matches are looked up, so the junk is inert. Of the 36 degrees
that actually reach the TPO screens, **33 resolve**; the rest fall back to the
full name (`Unknown`, `Bachelor's`, `Post Graduate Diploma` — fixable by adding
short forms to those master rows, a data change, not code).

Gotchas worth keeping:

- Short forms are stylistically inconsistent in the master (`M.B.A`, `B.COM`,
  `B.Sc`, `B.Tech`, `BBA`). Shown verbatim on purpose — normalising would make
  the screen disagree with the report export.
- `ELEVENTH` (the largest single group on PROD) maps to `11`. Correct — it is a
  school class, not a degree — but it reads oddly under a "Degree" heading.
- Every shortened label keeps the full name in `title`, and the **CSV export
  keeps full names**: an export is data, not UI.
- The map is cached 10 min in institute-node and once per page load in the
  client; a failed load answers `{}` and every caller falls back to the full
  name, so the abbreviation can never take a list down.

### Level lists order by score band, never alphabetically

The analytics drawer's **Level** filter was a `Set` over the students in
arrival order, so it read "A2, B2, B1, C1, A1" (`d84e8f9`, 2026-08-13). It now
orders by the LOWEST score seen in each band, which reproduces the ladder
exactly — a level *is* a score band, the bands partition the score line, so
everyone in a lower band scores below everyone in a higher one.

Do not sort the names: that only works for CEFR. Aptitude puts "Advanced"
before "Beginner" alphabetically, and the DEFAULT ladder
(Novice/Developing/Proficient/Advanced/Expert) is worse. Any new level list
must order by band, and there is exactly one such list today — keep it that way
or the two will drift.

### The dashboard's filters and freshness stamp live in the TOP BAR

`d389a03`. Two deviations, both fixed 2026-08-13:

- The design's **`Updated <time> IST` stamp** was missing entirely, although its
  CSS (`.head-stamp`, the live dot, the `is-loading` spinner, the
  reduced-motion and small-screen rules) was already ported and unused.
  `PageChrome` now carries a `stamp` slot that `Topbar` renders beside the
  title. The value is the LATER of the two dashboard payload fetch times — the
  screen is only as current as its slowest block — formatted in Asia/Kolkata,
  because the label says IST and formatting a viewer's local clock while calling
  it IST would be a lie. While either block is in flight it shows the design's
  `Data loading` state rather than a stale time.
- The **cohort filters** sat in a `.dash-toolbar` strip invented below the
  header. The shell already renders page-chrome `actions` into `.topbar-group`
  (the design's own slot), so they were handed over and the strip — markup and
  CSS — is gone. `usePageChrome` moved from `dashboard/page.tsx` into
  `DashboardView`, which owns the filter and load state both slots need.

Proctoring is **not** a body card: it lives in the popover behind the head's
shield (red via `.iconbtn.flagged`, plus the `.rep-warn` band), so the body stays
about the assessment. `#procPop` is widened to 384px — our verdict is a phrase
("Needs review"), not the design's one-word Good/Bad, and heading + chip + close
needed exactly 360 inside a 360px box.

The trend plots `timeline[].cohortAvg` as a muted dashed series beside the
student's line. A rising line says nothing on its own — the batch may have risen
with it, or the student may be climbing while everyone else climbs faster.
`TrendChart` takes an optional index-aligned `peer` array (its three other
callers pass nothing and are unchanged), and the drawer builds BOTH series off
`timeline` rather than `history`, so an occurrence the student was never sent
keeps its slot instead of shifting the cohort line sideways.

### Every hook must run before `if (!email) return null`

The drawer blanked the whole screen on open with **React #310** — "Rendered more
hooks than during the previous render". The outside-click and popover-reset
effects had been added *after* that early return, so the component ran one hook
while closed and three once opened; React tore the tree down and
`app/global-error.tsx` took over, which is why it looked like a dead white page
rather than a drawer error. Fixed in `ceff917`.

Two things worth carrying forward:

- **`eslint` did not catch it** (`rules-of-hooks` stayed silent on hooks placed
  after an early `return`), so a green lint is not evidence here. What did catch
  it: a throwaway client page under `src/app/<name>/` that mounts the component
  with `email=null` and flips it after 60ms — the exact transition — driven by
  headless chromium listening for `pageerror`. It reproduces on the broken
  commit and passes on the fix. Route folders starting with `_` are **private**
  in the App Router and 404, and the page needs `.env.local` present or
  `lib/auth.ts` throws at module scope.
- **Prefer deriving over resetting.** The popover now tracks WHICH student it is
  open for (`procOpenFor === email`) instead of a boolean reset by an effect, so
  changing student closes it for free — one less hook, and one less render pass.

The report payload's list fields are normalised on arrival
(`sections` / `history` / `timeline` / `proctoring.signals`). The drawer is
portaled with no boundary of its own, so a single `.map` on an undefined field
escapes to the root error boundary and blanks the screen the same way — and a
frontend deployed ahead of its backend is enough to cause it.

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
find .next/static .next/server -name '*.js' -o -name '*.css' \
  | xargs grep -ho '[a-z-]*\.dev\.pluginlive\.com' | sort | uniq -c   # must be empty
```

**Exclude `*.map`, or the check cries wolf.** Source maps preserve source
*comments*, and two comments in this repo mention `dev.pluginlive.com` while
explaining the trap — including the one in `src/lib/auth.ts`, which trips the
very grep it describes. A bare `grep -r` over `.next/` therefore reports a leak
on every clean UAT build (seen 2026-08-13). Maps are not executed and not served
to the browser, so scan the `.js`/`.css` only. A guard that fires on every build
gets ignored, which is how a real leak would get through.

To confirm positively rather than by absence, check what IS baked in:

```bash
grep -rhoE 'https://[a-z-]+\.(uat\.)?pluginlive\.com' .next/static --include='*.js' | sort -u
```

On UAT that should name only `*.uat.pluginlive.com` hosts.

Never add a `?? 'https://...dev...'` fallback for one of these vars — it is not a
runtime default, it is a literal baked into every bundle, and it defeats the grep
above. `src/lib/auth.ts` throws when `NEXT_PUBLIC_LOGIN_URL` is missing instead.

### PROD does not use the public API hosts (2026-08-17)

`6fc89c5`. There is no `STUD_API_URL` on the boxes, so `src/lib/api/studentApi.ts`
**derives** the student-node host from `INST_API_URL` — deriving cannot bake a
DEV hostname into a UAT bundle the way a literal fallback would. Three shapes,
and the third is the one that bit:

    api-inst.dev.pluginlive.com       →  api-std.dev.pluginlive.com
    api-inst.uat.pluginlive.com       →  api-std.uat.pluginlive.com
    api-inst.pluginlive.com           →  api-stud.pluginlive.com    ← "stud"
    institute-node.api.svc.cluster…   →  student-node.api.svc.cluster…

**PROD runs on k8s and talks service-to-service**, so its deployment env is
in-cluster DNS, not the public host:

```
kubectl -n frontend get deploy institute-react-v2 \
  -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}'
INST_API_URL=http://institute-node.api.svc.cluster.local
```

That matched neither public branch, so the resolver returned null and the BFF
short-circuited **before calling student-node at all**: `500 {"message":"Export
service is not configured"}` on every export (series, occurrence, diagnosis) and
`"Report service is not configured"` on the single-student PDF — four dead
actions, PROD only, DEV and UAT fine. The error names a config problem, not a
student-node or DB problem; nothing ever reached them.

PROD was unblocked first with an explicit override, which the resolver returns
verbatim ahead of any derivation:

```bash
kubectl -n frontend set env deployment/institute-react-v2 \
  STUD_API_URL=http://student-node.api.svc.cluster.local
```

**That override lives outside any manifest.** `~/autodeploy.sh` deploys with
`kubectl set image`, which preserves it, but a manifest re-apply would drop it
and PROD would break again — which is why the derivation now also understands
`institute-node.<rest>` → `student-node.<rest>`, carrying namespace and cluster
suffix through, and needs no env var on any box.

Probe from inside the pod when this looks wrong again — 404 on `/` still proves
DNS, service and port are good, since these APIs have no root route:

```bash
kubectl -n frontend exec deploy/institute-react-v2 -- \
  wget -qS -O /dev/null http://student-node.api.svc.cluster.local/
```

## Deploying v2

Not in `auto_deploy.sh` (that script only knows the numbered v1 services).

```bash
# on the target box
cd ~/frontend/institute-react-v2
git pull origin UAT
corepack prepare pnpm@10.33.0 --activate     # pnpm, NOT npm — the repo has pnpm-lock.yaml
pnpm install --frozen-lockfile
rm -rf .next && pnpm build
find .next/static .next/server -name '*.js' -o -name '*.css' \
  | xargs grep -ho '[a-z-]*\.dev\.pluginlive\.com'   # must be empty (skip *.map — see above)
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
  `institute-react-v2.service` exists on **both DEV and UAT** (DEV also has
  `admin-react-v2` and `corporate-react-v2` units). The failure is quieter than
  the note above suggests: `Restart=always` means killing the process brings it
  straight back on the *new* build, so a following `nohup next start` just dies
  with `EADDRINUSE` and the site looks perfectly healthy — the deploy worked, but
  not for the reason you think, and the log fills with a crash you did not cause.
  Confirm with `systemctl status` that `Main PID` is the process on the port, and
  that `Active: since` is later than `stat -c %y .next/BUILD_ID` (seen 2026-08-17).
  On DEV, plain `systemctl` fails with *"Failed to connect to bus"* — use `sudo`.

## Order of operations when flipping a nav entry

v2 must be **up on the target environment before** the v1 nav change ships, or
every click on that entry 404s. Deploy order: `institute-node` → stand up v2 →
verify → flip v1 nav.

## Communication/Aptitude rank on progress score, not raw % (2026-08-25)

`d84988c` + `ba3b394` institute-node, `f39e026` + `aa1eeb3` institute-react-v2.
**DEV + UAT. PROD pending.**

The dashboard ranked and banded every type on a plain 0–100 percentage, so an
**A1 student at 80% outranked an A2 student at 60%** — the wrong ordering, and
it repeated in the roster sort, the Avg-score column, the KPIs and the risk
bands. The most literal instance was `PerformanceTab.tsx` `SORT_VALUE.level`
= `(s) => s.score ?? -1`: the **Achieved Level** column sorted by raw
percentage and never by level ordinal.

Communication and Aptitude now rank and band on **NPS** (the difficulty-anchored
progress score) instead. Everything else is unchanged.

### Only Communication and Aptitude — everything else keeps its raw %

Those are the only two types with a level ladder to anchor on. Role_Based,
Custom_Assessment, AI_Interview and Behavior have **no NPS at all** (NULL, not
zero) and keep their raw percentage on a visibly separate scale. Do not mix an
NPS and a percentage in one column — that is the original bug.

### The NPS read is per-attempt, inside the schedule

`assessmentScoreSql.js` gained `NPS_EXPR` / `NPS_JOIN`, joining
`assessment.progression_history` on `assessment_assigned_id`, plus
`npsExprFor(type)` / `npsLevelExprFor(type)` which resolve the **one** column
that type's ladder lives in:

| type | progress score column | level column |
|---|---|---|
| Communication | `assessment_communication_progress_score` | CEFR |
| Aptitude | `assessment_aptitude_progress_score` | competency |
| anything else | `NULL::double precision` | `NULL::text` |

`NPS_EXPR` COALESCEs the two only because the dashboard query spans several
types at once. A per-type query **must** use `npsExprFor` — a Communication
schedule must never surface an aptitude progress score.

**Do not take "latest NPS per type, ignoring the schedule".** That leaks other
schedules in: on the PROD preview, "Aptitude 2027 24/04" went 17 → 24, inflated
by a *later* schedule, and four distinct Communication rows nearly collapsed to
10/10/10/11 — an April schedule showing a number shaped by a June test. Join
per attempt inside the schedule.

### The number in SQL is LINEAR; the curve is applied last, once

`NPS_EXPR` is deliberately the stored linear column. **Never curve in SQL.**
Aggregate linear, curve last, curve once — see
[../../Assessment/nps-scale-and-curve.md](../../Assessment/nps-scale-and-curve.md).
Sorting is exempt: the curve is strictly monotonic, so `ORDER BY` on the linear
column is correct and cheaper.

### Band thresholds come from the curve, not from `AVG_OK = 70`

`assessmentBands.js` resolves Communication and Aptitude cutoffs from
`communicationBandBoundaries()` / `aptitudeBandBoundaries()`. The old
`AVG_OK = 70` green threshold made **every row amber forever** under either
scheme and is gone for these two types. The DEFAULT ladder (Role_Based /
AI_Interview / Custom) still uses the design's 40/55/70/85 percentage cutoffs.

### Label the column honestly

"Avg score" implies a percentage and NPS is not one. Communication reuses the
CEFR names; Aptitude does **not** reuse its percentage ladder wording — its NPS
bands are `Beginner / Learner / Competent / Advanced`, while its percentage
bands read `Beginner / Intermediate / Upper Intermediate / Advanced`. Those are
two different vocabularies for the same type and `assessmentBands` keeps them
apart on purpose.

### A Communication NPS average silently drops half the cohort

Communication diagnosis #1 stores `nps: null` by design, which on UAT is **48%
of Communication students** (they have taken exactly one assessment). Averaging
"whatever has NPS" describes only students who came back for a second sitting —
survivorship bias toward the more able half. Show `n` with the number. Aptitude
has no equivalent gap.

### The Overview Competency card is NOT height-locked (2026-08-26)

`96c9d5d` institute-react-v2. **DEV + UAT branches; DEV deployed, UAT pending.**

The Overview tab has two `.ov-2col` rows. Section 2 (Completion analysis +
Progress trend) is deliberately locked to `--ca-card-h: 416px` with
`overflow: hidden`, so flipping the completion card's funnel/department toggle
never reflows the row. That rule was originally written unscoped —
`.ov-2col > .panel` — and the **Competency + Student-at-risk** row underneath
reuses the same `.ov-2col` class, so it silently inherited both the fixed height
and the hidden overflow.

A 6-rung CEFR ladder needs **555px**. Under the lock, **C1 and C2 were cut off
mid-row with no scrollbar** — the two highest Communication bands were
unreachable on the page that exists to report them. Aptitude's 4-rung ladder fit
inside 416px, which is why this only showed on Communication.

The lock is now scoped to `.ov-2col-wrap .ov-2col` (Section 2, the only row with
a toggle to hold still). The bottom row sizes to its content; `align-items:
stretch` keeps the at-risk donut card level with it.

**If you add a rung to any ladder, check this row.** The ladder length is data
(4 for Aptitude, 6 for CEFR, 5 for the DEFAULT ladder) and the card must follow
it — do not reintroduce a fixed height there, and do not "fix" a future overflow
with an inner scrollbar, which buries bands a TPO has no reason to expect below
the fold.

## Missed schedule rows cannot download reports (2026-08-27)

`institute-react-v2` Development `e7e530d`, UAT `8a09f4c`. **DEV + UAT deployed; PROD pending.**

In Assessment Details → Student-wise performance → per-student drawer, a schedule row with status `missed` now renders its report-download icon disabled even when the API retained an `attemptId` for the assignment. The action title explains that no report exists for a missed assessment. The same eligibility check also guards the click handler, so the rule is not only visual. Completed rows with an attempt remain downloadable; rows without an attempt remain disabled as before.

The import-free `src/lib/occurrenceReport.ts` owns the rule and has focused Node tests for completed, missed-with-assignment-id, and no-attempt cases. Both target builds passed and both services returned HTTP 200 after restart; deployed DEV and UAT bundles contain the disabled-action copy.

## Usage widget — real pack usage in the top bar (2026-08-25)

`285211c` → `1dc5397` + `7c1d86d` institute-react-v2. **DEV + UAT. PROD pending.**

The top-bar `UsageWidget` (renamed from `UsagePill` in `0652c01`) shows the
institute's assessment pack consumption. It is **hover-only** — the
click-through modal was dropped in `0edf71e`.

Data comes from a new BFF route, `GET /v2/api/usage`
(`src/app/api/usage/route.ts`). **admin-node owns subscriptions**, so the route
proxies the existing `assessment/getInstituteSubscriptionQuota` — the same
endpoint the admin Feature Access screen reads — rather than duplicating the
`subscribed_institutes` query in institute-node. It needs `ADMIN_API_URL` set on
the v2 app (server-side, read at runtime, not baked).

The institute id is taken from **the caller's JWT only**, never a query param;
admin-node resolves a campus id to its parent institute itself.

Two gotchas already fixed here:

- A non-zero rate rendered as a flat `0%` (`7c1d86d`).
- Unlimited packs are a separate state from a numeric quota. `total > 0` with
  `hasUnlimited` is a real combination — a metered pack *and* an unlimited one —
  so the widget cannot treat "unlimited" as simply `total === 0`.

## The breakdown columns sort too (2026-08-26)

Speaking / Listening / Reading / Writing — the columns the Performance Score
header's caret expands — were the only plain `<th>` left in the Student-wise
performance table. Every other column already carried `SortHeader`, so ranking a
cohort by one language skill (the reason the breakdown is opened at all) meant
reading down the roster by eye.

They were left out because they are the table's only **dynamic** columns:
`SCORE_SUB_CATEGORIES` gives Communication its four language skills and Aptitude
its three reasoning sections, so they never fitted the fixed `SortKey` union.

`SortKey` now also admits `` `sec:${string}` `` — one key per breakdown column —
and `sortValue(key)` in `PerformanceTab.tsx` resolves a `sec:` key against the
row's own `sections`, with everything else falling through to the existing
`SORT_VALUE` map. A student whose attempt carries no such section sinks with the
nulls, the same way every other column treats missing data. First click opens
best-first, matching the other performance columns.

**Collapsing the breakdown hands the sort back to Performance.** Otherwise the
column driving the row order would be hidden and the table would sit in an order
nothing on screen explains.

## Schedule-history report and stored dropout status fix (2026-08-27)

The Schedule tab's occurrence roster now returns each submitted attempt's
`assessment_assigned_id` and the matching student id, enabling its per-student
PDF report action. It also reads `assessment_assigned_students.status` as the
lifecycle source of truth: `DROPOUT` renders Dropped, `INPROGRESS`/`IN_PROGRESS`
renders In progress, and `COMPLETED` renders Completed. Dropout is not inferred
from the schedule window or attempted/submitted flags; only never-started
absence remains derived.

Shipped to DEV and UAT on 2026-08-27:

- `institute-node`: Development `16fb221`, UAT merge `e402f55`.
- `institute-react-v2`: Development `01314f0`, UAT merge `163a999`.

Both environments were rebuilt. UAT verification: backend health 200, frontend
`/v2/assessments` 200 locally and publicly, backend restart policy
`unless-stopped`, stored-dropout mapping present in the running container, and
zero `dev.pluginlive.com` references in built client JavaScript.

## Assigned-batches popover scrolling (2026-08-27)

The shared `BatchPopover`/`ValuePopover` previously closed as soon as its own
list was scrolled. Their capture-phase `window.scroll` listener could not
distinguish internal list scrolling from movement of the page beneath the
fixed-position portal. The listener now ignores scroll events originating
inside the popover, while page/table scroll still dismisses it. The list also
uses `overscroll-behavior: contain` so reaching either end cannot chain the
wheel/touch gesture into the dashboard behind it.

Frontend commit `700888c`; deployed to DEV and promoted/deployed to UAT in
merge `1c0f861`. UAT verification: dashboard 200 locally and publicly, fix
present in the deployed checkout, and zero DEV URLs in built client JavaScript.
