# Mix & Match candidate journey (v2)

## DEV entry point

Universal Mix & Match OTP invites resolve to:

`https://assessment.dev.pluginlive.com/candidate-assessment-journey/v2?inviteToken=<signed-ticket>`

After OTP verification, the browser stores a candidate-scoped `assessment:run` JWT in session storage. The JWT identifies the owner assignment; it is not replaced with a second token.

## Candidate APIs

`student-node` exposes private Mix & Match routes. Every part-level route verifies that the requested assignment has the same Mix Match group and candidate email as the owner assignment in the scoped JWT.

- `GET /students/mix-match/summary`
- `GET /students/mix-match/assessment/:assessmentAssignedId/questions`
- `POST /students/mix-match/assessment/:assessmentAssignedId/submit`
- `POST /students/mix-match/assessment/:assessmentAssignedId/save-response`
- `POST /students/mix-match/assessment/:assessmentAssignedId/proctoring/image`
- `POST /students/mix-match/assessment/:assessmentAssignedId/proctoring/events`
- `POST /students/mix-match/assessment/:assessmentAssignedId/upload-audio`
- `POST /students/mix-match/assessment/:assessmentAssignedId/upload-video`
- `POST /students/mix-match/ai-interview/:assessmentAssignedId/start`
- `POST /students/mix-match/ai-interview/turn`
- `POST /students/mix-match/ai-interview/complete`

The existing single-assessment APIs are unchanged. `assessment-react-v2` calls the routes through same-origin `/api/assessment/*` BFF handlers.

## Implemented assessment runners

As of 2026-08-17, the v2 combined runner serves live questions for every assessment type. No backend change was needed for the last four: the Mix & Match part routes delegate to the same generic question and submit handlers the single-assessment flow uses, which already branch per type.

- Communication: live assigned questions/sections, signed listening audio, audio/video recording uploads, v1-compatible final response payload, and real submission.
- AI Interview: real session start, generated question turns, browser speech transcript submission, server completion, and camera/microphone checks.
- Aptitude: `questionsBySection`, an object keyed by lower-cased section name, one MCQ subsection each.
- Behaviour: `behaviors[]`, one subsection per behaviour.
- Custom: `sections[]`, with question and option artwork rendered from the signed `question_image_url` / `option_image_url` the API resolves.
- Role Based: `sections[]` mapped onto the surface each needs — MCQ Question to single-select, Subjective Question to free text, Video Response to the recording surface, Coding Question to the code editor. Taken section by section, as in v1.

## How each type gets its questions at assign time

The runner can only serve what assignment created, and each type sources its questions differently. The Mix & Match wizard (`admin-react-v2`, `POST /api/assessments/mix-match`) must therefore send a different payload per part; `assignMixMatchAssessment` runs each one through the normal single-assessment dispatcher.

| Type | Where questions come from | What the assign payload must carry |
| --- | --- | --- |
| Communication | a pre-generated set, picked by CEFR level + domain + accent | `cefrLevel`, `accent`, `responseLanguage`, `enabledSections` |
| Behaviour | a pre-made active set for the stream's domain | `assessmentDomain` (Engineering / Management) |
| Aptitude | composed at assign time from sub-topics | `aptitudeSubtopics` — **sub-topic IDs, at least 10** |
| Role Based | generated at assign time from the role | `roleName`, `skills`, `seniority`, `jobDescription`, `industry_domain`, `questionConfig` |
| AI Interview | none stored — asked live, turn by turn | `interviewConfig` |
| Custom | admin-authored sections, questions uploaded ahead of time | `sectionConfigurations` with **persisted** `section_id`s |

### enabledSections is two different vocabularies

This is what served candidates an empty Communication paper. The wizard picks the four **skills** — Reading / Listening / Speaking / Writing — but student-node filters the assigned set by each question's **question section**: `Paragraph Reading`, `Audio Question`, `Video Response`, `Question Based Response`, `Email Writing`, `Dictation`, `Sentence Completion`, `Sentence Build`. Storing skill names on the assignment map matches nothing, so every question is filtered out and the API returns `communications: []`.

