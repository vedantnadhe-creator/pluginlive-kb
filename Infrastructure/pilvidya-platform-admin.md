# aividya — Platform admin (aividya team running many schools) (UAT, feat/chat-simulations 51c60207)

Migration `20261118250000_admin_platform.sql`. Every new function checks the caller's **admin area** (internal role).

## Admin menu (rebuilt 2026-11-14)
Overview (Overview, School health, Parent experience, Admin 360, Learning usage, Predictive, Dropout) · Schools (School onboarding, Schools &
Institutes, Branches & Boards, School Staff Accounts, School Operations) · Billing (School Plans, Billing & Renewals, Plan
Menus) · Support (Support Desk, Messages to Schools, View as user, Data Requests) · Users & Access (students, teachers,
roles, reset password, all accounts, admin users, Admin Team & Roles, My Two-factor) · Curriculum & AI · School Tools ·
Platform · Previews. Removed from the menu: AI Meta Dashboard, School Analytics, Audit Summary. Removed code: 9 unrouted
admin pages (fee, HR, transport, library, attendance, parent registry, communication gateway, report-card generate,
curriculum management) and 11 dead route declarations.

## One way to add a school, one place to maintain it (18c0a8da)
- **New schools only via School onboarding** (`/admin/onboard-school`, `?new=1` opens the wizard). **Schools & Institutes**
  (`/admin#institutes`, the Institute master) edits name/board/address/contact and active/inactive only; its button
  "Set up a new school" opens the wizard; `?edit=<school id>` opens a school's editor, `?q=<name>` filters.
- Old creators redirect: `/admin/onboarding` (Admin Setup) and `/admin/school-setup` → wizard; `/admin/institutes`
  (Institute Registry) → master; `#add-institute` → wizard. Functions `admin-create-school` and
  `admin-manage-institutes` were deleted (no other callers). Duplicate school names are refused by `schools_name_unique`.
- Admin search links schools to the master filtered by name; the go-live board links each school to the master.

## Navigation (4b9081ed)
- `lib/goBack.ts`: Back = previous in-app page when React Router's `history.state.idx > 0`, else the role home. Used by
  the header Back (was `window.history.length`) and 23 pages' generic in-page back arrows (were fixed `/student`,
  `/teacher`, `/admin`…). Arrows labelled with a destination (Back to sign in, Dashboard, My Portal, Home) keep it.
- Logout (`hardLogout`) revokes the session globally (all devices) and clears `pilvidya_*` / `sb-*` keys.
- Check: `~/pilvidya-checks/nav/nav-check.cjs` (every menu item per role: header Back, browser Back/Forward, reload keeps
  session, Home, Logout + back/protected URL → sign-in), `inpage-back.cjs`.

## Roles and two-factor
- `platform_admin_roles` (super_admin, sales, support, content, finance). **An admin with no row is a super admin.**
- `admin_areas()` → areas: sales = schools, onboarding, renewals, health, messages; support = schools, health, support,
  users, data_requests, messages; content = content; finance = schools, billing, renewals, health. Menu items carry an
  `area`; `/admin#tab` tabs map via `ADMIN_TAB_AREA`; new pages use `<AdminRoute area=…>` and the functions check too.
  Older admin screens still read data with full admin RLS (menu/tab hidden only).
- Two-factor: Supabase TOTP (GoTrue v2.158). Admin → My Two-factor to enrol; `AdminRoute` asks for the code when the
  session is aal1 and a factor exists. `platform_billing_settings.require_admin_mfa` (off; super admin turns it on in
  Admin Team, only from an aal2 session) makes `admin_areas()` return `['mfa_required']` until aal2.
- View as user needs a reason (≥ 8 chars, UI + `admin-view-as`).

## Password reset response handling (UAT `a05bee6e`, 2026-11-24)

- **Users & Access → Reset Password** uses the dedicated student/teacher reset functions first.
  The UI accepts their successful `{ ok: true, message: ... }` response as success; it no longer
  mistakes the informational message for an error, calls the legacy fallback unnecessarily and
  shows a false red failure toast after a reset actually completed.
- The client waits for the authenticated admin session before considering a fallback. A real
  unauthenticated or unauthorized request returns the normal structured `Admin access required`
  response; the UI does not expose database or function internals.
- UAT gateway verification is non-mutating: an unsigned request to
  `/sb/functions/v1/admin-set-student-password` reaches the deployed function and returns its
  structured authorization failure. Use an authorised UAT admin and a designated test account for
  an actual password-change test; do not exercise resets against a customer account during smoke
  checks.

## Schools: onboarding, billing, renewals, seats, health
- **School onboarding** (`/admin/onboard-school`): wizard school → plan → billing details → principal account
  (`admin-manage-users` createInstituteUser) → branding; **go-live board** `admin_onboarding_board()` with 12 checks
  (plan, principal, year, terms, classes, teachers ≥ 2, subject teachers, students, ≥ 90% in sections, timetable,
  parents linked, fee structure).
- **Billing** (`/admin/billing`): `admin_create_invoice(subscription)` → `<prefix>/<FY>/<0001>` (FY April–March,
  `platform_invoice_counters`), taxable = plan term amount, CGST+SGST if school state = seller state else IGST, seller and
  buyer snapshots; `admin_record_invoice_payment` (≤ balance, reference for bank/UPI/cheque), `admin_void_invoice` (no
  payments), `admin_email_invoice` (queues `email_outbox` to billing email + principals), print at `/admin/invoices/:id`
  and for principals `/teacher/invoices/:id` (`invoice_for_print`). No SAC code is printed (to be confirmed by accounts).
- **Renewals**: `admin_renewals(days)`, `admin_send_renewal_reminder` (email + in-app to principals),
  `admin_renew_subscription` (starts the day after). **`school_plan()` now honours `grace_days` (default 15)** after a
  term ends.
