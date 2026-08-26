# Admin v2 — strangler-fig (LIVE on DEV and UAT; Create Assessments migrated)

The Admin portal is being rebuilt module-by-module behind a strangler-fig, the same
pattern as [institute-react-v2](../Institute/README.md) and
[corporate-react-v2](../Corporate/v2-strangler-fig.md). One new repo sits alongside
the v1 app; there is **no** admin-node-v2 — the BFF calls the existing `admin-node`.

| Repo | Checkout | Stack | Where it runs |
|---|---|---|---|
| `admin-react-v2` | `~/frontend/admin-react-v2` | Next.js 16.2.10 + React 19 + TS + Tailwind 4, `basePath=/v2` | DEV: systemd :3013 · UAT: systemd :3013 (since 2026-08-19) · PROD: not yet |
| `admin-react` (v1) | `~/frontend/admin-react` | webpack SPA, antd 4 + Redux | DEV `admin-react.service` (:3004) · UAT · PROD |

Created 2026-08-03 (`PluginLive-Technologies/admin-react-v2`, branch `Development`).
The org repo had to be created by hand: neither PAT on the DEV box (RajPluginLive,
vedantnadhe-creator) nor the MCP GitHub identity can `POST /orgs/.../repos` — 403
"You need admin access to the organization". Pushing to an existing repo is fine.

## Status

**The nav is still all-v1; one action has moved.** `ADMIN_V2_MODULES` is empty on
both DEV and UAT, so no sidebar entry redirects anywhere. What *has* migrated is
the **Create Assessments** action on `/assessment` — see below. The assessment
list itself stays on v1.

| Env | app running | nginx `location /v2` | `ADMIN_V2_MODULES` | `ADMIN_V2_CREATE_ASSESSMENT` |
|---|---|---|---|---|
| DEV | systemd :3013 | yes | `''` | `'1'` |
| UAT | systemd :3013 | yes (added 2026-08-19) | `''` | `'1'` (2026-08-19) |
| PROD | no | no | unset | unset |

## Create Assessments hands off to v2 (action-level strangler-fig)

Second flag, independent of `ADMIN_V2_MODULES`, in `admin-react`'s gitignored
`.env`/`.env.uat`:

```bash
export ADMIN_V2_CREATE_ASSESSMENT='1'   # '1' enables; anything else = legacy wizard
```

`modules/Assessment/index.js` reads it and, when on, makes the button a real
browser navigation (react-router cannot client-route into another app):

```js
window.location.href = `/v2/assessment?create=1&type=${entityType}`
```

v2's `ManageAssessmentsView` derives the hand-off from the URL — `create=1` opens
the entity picker, `type=college|corporate` pre-selects the tab the user left.
Derived from the URL rather than copied into state, so a refresh reopens the
picker.

`config/webpack.base.js` declares it in the **object** form of `EnvironmentPlugin`
(default `''`), so it inlines cleanly. Verify a build took by grepping the
shipped JS — when the flag is on, terser drops the condition *and* the legacy
branch entirely:

```bash
docker exec adminreact sh -c "grep -c '/v2/assessment?create=1' /app/build/main.*.js"
```

If the string is absent, the flag was off at build time — the dead branch was
eliminated. The env var name itself should appear only in the `.js.map`.

## The handoff is env-gated, not branch-gated

This is the one real difference from Corporate, and it exists because of what
happened there: the Roles nav flip was hand-edited into `navItems.js`, rode a
Development→UAT merge, and went live on a box with no v2 app. nginx there has only
`location /` → the v1 SPA, so `/v2/roles` was served **v1's index.html with a 200**
and rendered `PageNotFound`. Health checks and `curl -w %{http_code}` both looked
fine; the nav item was simply dead.

In `admin-react`, every top-level nav path resolves through a helper instead:

```js
// src/modules/Nav/navItems.js
const V2_MODULES = new Set(
  (process.env.ADMIN_V2_MODULES || '').split(',').map(k => k.trim()).filter(Boolean)
)
const v2Path = (key, legacyPath) => V2_MODULES.has(key) ? `/v2/${key}` : legacyPath
...
{ path: v2Path('assessment', '/assessment'), navTitle: 'Assessment', ... }
```

