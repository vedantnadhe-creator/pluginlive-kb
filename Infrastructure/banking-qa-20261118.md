# Banking journey QA — 18 November 2026

The saved journey fixes and the issues found during live retesting are pushed to GitHub `UAT` and `main`, and live at https://banking.uat.pluginlive.com on `ebb982619` (the original complete QA release was `70dd72d06`).
The final frontend was built on UAT via `auto_deploy.sh banking UAT`; the final dropdown follow-up uses snapshot `20261118T131422Z`, bundle `index-NeiMhnMf.js`, 129 edge functions and 3 self-hosted fixups. The fixes are also live on PROD as `v1.1.28`, release `c4da74ce2`, built on the PROD VM (bundle `index-BN3iuF76.js`).

| Journey | Sidebar screen checks |
|---|---:|
| admin | 57 |
| candidate | 28 |
| trainer | 29 |
| institute | 7 |
| principal | 31 |
| hod | 31 |
| faculty | 31 |
| collegestudent | 4 |
| Total | 218 |

The crawl also opened in-page tabs, dropdowns, searches and report controls. Focused checks covered nine identities across these eight roles on the final behaviour, including assigned home/progress screens, institute analytics, provider settings, mappings, native filters and exports.

- **83 targeted regression tests passed** (77 feature tests plus 6 platform-usage tests). The repository-wide TypeScript check still has its pre-existing 19 distinct diagnostics; the release adds none.
- **95 downloaded files checked:** 52 CSV, 28 XLSX, 8 PDF and 7 JSON. Validation covered parsing/signatures, headers, column counts, duplicate rows, broken values, UTF-8/Excel handling, sheet names/widths and PDF pagination. Practice and assessment PDFs were inspected on their first and last pages.
- The last admin export audit regenerated 10 workbooks across the available period tabs: learner identifiers are populated, exported rows are unique, all six usage worksheets have headers even when empty, and all three native module filters have distinct labels.
- The college transaction run passed 37/38 assertions; the remaining assertion used a non-unique principal-overview locator because the same course appears in two different summary tables. The corrected principal rerun passed **3/3**, including the waiting row and sign-off. Attendance, marks, assignments/submission/review, return/resubmit/HOD approval, mentor access, announcements, Robo Faculty class/quiz, leave request and transcript were verified.
- Learner profile changes, reminders, module completion/reload, quizzes and practice results were checked. Descriptive practice initially hit Chromium `ERR_NETWORK_CHANGED`; after using a stable owned runtime directory its full browser generate/grade/persist flow passed. Direct API generation/grading also returned 200.
- RBAC actor stamping was verified inside a rolled-back transaction: an authenticated caller cannot forge the audit actor.

The fixes cover CSV quoting/encoding, XLSX names/headers/widths, PDF bars/wrapping, null-safe menu search, provider-list errors, budget-panel error handling, assignment-scoped recommendations, institute progress/score/cohort joins, duplicate record labels/references and dashboard exports that previously lost student names. Existing same-name content records remain separate; labels and identifiers distinguish them rather than merging unrelated learner histories.

Four file-audit notes remain as data-completeness facts: historical RBAC rows have no actor name, and three college roster CSVs contain no mobile numbers for their sample learners. Missing values stay blank. Repeated taxonomy headings have distinct adjacent slugs; stored error-log messages and controls that open previews/import dialogs are not live application failures.

The test host interrupted the first long sweep. Completed role evidence was retained; the remaining sweeps used checkpoints, followed by focused retests. The optional Jev suite was offered and was not launched without a response.

**Cleanup completed:** all six temporary auth identities, three temporary student rows and the isolated QA programme, section and course were removed. Real courses/results were not reset. Reusable content-bank assets remain cached, including their legitimate budget accounting.

Detailed local evidence: `/home/ubuntu/banking-checks/journeys/release-20261118/` (`summary.json`, role JSONs, focused checks, workbook verification, browser/transaction logs and cleanup SQL/log).


## PROD promotion and dropdown follow-up

