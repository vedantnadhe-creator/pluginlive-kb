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