`ADMIN_V2_MODULES` is a comma-separated list of module keys live in v2 **on that
box**, read from its own **gitignored** `.env`. Empty or unset ⇒ every module stays
on the legacy screen, so the flip physically cannot travel through a branch merge.

`config/webpack.base.js` declares it via the **object** form of `EnvironmentPlugin`
(`{ ADMIN_V2_MODULES: '' }`) — the array form used for the other vars *throws* when
a var is missing, which would break the first UAT/PROD build after this landed.

## React-router cannot client-route into another app

A `/v2/*` path in `navItems.js` is not enough. `Nav/index.js`'s `onItemClick` calls
react-router's `navigate()`, which matches the path against **v1's** route table,
misses, and renders v1's 404 inside the v1 shell — the click looks broken. So:

```js
const hardNavIfV2 = path => {
  if (!path?.startsWith('/v2')) return false
  window.location.href = path
  return true
}
```

It runs **first** in `onItemClick`, before the Reports/Analytics accordion branches,
so a migrated one hops to v2 instead of toggling a now-empty accordion. The Analytics
sub-items derive their target from the parent `item.path` rather than a literal
`/dashboards`, so they follow the parent when it moves.

**Stale-bundle gotcha:** until a user hard-refreshes once after a v1 deploy, the old
bundle's handler is still running and has no `/v2` check.

## Route convention

A module's route is **`/v2/<key>`**, and the key is identical in both repos:
`admin-dashboard`, `meta-dashboard`, `onboarding`, `corporates`, `institutes`,
`assessment`, `feature-access`, `analytics`, `reports`, `users`, `system-config`,
`course-mapping`, `event-catalogue`, `ranking-algorithm`.

Note the keys that differ from the v1 path: `feature-access` → v1 `/assessmentAccess`,
`analytics` → `/dashboards`, `system-config` → `/systemConfig`, `course-mapping` →
`/coursemapping`, `event-catalogue` → `/eventcatalogue`, `ranking-algorithm` →
`/rankingAlgorithm`.

In v2, `config/nav.tsx` exports `firstV2Route` (the first `kind: "v2"` leaf) and
`(app)/page.tsx` redirects `/v2` there, so the landing page follows the migration
automatically. While nothing is migrated it renders an explainer instead.

## Migrating a module

1. Build it at `admin-react-v2/src/app/(app)/<key>/`, with its BFF endpoints under
   `src/app/api/` calling `adminNodeGet`.
2. Flip that entry in `src/config/nav.tsx` to `kind: "v2"`, `href: "/<key>"`.
3. Deploy admin-react-v2 to the target env **and** add a `location /v2` block to that
   env's admin nginx conf.
4. Only then, add `<key>` to `ADMIN_V2_MODULES` in that box's `.env` and rebuild v1.

Steps 3 and 4 are the ones that matter. Enabling a key in an env without the app and
the nginx block reproduces the Corporate failure exactly.

## Assessment wizard — current state (2026-08-19)

Reached from v1's Create Assessments button (above) at `/v2/assessment/new`.

**"Generate with AI" and the JD file attach are both simulations.** Attaching a
file makes the Job description box read-only, shows a spinner and
"Parsing <name>…", then types generated text in a few characters at a time,
landing on "Parsed <name>". It looks exactly like extraction. **No
text-extraction is wired up** — nothing reads the PDF, and there is nowhere to
send one yet. Generate with AI goes through the same typing engine and is
likewise canned. Both share one timer ref, so starting either cancels a running
other rather than letting two reveals collide in the same field. Treat any JD
text these produce as placeholder, not as anything derived from the file.

**Custom Assessment can now be floated** (2026-08-20). It was the one type the
wizard could configure but never send: admin-node composes a Custom paper from
sections that are already rows in its own bank, referenced by `section_id`, and
the wizard only held them in the browser under generated ids — so the BFF
refused the float outright and told the admin to remove Custom to send the rest.
The float now **persists each section first** via `createSectionquestions` and
points the assign call at the ids that come back. Manual sections post their
questions as JSON (`correct_opt` is a **1-based index into the options actually
sent**, so dropping a blank option renumbers the answer with it rather than
marking the wrong one); an Excel section posts the sheet itself as multipart,
because admin-node is what parses it — including the images embedded in the rows.

