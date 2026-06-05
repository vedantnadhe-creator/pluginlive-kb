# AI Interview Assessment

> AI Interview is a **real-time, voice-based, adaptive interview** assessment type. The candidate speaks; the AI interviewer (Gemini) listens via Deepgram, responds via ElevenLabs TTS, and adapts each next question based on what the candidate just said. The interview is anchored to the role + job description — the candidate's resume is *not* used to bias questions or scoring. Final scoring runs asynchronously via the existing score cron and produces a single Fit Score (0–100) + verdict.

---

## Overview

| Property | Value |
|---|---|
| **Assessment Type** | `AI_Interview` |
| **Domain** | `AI_Interview` (short form: `AI_INT`) |
| **Total Duration** | Configurable per assignment; default **20 minutes** (1200 s). Pulled from `ai_interview_config.interview_duration` and shown on the instructions screen via `GET /ai-interview/config-info/:assignmentId`. |
| **Question Cap** | `MAX_TOTAL_QUESTIONS = 8` total turns **including the warmup intro** (1 intro + up to 7 substantive). |
| **Per-parameter Cap** | `QUESTIONS_PER_PARAM = 2`. Orchestrator round-robins the lowest-count parameter first so every parameter gets at least one probe before any gets two. |
| **Question Generation** | Gemini **2.5-flash** (no thinking), prompt anchored to role + JD, resume explicitly ignored. |
| **Per-turn Signal Scoring** | Gemini **2.5-flash**, fire-and-forget after each answer. |
| **Final Scoring** | Gemini **3.5-flash** (gemini-2.5-pro available as fallback), run by the score cron behind a semaphore on the background thread-pool. |
| **STT** | Deepgram Nova-3 streaming over WebSocket. `language=hi` covers Hinglish (English script + Hindi words). |
| **TTS** | ElevenLabs Flash v2.5, voice ID `CpLFIATEbkaZdJr01erZ` (Payal — Indian-accented). |
| **Languages** | English, Hinglish, Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Gujarati, Marathi, Punjabi, Urdu. |
| **Input Modality** | Voice only on the candidate side. `responseObjectKey` reserved for future audio archival. |
| **Verdicts** | `Strong Fit`, `Fit`, `Borderline`, `Not Fit` — score-anchored on both backend (`score-final` guardrail) and frontend (`effectiveVerdict()` defensive clamp). |

---

## Assessment Structure

The interview is a **conversation**. Questions are generated one-at-a-time, parameter-driven, and the AI adapts to the candidate's previous answer. The pacing is:

1. **Warmup intro** (hardcoded, not LLM-generated): *"Hi! Welcome to the interview for the &lt;role&gt; role. Before we dive in, could you give me a brief introduction…"*
2. **Parameter probes**: orchestrator picks `nextParameter` = the param with the lowest probe count so far. Each parameter gets up to `QUESTIONS_PER_PARAM = 2` questions before the loop moves on.
3. **Wrap-up**: triggered when any of these hits:
   - `all_parameters_covered` — every param hit its quota
   - `question_cap_reached` — `MAX_TOTAL_QUESTIONS = 8` total turns answered
   - `time_up` — `interviewDuration` exceeded
   - `candidate_unwilling` — `REFUSAL_LIMIT = 2` consecutive trailing refusals
   - `candidate_initiated` — explicit End Interview click

### Per-parameter Rating (0–5)

| Rating | Label | Meaning |
|---|---|---|
| 5 | Excellent | Clear, multi-example mastery for the seniority. |
| 4 | Strong | Solid evidence with minor gaps. |
| 3 | Adequate | Meets the bar for the seniority. |
| 2 | Concern | Gaps worth probing in round 2. |
| 1 | Weak | Real deficiency, but the candidate engaged with the question. |
| **0** | **No Response** | Silence, refusal, song lyrics, gibberish, off-topic content, or one-word non-answers. Contributes **0** to the weighted average (the 20-point arithmetic floor of rating=1 does NOT apply). |

### Overall Score Formula

```
overall_score = Σ ((rating_i / 5) × 100 × weight_i) / Σ weight_i
```

