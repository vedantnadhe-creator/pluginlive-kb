# aividya — Schools, staff accounts and School Operations (UAT, feat/chat-simulations 6f6051fd)

Live on UAT since 2026-11-13 (`feat/chat-simulations` a0af4e96 + 01a7bfd6 + 20a2aa73; DB migration `20261118100000_school_operations_scope`, DB-Scripts `EduSpeak Postgres Migration/…__school_operations_working_school_scope.sql`). PROD: none (no aividya PROD).

## One school model
- **`schools`** is the school record everything uses (teachers, students, plans, pickers). `school_branches` holds campuses; a DB trigger creates the `MAIN` campus on school insert.
- `institutes` is a thin link table (Institute Users → `institute_users.institute_id`); kept in step by the server.

## Admin → Institutes (`/admin#institutes`; old `#add-institute` opens the Add dialog)
- `frontend/src/components/admin/InstitutesPanel.tsx`: lists `schools` (location, contact, current plan from `school_subscriptions`, people counts), Add / Edit dialog, Activate / Deactivate, "Show inactive".
- Writes: `admin-manage-users` action `upsertInstitute` → schools row + MAIN campus (upsert on `school_id,code`) + institutes row; a rename also updates `school_name` on teacher/student profiles. New schools are on Trial until a plan is added in Plans & Subscriptions.

## Admin → Teachers (`/admin#teachers`; old `#create-teacher` opens Add teacher)
- One menu; Add teacher dialog and Edit dialog share `TeacherPlacementFields` (searchable School / Institute picker: one option per campus "school · campus · city"; fills board and location).
- `admin-create-teacher` saves `branch_id` and `board`; `updateTeacherProfile` accepts `school_id` / `branch_id` (name taken from the school).
- Non-teaching institute staff (Principal, School Admin, Admission Manager…) are not listed here.
- **No sign-in** badge = `teacher_profiles.user_id` is NULL (11 imported profiles on UAT; those teachers get an error on sign-in). Edit → *Link sign-in* (`admin-manage-users` `linkTeacherLogin`, admin or the school's principal): links the existing login with that email (`auth_user_id_by_email`, service role only) or creates one with a temporary password, adds the teacher role, audited.
- `admin-set-secret` and `llm-config` find a teacher's school by `teacher_profiles.user_id` (before 2026-11-13: by display name, which 403'd or matched another school).

## Admin → Institute Users (`/admin#institute-users`)
- Creates real staff sign-ins (`admin-manage-users` `createInstituteUser` / `updateInstituteUser`): auth user + profile + `teacher_profiles` on the school (this scopes all data) + roles + `institute_users` row. Role catalogue `supabase/functions/_shared/institute-roles.ts` (frontend copy `lib/instituteRoles.ts`, parity test):

| Role | App roles | School ops roles | Lands on |
|---|---|---|---|
| Principal / Vice Principal | principal + teacher | — | Principal Brief |
| School Admin (`institute_admin`) | principal + teacher | finance, procurement_officer, warden | School Operations |
| School Operations | teacher | procurement_officer, warden | Procurement |
| Admission Manager | teacher | — | Admissions |
| Accounts / Finance | teacher | finance | Payroll |
| HOD | hod + teacher | — | Staff dashboard |
| Counselor | teacher (`is_counselor`) | — | Staff dashboard |
| Hostel Warden | teacher | warden | Hostel |

- Every staff account also gets `teacher`: `has_role` is exact and staff screens check `teacher`. Never grants `admin` or `ops_admin` (both reach every school).
- Ops-only roles see only School Operations in the sidebar and only their tools inside it (`OPS_TABS_BY_INSTITUTE_ROLE`).
- Deactivate = auth ban + sessions revoked.

