# Banking LMS managed institute roles

The admin account selectors share one role catalogue. Selecting a registered `institute` adds **Faculty / Teacher, Institute Admin, Head of Department (HOD), Principal, Vice Principal, Dean and Director**. Candidate, Trainer and Platform Admin remain available. Corporate or unregistered organizations cannot receive academic roles. HOD requires an existing programme department in the selected institute.

## Application surfaces

| Place | Behavior |
| --- | --- |
| User Management → All Users → Create New User | College-aware role list, HOD department selection, server-side staff onboarding |
| User Management → All Users and shared Roles & Access grid | Full role filters, actual academic titles and organization-aware reassignment |
| Admin journey → Users → System Role Access | Complete filters and reassignment, including college leadership titles |
| Roles & Access → RBAC | Account role assignment remains separate from additional capability permissions |
| RBAC & Reports → Permission Matrix | Leadership choices show inherited Faculty/Trainer policies read-only |
| Plan Menu Access | Consistent Faculty / Teacher, Institute Admin and Platform Admin audience labels |
| Agent Activity Log and Agent Tool Analytics | Includes roles recorded on historical events, without relabeling old events after a promotion |
| Assessments → Creator role | Includes additional recorded staff roles |

The combined admin Users page renders 50 candidate rows per page. Search, CSV export and bulk selection continue to cover all matching candidates; the count shows selections across pages. This prevents a large roster from blocking the role controls above it. Missing legacy name/email/contact values are normalized on roster load; unmatched searches no longer crash on null email addresses.

## Account and authorization wiring

`bulk-create-users` and `admin-user-actions` both call the service-only `admin_assign_managed_role(uuid,uuid,text,text)` RPC. It validates the platform-admin actor, Auth-linked target, institute type and department before atomically writing roles, staff records, scoped appointments and an audit event.

| Selection | Persisted authority |
| --- | --- |
| Candidate | `student` role and learner record |
| Trainer | `trainer` role and approved trainer record |
| Faculty / Teacher | `teacher` + `trainer` and approved trainer record |
| Institute Admin | `institute` + `trainer` and approved trainer record |
| HOD | Faculty roles plus `department_heads` scoped to institute/department |
| Principal / Vice Principal / Dean / Director | Faculty roles plus the matching `college_principals.title` |
| Platform Admin | `admin` role |

Staff use the Trainer OTP entry point; Institute Admin has the institute journey. Platform Admin uses password sign-in, and the creation confirmation explains that distinction. Successful staff creation does not create a candidate record. Welcome notifications follow successful persistence; failed new account persistence cleans up its own newly created records and Auth identity.

Changing the account role removes obsolete college leadership appointments and stale trusted Auth role claims, while preserving independent capability roles. Self-reassignment and Super Admin replacement are blocked. A staff account with retained teaching/mentoring authority cannot become a candidate through this form; use a separate learner account. Existing academic staff cannot silently move institute through profile editing without first reviewing their role/academic assignments.

Role directories paginate beyond 1,000 rows and fail closed if a required read fails. Browser code no longer creates roles or trainer rows as a compatibility fallback.

`useUserRole` reads the current user's `user_roles` under RLS, consistent with AuthContext. Live testing exposed text and enum `has_role` overloads: PostgREST returned HTTP 300/PGRST203, making the old hook deny valid admins on Agent screens. The hook avoids that ambiguous RPC, accepts Admin/Super Admin, fails closed on query failure and ignores old results after sign-out. Database overloads are retained for existing callers; no function was dropped.

The Activity Log no longer selects the nonexistent `thread_id` column. `agent-runtime` stores thread context in `metadata.threadId`, sets `user_id` from the verified caller, awaits persistence on success/error returns, and logs database audit failures without discarding a completed response.

## Release and verification — 2026-11-22

| Environment | GitHub and live revision | Bundle | Backup / snapshot |
| --- | --- | --- | --- |
| UAT | `dea9e01fd7d3ae299c11c69b6849c2ef48666542` on `UAT` | `index-COe2Ai_t.js` | `~/banking-sb/snapshots/20261122T150131Z` |
| PROD | `a392b569db2612e79be0301200262e5f3a4798cd` on `release/prod-v1.1`, tag `v1.1.35` | `index-Bmd99pUW.js` | `/data/backups/prod-20261122T150405Z` |

Both builds ran on their target VMs through `~/auto_deploy.sh`, using each environment's existing configuration. Final checks verified all 32 changed source files and five runtime function/shared files against GitHub, public HTML/assets returning HTTP 200, running API/DB/function containers, and no foreign DEV/UAT/hosted API origins in the bundles. The role RPC is executable by service_role and denied to anon/authenticated.

Only scoped commits were promoted from UAT onto `release/prod-v1.1`. The student LMS redesign, video-watch completion gate and AI video checker remain excluded from PROD.

The migration `20261122153000_admin_managed_college_roles.sql` adds a function and grants using existing tables and enum values. It does not alter table schemas. Apply that migration before deploying its Edge callers and frontend. DEV was not part of this deployment request.

Testing uses temporary, isolated institutes and QA identities with reserved `.invalid` registered emails; no real user's roles are changed. Login checks establish authenticated QA sessions without sending SMS OTPs. QA accounts and institutes are removed after testing; legitimate security audit records are retained.

### Test evidence and limits

- **137/137 targeted automated tests across 17 files** passed on the final PROD promotion. These include real Edge handler execution with mocked transport, PostgreSQL permission/rollback tests, role forms, pagination/search, role-hook sign-out races and audit persistence.
- **26 live checks on each environment** passed: all ten account roles, HOD UI creation, assignment/title refresh, corporate/department rejection, self-change and unauthorized RPC denial, candidate/faculty/HOD/Principal/Institute Admin journeys, all seven academic access boundaries, mobile selectors, matrix/plan controls, Agent/assessment role filters, real Agent response with audit persistence, and roster paging/selection/empty-filter recovery.
- OTP delivery was not sent to real phone numbers: authenticated QA sessions exercised journeys; role creation used reserved `.invalid` registered emails. No production user's roles were altered.
- Ten QA login identities and three isolated organizations per environment, their candidate/staff/role/leadership/programme/consent records, and temporary synthetic Agent activity were removed. Security audit records of authorized role changes remain.
- The 49 existing SRM Python topic-package records have the same before/after checksum in PROD. Content, certificates, held student LMS/video-gate/checker work and `/v2` were not changed by this release.
- Full-project TypeScript still reports **24 existing errors**, with identical diagnostic messages/files after accounting for moved line numbers. This release adds no new diagnostics. The earlier eight broader regression failures were reproduced on the unchanged base and remain outside this role rollout; targeted release tests are green.
- Local evidence: `/home/ubuntu/banking-checks/managed-roles-release-20261122/` (per-environment JSON results, cleanup records, runtime health, source verification and deployment logs). No tokens/passwords are saved in these reports.

The PROD progression during this authorized test/fix cycle was v1.1.33 (role catalogue and responsive roster), v1.1.34 (role-hook/audit fixes), then v1.1.35 (legacy nullable contact fields). Original pre-rollout PROD was `9ffb360b5` / v1.1.32. The final reviewed source remains on the separate PROD release branch; DEV and `main` were not deployment targets.
