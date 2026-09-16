# Shared assessment creation — Admin and Corporate

## Architecture

`PluginLive-Technologies/design-system` owns the reusable React UI and four-step assessment wizard. `admin-react-v2` and `corporate-react-v2` consume it at build time. Legacy Admin redirects creation into the v2 app. There is no separate design-system server or microfrontend runtime.

The Next.js apps pin versioned `@pluginlive-technologies/assessment-creation` and `@pluginlive-technologies/ui` artifacts. Admin currently uses assessment creation 0.1.11. Packages are generated using `npm pack`, committed as `vendor/*.tgz`, and integrity-pinned in package-lock.json. This rollout does not publish to an npm registry. Both apps transpile the packages through Next.js and load their scoped styles. Docker dependency stages copy vendor before npm ci.

## Entry points and responsibilities

- Admin: Create Assessments on legacy `/assessment` redirects to `/v2/assessment?create=1&type=college|corporate`. The entity picker opens immediately. Cancel (including Escape) returns to legacy `/assessment`. Selection opens the shared wizard at `/v2/assessment/new` with the selected entity context.
- Wizard exits: Close, the Assessments breadcrumb, and confirmed Discard and leave navigate to legacy `/assessment`, using a native browser navigation that does not add the `/v2` prefix. The missing-organisation Back link also returns there. Keep editing stays in the wizard; step-level Back still moves to the previous step. Creation success retains the existing v2 confirmation flow.
- Corporate: `/v2/assessments/new`, using the corporate organisation derived by its BFF from the authenticated session.
- Institute: excluded from this rollout. Its temporary creation implementation was removed on its feature branch; no Institute merge or deployment is needed for the shared wizard.

The package owns setup, type configuration, recipient tools, scheduling, validation and review. Hosts own authentication headers, basePath-aware transport, navigation, organisational scope and existing BFF routes. Admin's selected IDs and display name are not authorization evidence; its authenticated upstream authorizes access. Corporate ignores client entity IDs and derives its scope from the session. No backend or database changes are part of this rollout.

College contexts expose course/cohort selectors, recurring schedules and supported broadcast workflows. Corporate retains its multi-type flow. Host changes remount the Admin wizard, clearing the previous entity's draft. Corporate returns to its own assessment list. Admin exits return to the legacy dashboard; successful creation retains the v2 confirmation flow.

## Release and deployment

Promoted 2026-09-11 to Development and UAT in design-system, admin-react-v2 and corporate-react-v2. The UI runtime deploys to DEV and UAT; PROD is unchanged.

Admin v2 and Corporate v2 run via systemd. `~/auto_deploy.sh <app> Development|UAT` delegates these two apps to `~/scripts/deploy-shared-assessment-next.sh`. The helper builds in a new local `~/releases/<app>/<env>-<revision>-<timestamp>` checkout using the target server's `.env.local`. UAT is built on the UAT server and checked for DEV URLs before switching the service. A systemd drop-in selects the release; port ownership and referenced asset URLs are checked. The prior release is retained for rollback. This avoids overwriting a live `.next` directory.

Package changes require a versioned artifact, lockfile update, app build and deployment. They do not update a deployed UI automatically. Future shared features may be additional packages in design-system.

## Verification boundary

Shared package tests, Admin tests, Corporate BFF tests, production builds and deployed browser checks cover both Admin segments and Corporate creation, error/retry, navigation and mobile layout. Browser workflow checks mock API calls, so they do not create records or send invitations and do not establish real delivery or quota behavior.

## Validation fixes — DEV and UAT, 2026-09-11

Shared package 0.1.2 fixes two creation-flow issues:

- College recipient selection now identifies missing Degree, Department and Year of passing beside Continue. Candidate Details no longer shows complete while those fields are missing. The existing cohort requirement still applies to saved/suggested lists; choosing a list does not fill the separate cohort fields automatically.
- College Communication configuration fixes Speaking evaluation language to English and explains the restriction. Draft configuration updates enforce English as well, matching admin-node's institute assignment contract and preventing the regional-language rejection at Float. Corporate keeps its language choices.

Release: design-system `6a3efe8`; admin-react-v2 DEV `da970cd`, UAT `4af9505`; corporate-react-v2 DEV `955b0a1`, UAT `73e44a8`. Both apps were rebuilt through auto_deploy.sh on their target servers. No backend or database changes.

Validation: all 24 shared-package tests and TypeScript checks passed. Deployment checks verified pages and referenced assets. Public DEV/UAT browser checks exercise Admin college, Admin corporate and Corporate configuration, recipients, review, submission error/retry, navigation and mobile layout with mocked APIs; they do not create assessments or send invitations.

## Return-navigation correction — 2026-09-11

The temporary inline React 18 integration has been reverted. Legacy Admin no longer installs shared UI tarballs or renders the wizard itself; `ADMIN_V2_CREATE_ASSESSMENT=1` restores the v2 creation redirect. No design-system or Corporate release is needed for this correction.

The actual routing defect was the Admin wizard host calling `apiUrl("/assessment")` on cancel, which added `/v2` and exposed the v2 listing. It now navigates directly to `/assessment`. The missing-organisation fallback uses a native link for the same cross-app boundary. The existing handoff entity-picker Cancel already returned to legacy Admin.

