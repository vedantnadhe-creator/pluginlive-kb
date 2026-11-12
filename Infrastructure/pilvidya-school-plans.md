# PilVidya (aividya) — School plans and plan access

Plans belong to a **school**, not to a person. Every student, teacher and parent in a school gets the school's plan
automatically. Live on UAT `dc1a74b9` (2026-11-12); PROD has no aividya yet.

## Plans
| Plan | Price (per student per year) | Includes |
|---|---|---|
| Basic | ₹3,600 | Curriculum, lessons, practice, tests, assessments, progress, report cards, fees, community, teacher school tools, all core parent menus |
| Advanced | ₹4,800 | Basic + AI Coach / Virtual Tutor, English Lab, Aptitude Lab, Foreign Languages, Competitive Exams, SWOT, **Simulations**; teacher FL content/assessment, AI config; parent insights, wellbeing, learning plan, SWOT |
| Enterprise | ₹6,000 | Advanced + **Robo Teacher**, Robo Classes, NovaCampus, NovaWorld |
| Trial (no live term) | — | Same as Basic |

- Annual, **1–5 years** per term. A renewal is booked as a new term that starts after the current one ends (overlaps are refused).
- Amount = price × licensed students × years by default; admin can type a different amount (discount) or mark it Complimentary.
- Prices and what each plan includes are admin-editable: Admin → **School Plans** (prices, add/renew/cancel terms) and
  Admin → **Plan Access Matrix** (menus per plan). Prices live in `plan_pricing.annual_price` (now per student).

## Data and functions (migration `20261117140000_school_plans.sql`; DB-Scripts `9f280f4`)
- `school_subscriptions`: school_id, plan (basic/advanced/enterprise), start_date, years, generated end_date,
  licensed_students, amount_inr, payment_mode (MANUAL/GATEWAY/COMPLIMENTARY), payment_reference, notes, cancelled_at.
  Platform admins only (RLS). Overlap trigger `school_subscriptions_no_overlap`.
- `school_plan(school)` → plan today, else `free`.
- `profile_school_id(school_id, school_name)` → school_id, falling back to a name match (old teacher rows).
- `my_plan(p_role)` → `{plan, school_id, school_name, term, next_term}` for the signed-in user; admin = enterprise;
  parent = best plan among verified children's schools. Used by `usePlanAccess` / `fetchMyPlan`.
- `student_menu_enabled(student, menu_key)` → server check; menus without a matrix row stay open.
- Menu keys added: `student.robo-teacher`, `student.simulations`, `teacher.robo-classes`, `teacher.simulations`, `student.practice`.
- Dropped `staff_manage_plan_menu_access` and `staff_manage_plan_pricing` (any teacher could rewrite plan access and prices).

## Enforcement
- Sidebar and route guard (`PlanRouteGuard`) lock menus by the school plan.
- Server: `robo-teacher` (start), `robo-speech`, `sim-attempt` (start) call `_shared/plan.ts` → 403
  "… is not included in your school's plan". The check **fails closed**. Other modules are still client-side only.

## What was removed
- Per-person plans: plan dropdowns on Admin → Students / Teachers, the plan picker on Admin → Roles (role-only now),
  teacher self-upgrade requests (Subscription Approvals hidden from the menu), the per-teacher Subscriptions tab.
- `teacher_subscriptions` and `*.plan_override` remain in the DB but nothing reads them. `admin-manage-users`
  only writes `plan_override` if an old client still sends a plan.
- Teacher → My Plan is read-only: school plan, dates, renewal, and a menu-by-plan table.
- Admin Overview revenue = live school terms, amount spread evenly over the term's months; "Schools by plan".

## UAT data (2026-11-12)
- Every school mapped to a complimentary 1-year Enterprise term (amount 0, licensed students = current count).
- 7 teacher schools that existed only as typed names were registered in `schools` (`is_public=false`) and the
  teachers linked by `school_id`. One teacher with a blank school name stays on trial.

## Verified
- Plan unit tests 438/439 (the 1 failure pre-dates this: an audit-log assertion in `admin-manage-users`).
- UAT: logins 10/10, Robo 15/15, View-as 26/26, Simulation E2E pass; Test School A switched to Basic → Robo and
  Simulation start both 403, restored to Enterprise; admin School Plans, Roles, Matrix, Overview and teacher My Plan render with no page errors.

## Home page (UAT `8de6d747`, 2026-11-12)
- The public home page (`frontend/src/pages/Index.tsx`) lists the three plans with prices from `public_plan_prices()`
  (anon-callable, returns basic/advanced/enterprise `annual_price`; DB-Scripts above). Falls back to 3600/4800/6000 if the call fails.
- Sections: hero with a Robo class preview, Robo Teacher, chat simulations, English + 13 Indian languages and 8 world
  languages (with pronunciation), NEET/JEE Main/JEE Advanced/MHT CET/CUET actual-mock preview (patterns from
  `lib/CompetitiveExam/ExamConfigs.ts`), boards + learning picker, role sign-in (`LoginRoleSwitcher`), school plans, promises + FAQ.
- Header "Sign in" opens a role menu (Student → /student-entry, Teacher → /auth?role=teacher, Parent → /parent/login, School admin → /admin/login); UAT `6253116f`.
- "Book a school demo" = mailto contact@aividya.si (no booking form yet). Previews are static HTML, not live data.
- The app-wide floating theme toggle (`.app-theme-toggle` in App.tsx) is hidden on the home page; the header has its own.
- Logo is `src/assets/aividya-logo.webp` (11 KB). Still open: `vendor-charts` (~900 KB) loads on the home page via eager imports in App.tsx.

## Student Curriculum page + Nova off (UAT `49936858`, 2026-11-12)
- Nova floating assistant removed from `AppLayout` (every signed-in page). `NovaAgent.tsx` / `lib/novaStream.ts` stay (practice "Explain this question" uses the stream). The mobile bottom nav "NovaQuest" (→ /student/novaworld) is a separate gamification page and is still there.
- `/student/curriculum`: board/class/school come from the profile (fixed: the profile board was copied into the state-board field, which flipped the page to "State Board"); no board dropdowns for students.
- "Pick up where you left off": first in-progress topic, first needs-revision topic, first undone teacher-assigned Robo class (from `get_coach`), else the first not-started topic.
- Subject cards show topics done and coach mastery vs target. A chosen subject shows subject tabs and a topic list with status and Start/Open/Revise, Lessons, Practise (`/practice?subject&topic&class&board`) and Robo class (`/student/robo-teacher?subject&topic`; only for subjects present in `curriculum_topics`, and only when the plan includes Robo).
- Robo Teacher preselects from `?subject=&topic=` with loose name matching ("&" = "and").
- `subjectLabel` maps ai→AI, gk→General Knowledge, evs, it, ict, sst, pe.
