# aividya — Student learning journey: Curriculum, Subject Lessons, My Portal, Foreign Languages (UAT, feat/chat-simulations 121e7e94)

## Which page is which
- **Curriculum** (`/student/curriculum`): the student's own syllabus, fixed to their board and class (`curriculum_content` + `curriculum_topics` + `student_curriculum_progress`), with topic progress and Robo mastery vs target. Teacher uploads (`student-360` `portal_content`) appear in a **From your teachers** section grouped subject → topic ("Whole subject" for uploads without a topic), inline under the matching topic row, and as a count on each subject card.
- **AI Topic Lessons** (`/lessons`, renamed from Subject Lessons 2026-11-13): AI topic lessons (`generate-topics`, `topic-lesson`, `topic-media-catalogue`); any board/class can be picked; no teacher content, no progress. Candidate to fold into Curriculum.
- **My Portal** (`/student/portal`): published curriculum lessons + the school's teacher uploads for the student's board/class, **My goals**, completion and subject progress.

## Teacher uploads → students
- Teacher → Lesson Content → Upload (`TeacherContentUploadPanel`) inserts `teacher_content` (`pending_review`, unpublished) → the teacher Approves then Publishes (`teacher-360` `manage_content`, own school only; admins any).
- Students see approved + published rows for their board (aliases cbse/CBSE…), class and school (or `school_id` NULL) in Curriculum and My Portal; Start opens `/student/lesson/teacher/<id>` (written notes = `body_markdown`, quiz = `quiz`).
- Subject-wide uploads (no topic) are listed; uploads store the subject **name** ("Mathematics"), curriculum rows the **id** ("mathematics") — compare via `SUBJECTS`.
- UAT fixes 2026-11-13: `teacher_content` had no `body_markdown` / `extracted_text` (written lessons were saved as links, notes in description, quiz dropped) and its `content_type` CHECK allowed only pdf/video/link/image/document (lesson/ppt/doc/xls failed). DB-Scripts `…__teacher_content_lesson_text_columns`, `…__teacher_content_type_lesson_office`; PROD pending.

## Goals
- One row per student and subject in `goal_target (student_id, subject name, target_percent)`; written by the student (RLS `current_student_profile_id()`), read by teachers, parents, Robo Teacher.
- My Portal **My goals** (`PortalGoalsCard`): every subject of the class (`getCurriculumSubjects`), target input, current = Robo Teacher mastery (avg of last 5 classes, `robo-teacher get_coach`) else practice/mock accuracy (`student_progress`), "N points to your X% goal", lessons done.
- Dashboard Learning Goals uses accuracy % (was a correct-answer count); gap is green only when reached.
- `components/ui/progress.tsx` track is `bg-muted` (theme `--secondary` is blue, so empty bars looked full).

## Foreign Languages
- Languages come from `foreign_language_catalog` (falls back to `lib/foreignLanguages.ts` only when the table is empty): 10 on UAT incl. Korean (`ko`) and Indonesian (`id`), added 2026-11-13.
- A **Foreign Language** (2nd/3rd language) subject card shows on Curriculum and AI Topic Lessons for Class 6–12 (CBSE/ICSE/State) and every IB class (`offersForeignLanguage` in `subjectMatrix.ts`); it opens Foreign Languages. It is not in the topic-mapped subject list (mock tests, practice, teacher mapping).
- Curriculum YouTube videos: `curriculum-videos` → `_shared/video-verification.ts` maker (deterministic) + checker (`pl` gateway, Gemini). Query from `lib/foreignLanguageVideoScope.ts`: `Learn <language> <CEFR> <topic> <beginners|intermediate|advanced> lesson`. For CEFR scopes the maker accepts topic word stems (5 letters) and level words, and the checker does not require a board/class mention. Results cached in `topic_media` for 7 days. UAT 2026-11-13: French A1 / Spanish A2 12 approved each (was 0).

## Teacher material opens
- The lesson page calls `record_material_view` (open, then completed) → `teacher_content_views`, used by Teacher Growth. See `pilvidya-teacher-growth.md`.

## Dashboard: Due today & next 7 days (UAT `121e7e94`, 2026-11-13)
- `StudentDueTodayPanel` on `/student`: counters Overdue / Today / Next 7 days / Fees to pay (₹), type chips with counts; both drill down. Items grouped Overdue → Today → Next 7 days → No due date; tap opens Start (assessment `/assessment-submit/<id>`, test `/student/test-series`), Pay (`/student/fees`), Open (Robo `/student/robo-teacher?subject=&topic=`, simulations, tasks `/student/progress`).
- Data: `student_due_items(p_days)` (SECURITY DEFINER, `current_student_profile_id()` + own school/class): pending/in-progress assessment assignments, chat sim assignments not scored (`sim_assignments` + `sim_attempts`), test-series items (class in `class_levels`), fee invoices not paid/void with amount left, school events (audience all/students/class_N), live classes, `student_learning_tasks` not completed. Overdue window 60 days. Robo assignments (not done) and spaced revisions come from `robo-teacher get_coach` (`lib/dueItems.ts roboItems`).
- Fixed: `trg_emit_alert_scan()` read `NEW.school_id`; `assessment_assignments` has no such column, so every assignment insert failed (none on UAT since 2026-10-22). Now `to_jsonb(NEW)->>'school_id'`.
- No homework table exists; library returns / transport dues not included.

## Tests
- `~/pilvidya-checks/due-items/` — `due-items-test.sql` (rolled back), `ui-check.cjs` (LIVE=1 for live), `seed-live.sql` / `cleanup-live.sql`.
- `~/pilvidya-checks/student-journey.cjs` (BASE=UAT URL; 16 checks: upload→approve→publish, My Portal + Curriculum listing, Start for teacher and curriculum lessons, written notes, goals, languages, French videos).
- Homework (Student → Homework) and Timetable & Attendance (Student → Timetable & Attendance): see `pilvidya-homework-timetable.md`.
