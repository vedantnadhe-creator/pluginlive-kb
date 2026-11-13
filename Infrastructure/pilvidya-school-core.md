# aividya — School core: setup, promotion, My Day, My Class, exams → report cards, parent messages, fees (UAT, feat/chat-simulations 2c80ab0c)

The day-to-day running of a school. Every write is a SECURITY DEFINER function that checks the caller; the browser
never writes these tables directly. Migrations: `20261118210000_school_setup_day_and_exams.sql`,
`20261118220000_parent_messaging_and_fee_collection.sql`.

## Who sees what
| Screen | Who | What |
|---|---|---|
| School Admin → **School setup** (`/teacher/school-admin`, first tab) | Principal | Academic years (one current), terms (inside the year, no overlap), classes & sections (Nursery, LKG, UKG, 1–12; section upper-cased), class teacher, subject teacher per class, move students in/out of a section; banner with students in no section |
| School Admin → **Year-end promotion** | Principal | "Create next year's classes" (grade + 1, same section; lowest grade kept) also copies **subject teachers** from the same grade + section of the old year into new classes that have none (class teachers are not copied); per class it warns about old-year exams not published and a missing published annual exam, and Promote stays disabled until "Promote anyway" is ticked; choose the target class, tick who is held back; Class 12 → graduated; new year becomes current; re-running skips students already moved (`student_promotions`) |
| **My Years** (`/student/history`, `student.history`); parent Report Cards → "Year by year"; My Class → click a student | Student, linked parent, staff of the school | `student_year_history()`: one card per academic year — class (current class, or `student_promotions.from_class` for past years), promotion outcome, attendance %, report cards, published exam marks by subject, homework set/handed in/average mark. Nothing is copied at promotion; past rows are read by year |
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

## Teacher-assist AI (suggestions only, the teacher saves)
- **Draft remarks with AI** (Exams & Marks → Remarks · class): `school-ai` action `draft_remarks` → `exam_remark_context` (class teacher / principal / HOD only) → gateway task `pl/report-remarks`. 1–2 sentences per student from this exam's marks, attendance and homework; no exact marks, rank or comparisons. Fills only empty remark boxes; nothing is saved until Save remarks.
- **Suggest** (Homework → submission): `school-ai` action `suggest_homework_mark` → `homework_ai_context` (teacher of the homework or school leader) → reads the written answer and up to 3 photos (jpg/png/webp ≤ 4 MB; PDF/Word skipped and listed) → gateway task `pl/homework-mark` → marks (half marks, clamped to max) + feedback filled in; nothing is saved until Mark.
- Measured on UAT 2026-11-13: remarks ~2 s for a class of 2, photo marking ~4 s.

## How promotion and the curriculum work
- The student's class (`student_profiles.class_id` + `class_level`) changes; every student page reads the class from the profile, so the next class's curriculum, timetable and homework show automatically.
- Past-year data (homework, exam marks, attendance, report cards, Robo/practice history) stays in place; homework and exams screens show only the current class, so the past is shown in **My Years**.
- Publish every exam before promoting: an unpublished exam lists students by their *current* class, so after promotion it no longer finds them.
- Subject-teacher rows are per class (`teacher_class_mappings_class_unique` includes class_id), so the same teacher can hold 10 A Maths in two years.

## Gotchas
- Removed 2026-11-13: `frontend/src/components/ai/` (56 files nothing imported), `AdminClassRegistry` page and `admin-manage-classes` function (replaced by School setup). Still declared in `App.tsx` but never routed: TargetVsAchievement, AdminParentRegistry, AdminFeeManagement, AdminAttendanceDashboard, AdminCommunicationGateway, AdminLibraryManagement, AdminCertificateGenerate, AdminReportCardGenerate, AdminHRManagement, AdminTransportManagement, AdminCurriculumManagement.
- UAT has no Razorpay keys: "Pay link" fails; offline payments with receipts work.
- New alerts/messages are in-app only (no WhatsApp/SMS provider on UAT).
- My Day is empty until the school enters a timetable (School Operations → Timetable).
- The 56 held edge functions (`~/eduspeak-sb/functions.hold`) are not needed by these screens and stay held.
- Checks: `~/pilvidya-checks/school-core/` — `school-core-test.sql` (54) + `messaging-fees-test.sql` (27) + `year-end-test.sql` (18) rolled back; `year-end-live-check.cjs` + `year-end-cleanup.sql`; `ui-check.cjs` (28, stubbed); `live-check.cjs` with `seed-live.sql` / `cleanup-live.sql` (live UAT).
- PROD: none (no aividya PROD).
