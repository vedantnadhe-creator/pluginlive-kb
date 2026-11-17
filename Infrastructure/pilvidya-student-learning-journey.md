# aividya — Student learning journey: Curriculum, Subject Lessons, My Portal, Foreign Languages (UAT, feat/chat-simulations 104a20c9)

## Which page is which
- **Curriculum** (`/student/curriculum`): the student's own syllabus, fixed to their board and class (`curriculum_content` + `curriculum_topics` + `student_curriculum_progress`), with topic progress and Robo mastery vs target. Teacher uploads (`student-360` `portal_content`) appear in a **From your teachers** section grouped subject → topic ("Whole subject" for uploads without a topic), inline under the matching topic row, and as a count on each subject card.
- **AI Topic Lessons** (`/lessons`; `/topic-lessons` is an old alias, not in the menu; renamed from Subject Lessons 2026-11-13): AI topic lessons (`generate-topics`, `topic-lesson`, `topic-media-catalogue`) incl. YouTube video picks; any board/class can be picked; no teacher content, no progress. **Gated by menu key `student.lessons`** (since a4d3a202, 2026-11-17; the menu entry had been hidden and is restored): principals switch it in *Teacher → School Admin → Menu access*, platform admins per school in *Admin → Plan Menus* (school selector). `generate-topics` and `topic-lesson` enforce it server-side via `_shared/lesson-access.ts`: a student call needs a valid `student_profile_id` + `session_token` and `student_menu_enabled(student,'student.lessons')`; staff calls need a JWT with admin/principal/hod/teacher/trainer role; anonymous → 401, switched off → 403. Subjects & Topics uses the same switch for AI starter lessons/quizzes.
- **AI content reuse:** quizzes, mock tests, labs, competitive questions, FL packs and flashcards are stored once and reused across students, never repeated for the same student — see `pilvidya-ai-content-reuse.md`.
- **Subjects & Topics → Lessons button** (a4d3a202): expands the topic's lesson choices inline directly under that topic (`aria-expanded`, panel `topic-lessons-<id>`); before, the list rendered after the whole topic list so the button looked dead. Each choice requests its own subtopic lesson (`topic-lesson` mode standard, cached in `topic_lesson_cache`; first uncached open takes ~20–40 s).
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

## Student Today and Progress summary (UAT 104a20c9, database 2026-11-15)

- `/student` is the student's single home: it opens on the next best action, due work, fees, weekly activity, resume items, weak topics and a question of the day instead of the former multi-dashboard landing experience.
- `/student/progress` reuses the same learning summary so streaks, recent activity and weak-topic recommendations do not disagree between screens.
- `public.student_learning_summary(uuid)` is the scoped RPC used by the browser and `parent-weekly-insights`. It accepts the student's profile id only when the caller is the student, linked parent, same-school teacher or platform admin; the service role is allowed only for already-authorised edge functions.
- The RPC counts a learning day only for a real action (answer, completed topic/quiz, homework submission, assessment, Robo class or practice), uses India time for streaks, and returns resume items, weak topics, subject trends and a class/board-matched question of the day.
- `public.topic_lesson_cache` is an RLS-protected service-role cache used by `topic-lesson`; students do not receive direct table access. `student_question_history.created_at` and `sqh_student_created_idx` support the summary's recent-activity queries.
- The migration is recorded in DB-Scripts as `EduSpeak Postgres Migration/20261115T125311Z__pilvidya_student_today_learning_summary.sql` (`19dfd1f`); UAT is applied to `eduspeak_uat`, DEV is hosted Supabase, and PROD remains pending.
- After applying this migration or any new RPC on UAT, run `NOTIFY pgrst, 'reload schema';` and verify the authenticated student path. The live check for student `9820065335` returned RPC HTTP 200 with no page errors or failed requests.

## Tests
- `~/pilvidya-checks/due-items/` — `due-items-test.sql` (rolled back), `ui-check.cjs` (LIVE=1 for live), `seed-live.sql` / `cleanup-live.sql`.
- `~/pilvidya-checks/student-journey.cjs` (BASE=UAT URL; 16 checks: upload→approve→publish, My Portal + Curriculum listing, Start for teacher and curriculum lessons, written notes, goals, languages, French videos).
- Homework (Student → Homework) and Timetable & Attendance (Student → Timetable & Attendance): see `pilvidya-homework-timetable.md`.

## Curriculum topic page = 5-step learn flow (UAT 2e1d2b71, 2026-11-15)

`components/student/TopicLearnFlow.tsx` (+ pure helpers `lib/topicLearnFlow.ts`) replaces the old long topic page.

- **Steps**: Learn (lesson split by `####` sections, one per screen, "Listen" via Robo Teacher TTS in the subject's
  language) → Example (AI `examples` from topic-lesson, previously discarded) → Key points (the lesson's "Key Points"
  list + summary) → Quiz (one question at a time, Check answer → why; "Different questions" = fresh AI set) → Done
  (score, Revise with Robo Teacher, Ask AI Coach, Quiz again, mock test for Class 6+, Print or save notes). Steps
  without real content are skipped.
- **Only real content**: the fallback pack's template lesson / quiz (`mappedTopicToContentRow`) is never displayed —
  skeleton while generating, one automatic retry, then "This lesson isn't ready yet · Try again". Removed for students:
  template takeaways, coaching tips (invented institutes), case studies, study materials, study meter, YouTube-API
  button, Regenerate / Create more / AI PDF search, duplicate PDF + mock-test buttons, prerequisite tip (it compared
  rows across subjects).
- **Language subjects** (tamil, kannada, marathi, …) request the AI lesson and quiz in that language and get larger body
  text; "AI starter lesson" chip only when no published lesson exists (`mapped_only`).
- **Notes**: browser print of `#topic-print-notes` (index.css print rule) replaces the jsPDF export, which could not
  render Indian scripts.
- **Progress fix**: `saveTopicProgress` sent the curriculum_topics id as `curriculum_content_id` for mapped topics →
  FK 409 → progress for curriculum-table topics never saved. Now null for mapped rows; quiz scores save.
- Live check: `~/pilvidya-checks/student-9820065335/learnflow-live.cjs <Subject> "<Topic>" <tag>` (screenshots in `flow/`).