Revisions: admin-react revert Development `873af363`, UAT `99be976b`; admin-react-v2 routing fix Development `10701f9`, UAT `20d958a`. DEV/UAT deployment uses auto_deploy.sh with separate environment builds. Legacy Admin uses the isolated-release helper (DEV systemd, UAT Docker); v2 uses the Next.js release helper and systemd. PROD is outside this rollout.

Regression tests exercise actual host exit callbacks for both entity segments and the fallback link. Public browser checks use mocked APIs and do not create records or send invitations.

DEV/UAT deployment verification passed: pages and assets load, services are active, and UAT executable bundles contain no DEV URLs. Public browser checks cover the restored legacy-to-v2 redirect, popup Cancel, wizard Close/discard in both segments, Keep editing, internal step Back, and the missing-organisation Back link. All exit paths land on the real legacy dashboard with no page errors; API calls are mocked.

## Candidate import and validation fixes — DEV and UAT, 2026-09-11

Admin and Corporate now consume the vendored `assessment-creation` 0.1.2-bugfix.1 artifact. Source is based on 0.1.2 (`6a3efe8`) with fix commit `cbef4e0`; unrelated 0.1.3 changes are not included. The source branch push was unavailable in this deployment session; the consumed package artifacts and integrity lockfiles are committed in both app repositories.

- Candidate-sheet parsing in admin-node returns `candidates`, `skipped`, and `skippedCandidates` (name, email, mobile, row number and reason). The host BFFs forward skipped identities. The shared upload UI lists them even when every candidate was skipped.
- Corporate Add Candidates lists candidates already on the roster, and bulk-report progress retains skipped names/emails and reasons.
- Manual name/email fields trim surrounding whitespace; server draft validation accepts surrounding email whitespace while rejecting internal whitespace and malformed addresses.
- Hinglish remains a language option and is excluded from the unsupported-assessment warning. This does not delete stored legacy assessment types or alter quotas.

Released app revisions: Admin DEV `623d999`, UAT `826891c`; Corporate DEV `da355a8`, UAT `9270886`. The target environment's auto_deploy.sh rebuilt and switched each app. Shared package tests (27), Corporate integration tests (4), TypeScript and deployment page/asset checks passed. No production rollout is included.

## Institute biometric verification default — DEV and UAT, 2026-09-16 (superseded same day — see below)

Assessments created for an institute through Admin v2 now require biometric verification by default. The shared wizard initializes `biometric` to `true` for a `college` host and keeps it `false` for a `corporate` host.

Admin's `/api/assessments/mix-match` BFF also derives `allowVerification` from the entity segment instead of trusting the browser draft. It sends `true` for college and `false` for corporate in all three creation paths: one-time assignment, recurring schedule configuration and role-based broadcast creation. This server boundary ensures a stale or modified client cannot disable institute biometric verification.

Admin consumes the versioned assessment-creation 0.1.9 artifact. Released revisions: DEV `beff006`, UAT `e569c6f`. The app was rebuilt independently in each target environment; tests (97), TypeScript, lint, deployed page/asset checks and the UAT no-DEV-URL check passed. PROD is unchanged.

## Degree / Department can be unselected — DEV and UAT, 2026-09-16

Shared package **0.1.10** (design-system `fix/select-field-clear-0.1.x`, `0e916fb`): the cohort and
broadcast-scope Degree/Department `SelectField`s gain a clear control — an × in the chevron's place on
hover/focus, and Backspace/Delete on the trigger. Before this a degree or department picked while
creating a college assessment could not be unselected. Admin consumes the vendored 0.1.10 artifact
(`60e2594`); released revisions DEV `60e2594`, UAT `24842a7`. Corporate v2 stays on 0.1.2-bugfix.1
(it never renders these selects — recurring schedules and cohorts are college-only). PROD unchanged.

## Biometric verification on for every segment — DEV and UAT, 2026-09-16

Supersedes the institute-only default above. Product asked for corporates to be verified too, so
the segment gate is gone entirely:

- Shared package **0.1.11** (design-system `fix/biometric-default-on-0.1.x`, `c4f6dfc`, branched
  from the 0.1.10 lineage): `EMPTY_DRAFT.biometric` is `true` and the college-only override in the
  draft initialiser is removed. The Proctoring card still has no biometric switch — the flag is
  carried in the draft, not editable.
- Admin's `/api/assessments/mix-match` BFF sends `allowVerification: true` unconditionally in all
  three creation paths (one-time assignment, recurring schedule, role-based broadcast). The
  `requiresBiometricVerification(segment)` helper and its test were deleted — a literal `true` is
  the whole rule now.
- Admin consumes the vendored 0.1.11 artifact. Released revisions: DEV `e5db8bb`
  (`~/releases/admin-react-v2/DEV-e5db8bbcf32a-…`), UAT `e8e3dc8` (merge of Development into UAT,
  `~/releases/admin-react-v2/UAT-e8e3dc8fc6da-…`). Verified per environment: unit MainPID owns
  `:3013`, compiled route chunk contains `allowVerification:!0` ×3, UAT bundle has no DEV URLs.
  Tests (97), TypeScript and lint passed. PROD is unchanged.
- **Not covered:** Corporate v2's own self-service creation (`corporate-react-v2`
  `/api/assessments/mix-match`) still forwards `draft.biometric` from its pinned 0.1.2-bugfix.1
  wizard, where the default is `false`. Assessments a corporate creates for itself are therefore
  still unverified until that app is bumped or its BFF is hard-set the same way.
