# PilVidya (aividya) — Teacher classroom tools: Teach Mode, Portion Tracker, Worksheets

Live on UAT `66fecda5` (2026-11-12). Menu items for teachers; plan keys `teacher.teach-mode`, `teacher.portion`,
`teacher.worksheets` are on for every plan. Migration `20261117160000_teach_portion_worksheets.sql`.

## Teach Mode (`/teacher/teach`, optional `?class=&topic=<curriculum_topic_id>`)
- Pick class, subject, topic. Slides: title (topic, textbook ref, subtopics) → published `curriculum_content.lesson_markdown`
  split at `##` headings → video (first approved video) → up to 5 approved `question_bank` questions for the topic
  (Show answer + explanation) → blank whiteboard.
- No published lesson: calls `topic-lesson` (same generator students use, ~15–40 s) and uses its reading
  (intro, sections, key points, summary) and, if the bank has no topic questions, its 5-question quiz. AI-written, not teacher-approved.
- Pen overlay on every slide (4 colours, eraser, clear), resets per slide (not saved). Arrow keys / PageUp/Down, F = full screen.
- "Mark as taught" upserts `topic_portion` (section '') with today's date.

## Portion Tracker (`/teacher/portion`)
- My class: class + optional section + subject → topics in syllabus order with textbook ref, planned date, taught date,
  status (Not planned / Planned / Overdue = planned in the past and not taught / Taught), Taught today, Teach shortcut.
- Textbook editor per topic: book, chapter (1–99), pages, "checked against the book" (`textbook_verified`).
  Students see the reference on `/student/curriculum` only when verified.
- School coverage tab: taught / tracked topics and overdue count per class, section, subject (tracked = has a plan or taught date).
- `topic_portion` RLS: platform admin or `school_id = ANY(sim_teacher_schools())`; trigger stamps updated_by/at and taught_by.

## Worksheets (`/teacher/worksheets`)
- Approved `question_bank` questions for the teacher's board + class + subject (subject ids mapped to the bank's display
  names, e.g. science → Science, social → Social Studies). Filters: search, topic, difficulty, Bloom level, competency-based only.
- Inline tagging writes `question_bank.competency_level` (remember…create) and `is_competency_based` (teacher update policy).
- Print / Save as PDF: header with name/section/roll/date lines, numbered questions with a–d options, answer key with explanations on its own page.

## Data notes (UAT)
- `curriculum_topics.textbook_name` seeded "NCERT <Subject> (Class N)" for CBSE global NCERT subjects (400 rows); chapters and pages are
  NOT seeded (topic order ≠ chapter order).
- Question bank has no topic tags for e.g. Class 9 Science (104 questions with empty topic), so topic filters/quiz slides are thin there.
- `curriculum_content` has only 61 rows (59 published); most topics use the topic-lesson fallback.