GitHub `release/prod-v1.1` and tag `v1.1.28` are `c4da74ce2`; `UAT`/`main` are `ebb982619`. The QA commits were cherry-picked onto the live PROD `v1.1.27` base; the permanent LMS v2, lesson-video watch-gate/checker and their held migrations remain absent. The initial 67-file source guard matched the expected release changes. The final 68-file release (including the additional export regression test) was checked against its archive on the live VM: every source file matches, excluding the preserved environment and generated MCP file.

A live PROD check found case-only variants among institute, department and location filter values. The shared label helper now compares references without case/whitespace differences; values that are otherwise indistinguishable get stable numbered references. It preserves every underlying value and record. Two new regression cases cover this and mixed-case common prefixes. **All 87 targeted tests pass across 18 files.**

The RBAC actor migration was rehearsed in BEGIN/ROLLBACK, then applied in one transaction. A second rolled-back check on the deployed trigger verifies authenticated actor stamping, replacement of a forged identity, and private-function ACLs. DB-Scripts commit `c12fe73` records PROD applied. Historical audit rows remain intact.

Backups on Pl-Prod-Banking: `/data/backups/prod-20261118T125813Z` is the full pre-promotion `v1.1.27` backup; `/data/backups/prod-20261118T130801Z` precedes the final case-label follow-up. The final CSV correction backup is `/data/backups/prod-20261118T131501Z`. All include verified custom-format DB dumps, prior source/dist/functions and environment. The follow-ups have no further schema change. The bundle audit has no DEV/UAT/local/hosted Supabase addresses, and the live site returns HTTP 200.

Deployment entry point is now `~/auto_deploy.sh banking release/prod-v1.1` on Pl-Prod-Banking (`130.210.28.66`, SSH key `~/.ssh/pl_prod_banking`). It locks and dispatches to `/opt/banking-sb/deploy-release.sh`, which pins old/new commits and the archive checksum. Prepare that script for each future release; it deliberately refuses a different live base. `/opt/banking-sb/deploy.sh` is an obsolete UAT copy and must not be used on PROD. Node 20 is installed at `/usr/bin/node`.

Local PROD evidence: `/home/ubuntu/banking-checks/journeys/prod-release-20261118/`. The browser checks use eight synthetic identities and one isolated QA college/programme/term/section/course. No real user session or consent is used. The initial harness used UAT's settings URL and an institute fixture without the enterprise plan; the final checks use the classic PROD `/admin?tab=llm-config`, an explicit privacy-consent selector and the correctly configured synthetic institute. An initial long browser process was stopped by the host; final checks run in bounded role batches with per-screen checkpoints.

The final live download check also found a pre-existing institute candidate CSV assembly bug: a spread was applied to the joined text instead of to the row list, splitting its characters into rows. `ebb982619` / PROD port `c4da74ce2` use the existing `toCsv` writer for the entire matrix. Two tests drive the real Export button and parse its downloaded bytes: a filtered learner with quotes/commas and missing fields, and a no-match result with its ten headers.

**PROD verification complete:** eight roles, 21 distinct screens and eight actual downloads (6 XLSX, 1 CSV, 1 PDF). The final admin dashboard and institute candidate export retest has no issues, and the other six roles have no issues. Checked report signatures/parsing, aligned columns, headers on empty sheets, column widths, distinct learner IDs and duplicate rows; the two-page practice PDF was visually inspected on both pages. The case-only dropdowns are distinct, the plan-menu search and LLM provider/budget screens render, assigned home/progress and college course access render, and there are no active page errors or failed platform requests on the verified routes. One generic 3-second dropdown-open timeout passed on the final targeted retest. The repository-wide TypeScript diagnostics remain the same 19 distinct baseline diagnostics, with no new diagnostics.

**PROD cleanup complete:** all eight synthetic auth identities, their eight privacy agreements, two students, four trainers, and the owned college/programme/year/term/section/course were deleted in a guarded transaction. The cleanup verifies no owned users/students/institute remain. Real users, their agreements and their course/result data were not changed. Evidence: `summary.json`, `final-regression-87.log`, `smoke-*-results.json`, `downloads/`, PDF page previews, `cleanup.log`, migration checks and deployment logs in the PROD evidence directory above.
