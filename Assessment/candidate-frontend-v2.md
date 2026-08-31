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

## Still v1's job

Nothing in this doc moves the **backend**. Both apps talk to the same
`student-node` / `admin-node` APIs; v2 added Route Handlers that reshape
existing responses, it did not fork the API. Scoring, progression, reports and
proctoring processing are unchanged and live where they always did — see
[README.md](README.md).
