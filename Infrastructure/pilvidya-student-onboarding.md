# aividya — Student onboarding: bulk upload, school-issued logins, first sign-in (UAT, feat/chat-simulations 13a114c2)

Most students are created by their school, not by self-registration, so `/student-entry` opens on **Login**
("Use the mobile number and password your school gave you"); Register stays as "School has not given you a login yet?".

## Who uploads, where
| Role | Screen | School |
|---|---|---|
| Teacher, principal, school admin | Teacher portal → Bulk Upload Students (`/teacher#upload`); Add student dialog | always their own (`teacher_profiles` via `user_id`) |
| Platform / ops admin | Admin → Bulk Student Upload (`#bulk-students`), Admin → Bulk User Management → Students, Admin → School Setup (single) | must pick the school; upload disabled until chosen |

All use `components/shared/StudentBulkUploadPanel.tsx` → edge function `teacher-bulk-upload-students`.

## Template (CSV; Excel → Save as CSV)
`Student Name*, Mobile No*, Email ID*, Board*, Class*, Parent Mobile No, Parent Email ID, Residential Address`
- Mobile: 10-digit Indian (6–9 start); +91 / leading 0 stripped. Email valid (not unique: siblings may share).
- Board: CBSE, ICSE (ISC/ICSE/CISCE), IB, State (State Board/SSC/HSC/Matriculation). Class 1–12 ("9th", "Class 9").
- Parent mobile optional, must differ from the student's. Duplicate mobiles in the file are flagged.
- Rules live in `frontend/src/lib/studentBulkUpload.ts` and again in the function; bad rows are skipped with reasons.

## What the upload does
- Creates approved `student_profiles` (school, board, class, email, parent_mobile, parent_email, address) with a
  temporary password (8 chars, 4 letters + 4 digits, hash `sha256("pilvidya:v1:"+pw)`) and `must_change_password = true`.
- Returns per-row results (created / exists / invalid / failed) and **login slips** (CSV: school, name, class, mobile,
  temporary password) — shown once; not stored in clear anywhere.
- Mobiles already registered: reported as "already registered", left unchanged.
- Parent mobile: reuses or creates `parent_profiles` (display "Parent of <student>", email) and a verified
  `parent_student_links` row; the parent signs in at `/parent/login` with that mobile.

## First sign-in
`student-authenticate-profile` returns `profile.must_change_password`; the entry page shows **Set your own password**
(app strength rule), calls action `change_password` (verifies the temporary password, sets the new hash, clears the
flag, syncs the auth user password), then signs in again with the new password (the auth update ends the old session)
and continues to `/student`. The temporary password stops working.

## Fixed 2026-11-13
- Staff lookup used `teacher_profiles.id = login id`, so linked principals/school admins/teachers uploaded students with no school.
- Admin CSV view marked every row invalid and never sent a school; Bulk User Management inserted students directly.
- `student_complete_profile` was executable by `anon` (set any student's password by profile id) → student themself or platform admin only.

## Tests
`~/pilvidya-checks/student-bulk-upload-ui.cjs` (screens, stubbed function), `student-bulk-upload-live.cjs` (live: upload → temp login → own password → old fails → re-upload), `student-bulk-upload-cleanup.sh` (run on the UAT box).