* Then a **completion penalty** if `completion_pct < 80%`: `overall_score × (completion_pct/100)`.
* **Non-engagement caps** (override the formula): >50% non-engagement turns → `overall_score ≤ 10`; 25–50% → `≤ 25`. Verdict forced to Not Fit.
* **Defensive word-count cap** in code after the LLM responds: if ≥50% of substantive answers are ≤ 3 words → cap at 10; if ≥25% short OR average <8 words → cap at 25.

### Verdict Bands & Guardrails

The verdict is **score-anchored** on the backend (and clamped again on the frontend as defense in depth):

| Score | Allowed verdict |
|---|---|
| < 35 | Not Fit |
| 35 – 49 | Borderline |
| 50 – 79 | Fit |
| 80 + | Strong Fit |

Rule is "tighten never upgrade" — if the LLM was stricter than the score (e.g. flagged cheating with Not Fit on a 65), that's preserved. An unknown/missing verdict gets clamped to the ceiling.

### Scoring Eligibility Gate

In `completeSession`, **before** the cron is allowed to score, the interview has to clear:

* `totalAnswered ≥ min(4, totalExpected)`
* `totalAnswered ≥ ceil(totalExpected × 0.5)`

Here `totalAnswered` counts every interaction with a `candidate_response` **including the intro**, and `totalExpected = min(MAX_TOTAL_QUESTIONS, params × QUESTIONS_PER_PARAM + 1)`. Sub-threshold sessions are flagged `sessionMetadata.interviewIncomplete = true` — no score row is created, no fit score is shown, and every report surface (candidate done page, admin StudentReport, admin AIInterviewReport, candidate Reports tab) renders an amber **Interview Not Completed** banner instead of a fabricated score.

---

## End-to-End Flow

```
ADMIN                                CANDIDATE                              SCORING
─────                                ─────────                              ───────
configure config + params            view instructions page                 cron picks up
   │                                   │                                       scores_calculated=false
   ▼                                   ▼                                       ▼
POST /ai-interview/save-definition   GET /ai-interview/config-info           runScoringForAssignment
                                       │ (duration, resumePolicy)               │
                                     biometric → resume? → ready                ▼
                                       │                                     POST /ai-interview/score-final
                                     POST /ai-interview/session/start          (Gemini 3.5-flash,
                                       │                                        background executor +
                                       ▼                                        scoring_semaphore)
                                     loop:                                      │
                                       speak()  ──── ElevenLabs Flash v2.5      ▼
                                       record() ──── Deepgram Nova-3 WS      INSERT ai_interview_scores
                                       Done answering  ──►                      │
                                         POST /ai-interview/session/turn        ▼
                                       (next question or complete=true)      UPDATE scores_calculated=true
                                       │
                                       ▼
                                     POST /ai-interview/session/complete
                                       │
                                       ▼  (status=COMPLETED, submitted=true,
                                          scores_calculated=false unless
                                          interviewIncomplete=true)
```

`completeSession` returns in **< 500 ms** — no inline LLM call. The candidate sees the done screen with a "you'll get results in a few minutes" message + Back to Home button. The per-minute score cron (`calculatePendingAssessmentScores`) does the actual scoring via the new `ai_interview` branch in `Assessment.calculateAssessmentScore`.

---

## Live Conversation Pipeline

