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
  The refresh POST must carry an **object** body (`{}`), never `null`: axios
  0.27 labels a null body `application/x-www-form-urlencoded`, which Fastify has
  no parser for, so the endpoint answered **415 before the handler ran** and the
  portal — which treats any refresh failure as "session over" — cleared the
  session and bounced the user to sign-in. Every v1 portal was affected until
  the first renewal after the 2026-09-23 fix; the v2 BFF routes never were,
  because `fetch` with no body sends no Content-Type at all.
- v2 Next apps (corporate/admin/institute/assessment-react-v2): the browser
  cannot reach `api-auth` with credentials, so a BFF route
  `POST <basePath>/api/auth/refresh` forwards the cookie server-side and relays
  the rotated `Set-Cookie` back. `lib/sessionRefresh.ts` runs it on mount, on tab
  focus and every 5 minutes; the new token is written to **both**
  `localStorage.token` and the redux-persist `auth` slice, because v1 reads the
  latter.
- **v2 401 handling (corporate/institute/admin v2, DEV+UAT 2026-10-15, PROD
  pending):** `installAuthFetch()` in `lib/sessionRefresh.ts` wraps
  `window.fetch` at import (not in an effect — child effects run before
  AppShell's). Every BFF call carrying the portal `Bearer` token (i.e. built
  with `authHeaders()`) renews the token first if it has <5 min left, and on a
  401 refreshes once and retries. If the refresh fails for any reason the
  session is cleared and the user goes to `NEXT_PUBLIC_LOGIN_URL`. A 401 that
  survives a successful refresh is returned to the caller (a permission error,
  not a logout). Calls with no / a foreign Authorization header pass through.
  Before this, the timer was the only renewal path, so PROD corp v2 logged
  `jwt expired` 401s on `/assessments/v2/usage` and `/users/v2/me/access` and
  pages failed silently instead of renewing or logging out.
  - Test: `institute-react-v2/src/lib/sessionRefresh.test.ts` (Node ≥ 22).
    E2E: log in via auth UI, then reload `/v2/...` with (a) a forged-signature
    copy of the token → expect 401 → `/api/auth/refresh` 200 → retry 200;
    (b) an `exp`-in-the-past copy → refresh before any call; (c) cookies
    cleared → redirect to auth. Seed the token with `addInitScript` on the v2
    URL — visiting a v1 route first bounces to sign-in and wipes `localStorage`.
  - (a) only exercises the 401 path on **corporate** v2: institute v2's BFF
    decodes the JWT without verifying it and calls institute-node
    `/institutes/dashboard/v2/*`, which are public routes, and admin v2
    `/api/assessments` also returned 200 for a forged signature (known
    security gap, 2026-10-15, unfixed).
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
# 415 instead of 401 means the caller sent a Content-Type the service cannot
# parse (urlencoded); the route only accepts application/json or no body:
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  https://api-auth.uat.pluginlive.com/user/token/refresh    # 415 by design
# sign in, then check the token really lasts 2 days:
#   the redirectLink's ?token= payload should have exp - iat == 172800
```

## Already signed in? The sign-in page skips the form (2026-11-17, DEV on / UAT off / PROD pending)

Opening the auth URL (or any app in a new tab with no local token, which bounces
to the auth URL) while this browser already has a live session goes straight to
the user's app, with no login form.

- **How:** on load (unless `?code=` from Google is present) `src/pages/login.js` calls
  `POST /user/session/resume` with credentials and a **5 s timeout**. The
  `pl_refresh_token` cookie is on the parent domain (`.dev.` / `.uat.` /
  `.pluginlive.com`), so a session started in any app is visible here.
  - 200 → `{ redirectLink }` (same hand-off link a fresh sign-in returns:
    `getLoginUrl(journey, access_level)` + `withLoginToken`) → `location.replace`.
  - anything else (no/expired cookie, flag off, timeout) → normal form.
- **Backend** (`user-management-node`): `exports.resumeSession` in
  `app/handlers/user.js`; it shares `rotateSessionUser` with `/user/token/refresh`, so
  the call rotates the cookie (same 60 s two-tab grace applies).
- **Per-env switch:** `SESSION_RESUME_ENABLED=true` in the UMS env. When unset, the
  endpoint returns **404 "Session resume is disabled."** and the page shows the form.
  - DEV: **on** (`.env.dev`).
  - UAT: **off by design.** Testers must be able to sign in as a different user
    without logging out. Code is deployed (UMS `b046d3e`, auth-react `37ea0d0`
    UAT port for the older UAT login UI).
  - PROD: intended **on**. Not shipped yet. Before enabling, confirm
    `REFRESH_COOKIE_DOMAIN` resolves to `.pluginlive.com`.
- **Logout must clear the cookie,** or a logged-out user is bounced straight back in.
  Legacy apps send `users/signout` with `withCredentials`. The v2 Next apps forward the
  browser `Cookie` header through `/api/logout`. On Development all apps do;
  the 2026-11-17 UAT checkouts of admin/corporate-react-v2 did not yet.
- **Limit:** with it on, switching user means logging out first. The multi-account
  `mat` token is not re-issued on resume, so the account switcher only appears
  after a password sign-in.
- **Verify:**
  ```bash
  curl -s -X POST https://api-auth.<env>.pluginlive.com/user/session/resume \
    -H 'Content-Type: application/json' -d '{}'
  # 404 "Session resume is disabled." = flag off (UAT); 401 "Refresh token missing" = on
  ```

## Sign in with a one-time code — email or mobile (2026-11-17, DEV + UAT, PROD pending)

The sign-in page (auth.<env>.pluginlive.com) now starts with **"Email or mobile number" → Send code → 6-digit
code → Sign In**. The answer is the same as a password sign-in: straight to the person's app, or **"Choose an
account"** when the email/mobile has several accounts — including the **LMS** (lmsv2) account, labelled "LMS".
"Sign in with a password instead" keeps the old email + password form.

| Piece | Where |
|---|---|
| Screen | auth-react `src/components/CodeSignIn.js` (+ `pages/login.js` toggle). DEV `0e2c159`; UAT `95a3cbd` (UAT now carries the same tree as Development, see below). |
| API | user-management-node `POST /user/signin/otp/request { identifier }` and `POST /user/signin/otp/verify { identifier, otp }` (DEV `5b51e1b`, UAT `56ff22b`). After the code, `finishSignIn` — the same code a correct password runs (student-record check, LMS account, single account → redirect + refresh cookie, several → sessionToken + accounts). Verify is audited like `/user/signin` (`AUTH_SIGNED_IN` / `AUTH_SIGN_IN_FAILED`). |
| Code rules | `app/services/otpService.js`, shared with the assessment / AI-interview invite code: 6 random digits, only an HMAC stored, 5-minute expiry, 30 s between codes, 5 tries per code counted atomically, single use. Sign-in codes also have **5 per hour and 10 per day per email/mobile**; an optional per-network cap is off unless `LOGIN_OTP_MAX_PER_NETWORK_HOUR` is set. |
| Storage | `user_management.assessment_invite_otps` with `purpose = 'login'` (`'invite'` for invite codes) and `network_hash`. DB-Scripts `Central OTP Sign-in/20261117T092054Z__otp_purpose_for_login_codes.sql` (DEV + UAT applied, PROD pending). The identifier key is the lower-cased email, or `mobile:<10 digits>`. |
| Delivery | Email identifier → email. Mobile identifier → SMS (MSG91 OTP template) when `SMS_ENABLED=true` (it is on UAT); with SMS off, the code goes to the account's email only when that number belongs to exactly one email, otherwise "sign in with your email". Mobile matching covers every stored phone form (encrypted or plain, with or without +91). |
| Password switch | `LOGIN_PASSWORD_ENABLED=false` in user-management-node `.env.<env>` makes `/user/signin` answer 403 and the page falls back to the code. Unset = password still works (both envs today). |

**Known trade-off:** like the password form, the request step says "No account found for …" for an unknown
email/mobile (account existence is visible). Kept for usability; the hourly/daily caps limit probing.

**Test accounts (DEV and UAT, same set-up):** `ravi.kotadiya+pl.only@pluginlive.com` (PluginLive admin only →
admin portal), `ravi.kotadiya+lms.both@pluginlive.com` (PluginLive admin + LMS admin → Choose an account),
`ravi.kotadiya+lms.only@pluginlive.com` (LMS admin only → LMS). Codes arrive in Ravi's inbox (plus-addressing).

## Redesigned sign-in pages on UAT (2026-11-17)

UAT auth-react now matches Development exactly (UAT `95a3cbd`, `git diff origin/UAT origin/Development` is empty):
the 2026-10-28 redesign (`5ebcfa5`) of sign-in, Choose an account, forgot password and reset password —
`AuthLayout` with the brand panel (testimonial carousel, client logos, hover-only WebGL background
`BrandShader`, static card without WebGL / with reduced motion), design-system tokens (`src/styles/ds-tokens.css`,
`auth.css`), Satoshi + JetBrains Mono fonts loaded from fontshare.com / Google Fonts in `public/index.html`,
Contact and Terms dialogs. Same React app, same `package.json`, same build and Docker image — no new stack;
Ant Design stays installed but these pages no longer use it. The earlier UAT-only ports (`37ea0d0` session resume,
`4872419` code sign-in) are replaced by the Development versions. Session resume still depends on
`SESSION_RESUME_ENABLED` in user-management-node (off on UAT), so UAT keeps showing the form.
