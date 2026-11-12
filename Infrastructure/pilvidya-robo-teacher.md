# PilVidya (aividya) — Robo Teacher

A spoken, one-to-one class with "Robo Vidya" on a curriculum topic (Board → Class → Subject → Topic) or a
foreign-language theme. Live on UAT from 2026-11-12 (`feat/chat-simulations` `cfd12102`); no PROD yet.

## Student flow (`/student/robo-teacher`, menu Learn → Robo Teacher)
1. **Setup:** the student picks a subject and a topic from their own curriculum (`curriculum_topics`: global plus their school's), or a foreign language, a CEFR level (A1/A2/B1) and a theme. They pick the teaching language (14 Indian languages) and can set their subject target (`goal_target`).
2. **Class:** the stages are Warm-up → Teach → Worked example → Case study → Video → Check understanding → Assessment → Wrap-up.
   - The video is the topic's approved curriculum video (`curriculum-videos`, cached; loaded in the background, and the stage is skipped if there is none).
   - Teaching is grounded in curriculum material (`loadCurriculumMaterial`), uses Indian everyday contexts, asks one question per turn, and steers off-topic requests back to the lesson.
3. **Voice:**
   - The teacher speaks through `ai-coach-tts` (ElevenLabs/Gemini, Indian voices).
   - In foreign-language classes, phrases inside «» are spoken with the browser's voice for that language.
   - The student speaks through the browser recogniser (Chrome/Edge, with locale per language) or types.
   - There is no server speech-to-text yet: aividya has no Deepgram key (Banking's `stt-stream` relay is the upgrade path).
4. **Assessment:** 5 multiple-choice questions written by `pl/robo-quiz` from what was taught (`prepare_quiz`, about 20 s, in its own call). Answers stay on the server until submission.
5. **Debrief:**
   - Mastery = 70% assessment + 30% in-class answers.
   - The subject average (last 5 classes) is compared with the target, giving a nudge: on track, closing or behind.
   - The LLM writes a summary, next steps and encouragement in the class language.
   - Writes `student_curriculum_progress` (`completed` at ≥ 60%, otherwise `needs_revision`; `metadata.source = robo_teacher`), so dashboards and Student 360 see it, and credits lesson XP via `daily_quests`.

## Server
- **Edge function `robo-teacher`:** actions `start`, `turn`, `prepare_quiz`, `quiz_submit`, `get`, `history`, `end`.
  - Every call needs the student's session (`student_profile_id` + `session_token`).
  - The topic must belong to the student's board, class and school.
  - Foreign-language themes come from a fixed catalogue.
  - A message is at most 600 characters; a class is at most 40 turns.
- **Engine `_shared/robo/teacher.ts` (unit tests in `teacher.test.ts`):**
  - stages and the maximum turns per stage (the server moves on by itself; the model can only advance one stage);
  - prompts and strict JSON schemas;
  - quiz validation and scoring, mastery, and target nudges.
- **LLM:** central LiteLLM only, through key alias `aividya-app`.
  - `pl/robo-teacher`: gemini-3-flash-preview → gpt-5.4-mini, 20 s.
  - `pl/robo-quiz`: gemini-3.8-flash medium → gpt-6-luna low, 90 s.
  - Both were registered with `apply_policy.py` on 2026-11-12, and the forced fallback was verified for both.
- **Tables (migration `20261117120000_robo_teacher.sql`; DB-Scripts `c2e8384`):**
  - `robo_sessions` and `robo_events`: service role only (they hold quiz answers).
  - `robo_class_summaries` view (no quiz): readable by the student, their teachers, principal and parents (`can_access_student`) and admins.
- **Targets and XP (migration `20261117110000_student_targets_daily_quests.sql`; DB-Scripts `b32d661`):**
  - `goal_target`: one row per student and subject; the student writes it, staff and parents read it.
  - `daily_quests`: one per lesson per day; a trigger forces 10 XP and credits `student_gamification_profiles`.
- **Admin "View as":** a preview can open the page and history; starting, talking and submitting are refused (read-only gate).

## Verified on UAT 2026-11-12
- **API (`~/pilvidya-checks/chatsim-e2e/robo-e2e.mjs`), 18/18:**
  - every stage;
  - off-topic question steered back;
  - class turns at most about 4 s; the assessment prepared in about 19 s;
  - quiz sent without answers;
  - server scoring, with a debrief against the 85% target;
  - progress written; the principal sees the result;
  - another student, another class's topic and no session are all refused;
  - a French A1 class with «Bonjour».
- **Browser:** class opens in 2.4 s, avatar, stage tracker, mic button, typed turn, history.

## Foreign languages
French, German, Spanish, Japanese, Mandarin, Russian, Portuguese and Arabic, at A1–B1, each with 6 themes per level.
- **Medium:** the explanation is in the student's language; the phrases being learned are in the foreign language «inside guillemets» with their meaning, and the student repeats them.
- **Voice:** the student can tick "Answer in French" to switch the recogniser to that language.
- **Limits:**
  - There is no pronunciation scoring yet; `pronunciation-score` or Azure pronunciation assessment would be the next step.
  - The foreign-language curriculum (CEFR units) is a fixed catalogue, not admin-managed.
  - Plan gating: the Foreign Languages menu is plan-locked for Free Trial users, but the Robo Teacher foreign-language tab is not.

## Next steps (not built)
- Server speech-to-text (Deepgram live relay as in Banking) for Edge and Indic accuracy.
- Talking avatar, with lip movement driven by audio level.
- Teacher assigns Robo classes and sees class transcripts.
- Proactive nudges (dashboard and parent digest) from `robo_class_summaries` against `goal_target`.
- Spaced revision of topics marked `needs_revision`.
