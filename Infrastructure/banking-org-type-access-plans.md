# Banking LMS — menus and plans per organisation type (College / Corporate)

Organisation-specific menus and plans launched on **DEV, UAT and PROD**. Original UAT release: commit `7ff6ee12e` on GitHub `UAT`, deployed 2026-11-25 (snapshot `20261125T125056Z`).
PROD (`lms.pluginlive.com`): **v1.1.50** = `da3109644` on `release/prod-v1.1` (cherry-pick of `7ff6ee12e` onto v1.1.49 only;
the aividya lesson flow and other UAT-only commits are not in it), live 2026-11-25 14:25 UTC, rollback backup
`/data/backups/prod-org-access-20261125T142518Z` (dist, functions, full `banking_prod` dump).
Migration: `supabase/migrations/20261125130000_org_type_menu_access_and_plans.sql`
(DB-Scripts: `Banking LMS Institute Plans/20261125T124134Z__org_type_menu_access_and_plans.sql`, applied DEV/UAT/PROD).

## Canonical menu controls

Admin Journey → Subscriptions → Menu Access Controls shows one switch for each audience, menu and plan tier. The plan comparison, Plan Menu Access table and matrix use the same controls. Editing a switch updates that menu and tier. In the RBAC permission matrix, each role has one row per destination. Existing permissions that only apply to a role remain editable. Similar names that refer to separate audiences are labelled by audience.

| Active controls | Before cleanup | After cleanup |
|---|---:|---:|
| Candidate plan menus | 69 | 59 |
| Trainer plan menus | 57 | 52 |
| Teacher plan menus | 40 | 40 |
| Institute Admin plan menus | 20 | 20 |
| Platform Admin plan menus | 23 | 22 |
| All plan menu controls | 209 | 193 |
| RBAC role permissions | 198 | 179 |

The migration retires old keys and retains their original settings for audit. When a destination already has a rule, that rule supplies the tier flags or role actions. Candidate Module Quiz and Module Videos are locked on Free. Trainer Project Reviews has one control. Trainer RBAC Reports grants View and Export. The prior duplicate also listed Configure. Organisation and institute overrides retain their precedence, and candidates’ and admins’ individual permission lists are preserved.

Migration file `supabase/migrations/20261127164000_canonical_menu_controls.sql`. The application uses `src/lib/menuCatalog.ts` for audience-specific aliases and `src/lib/roleMenuCatalog.ts` for role permissions.

The cleanup went live on 27 November 2026. GitHub `UAT` and `fix/menu-access-duplicates` point to `591b5fc42`. The production release is `d253146c6` on `release/prod-v1.1`, live at 17:11 UTC. [GitHub release v1.1.63](https://github.com/PluginLive-Technologies/bankingjobreadiness/tree/v1.1.63)

| Environment | Served bundle | Backup before release |
|---|---|---|
| UAT | `index-C6LSpNC_.js` | `~/banking-sb/snapshots/20261127T170345Z` |
| PROD | `index-9_cOeiQy.js` | `/data/backups/prod-menu-access-20261127T171127Z` |

On both environments, a temporary QA admin signed in through the password form and opened Menu Access Controls, the Plan Menu Access table and matrix, and the Trainer permission matrix. The browser confirmed the counts and settings above. Database checks matched the migration rehearsal, including the saved plan flags, role actions, individual permission lists and service-function privileges. The QA accounts and their permissions were removed after the checks.

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
