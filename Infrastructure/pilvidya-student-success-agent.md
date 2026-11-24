# aividya — Student Success Agent (UAT)

Status: deployed to UAT on 2026-11-24 at app commit `448c727f` (branch `feat/chat-simulations`). There is no aividya PROD deployment.

## Purpose and boundaries

Student Success is a staff-led, academic-support workflow. It turns observable learning signals into an owned, time-bound support case; it does **not** diagnose health, wellbeing, behaviour or a child's future outcome. The case ledger is separate from wellbeing records.

The agent is deterministic in P0: it derives signals and recommended next actions from attendance, mastery, curriculum coverage, recent assessment scores, unresolved learning gaps and the existing support score. It makes no LLM call and therefore needs no LiteLLM task or fallback configuration.

## Who can use it

| Surface | Route | Access |
|---|---|---|
| Teacher navigation: **Student Success** | `/teacher/student-success` | A teacher may see only learners on their mapped roster and cases they own or opened. |
| Admin navigation: **Student Success** | `/admin/student-success` | Platform admin selects a school; school leaders can review school-wide cases. |

Academic membership roles are teacher, HOD, principal, vice-principal, institute admin and counsellor. Leadership roles (and platform admins) can review all cases in their school. A platform admin must select a school and assign a real school staff owner; a case cannot be assigned to a person outside that school.

## Consent and data protection

- A current `consent_records` decision for `subject_type = 'student'`, the student's profile id and `purpose = 'ai_data_processing'` must be granted and not revoked before a case, action or family-message record can be created or changed.
- The Edge function checks consent before reading learning signals; a database trigger repeats the guard so a faulty service caller cannot bypass it.
- Tables are RLS enabled and have no `anon` or `authenticated` privileges. Only the service role accesses them after the Edge function has performed identity, role, school and roster checks.
- If consent is withdrawn later, case records stay protected but cannot be mutated until a fresh valid decision exists. Do not use the feature to record diagnoses, labels or disciplinary claims.

This gate uses the existing consent ledger; it does not by itself provide the outstanding parent-consent capture or withdrawal UX documented in [DPDP compliance](pilvidya-dpdp-compliance.md).

## Workflow

1. Staff opens a case for an eligible learner. The server snapshots only factual academic evidence and shows up to three deterministic recommendations.
2. Staff assigns and tracks actions: teacher check-in, targeted practice, attendance plan, family meeting, counselling referral, review or another explicitly named action.
3. A teacher drafts a fact-based parent message. A different authorised school leader must approve it; the original author cannot self-approve.
4. The sender or a leader sends only to the learner's verified parent links. The send creates normal parent messages and in-app notifications, then moves an open/in-progress/monitoring case to `awaiting_family`.
5. A resolved case needs an outcome summary. Every create/change writes an append-only case event.

## Runtime and data model

- Edge function: `student-success-agent` (`verify_jwt = true`), actions: `bootstrap`, `summary`, `open_case`, `update_case`, `create_action`, `update_action`, `draft_parent_message`, `approve_parent_message`, `send_parent_message`, `case_detail`.
- UAT database: `eduspeak_uat`, migration `20261124061005_student_success_agent.sql`.
- Tables: `student_success_cases`, `student_success_case_actions`, `student_success_parent_messages`, `student_success_case_events`.
- Database script: `Student Success Agent/20261124T072636Z__student_success_agent_case_ledger.sql` in `PluginLive-Technologies/DB-Scripts` (`32fab50`). UAT applied; the separate hosted DEV Supabase project and PROD remain pending.
- UAT frontend and function runtime are deployed from `~/frontend/eduspeak-india-react` and `~/eduspeak-sb`; the UAT release rebuilt the bundle with UAT configuration and verified no DEV URLs in the deployed assets.

## Verification

- Focused frontend checks: TypeScript, targeted ESLint and 4 Vitest cases for deterministic rules and the case workspace.
- UAT migration dry-run and live application: four RLS tables, consent/scope/audit triggers and service-only access verified.
- UAT runtime: frontend container `eduspeakreact:448c727f` healthy; unsigned function request returns the structured `unauthorized` response (intended status 401) and no Student Success runtime error was logged.