**Step 3's candidate lists and sheet upload are real** (2026-08-20). "Use an
existing list" offered a hardcoded `B.Tech CSE` / `MBA-Fin` catalogue with
invented headcounts, and every uploaded file resolved to the same eight
fictional people after a 700 ms fake delay that always ended in "Parsed
successfully". Three admin-node endpoints back them now:

| Endpoint | Returns |
|---|---|
| `GET /assessment/getInstituteBatches?instituteId=` | the degree / department / passing-year cohorts a campus has students in, with true headcounts |
| `GET /assessment/getInstituteBatchStudents?instituteId=&degreeId=&streamId=[&passingYear=]` | that cohort's students as `{name, email, mobile}` |
| `POST /assessment/parseCandidateSheet` (multipart) | an uploaded XLSX/CSV read into `{candidates, skipped}` |

The cohorts come from the same three columns the broadcast scope picker reads
(`student.current_course.degree_id / stream_id / ended_on`), so a list here
reaches the cohort a broadcast would. A cohort with **no passing year on file**
is still real students and is offered as "No year" rather than dropped.

The sheet is parsed in admin-node, not the browser, because admin-node already
carries `exceljs` — the wizard would otherwise need a spreadsheet library of its
own to read a file whose contents it immediately posts back. Header aliases are
accepted (`email` / `email id` / `e-mail`, `mobile` / `phone number`, …), rows
with no usable email and duplicate emails are dropped, and the **count of
skipped rows is returned and shown** — a dropped row is a candidate who would
not be invited. Rosters are returned in full for the same reason: silently
sampling a cohort the admin was told held N students would float to fewer people
than promised.

**A recipient row must be complete before it is floated** (2026-08-20).
`parseCandidateSheet` answers with `{name, email, mobile}` — a sheet has no
institute column, so admin-node never sends one — while the wizard's
`RecipientCandidate` also carries `instituteName`. The mix-match BFF built its
`bulkUploadData` by reading `candidate.instituteName.trim()` off every
recipient, so an **uploaded row, or a saved custom list cloned from one, threw
`TypeError: Cannot read properties of undefined (reading 'trim')`** before the
handler's `try` — which Next answers as a bare 500, with no error body for the
wizard to show ("Float responded 500"). Picking an existing institute batch was
never affected: `/api/entities/batches` already filled the column with `""`.

Two fixes, source and boundary: `parse-sheet` now fills `instituteName` on every
parsed row, and the row builder lives in `src/lib/assessments/bulkUploadRows.ts`
and **coerces every column instead of trusting it** (`typeof v === "string" ? v.trim() : ""`).
The draft is client input arriving from three recipient sources that do not all
write the same fields, so one absent column must not be able to fault the float.
A real admin-node refusal now surfaces as its own message again instead of
being masked by a 500.

**Corporate has no suggested lists** — there is no enrolled population behind a
company, so the section says so rather than rendering an empty box that reads as
a failed load. Custom lists work for both segments.

**Type-list ordering.** Only Pre-Assessment Registration is pinned (first,
undraggable, lock icon instead of a grip). AI Interview was briefly pinned last
the same way (`a78c17b`) — that was never a requirement and was reverted in
`eee9ddb`, including in the mix-match payload builder, which now maps
`draft.typeKeys` directly with no reordering. AI Interview is freely draggable.

**Evaluation parameter descriptions are back** (2026-08-20). The BFF mapped each
suggested parameter down to `{name, weight}` and threw the description away.
That is not cosmetic: the interview engine serialises the whole parameter into
both the question-generation and the scoring prompt, so the description is what
tells the model what a bucket measures — without it the interview was questioned
and scored against bare names. v1 forwarded `ai.parameters` verbatim and never
had this. Each row now carries its description under the name and weight.

**Field changes worth knowing:** Listening audio accent is now a two-option
RadioCardGroup (`US`, `Indian`, default `US`) rather than a five-option
dropdown; Role Based's Industry/domain carries the standard optional tag (it was
always optional in practice — `buildJobDescription` treats blank as absent — it
just did not say so); AI Interview's Difficulty curve select is gone from the
config panel but the field remains in `AiInterviewConfig`, `defaultConfig` and
the mix-match payload defaulting to `"Flat"`, the same way Probing Style was
removed earlier and still defaults to `"Neutral"`.