| Layer | Detail |
|---|---|
| **Mic capture** | `getUserMedia({audio:true})`. `MediaRecorder` runs in parallel as a fallback so a dropped WebSocket never strands a turn. |
| **Streaming STT** | Browser AudioWorklet pushes 16 kHz PCM frames to FastAPI's `/ai-interview/stt-stream` WebSocket; FastAPI proxies to Deepgram Nova-3 with `utterance_end_ms=1200` + `endpointing=300`. After Deepgram `finish()`, FastAPI sleeps **0.8 s** to drain pending `is_final` callbacks so the last sentence never drops off the transcript. |
| **VAD** | AudioWorklet emits RMS every ~150 ms. Used purely for the "you're speaking" UI cue — **silence auto-submit was removed**. The candidate must click `Done answering`. |
| **No-speech watchdog** | 10 s after the mic opens with zero audio → auto-advance with `[No response]` marker so a broken mic doesn't stall the interview. |
| **Auto-mic** | 350 ms after the AI's TTS audio fires `onended`, `startRecord()` runs automatically. Mic-open path is **non-blocking**: get the media stream + start MediaRecorder + `setRecording(true)` synchronously (sub-1 s on screen); WS + AudioWorklet attach in the background with a 3 s open timeout. |
| **TTS streaming + subtitle** | `speak()` increments a `speakSeqRef` so two concurrent calls can't overlap audio. The question text reveals **word-by-word** in sync with the audio: `<audio>.duration` divides total → per-token interval (clamped 50–180 ms), with a `setTimeout(250 ms)` fallback if metadata never fires. Blinking caret while the AI is still speaking. |
| **End Interview** | `finalize()` bumps `speakSeqRef`, calls `stopCurrentAudio()`, sets `stepRef.current = STEP_DONE` synchronously, and dispatches `completeSession` through `finalizeFnRef` so the mount-time `setInterval` (timer-end path) hits the *latest* closure with a real `sessionId`. Belt-and-suspenders: `completeSession()` also accepts `assessmentAssignedId` as a fallback lookup if `sessionId` ever goes stale on the client. |

---

## Candidate UI

* **Instructions screen** — duration + resume policy fetched from `/ai-interview/config-info/:id`. Resume step is **completely hidden** when policy = `not_required`. Single primary CTA, label-flips based on state ("Continue" / "Skip and continue" / "Continue with resume"). Note pill flips amber (Required) vs indigo (Optional).
* **Live screen** — old "Zoom-style" UI was removed. Simple layout: TopBar (timer + 3-dot End Interview menu), Question card with `AvatarRing` (blue gradient + pulse while AI is speaking, green gradient + listenPulse while listening), streaming subtitle text, Response card with the `Done answering` button. Bottom-right **self-view camera PIP** (200×150 desktop, 120×90 mobile, light-themed) runs independently of the mic capture so it survives between turns.
* **Done screen** — green check + "Your interview is complete", info pill: *"our system is scoring your responses in the background. You'll receive your evaluation in a few minutes. You can safely close this window."* Session reference shown. **Back to Home** button always rendered. The "Scoring in progress" spinner and the "X of Y questions answered" count were both removed — candidates don't get told how many questions are in the bank.

---

## Reports

* **Candidate (Assessment-React)**
  * Reports tab: `getAssessmentReport` now has an `else if (type === "ai_interview")` branch that loads the latest session + score row and emits a flat report into `formattedData`. `AIInterviewReportCard` honours `report.interviewIncomplete` and shows the Interview Not Completed banner instead of a fake "not yet scored" state.
  * Completed list: `View Report` button hidden for corporate-assigned rows (existing `!isCorporate` guard). **Institute candidates do see the button** for AI Interview rows.
* **Admin (admin-react)**
  * `StudentReport` modal: dedicated Candidate header card (resolved via `student.full_name` from `studentPersonalProfile.student_id` → student) plus score block. `effectiveVerdict()` clamps the badge so a score=0 can never read as Borderline.
  * `AIInterviewReport` standalone view: same name resolution, same defensive verdict clamp.
