# Assessment OTP Invite (account-less flow)

## What it is

A per-campaign mode for **corporate-assigned** assessments where the candidate does **not** need a PluginLive student account. They receive a single email containing an invite link, verify their email with a 6-digit OTP, and drop straight into the assessment runner.

Originally built for AI Interview. As of 2026-06-11 it is **generalized to all corporate-side assessment types**: AI Interview, Communication, Aptitude, Hinglish, Role-Based, Behaviour, Custom.

Institute-side assessments still go through the portal-login flow.

## Admin trigger

`admin-react` Assessment Assignment screen has a **"Send OTP invite"** checkbox. When checked, the assignment is persisted with `is_otp_invite = true` on the corporate map row; when unchecked (default), the legacy portal-signup + reminder-email flow is used. The flag is round-trippable so resends and post-hoc listings stay consistent.

## Data model

### Postgres — single column

```sql
ALTER TABLE assessment.assessment_corporate_map
  ADD COLUMN is_otp_invite BOOLEAN NOT NULL DEFAULT false;
```

- One row per corporate campaign; the flag lives at campaign granularity, not per-student.
- `DEFAULT false` → zero backfill, every existing campaign keeps its legacy behavior.
- No new tables, no enum changes, no new indexes.
- DB-Scripts: `Assessment OTP Invite/001_corporate_map_is_otp_invite.sql`.

### MongoDB (user-management-node) — generalized OTP store

- Old: `ai_interview_invite_otp` collection + `AiInterviewInviteOtp` model + `aiInterviewOtpHandler` + `/public/interview-otp/*` routes.
- New: `assessment_invite_otp` collection + `AssessmentInviteOtp` model + `assessmentInviteOtpHandler` + `/public/assessment-otp/*` routes.
- The old paths/models are **kept as thin aliases** for backward compatibility — already-issued AI Interview invite links keep working.
- The OTP record stores: hashed OTP, expiry, `assessment_assigned_id`, `assessment_type`, `email`, attempt counter, resend timestamp.

## Email flow

When `is_otp_invite = true` the admin-node assignment handler **suppresses both** the portal-signup email and the legacy "complete your assessment" reminder, and sends only the OTP invite-link email.

The invite-link email template lives at `user-management-node/src/utils/emailTemplates/assessmentInviteOtp.js` (renamed from the AI-interview-specific template). It carries: candidate name, assessment name (resolved live), corporate name, link to `/assessment/start/<token>`, expiry window.

The invite URL is built from `process.env.ASSESSMENT_FE_BASE_URL` (admin-node helper `app/helpers/assessmentInviteEmail.js`). Each environment **must** set this — the helper falls back to `https://assessment.dev.pluginlive.com` if unset, so a UAT or PROD container without the var silently sends candidates to DEV. UAT value: `https://assessment.uat.pluginlive.com`. PROD value: `https://assessment.pluginlive.com`.

## Candidate flow

1. Candidate opens `assessment.<env>.pluginlive.com/assessment/start/<token>`.
2. Assessment-React `InviteStart` component prompts for email → calls UMS `/public/assessment-otp/send` → 6-digit OTP delivered.
3. Candidate enters OTP → `/public/assessment-otp/verify` → UMS mints a scoped JWT carrying `assessment_assigned_id`, `assessment_type`, `email`, short TTL.
4. `student-node` `/ai-interview/invite/resolve` (generic despite the legacy path name) reads the corporate map + assessment row, returns the **real assessment name** and the type-specific runner config.
5. Assessment-React `InviteAssessmentRunner` dispatches to the matching `*assmt` partial (Communication, Aptitude, Hinglish, Role-Based, Behaviour, Custom, AIInterview). The runner title shows the real assessment name (not "AI Interview").
6. On completion, the candidate lands on `/assessment` (home) so any other assigned assessments are visible — the OTP `sessionStorage` is cleared on this hard redirect.

## Backend touchpoints

| Repo | What changed |
|---|---|
| `admin-react` | Checkbox in Assessment Assignment form; `isOtpInvite` carried through `filterAssessmentData` (the function used to strip it). |
| `admin-node` | `assignAssessmentSchema` accepts `isOtpInvite` (was stripping it via the Fastify body schema); `assign*Assessment` methods set it on the corporate map and gate email branches via `isCorporateOtpInvite`. Invite URL built from `ASSESSMENT_FE_BASE_URL` env var. |
| `user-management-node` | Renamed handler/model/routes; backward-compatible aliases retained; scoped JWT carries `assessment_type`. |
| `student-node` | `resolveInvite` reads the real campaign name from the corporate/institute map and **no longer hard-codes `"AI Interview"`** for the title — that was the early bug where Communication invites displayed as "AI Interview". |
| `Assessment-React` | `InviteStart` is generic; `InviteAssessmentRunner` dispatches by `assessment_type`; the OTP input is a fixed-width 48 px box grid (the earlier overflow bug); demo OTP code hint removed; "Back to Home" hard-redirects to `/assessment`. The invite axios layer (`aiInterviewInviteAPI.js`) **reuses the shared `utils/authRequest` + `utils/studentRequest` instances** — see the env gotcha below. |

