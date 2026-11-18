# Banking LMS — College curriculum agent

Live on **UAT** (`e6096148a` with reconcile + Re-check, 2026-11-16; first release `20686f31c`) and **PROD** `lms.pluginlive.com` (`release/prod-v1.1` `e6f88e08`, tag `v1.1.15`, 2026-11-16; reconcile + Re-check `de9bbd5c7`, tag `v1.1.16`).
Code: `bankingjobreadiness` — `supabase/functions/college-curriculum-agent`, `supabase/functions/_shared/curriculum-agent-checks.ts`,
`src/components/college/CurriculumAgentPanel.tsx`, `src/lib/curriculumAgentApi.ts`. Migrations `20261116150000_college_curriculum_agent.sql`,
`20261116160000_curriculum_agent_offering_link_no_fk.sql` (DB-Scripts folder *Banking LMS College Mode*).

**Quality controls** (source provenance, duplicate check, evidence-checked lessons, HOD maker-checker; see the section below) are
live on **UAT** (`e89cd43bb` + `69cf6c3ae`, 2026-11-18) and **PROD** (`release/prod-v1.1` `b831175c2`, tag `v1.1.27`, 2026-11-18, backup
`/data/backups/prod-20261118T045457Z`). Migration `20261118100000_curriculum_quality_controls.sql` is applied on DEV, UAT and PROD.

## What it does

**Academics → Curriculum agent** (college-mode institutes; academic admins and platform admins build syllabus versions). Faculty,
HODs and principals work on lessons from the course workspace (tab **Lessons from textbook**) and the HOD inbox (see below).