* **PDF**
  * Server-side via `students/assessments/generatePDFReport`. Filename is `<First>_<Last>_report.pdf` derived from `studentData.name` returned by `generateAIInterviewReport`. The HTML template uses `{{candidateName}}` in `<title>` and the header card.
  * Cross-schema name lookup joins `assessment.assessment_assigned_students` → `student.student_personal_profile` → `student.students` (the personal profile carries only address/parents fields, not the name — that's on `students`).

---

## File Reference

### 1. AI Engine (FastAPI)

#### Router — `ai_interview.py`

| Endpoint | Verb | Purpose | Notes |
|---|---|---|---|
| `/ai-interview/suggest-parameters` | POST | Generate role-fit evaluation parameters | priority executor, gemini-2.5-flash |
| `/ai-interview/generate-question` | POST | Next adaptive question | priority executor, gemini-2.5-flash, resume **not** in prompt |
| `/ai-interview/score-turn` | POST | Per-turn signal extraction | priority executor, gemini-2.5-flash, fire-and-forget from student-node |
| `/ai-interview/score-final` | POST | Full transcript → fit score + verdict + narrative | **background executor + scoring_semaphore**, gemini-3.5-flash, resume **not** in prompt |
| `/ai-interview/stt` | POST | Batch STT (fallback for WS failure) | Deepgram Nova-3, `language=hi` covers Hinglish |
| `/ai-interview/stt-stream` | WS | Live streaming STT | 0.8 s post-`finish()` drain so the last sentence isn't lost |
| `/ai-interview/tts` | POST | ElevenLabs Flash v2.5 audio bytes | Payal voice |
| `/ai-interview/parse-resume` | POST | PDF/DOCX/TXT → text (still used by candidate upload; text is captured but NOT passed to the scorer's prompt) |

The blocking Gemini SDK calls are wrapped in `_gemini_json_priority()` and `_gemini_json_background()`, which offload to `priority_executor` (8 workers, shared with proctoring `verify-frame`) and `background_executor` (4 workers, behind `MAX_CONCURRENT_SCORING = 1`) respectively. Live interview LLM calls therefore never queue behind a slow score-final run.

### 2. Admin Backend (admin-node)

#### Handler — `aiInterviewHandler.js`

* `getDefinition`, `saveDefinition`, `assignToStudents`
* `getReportByAssignment` — returns `candidateName`, `candidateEmail`, `interviewIncomplete`, score block

#### Routes

* `GET    /ai-interview/get-definition/:assessmentSetId`
* `POST   /ai-interview/save-definition`
* `POST   /ai-interview/suggest-parameters`
* `POST   /ai-interview/assign-to-students`
* `GET    /ai-interview/report-by-assignment/:assessmentAssignedId`

### 3. Student Backend (student-node)

#### Handler — `aiInterviewHandler.js`

* `startSession`, `submitTurn`, `completeSession` (queues for cron), `getReport`
* `getConfigInfo` — read-only metadata for the instructions screen (duration, role, seniority, resumePolicy, parameterCount)
* `runScoringForAssignment` — cron-callable scorer (loads latest session + transcript + params, calls `score-final`, persists `ai_interview_scores`, flips `scores_calculated=true` via raw SQL `markCalculated()` helper)

#### Routes

* `POST  /ai-interview/session/start`
* `POST  /ai-interview/session/turn`
* `POST  /ai-interview/session/complete`
* `GET   /ai-interview/report/:sessionId`
* `GET   /ai-interview/config-info/:assessmentAssignedId`

#### Cron wiring

* `Assessment.calculateAssessmentScore` has an `ai_interview` branch that delegates to `aiInterviewHandler.runScoringForAssignment`. The existing per-minute `calculatePendingAssessmentScores` cron picks up `scores_calculated=false` rows the same way it does Communication / Aptitude / Behavior / Role-Based.
* `updateDropoutStatusCron`: AI Interview type ID `5f738875-ea18-40f4-9a92-9bccdd732c46` gets a **60-min cutoff** (same as Aptitude) instead of the default 22. The UPDATE re-checks `status='INPROGRESS' AND submitted=false` in its WHERE so a concurrent `completeSession` can never be clobbered back to DROPOUT (race-safe).

---

## Proctoring

`students/assessments/proctoring/uploadImage` was 400'ing intermittently in PROD with *"assessmentAssignedId is required"*. The handler used `await req.file()` then read `data.fields`, but `fastify-multipart` only populates `data.fields` with parts parsed **before** the file boundary. On PROD's k8s ingress the upload was chunked enough that the trailing text parts hadn't been parsed yet when we read fields.

Fixed two ways:

* **Backend** — switched the handler to drain `req.parts()` as an async iterator. The file is buffered via `part.toBuffer()` so iteration continues past it and we still pick up the trailing text parts. Order-independent.
* **Frontend** — `Assessment-React` now appends text fields (`assessmentAssignedId`, `studentId`) **before** the image blob in every proctoring upload call site (`RoleBasedassmt`, `AIInterview/interview.js`; the other types were already in this order).

---

## Database Tables

```
ai_interview_config
  ├─ assessment_set_id   (FK)
  ├─ job_role, job_description, seniority, industry_domain, region
  ├─ interview_duration  (seconds, default 1200)
  ├─ resume_policy       (enum: mandatory | optional | not_required)
  ├─ conversation_rubric (JSONB)
  ├─ evaluation_parameters (JSONB — array of {id, name, description, weight, min_pass_rating})
  └─ stage_config        (JSONB — language, responder_language, probing_style, difficulty_curve)

ai_interview_sessions
  ├─ id                          (UUID, FK from interactions + scores)
  ├─ assessment_assigned_id      (FK)
  ├─ status                      (IN_PROGRESS | COMPLETED)
  ├─ current_stage               (current parameter id)
  ├─ started_at, completed_at, total_duration
  └─ session_metadata            (JSONB — counts, completionReason, interviewIncomplete, totalAnswered, totalExpected, configId, resumeProvided)

ai_interview_interactions
  ├─ session_id                  (FK)
  ├─ question_type               ("introduction" or a parameter id)
  ├─ stage_name, stage_order
  ├─ question_text, question_metadata (JSONB — reasoning, isFollowup, isWarmup)
  ├─ candidate_response          (text — Deepgram transcript)
  ├─ ai_evaluation               (JSONB — per-turn signals from score-turn)
  └─ asked_at, answered_at, evaluated_at

ai_interview_scores
  ├─ session_id, assessment_assigned_id (FKs)
  ├─ overall_score               (0–100)
  ├─ ai_recommendation           (verdict)
  ├─ executive_summary, recommendation_text
  ├─ strengths, weaknesses       (JSONB arrays of {claim, quote, [impact]})
  ├─ parameter_scores            (JSONB array of {id, name, rating, rating_label, analysis, supporting_quote, not_assessed})
  ├─ section_scores              (JSONB — reserved)
  └─ detailed_feedback
```

---

## Migration

The initial migration is bundled at S3 (`pl-uat-public-docs/ai-interview/`). The orchestrator + scoring + cron-handoff changes are pure code; no schema additions required after the initial migration. Subsequent additions live in `DB-Scripts` under `AI Interview/` if any.

The `AI_Interview` type row in `assessment.assessment_type` must exist on each env (DEV + UAT have it; PROD requires the seed before first use).

Reference assessment-type ID: `5f738875-ea18-40f4-9a92-9bccdd732c46` (same on DEV and UAT).

---

## Key Concepts

* **Adaptive, not scripted.** Every next question depends on what the candidate just said. No pre-built question bank.
* **Role-anchored scoring.** Resume text is *not* in the question or scoring prompts — the AI evaluates against the role + JD only. The resume upload UI still exists (admin controls visibility via `resumePolicy`) but the captured text never reaches an LLM prompt.
* **Async by default.** `completeSession` returns immediately; the score cron does the heavy LLM call off the candidate's request path. This is why the priority/background executor split on FastAPI matters — a slow score-final can never starve a live interview turn.
* **0-star floor.** A non-engagement turn (song lyrics, refusal, gibberish, one-word non-answer) scores 0 on the relevant parameter and contributes 0 to the weighted average. Combined with the verdict ceiling and the non-engagement cap, a candidate who didn't actually participate cannot land above ~10/100.
* **Recruiter-first reports.** Corporate-assigned candidates don't see a download button — the report is internal. Institute candidates *do* see their report.
* **Stale-closure dispatcher pattern.** The mount-time `setInterval` (elapsed timer) and the fullscreen-violation `setTimeout` both call `finalize()` via `finalizeFnRef`, which a no-deps `useEffect` rebinds every render. Same pattern for VAD auto-submit via `submitTurnFnRef`. Without this, a timer that fires before the second render would hit a `finalize()` whose closure read `sessionId = null` and the row would stay stuck in INPROGRESS.