## Environments

| Env | Status | `ASSESSMENT_FE_BASE_URL` |
|---|---|---|
| DEV | live since 2026-06-10 | `https://assessment.dev.pluginlive.com` (or unset — hardcoded fallback covers DEV by accident) |
| UAT | live since 2026-06-11 | `https://assessment.uat.pluginlive.com` — must be set in `~/api/admin-node/.env.uat` |
| PROD | pending | `https://assessment.pluginlive.com` — must be set before sending live invites |

## Backward compatibility checklist

- Existing AI Interview invites continue to work via the `/public/interview-otp/*` and `aiInterviewInviteOtp` aliases.
- Every existing corporate campaign has `is_otp_invite = false` after backfill (NOT NULL DEFAULT false), so portal-signup + reminder behavior is unchanged for them.
- Institute campaigns are untouched — the column does not exist on `assessment_institute_map`.

## Known gotchas (carried over from build)

- **`ASSESSMENT_FE_BASE_URL` env var.** Without it, the admin-node helper falls back to the DEV URL — UAT and PROD admin-node `.env.<env>` files must include the matching frontend base URL or every invite email links candidates to DEV.
- **Fastify body schema strips unknown fields.** `admin-node` `assignAssessmentSchema` must explicitly list `isOtpInvite` or the handler never sees it (server logs the row with `is_otp_invite = false` even though the request carried `true`). Same applies to any future toggles added on this form.
- **`admin-react` `filterAssessmentData`** rebuilds the payload from a whitelist before submit. Any new field on the form must be added there or it silently disappears.
- **Title is dynamic, not hard-coded.** `resolveInvite` returns the campaign's real assessment name; the runner uses it for the instructions header. Old caches on the client can still show "AI Interview" — a fresh OTP verify rewrites the `sessionStorage` entry, so retesting requires reopening the invite link.
- **Frontend `process.env` in `aiInterviewInviteAPI.js` — TWO opposite failure modes (resolved 2026-06-15).** The invite *email link* was always correct (`assessment.uat...`), but after landing the invite/AI-interview flow misbehaved depending on how the module read its axios base URLs:
  1. **Member access** `const API_URL = process.env.API_URL` with `|| 'https://api-auth.dev.pluginlive.com/'` / `|| '...api-std.dev...'` fallbacks → in this webpack build the member-access token was **not inlined**, so `API_URL`/`STD_API_URL` were `undefined` at runtime and the **DEV fallback fired → candidates bounced to DEV** (page loaded fine, wrong env). The dev string surviving in the bundle (not folded away by terser) is the tell.
  2. **Named-key destructuring** `const { API_URL, STD_API_URL } = process.env` → URLs **did** inline correctly (no DEV leak), BUT webpack left a **dangling `process.env;` expression statement** that terser did not eliminate. At runtime `process` is undefined → **`Uncaught ReferenceError: process is not defined` → blank screen** on the invite entry page. (The tiny `src/utils/*Request.js` files use this same destructuring safely because the binding is their only statement and the declaration gets fully DCE'd; a larger module like this one keeps the dangling reference.)
  - **Final fix:** do **not** touch `process.env` in this chunk at all. Reuse the shared, already-configured axios instances: `import authRequest from 'utils/authRequest'` (→ `API_URL` / api-auth / UMS, for the public OTP endpoints) and `import studentRequest from 'utils/studentRequest'` (→ `STD_API_URL` / api-std, which also attaches the invite scoped JWT from `sessionStorage` that the resolve call needs). Their base URLs inline cleanly and no `process.env` reference is left in the module.
  - **Build/verify rules:** frontend env URLs are **baked at build time** (`EnvironmentPlugin` from `.env.<env>`), so **always rebuild the FE on the target box from the target-env checkout — never ship a DEV-built bundle to UAT/PROD.** After building, before swapping the container: `docker exec <c> sh -c "grep -rho '[a-z-]*\.dev\.pluginlive\.com' /app/build | sort | uniq -c"` must be empty, and a quick headless load (`playwright-core` + `/usr/bin/chromium-browser`) of `/assessment/start/<anytoken>` must show **no `pageerror`** and a non-empty `#root` (a bogus token correctly renders "Invite link invalid", not a blank screen).
- **Audio/proctoring student_id fallback.** Proctoring `verify-frame` / `detect-audio` calls fall back to `assessment_assigned_id` as `student_id` for account-less candidates. Don't gate these endpoints on a real `users.id`.
- **MediaRecorder mime gotcha.** `video/webm;codecs=vp8,opus` contains a comma; splitting on `,` for the base64 part instead of `;base64,` produces a corrupt `"opus;base64"` payload and the audio-detect endpoint returns `Incorrect padding`.
