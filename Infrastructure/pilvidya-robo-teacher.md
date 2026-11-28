# PilVidya (aividya) — Robo Teacher

Robo Vidya teaches curriculum topics and foreign-language themes in one-to-one spoken classes. The Indian language programmes and the Maharashtra and Karnataka pilots are live on UAT at commit `51203fc4`. [UAT](https://pilvidya.uat.pluginlive.com) · [GitHub release](https://github.com/PluginLive-Technologies/eduspeak-india/commit/51203fc40a34b8055628d2dd09e8f4d2154da2c8)

## Indian language programmes on UAT

Schools can approve language offerings, record teacher qualifications and enrol each learner in their selected pathway. The programme catalogue includes 22 scheduled Indian languages. It supports CBSE R3 by class and academic year, CISCE third- and second-language pathways, school-specific state syllabuses, IB MYP and Diploma placement, senior electives and classical study. A principal records the reference from their school’s OASIS declaration for CBSE R3. The school register retains learner choices and transfers and can be downloaded as CSV.

| Role | Where to go | What happens |
|---|---|---|
| Principal | School Admin → School setup → School language programmes | Approve an offering and record each learner’s R1, R2 and R3 where applicable. Review or return CBSE Class 9 assessments and publish approved marks. |
| Teacher | Robo Classes → Indian languages and electives | Approve a source, chapter and activity, then assign it to the class. Review learner work, publish feedback and send Class 9 marks for moderation. |
| Student | Learn → Robo Teacher → Indian languages and electives | Open a chapter, choose a study-guide language, play teacher audio where provided and submit written work or a reference to classroom work. My Progress shows reviewed work and published marks. |
| Parent | This Week and Report Cards | A verified guardian sees signed feedback and the published Class 9 report. Parent Settings controls AI learning consent for conversation practice. |

The NCERT catalogue links 44 readers for Classes 6 and 9, representing 528 chapter references. Teachers can assign those chapters or use a verified school textbook or resource. The lesson form offers editable activity templates for listening, speaking, reading and writing. Learners can choose study guidance in 14 Indian languages. Schools approve the chapter, learner instructions and any model recording before publishing. [NCERT language resources](https://ncert.nic.in/R3_learning_Resources.php)

The CBSE Class 9 rubric totals 100 marks. Teachers record eight distinct listening and speaking observations worth 5 marks each, creative writing worth 15, reading worth 20, resource-based writing worth 10, and project work with viva worth 15. The principal reviews the evidence before publishing and can export a component-level CSV. [CBSE assessment framework](https://cbseacademic.nic.in/web_material/Circulars/2026/46_Circular_2026.pdf)

## Maharashtra and Karnataka language pilots on UAT

The 2026–27 pilot has two private state-board demo schools, `UAT-LANG-MH-2627` for Marathi and `UAT-LANG-KA-2627` for Kannada. Each school has a Class 6, 10, 11 and 12 pilot section. A learner enrolled in one of these sections can open an original reading or writing activity, follow its official source, choose a study guide and submit work to the pilot teacher. [UAT language programmes](https://pilvidya.uat.pluginlive.com/student/robo-teacher?course=r3)

| Class | Maharashtra Marathi | Karnataka Kannada |
|---|---|---|
| 6 | Sequence the events in a short passage. | Retell a short passage using two details. |
| 10 | SSC second-language reading with *Aksharbharati* as the reference. | SSLC second-language reading with the Karnataka Textbook Society's Kannada reader as the reference. |
| 11 | Write a notice for a college book exchange. | Write an I PUC report distinguishing an observed result from a missing observation. |
| 12 | Use two sources in an HSC letter to the editor. | Use two sources in an II PUC letter to the editor. |

The four invited learners at the CBSE demo school use their existing logins. Each has two individually assigned reading quizzes in **Assessments**, one per language. Classes 11 and 12 also have one written paper per language. Their existing class teachers can review the assigned work. Their CBSE classes and formal language choices are preserved. [UAT assessments](https://pilvidya.uat.pluginlive.com/student/assessments) · [UAT written papers](https://pilvidya.uat.pluginlive.com/student/written-papers)

On 28 November 2026 all eight state-school demo logins opened the lesson, guide and reading questions in Chromium. In each state, the Class 6 demo learner completed the reading quiz and the Class 10 demo learner submitted language work. Both pilot teachers could retrieve the senior writing samples. Access-policy checks verified the four invited accounts could read their own assignments and questions. [Balbharati textbooks](https://ebooks.ebalbharati.in/) · [Karnataka pre-university papers](https://dpue-pragathi.karnataka.gov.in/MQP/)

Release `51203fc4` adds the eight original lessons, 16 reading quiz questions and four senior writing prompts to the application repository. After the UAT build, all eight demo classes passed the learner checks, both pilot teachers could read submitted Class 10 work, and the four invited accounts could still access their 12 assignments. [Versioned pilot materials](https://github.com/PluginLive-Technologies/eduspeak-india/blob/51203fc40a34b8055628d2dd09e8f4d2154da2c8/supabase/seeds/mh_ka_language_pilot_2026_27.json)

## Class 6 conversation practice

Current CBSE Class 6 sections can use six classroom activities in each of 182 target and support language directions across 14 Indian languages. The scenarios cover introductions, the canteen, fruit stall, bus, library and playground. In School setup → R3 offerings, the principal picks the support language and practice roster. The roster follows formal R3 choices recorded for that section. Teachers review and assign a practice activity in Robo Classes. Teacher recordings are required for Kashmiri and Sanskrit practice.

The learner needs active AI learning consent from a verified guardian. Conversation practice saves the current step across reloads. The teacher can assess speaking when the server has transcribed the recording. A typed response is saved for review and the oral observation reads “Not observed”. Principal Brief handles the publication of formal conversation assessments to Report Cards.

UAT received the Class 6 language expansion and school language programme migrations on 28 November 2026. The deployment rebuilt the frontend on UAT and synced the edge functions. [DB-Scripts](https://github.com/PluginLive-Technologies/DB-Scripts/tree/4b38403/EduSpeak%20Postgres%20Migration)

The live Class 9 check enrolled a learner, assigned an NCERT chapter, displayed the Tamil guide and accepted Gujarati evidence in Chromium. The teacher recorded the marks, the principal moderated and published them, and the verified family received the report. The test also checked that an unverified child link was refused. The temporary school and accounts were removed.

The original Gujarati and Marathi pilot checks completed all six activities and 24 responses on UAT. They covered microphone transcription, typed and recorded evidence, a Gujarati paraphrase, withdrawn consent and school report-card approval. [Original pilot release](https://github.com/PluginLive-Technologies/eduspeak-india/commit/7f6ea2f8f4ac0b6e095ccbbbeb01b4f25f590740)

## Student flow (`/student/robo-teacher`, menu Learn → Robo Teacher)
1. **Setup:** the student picks a subject and a topic from their own curriculum (`curriculum_topics`: global plus their school's), or a foreign language, a CEFR level (A1/A2/B1) and a theme. They pick the teaching language (14 Indian languages) and can set their subject target (`goal_target`). Global CBSE 3-10 topics follow the official 2026-27 books, and languages are grouped apart in the picker: see [pilvidya-board-curriculum-sources.md](pilvidya-board-curriculum-sources.md).
2. **Class:** the stages are Warm-up → Teach → Worked example → Case study → Video → Check understanding → Assessment → Wrap-up.
   - The video is the topic's approved curriculum video (`curriculum-videos`, cached; loaded in the background, and the stage is skipped if there is none).
   - Teaching is grounded in curriculum material (`loadCurriculumMaterial`), uses Indian everyday contexts, asks one question per turn, and steers off-topic requests back to the lesson.
3. **Voice:**
   - The teacher speaks through `ai-coach-tts`, using a female Indian teacher voice: Sarvam Priya first for supported Indian languages, then ElevenLabs Kavya and Gemini Kore.
   - In foreign-language classes, phrases inside «» use the server's native-language voice plan. The device voice is a fallback when server speech fails.
   - The student records an answer for `robo-speech` or types; the browser recogniser is used where recording is unsupported. See the current speech-to-text routing below.
   - **Preparing voice…** means synthesis is pending; **Speaking…** appears only when playback starts. **Replay voice** repeats the last teacher reply without sending a teaching turn or advancing the class. Voice off cancels pending audio as well as playback; playback failures show a retry message.
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

## Turn output format (UAT `d96ab82c`, 2026-11-13)
- Each turn asks `pl/robo-teacher` for JSON `{reply, advance, answer_assessment, misconception}`. History teacher turns are plain text, so gemini-2.5-flash sometimes replied in prose; the gateway retry did the same and the class stopped with "The AI partner gave an unusable answer" (seen on a Class 6 Gravitation class after a long spoken answer; replay 4/5 valid).
- Fix: a final system message "Format: answer with the JSON object only — keys reply, advance, answer_assessment, misconception" (replay 10/10 valid), and `callSimTask(..., proseFallback)`: if the second answer is still prose (not starting with `{`, `[` or a fence, ≤ 1500 chars) it becomes `{reply: text, advance: false, answer_assessment: "none"}` — the class continues without advancing or scoring that turn. Log line `gateway_prose_fallback`. Malformed JSON is never masked; other sim tasks are unchanged.
- Check: `~/pilvidya-checks/chatsim-e2e/robo-prose-check.mjs` (live, 8 rambling answers; 2026-11-13: 8/8 turns ok, 9/9 calls valid first time).

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

## Voice and speech-to-text (UAT `baf76f5d` + `330dc346`, 2026-11-13) — native Indian teacher voice
- **One female teacher voice by default** for Robo Teacher (`voiceProfile: "robo"`), AI Coach, Virtual Tutor and lesson read-aloud (`voiceProfile: "coach"`, same plan). Explicit Gemini/OpenAI choices in voice settings are honoured by the coach, tutor and admin preview. Plan: `supabase/functions/_shared/teacher-voice.ts` (`teacherVoicePlan`):
  - en (Indian English), hi, bn, gu, kn, ml, mr, or (`od-IN`), pa, ta, te → **Sarvam `bulbul:v3` priya** → ElevenLabs Kavya (`eleven_flash_v2_5` for en/hi/ta/mr, `eleven_v3` otherwise) → Gemini Kore. The shared frontend request helper always requests female speech.
  - ur, ne, sa → ElevenLabs Kavya flash; as → ElevenLabs `eleven_v3`; then Gemini.
  - Foreign-language phrases (fr, de, es, ja, zh, ru, pt, ar, ko, id) → **Gemini** first with a native-pronunciation prompt, ElevenLabs `eleven_multilingual_v2` backup.
  - Normal pace (speed 1.0); no slow cue. ElevenLabs gets `previous_text`/`next_text` (not on eleven_v3).
  - Long text (AI Coach lessons): split into ≤1500-char sentence-aligned pieces, Sarvam in parallel, MP3 joined (≈5 min of audio in ~6 s).
- **Client (`frontend/src/lib/roboTeacher.ts`):** `speechParts()` — language classes voice the teaching-language text on the server and «phrases» in the target language. Pronunciation guides in `[ ]`, or `( )` right after a «phrase», are shown but never spoken. `speechChunks()` keeps the first sentence short (joins the next if <25 chars), then groups remaining sentences up to 600 characters; a single longer sentence remains intact and is split by the provider helper. Browser voice is used when server synthesis or decoding fails; blocked autoplay produces a Replay message.
- **Keys:** `SARVAM_API_KEY` global row in `app_secrets` (Admin → Provider API Keys); ElevenLabs/Gemini keys as before.
- **Gateway output:** `gemini-2.5-flash` (pl/robo-teacher) returns ~6–8% non-JSON/non-object answers; `_shared/sim/gateway.ts` `parseModelJson` unwraps fences / JSON-in-a-string / one-item arrays and `callSimTask` retries a schema-invalid answer once (logged `"retry":1`). Applies to every sim task.
- **Tests:** `~/pilvidya-checks/chatsim-e2e/voice-ui-teacher.cjs` (browser: en/hi/ta classes, Korean-in-Tamil, AI Coach — every clip from the server voice, no browser voice, no spoken pronunciation guide), `voice-e2e.mjs` (21/21, voiceProfile path, first audio ~0.4 s), `turnprobe.mjs` (empty-reply repro). Listening page: `pl-uat-public-docs/aividya-voice-staging-610c3c73/index.html`.
- History: 11-12 `8b4e91ed` Gemini slow voice → `615ede84` Banking voices (Kavya/Rachel) → 11-13 native Sarvam voice.
- **Playback:** chunks are synthesised in parallel and played in order. Default playback pace is 1.0; the caller can request a slower practice rate. Device fallback prefers a female voice matching the requested locale, including Indian English, but the installed device voices determine availability.
- **Speech-to-text:** `robo-speech` → gateway task `pl/robo-stt` (gemini-2.5-flash, thinking off → gemini-3.8-flash low, 20 s, modality audio; input_audio wav/webm/ogg/mp4), Scribe as fallback; responses include `engine`. Pronunciation transcribes verbatim and is not told the target phrase.
- **Teacher wording:** ≤4 sentences under 15 words, plain Indian English, everyday spoken Indian languages in their own script (never romanised), units spoken out.
- **Timing (UAT):** after the student stops speaking ≈ STT 3 s + reply 2 s + first voiced sentence 3 s. Tests: `~/pilvidya-checks/chatsim-e2e/voice-e2e.mjs` (20/21 after 615ede84 — reply length), live voice routing `~/pilvidya-checks/chatsim-e2e/voicelive.mjs` (8/8).

## Audible voice and recovery (UAT `ce17e640`, 2026-11-18)

- **Root causes:** `ai-coach-tts` validated the ElevenLabs account before trying primary Sarvam. That account request could hang until the edge worker's 300-second limit. The browser also attached media to a newly created, suspended AudioContext, which could mute otherwise valid audio while the UI claimed to be speaking.
- **Server fix:** ElevenLabs account validation runs only when that provider is needed and has a 2-second deadline. Provider fetches, including response-body reads, have a 10-second deadline within a 22-second request budget. Database/cache/secret requests are bounded to 2 seconds, and secret lookups run concurrently. Sarvam uses `language_code` and the requested `pace`; long sentences are split without losing text.
- **Client fix:** `invokeTutorSpeech` is shared by all frontend TTS callers, requests female speech, and applies 26-second speech / 5-second probe timeouts. Robo unlocks its AudioContext on Start/Send/Replay; the animation analyser attaches only to a running context. Playback errors are visible, and cancellation prevents late audio after muting or leaving. Lesson Listen, speaking practice and foreign-language samples also use the shared speech engine.
- **Natural delivery and language:** normal conversational pace, brief pauses, no repeated greetings or promised perfect scores. Language names and locales such as `Tamil` and `hi-IN` resolve to their actual voice. Admin preview uses a native-language sample. MP3/WAV headers are detected, corrupt cached clips are discarded, and blocked browser caching does not prevent playback.
- **Pre-deployment checks:** 53 focused tests, 9 browser checks, and real English/Hindi/Tamil Sarvam clips passed. Changed frontend files passed scoped TypeScript and lint checks. Whole-repository lint/typecheck still have pre-existing failures in untouched files; this is not a complete application regression sign-off.
- **UAT verification:** frontend manifest and running image `eduspeakreact:ce17e640`; all four changed server files match the checkout. Nine browser checks passed on the deployed frontend. The first Robo speech request reached the real UAT endpoint: HTTP 200, Sarvam, 56,842 bytes in 1.038 seconds; MP3 decoding succeeded (mean -16.1 dB, peak -0.6 dB). Browser media time advanced unmuted with a running AudioContext. Replay recovered after a simulated autoplay block without a teaching turn; mute prevented late playback. Tutor/admin preview and forced failure checks reused recorded clips; teaching turns were fixtures, so this verification did not create or complete a class.
- **Evidence:** `~/pilvidya-checks/voice-20261118/uat/{browser-results.json,live-speech.json,teacher-en.mp3,robo-playing.png,robo-blocked.png}`. Re-run with `BASE=https://pilvidya.uat.pluginlive.com LIVE_UAT=1 node ~/pilvidya-checks/voice-20261118/browser.cjs` (one short real speech request; other audio checks use fixtures).
- **Deployment:** pushed to GitHub and deployed through `~/auto_deploy.sh pilvidya feat/chat-simulations`, with the frontend rebuilt on UAT. No schema change. All 55 held functions remain excluded. Previous image `eduspeakreact:51c60207`; server backup `~/eduspeak-sb/functions.bak-20261118T161657Z`.


**2026-11-15 (d28ddf6e):** subject list now includes the school's state language (e.g. Tamil for a Tamil Nadu school) with "Teach me in" defaulting to it; topic dropdown dedupes sub-lesson rows. See `pilvidya-state-language-and-journey-fixes.md`.

## Robo Faculty visuals (2026-11-18, live on UAT `fa8238d3`)

- **A. Diagrams.**
  - The tutor's reply schema (`roboTurnSchema`) has a `diagram` field: `kind` none|flow|cycle|parts, a `title`, and 2-7 `items`. The tutor fills it only in the Teach, Example and Case study stages.
  - `cleanDiagram` stores it in `robo_events.visual`.
  - The page draws it with `components/robo/RoboDiagram.tsx` (HTML for flow and parts, a small SVG for cycles; no new dependency), so labels are exactly the tutor's words.
- **B. Topic image.**
  - The page calls robo-teacher action `visual` after a class starts, so starting never waits for an image. `_shared/robo/visuals.ts` holds the logic.
  - Images are pooled in `ai_content_pool` (feature `robo-topic-image`, key = `curriculum_topic_id`) and stored at `pilvidya/robo-images/<topic>/<sha256>.png`.
  - A student gets an image they have not seen (`ai_pool_take`, least-served first). When they have seen every pooled image, a new one is generated and added to the pool for others.
  - The image is saved on `robo_sessions.topic_image` and shown with a 6-hour signed link.
  - Signed links are rewritten from the internal `SUPABASE_URL` (`http://gateway:80`) to `SUPABASE_PUBLIC_URL` (UAT: `https://pilvidya.uat.pluginlive.com/sb`). Other features that sign storage links (for example `topic-media-catalogue`) likely need the same fix.
  - The prompt asks for the real concept with no text (titles taken literally gave a brick wall for "Cell: The Building Block of Life").
- **Provider order** comes from the Admin LLM config row `robo-faculty-images`: Higgsfield `higgsfield-ai/soul/v2/standard` (direct API, submit then poll `status_url`; key ID and secret in `app_secrets` as `HIGGSFIELD_API_KEY_ID` / `HIGGSFIELD_API_KEY_SECRET`, entered under Admin → Provider API keys), then Gemini through the LiteLLM task `pl/robo-topic-image` (`gemini-2.5-flash-image`, 90 s).
  - The direct Higgsfield call is the one exception to gateway-only routing, because LiteLLM has no Higgsfield provider. It is marked `ponytail` in the code.
  - **No Higgsfield key is configured yet**, so every image currently comes from the Gemini fallback.
- **Budget**: the gateway key `aividya-robo-images` (UAT `~/litellm/aividya_robo_images_vkey.txt`, functions env `ROBO_IMAGE_GATEWAY_KEY`) is limited to `pl/robo-topic-image`, $11.90 every 30 days. In the app, `ROBO_IMAGE_MONTHLY_BUDGET_INR` (default 1000) caps new images by the summed `cost_usd` of this month's pooled images (Higgsfield estimate endpoint, else $0.039 for Gemini).
- **Schema**: `robo_sessions.topic_image jsonb` and `robo_events.visual jsonb`, plus the llm_config seed row. Migration `20261204010000_robo_faculty_visuals.sql`; DB-Scripts `33d6044`.
- **UAT checks**:
  - `~/pilvidya-checks/robo-visuals/e2e.cjs`, two Class 9 students in School A on "Cell: The Building Block of Life": image shown; reuse without generating (pool unchanged); the same student never repeats (pool +1); a diagram was drawn in 3 of 4 runs.
  - `admin-config.cjs` for the Admin LLM config row and key fields; `cleanup.cjs <topic>` removes a topic's test images.

## Synchronized lesson RoboBoard (P0–P3, UAT `84b5b596`, 2026-11-23)

This is the Board mode on the ordinary student lesson page, not the separate conversational
`/student/robo-teacher` class. It is live on UAT only; PROD has not received this release.

- **Access and fallback:** `topic-lesson` accepts `include_board: true`, but sends a package only after checking the
  student's `student.robo-teacher` plan entitlement and the server-side `robo_teacher_enabled` feature flag. UAT has
  the flag enabled at 100%. A false flag, missing entitlement, missing package or malformed package returns the normal
  Read lesson without exposing board data. The rollout bucket for device-token student sessions is deterministic from
  their profile ID, so a student does not flicker between modes.
- **Lesson contract:** each part may carry `board[]` items (`id`, `type` = heading/bullet/equation/table/tally/highlight,
  `zone`, `content`, `animation`) and `visuals[]` items (`id`, `kind` = svg_spec/library/image, `spec`, `alt`,
  `actions`). Transcript narration contains `[[board:<id>]]` and `[[visual:<id>]]` cues. A teacher-provided Board
  artifact wins over the generated package; existing prose remains the transcript and is still available in Read mode.
- **Generation and safety:** after the canonical starter lesson, `pl/lesson-board` writes the Board package and
  `pl/lesson-visual-plan` writes the visual plan. Maths/science tally marks, pictographs, bar graphs, number lines and
  geometry are validated JSON specs rendered into SVG on the server. P0–P3 deliberately does not auto-generate arbitrary
  raster images; approved/library image references can still be displayed. Raw legacy tally tags such as
  `<s>||||</s>` are sanitised rather than rendered as markup.
- **Player:** the student page shows a Read | Board choice next to Listen and defaults to Board only when the server
  supplied a valid package. RoboBoard shows animated board cues, rendered visuals, a small Robo Teacher avatar and
  captions. Learn and Example use the Board/visual sequence; Key points is a recap board. The quiz shows checkpoints
  and offers the relevant re-explanation after two wrong answers. The sidebar's Robo Teacher link opens the current
  lesson in Board mode. Mobile stacks the board above the visual panel.
- **One clock:** `ai-coach-tts` can return word timestamps and persists a signed per-part timeline manifest. Play/pause,
  seek, 0.75x–1.5x speed and tapping a board cue drive the same audio/board/visual clock. If timestamp-capable speech is
  unavailable, the existing speech path provides an estimated timeline instead of breaking the lesson.
- **Verification:** 15 targeted component/unit tests, production build and Storybook build passed. The deployed Class 6
  *Data Handling and Presentation* learner flow passed in Board mode: the package was returned, raw tally markup was
  absent, timestamped TTS returned HTTP 200 and audio/board progress advanced without browser errors. The release image
  is `eduspeakreact:84b5b596` and public `/healthz` returned `ok`.
