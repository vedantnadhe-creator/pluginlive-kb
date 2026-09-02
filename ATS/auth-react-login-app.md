# auth-react — the shared sign-in app

`auth-react` is the Create React App that serves the single sign-in page for the
platform: `auth.pluginlive.com` (PROD), `auth.uat.pluginlive.com` (UAT),
`auth.dev.pluginlive.com` (DEV). Every portal (admin, corporate, institute,
student) bounces unauthenticated users here and back via
`REACT_APP_AUTH_PAGE_URL`.

Runtime per env:

| Env | How it runs | Deploy |
|-----|-------------|--------|
| DEV | `auth-react.service` (systemd), build served from the checkout's `build/` | push to `Development`; GitHub Actions self-hosted runner builds + restarts the unit |
| UAT | container `authreact` from image `auth-react:frontend`, port 3000 | `./auto_deploy.sh auth-react UAT` on the UAT box (builds in Docker with `.env.uat`) |
| PROD | K8s `deployment/auth-react` in namespace `frontend` | `~/autodeploy.sh auth-react <release-branch>` on `140.245.25.134` (copies `repositories/envs/ui/auth-react.env` → `.env.prod`, buildx, push to OCIR, `kubectl set image`) |

Its `.env.uat` is untracked on the UAT box — see
`Infrastructure/uat-deploy-traps.md`.

## No PWA install prompt (2026-09-02)

The repo still ships the **stock CRA `public/manifest.json`** — that is why the
Chrome install dialog said *"Create React App Sample"* with the React logo.

Chrome treated the sign-in page as an installable PWA purely because that
manifest had `"display": "standalone"`; there is no service worker and no
`beforeinstallprompt` handler anywhere in the app. Users on `auth.pluginlive.com`
got an "Install app" dialog (and the omnibox Install button) over the login card.

Fix: `public/manifest.json` → `"display": "browser"`. That drops the page out of
Chrome's installability criteria, so the dialog and the omnibox button are gone,
while the manifest is still there for icons/theme colour. Applied on **DEV, UAT and PROD on
2026-09-02.** PROD ships from `release-v1.35` (auth-react's PROD line; the repo
has no newer release branch) via `~/autodeploy.sh auth-react release-v1.35` on
the prod box → image `pl-auth-react:2026-09-02-11-02-13-release-v1.35`.

Verify after a deploy:

```bash
curl -s https://auth.uat.pluginlive.com/manifest.json | grep -o '"display": *"[a-z]*"'
curl -s https://auth.pluginlive.com/manifest.json     | grep -o '"display": *"[a-z]*"'
# must print "display": "browser"
```

Anyone who already installed the PWA keeps their installed copy — the manifest
change only stops new install prompts.

Note the manifest `name`/`short_name` are still the CRA defaults ("Create React
App Sample" / "React App"). They are no longer user-visible now that the install
dialog cannot open, but they are worth renaming if the app is ever made
installable on purpose.
