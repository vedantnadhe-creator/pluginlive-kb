# aividya — Teacher Growth (UAT, feat/chat-simulations 7c50c729)

Measures each teacher on three dimensions from what students and teachers actually do. Growth is against the teacher's
own previous period; principals see teachers alphabetically, never ranked.

## Where
- **Teacher → My Growth** (`/teacher/growth`, menu key `teacher.growth`): period This term (Apr–Sep / Oct–Mar) or Last 30 days; three dimension cards (score 0–100, level, change since previous period), every metric with weight, "Needs data (n of min)" and a next step when < 60; lesson observations (mark next step done); classes & subjects editor.
- **Principal → School Admin → Teacher growth**: school averages, teachers needing support (a dimension at Emerging or down ≥ 10), table with View (full detail) and Record observation.
- **Teacher → Lesson Content → School library**: colleagues' approved material; Adopt counts towards the author's reuse.
- **Student → My Portal → Weekly check-in**: 3 questions per subject per week, anonymous.

## Data
| Table | What | Access |
|---|---|---|
| `teacher_class_mappings` | teacher → class (class_id) or class_level (+ section) → subject; decides whose students count. Unique per teacher/class/section/subject | teacher own; principal of the teacher's school; admin |
| `teacher_content_views` | student opened / completed a teacher's material (`record_material_view`, called by the lesson page) | functions only |
| `student_pulse` | anonymous check-in: school, class, section, subject, week, `respondent_hash` (md5 of student+subject+week), 3 answers 1–5 (`submit_student_pulse`, `pulse_answered_this_week`) | functions only; never per student |
| `lesson_observations` | 5 criteria 1–4, strengths, one next step, follow-up date; teacher ticks done via `mark_observation_step_done` | principal / HOD of the school write; teacher reads own; nobody observes themselves |
| `content_adoptions` | colleague adopts approved material of the same school | school staff read; own insert/delete |

## Engine (`_growth_compute`, `teacher_growth`, `school_teacher_growth`)
Metric min-data rules: a metric scores only with enough data; a dimension is the weighted average of scored metrics.
Levels: < 40 Emerging, 40–59 Developing, 60–79 Proficient, ≥ 80 Leading. Growth only when the teacher's classes were mapped before the period.

| Dimension | Metrics (weight, min data) |
|---|---|
| Student engagement | Assignment completion — Robo + simulation assignments due in period, done ÷ expected (30%, 10) · Weekly active reach — students active in the subject each week (25%, 10) · Student voice — % agreeing (4–5) in check-ins (20%, 10 responses) · Material uptake — opened ÷ students the material was for (15%, 10) · Doubt responsiveness — escalated doubts answered in 24 h (10%, 3) |
| Outcomes | Mastery gain — latest − first Robo mastery per student/topic, 50 + 2.5×gain; school average gain shown (35%, 10 students) · Goal attainment — students at/above `goal_target` (25%, 10) · Topic mastery — taught topics (`topic_portion.taught_by`) with class avg ≥ 60% (20%, 3 topics) · Lift for weakest learners — gain of the lowest starting quarter (10%, 3) |
| Content & methods | Method variety — taught topics with ≥ 2 of Robo assignment / simulation / own material / observed (25%, 3) · Content quality — completion after opening (≥ 10 views) and simulation review scores (25%) · Lesson observation — rubric /20 (20%, 1) · Contribution & reuse — taught topics with own material, colleague adoptions (15%) · Syllabus pacing — planned topics taught within 7 days (15%, 3) |

Gotchas: `topic_portion.section` defaults to `''` (treated as whole class); `robo_assignments.assigned_by` and `topic_portion.taught_by` are login ids, simulation assignments use teacher profile ids; subjects are normalised with `subject_key()` (names and ids).

## Nightly
Scheduled job `teacher-growth-snapshot-nightly` (21:30 UTC) → edge function `teacher-growth-snapshot` (service key only, 401 otherwise) → `teacher_growth_snapshot_all()` → term-to-date row per mapped teacher in `teacher_kpi_snapshots` (`engagement_score`, `outcomes_score`, `content_methods_score`, `metrics`).

## Tests
- `~/pilvidya-checks/teacher-growth/engine-test.sql` — engine + RLS with seeded data in a rolled-back transaction (12 checks).
- `ui-check.cjs` (screens with stubbed DB calls, 18), `live-check.cjs` (live UAT, 14), `cleanup-live.sql`.

## Not yet
HOD screen (DB access exists); labs/Teach Mode per topic in method variety; "closed half the goal gap" in goal attainment; term record into `teacher_kpi_history`.
