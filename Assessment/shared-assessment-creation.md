# Shared assessment creation — Admin and Corporate

## Architecture

`PluginLive-Technologies/design-system` owns the reusable React UI and four-step assessment wizard. `admin-react-v2` and `corporate-react-v2` consume it at build time. Legacy Admin redirects creation into the v2 app. There is no separate design-system server or microfrontend runtime.

The two Next.js apps pin `@pluginlive-technologies/assessment-creation` 0.1.2 and `@pluginlive-technologies/ui` 0.1.0. Packages are generated using `npm pack`, committed as `vendor/*.tgz`, and integrity-pinned in package-lock.json. This rollout does not publish to an npm registry. Both apps transpile the packages through Next.js and load their scoped styles. Docker dependency stages copy vendor before npm ci.

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
