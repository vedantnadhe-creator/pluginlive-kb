# PilVidya (aividya) — Learning programmes

Live on UAT `69744620` (2026-11-12). Migration `20261117170000_learning_programmes.sql` (DB-Scripts `4b2f82f`).
Tests: `~/pilvidya-checks/chatsim-e2e/programmes-e2e.mjs` (API, 37 checks incl. refusals) and `/tmp/pvqa/prog-ui.cjs` (browser, 19 checks).
Plan menus: Advanced+ for test series, doubt desk, skill projects, science labs (student) and test series, doubt desk, skill reviews (teacher);
every plan for progress cards and teacher development.

## Test Series (`/teacher/test-series`, `/student/test-series`)
- `test_series` (school, title, exam_type NEET/JEE_MAIN/JEE_ADVANCED/CET/CUET/FOUNDATION, class_levels) + `test_series_items` (title, stage chapter/combined/full/foundation, subject for foundation, scheduled_on).
- Students see series for their school and class (RLS via `my_student_scope()`); tests open on/after their date.
- Competitive tests open `/competitive-exam?exam=&mode=actual_mock&series_item=`; the attempt saves `summary.series_item_id`.
- Foundation tests (Classes 6–10) open the Practice mock (`/practice?subject=&class=&mode=mock`); the first Practice result in that subject within 7 days of the date counts.
- `test_series_results(item)`: best score per student, `rank()` and `cume_dist()` percentile within the school. Staff of the school see names; a student sees only their own row; other schools get `forbidden`.

## Doubt Desk (`/student/doubts`, `/teacher/doubts`)
- Edge function `doubt-desk` (student session): `ask` → gateway task `pl/doubt-answer` (syllabus-only; off-topic → `ai_source = gateway_off_topic`), 20 doubts/day; `escalate` → status `escalated`.
- Teachers of the school (or `is_teacher_for_student`) read and answer; trigger `doubt_answer_guard` allows only the teacher answer to change and stamps status/answered_by/at.

## Holistic Progress Card + Skill Passport (`/student/progress-card`, `/parent/progress-card`, `/teacher/progress-cards`)
- `hpc_entries` (student, academic_year `YYYY-YY`, term1/term2, source self/peer/parent/teacher, author, ratings on 6 domains × beginner/proficient/advanced, strengths, to work on).
- `hpc_guard` enforces: self = own; peer = classmate in the same school and class (not self); parent = verified linked child; teacher = student in the teacher's school.
- `hpc_card()` returns all sources with peer authors hidden, for the student, a linked parent or school staff. `my_classmates()` lists peers.
- `skill_passport()` = approved skill projects + completed Robo classes. Printable.

## Skill Projects (`/student/skills`, `/teacher/skill-reviews`)
- 6 `skill_modules` labelled with the CBSE skill module they align to (AI, Coding, Financial Literacy, Design Thinking for 6–8; Data Science, Mass Media for 9–10), 3 projects each. No 11–12 modules yet.
- `skill_project_submissions`: student writes the work (status forced to submitted, approved work locked); teacher can only set status/feedback.

## Teacher Development (`/teacher/development`)
- 4 `teacher_micro_courses` (AI in the classroom, Robo classes, chat simulations, competency-based assessment), 3 lessons + 3-question quiz each.
- Table not readable by users; `teacher_micro_course_catalog` view (staff only) hides answers; `submit_micro_course_quiz()` grades on the server and issues `AVS-<code>-<yymmdd>-<6>` certificates at ≥ 70%. Correct answers are returned after grading (a retry can copy them; fine for learning, not an exam).

## Classes 1–5
- 127 CBSE global `curriculum_topics` (school_name 'NEP foundational defaults'): English, Hindi, Mathematics for 1–5, EVS for 3–5. Competency-style topic names, not textbook chapters.
- `CLASSES`, `PUBLIC_MIN_CLASS` (1) and `resolveNep2020ClassLevel` (min 1) now allow Classes 1–5.

## Science Labs (`/student/labs?lab=ohm|pendulum|lens|indicator|atom`)
- Front-end only, computed from textbook formulas: Ohm's law (I = V/R, P = VI), pendulum (T = 2π√(L/g), Earth/Moon/Mars), convex lens (1/v − 1/u = 1/f, Cartesian signs, ray diagram), indicators (litmus, phenolphthalein, turmeric by pH), 3D Bohr atom Z 1–20 (shells 2,8,8,2, valency).
- Curriculum topic rows show a Lab button when the subject is science/physics/chemistry and the topic matches (`lib/scienceLabs.ts`).