Skills expand as follows (`src/lib/assessments/communicationSections.ts`, mirroring v1's `SECTION_GROUP_MAP`):

- Reading → Paragraph Reading
- Listening → Audio Question
- Speaking → Video Response
- Writing → Question Based Response, Email Writing, Dictation, Sentence Completion, Sentence Build

**All four selected must store `[]`**, not the expansion: an empty list means "no filter", so any section the map does not enumerate is still served. Existing DEV maps holding skill names were cleared to `[]`.

### Known gaps

- **Custom Assessment cannot be floated from v2 yet.** It needs `sectionConfigurations` pointing at sections already persisted with their questions, and the wizard still holds both client-side under generated ids with no endpoint to save them. The BFF now refuses it with that reason — previously it sent the draft shape, admin-node threw `No valid section configurations provided`, and the **whole group** failed, taking every other type with it.
- **Aptitude sub-topics are all-or-nothing per topic.** Production opens a sub-topic modal per topic card; v2 has no such modal, so choosing a topic sends every selectable sub-topic under it. Critical Reasoning has only 7, so selecting it alone is refused by the BFF for falling under the 10 minimum.

### Communication sections with missing media

Listening audio and question images live in Oracle object storage and are presigned per request. When the object is gone the API **still returns the section**: `getAudioURL` throws `NotFound` and the error is swallowed to `audioUrl: null`, while `generatePreSignedURLImage` signs without checking existence at all, so it returns a URL that 404s on fetch. Candidates got a listening question with no audio, a dictation with nothing to transcribe, and an image question with no image.

The runner now drops a section whose required media the API did not resolve — Audio Question without `audioUrl`, Dictation missing audio on any sentence, Question Based Response without `imageUrl` — and an image that fails to load renders an explanatory panel instead of a broken tile. Sections needing no media are never dropped. If every section drops, the part fails with "No Communication questions are available for this assignment."

Sets generated around 2026-03-31 on DEV have DB rows pointing at audio/image objects that are no longer in the bucket; sets from 2026-06 presign fine. A set that looks fine in the admin UI can therefore still serve a half-empty paper — check the objects, not just the question count.

### Sub-question text is not always the question

Two sections carry the *answer* in their sub-question text, so it must never be used as the prompt:

- **Dictation** — `sentence` is the sentence to transcribe. Printing it as the question handed the candidate the answer.
- **Sentence Completion** — `sentence` is the fill-in-the-blank surface, so using it as the question rendered the same line twice.

Both use a fixed instruction from `SECTION_PROMPTS` instead (`src/lib/examShapes.ts`).

### Video Response is filmed

Video Response maps to `communicationMode: "speaking"`, which captures camera **and** microphone and uploads under `kind=video`. The runner shows a live camera preview while filming and asks for camera permission by name — without the preview it was indistinguishable from an audio answer.

### The AI Interview speaks in ElevenLabs

The interviewer's questions are spoken by the ElevenLabs voice the admin chose, **not** by the browser's `speechSynthesis` — that read every question in whatever voice the candidate's OS shipped.

The chain: the admin picks a voice in the wizard → its **ElevenLabs `voice_id`** is sent as `interviewConfig.voiceId` at assign → stored on `ai_interview_config.voice_id` → returned as `voiceId` by `POST /students/mix-match/ai-interview/:id/start` → the runner posts `{ text, voice }` to its own `/api/assessment/ai-interview/tts`, which proxies FastAPI `/ai-interview/tts` and streams back `audio/mpeg`.

The two curated voices (ElevenLabs Creator tier) are:

| Voice | `voice_id` |
| --- | --- |
| Payal (default) | `CpLFIATEbkaZdJr01erZ` |
| Anika | `RABOvaPec1ymXz02oDQi` |

Samples for the admin picker live at `…/pl-uat-public-docs/ai-interview/voice-samples/{payal,anika}.mp3`. Placeholder ids like `"payal"` must never be stored — the speech endpoint cannot resolve them.

`FASTAPI_URL` is a **server-side** var on `assessment-react-v2` (v1's `REACT_APP_FASTAPI_URL`), read at request time by the proxy route, so it is not baked into the bundle. The typing reveal is only a floor: audio decides when the candidate may answer, and if speech fails the response still opens rather than stalling.

### Full screen is a condition of sitting, not a button

The runner requests full screen as the attempt opens. Browsers only grant that during a user gesture, so when the automatic request is refused the guard dialog covers the exam until the candidate clicks — it now appears whenever full screen is inactive, not only after they leave it.

### Interview evaluation parameters come from the model

The wizard's "AI Suggestion based on Role" calls `POST /ai-interview/suggest-parameters` on admin-node (which forwards to the FastAPI engine), through the BFF route `/v2/api/assessments/ai-interview/suggest-parameters`. It answers `data.parameters[]` of `{id, name, description, weight, min_pass_rating}`; the wizard takes the first five names and weights, and only splits 100 evenly if the engine omits weights. Note the admin-node route is **not** auth-gated upstream, though the BFF still requires an admin session.

### Answers are saved per question, not only at submit

v1 writes every answer as the candidate gives it, via `POST /students/assessments/saveResponse` with `{ payload: { questionId, answer, assessment_assigned_id, timeTaken } }`. The Mix & Match runner does the same through `POST /students/mix-match/assessment/:id/save-response`, debounced and best-effort — the final submit still sends the whole attempt, so this is the recovery copy, not the record of truth. Without it a browser that dies mid-test loses everything.

The scoped route exists rather than reusing the student one because `saveResponse` trusts whatever `assessment_assigned_id` the body carries. That is safe for a logged-in student, who only holds their own token; an invite token is scoped to one group, so membership is checked before the answer is stored. Verified: a token for one candidate saving to another's assignment gets `403 Assessment is not part of this Mix & Match invite`.

Answer shape per type — the same values the submit sends, so the two cannot disagree:

| Type | `answer` |
| --- | --- |
| Communication, sub-question | `{ subQuestionId, selectedOption }` |
| Communication, single-response (Email Writing, Question Based Response) | the plain value |
| Aptitude, Behaviour | the option **text** |
| Role Based | option **id** (MCQ), trimmed text (subjective), `{code, language, test_results}` JSON (coding) |

Not sent through this path: **recordings** (the media upload already writes the row, with a storage key this endpoint has no field for), **Role Based video**, and **Custom Assessment** — `saveResponse` throws `Unsupported assessment type: custom_assessment`, which is why Custom stores only at submit.

### Two answer values that were unscoreable

Both were found in `assessment.student_answers` on DEV and are fixed in the shared value transform:

- **Sentence Build** stored the drag handles' ids (`"…-item-1 …-item-0"`) because the reorder answer keeps ids rather than words. v1 saves the arranged content, which is what the scorer compares against.
- **Recordings** stored `{"durationSec":3}` as the answer text, overwriting the row the upload had already written with the real storage key.

### Proctoring

Report-only, as in v1: nothing warns, interrupts or auto-submits, and the whole runner is inert unless the invite carried `allowProctoring`. Two streams, at v1's cadences:

- **Snapshots** — a hidden camera sampled every **13s**, uploaded as multipart to `POST /students/mix-match/assessment/:id/proctoring/image`. Lands in `assessment.proctoring_snapshots` (`snapshot_key`, joined to `proctoring_logs`).
- **Events** — batched and flushed every **30s**, plus on submit and teardown (`keepalive`, so a closing page does not drop the last batch), to `POST /students/mix-match/assessment/:id/proctoring/events`. Lands in `assessment.proctoring_events`.

Snapshots follow whichever part is open when they fire. The event envelope must match what the report scores: `{ type, source, startMs, endMs, durationMs, severity, confidence, evidenceObjectKey, meta }`, with `startMs` relative to the start of the sitting.

Only **`tab_hidden`** and **`fullscreen_exit`** are reported — the signals the screen genuinely observes. v1's gaze, head-turn and no-face events come from a MediaPipe FaceLandmarker collector loaded from CDN, which v2 does not run; emitting them without it would put unearned findings into a report a human acts on.

Both upstream endpoints (`/students/assessments/proctoring/{image,events}`) take the assignment **from the request body and never check ownership** — safe for a logged-in student, not for an invite token scoped to one group. The candidate routes verify membership first. The snapshot route cannot rewrite a streamed multipart body, so it passes the verified id out-of-band and `uploadImage` prefers `req.proctoringAssignmentId` over the form field. Verified on DEV: no auth `401`, another candidate's assignment `403`, own assignment `200` with rows written.

Note `studentId` is optional upstream and deliberately so — OTP-invite candidates have no portal student id, and requiring it used to 400 them and skip proctoring entirely.

### Submit payload per type

Each type is scored from a different shape, so the runner builds a different payload per part. These live in `assessment-react-v2/src/lib/examShapes.ts`, which imports only types so the transforms are unit-tested without a browser.

| Type | `response` shape | Answer identified by |
| --- | --- | --- |
| Aptitude, Behaviour | `{ [questionId]: answer }` | option **text** |
| Custom | `{ [questionId]: answer }` | option **id** |
| Role Based | `{ mcqQuestions, subjectiveQuestions, codingQuestions, videoResponses }` | option **id**; video by `objectKey` |
| Communication | one array per section (`paragraphReading`, …) | per-section |

Getting the option-id-versus-option-text distinction wrong scores a candidate zero without failing anything, so both directions are pinned by tests in `examShapes.test.ts`.

Coding answers submit `{ code, language, test_results: [] }`. The empty results are deliberate — the server re-runs the test cases itself and only trusts frontend results when they are supplied. The in-browser runner executes JavaScript only, so runnable languages are offered first and the rest are labelled "(no run)".

Role Based video clips are uploaded while recording; that upload already attaches the storage key to the attempt server-side, and the submit payload repeats it as a safety net exactly as v1 does.

Unanswered questions are omitted rather than sent blank: the server rejects an empty answer, and a missing row scores the same as an explicitly skipped one.

### Refresh and resume

The take-page loader is single-flight because fetching questions claims a single-shot assessment (`PENDING` to `INPROGRESS`). This prevents React remounts from issuing a second start request.

That claim happens for **every part in the group** the moment the combined test opens, so `INPROGRESS` is the normal state of a part the candidate has not reached yet. The start guard used to read that as "already running on another device", so one browser refresh answered `409 ALREADY_IN_PROGRESS` for every part at once and ended the sitting with no way back in.

`resolveAssessmentStartConflict` now takes an `isMixMatch` flag and treats an `INPROGRESS` Mix & Match part as a same-candidate resume. The flag is set only by `getMixMatchAssessmentQuestions`, after `assertMember` has verified the scoped invite JWT owns that assignment — a caller who merely knows an assignment id cannot set it. `COMPLETED` and `DROPOUT` are still refused, so a submitted or abandoned part cannot be reopened.

On the client, a restored attempt is re-seated against the test that actually loaded (`reconcileAttempt`). Questions are fetched again on every mount and a part can come back with different ones (Aptitude regenerates its set when the candidate's level has moved), so a persisted cursor could name a question that no longer exists — which rendered nothing at all and stranded the candidate on the loading skeleton. Answers are keyed by question id, so a refresh costs the candidate their place, not their work.

A combined final submission is blocked until AI Interview is complete. Every other part is submitted with one request each. The overall timer uses the same backend submission path as manual finish.

## DEV deployments

- `student-node` commits `e60c67b2`, `9f7dfca5`, `1f43c573`, `b6eeeb63`
- `assessment-react-v2` commits `4602376`, `c70bee7`, `d1822b4`, `b7c78b4`, `da1432a`, `518203e`, `936a10d`, `6fafe50`, `8b0d903`, `2b5c9b3`, `19fe1e4`
- `admin-react-v2` commits `741a9b4`, `c17e420`
