# Banking LMS — College curriculum agent

Live on **UAT** (`e6096148a` with reconcile + Re-check, 2026-11-16; first release `20686f31c`) and **PROD** `lms.pluginlive.com` (`release/prod-v1.1` `e6f88e08`, tag `v1.1.15`, 2026-11-16).
Code: `bankingjobreadiness` — `supabase/functions/college-curriculum-agent`, `supabase/functions/_shared/curriculum-agent-checks.ts`,
`src/components/college/CurriculumAgentPanel.tsx`, `src/lib/curriculumAgentApi.ts`. Migrations `20261116150000_college_curriculum_agent.sql`,
`20261116160000_curriculum_agent_offering_link_no_fk.sql` (DB-Scripts folder *Banking LMS College Mode*).

## What it does

**Academics → Curriculum agent** (college-mode institutes; academic admins and platform admins only).

1. **Documents.** Per programme the admin uploads the approved syllabus PDF (university / deemed / autonomous) and the prescribed
   textbooks (PDF, max 50 MB, bucket `curriculum-sources`, path `<institute>/<programme>/<uuid>.pdf`). A textbook needs the
   "college holds a licence or library copy" tick; its text is used only to draft lessons and is never shown to students.
   `read_source` extracts text page by page (unpdf); under ~100 characters per page it is marked **scanned**.
2. **Build a version** (`start_build` → `extract_next` until it returns `draft`). The syllabus is read in page ranges of at most
   10 pages / 18,000 characters (8 pages for scanned PDFs, which go to the model as PDF pages). Each range returns courses
   (semester, code, title, credits, L-T-P, type core/elective/lab/project/audit/other, units with topics, prescribed textbooks,
   page numbers) plus the semester credit totals printed in scheme tables. The same code from several ranges is merged.
3. **Checks + self-repair.** Per semester the course credits (audit excluded) must equal the printed total; every non-elective
   course needs a semester and (except audit) credits; missing units / textbooks and odd code formats are warnings. If an error
   remains after the last range, one extra `extract_next` re-reads only the scheme pages with the failures listed and applies
   corrections **only for codes printed on those pages** and never to courses an admin edited. Remaining errors show in red.
3b. **Reconcile (deterministic, before and after the repair pass; `reconcile()` in the shared module).** An elective *option* with a
   real course code loses its semester (only elective *slot* rows belong to a semester). In a semester that matches the printed
   total only when its "audit" courses are counted, those courses become core (Anna University R2025 Life Skills / Physical
   Education are 1-credit and counted). Admin-edited courses are never changed. **Re-check against syllabus** (action `recheck`,
   draft only) re-runs reconcile + one more repair pass + the checks. The repair pass falls back to the first two page ranges
   when no scheme table was detected.
4. **Review.** Per semester: accept / reject / edit (semester, code, title, credits, type), "Accept all without errors".
   Edited courses are marked `edited`.
5. **Publish** (`publish_curriculum_build`): every pending course must be decided. Accepted non-elective courses are upserted
   into each section of the programme whose term has that semester number (`course_offerings`, matched on section + code,
   linked by `build_course_id`); elective options are reported and placed through elective groups. The previous published
   version of the same programme + regulation is archived; its courses that the new version dropped are removed unless they have
   activity (class sessions, grade components, assignments or lectures), which are kept.
6. **Delete** (`delete_curriculum_build`): same activity rule; kept courses are unlinked. **Regenerate**: new draft from the same
   syllabus with `replaces_build_id`; edited courses and already built lessons carry over.
7. **Lessons from the textbook** (`build_content`, per unit): the agent maps units to textbook pages once per textbook
   (`unit_pages`), then writes 3–6 lessons in its own words with page citations and 3 MCQs per lesson into a `trainer_curricula`
   (one subject per unit; rebuilding a unit replaces it), mapped to the institute and linked to the published section courses
   (`course_offerings.curriculum_id`). Scanned textbooks are refused with a message (upload the text PDF / ebook).

The agent does **not** search for or download textbooks; colleges upload licensed copies.

## AI route

