# Shared assessment creation — Admin and Corporate

## Architecture

`PluginLive-Technologies/design-system` owns the reusable React UI and four-step assessment wizard. `admin-react` (legacy React 18), `admin-react-v2` and `corporate-react-v2` consume it at build time. There is no separate design-system server or microfrontend runtime.

The two Next.js apps pin `@pluginlive-technologies/assessment-creation` 0.1.2 and `@pluginlive-technologies/ui` 0.1.0. Packages are generated using `npm pack`, committed as `vendor/*.tgz`, and integrity-pinned in package-lock.json. This rollout does not publish to an npm registry. Both apps transpile the packages through Next.js and load their scoped styles. Docker dependency stages copy vendor before npm ci.

## Entry points and responsibilities

- Legacy Admin: Create Assessments at `/assessment` opens the entity picker and shared wizard in place. The browser remains at `/assessment` throughout creation and cancellation; success reloads that same page. The picker supports college/corporate and checks contract availability before continuing. Entity ID, segment, name and optional campus ID are held in host state. Requests still use the existing same-origin `/v2/api/*` BFF, so admin-react-v2 must remain running.
- Admin v2: its direct `/v2/assessment?create=1&type=college|corporate` and `/v2/assessment/new` entry points remain available, but the legacy button no longer navigates there.
- Corporate: `/v2/assessments/new`, using the corporate organisation derived by its BFF from the authenticated session.
- Institute: excluded from this rollout. Its temporary creation implementation was removed on its feature branch; no Institute merge or deployment is needed for the shared wizard.

The package owns setup, type configuration, recipient tools, scheduling, validation and review. Hosts own authentication headers, basePath-aware transport, navigation, organisational scope and existing BFF routes. Admin's selected IDs and display name are not authorization evidence; its authenticated upstream authorizes access. Corporate ignores client entity IDs and derives its scope from the session. No backend or database changes are part of this rollout.

College contexts expose course/cohort selectors, recurring schedules and supported broadcast workflows. Corporate retains its multi-type flow. Host changes remount the Admin wizard, clearing the previous entity's draft. Both hosts return to their own assessment list after creation or cancellation.

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

## Legacy Admin inline integration — 2026-09-11

Legacy Admin pins assessment-creation 0.2.0 and ui 0.1.1 as committed `vendor/*.tgz` artifacts, with checksums in `vendor/manifest.json`. These versions accept React 18 or React 19 peers and retain the college validation fixes above. Webpack transpiles the shared TS/TSX package source and loads scoped package CSS. The Docker dependency stage copies vendor before installation. This remains an npm-pack delivery, with no registry publication.

The host lazy-loads the wizard, forwards the legacy login token to the BFF, keeps selection in component state, and mounts the wizard in a fullscreen dialog above the existing page. Background interaction is disabled while the wizard is open. The former `ADMIN_V2_CREATE_ASSESSMENT` redirect flag no longer controls this button.

Source revisions: design-system Development/UAT `04e92cf`; admin-react Development `8b2719ea`, UAT `5556df71`. Corporate and Institute are unchanged by this correction.

Deployment uses `~/auto_deploy.sh admin-react Development|UAT`, delegating to `~/scripts/deploy-inline-admin.sh`. It builds clean checkouts under `~/releases/admin-react/` without overwriting the existing working tree. DEV runs the release through a systemd override. UAT builds its Docker image on UAT using `.env.uat`, scans executable bundles for DEV URLs before switching `adminreact`, and retains the previous container for rollback. Pages and referenced assets are checked after switching.

Validation: React 18 integration browser tests cover both entity segments, picker cancellation, contract-lock handling, wizard steps, submission failure/retry, success reload, mobile width and an unchanged page URL using mocked APIs. Shared-package tests (24) and type checks passed. These tests do not create records or send invitations.

Deployment verified on DEV and UAT: legacy `/assessment` and all referenced assets respond successfully; DEV systemd and UAT `adminreact` are running the revisions above. Public-site browser checks clicked Create Assessments, selected an entity and opened the shared wizard with no page errors and no URL change. API responses were mocked. UAT executable bundles were independently scanned and contain no DEV hostnames; the deployment helper now uses a Node-based scan compatible with Alpine images.
