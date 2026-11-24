# aividya — Assessment Evidence & Board Compliance + State School Lite (UAT)

**Status:** deployed to UAT on 2026-11-24 at `eduspeak-india` commit `a05bee6e` on
`feat/chat-simulations`. UAT database migration is applied; PROD is pending. The separate
hosted DEV Supabase project has not received this migration.

This release adds two deliberately narrow school workflows. It does not add a national
state-board content catalogue, assert an official board/government partnership, or enable
anything for a school until authorised staff configure it.

## P1 — Assessment Evidence & Board Compliance

### Surfaces and access

| Surface | Route | Who can use it |
|---|---|---|
| Teacher navigation: **Board Compliance** | `/teacher/board-compliance` | A teacher can work only with their mapped learners, portfolios they created, or portfolios they own. |
| Admin navigation: **Board Compliance** | `/admin/board-compliance` | An operations-area platform admin selects a school; school leadership/coordinators can manage their own school. |

Academic staff membership may be teacher, HOD, principal, vice-principal, institute admin or
counsellor. Only a school leader/coordinator (or a platform admin) can independently approve a
portfolio.

### Workflow and safeguards

1. Staff creates an ICSE project, ISC internal assessment, or an IB IA, Extended Essay, CAS or
   TOK portfolio (a custom programme is also available).
2. A current student `consent_records` decision for `purpose = academic_portfolio` is required
   before a student record, requirement or evidence item can be created or changed.
3. Staff records an official source title, URL and version, then verifies it. A source must be
   verified before installing a package, submitting a portfolio or activating a rubric.
4. Requirements and evidence are gathered, then submitted. A different authorised staff member
   reviews evidence and approves the final portfolio; neither evidence authors nor portfolio
   creators can self-approve.
5. All material portfolio, requirement, evidence and review changes create an append-only event.

Direct browser table access is denied. The `board-compliance` Edge function validates identity,
school/roster scope, consent, verified source provenance and maker/checker separation before it
uses the service role.

## P2 — State School Lite

### Scope and activation

| Pilot lane | Instructional language |
|---|---|
| Tamil Nadu (`tn`) | Tamil (`ta`) |
| Maharashtra (`mh`) | Marathi (`mr`) |
| Karnataka (`ka`) | Kannada (`kn`) |

These are only the first configured lanes, not a claim of an official content partnership. A
school leader must create the pilot, record an official source title/URL/version, verify it and
explicitly activate it. The same leader can pause it. The `state-school-lite` Edge function
refuses every classroom action while the pilot is not active and verified.

### Surfaces and behaviour

| Surface | Route | Behaviour |
|---|---|---|
| Teacher navigation: **State School Lite** | `/teacher/state-school-lite` | Browser-offline outbox for up to 25 idempotent attendance, homework, marks, parent-alert or lesson-delivery actions per sync. |
| Admin navigation: **State School Lite** | `/admin/state-school-lite` | Operations-area configuration, source verification, activation/pause and recent sync review. |

Each minor-related action requires a current `consent_records` decision for
`purpose = state_school_lite`; records are restricted to the actor's school and a teacher's
profile must belong to that school. Sync events use a school-scoped idempotency UUID so a retry
does not duplicate an attendance, homework, mark, message or lesson delivery.

## Runtime and database record

- Migration: `supabase/migrations/20261203010000_assessment_evidence_and_state_school_lite.sql`.
- UAT database: `eduspeak_uat` on PluginLive PostgreSQL.
- Canonical DB record: `PluginLive-Technologies/DB-Scripts`,
  `EduSpeak Postgres Migration/20261124T103401Z__assessment_evidence_and_state_school_lite.sql`
  (commit `80d2dcb`; UAT applied, DEV/PROD pending).
- Board tables: `board_compliance_portfolios`, `board_compliance_rubrics`,
  `board_compliance_requirements`, `board_compliance_evidence`,
  `board_compliance_approvals`, `board_compliance_events`.
- State Lite tables: `state_lite_pilots`, `state_lite_sync_events`,
  `state_lite_lesson_deliveries`.
- All nine tables use RLS with `anon`/`authenticated` privileges revoked; service-role calls
  are guarded in the Edge functions and again by database triggers.

## Password reset correction in the same UAT release

The admin Users & Access reset path now recognises the dedicated password-reset function's
successful `{ ok: true, message: ... }` response. Previously the presence of a success message
could be misread as an error, unnecessarily invoke the fallback function and show a false
failure toast even after a password changed. The UI now waits for a valid admin session before
retrying, and the student/teacher reset functions return a structured authorization failure
without exposing technical details when unauthenticated.

## UAT verification

- 16 focused Vitest cases passed (Board Compliance/State School Lite, Student Success regression
  and password-reset response handling); targeted ESLint had no errors.
- UAT schema check: nine feature tables with RLS, 17 expected guard/audit triggers and service-role
  access to all nine tables.
- UAT frontend rebuilt as `eduspeakreact:a05bee6e`, served manifest reports `a05bee6e`, contains
  both new route chunks and contains no `*.dev.pluginlive.com` hostnames.
- Unsigned requests through `/sb/functions/v1/board-compliance`,
  `/sb/functions/v1/state-school-lite` and `/sb/functions/v1/admin-set-student-password` returned
  their expected structured authorization responses. This verifies deployment and avoids mutating
  a real school account during release validation.
