# Banking LMS — College curriculum agent

Live on **UAT** (`20686f31c`, 2026-11-16) and **PROD** `lms.pluginlive.com` (`release/prod-v1.1` `e6f88e08`, tag `v1.1.15`, 2026-11-16).
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

## Known gaps

- Students do not yet see the linked lessons in My Courses (`course_offerings.curriculum_id` is set but not rendered).
- Deleting a whole college that has sections fails in one cascade (older college-mode issue: `class_sections` →
  `academic_terms`). Delete in order (see `~/banking-checks/curriculum-agent/cleanup.sql`).
- `Development` has no college-mode code, so DEV deploys remove this function from the DEV stack.

## Checks

`supabase/tests/college-curriculum-agent.sql` (rolls back; run on DEV, UAT and PROD 2026-11-16), `src/test/curriculumAgentChecks.test.ts`,
API/browser scripts in `~/banking-checks/curriculum-agent/` on DEV (`flow.cjs`, `content.cjs`, `publish.cjs`, `regen.cjs`, `rep.sh`,
`ui.cjs`; `CAG_ENV_FILE` / `CAG_BASE` point them at UAT). QA fixtures `fixtures.sql` / `cleanup.sql` + `cleanup-files.cjs`.