- **Seats**: `school_seat_usage(school)`; trigger `trg_enforce_school_seats` blocks approving students over
  `licensed_students` only when `seat_enforcement = 'block'` (default `warn`).
- **School health** (`/admin/school-health`): score 0–100 = students active 7d 40 + teachers active 7d 25 + attendance
  days 20 + homework/exams 10 + AI 5 (from `app_usage_events`, `attendance_records`, `homework`, `exams`, `robo_sessions`,
  `sim_attempts`, `student_doubt_questions`); RAG ≥ 60 / ≥ 30; flags few_students_active, no_teacher_activity,
  no_attendance, renewal_due, over_seats, inactive_14d.
- Principal: School Admin → **Plan & billing** (`my_school_plan_status`), **Branding**; "From aividya" card.

## Support, data requests, branding, messages
- **Support desk**: staff raise at `/teacher/support` (`support_create_ticket`; urgent only for principals; 10/day);
  SLA urgent 4 h, high 24 h, normal 72 h, low 120 h; admin queue `/admin/support` (take, status, priority, reply →
  notification to the raiser). Principals see all their school's tickets.
- **Data requests** (`/admin/data-requests`): `privacy_requests` queue with 30-day target; `admin_privacy_export` (JSON,
  no password hash), `admin_privacy_erase` (type ERASE; anonymises profile, clears written answers/doubts, unlinks
  parents; marks/attendance kept unnamed; audit-logged), `admin_privacy_resolve`; whole-school export via
  `admin_school_export_page` (11 tables, 1000 rows/page, one JSON download). Parents' own export and erasure-request flow and the DPDP gap list:
  [pilvidya-dpdp-compliance.md](pilvidya-dpdp-compliance.md).
- **Branding**: `schools.logo_path` (storage `branding/<school>/logo-*.png|jpg|webp`, ≤ 1 MB) and `brand_color`;
  `my_school_branding()` → header logo + `--primary` for that school's students/teachers/parents (colours with luminance
  > 0.7 ignored).
- **Messages to schools**: `platform_messages` to all or chosen schools, principals (+ teachers optional),
  `my_platform_messages`, `platform_message_read`, read counts.

## Parent experience release (ce01ad9f)
- The admin **Parent Journey** preview opens the current parent shell read-only. The parent shell is documented in
  [`pilvidya-parent-experience.md`](pilvidya-parent-experience.md); use it when validating a school’s parent-facing
  experience after changes to attendance, homework, fees, messages, report cards, notifications, or curriculum.
- This release changed the parent frontend only; it adds no database migration or new admin function. The follow-up
  `ce01ad9f` fix imports the attendance summary icon used by the live parent home so the authenticated parent route
  renders successfully. Parent access
  remains controlled by the existing parent session, child-link checks, plan menu access, and school RLS/function
  boundaries.

## Parent experience control tower (8dfa2869)
- The admin Overview now links to **Parent experience** (`/admin#parent-experience`), a read-only control tower for the
  family journey. It is available under the health area and therefore follows the same internal admin-area checks as
  School health.
- The control tower shows a configurable 7/30/90-day signal window and school filter, with four transparent measures:
  verified family-link activation, active parent sessions, recent digest coverage, and open follow-ups. It deliberately
  does not invent a child or family risk score.
- The activation funnel counts students → verified parent link → active parent signal → recent digest signal. School pulse
  rows show activation percentage, active parents, digest signal count, and an operational status. The attention queue
  points admins to the existing Students, Messages to Schools, Roles, and View as Parent workflows; the new screen does
  not mutate parent records or expose parent contact details or message bodies.
- Data trust is explicit. Existing `parent_profiles`, `parent_student_links`, `parent_digests`, `parent_messages`, and
  `notifications` records are read opportunistically; if an optional source is unavailable, the screen labels it as
  needing review instead of treating missing data as family inactivity.
- Focused regression coverage is in `frontend/src/test/adminParentExperience.test.ts`, with the existing admin role
  navigation and platform-area tests updated for the new tab. No database migration or new Edge Function was introduced.

**UAT deployment verification (2026-11-15).** GitHub `feat/chat-simulations` and the UAT checkout are at `8dfa2869`.
The PilVidya frontend was rebuilt on the UAT host with the UAT environment as `eduspeakreact:8dfa2869`; the served
manifest reports the same version, the site returns HTTP 200, and the bundle contains no `*.dev.pluginlive.com`
hostnames. No database migration was required.

## Reports and downloads (2026-11-18)
- Admin audit-log export honours the date filter; CSV downloads use Excel-compatible UTF-8, correct escaping and spreadsheet-formula protection.
- Subscription-report tabs clear stale rows before loading and have corrected PDF table widths. Dropout generation is restricted to authorised staff and replaces the selected school/period's report rows when producing a new report.
- Board/school/model dropdown duplicates are removed, and same-name people/campuses carry identifying details. Database-export pagination orders by `id` when available; SQL downloads handle JSONB and array values correctly.
- Current UAT release and the limits of the completed checks: [reports, downloads, dropdowns and timetable validation](pilvidya-reports-downloads-and-dropdowns.md).

## Checks
`~/pilvidya-checks/school-core/admin-platform-test.sql` (51, rolled back); `~/pilvidya-checks/admin/admin-journey.cjs`
(menu crawl of 59 items + new flows; `LIVE=1 BASE=https://pilvidya.uat.pluginlive.com` for no stubs),
`school-side.cjs`, `wizard.cjs`, `live-flows.cjs` with `live-seed.sql` / `live-cleanup.sql`.
Fixed on the way: admin "Clear filters" crashed (`setFilterPlan` undefined).
