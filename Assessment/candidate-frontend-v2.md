# Candidate assessment frontend — `assessment-react-v2` is where changes go

**Decision recorded 2026-08-26.** The candidate-facing assessment experience has
moved to **`assessment-react-v2`**. Any new assessment work — bug fix, UI change,
proctoring rule, new question type — is written in **v2**. The legacy
`Assessment-React` app is **maintenance-only**: touch it only to keep a path that
still routes through it alive, and when you do, decide deliberately whether the
same change is also needed in v2 (it usually is — see *The code is not shared*).

Companion docs: [mix-match-candidate-journey.md](mix-match-candidate-journey.md),
[../Infrastructure/v2-apps-uat-topology.md](../Infrastructure/v2-apps-uat-topology.md),
[../ATS/Institute/v2-strangler-fig.md](../ATS/Institute/v2-strangler-fig.md).

## The two apps

| Repo | Checkout | Stack | Where it runs |
|---|---|---|---|
| `Assessment-React` (v1, legacy) | `~/frontend/Assessment-React` | CRA-style React + webpack, styled-components | DEV: docker `assesment` :3006 · UAT: docker · serves `/` |
| `assessment-react-v2` | `~/frontend/assessment-react-v2` | Next.js App Router + TS, `output: standalone` | DEV + UAT: docker `candidate-assessment-journey-v2` `127.0.0.1:3015→3000` · PROD: live |

Both sit on the **same host** (`assessment.<env>.pluginlive.com`) — a strangler
fig, exactly like institute-react-v2 and corporate-react-v2. Same origin means
the candidate's session survives crossing the seam.

```
assessment.<env>.pluginlive.com
  ├─ /                                → Assessment-React (v1)  :3006
  └─ /candidate-assessment-journey/v2 → assessment-react-v2     :3015
```

The prefix comes from **`NEXT_PUBLIC_BASE_PATH`** (`next.config.ts`, default
`/v2`), baked at build time, plus the matching nginx `location` blocks — which
must sit **above** `location /` or the v1 SPA swallows them. Verified 200 on
DEV, UAT and PROD (2026-08-26).

## What still reaches v1 — read this before assuming a v2 fix shipped

`admin-node/app/helpers/assessmentInviteEmail.js` → **`buildStartUrl()`** is the
single place that decides which app a candidate lands in, and today it still
branches:

| Invite | URL built | App that serves it |
|---|---|---|
| Mix & Match float | `/candidate-assessment-journey/v2?inviteToken=…` | **v2** |
| Single assessment | `/assessment/start/<inviteToken>` | **v1** |

Short links (`/s/<code>`, `buildInviteUrl` → `InviteShortLinkService`) resolve
through that same function, so they inherit the same split.

**Consequence:** until that branch is flipped, a fix made only in v2 does not
reach a candidate who opened a single-assessment invite. When you fix something
a candidate can hit *today*, check which of the two URLs their invite carries.
The direction of travel is that everything moves to the v2 URL; the branch is
the thing to delete when it does.

## The signed-in student handoff (`?assigned=`)

Institute students never get an invite: they sign in, see their assessments on
the **v1** dashboard, and pick one. v1 no longer runs any assessment itself —
`Assessment-React` `src/modules/Assessments/index.js` hands every chosen
assignment straight over, in the same tab:

```js
window.location.assign(
  `/candidate-assessment-journey/v2/assessment?assigned=<assessment_assigned_id>&back=<dashboard path>`
)
```

v2 (`src/app/assessment/page.tsx`) trades the student's login for the same
scoped session an invited candidate holds, via
`POST /v2/api/assessment/session/:assessmentAssignedId` →
student-node `POST /students/assessments/:id/session`. Past that point the two
kinds of candidate are indistinguishable, which is the point.

**Completion returns institute students to v1 (2026-08-31).** The v2 completion
page uses the trusted return-path marker created by the signed-in handoff to
distinguish institute students from invite candidates. After clearing the
scoped sitting, an institute student is hard-redirected with
`window.location.replace('/assessment')`, crossing the nginx seam back to the
v1 student assessment dashboard without leaving the completed flow in browser
history. Invite/OTP candidates have no return marker and remain on the existing
completion screen. Implemented in `src/app/assessment/complete/page.tsx` with
the pure `src/lib/completionRedirect.ts` policy. Development `c20751e`; UAT
merge `317b46a`; deployed and HTTP 200 verified on DEV and UAT.

