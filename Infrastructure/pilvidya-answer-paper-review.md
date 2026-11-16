# PilVidya (aividya) — Handwritten answer papers: upload, AI draft, teacher approval, release

LIVE on UAT 2026-11-16 (`eduspeak-india` branch `feat/chat-simulations`, app `9956e00e`, SQL fix `3ebcb0aa`). PROD: not deployed.

## Flow
1. **Student** (descriptive assessment → `/assessment-submit/<assignment>`): "Handwritten answer paper" card. Take/choose photos (≤ 10 pages, ≤ 8 MB each after in-browser JPEG compression). Each page is read immediately (vision model, llm-resolver task `alt-submission-ingest`); unreadable pages show "Unclear: remove and retake". **Submit paper** → pages joined in upload order (`--- Page n ---`), assignment `completed`, AI draft created, teacher notified (`answer_paper_submitted`, link `/teacher/ops#review`). Typed answer is still available; uploaded pages replace it.
2. **Teacher QR scanning** (Operations → Alt intake → QR answer sheets) feeds the same pipeline. Extra pages for the same student are **added**, never overwrite (old bug: last page replaced the answer). Each scanned page re-drafts the whole answer.
3. **AI draft** (`descriptive-auto-grade`): if the assessment has `question_ids`, marks each question against `questions.marks` (+ `correct_answer` as model answer) → `ai_breakdown.question_scores`, total = sum. Otherwise rubric/criteria. Writes ONLY to `assessment_grade_reviews` (status `ai_draft`). Refuses if already released.
4. **Teacher review** (Teacher → Operations → Review, `AssessmentReviewPanel` + `AnswerReviewDialog`): original page photos (signed URLs), text the AI read, per-question marks, grading + handwriting confidence. Filters: All / Check first / Not marked / AI draft / Approved / Released. "Check first" = AI confidence < 0.6 or handwriting confidence < 0.6 (listed first). Actions: Approve, Approve & release, bulk **Approve confident** (both confidences ≥ 0.8, RPC `approve_assessment_reviews`), **Release approved** (RPC `release_assessment_results`). A released mark can be corrected and re-released.
5. **Release** copies teacher mark/feedback to `assessment_assignments.final_score/final_max_score/teacher_feedback/released_at/result_breakdown` and notifies the student (`/assessment-submit/<id>`) and verified parents (`assessment_result`). Per-question marks are copied only if they add up to the teacher's final mark.
6. **Student** sees "Awaiting teacher review" until release, then "Marks X/Y", feedback, per-question table, strengths/improvements.

## Data & security
- `assessment_grade_reviews` (PK `assignment_id`): status `pending|ai_draft|approved|released`, page_count, ocr_confidence, ai_*, teacher_*, reviewed_by/at, released_at. RLS: `can_manage_assessment(assessment_id)` only (assessment author or platform admin) — students/parents cannot read AI drafts. TRUNCATE/REFERENCES/TRIGGER revoked from `authenticated` (UAT default ACL grants them; TRUNCATE skips RLS) — also in `lockdown.uat.sql`.
- `assessment_assignments.ai_*` columns are kept but cleared and no longer written. `legacyBackend.gradeSubmissionWithAI` (wrote them, unused) deleted.
- Trigger `trg_guard_assessment_assignment_marks`: non-staff callers who don't manage the assessment cannot change marks/feedback/release/plagiarism/ai columns; parents cannot update assignments; the student cannot change submission text/url after the teacher approved or released. Service role and staff unaffected.
- Edge function `student-answer-upload` (actions list/upload/remove/submit): student device session (`requireStudentSession`), assignment must belong to the student and be descriptive, locked after approval/release or past due date, ≤ 10 pages, 40 uploads/hour/student.
- Still student-readable: `plagiarism_score/plagiarism_matches` on the assignment (not changed).
- Migration: `supabase/migrations/20261118120000_answer_sheet_review_release.sql`; DB-Scripts `EduSpeak Postgres Migration/20261116T…__pilvidya_answer_paper_review_release.sql` (UAT applied, PROD pending).

## Checks
- `node ~/pilvidya-checks/answer-paper/student.cjs <assignmentId> page1.jpg page2.jpg` then `node ~/pilvidya-checks/answer-paper/teacher.cjs <assignmentId>` (principal@pilvidya.in authors the QA assessment). 2026-11-16 run: 2 pages read (OCR 0.99/1.0), AI draft 8/10 with Q1 4/5, Q2 4/5, teacher saw both scans, edited to 9/10 and released, student saw 9/10 + feedback, no page/API errors. QA data deleted afterwards.
- Regression tests: `frontend/src/test/answerPaperReview.regression.test.ts`.

## Gotcha found during this deploy
- Demo students 9820000010/11/12 (seeded 2026-11-15 by SQL) could not log in in the browser: their `auth.users` token columns were NULL → GoTrue "Database error checking email" → "Student authentication service requires an update". Fixed on UAT (set to '') and in the seed. Any SQL-created auth user must set `confirmation_token, recovery_token, email_change_token_new, email_change, email_change_token_current, phone_change, phone_change_token, reauthentication_token` to ''.
