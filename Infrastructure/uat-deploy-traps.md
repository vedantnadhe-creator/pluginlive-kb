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
