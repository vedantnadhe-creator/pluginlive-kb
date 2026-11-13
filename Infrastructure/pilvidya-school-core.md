# aividya — School core: setup, promotion, My Day, My Class, exams → report cards, parent messages, fees (UAT, feat/chat-simulations 31e375c5)

The day-to-day running of a school. Every write is a SECURITY DEFINER function that checks the caller; the browser
never writes these tables directly. Migrations: `20261118210000_school_setup_day_and_exams.sql`,
`20261118220000_parent_messaging_and_fee_collection.sql`.

## Who sees what
| Screen | Who | What |
|---|---|---|
| School Admin → **School setup** (`/teacher/school-admin`, first tab) | Principal | Academic years (one current), terms (inside the year, no overlap), classes & sections (Nursery, LKG, UKG, 1–12; section upper-cased), class teacher, subject teacher per class, move students in/out of a section; banner with students in no section |
| School Admin → **Year-end promotion** | Principal | "Create next year's classes" (grade + 1, same section; lowest grade kept); per class choose the target class, tick who is held back; Class 12 → graduated; new year becomes current; re-running skips students already moved (`student_promotions`) |
| **My Day** (`/teacher/today`, `teacher.my-day`) | Teachers | Today's periods from `timetable_slots` (+ cover periods from `teacher_substitutions`), Now badge, "Take attendance" per period (starts from the day's register, so absentees stay absent); class teacher's register; to-do: homework to mark, exam marks to enter, escalated doubts, homework due in 2 days |
| **My Class** (`/teacher/my-class?class=`, `teacher.my-class`) | Class / subject teachers, principal, HOD | Per student: attendance % and absences (30 d), homework done/set (30 d), last **locked or published** exam %, parents linked; flags <75% attendance, 2+ homework missing, <40% exam. Message parents: presets Absent today / Homework missing / Needs attention / Whole class, or ticked students |
| **Exams & Marks** (`/teacher/exams`, `teacher.exams`) | Principal/HOD create & publish; subject teacher enters marks; class teacher writes remarks | Exam = class level + subjects (max, pass, date) + optional term. Status draft → marks open → marks locked → published (locked/published can reopen; unpublish deletes the exam's report cards) |
| School Operations → **Report cards** | Staff; students/parents in their Report Cards | Exam report cards appear in the existing panel + PDF; principal can add a remark on exam cards |
| **Fees** (`/teacher/ops#fees`, `teacher.fees`) | All staff see invoices; only principal, finance ops role, `institute_users.role` accounts/institute_admin, platform admin can record payments and see "Who has not paid" | Record payment → numbered receipt, parents notified in-app |

## Rules worth knowing
- **Register** (`mark_daily_attendance`): class teacher, principal, HOD only; today or last 7 days. Absent/late → one in-app `notifications` row per linked parent per child per day.
- **Period attendance** (`mark_period_attendance`): anyone who `can_teach_class` (class teacher, mapped subject teacher, teacher with a slot, principal/HOD); unique per student/date/period.
- **Marks** (`exam_save_marks`): only while marks open and only for a subject the teacher is mapped to for that grade (`teacher_class_mappings`, by class_id or class_level) or principal/HOD; 0 ≤ marks ≤ max; absent → AB.
- **Report card** (`_exam_build_report_cards` on publish): per subject marks, `marks_pct`, CBSE 8-point grade (A1 >90, A2 >80, B1 >70, B2 >60, C1 >50, C2 >40, D ≥33, E), descriptor "42 / 50"; overall total, %, grade, rank ("Rank 1 of N"), result PASS / NEEDS IMPROVEMENT (below pass mark in any subject or <33%) / NOT ASSESSED; attendance over the term (or year) up to the exam end; class-teacher remark; co-scholastic grades A/B/C in `standards_summary.coscholastic`. Stored in `report_cards` with `exam_id`.
- Students and parents read exams/marks/notes only once **published**, only their own.
- **Parent messages**: read/insert/mark-read limited to the parent of the student and that student's own teachers (`can_message_about_student`); a trigger lets participants change only `read_at`. Before this, any teacher could read/write every school's messages and mark-read failed (missing `updated_at` column).
- **Fees**: `fee_record_payment` locks the invoice, refuses more than is due, needs a reference for UPI/cheque/DD/bank transfer, writes `payment_receipts` with `RCT-<school code>-<year>-<00001>` from `fee_receipt_counters`. Trigger `trg_fee_invoices_guard_paid` blocks direct `amount_paid`/paid status edits by signed-in users (service role and platform admins allowed, so reconcile/Razorpay functions still work).
- `terms` / `academic_years`: any teacher could write them before; now only the setup functions (principal) and platform admins.

## Gotchas
- UAT has no Razorpay keys: "Pay link" fails; offline payments with receipts work.
- New alerts/messages are in-app only (no WhatsApp/SMS provider on UAT).
- My Day is empty until the school enters a timetable (School Operations → Timetable).
- The 56 held edge functions (`~/eduspeak-sb/functions.hold`) are not needed by these screens and stay held.
- Checks: `~/pilvidya-checks/school-core/` — `school-core-test.sql` (54) + `messaging-fees-test.sql` (27) rolled back; `ui-check.cjs` (28, stubbed); `live-check.cjs` with `seed-live.sql` / `cleanup-live.sql` (live UAT).
- PROD: none (no aividya PROD).