**The `assigned` id is used once, to mint the token — and never again.**
Everything downstream (`/students/mix-match/summary`, questions, save, submit,
proctoring) takes the assignment from `req.user.assessmentAssignedId` inside the
scoped JWT. The URL is not consulted.

> **Bug fixed 2026-08-31 — the session must be keyed on WHICH assignment.**
> The guard was `if (assigned && !sessionStorage.getItem(scopedJwt))`: mint a
> session only when the tab holds none. But a scoped session survives every exit
> except `/assessment/complete` (the only caller of `clearInviteSession()`) — a
> Back out of the summary, the error screen's *Return to overview*, an abandoned
> readiness check. And v1 hands over **in the same tab on the same origin**, so
> `sessionStorage` carries across the seam by design.
>
> So the second assessment a student opened silently ran the **first one's**
> session, and nothing downstream could notice because nothing downstream reads
> the URL. On a diagnosis pair this surfaced as *"took Assessment #2 first, now
> I can't take Assessment #1"*: opening #1 re-served #2, which the start guard
> refused with 409 `ALREADY_COMPLETED`. It worked on another machine because
> `sessionStorage` is per tab.
>
> The guard is now `needsNewStudentSession(assigned, heldAssignedId)`
> (`src/lib/sessionSwitch.ts`, import-free so `node --test` can reach it):
> re-mint whenever the URL names a different assignment, after
> `clearInviteSession()` and `forgetReturnTo()` drop the previous sitting. A
> refresh mid-attempt still resumes, because the id matches.

## What counts as a diagnosis

**The stored `assessment_assigned_students.is_diagnosis` flag, written by
admin-node at assignment time — never the assessment's name, and never a
missing `schedule_id`.** Both guesses were in the candidate path until
2026-08-31 and both hid assessments students still had to sit:

| Guess | Where it was | How it broke |
|---|---|---|
| `title === "Assessment #1" \|\| "Assessment #2"` | v1 `AssessmentTable.js` — hid diagnosis from the regular table | A **scheduled** float named that way vanished from the dashboard (38 such rows on UAT); a renamed diagnosis appeared twice |
| same names | student-node `Assessment.js`, choosing Email Writing vs Dictation | Renaming the float dropped **both** sittings into the random branch, so the pair could get the same written format twice |
| `!corporateMapId && !instituteMap.scheduleId` | student-node `getActiveAssessments`, start guard, reload guard; admin-node TPO diagnosis-score queries | Every unscheduled Behavior / Role_Based / Custom / AI Interview assignment was labelled a diagnosis (2,532 rows on DEV, 740 on UAT) — and v1 hides diagnosis rows from its regular table, so that label is what made them unreachable |

Two further v1 rules changed with it:

- The diagnosis section shows **every** diagnosis still on the active list. It
  used to trim to `slice(0, 2 - completedOfThisType)`, counting unrelated
  completed papers — and the trimmed-off row was hidden by the table's title
  filter too, so it could be reached from nowhere. A submitted diagnosis has
  already left the active list, so there is nothing to trim.
- Regular assessments lock while *a diagnosis of that type is still
  outstanding*, rather than while *fewer than 2 of that type are completed*.
  The old rule locked a student who was never assigned a diagnosis at all.

The Communication pair now derives its written format from the pair itself
(`student-node/app/helpers/diagnosisPair.js`): a sitting serves whichever format
its sibling did not, so the pair is correct **whichever one is sat first**, and
falls back to a stable id-based split when neither has started. Tests:
`student-node/test/diagnosisPair.spec.js`.

The institute side already read the flag — see
[institute.md](institute.md) → *Assessment type classification* and
`ATS/Institute/v2-strangler-fig.md` → *Diagnosis ownership is stored, not
inferred*.

## The code is not shared

v2 is a rewrite, not a wrapper. There is **no shared package** between the two
apps — each carries its own copy of the same concerns, under different names and
languages:

