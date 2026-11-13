# aividya — Schools, staff accounts and School Operations (UAT)

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

## Tests
- DB access by role (rolled-back transaction, real UAT users): `~/pilvidya-checks/school-ops/rls-roles-test.sql` (47 checks).
- Browser: `~/pilvidya-checks/school-ops/{admin-teachers,institute-users,institutes,ops-e2e,ops-menu-check}.cjs` (UAT 2026-11-13: 12 + 15 + 10 + 23/24 then fixed + 6); test data cleanup `cleanup-uat.sh`.
- The ops menu does not open modules from a "nobody has an ops role" fallback any more (it miscounted under RLS and opened Hostel/Payroll for every teacher).

## Known open issue
- `is_admin_user()` (and `security_is_platform_admin()`) counts **principal** as a platform admin; ~100 policies use it (user_roles writes, subscriptions, plan pricing, gateway configs). Not yet fixed.
