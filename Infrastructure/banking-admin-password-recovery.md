# Banking LMS admin sign-in and password recovery

## Current behavior

On UAT and PROD, `/login` offers Candidate, Trainer / Institute and Admin. Administrators can go directly to `/login/admin`. Signed-out trainer and institute links open the staff sign-in page and retain the requested destination. An institute administrator can reach the institute workspace with an active institute role and profile even when the account has no trainer roster row.

Admin password sign-in accepts an email, mobile number or legacy short ID. `admin-email-login` resolves the identifier through `resolveAdminLoginIdentity`, verifies the assigned `admin` or `super_admin` role, and checks the password once against the matched Auth owner. Admin OTP and public password recovery use the same resolver. An exact Auth or profile match takes priority. When an email has no such match, a single approved trainer roster row can identify its linked administrator. Ambiguous matches cannot issue a session or a recovery link.

Recovery mail and email OTPs go to the administrator's real Auth mailbox, or to the registered profile mailbox when Auth uses an internal alias. The same contact rule applies when a multi-role administrator signs in through the trainer or candidate form. A roster alias only identifies the account. Both environments use `pluginlive_relay`. Unknown and mailboxless accounts receive a generic acknowledgement. A provider failure leaves the recovery dialog open for a retry.

Recovery messages contain both a button and the complete reset URL as visible, copyable text in the HTML and plaintext parts. The delivery helper creates a recovery token with the Auth admin API and sends the user directly to the approved LMS `/reset-password` route with `type=recovery` and `token_hash`. The public bases are `https://lms.pluginlive.com/sb` and `https://banking.uat.pluginlive.com/sb`.

The reset page redeems `token_hash` when the person presses **Continue**, so email previews can open a link without spending it. An expired link returns the person to the sign-in page for the role in the link.

When an administrator sets a managed user's password, the backend completes that update first and then sends the same recovery email so the user can choose a private password. The UI reports a failed delivery separately. It does not retry an ambiguous timeout or gateway error, because a retry could replace the first valid recovery link.

The reset page establishes the recovery session and permits password entry before platform privacy consent. Consent is still required when entering the admin dashboard. The authenticated admin saves through `admin-user-actions` (with the existing dedicated fallback), which sets `app_metadata.admin_password_set=true` with the password. This prevents subsequent candidate/trainer OTP login from rotating an admin's chosen password. The fallback also authorizes Super Admin callers. Ordinary candidate/trainer OTP accounts retain their existing login rules.

After a successful save, the recovery session ends and the user returns to Admin Login. The old password and consumed recovery link are rejected. Missing, expired or used links show an action to request a new link. Wrong password remains HTTP 401; a rate limit returns 429 and service failures are distinguished from incorrect credentials.

## Role sign-in release on 2026-11-25

| Environment | GitHub revision | Served bundle | Rollback snapshot |
| --- | --- | --- | --- |
| UAT | [87fd14775](https://github.com/PluginLive-Technologies/bankingjobreadiness/commit/87fd147757b372febab51db855f5973b4526908a) | `index-CSYJqSY_.js` | `~/banking-sb/snapshots/20261125T015646Z` |
| Production | [8392ab4cb](https://github.com/PluginLive-Technologies/bankingjobreadiness/commit/8392ab4cb7f01fc476fe6c29750edb97068a7a94) | `index-CO5cijiV.js` | `/data/backups/prod-role-login-20261125T020121Z` |

The UAT branch passed 325 focused tests. Password sign-in against the published UAT service returned the correct account for candidate, trainer, faculty, institute administrator, platform administrator and super administrator fixtures. The platform administrator used its approved trainer email. All six temporary users were removed. In each environment the eight changed backend files matched the GitHub revision.

Browser checks on UAT and production covered all three public sign-in forms, protected-route redirects, reset-link previews, and the return from an expired link. Unregistered QA identifiers produced the expected generic OTP and reset acknowledgements. Delivery to a production inbox still needs a dedicated QA mailbox. [Production tag v1.1.46](https://github.com/PluginLive-Technologies/bankingjobreadiness/tree/v1.1.46)

## Incident and release — 2026-11-23

The reported PROD account had a registered-email admin and a separate trainer profile. The reset handler rejected the admin's internal email alias and logged `account_has_no_email`, while the UI reported generic success. An isolated PROD reproduction confirmed that no recovery token was generated. Password authentication itself accepted a known valid password; the user's unknown password was neither inspected nor changed.

- UAT: `801a212d5eded3a45ed09f85bb021a9e0b891202`, snapshot `20261123T044514Z`, bundle `index-_EK1tHBy.js`.
- PROD: `release/prod-v1.1`, tag `v1.1.36`, commit `77000f2ffdd988ce16f209a4b65bec14ddc4caac`, backup `/data/backups/prod-20261123T044733Z`, bundle `index-Bg_8IY7c.js`.
- Both frontends were built on their own VM and deployed through `auto_deploy.sh`. Four runtime function/shared files and all 14 changed source files match the GitHub release. Public HTML/assets return 200 and bundle API origins match their environment.
- No database schema migration or real-account credential change was required. The production student LMS redesign, video completion gate and AI checker holds remain excluded.

## Verification

69 targeted tests pass on both release trees, including actual Edge handler execution with provider/database doubles, duplicate-role identity selection, registered-email delivery, foreign redirects, public recovery URL routing, denied credentials, provider errors, password-save failures and privacy-gate boundaries. Full TypeScript checks retain the existing 24 diagnostics with no new errors.

**18 live checks passed on each environment (36 total)**, and every temporary QA identity, learner/staff row, role and consent record was removed. The final database check finds zero remaining QA users. The deployed browser/API journey covers registered-email and legacy-ID sign-in, a duplicate trainer profile, direct-email Super Admin, protected fallback reset, Forgot Password submission, recovery token ownership, password save, new-password sign-in, old-password rejection, one-time link reuse and cleanup. QA email transport uses reserved `.invalid` addresses, not real users; provider acceptance does not prove inbox receipt. For the browser step, the test reads only the isolated QA account's generated recovery-token hash and opens the corresponding public Auth link. No browser API responses are mocked in this live journey.

Evidence: `/home/ubuntu/banking-checks/admin-recovery-20261123/` contains targeted test logs, baseline reproduction, per-environment live reports, deployed source checks and cleanup results. Real users' passwords, recovery links and sessions are not stored in the reports.

## Recovery email refinement — 2026-11-24

The scanner-safe, visible-link recovery update is on GitHub as `0ee025189d9cbe36cc69b035a1f1a441f3f267f7` for `release/prod-v1.1` and `dfca2c9c9814f806c1a2480710aac67006e918d3` for the divergent UAT branch. Targeted tests pass: 61 assertions across the recovery email, managed reset and client error-handling suites.

The UAT deployment was built on the Banking UAT host and verified through `https://banking.uat.pluginlive.com`: its public bundle includes the `token_hash`/Continue flow, its `request-password-reset` function answers preflight requests, and the deployed shared email helper contains the visible-link template.

Production was promoted through the Banking release wrapper at `0ee025189d9cbe36cc69b035a1f1a441f3f267f7`, with rollback snapshot `/data/backups/prod-password-reset-20261124T171931Z`. Its public index, reset-password route and reset client assets match the production-host build; `banking-sb-functions` is running with the new shared helper. This release is limited to the Banking LMS (`lms.pluginlive.com` / `banking.uat.pluginlive.com`); Aividya/Pilvidya is a separate application and is not part of this change.
