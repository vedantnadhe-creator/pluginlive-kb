# aividya — Reports, downloads, dropdowns and timetable validation

Live on UAT `51c60207`, deployed 2026-11-18 from `eduspeak-india` branch `feat/chat-simulations`.
This release contains `f0bce7de` (reports and duplicate-data fixes) and `51c60207` (explicit Unicode escape for the CSV byte-order mark).

## Reports and downloaded files

- Client CSV exports use `frontend/src/lib/csvExport.ts`: UTF-8 BOM for Excel, CRLF row endings, quoting for commas/quotes/newlines, empty cells for missing values, and a guard against spreadsheet formulas in text. Numeric values and phone numbers remain data. The subscription-report function uses equivalent CSV handling.
- **Simulation analytics:** CSV columns align with the headers, missing attempts do not crash export, and exports respect the date filter.
- **Subscription reports:** switching tabs clears the previous report before loading the next one; PDF table widths are calculated correctly. Server CSV/XLSX filenames start with `PilVidya_`.
- **Gradebook:** CSV includes the filtered rows rather than just the current page; student filtering is applied. Admin audit-log exports respect the selected date range.
- **Report cards and answer sheets:** corrected report-card fields, PDF page breaks and answer-sheet header spacing. Certificates can only be downloaded when earned.
- **Teacher and wellbeing reports:** exports use the full available filtered list; missing weekly values stay blank, numeric sorting is numeric, and student CSV columns can be re-imported.
- **Invoices and receipts:** print styling and rupee/paise handling corrected; generated receipt HTML declares its charset and escapes user text. Admin-generated print content is escaped.
- **Other exports:** compliance export errors are surfaced, LMS question exports include options and answer text, and evidence-trend exports use the corrected rows.
- **Database dump:** pages order by `id` where that column exists, falling back when it does not; SQL export handles JSONB/array values correctly. This does not guarantee stable pagination for a table without `id`.

## Dropdowns and duplicate records

- Board options are canonicalised to prevent case/alias duplicates. School options no longer repeat once for each person belonging to the school.
- Same-name people and campuses are distinguished with their available identifying details; duplicate model aliases are removed, and status/content-type options use display labels.
- Question upload skips questions already present in the matching question bank.
- Dropout-report generation requires authenticated staff or an authorised internal caller. School staff are scoped to their own school; admins can select a school. When reports are produced, re-running generation replaces that school/period's rows. The report list keeps the newest row per class.
- Student curriculum opens the available lesson while the YouTube lookup finishes.

## Teacher timetable

At `/teacher/ops#timetable`, periods retain the class's mapped subject teacher rather than assigning every period to whoever presses Save. UI validation and `teacher_replace_timetable_slots(uuid,jsonb)` reject booking one teacher into another class at the same day and period in the same school.

Migration `20261205010000_timetable_subject_teachers.sql` was already applied on UAT before this frontend release. Its function body was verified against the release (`md5(prosrc) = 8d63c5499dc2c4c91315c6607a5e276a`); it was not re-applied during this deployment.

## Deployment and verification

- UAT checkout and frontend image: `51c60207` / `eduspeakreact:51c60207`. Public `/chunk-manifest.json` reports the same revision; the container is healthy. `/`, `/student-entry`, `/auth`, `/admin/login`, `/parent/login` and `/healthz` returned HTTP 200.
- Rebuilt on the UAT host through `~/auto_deploy.sh pilvidya feat/chat-simulations`, using the UAT environment and a build without cache. The bundle passed the DEV-URL guard before the frontend container was replaced.
- Deployed `database-dump`, `dropout-report-generate` and `subscription-reports`; all three live files match the GitHub release. Unauthenticated calls are rejected: the first two return 401; subscription reports use the shared HTTP-200 error envelope with `ok:false`, `Admin access required`.
- **Held-function guard restored:** `~/eduspeak-sb/deploy-frontend.sh` had lost `--exclude-from`, and all 55 entries in `functions.hold` were present in the live directory. They were moved to `~/eduspeak-sb/functions.quarantine-20261118T075557Z`. The helper now requires a nonempty hold list, excludes it during rsync, preserves the local `main/` dispatcher, and refuses a frontend bundle containing DEV URLs. The local source helper at `~/pilvidya-checks/deploy-frontend.sh` matches. All 55 held endpoints returned 404 after deployment. Helper backup: `deploy-frontend.sh.bak-20261118T075557Z`.
- Browser download smoke: `reports/sweep.cjs teacher '/teacher#students'` and `reports/sweep.cjs admin '/admin#audit-log'` under `~/pilvidya-checks/`. Both had zero page, dropdown or dead-button issues. Outputs: `reports/out-uat-51c60207/`.
- `reports/check_files.py` found zero problems: teacher CSV (53 rows, 6 columns), teacher PDF (2 pages, no text outside page bounds or garbled glyphs), admin audit CSV (118 rows, 9 columns). Run with normal `python3`; `python3 -I` hides the installed user-site PyMuPDF package.
- The 9 targeted CSV/campus/timetable regression tests passed before deployment. Full repository lint/typecheck remain failing, including syntax errors in unchanged files; the prior full Vitest run stalled and was stopped. These deployment checks are not a complete all-journey QA sign-off. The Jev regression suite was not started as part of this release.

PROD was not deployed.
