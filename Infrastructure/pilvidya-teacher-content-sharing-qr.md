# PilVidya (aividya) — Teacher content privacy & sharing, QR upload from phone, QR answer sheets, live polls

Live on UAT since 2026-11-14 (`eduspeak-india` `feat/chat-simulations` 850a3fa9). No PROD.

## Who can see a teacher upload (`teacher_content` + file in `pilvidya/teacher-content/<teacher_profile_id>/…`)

| Who | Access |
|---|---|
| Owner teacher | read / edit / delete |
| Colleague, same school | read only if shared with them (`teacher_content_shares`) or with the whole school (`shared_with_school`) |
| Principal / HOD of the same school | read + moderate all of the school's uploads (`can_observe_school`) |
| Student | approved + published uploads of their own school (`current_student_school_id()`) |
| Anyone signed in | approved + published platform content (`school_id IS NULL`) |
| Platform admin | everything |

- New uploads are **private**. A BEFORE INSERT trigger pins non-admin uploads to the uploader's school.
- Storage: `teacher_content storage read` checks the row through RLS. The catch-all `Staff full access to app buckets` **excludes `teacher-content/`**; own-folder upload/delete for any staff role. `security_assessment_submission_read` covers `assessment-submissions/` only (before: any staff read the whole bucket).
- AI grounding (`_shared/curriculum-material.ts`, used by robo-teacher and ai-coach-generate) only uses the caller's school + platform uploads.
- UI: Lesson Content → Upload: **Share** button per item (colleagues or whole school) + Private / Shared with N / School badges; **Shared with me** tab; principal **School Admin → Teacher content** (all school uploads, filters, open).

## Upload from phone (QR)

- Desktop "Upload from phone (QR)" → `qr-upload` `create` → one-time token (32 random bytes; only SHA-256 stored in `upload_handoffs`), **10 min**, one teacher, max 20 files (120 for answer sheets).
- Phone opens `/m/upload/<token>` (no login). Photos can be combined into one PDF (jspdf). Upload = multipart to `qr-upload`; types PDF/JPEG/PNG/WebP/MP4/DOCX/PPTX, ≤ 20 MB. Lands private + `pending_review`.
- Desktop polls `upload_handoffs.files_received` every 3 s (owner-only column grant; `token_hash` not readable). Done closes the handoff.

## QR answer sheets (Teacher → Operations → Alt intake → QR answer sheets)

- Print: one A4 page per assigned student; QR text `PVSHEET:1:<assessment_id>:<student_profile_id>` top-right.
- Scan: phone (handoff `answer_sheets`, QR read on the phone with jsQR) or bulk upload on desktop (QR read in the browser) → `_shared/answer-sheets.ts`: assessment must be in the caller's school, student must be assigned → page stored at `assessment-submissions/<assessment>/<student>/…` → vision transcription (llm-resolver task `alt-submission-ingest`) → `assessment_alt_submissions` row + `assessment_assignments.submission_text/submission_url`, status completed. Pages for the same student are joined, not overwritten → `descriptive-auto-grade` (internal call) writes an AI **draft** to the teacher-only `assessment_grade_reviews`; the teacher approves and releases marks — see `pilvidya-answer-paper-review.md` (2026-11-16).
- `alt-submission-ingest` and `descriptive-auto-grade` now require a staff session and same-school scope (both were callable with only the anon key).
- Live check 2026-11-14: typed sample sheet read in ~8–10 s, graded 78–88/100.

## Live polls — see `pilvidya-teacher-classroom-tools.md` (Teach Mode). Read actions are named `list_classes` / `my_polls` / `list_open` so admin View-as allows them; create/close/answer are blocked in View-as.

## Checks
- `~/pilvidya-checks/content-sharing/rls-matrix.sql` — 17-case access matrix (rolled back).
- `~/pilvidya-checks/content-sharing/qr-polls-db.sql` — handoff slots / poll constraints (rolled back).
- `ANON=<key> node ~/pilvidya-checks/content-sharing/live-e2e.cjs` — 47 live checks on UAT incl. phone page, answer-sheet OCR+grading, student poll in the browser; deletes its data.
- Gotcha: after applying migrations run `NOTIFY pgrst, 'reload schema';` or new tables return 404 through the API.

## Known open
- `is_staff` still grants every staff member of every school read on `assessment-submissions/` and full access to all other pilvidya folders except `teacher-content/` (pre-existing; needs school-scoped paths).
- Fees tab still issues a 403 RPC for teachers (by design, console noise).
