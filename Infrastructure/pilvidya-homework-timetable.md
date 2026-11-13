# aividya — Homework and student Timetable & Attendance (UAT, feat/chat-simulations eea8c505)

The daily school loop: the teacher sets homework, the student submits an answer and/or photos, and the teacher marks
it or returns it for a redo. Students also see their own periods for the day and week, and their attendance.

## Where
- **Teacher → Homework** (`/teacher/homework`, menu key `teacher.homework`): set homework (class, optional section, subject, title, instructions, optional attachment, due date/time, max marks); "My homework" list with submitted counts; open one to see the class roster: each student's answer and files (signed links), **Mark** (marks ≤ max, optional feedback) or **Return to redo** (feedback required). Cancel stops it showing to students.
- **Student → Homework** (`/student/homework`, `student.homework`): tabs To do / Submitted / Marked. Submit = text answer + up to 5 files (jpg/png/webp/heic/pdf/doc, ≤ 10 MB each). Resubmit allowed until marked; a returned item goes back to To do with the teacher's note. Late = submitted after `due_at` (flagged, still accepted).
- **Student → Timetable & Attendance** (`/student/timetable`, `student.timetable`): Today with **Now** / **Next**, the week grid, and attendance: this month %, present/late/absent/excused, warning below 75%, last 30 days, last-90-days line.
- **Student dashboard → Due today & next 7 days**: homework not yet submitted (or returned) appears as kind "Homework" (Start → `/student/homework`).

## Data (migration `20261118200000_homework_and_student_timetable.sql`)
| Object | What | Access |
|---|---|---|
| `homework` | school, teacher, class_level, section (null = whole class), subject, title, instructions, attachment_path, due_at, max_marks, cancelled_at | read: `can_see_homework` (student of that class/section, the teacher, school admin/principal); insert: own teacher school; update: owner or school admin |
| `homework_submissions` | text_answer, file_paths[], status submitted / returned / marked, is_late, marks, feedback, marked_by/at; unique per homework + student | read only (student own, staff who manage it); writes only via the functions below |
| `submit_homework(p_homework, p_text, p_files)` | files must be under `homework/<hid>/<student>/`, max 5; blocked once marked | student |
| `mark_homework(p_submission, p_marks, p_feedback, p_return)` | marks ≤ max_marks; return needs feedback | `can_manage_homework` |
| `homework_roster(p_homework)` | every student of the class with their submission | manager |
| `student_timetable()` | the signed-in student's `timetable_slots`; if the student has no `class_id`, all sections of their grade (page says so) | student |
| `student_due_homework(p_days)` | due-list items for the panel | student |
| Storage | bucket `pilvidya`, prefix `homework/<hid>/<student>/…`; policies "homework files read/write" via `homework_file_ok(name, write)` | student writes own folder; teacher/student read via signed URL |

Attendance on the student page reads the student's own `attendance_records` (last 90 days). Present + late count as
attended; excused is left out of the percentage.

## Gotchas
- UAT has no real `timetable_slots`: students see "Your school has not published a timetable" until staff add periods (School Admin → timetable).
- Students without a `class_id` see every section's periods of their grade.
- Checks: `~/pilvidya-checks/homework/` (`homework-test.sql` 23 DB checks rolled back; `ui-check.cjs` stubbed; `live-check.cjs` + `seed-live.sql` + `cleanup-live.sh` for a live UAT run).
- PROD: none (no aividya PROD).