| Concern | v1 | v2 |
|---|---|---|
| Device capability tiers | `src/utils/deviceTier.js` | `src/lib/deviceTier.ts` |
| Fullscreen enforcement | inline in each `Partials/*/assessment.js` | `src/lib/fullscreen.ts` |
| Proctoring events | `src/utils/useProctoringCollector.js` | `src/lib/proctoringEvents.ts` |
| Tab-switch / violation counting | per-assessment-type, 5 copies | `src/app/assessment/take/page.tsx` (one place) |

So **porting is manual and is never automatic**. A worked example: the
mobile-call auto-submit fix. An incoming call backgrounds the page, and mobile
browsers report that identically to a deliberate app switch, so three calls
auto-submitted the paper. Fixed independently in each app, because there is
nothing to share — v1 as `Assessment-React` `448f87f` (DEV 2026-08-26), v2 as
`assessment-react-v2` `078241a` + `17bfa86` (DEV + UAT 2026-08-26). In v2 the
`isMobileDevice()` helper lives in `src/lib/deviceTier.ts` rather than a new
module — `node --test`
resolves sibling `.ts` imports by real path with no extension, so a test-covered
lib file here has to stay import-free (`proctoringEvents.ts` documents the same
constraint). `watchVisibility` and the `fullscreenTransition` exit in
`src/app/assessment/take/page.tsx` both now check
`isMobileDevice()` before counting a `TAB_VIOLATION` on the visibility change —
but **not** on the fullscreen exit, which counts everywhere (`17bfa86`; a phone
reports a deliberate app switch as a fullscreen exit and nothing else, so
exempting it made switching away free). See
[mix-match-candidate-journey.md](mix-match-candidate-journey.md) for the table.

One structural advantage when you do port: v1 repeats the violation logic once
per assessment type (Aptitude, Communication, Hinglish, Custom, Role-Based), so
a v1 fix is a five-file edit. v2 runs every type through one `take/page.tsx`, so
it is one.

## Deploying

**DEV** — push to `Development`; CI builds and swaps the container.

**UAT**
```bash
ssh ubuntu@uat.pluginlive.com
./auto_deploy.sh candidate-assessment-journey-v2 UAT     # menu id 22, type nextjs-docker
```

The build **must** run on the target box. `next build` inlines every
`NEXT_PUBLIC_*` into the client bundle, so a DEV-built image sends UAT
candidates to DEV APIs. The `nextjs-docker` deploy branch greps the built image
for `dev.pluginlive.com` and **fails the deploy** rather than serving it.

`NEXT_PUBLIC_DEMO_MODE` must stay absent outside DEV — it is what opens the
invite-less demo journey with the fixed OTP `123456`. See
[mix-match-candidate-journey.md](mix-match-candidate-journey.md).

## Analytics — PostHog in v2 (DEV + UAT 2026-08-31, PROD pending)

v2 shipped with **no analytics at all** until `4e9fe59`. v1's configuration and
event catalogue are now ported character for character, so both candidate
journeys land in **one funnel** and the existing insights keep working:

| Piece | v1 | v2 |
|---|---|---|
| Init + identify | `src/utils/posthog.js` | `src/lib/posthog.ts` |
| Event catalogue (36 events) | `src/utils/assessmentEvents.js` | `src/lib/assessmentEvents.ts` |
| Init call site | mount effect in `src/App.js` | `src/app/_components/PostHogInit.tsx`, mounted in the root `layout.tsx` |
| Passive view/section events | scattered per assessment type | `src/app/_components/useExamAnalytics.ts` |

Init config is **identical** to v1 (`capture_pageview: false`, `autocapture:
false`, `capture_heatmaps: false`, `capture_performance: false`,
`capture_exceptions: true`, `maskAllInputs: true`,
`session_recording.sampleRate: 0.3`) — see the v1 write-up in
[otp-invite.md](otp-invite.md) for why the funnel is built from explicit
`invite_*` / `assessment_*` events rather than `$pageview`.

**Init is on mount, never gated on knowing the candidate.** This is the v1 bug
(fixed 2026-07-31) that made the entire OTP invite journey invisible for months.
v2 is invite-first, so the same mistake would cost more here.