Task **`pl/college-curriculum`** (gemini-2.5-flash, reasoning disabled → gpt-6-luna, 120 s per attempt, 0 retries, text; PDF
file parts work on the primary). Registered 2026-11-16 on the UAT gateway (policy backup `policy-backups/tasks-20261116T152521Z.json`,
key `banking-app`) and the PROD gateway (backup `policy-backups/tasks-20261116T152550Z.json` on the PROD builder, key
`banking-app-prod`); normal → gemini-2.5-flash and `mock_timeout` → gpt-6-luna verified on both, PDF input verified on PROD.
DEV banking uses the UAT gateway. Tags `service:banking-app,module:college-curriculum-agent`.

## Measured behaviour (2026-11-16)

- 57-page KCG R2023 B.E. CSE syllabus: 131 courses, ~90 s, all 8 printed semester totals matched on UAT (twice) and in most DEV runs;
  a failed check is fixed by the repair pass or shown in red. 336-page CC-BY textbook: 5 units → 26 lessons, 78 MCQs, ~20 s per unit.
- 30-page ranges made the model skip most courses; `temperature: 0` made it loop until the 16k-token cut-off — don't add either back.
  A cut-off answer is a retryable 503; the browser retries each range twice (240 s timeout) before showing "Retry this part".
- The UAT gateway path cuts a single call at about 60 s; ranges are sized to stay under it.

## SRM Easwari Engineering College on UAT — Anna University curricula (2026-11-16)

UAT only (PROD still has the 2026-11-15 script data). Source: Anna University CAC pages for **non-autonomous affiliated
colleges** (`cac.annauniv.edu/aidetails/ai_ug_cands_2021ft.html`, `…ug_cands_2025ft.html`, `…pg_cands_2025ft.html`).
Batches → regulation: 2023/2024 batches (Sem 5–8) **R2021 (Revised)**, 2025/2026 batches (Sem 1–4) **R2025**; PG (2025/2026
batches) R2025. 37 official PDFs (15 UG × 2 + 7 PG; R2021 books 337–421 pages), one syllabus source + one version per programme
and regulation (`AU R2021` / `AU R2025`), all **published**. Kit: `~/banking-checks/srm-anna/` (`manifest.tsv`, `run.cjs`,
`recheck.cjs`, `publish-all.cjs`, `plan.json`); ~900 AI calls, ~45 min wall time with 8 in parallel.

**Review rule applied (as the reviewing admin):** accept non-elective courses with a real course code in the semesters the
regulation covers; elective slot rows ("PROFESSIONAL ELECTIVE – I") rejected; a semester whose accepted credits exceed the printed
total is **held** (rejected, old courses kept): R2021 Civil Sem 5–6, CSBS Sem 7, IT Sem 5, and R2025 M.E. Structural Sem 3
(no printed totals, 17 courses). Result: **887** Anna University section courses placed; **1,132** old script courses removed from
sections that received agent courses (backup CSV `~/banking-sb/snapshots/srm_script_courses_removed_20261116.csv` on UAT); 40 old
courses remain only in the held semesters; 0 empty sections; 500 student memberships unchanged. R2021 Sem 5–8 carry few core
credits by design (most credits are elective slots), so the red total checks on those versions count the slot rows.

Caveat: SRM Easwari is an **autonomous** institution with its own R2023 curriculum (codes like `231CSC301T`); Anna University's
affiliated-college curriculum was used on the user's instruction.

## Known gaps

- Students do not yet see the linked lessons in My Courses (`course_offerings.curriculum_id` is set but not rendered).
- Deleting a whole college that has sections fails in one cascade (older college-mode issue: `class_sections` →
  `academic_terms`). Delete in order (see `~/banking-checks/curriculum-agent/cleanup.sql`).
- `Development` has no college-mode code, so DEV deploys remove this function from the DEV stack.

## Checks

`supabase/tests/college-curriculum-agent.sql` (rolls back; run on DEV, UAT and PROD 2026-11-16), `src/test/curriculumAgentChecks.test.ts`,
API/browser scripts in `~/banking-checks/curriculum-agent/` on DEV (`flow.cjs`, `content.cjs`, `publish.cjs`, `regen.cjs`, `rep.sh`,
`ui.cjs`; `CAG_ENV_FILE` / `CAG_BASE` point them at UAT). QA fixtures `fixtures.sql` / `cleanup.sql` + `cleanup-files.cjs`.
