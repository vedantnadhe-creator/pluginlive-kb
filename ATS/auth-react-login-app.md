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

## Password reset revokes the temporary password (2026-09-16, DEV+UAT)

`user_management.users` carries two credentials: `password` (sha256) and
`temp_password` (the encrypted invite/temporary password that corporate invites
and admin "temporary password" flows mint). Sign-in accepts either. Forgot-password
and change-password in `user-management-node` (`app/handlers/user.js`) used to
write only `password`, so the **old temporary password kept working after a
reset** — the candidate could log in with both. Both handlers now also null
`temp_password`. Covered by `test/handlers/passwordReset.spec.js` (reset → old
temp password refused, new password accepted).

## Session lifetime: 2-day access token + 30-day refresh cookie (2026-09-22 DEV, 2026-09-23 UAT)

Portal access tokens used to last **12 hours** with no way to renew — everyone
was signed out mid-day. (`LOGIN_TOKEN_EXPIRES_IN=43200000` reads as a *string*,
which `jsonwebtoken` parses as **milliseconds**, not the ~500 days a bare number
would mean.) Access tokens are now **2 days** and renew silently from a
**30-day refresh token**.

`user-management-node` is the only issuer; corporate/institute/student/admin-node
still just `jwt.verify` the access token and needed no change.

**Server** (`user-management-node`)

- `app/services/refreshToken.js` — 48 random bytes, stored only as a **SHA-256
  hash** in `user_management.refresh_tokens`, 30-day expiry.
- `POST /user/token/refresh` — authenticated *by the cookie only*. Rotates:
  the presented token is revoked and a replacement issued, and a new access
  token is returned in `data.token`.
- **Rotation safety.** A replay within 60s is treated as the two-tabs race and
  allowed (both tabs refreshed at once). A replay *after* that window means the
  token leaked, so **every session for that user is revoked**. Explicit
  revocation also back-dates `expires_at`, so a revoked token can never slip
  through the grace window.
- Revoked on sign-out (`POST /users/signout`, cookie forwarded), password reset
  and password change.
- The cookie `pl_refresh_token` is **httpOnly, Secure, SameSite=Lax**, scoped to
  the parent domain (`.uat.pluginlive.com`, `.pluginlive.com`) so every portal
  sub-domain sends it. `REFRESH_COOKIE_DOMAIN` defaults to the parent of
  `AUTH_FE_BASE_URL`.
- CORS changed from a blanket `origin: '*'` to a delegator: our own sub-domains
  (and localhost) get `credentials: true`; every other origin keeps the old
  wildcard, credential-less access.

**Clients**

- v1 webpack apps (`auth-react`, corporate/admin/institute/student-react,
  `Assessment-React`): `src/utils/sessionRefresh.js`, installed on every axios
  instance by `initApiServices.js`. It refreshes proactively when the token has
  <5 min left, and once more on a 401 before retrying the request. Invite-scoped
  candidate JWTs are deliberately left alone. `auth-react` needed
  `withCredentials: true` or the browser discards the sign-in `Set-Cookie`.
- v2 Next apps (corporate/admin/institute/assessment-react-v2): the browser
  cannot reach `api-auth` with credentials, so a BFF route
  `POST <basePath>/api/auth/refresh` forwards the cookie server-side and relays
  the rotated `Set-Cookie` back. `lib/sessionRefresh.ts` runs it on mount, on tab
  focus and every 5 minutes; the new token is written to **both**
  `localStorage.token` and the redux-persist `auth` slice, because v1 reads the
  latter.
- **Admin check-out** (`/api/checkout`) relays `portalSignin`'s `Set-Cookie`.
  Without that, the refresh cookie still belongs to the corporate/institute
  session and the next refresh silently resurrects the identity the admin just
  left.

**Operational notes**

- Schema: `DB-Scripts/Auth Refresh Tokens/20260922T093156Z__auth_refresh_tokens.sql`
  (DEV + UAT applied; PROD pending).
- Each env's UMS env file must carry `LOGIN_TOKEN_EXPIRES_IN=2d` — the code only
  falls back to `2d` when the variable is **absent**, so an env still holding
  `43200000` keeps 12-hour tokens even with the new build. PROD's value lives in
  the `auth-api-config` ConfigMap and is still 12h.
- `@fastify/cookie` was added, so the UMS image must be rebuilt, not restarted.
- On the deploy itself, everyone signed in beforehand has no refresh cookie:
  their current token runs out its clock, the first refresh 401s and they get one
  clean redirect to the login page. This happens once per rollout.

Verify after a deploy:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  https://api-auth.uat.pluginlive.com/user/token/refresh    # 401 = route is live
# sign in, then check the token really lasts 2 days:
#   the redirectLink's ?token= payload should have exp - iat == 172800
```
