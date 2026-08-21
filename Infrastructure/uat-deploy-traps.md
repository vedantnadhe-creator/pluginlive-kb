# UAT deploy traps — things `auto_deploy.sh` gets wrong or silently loses

Production-truth as of 2026-08-20. Companion to
[uat-docker-build.md](uat-docker-build.md) (apt/network failures) and
[v2-apps-uat-topology.md](v2-apps-uat-topology.md) (the Next.js v2 apps).

## "Behind" is not one number — check both directions

`git rev-list --count HEAD..origin/UAT` tells you the box is missing commits. It
does **not** tell you the box is *worse*. Two services on UAT are **diverged**,
with the box carrying work that `origin/UAT` does not:

| Repo | Box | What deploying `UAT` would destroy |
|---|---|---|
| `Resume_parser` | `master` @ `d3ee51f`, 2 commits ahead | the CV-download retry/backoff + PDF/DOCX/DOC magic-byte validation (`657bab7`) and per-module LLM spend tagging (`d3ee51f`). `origin/UAT` is `13dfad6` "Moving to UAT" from 2026-06-30, which predates both. |
| `Llama-JD-Parser` | `release-v1.22.4` @ `99e230a`, 1 ahead | its SonarQube config, and the pinned release branch itself |

Both also carry **uncommitted** modifications (`Resume_parser`: `USING API/.env`,
`USING API/Dockerfile`; `Llama-JD-Parser`: `backend.Dockerfile`, `main.py`,
`requirements.txt`). `git_commands` runs `git stash` first, so a deploy pushes
those into the stash and builds without them.

**So "just deploy everything that is behind" would roll UAT back on both.**
Before deploying either, someone has to decide the direction deliberately:
`Llama-JD-Parser`'s `origin/UAT` does carry wanted work (LiteLLM gateway routing
+ PostHog, `b78f0c5`/`e0c4d4d`), but taking it means leaving the pinned release
branch.

Repos with **no `UAT` branch at all** — `Static-website` (on `Testing`),
`eduspeak-india-node`, `eduspeak-india-react` (both on `main`) — are not part of
this promotion flow and are not "behind".

## mandate-node / mandate-react were unreachable through the script

Fixed 2026-08-20. Both are one repo with the app in a **subdirectory**
(`api/mandate-node/backend`, `frontend/mandate-react/frontend`), and dedicated
blocks at the end of `deploy.sh` (`APP_NAME == 18` / `19`) `cd` into it
correctly. Those blocks were **never reached**: the generic branches above them

```bash
if [[ "$TYPE" == "api"  && ... && "$APP_NAME" != "20" && "$APP_NAME" != "21" ]]
elif [[ "$TYPE" == "frontend" ]]
```

matched first, `cd`'d to the **repo root**, found no `Dockerfile` there and
`exit 1`'d:

```
ERROR: failed to solve: failed to read dockerfile: open Dockerfile: no such file or directory
!!! BUILD FAILED — old container left running !!!
```

The guards now also exclude `18` and `19`, so control falls through to the
dedicated blocks. Anything else whose Dockerfile is not at its repo root needs
the same exclusion.

## auth-react: `.env.uat` is now untracked, and the deploy needs it

`origin/UAT` commit `0cce393` **deletes `.env.uat` from git** (correct — secrets
do not belong in the repo), but `deploy.sh`'s frontend branch still does:

```bash
cp .env.uat .env
source .env.uat
```

So a box updating past that commit loses the file and the deploy builds with no
env. It was restored by hand on UAT on 2026-08-20 and the build verified to
point at `api-auth.uat` / `auth.uat`.

**It is untracked and NOT gitignored**, so `git clean -fd` or `git stash -u`
would delete it and the next deploy would produce an env-less login app. A copy
is kept at `~/auth-react.env.uat.backup.<UTC>` on the UAT box. The real fix is
to add `.env.uat` to that repo's `.gitignore`.

Its six keys: `REACT_APP_AUTH_API`, `REACT_APP_PASSWORD_MASK_SECRET`,
`REACT_APP_AUTH_PAGE_URL`, `REACT_APP_STATIC_PAGE_URL`,
`REACT_APP_GOOGLE_AUTH_URL`, `REACT_APP_GOOGLE_CLIENT_ID`.

## Concurrent deploys are normal on this box

Several people deploy to UAT through the day. A repo can move between the survey
and the deploy — `student-node` landed on a commit two behind `origin/UAT` on
2026-08-20 because two commits were pushed while its image was building, and
needed a second run. **Re-check the deployed SHA after every deploy** rather
than assuming the one you merged is the one now running.

## admin-node's Dockerfile env copy — the trap that broke PROD twice

`admin-node/Dockerfile:39` must read:

```dockerfile
COPY .env.${ENVIRONMENT} .env
```

It has twice been regressed to a bare `COPY .env .env`, and each time that broke
the **production** image build with `"/.env": not found` — on release-v1.37
(2026-08-11, fixed by c8fbe1f) and again on release-v1.38 (2026-08-21).

