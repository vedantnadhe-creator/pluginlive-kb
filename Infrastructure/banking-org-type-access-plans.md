# Banking LMS — menus and plans per organisation type (College / Corporate)

Status: **LIVE on DEV, UAT and PROD.** UAT: commit `7ff6ee12e` on GitHub `UAT`, deployed 2026-11-25 (snapshot `20261125T125056Z`).
PROD (`lms.pluginlive.com`): **v1.1.50** = `da3109644` on `release/prod-v1.1` (cherry-pick of `7ff6ee12e` onto v1.1.49 only;
the aividya lesson flow and other UAT-only commits are not in it), live 2026-11-25 14:25 UTC, rollback backup
`/data/backups/prod-org-access-20261125T142518Z` (dist, functions, full `banking_prod` dump).
Migration: `supabase/migrations/20261125130000_org_type_menu_access_and_plans.sql`
(DB-Scripts: `Banking LMS Institute Plans/20261125T124134Z__org_type_menu_access_and_plans.sql`, applied DEV/UAT/PROD).

## What it does

Organisations are typed by `institutes.organization_type` (`institute` = college/institute, `corporate`).
Menus and plans can now differ by that type, and the decision is made on the server.

| Area | How it works |
|---|---|
| Menu rules | `menu_access_controls` stays the all-organisation rule (one row per audience + menu, flags per plan tier). New table `menu_access_overrides` adds optional per-tier flags scoped to **one organisation type** or **one institute** (exactly one scope per row). Most specific wins: institute → organisation type → all. A flag left null falls back to the base rule. |
| Plan catalogue | `subscription_plans.organization_type` (null = offered to both) and `access_tier` (`free`/`beginner`/`advanced`/`enterprise`, the RBAC tier the plan unlocks). |
| Plan guards (triggers) | An institute or institute subscription cannot use a plan offered only to the other type. A plan's type cannot be narrowed while an organisation of the other type uses it. Any plan code written to `students/trainers/profiles.subscription_tier` is stored as its tier. `admin_activate_institute_subscription` copies the plan's tier to members. |
| Effective plan | Organisation plan = its active, unexpired `institute_subscriptions` row; if it has subscriptions but none active → `subscription_expired` (no plan); if it never subscribed → `institutes.default_plan_code`. Learner's access tier = **higher** of their own tier and the organisation's tier, so nobody loses access. |
| Sidebar | `public.my_effective_access(p_audience)` returns the plan breakdown and resolved menu rows; the sidebar uses it, with the old browser-side lookup kept as fallback. Callable by `authenticated` only. |
| Server check | `public.has_menu_access(user, menu_key)` (service_role only): staff roles bypass, then the user's allow-list (`candidate_menu_permissions`), then the tier rule. Used by `ai-coach` (menu `ai-coach`) and `ai-practice-interview` (menu `practice-interview`) via `_shared/plan-access.ts`. |
| Enforcement | **Shadow mode**: a denial is logged as `plan_access_denied` and the request continues. Set `PLAN_ACCESS_ENFORCE=true` on the functions container to return 403. A failing check never blocks (logged as `plan_access_check_failed`). Not set on DEV, UAT or PROD. |
| Admin UI | Plan Menu Access has "Applies to" All / College / Corporate with an override badge and Reset. Plan catalogue: offered to, access tier, active, add plan. "Effective access by organisation" report (`effective_access_report()`). Institute plan pickers list only plans for that organisation's type; individual payments list all plans. |

## UAT release check (2026-11-25)

- Migration rehearsed in `BEGIN…ROLLBACK` on `banking_uat` before release: no errors, 0 student tiers changed, 0 institutes
  on a mismatched plan, candidate and trainer core reads unchanged. All four existing plans default to `organization_type` null (both).
- After deploy: table, columns and functions present; `anon` cannot call `my_effective_access`, `authenticated` cannot call
  `has_menu_access`. A signed-in candidate RPC returned its plan breakdown and 65/69 menus allowed.
  `ai-coach` / `ai-practice-interview` boot and return 401 unauthenticated. `/`, `/login`, `/dashboard`, `/pil-admin`,
  `/academic-curriculum` load headlessly with no page errors and no DEV calls.
- Not yet done on UAT: an admin creating a College/Corporate override in the UI and a learner of each type seeing the
  sidebar change. The DEV smoke test for that is `~/banking-checks/org-access/db-smoke.sql` (DEV fixture IDs).

## PROD release check (2026-11-25, v1.1.50)

- Rehearsed on `banking_prod` in `BEGIN…ROLLBACK`: no errors, 0 stored tiers changed, 0 mismatched institutes. Of 2,323
  learners, 1 gains access (college learner beginner → advanced via the institute's plan); nobody loses access.
- Released with the staged-driver method (`/opt/banking/staged-org-access-da3109644/deploy-release.py`): file checksums,
  no DEV/UAT URLs, idle bulk jobs, backup + dump, migration in one transaction, functions + rest restarted.
- After: functions present and grants as on UAT; signed-in candidate RPC returns its plan; `ai-coach` /
  `ai-practice-interview` 401 unauthenticated; `/`, candidate/admin login, `/dashboard`, `/pil-admin`,
  `/academic-curriculum`, `/ai-coach` load headlessly with no page errors and no DEV/UAT calls.

## Before turning on enforcement

Watch functions logs for `plan_access_denied`; set `PLAN_ACCESS_ENFORCE=true` only when there are no unexpected denials.