**Assessment validity is the window, said the other way round** (2026-08-26).
Step 3's Assessment Configuration panel shows an **Assessment validity (days)**
box next to Assessment duration on every **one-time** float, corporate and
college. It is not a field of its own: typing `N` moves the **end date**, and
moving the end date re-derives `N` (`windowDays` / `addDays` in
`src/lib/assessments/schedule.ts`, wired through `windowValidityDays` /
`setWindowValidityDays` in `useAssessmentWizard`). `end = start + N` matches the
arithmetic admin-node applies to a schedule's `assessment_validity_days`, so
both flows mean the same thing by "N days".

It is derived rather than stored because **a standalone number here would be a
dead control, and was one**. `POST /assessment/assignMixMatchAssessment` takes
`startDate`/`endDate` verbatim and has no `assessment_validity_days` — the BFF
has only ever sent validity on the recurring-schedule branch. The corporate
panel nonetheless carried its own validity input from the start, posted nowhere,
so every one-time float ignored whatever was typed into it. That is the
"Corporate: Assessment Validity — whatever we set it gives the default only"
report. `d176182` (UAT) / `bd45305` (Development) answered it by **deleting** the
input on 2026-08-21, which left the admin with no way to say how long a
candidate gets; deriving it from the window restores the control and makes it
impossible for the box to disagree with what is actually sent.

**A recurring schedule keeps its own separate validity input** inside
`RecurringSchedule`, and that one really is a stored column
(`assessment_schedules.assessment_validity_days`) sizing **each generated run** —
a different number from the schedule's overall start/end window, which the single
window cannot express. Corporate never reaches it: recurring schedules are
college-only (`unschedulableSelectionReason`), because the nightly scheduler
assigns with `isOtpInvite: false` and would send a corporate candidate the
password-flow email instead of an OTP. v1 draws the same boundary — its validity
input lives inside the `entityType !== 'corporate'` scheduled-distribution block
(`AssessmentSelect.js`), so corporate never had one there either.

Round-trip, month/year-boundary and empty/backwards-window cases are covered in
`src/lib/assessments/schedule.test.ts`. See also
[Assessment/schedule.md](../../Assessment/schedule.md) for the matching
admin-node fix — the immediate diagnosis assign used to hard-code a 10-year
window and ignore the configured validity.

## Auth — admin-node wants the RAW token

v2 is same-origin with v1, so it reads v1's JWT from `localStorage.token` (falling
back to the redux-persist `persist:root` → `auth` slice) and forwards it to its own
Route Handlers as `Authorization: Bearer <token>`.

**`admin-node`'s `verifyToken` feeds the entire `Authorization` header straight into
`jwt.verify()` — it does not strip a `Bearer ` prefix.** `lib/api/adminNode.ts`
therefore sends the **raw** token, matching v1's `utils/adminRequest.js`; a
Bearer-prefixed header 401s. The auth service behaves the same way. Only the BFF
itself speaks Bearer.

## Env

Server-only (read at runtime): `ADMIN_API_URL`, `AUTH_API_URL`.
Baked into the client bundle at build time by `next build`: `NEXT_PUBLIC_BASE_PATH`
(`/v2`), `NEXT_PUBLIC_V1_BASE` (empty = same origin), `NEXT_PUBLIC_LOGIN_URL`.

A DEV-built image calls DEV APIs forever regardless of the container's runtime env —
build each environment's image for that environment. The `Dockerfile` refuses to
build without `.env.prod` rather than silently baking an env-less bundle.

## Ports

DEV: institute-react-v2 :3011, corporate-react-v2 :3012, **admin-react-v2 :3013**.
UAT numbers them differently — 3011 is `pil-ai-learning` there, so institute is
:3012, admin :3013 and corporate :3014. Never copy a port from a DEV unit file.
Full UAT topology:
[Infrastructure/v2-apps-uat-topology.md](../../Infrastructure/v2-apps-uat-topology.md).
