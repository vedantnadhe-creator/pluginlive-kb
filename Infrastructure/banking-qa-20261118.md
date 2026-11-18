# Banking UAT QA — 18 November 2026

The saved journey fixes and the issues found during live retesting are pushed to GitHub `UAT` and `main`, and live at https://banking.uat.pluginlive.com on `70dd72d06`.
The final frontend was built on UAT via `auto_deploy.sh banking UAT`; snapshot `20261118T085018Z`, bundle `index-DAV_H3nn.js`, 129 edge functions and 3 self-hosted fixups. PROD was not changed.

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