### Why the bare form looks fine and is not

Each environment builds with its own build-arg and ships its own env file. Only
prod has no plain `.env` to fall back on:

| Env | Build arg | Env file written by the deploy | Bare `COPY .env .env` |
|-----|-----------|-------------------------------|-----------------------|
| DEV | `--build-arg ENVIRONMENT=dev` (`.github/workflows/dev-admin.yml`) | `.env.dev` — and a plain `.env` also exists on the box | works by accident |
| UAT | `--build-arg ENVIRONMENT=uat` (`deploy.sh:201`) | `deploy.sh` does `cp .env.uat .env` | works by accident |
| PROD | `--build-arg ENVIRONMENT=prod` (`autodeploy_noprune.sh:143`) | `autodeploy_noprune.sh:119` writes **`.env.prod` only** | **build fails** |

So the regression is invisible on DEV and UAT and only ever surfaces at the
worst moment — mid-release, on the prod builder box.

The `.dockerignore` settles the intent: it excludes `.env*` then explicitly
whitelists `!.env.dev`, `!.env.uat`, `!.env.prod` — never a bare `.env`. The
parameterised form is what the build context was designed for.

### Why it kept coming back

Prior fixes were applied **only to the release branch**. `origin/UAT` kept the
broken line, so the next release cut from UAT reintroduced it. As of 2026-08-21
the fix is on **Development (44154d4), UAT (1fc2347) and release-v1.38
(262bd4e)**, so a future release cut from UAT carries the correct line.

If a prod admin-node build ever fails with `"/.env": not found` again, check
line 39 before anything else — and fix it on all three branches, not just the
release branch.

## institute-react-v2's container files were release-branch-only

`institute-react-v2` has been live in PROD since release-v1.37, but its
`Dockerfile`, `.dockerignore` and `next.config.ts`'s `output: "standalone"`
were authored **directly on the release branch** (`063a9f7` / `f74e524`) during
that first onboarding and never merged back. `Development` and `UAT` never had
them.

Every release is cut from `origin/UAT`, so every release lost them, and the
prod build died with:

```
ERROR: failed to solve: failed to read dockerfile: open Dockerfile: no such file or directory
```

That is exactly the admin-node shape above: a release-branch-only fix that
cannot survive the next cut. It recurred on release-v1.38 (2026-08-21) and had
to be re-applied a second time (`409e6b4`).

As of 2026-08-21 the files are on **Development (`855c849`), UAT (`8c526ec`)
and release-v1.38 (`409e6b4`)** — byte-identical blobs on all three
(`Dockerfile a6436156`, `.dockerignore 3fe2fee9`, `next.config.ts bc8c7b73`).

The Dockerfile is env-agnostic, matching the other v2 apps: the deploy writes
the target environment's central env file to `.env.prod`, and the Dockerfile
renames it to `.env.production`, the filename Next actually loads for a
production build. It hard-fails when `.env.prod` is absent rather than baking an
env-less bundle. Note this means **a UAT image cannot be built until someone
adds a UAT env file** — institute-react-v2 runs on UAT under systemd
(`next start`), not Docker, so no UAT env file exists yet.

## `autodeploy_noprune.sh` silently shipped DEV URLs to PROD (student-react)

On 2026-08-21 the `release-v1.38` **student-react** image reached production
baking `api-*.dev.pluginlive.com` and `auth.dev.pluginlive.com` — and **no prod
URLs at all**. `student.pluginlive.com` called DEV APIs and DEV auth for about
23 minutes before it was rolled back.

The cause is a divergence between the two prod deploy scripts:

| | writes `.env.prod` | also writes `.env` |
|---|---|---|
| `autodeploy.sh` | all frontends | **student-react only** |
| `autodeploy_noprune.sh` | all frontends | **nothing — the special case was missing entirely** |

student-react's `.env` is **git-tracked and holds DEV values**, and its
`webpack.prod.js` loads `../.env` via dotenv — not the `.env.prod` the deploy
writes. `autodeploy.sh` compensates by overwriting `.env`; `autodeploy_noprune.sh`
never did. Since `prod_deploy_notify.sh` **always** uses the noprune variant for
parallel releases, every parallel release built student-react from its tracked
DEV `.env`. The 2026-08-04 image escaped only because it was rebuilt by hand
with `autodeploy.sh` after a yarn timeout.

`admin-react` has the same shape — `config/webpack.prod.js:13` also reads
`../.env` — but its `.env` is untracked and hand-placed with prod values, so it
leaked nothing. It did mean every edit to the central
`repositories/envs/ui/admin-react.env` was silently ignored.

Both scripts now copy the central env to `.env` for **student-react and
admin-react**. The lasting lesson: **an HTTP 200 smoke check does not prove a
bundle points at the right backend.** After any frontend build, grep the image:

```bash
docker export $(docker create <image>) | tar -xO | grep -aoE '[a-z-]+\.dev\.pluginlive\.com' | sort -u
```

Empty is the only acceptable result.