## School Operations (`/teacher/ops` for staff, `/admin/school-operations` for admins)
- **Working school** = `public.current_ops_school_id()`: staff → their `teacher_profiles.school_id`; platform admin (app role `admin`) → the school picked at the top of the page (`ops_active_school`, set via `set_ops_school()`, admins only).
- **Access rule** on ~30 tables: `ops_school_access(school_id)` (row in the working school + user is admin/teacher/principal/hod). Children (offers, documents, tests, interviews, waitlist, enrolments, fee payments, receipts, bus stops, loans, allocations, payroll items, PO lines) follow their parent row.
- **Sensitive modules** (payroll, HR employees, vendors, procurement, hostel) also need `ops_module_allowed`: admin, principal, or the matching ops role (finance / procurement_officer / warden; finance may read vendors and POs).
- New rows get `school_id` from the working school (`set_school_id_from_teacher` trigger, now using `current_ops_school_id`).
- Admin tools: admissions, fees, transport, library, hostel, HR, payroll, vendors, procurement, events, calendar, timetable, SIS, principal brief, leadership, UDISE, compliance, accreditation, tenant audit, ops roles.
- The 10 server functions (admission-offer-generate, admission-screen, fee-reconcile, fee-reminders-send, razorpay-payment-link, transport-optimize, library-overdue-summary, payroll-run-generate, timetable-generate, principal-morning-brief) call `_shared/ops-auth.ts` `opsCaller`: signed-in staff/admin with a working school; data calls run as the caller (school rules apply). Before 2026-11-13 they had no caller check at all.
- Public admissions (`/admissions/apply`, `/admissions/enquire`) require a school: `public_admission_schools()` lists active public schools; a school can share `/admissions/apply?school=<id>`. Enquiries/applications from before this have no school and are not visible.

## Principal = admin of their own school (2026-11-13)
- `is_admin_user()` / `security_is_platform_admin()` = the platform **admin** role only. Principals no longer pass the ~120 platform-admin policies (user_roles, plan pricing, gateway configs, every school's subscriptions).
- School-scoped rights come from `is_school_admin_of(school)` / `is_school_admin_of_student(student)` (principal of that school): edit school details (teachers no longer can), staff and student profiles, parent links/messages, announcements, simulations, live sessions; read own school's institute users and subscription.
- **Teacher → School Admin** (`/teacher/school-admin`, principals only; menu key `teacher.school-admin`): *Staff & roles* = Institute Users locked to the school (`admin-manage-users` principal actions: create/update institute user, reset password, activate, link teacher login — own school only, cannot grant admin); *Menu access* = switch student / teacher / parent menus off for the school.
- `school_menu_access (school_id, role, menu_key, enabled)`: no row = the plan decides. Enforced in the sidebar and route guard (`usePlanAccess.schoolOff`, page shows "turned off by your school") and for students' paid modules in `student_menu_enabled()`. Principals and admins are never switched off. A school cannot switch on what its plan excludes.
- `usePlanAccess` read the plan matrix with an object key before 2026-11-13, so plan menu limits never applied in menus; fixed.

## Boards, classes and subjects
- Class 11/12 with no stream picked lists the base subjects plus every stream's (Science, Commerce: Accountancy, Business Studies, Economics; Humanities: History, Political Science, Geography, Sociology, Psychology; Computer Science) — `lib/subjectMatrix.ts`.
- `curriculum_topics` seeded (migration `20261118130000`, 1086 global rows, generator `supabase/seed/curriculum_topics_commerce_arts_ib.py`): those 11/12 subjects in NCERT chapter order for cbse / icse / state, and IB PYP / MYP / DP topics per class. IB is in every board dropdown.

## Tests
- DB access by role (rolled-back transaction, real UAT users): `~/pilvidya-checks/school-ops/rls-roles-test.sql` (47 checks); `principal-rls-test.sql` (24). Both must run inside their own `BEGIN … ROLLBACK` — without a transaction `SET LOCAL ROLE` does nothing and the writes commit as the owner.
- Browser: `~/pilvidya-checks/school-ops/{admin-teachers,institute-users,institutes,ops-e2e,ops-menu-check}.cjs` (UAT 2026-11-13: 12 + 15 + 10 + 23/24 then fixed + 6); `principal-ui.cjs` (19) and `subjects-ui.cjs` (4) on 6f6051fd; test data cleanup `cleanup-uat.sh`.
- The ops menu does not open modules from a "nobody has an ops role" fallback any more (it miscounted under RLS and opened Hostel/Payroll for every teacher).
- School setup, promotion, My Day, My Class, exams → report cards, parent messages and fee receipts: see `pilvidya-school-core.md`.