1. **Documents.** Per programme the admin uploads the approved syllabus PDF (university / deemed / autonomous) and the prescribed
   textbooks (PDF, max 50 MB, bucket `curriculum-sources`, path `<institute>/<programme>/<uuid>.pdf`). A textbook needs the
   "college holds a licence or library copy" tick; its text is used only to draft lessons and is never shown to students.
   Every upload records its **source** (`issuing_body`: university, deemed university, autonomous, AICTE/UGC model curriculum,
   college website, publisher, author's e-book repository, library copy, other) plus optional link, publisher, edition, ISBN.
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
   (one subject per unit; rebuilding a unit replaces it), mapped to the institute. Every lesson and question must carry a word-for-word
   quote from the pages; see *Quality controls*. The unit waits for the HOD; the section courses (`course_offerings.curriculum_id`)
   are linked on approval. Scanned textbooks are refused with a message (upload the text PDF / ebook). A unit the book does not
   cover is refused ("… does not seem to cover unit N").

The agent does **not** search for or download textbooks; colleges upload licensed copies.

## Quality controls (UAT + PROD, 2026-11-18)

Roles (`private.can_contribute_curriculum(program)`, `private.can_check_curriculum(program)`):
- **Contributor** — academic admin, principal, HOD of the programme's department, faculty teaching any course in the programme
  (`course_faculty` → offering → section → programme). Contributors read the programme's sources/versions/courses, upload sources
  (storage + row; delete only their own) and build lessons.
- **Checker** — the HOD of the programme's department; when that department has no HOD, the principal or an academic admin.

Checks:
- **Duplicates** (`read_source`): sha256 of the file and sha256 of the normalised text (≥ 2,000 chars). A second copy in the same
  programme + kind, whether the same file or a re-saved copy with the same text, fails with "Duplicate of "<title>" uploaded on
  <date>. Delete this copy." (`duplicate_of` set). Hashes are written only by the agent (trigger `curriculum_quality_guard`).
- **Mapping**: the textbook must belong to the course's programme and institute.
- **Hallucination** (`_shared/curriculum-quality.ts`, `checkUnitContent`): each lesson needs ≥ 1 and each question 1 quote from the unit's
  pages, at least 5 words. A quote counts when it matches the pages exactly (ignoring case, punctuation and spacing), or when 80% of
  its 4-word runs are on the pages. Unsupported lessons and questions are dropped. If nothing survives, nothing is saved (422).
- **Duplicates in content**: lessons with ≥ 0.8 key-word overlap are dropped. Question stems already used in the unit or in other units
  of the course are dropped. Malformed questions (fewer than 2 or more than 6 options, repeated options, bad answer index) are dropped.
- **Report** saved in `curriculum_subjects.metadata.quality` and shown to the HOD: prescribed book yes/no (title match against
  the syllabus textbooks); kept/removed counts; lessons copying ≥ 12 words verbatim (flagged, not removed); syllabus topic
  coverage with the missing topics.

Maker-checker:
- Unit state lives in `curriculum_subjects.metadata` (`review_status` pending/approved/returned, `built_by`, `built_at`,
  `reviewed_by`, `reviewed_at`, `review_note`). The course aggregate is `curriculum_build_courses.content_review_status`
  (+ note, checked by/at). Clients cannot change these (guard triggers); only the agent and the definer RPCs can.
- `review_curriculum_content(course, 'approve'|'return', note)`: checker only. Return needs a reason. **The person who built
  a pending unit cannot approve it.** Approve links the section courses.
- `curriculum_content_for_review(course)` returns units, lessons, quotes, questions, report and `can_check` to contributors.
  `curriculum_review_queue(institute)` is the checker's inbox: draft versions to publish plus courses with pending lessons.
- **Robo Faculty** grounds a class only on units that are not pending or returned. Content without `review_status` (built before
  2026-11-18) counts as approved.
- **Publish** (`publish_curriculum_build` → `private.assert_can_publish_build`): only the programme's checker, and never the
  person who created the version. The academic admin still accepts or rejects courses. The HOD sees a read-only version review
  with **Publish** in the inbox. A college with one admin and no HOD or principal cannot publish its own versions; another admin,
  a principal or a PluginLive admin must.

UI: Trainer portal → **College overview** opens with *Curriculum waiting for your review*, shown only when there are items.
Course workspace → **Lessons from textbook**: pick or add a textbook, Build / Rebuild per unit or Build all, status, built by,
checks, an expandable lesson view with quotes and answers, and HOD Approve / Return. The admin Curriculum agent's "Lessons"
dialog is the same panel.

Measured on UAT 2026-11-18 (CS25C01, 6-page test book): 5 lessons and 15 questions, all verified, prescribed yes, coverage 16–17
of 18 topics. A build takes 16 s to about 3.5 min depending on the gateway (the page waits up to 4 min). If the page is closed
during a build, the result is still saved.

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

## SRM Easwari Engineering College — Anna University curricula (UAT + PROD, 2026-11-16)

**PROD (2026-11-16 ~18:05Z, user's go):** the confirmed UAT result was copied, not re-generated: 37 PDFs uploaded to PROD storage at the same paths; `curriculum_sources` (37), `curriculum_builds` (37 published + 4 archived), `curriculum_build_courses` (7,787) and the 899 `course_offerings` imported with the same ids (institute, programme and section ids are identical on UAT and PROD); the 1,172 modelled courses removed (no activity; backup `/data/backups/srm_prod_old_offerings_20261116.csv` on the PROD VM). Fingerprint of (section, code, credits) identical on UAT and PROD; 0 empty sections, 500 memberships unchanged.

 Source: Anna University CAC pages for **non-autonomous affiliated
colleges** (`cac.annauniv.edu/aidetails/ai_ug_cands_2021ft.html`, `…ug_cands_2025ft.html`, `…pg_cands_2025ft.html`).
Batches → regulation: 2023/2024 batches (Sem 5–8) **R2021 (Revised)**, 2025/2026 batches (Sem 1–4) **R2025**; PG (2025/2026
batches) R2025. 37 official PDFs (15 UG × 2 + 7 PG; R2021 books 337–421 pages), one syllabus source + one version per programme
and regulation (`AU R2021` / `AU R2025`), all **published**. Kit: `~/banking-checks/srm-anna/` (`manifest.tsv`, `run.cjs`,
`recheck.cjs`, `publish-all.cjs`, `plan.json`); ~900 AI calls, ~45 min wall time with 8 in parallel.

**Review rule applied (as the reviewing admin):** accept non-elective courses with a real course code in the semesters the
regulation covers; elective slot rows ("PROFESSIONAL ELECTIVE – I") rejected; a semester whose accepted credits exceed the printed
total is **held** (rejected, old courses kept; hand-corrected the same day, see below): R2021 Civil Sem 5–6, CSBS Sem 7, IT Sem 5, and R2025 M.E. Structural Sem 3
(no printed totals, 17 courses). Result: **887** Anna University section courses placed; **1,132** old script courses removed from
sections that received agent courses (backup CSV `~/banking-sb/snapshots/srm_script_courses_removed_20261116.csv` on UAT); 40 old
courses remain only in the held semesters; 0 empty sections; 500 student memberships unchanged. R2021 Sem 5–8 carry few core
credits by design (most credits are elective slots), so the red total checks on those versions count the slot rows.

**Held semesters hand-corrected 2026-11-16 (user confirmed Anna University's affiliated curriculum is right for SRM Easwari).**
New versions copied from the published ones (no AI), corrected from the PDF scheme tables, published (old versions archived):
R2021 Civil Sem 5 CE3501/CE3502/CE3503/CE3511 lab/CE3512 project (12 cr = 21 − 3 PE) and Sem 6 CE3601/CE3602/AG3601/CE3611 lab
(11 cr = 23 − 3 PE − OE); R2021 CSBS Sem 7 GE3791 (2 cr = 14 − 4 slots); R2021 IT Sem 5 CS3591/IT3501/CS3551/CS3691/IT3511 lab
(16 cr = 22 − 2 PE); R2025 M.E. Structural Sem 2 ST25201/ST25202/ST25203/ST25204 lab (12 cr; 5 elective options removed) and
Sem 3 ST25301 training + ST25302 Project Work I (8 cr). Mixed-in elective options became unplaced electives; corrected rows are
marked `edited` (kept on regenerate). Script `~/banking-checks/srm-anna/held_fix.sql` (one transaction, temporary admin removed).
The last 40 script courses were removed (CSV `srm_script_courses_removed_held_20261116.csv` in UAT `~/banking-sb/snapshots/`).
**SRM on UAT now: 899 section courses, all from the agent, 37 published versions, 0 empty sections.**

Caveat (resolved — user confirmed Anna University's curriculum is correct): SRM Easwari is an **autonomous** institution with its own R2023 curriculum (codes like `231CSC301T`); Anna University's
affiliated-college curriculum was used on the user's instruction.

## Known gaps

- A college needs a checker before anything can be approved or published: a HOD per department (Academics → Heads of department),
  or else a principal or academic admin. Rajeev Gandhi College of Management Studies (PROD) had no HOD, no principal and no
  institute-role user on 2026-11-18, so only PluginLive platform admins could approve or publish there.

- Students do not yet see the linked lessons in My Courses (`course_offerings.curriculum_id` is set but not rendered).
- Deleting a whole college that has sections fails in one cascade (older college-mode issue: `class_sections` →
  `academic_terms`). Delete in order (see `~/banking-checks/curriculum-agent/cleanup.sql`).
- `Development` has no college-mode code, so DEV deploys remove this function from the DEV stack.

## Checks

Quality controls: `~/banking-checks/curriculum-quality/` on DEV. On PROD (2026-11-18), `prod-rgcms/` ran the whole chain inside
Rajeev Gandhi College of Management Studies, on an isolated QA programme and section created by `fixture.sql`: 21 PASS covering
syllabus maker-checker (the creator cannot publish, faculty cannot, the HOD publishes) and lessons (duplicate refused, build, the maker
cannot approve, HOD approve, and a return with its reason). `db-rules.sql` also gave 20 PASS on PROD. Cleanup: `cleanup-files.cjs`
(storage API, so files leave the bucket), then `cleanup.sql`. `db-rules.sql` runs 20 role/maker-checker checks in a rolled-back
transaction (DEV + UAT 2026-11-18, all PASS). `e2e.cjs` is the live API flow (12 PASS): upload, both duplicate kinds, a student is
refused, build, faculty cannot approve, inbox, HOD approves. `neg.cjs` checks that an uncovered unit is refused. `ui.cjs` drives the
faculty tab and HOD inbox in a browser. Test book from `make_book.py`. Fixtures: `../journeys/fixture.sql` + `approve.sql`; cleanup
with `cleanup.sql`, then `../journeys/cleanup.sql`. Unit tests: `src/test/curriculumQuality.test.ts`.

`supabase/tests/college-curriculum-agent.sql` (rolls back; run on DEV, UAT and PROD 2026-11-16), `src/test/curriculumAgentChecks.test.ts`,
API/browser scripts in `~/banking-checks/curriculum-agent/` on DEV (`flow.cjs`, `content.cjs`, `publish.cjs`, `regen.cjs`, `rep.sh`,
`ui.cjs`; `CAG_ENV_FILE` / `CAG_BASE` point them at UAT). QA fixtures `fixtures.sql` / `cleanup.sql` + `cleanup-files.cjs`.
