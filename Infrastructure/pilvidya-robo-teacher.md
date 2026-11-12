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
  - `pl/robo-teacher`: gemini-2.5-flash (thinking off) → gemini-3-flash-preview → gpt-5.4-mini, 20 s (same model as Banking Robo Play, from 2026-11-12).
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
  - Pronunciation is a word-match proxy (see below), not phoneme scoring.
  - The foreign-language curriculum (CEFR units) is a fixed catalogue, not admin-managed.
  - Plan gating: the Foreign Languages menu is plan-locked for Free Trial users, but the Robo Teacher foreign-language tab is not.

## Step 2 (UAT `4d78037f`, 2026-11-12)
- **Server speech-to-text (`robo-speech` edge function):**
  - `transcribe {audio_base64, mime, language}` → `{text}`; `pronounce {…, target_language, expected}` → `{heard, score, words}`.
  - Engine: ElevenLabs Scribe (`scribe_v1`, ISO 639-3 codes) with the existing `ELEVENLABS_PIL_API_KEY`. aividya has no Deepgram key, so no live relay.
  - Student session required; audio ≤ 2 MB (~30 s), mime allowlist; failures return 502 "Could not hear that clearly…".
  - Browser records with MediaRecorder and stops after 1.4 s of silence (25 s cap); falls back to the browser recogniser where recording is unsupported.
- **Talking avatar:** the mouth follows the TTS audio level (Web Audio analyser); the mic button shows a level ring.
- **Teacher assignments (migration `20261117130000_robo_teacher_assignments.sql`; DB-Scripts `cb3b13a`):**
  - `robo_assignments`: class/subject/topic copied from `curriculum_topics` by a guard trigger; whole class (`student_profile_ids` empty) or named students; `due_at`, `target_mastery`, note; withdraw = `cancelled_at`.
  - RLS: platform admin or the teacher's schools (`sim_teacher_schools()`); `assigned_by`/`school_id` frozen on update.
  - `robo_sessions.assignment_id`; `start` refuses an assignment that is not the student's or a different topic.
  - `robo_class_events` view: transcript lines, filtered by `can_access_student`.
  - Page `/teacher/robo-classes` (teacher menu "Robo Classes"): Assign, Assignments (reached/tried, Withdraw), Results (debrief, misconceptions, transcript).
- **Coach (`_shared/robo/coach.ts`, action `get_coach`):** assignments, revisions due, subject average (last 5) vs `goal_target`, last class.
  - Spaced revision: topics below max(60, target) come back after 1/3/7/14 days until mastered.
  - Shown on the Robo Teacher setup screen, the student dashboard (`RoboCoachCard`) and the parent Daily Digest (`learning_coach`, computed live).
- **Pronunciation (foreign languages):** "Practise saying it" chips for every «phrase» the teacher says; Hear (browser TTS) / Say (Scribe in the target language).
  - Score = expected words recognised, weighted by Scribe confidence; accents ignored; Japanese/Chinese compared by character.
  - Every foreign-language reply, including the greeting, carries at least one «phrase».
- **Verified:** `~/pilvidya-checks/chatsim-e2e/robo-next.mjs` 15/15 (cross-school assign refused, wrong-topic start refused, transcript ACL, Scribe English/Hindi exact, French pronunciation 97%); browser fake-mic turn answered in 9.5 s; teacher Results + transcript; parent digest section; fr/es/ja openings each carry a phrase.

## Plan gating
Robo Teacher and Robo Classes are Enterprise; see `Infrastructure/pilvidya-school-plans.md`.

## Next steps (not built)
- Live streaming STT (Deepgram relay) if a Deepgram key is added; phoneme-level pronunciation (Azure pronunciation assessment).
- Teacher notifications when an assignment is overdue; parent WhatsApp nudge from `learning_coach`.

