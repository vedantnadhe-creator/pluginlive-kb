# PilVidya (aividya) — State-language curriculum + four-journey QA fixes (UAT d28ddf6e, 2026-11-15)

Live on UAT since 2026-11-15 (`eduspeak-india` `feat/chat-simulations` `3d54f42f..d28ddf6e`). No aividya PROD.
Found by full end-to-end runs of all four journeys; re-runnable kits under `~/pilvidya-checks/`:
`student-9820065335/`, `teacher-jy1/`, `admin-prakash/`, `parent-9820065336/` (each: login helper, menu crawl, flows, cleanup).

## State language in the curriculum (per the state language acts)

- `state_regional_language(state)` maps every state/UT to its language (Tamil Nadu→tamil, Karnataka→kannada,
  Maharashtra→marathi, Kerala→malayalam, AP/Telangana→telugu, WB/Tripura→bengali, Gujarat→gujarati, Punjab→punjabi,
  Odisha→odia, Assam→assamese, J&K/Ladakh→urdu, Hindi belt→hindi; Goa + North-East unmapped — ask product).
- `ensure_school_regional_language(school)` writes school-scoped `curriculum_topics` rows (`is_state_language`),
  Classes 1–10 × cbse/icse/ib/state, stage-wise topics (prose, poetry, grammar, composition, comprehension, …) with
  2–3 sub-lessons each and the state textbook series as reference. Rebuilt by a trigger on `schools` insert / state
  change; skips a board+class where a global row for that language already exists (Hindi belt). 620 rows/school.
- Students read their own school's topics (`curriculum_topics_scoped_read` + `current_student_school_id()`).
- Frontend: Curriculum loads school rows and hides the generic "Regional Language" placeholder once a real state
  language is present; Robo Teacher / AI Coach list it and default "Teach me in" to that language; Robo topic
  dropdown dedupes by topic (school rows are per sub-lesson). Topic names are curriculum areas, not chapter titles.
- A school without `schools.state` gets no language until the state is set (7 UAT schools).

## Journey fixes in the same release

| Journey | Fix |
|---|---|
| Student | Fee totals treat part payments (paid part = Paid, balance = Pending/Overdue; `lib/feeTotals.ts`, Pending filter includes `partial`). Assignments whose assessment was deleted are hidden. Proctoring actually stores now: `useProctoring` writes the real columns and migration `20261130030000` adds student INSERT/UPDATE policies (before: zero rows ever) with identity-based reads (was display_name matching). |
| Teacher | Fees tab asks `can_collect_fees` before `fee_defaulters` (teachers no longer fire a 403 per visit). Teacher-Portal Assign/Results modals are labelled dialogs, Escape closes. |
| Admin | Upcoming / Conflicts / Free periods tabs show an **ActiveSchoolBar** naming + switching the active school (`ops_active_school` — same scope as School Operations). Free Period Finder lists only the active school's teachers (was: all schools). Previews (Student/Teacher/Parent Journey) open `/admin/view-as?as=…` instead of the admin's own empty role screens. |
| Parent | `parent-fees` selected the non-existent `parent_profiles.school_id` → every parent's Fees tab said "Unable to load fee data" (misreported as "Invalid or expired session"). Fixed + query errors now surface as `database_error`. Parent self-signup → suggested child → **Confirm** flow verified end to end with 9820065336 (kept as demo parent for Prakash Chinnadurai; pilot OTP 1234). |

Gotcha: `/parent` is the parent home — the header Back button is hidden there by design (same rule as /student, /teacher, /admin).
DB-Scripts: `EduSpeak Postgres Migration/…proctoring_student_writes.sql`, `…state_regional_language_curriculum.sql` (UAT applied, PROD pending).

## Third-language student and teacher journey — UAT verified 2026-11-28 (`9228f1ee`)

- The deployed Class 9 third-language flow is verified with a disposable CBSE school: principal programme setup and
  Gujarati choice; teacher chapter assignment; actual Student Entry mobile/password authentication; Gujarati lesson
  completion with a Tamil study guide; student evidence submission; teacher portal feedback; marks, independent
  moderation, and the parent progress report.
- Student device replacement is part of the release check. A second sign-in invalidates the first device session; the
  first device returns to Student Entry and, after re-authentication, resumes the original
  `/student/robo-teacher?course=r3` lesson rather than losing the third-language deep link.
- The browser-level UAT check is `~/pilvidya-checks/language-programmes-uat.j0QAPCqx/uat-language-smoke.py`. It
  confirms the deployed manifest version, uses normal student and teacher sign-in (not injected local storage), and
  removes its synthetic school, accounts, choices, evidence, marks, and report after every run.
- `frontend/src/lib/i18n/rtl.ts` now has one registry entry per language and font. The duplicate CJK and Indian-font
  keys that produced Vite warnings were removed; the production build is clean of those duplicate-key warnings.