### The event names are a contract — including the misspellings

`after_voilation`, `voilation_type`, `assessment_practice_session_dropedoff`,
`assessment_droppedoff`, `assessment_diagnosis_droppedoff` are carried over
**deliberately**. The existing insights are keyed on them; correcting them in
one app silently splits every chart in two. They change in a single migration
across both apps, or not at all. `src/lib/assessmentEvents.test.ts` pins the
full catalogue and fails the build if a name drifts.

The **diagnosis and practice events ship unwired** — v2 has no placement-prep
surface yet. The catalogue stays whole so those screens need no second migration
of event names when they land.

### Three deliberate departures from v1 (emitted property names unchanged)

- **The session spine is read, not threaded.** v1 passes
  `assessmentAssignId / assessmentType / isCorporate / entityName` down as four
  positional arguments through every component, which is why so many v1 events
  carry `undefined`. v2 reads them once from the tab's session
  (`INVITE_SESSION_KEYS`). **Invite events deliberately opt out** — they fire
  before a session exists, and on a shared browser the only thing
  `sessionStorage` could offer them is the *previous* candidate's assignment.
  The test asserts every `invite_*` event bypasses the spine helper.
- **`answer_value` reports prose by shape.** Choices go through exactly as v1
  sends them; `text` / `email` / `code` report `{ kind, length }` instead of the
  candidate's essay or source file, which is neither wanted nor readable in
  analytics and is already held properly by `student-node`.
- **Right-click is reported, not blocked.** v1 suppresses the context menu; in
  v2 `assessment_right_click` is a listener only.

### The DEV/UAT token split — the trap

There are **two PostHog projects**, and v2's `.env.uat` must not inherit DEV's:

| Env | Token | Project |
|---|---|---|
| DEV | `phc_YgAbqn…` | dev project |
| **UAT / PROD** | **`phc_y6PmDwg…`** | **"Assessment" (241173)** — what v1 `assessmentreact` and the other UAT frontends use |

The first UAT build of v2 went out carrying the **DEV** token, which sends UAT
candidate traffic into the dev project and defeats the whole point of the port.
Corrected the same day. `NEXT_PUBLIC_ENVIRONMENT` (`dev` / `uat`) is registered
as a super-property on every event and is what keeps the environments separable
inside the one project — set it, or every UAT row is indistinguishable from
production.

Confirm what a built image actually carries before trusting a deploy:

```bash
docker exec candidate-assessment-journey-v2 sh -c \
  'grep -rhao "phc_[A-Za-z0-9]\{20,\}" /app/.next/static | sort -u;
   grep -rho "environment:.[a-z]*." /app/.next/static | sort -u'
```

`.env*` is **gitignored**, so these three vars live only on the box. A new
environment starts with PostHog silently disabled: `initPostHog` warns
`PostHog API key or host is not provided` and captures nothing. That is
deliberate — there is **no fallback key or host**, because a wrong default would
post one environment's candidate telemetry into another's project.

### Verifying it end-to-end (headless will lie to you)

posthog-js `isLikelyBot()` suppresses **every** `capture()` under a plain
headless browser while `init()` still runs normally — so the assets load, the
config request fires, and no `/e/` POST is ever made. That looks exactly like a
broken analytics deploy and is not; see the gotcha in
[otp-invite.md](otp-invite.md). Launch with
`--disable-blink-features=AutomationControlled`, a real desktop `userAgent`, and
an init script setting `navigator.webdriver` to `undefined`. Ingest payloads are
gzipped, so `gunzipSync` the request buffer to read event names.

Verified on UAT 2026-08-31 by opening the app with a bogus `inviteToken`:
`$opt_in`, `PostHog initialized` and **`invite_link_invalid`** (props
`reason: "Invalid invite link."`, `environment: "uat"`) all POSTed to `/e/`.

## Still v1's job

Nothing in this doc moves the **backend**. Both apps talk to the same
`student-node` / `admin-node` APIs; v2 added Route Handlers that reshape
existing responses, it did not fork the API. Scoring, progression, reports and
proctoring processing are unchanged and live where they always did — see
[README.md](README.md).