## Foreign languages: 10 languages, A1–B2, 30 themes per level (UAT `a5003bf3`, 2026-11-12)
- Languages: French, German, Spanish, Japanese, Mandarin, Russian, Portuguese, Arabic, **Korean (ko-KR, Scribe kor)**, **Indonesian (id-ID, Scribe ind)**.
- Levels A1, A2, B1 and **B2**, 30 themes each (`FL_THEMES` in `_shared/robo/teacher.ts`; the page list `FL_LEVEL_THEMES` must match, enforced by `frontend/src/test/foreignLanguageThemes.test.ts`). The original 6 per level are kept first.
- Phrases inside «» are written in the language's own script (Hangul, kana/kanji, Cyrillic, Arabic…) with optional pronunciation in brackets after, so pronunciation practice matches Scribe's transcript. Before this, Korean/Japanese phrases came romanised and scored badly.
- Checked: `~/pilvidya-checks/chatsim-e2e/ko-id-e2e.mjs` 9/9 (Korean A1 + Indonesian B2 start, turn, pronunciation 100% / 99%, unknown theme refused).
- The Foreign Languages module page uses its own DB catalogue (`foreign_language_catalog`); Korean/Indonesian were not added there.

## Voice and speech-to-text (UAT `615ede84`, 2026-11-12) — same voices as the Banking LMS
- **Voice = Banking Robo Play.** Robo calls `ai-coach-tts` with `voiceProfile: "robo"` (optional `gender`, default female). The plan lives in `supabase/functions/_shared/banking-voice.ts` (copied from the banking repo `elevenlabs-tts` + `_shared/llm.ts`; change both apps together):
  - en, hi, ta, mr, ur, ne, sa → ElevenLabs **Kavya** `O0HDGZKCNpSHnOXD6aq6` (male: **Ranbir M** `2iAXJEMO2o0PqUHzvZwQ`) on `eleven_flash_v2_5`, stability 0.55 / style 0.15 / speed 0.95.
  - te, kn, ml, bn, gu, pa, or → Sarvam `bulbul:v3` speaker **priya** (male **rahul**; Odia code `od-IN`) first, then ElevenLabs `eleven_v3` Kavya.
  - as and anything else → ElevenLabs `eleven_v3` Kavya.
  - Backup: Gemini TTS **Kore** (male **Algenib**), then the browser voice (client).
  - Live timings (UAT): flash 0.3–1.2 s, Sarvam ~1.7 s, eleven_v3 ~3 s per clip.
- **AI Coach (`/ai-coach`) = Banking AI Coach:** `voiceProfile: "coach"` → ElevenLabs **Rachel** `21m00Tcm4TlvDq8ikWAM` on `eleven_multilingual_v2` for every language, Gemini Kore as backup. The per-language Voice Settings panel no longer changes the AI Coach voice.
- **Keys:** ElevenLabs and Gemini keys are the same as Banking's. `SARVAM_API_KEY` is a global row in `app_secrets` (copied from Banking's `llm_provider_configs` robo_voice row), editable in Admin → Provider API Keys.
- **Chat model:** `pl/robo-teacher` = gemini-2.5-flash (Banking Robo Play's model) → gemini-3-flash-preview → gpt-5.4-mini. Known gap: 2.5-flash sometimes exceeds the "≤4 sentences, <15 words" rule (voice-e2e reply-length check fails ~1 of 3 language samples per run).
- Before 615ede84: Gemini `gemini-2.5-flash-preview-tts` at a slow pace (`provider: "gemini", pace: "slow"`), Gemini voices Kore/Aoede/Leda; AI Coach used stock ElevenLabs voices per language (Sarah/Alice/Matilda/Lily/Laura).
- **Playback:** `speechChunks()` splits a reply into a short first sentence + groups ≤160 chars; all are synthesised in parallel and played in order (first audio ~3 s after the reply text arrives). Browser fallback voice rate 0.85.
- **Speech-to-text:** `robo-speech` → gateway task `pl/robo-stt` (gemini-2.5-flash, thinking off → gemini-3.8-flash low, 20 s, modality audio; input_audio wav/webm/ogg/mp4), Scribe as fallback; responses include `engine`. Pronunciation transcribes verbatim and is not told the target phrase.
- **Teacher wording:** ≤4 sentences under 15 words, plain Indian English, everyday spoken Indian languages in their own script (never romanised), units spoken out.
- **Timing (UAT):** after the student stops speaking ≈ STT 3 s + reply 2 s + first voiced sentence 3 s. Tests: `~/pilvidya-checks/chatsim-e2e/voice-e2e.mjs` (20/21 after 615ede84 — reply length), live voice routing `~/pilvidya-checks/chatsim-e2e/voicelive.mjs` (8/8).
