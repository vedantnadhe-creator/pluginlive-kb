# Corporate Company Management (v2) — Manage Users, roles, per-user permissions

**Live:** DEV + UAT (2026-10-08). PROD pending.
**Where:** corporate-react-v2 `/v2/users` and Settings (account menu) › Profile / Change Password / Manage Users.
v1 `/users` (sidebar "Users") now does a full-page redirect to `/v2/users`.

## Model

- **Role = a label.** The built-in role is **Admin** (in code, never a DB row). Each corporate can create its **own** roles
  (typed into the role picker → "Create … as a new role"); they are visible only to that corporate. Roles can't be
  renamed or deleted yet.
- **Permissions are per user** — 15 on/off actions, stored on the user, not the role:
  - Assessment: `viewAssessmentDetails`, `createAssessment`, `editAssessment` (edit/reopen/cancel), `duplicateAssessment`,
    `shareAssessment`, `addCandidates`, `remindCandidates` (reminders + resend), `removeCandidates`,
    `viewCandidateReport`, `downloadReports` (downloads + export sheets).
  - User Management: `viewUserDetails`, `addUsers`, `editUsers`, `editUserPermissions`, `deactivateUsers`.
  - `viewAssessmentDetails` (label **"View dashboard & assessments"**) opens the whole Assessment module: without it
    the Dashboard and Assessments nav items are hidden, `/v2/assessments/*` shows "no access", `/v2/dashboard` (the v2
    home) redirects to `/v2/users`, and the BFF read routes (list, dashboard, detail, overview, candidates) return 403.
    The users list is open to every user (not an action). (2026-10-09, v2 `ef497e3` / UAT `73a5f91`.)
  - PluginLive check-in sessions: Settings opens on Manage Users; Profile and Change Password are hidden (they are the
    internal admin's own).
- Picking **Admin** turns every switch on (each can still be turned off). Picking another role leaves the switches as they
  are. Anyone with `editUserPermissions` can grant anything, including Admin.
- **v1 role:** every user created or edited from v2 is **Admin in v1** (`user_management.users.admin_role_id` = the
  CORPORATE "Admin" role), whatever the v2 role. What they can do in v2 is decided by the v2 switches.
  ⚠️ There are several roles named "Admin" (`admin.roles` journeys CORPORATE / INTERNAL / INSTITUTE), and admin-node
  `/roles/journey/CORPORATE` returns the INTERNAL one too. Only a role whose **own** `journey = 'CORPORATE'` may be
  written to a corporate user — the INTERNAL Admin sends them to the **admin portal** at sign-in (fixed 2026-10-09,
  corporate-node `1c122812` / UAT `fde47e75`; 3 UAT users repaired).
- **Resolution** of a user's v2 access (corporate-node `CorporateUserAccessService.resolveAccess`):
  1. PluginLive internal user (`pluginlive_id`, i.e. an admin **check-in**) → full access. Their own record has no
     `corporate_id` — the auth service writes the corporate only into the token — so this rule runs first.
  2. A `corporate_user_access` row → that row's role + switches.
  3. No row (e.g. a user added from v1 later) → v1 Admin = full access, anything else = nothing on.
  An inactive user has nothing.
- **Guards:** you can't deactivate yourself; every call is scoped to the token's corporate (another corporate's user is
  a 404). There is **no** "keep one active Admin" rule — any other user, the last Admin included, can be deactivated or
  demoted (removed 2026-10-09, corporate-node `4ce499d7` / UAT `fa95751c`).

## Data

| Table (schema `corporate`) | Purpose |
|---|---|
| `corporate_roles` | `id, corporate_id, name, created_by, created_at`; unique `(corporate_id, lower(btrim(name)))` |
| `corporate_user_access` | `user_id` PK, `corporate_id`, `is_admin`, `corporate_role_id` → roles, `permissions jsonb` (`{action: true}`), `updated_by` |
| `user_role_backup_20261007` | every corporate user's v1 `admin_role_id` before the switch-over (rollback source) |

User records (name, email, phone, password, active flag, welcome email) stay in the auth service (user-management-node).

DB-Scripts `Corporate Company Management/`: `…__corporate_roles_and_user_access.sql`, then
`…__convert_corporate_users_to_admin.sql` (one-time: backup → every corporate user to v1 Admin → an all-on v2 Admin row;
rollback block inside). UAT applied 2026-10-08 (352 users, 109 v1 roles changed). PROD pending (~202 users / 46 roles).

## APIs

corporate-node (JWT, tenant from the token via `assertCorporateScope`):

| Method | Path | Gate |
|---|---|---|
| GET | `/corporates/:id/users/v2` | any user of the corporate |
| GET | `/corporates/:id/users/v2/me/access` | self |
| PUT | `/corporates/:id/users/v2/me/profile` | self (name + phone) |
| GET | `/corporates/:id/users/v2/:userId` | `viewUserDetails` (or self) |
| POST | `/corporates/:id/users/v2` | `addUsers` (+ `editUserPermissions` if a role/switches are sent) |
| PUT | `/corporates/:id/users/v2/:userId` | `editUsers` for details, `editUserPermissions` for role/switches |
| PATCH | `/corporates/:id/users/v2/:userId/status` | `deactivateUsers` |
| GET/POST | `/corporates/:id/user-roles/v2` | list: any user; create: `editUserPermissions` |

Create calls auth `POST /user` (generated password + welcome email). Email can't be changed on edit (auth `PUT /user/:id`
doesn't update `login_email`).

corporate-react-v2 BFF: `/api/me/users`, `/api/me/users/[id]`, `/api/me/users/[id]/status`, `/api/me/roles`,
`/api/me/access`, `/api/me/profile`, `/api/me/password`.

- `lib/permissions.tsx` loads `/api/me/access` once per page load; `can()` / `<RequireAccess>` read it. Fails closed.
- `lib/api/companyUsers.ts › requireAction()` gates every assessment write and report/download BFF route (403 when the
  switch is off). Calls made straight to corporate-node / admin-node are not gated by it yet.
- `/api/me/password` masks both passwords server-side (CryptoJS-compatible AES) and calls auth
  `PATCH /user/:id/password`. **Needs `PASSWORD_MASK_SECRET` in corporate-react-v2 `.env.local`** — same value as that
  env's user-management-node `PASSWORD_MASK_SECRET`. A successful change revokes the user's refresh sessions.

## Related v1 changes

- Interviewer pickers (schedule interview, create slot, add/replace interviewer) list **every active** user of the
  corporate — no role filter (`status=true`).
- auth `POST /user` requires a login JWT or the service auth-key (`isPrivateJWTOrKey`).

## Commits

corporate-node `4ee7d80c`, `215bf3bf`, `4537c296`, `88788ca7` (UAT `74620686…291cdffc`) · user-management-node `ce79726`
(UAT `ba80768`) · corporate-react `82172a38a` (UAT `7dcb4d610`) · corporate-react-v2 UI `3ce2c48…dd80e79` + wiring
`e7e4360` (UAT `b969c23`; UAT Sidebar keeps the ATS-access "Back to ATS" gate alongside permission-gated nav).
