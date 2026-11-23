# AIVidya handwritten answer papers

AIVidya UAT release on 23 November 2026. The application runs commit `1bc2fece` on the `feat/chat-simulations` branch. The UAT hostname is `pilvidya.uat.pluginlive.com`.

## Student and teacher journeys

1. **Student → Practise → Written papers** (`/student/written-papers`) lists assigned tests that accept written answers, including mixed tests and completed work. Open a paper to see its board, class, subject and topic. The student can photograph pages or choose images or a scanner PDF. The browser renders PDF pages in order. PDFs have a 20 MB input limit. A student assignment accepts up to ten pages and each compressed scan may be up to 8 MB.
2. The handwriting reader transcribes each uploaded page after checking AI processing consent. A printed sheet must match the selected test and student. Each saved page appears as it is processed. A student must retake or explicitly remove every unclear page before submitting. **Submit paper** joins the remaining pages in order, completes the assignment, drafts marks and sends the author a notification linking to the review screen. The typed-answer option remains available while the assignment is editable.
3. **Teacher → Assess & improve → Scan answer sheets** (`/teacher/written-papers/scan`) lists the teacher’s descriptive tests. For automatic identification, print the personalised QR sheets and scan using a desktop file picker or a phone handoff. For a plain paper, select the test and an assigned student before uploading. Additional pages append to that assignment. Each successful teacher scan requests a fresh draft of the combined answers.
4. **Teacher → Assess & improve → Review written papers** (`/teacher/written-papers/review`) shows the page images, transcription, per-question marks and confidence. For question-based assessments, the grader checks every question against the configured marks and model answer. A teacher can correct the score and feedback, approve, and release. **Approve confident** uses both handwriting and AI confidence thresholds of 0.8. **Release approved** publishes the selected approved results. The older School Operations intake and review links still work.
5. A student sees **Awaiting teacher review** until release. Release makes the teacher’s score and feedback visible on that student’s assignment and notifies verified parents. The result includes the question breakdown when its scores add up to the final mark.

## Access settings

| Action | Menu key | Scope |
| --- | --- | --- |
| Open written papers and upload | `student.written-papers` | Signed-in student with an assigned descriptive test |
| Print, pair a phone and scan papers | `teacher.paper-intake` | Eligible teaching staff for their own assessments |
| View AI drafts, approve and release | `teacher.paper-review` | Eligible teaching staff for their own assessments |

Platform administrators manage the plan matrix and individual schools in **Admin → Billing → Plan Menus**. School leaders use **School Admin → Menu access → Students / Teachers & staff**. The three switches are independent. On first installation they inherit the existing assessment plan setting and school opt-outs. Existing principal exemptions for school-level menu switches still apply.

## Data and enforcement

- `my_written_paper_access()` supplies the staff sidebar and deep-link checks. Institute staff need an active academic membership and the author’s teacher profile. Older teaching accounts can predate institute memberships. Platform administrators retain their assessment privileges.
- `student-answer-upload` checks the student session, menu, ownership, assignment type, deadline and review status. Approved work is locked. The intake and phone endpoints check scan rights on the assessment. Teacher-initiated AI grading, mark updates, approval and release check review rights.
- `assessment_grade_reviews` stores drafts and reviewed marks by assignment. Row-level policies protect the review and original scans. Released results are copied into `assessment_assignments`; student-facing reads show the final score, feedback and release time. Original page scans are served by signed URLs.
- The review queue tracks pending, AI draft, approved and released work. **Check first** prioritises AI or handwriting confidence below 0.6. A teacher can approve and release in one action, or correct and release an amended mark.
- The private review table holds the AI fields. The earlier `assessment_assignments.ai_*` columns are unused. The existing UAT lockdown revokes `TRUNCATE`, `REFERENCES` and `TRIGGER` on the review table from the authenticated role.
- The application migration is `supabase/migrations/20261123145729_written_paper_access.sql`. The corresponding DB Scripts file is `EduSpeak Postgres Migration/20261123T145729Z__pilvidya_written_paper_access.sql`.
- The PDF reader loads a bundled `paper-pdf-worker-*.js` module. The UAT static server serves this file as JavaScript, and the build check verifies that the worker is present.
- If the student loses the response while a scan is saved, the client looks up that page by its upload ID. On a lost submit response, it verifies that the assignment has a new completion time and the same readable pages. These read-only checks preserve the original upload and grading attempt.

## Checks

- On 23 November 2026, 67 targeted tests passed. A mobile-browser student submitted a CBSE Class 9 Mathematics paper on Statistics. The teacher uploaded a second scan, inspected the two originals and per-question marks (3 and 2 available), approved 5/5, and released it. The student saw the score and feedback after release. A second assigned student kept their own pending result.
- A separate two-page scanner PDF reached one draft when the test browser deliberately dropped a saved-upload response and a submitted-paper response. The same upload ID and pages confirmed receipt. A previously unreadable page required a retake or explicit removal.
- The UAT access checks covered school and plan switches, authorised authors, other teachers, students, inactive staff and operations-only memberships. The admin plan matrix showed the three controls in Trial, Basic, Advanced and Enterprise.
- The teacher’s phone handoff matched the printed QR to the correct student and test. A principal verified the three school controls. Another teacher’s review selector excluded both test papers. Each student submission produced one teacher notification. The two temporary assessments, related records and five scan objects were removed after verification.

- `node ~/pilvidya-checks/answer-paper/student.cjs <assignmentId> page1.jpg page2.jpg` then `node ~/pilvidya-checks/answer-paper/teacher.cjs <assignmentId>` (principal@pilvidya.in authors the QA assessment). 2026-11-16 run: 2 pages read (OCR 0.99/1.0), AI draft 8/10 with Q1 4/5, Q2 4/5, teacher saw both scans, edited to 9/10 and released, student saw 9/10 + feedback, no page/API errors. QA data deleted afterwards.
- Regression tests: `frontend/src/test/answerPaperReview.regression.test.ts`.

## Gotcha found during this deploy
- Demo students 9820000010/11/12 (seeded 2026-11-15 by SQL) could not log in in the browser: their `auth.users` token columns were NULL → GoTrue "Database error checking email" → "Student authentication service requires an update". Fixed on UAT (set to '') and in the seed. Any SQL-created auth user must set `confirmation_token, recovery_token, email_change_token_new, email_change, email_change_token_current, phone_change, phone_change_token, reauthentication_token` to ''.
