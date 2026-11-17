# aividya — AI content reuse (store once, reuse across students, unique per student)

LIVE on UAT since 2026-11-17 (eduspeak-india `feat/chat-simulations` 2edaccff). PROD: not deployed.

## Rule
Every reusable AI output is stored once. A student is served items they have **not** been given before; other students may
receive the same item. The LLM is called only for the shortfall, and its output is stored for the next student.
Measured on UAT: first student 5–23 s per request (LLM), second student 26–75 ms (stored).

## Storage
| Object | Purpose |
|---|---|
| `ai_content_pool` (feature, pool_key, fingerprint, payload jsonb, serve_count) | Reusable items. `pool_key` = normalised `board|class|subject|topic|language…`; `fingerprint` = SHA-256 of the item text (dedupe). |
| `ai_content_served` (student_profile_id, item_id, feature) | What each student has already been given (pool ids **and** `question_bank` ids). |
| `ai_pool_take(feature, pool_key, student, n)` | Atomically takes up to n unseen items (least-served first) and records them served. |
| `question_bank_take(subject, class, language, mode, board, source_ref, difficulty, question_type, school, student, n)` | Same for `question_bank`; also skips questions in `student_question_history`; only approved, not-rejected, school-null-or-own-school rows. |
All four are service-role only (revoked from anon/authenticated; also in UAT `lockdown.uat.sql`). DB-Scripts ce282f4.

## Code
`supabase/functions/_shared/content-pool.ts`: `poolStudent()` (needs `student_profile_id` + `session_token`, verified with
`student_verify_device_session`; otherwise the caller gets reused content without per-student tracking), `takeFromPool()`,
`addToPool()`, `servedTexts()` (tells the LLM what not to repeat). Frontend sends the session via `studentSessionFields()` (`lib/studentSession.ts`).

| Generator | Pool feature | Unique per student? |
|---|---|---|
| `generate-questions` (Practice, lesson quiz, FL quiz, Competitive Exams page) | `question_bank` (bank-first) | Yes — at the student's adaptive difficulty; a student only reuses questions banked at the same difficulty |
| `mock-test` generate | `mock-test.mcq/.descriptive/.video` | Yes |
| `topic-lesson` mode quiz | `topic-quiz` (standard/expanded lessons also seed it) | Yes |
| `aptitude-lab` | `aptitude-lab` | Yes |
| `english-lab` grammar / vocabulary / comprehension / email | `english-lab.<type>` | Yes (speaking chat is live, not pooled) |
| `foreign-language-content` (student packs incl. YouTube lookups) | `foreign-language-content` | Yes; teacher drafts (`seedContent`) and `forceRefresh` always generate |
| `flashcards-generate` | `flashcards` | Yes; now **requires** the student's device session (was writable for any id) |
| `generate-topics` | `generate-topics` | Shared outline (same for all) |
| `topic-lesson` standard / expanded | `topic_lesson_cache` (30 days) | Shared lesson |
| YouTube per topic (`curriculum-videos`, `topic-media-generate`) | `topic_media` (7-day TTL) | Shared |

Not pooled (personal output): grading, feedback, AI coach/tutor chat, reports, digests, wellbeing.

## Gotchas
- Lab prefetch (`lib/labPrefetch.ts`) also marks the prefetched items as served.
- Competitive numeric-answer requests use topic suffix ` numeric` so they never reuse an MCQ.
- Checks: `~/pilvidya-checks/content-pool/reuse-e2e.cjs` (A/B students, ONLY=fn), `frontend/src/test/aiContentReuse.regression.test.ts`.
