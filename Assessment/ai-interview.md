# AI Interview Assessment

> AI Interview is a **real-time, adaptive interview** assessment type where an AI interviewer dynamically generates questions based on the candidate's previous answers, resume context, and job description. It supports multiple interview round types (technical, behavioral, situational, case study) and provides automated shortlisting with hire/no-hire recommendations.

---

## Overview

| Property | Value |
|---|---|
| **Assessment Type** | `AI_Interview` |
| **Domain** | `AI_Interview` (short form: `AI_INT`) |
| **Total Duration** | Configurable (default: 60 minutes) |
| **Question Count** | Configurable (default: 5–15 questions) |
| **Question Types** | Technical, Behavioral, Situational, Case Study |
| **Question Generation** | AI-powered, adaptive (Gemini 2.5 Pro + Groq Llama 3.3 70B fallback) |
| **Scoring** | AI-evaluated per-response: Technical Accuracy (40%), Depth (25%), Communication (20%), Problem Solving (15%) |
| **Shortlisting** | Automated: `strong_hire`, `hire`, `maybe`, `no_hire` |
| **Follow-ups** | AI generates probing follow-up questions when responses need deeper exploration |
| **Modality** | **Voice conversation** — AI speaks each question (TTS), candidate replies by voice (STT). Text transcripts are stored alongside. |
| **TTS (interviewer voice)** | **ElevenLabs Flash v2.5** (`eleven_flash_v2_5`) — voice **Payal** (Indian female, Hindi/Indian-English, conversational; voice ID `CpLFIATEbkaZdJr01erZ`). Falls back to **Deepgram Aura-2 `aura-2-thalia-en`** (US English female) if the ElevenLabs key/call fails. Overridable via `ELEVENLABS_VOICE_ID` / `ELEVENLABS_MODEL_ID` env vars on the FastAPI container. |
| **STT (candidate voice)** | **Deepgram `nova-3`** — REST upload (`POST /ai-interview/stt`) plus a WebSocket bridge (`/ai-interview/stt-stream`) that proxies live mic audio to Deepgram and forwards interim + final transcripts back to the browser. |
| **VAD** | Browser-side voice-activity detection auto-submits the answer after ~1.8 s of silence (`Assessment-React/.../AIInterview/interview.js`). |

---

## Assessment Structure

Unlike static assessments, AI Interview is a **conversation** — questions are generated one-at-a-time based on the candidate's performance in prior turns.

| Phase | Description |
|-------|-------------|
| **Initial Questions** | 3–5 questions generated from job role, skills, seniority, and JD |
| **Adaptive Questions** | Next questions adapt based on evaluation scores — harder if candidate performs well, easier if struggling |
| **Follow-ups** | When a response needs probing, a follow-up question targets the weak area |
| **Completion** | After all questions answered (or time expires), a comprehensive report is generated |

### Scoring per Response

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Technical Accuracy | 40% | Correctness of concepts, methods, facts |
| Depth of Knowledge | 25% | Level of detail, nuance, edge-case awareness |
| Communication Clarity | 20% | Structure, articulation, explanation quality |
| Problem Solving | 15% | Analytical approach, reasoning, alternatives |

### Final Recommendation

| Recommendation | Criteria |
|---|---|
| `strong_hire` | Overall score ≥ 85 with high confidence |
| `hire` | Overall score ≥ 70 |
| `maybe` | Overall score 50–69, mixed signals |
| `no_hire` | Overall score < 50 or critical gaps |

---

## End-to-End Flow

1. **Admin assigns AI Interview**: Specifies job role, skills, seniority, industry domain, optional JD, interview duration, follow-up enabled
2. Backend creates `AIInterviewConfig` linked to `AssessmentSet`, assigns students via standard flow
3. Initial questions generated via FastAPI `/ai-interview/generate-questions`
4. **Student starts interview**: Creates `AIInterviewSession`, marks assignment as INPROGRESS
5. Student receives first question, submits text response
6. Response evaluated via FastAPI `/ai-interview/evaluate-response` → scores + feedback stored in `AIInterviewInteraction`
7. If evaluation says `needsFollowUp`, a follow-up question is generated via `/ai-interview/generate-follow-up`
8. Otherwise, next adaptive question generated via `/ai-interview/generate-next-question` based on full conversation history
9. Loop continues until all questions answered or time runs out
10. **Student completes interview**: Final report generated via `/ai-interview/generate-report`
11. `AIInterviewScore` record created with overall + category scores + recommendation
12. Assignment status updated to COMPLETED

---

## Current Orchestration Behavior (authoritative — student-node `aiInterviewHandler.js`)

The live interview is driven by `student-node` (`app/handlers/aiInterviewHandler.js`), not by per-response branching in FastAPI. Key rules as of 2026-06-16:

- **Parameter-driven progression.** The admin's evaluation parameters are probed round-robin (`nextParameter` picks the least-covered one). `QUESTIONS_PER_PARAM = 2`, hard cap `MAX_TOTAL_QUESTIONS = 8`. The interview ends on: all parameters covered, time up, the 8-question cap, or trailing refusals (disengagement).

- **Depth follow-ups (one per parameter).** After each answer, `submitTurn` decides whether to probe the **same** parameter again instead of moving on. It asks a single follow-up when the answer **lacks depth** — a cheap deterministic word-count heuristic (`lacksDepth`, `< 25` words, refusals excluded — no extra LLM call). Guard rails: only on a real parameter (not the intro), **never chains** (the previous turn must not itself be a follow-up → at most one follow-up per parameter), and it is skipped if spending the turn would stop an as-yet-untouched parameter from getting at least one question within the 8-question budget. When triggered, it sends `force_followup: true` to `/ai-interview/generate-question`, which mandates a follow-up that drills into the candidate's previous answer and tags the response `is_followup`.

- **Per-turn scoring is off the critical path.** `score-turn` is fire-and-forget from `submitTurn` (its signals are a soft hint only) and, in FastAPI, now runs on the **background executor** (`_gemini_json_background`, behind the scoring semaphore) instead of the priority pool — so it can never contend with the live `generate-question` call. This removed a visible slowdown on the turn after the first substantive answer (the candidate's "3rd question"). Each live turn is a single Gemini call.

- **Score-anchored verdict.** The fit verdict is always consistent with the numeric score: `< 35` → **Not Fit**, `< 50` → **Borderline**, `< 80` → **Fit**, `≥ 80` → **Strong Fit**. FastAPI `score-final` clamps the LLM's verdict to this ceiling, and student-node derives the verdict from the score when none is returned (`deriveVerdictFromScore`) — so a **0 score never reads as "Borderline"**, in both the report API and the PDF (`Assessment.js`).

- **Admin guidance fields (free-text, optional).** Two columns on `ai_interview_config`, set by the admin on the create form and threaded through admin-node → student-node → FastAPI:
  - `scoring_guidance` — injected into the **score-final** prompt as an "ADMIN SCORING GUIDANCE" block (how to weight/interpret answers). Bounded: it cannot override the non-engagement / anti-cheat rules.
  - `question_guidance` — injected into the **generate-question** prompt as an "ADMIN QUESTION GUIDANCE" block (sample questions, topics, how to ask). The model adapts samples rather than asking them verbatim; still respects role/JD/seniority.

- **Narration voice (admin-selectable).** The admin picks the AI interviewer's spoken voice from a curated set of 6 ElevenLabs voices (Hindi + English, M/F) on the create form, with inline ▶ sample preview (MP3 clips on OCI). The chosen `voice_id` is stored on `ai_interview_config` and threaded admin-node → student-node (`startSession`/`getConfigInfo` return it as `voiceId`) → Assessment-React → FastAPI `/ai-interview/tts`, which uses it as the ElevenLabs `voice_id`. When null, `/tts` falls back to its env default (`ELEVENLABS_VOICE_ID`). **Gotcha (fixed 2026-06-25):** the candidate-side `tts()` previously sent a hardcoded `voice: 'aura-2-thalia-en'` (Deepgram) on every call, which silently overrode the admin's voice choice and forced the Deepgram fallback path — so ElevenLabs voice selection never reached the candidate. Now `tts(text, voiceIdRef.current)` passes the admin voice; null falls back to the backend default.

- **Resume in question generation.** The candidate's resume is sent on every `generate-question` turn and is now **used** to personalise questions (a `CANDIDATE RESUME` block, capped ~6000 chars) — anchored to role/JD. (Earlier the prompt explicitly ignored the resume; that instruction was removed.) `score-final` still does not receive the resume.

- **Per-question context window.** `generate-question` is sent only the **last 3 turns** (`RECENT_TURNS_FOR_LLM = 3`), not the full history — a deliberate latency/cost tradeoff. `score-final` receives the **full** transcript.

---

## File Reference

### 1. AI Engine (FastAPI)

#### Router — `ai_interview.py`
**Path:** `fastapi-ai-engine/routers/ai_interview.py`

**Endpoints:**

| Endpoint | Purpose |
|----------|--------|
| `POST /ai-interview/suggest-parameters` | Suggest skills / topics / seniority defaults from a job role |
| `POST /ai-interview/generate-question` | Generate next adaptive question (initial + follow-ups handled in one path, based on conversation history) |
| `POST /ai-interview/score-turn` | Score a single candidate turn (used during the interview for adaptive routing) |
| `POST /ai-interview/score-final` | Generate the final report — overall + category scores + recommendation |
| `POST /ai-interview/parse-resume` | Extract structured data from resume text |
| `POST /ai-interview/tts` | **Text-to-speech** — ElevenLabs Payal (Flash v2.5); auto-falls-back to Deepgram Aura-2 (`aura-2-thalia-en`). Body: `{ text, voice? }`. Returns audio bytes (mp3). |
| `POST /ai-interview/stt` | **Speech-to-text (REST)** — upload an audio file, Deepgram `nova-3` returns the transcript. |
| `WS   /ai-interview/stt-stream` | **Live STT bridge** — proxies browser mic frames to Deepgram `nova-3` live transcription, forwards interim + final transcripts back over the socket. |

**Key payloads:**

`GenerateQuestionsRequest`:
```python
jobRole: str
skills: List[str]
seniority: str
jobDescription: Optional[str]
domain: Optional[str]
numberOfQuestions: Optional[int] = 5
questionTypes: Optional[List[str]]  # technical, behavioral, situational, case_study
```

`EvaluateResponseRequest`:
```python
question: str
answer: str
questionType: Optional[str] = "technical"
jobRole: Optional[str]
skills: Optional[List[str]]
seniority: Optional[str]
domain: Optional[str]
expectedTopics: Optional[List[str]]
```

`GenerateReportRequest`:
```python
jobRole: str
skills: List[str]
seniority: str
domain: Optional[str]
jobDescription: Optional[str]
conversationHistory: List[Dict]  # [{question, answer, evaluation}, ...]
candidateName: Optional[str]
```

**AI Model Strategy:**
- Primary: Gemini 2.5 Pro via `genai.Client`
- Fast path: Gemini 2.5 Flash (`GEMINI_FAST_MODEL`) for question gen + score-turn (latency-sensitive paths)
- Fallback: Groq Llama 3.3 70B (`llama-3.3-70b-versatile`)
- Temperature: 0.3 (for consistency)
- PostHog tracking on all endpoints

**Voice Stack (TTS + STT):**

| Concern | Provider | Model / Voice | Env Var |
|---|---|---|---|
| TTS primary | ElevenLabs | `eleven_flash_v2_5` + voice **Payal** (`CpLFIATEbkaZdJr01erZ`, Indian female, hi/Indian-English, conversational) | `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_ID` |
| TTS fallback | Deepgram | `aura-2-thalia-en` (US English female) — used if `ELEVENLABS_API_KEY` is missing or the ElevenLabs call errors | `DEEPGRAM_API_KEY` |
| STT (file + live) | Deepgram | `nova-3` (REST `/stt` + WebSocket `/stt-stream`) | `DEEPGRAM_API_KEY` |

The `/tts` endpoint also accepts an optional `voice` body param — values starting with `aura` route to Deepgram; anything else is treated as an ElevenLabs voice ID. The Assessment-React frontend sends the admin-chosen `voice_id` from the session config (falls back to backend default when null). **Don't** hardcode an `aura-*` voice in the frontend `tts()` call — that forces the Deepgram path and silently overrides the admin's ElevenLabs voice selection (this was a bug, fixed 2026-06-25).

Source-code defaults in `routers/ai_interview.py` are `EXAVITQu4vr4xnSDxMaL` (Sarah / US English) for the voice ID and `eleven_flash_v2_5` for the model — these are only effective when the env vars are not set. All deployed environments (DEV today) override the voice to Payal via `.env`.

---

### 2. Admin Backend

#### Model — `AIInterview.js`
**Path:** `admin-node/app/models/AIInterview.js`

**`assignAIInterviewAssessment()`**
Parameters: `entityId, entityType, name, startTime, endTime, bulkUploadData, interviewConfig, allowProctoring`

In a transaction:
1. Finds `AI_Interview` assessment type (must exist — run migration first)
2. Finds or creates `AI_Interview` assessment domain
3. Calls FastAPI to generate initial questions
4. Creates `AssessmentSet` with `roleName` and `seniority`
5. Creates `AIInterviewConfig` with job role, skills, seniority, domain, JD, duration, follow-up settings
6. Creates assessment sections and stores generated questions
7. Creates `AssessmentInstituteMap` or `AssessmentCorporateMap`
8. Assigns each student via `AssessmentAssignedStudent`

**`startInterviewSession(assessmentAssignedId)`**
- Gets assignment with config
- Creates `AIInterviewSession` (status: IN_PROGRESS)
- Updates assignment status to INPROGRESS
- Returns session ID and initial screening questions

**`submitInterviewAnswer({ sessionId, questionId, candidateResponse, responseObjectKey })`**
- Creates `AIInterviewInteraction` record
- Sends to FastAPI for evaluation with conversation context
- Updates interaction with scores
- Generates follow-up if `needsFollowUp` is true

**`completeInterview(sessionId)`**
- Gets all interactions
- Calls FastAPI `/ai-interview/generate-report`
- Creates `AIInterviewScore` record
- Updates session to COMPLETED, assignment to COMPLETED

**`getInterviewProgress(assessmentAssignedId)`**
- Returns session status, question count, answered count, scores

#### FastAPIService methods
**Path:** `admin-node/app/service/FastAPIService.js`

| Method | FastAPI Endpoint |
|--------|------------------|
| `generateAIInterviewQuestions()` | `POST /ai-interview/generate-questions` |
| `evaluateAIInterviewResponse()` | `POST /ai-interview/evaluate-response` |
| `generateFollowUpQuestion()` | `POST /ai-interview/generate-follow-up` |
| `generateInterviewReport()` | `POST /ai-interview/generate-report` |

#### Routes
**Path:** `admin-node/app/routes/aiInterview.js`

| Method | Path | Handler |
|--------|------|--------|
| `POST` | `/ai-interview/assign` | `assignAIInterview` |
| `GET` | `/ai-interview/progress/:assessmentAssignedId` | `getAIInterviewProgress` |
| `GET` | `/ai-interview/results/:assessmentAssignedId` | `getAIInterviewResults` |
| `GET` | `/ai-interview/analytics/:assessmentMapId` | `getAIInterviewAnalytics` |
| `GET` | `/ai-interview/config/:assessmentSetId` | `getAIInterviewConfig` |

---

### 3. Student Backend

#### Model — `AIInterview.js`
**Path:** `student-node/app/models/AIInterview.js`

| Method | Purpose |
|--------|--------|
| `startInterview({ assessmentAssignedId })` | Create session, get initial questions from FastAPI, create interaction records |
| `submitAnswer({ sessionId, interactionId, candidateResponse, responseObjectKey })` | Evaluate response, generate follow-up if needed |
| `getNextQuestion({ sessionId })` | Get adaptive next question based on conversation history |
| `completeInterview({ sessionId })` | Generate final report, create score record, mark complete |
| `getInterviewStatus({ assessmentAssignedId })` | Get session progress |
| `getInterviewResult({ assessmentAssignedId })` | Get full completed interview data |

#### Routes
**Path:** `student-node/app/routes/aiInterview.js`

| Method | Path | Handler |
|--------|------|--------|
| `POST` | `/ai-interview/start` | `startInterview` |
| `POST` | `/ai-interview/submit-answer` | `submitAnswer` |
| `POST` | `/ai-interview/next-question` | `getNextQuestion` |
| `POST` | `/ai-interview/complete` | `completeInterview` |
| `GET` | `/ai-interview/status/:assessmentAssignedId` | `getInterviewStatus` |
| `GET` | `/ai-interview/result/:assessmentAssignedId` | `getInterviewResult` |

#### Final Scoring Pipeline (production truth)

Final scoring does **not** run on the candidate's request path. It is driven by the
generic assessment-scoring cron, the same one used for aptitude/communication:

1. `aiInterviewHandler.completeSession()` (`student-node/app/handlers/aiInterviewHandler.js`)
   marks the session `COMPLETED`, sets the assignment `submitted=true`, and flips
   `scores_calculated=false` (only if there is enough signal — see thresholds below).
2. `script/calculatePendingAssessmentCron.js` runs **every minute**, picks **one** pending
   assignment (`attempted=true, submitted=true, scores_calculated=false, is_processing=false`),
   atomically locks it (`is_processing=true`), and calls
   `Assessment.calculateAssessmentScore({ assessment_assigned_id })`.
3. For `assessmentType === "ai_interview"`, that delegates to
   `aiInterviewHandler.runScoringForAssignment()`, which calls FastAPI
   `POST /ai-interview/score-final` (Gemini `gemini-2.5-pro`) and persists one
   `ai_interview_scores` row (`overall_score`, `ai_recommendation`, `parameter_scores`,
   `strengths`, `weaknesses`, `executive_summary`, `recommendation_text`).
4. On success the cron sets `scores_calculated=true`. On error it increments
   `calculation_attempts`; after the max it sets `calculation_error=true` and **stops
   retrying** (so the row silently disappears from the cron's pickup query).

**Scoring thresholds** (in `aiInterviewHandler.js`): `MIN_ANSWERS_FOR_SCORING = 4` and a
**50% coverage** floor of expected questions. Interviews below this are marked
`scores_calculated=true` with **no score row** (legitimately skipped as incomplete — not an error).

#### Gotcha — corporate candidates with no student profile (fixed 2026-06-12)

`Assessment.calculateAssessmentScore()` called `getFullName(primaryEmail)`
**unconditionally before** the assessment-type branch. `getFullName()` reads the student
micro-service profile and **throws `"Student not found"`** when none exists. AI-interview
candidates are **corporate applicants invited by email** (e.g. `name+alias@…`) who often have
no student profile in that DB — so scoring threw before ever reaching the `ai_interview`
branch (which never uses `full_name`). The cron classified it as non-transient, retried 3×,
then set `calculation_error=true` — leaving completed interviews permanently unscored.

**Fix:** compute `assessmentType` first, then make `getFullName()` non-fatal for
`ai_interview`/`ai-interview` (the original throw is preserved for every other type). Also
added an `ai_interview` case to `resetForRecalculation` (it previously fell through to the
communication-scores fallback and timed out the Prisma transaction), so manual recalc now
deletes `ai_interview_scores` cleanly.

**To re-score a stuck interview:** clear the flags on `assessment_assigned_students`
(`scores_calculated=false, is_processing=false, calculation_error=false,
calculation_attempts=0`) — the cron re-picks it within ~1 minute.

#### Gotcha — report/UI showed the email instead of the candidate name (fixed 2026-06-12)

Root cause of the **same** missing-profile problem: `assignAIInterviewAssessment()`
(`admin-node/app/models/Assessment.js`) **skipped student-account creation** — by design it
was "OTP-invite-only, no portal accounts". But every name lookup (the report header in both
`getReport` / `getReportByAssignment`, and the admin StudentReport modal + client-side PDF)
joins `student_personal_profile → students` by `primary_email`. With no profile row, the name
resolved to empty and the UI fell back to the **raw email** — so the report showed
`email — email` where `name — email` belongs.

**Fix (the right one, not a display patch):** AI-interview assignment now creates a student
profile for each **new** candidate exactly like the other corporate/college assessment types
(Aptitude / Communication / Role-Based all call `studentService.createPublicStudent`), using
the `first_name`/`last_name` already present in `bulkUploadData`. `skipActivationEmail` follows
the entity (see the invite-delivery split below). Payload lives in the pure, unit-tested helper
`admin-node/app/helpers/aiInterviewStudentPayload.js`. No change to the report code — the name
now resolves naturally from the profile.

#### Invite delivery splits by entity type — OTP for corporate, portal for institute (2026-06-17)

`assignAIInterviewAssessment()` (`admin-node/app/models/Assessment.js`) was OTP-invite-only for
**every** AI Interview, regardless of who it was assigned to. It now branches on `isCollege`
(derived from `entityType` ∈ `college`/`institute`/`university`):

- **Corporate** (`!isCollege`) — unchanged passwordless flow. Fires the
  `sendAssessmentInviteEmail(..., assessmentType: "AI_Interview")` OTP invite per candidate, and
  the student account is created **silently** (`skipActivationEmail: true`) so the OTP invite is
  the candidate's only email. Candidate authenticates with the 6-digit OTP and runs the
  interview straight from the invite link — see [otp-invite.md](otp-invite.md).
- **Institute** (`isCollege`) — **no OTP invite**. Uses the normal student-portal flow like
  Aptitude / Communication institute assignments, and splits emails **by new-vs-existing**
  exactly like `assignCommunicationAssessment`:
  - **New** candidates → only the **account-creation/activation email**, sent by
    `createPublicStudent` (`skipActivationEmail: false`, now `!isCollege` in
    `aiInterviewStudentPayload.js`). They do **not** also get a reminder. **Gotcha
    (fixed 2026-06-17):** student-node `createPublicStudent` **requires `degreeStreamMap`
    (`degreeId` + `streamId`) for non-corporate students** — without it `POST /students`
    returns `400 "degreeId and departmentId is required"`, the account is never created,
    and **no activation email is ever sent** (corporate skips this — the check is gated on
    `!isCorporate`). `aiInterviewStudentPayload.js` therefore populates `currentCourse` +
    `degreeStreamMap` from the upload's `degree`/`department` objects
    (`cand.degree?.degreeId || cand.degree_id`, `cand.department?.streamId || cand.stream_id`),
    exactly like the customAssessment / communication institute flows. **Second gotcha
    (fixed 2026-06-17):** the institute payload must **not** set `student.currentState = 1`.
    `current_state >= 1` marks a student as already-onboarded, so the activation email's
    `/onboarding/activate/:studentId` link **bounced to login instead of the account-setup
    flow**. Institute now omits `currentState` (student-node defaults `current_state` to 0 →
    onboarding runs), matching communication/customAssessment; only the corporate OTP path
    keeps `currentState: 1` (it never uses portal onboarding).
  - **Existing** candidates (already have a portal account) → only the standard
    **assessment-reminder email** via `this.sendRemindersToStudents(assessment.id, "college",
    existingUsers, …)`. No activation email (they're already activated).

  New-vs-existing is determined by a `student_personal_profile`/`students` lookup on the
  candidate emails (`newUsers` / `existingUsers`). The reminder links to the student portal
  (`/onboarding/activate/:studentId` or `/login`); the candidate logs in and takes the AI
  Interview from inside the authenticated portal. The reminder send is wrapped in try/catch so a
  reminder failure never aborts the assignment.

Net: corporate candidates get **one** email (OTP invite); institute candidates get **one**
portal email each — activation for new students, reminder for existing — and never see the OTP
screen. (Earlier the institute branch wrongly sent the reminder to *all* candidates, so new
students got a reminder instead of their activation email — fixed 2026-06-17 to match
Communication.)

Forward-looking only: candidates assigned **before** this fix still lack a profile (no upload
names are stored to backfill from). If names are missing from the upload, the profile is
created without them (same as other types) and the report shows the email until a name exists.

---

## Database Tables

| Table | Purpose |
|---|---|
| `ai_interview_config` | Per-assessment-set interview configuration: job role, skills, seniority, duration, AI model, evaluation criteria |
| `ai_interview_sessions` | Per-student session: status (PENDING/IN_PROGRESS/COMPLETED), start/end times, duration, metadata |
| `ai_interview_interactions` | Per-question interaction log: question text, response, score, AI evaluation, follow-up tracking |
| `ai_interview_scores` | Final scores: overall, technical, behavioral, communication, problem-solving, recommendation, strengths, weaknesses |

### Schema Relationships

```
AssessmentSet
  └─ AIInterviewConfig (1:1)

AssessmentAssignedStudent
  └─ AIInterviewSession (1:many)
       ├─ AIInterviewInteraction (1:many)
       └─ AIInterviewScore (1:many)
```

### Key Fields

**AIInterviewConfig:**
- `job_role`, `seniority`, `skills[]`, `industry_domain`
- `job_description` (full JD text for context)
- `interview_duration` (minutes, default 60)
- `enable_follow_up` (boolean, default true)
- `ai_model` (e.g., "gemini-2.5-pro")
- `evaluation_criteria` (JSONB for custom weight overrides)
- `scoring_guidance`, `question_guidance` (free-text admin guidance injected into score-final / generate-question prompts — see Orchestration)
- `voice_id` (ElevenLabs voice_id the AI narrator speaks in; admin-selectable, null → backend default)

**AIInterviewInteraction:**
- `question_type`: TECHNICAL, BEHAVIORAL, SITUATIONAL, CASE_STUDY
- `score`: 0–100 overall weighted score per response
- `ai_evaluation`: JSONB containing `{ technicalAccuracy, depthOfKnowledge, communicationClarity, problemSolving, strengths, areasForImprovement, needsFollowUp }`
- `is_follow_up`: boolean, true if this was a follow-up question
- `parent_interaction_id`: links follow-up to original question

**AIInterviewScore:**
- `overall_score`: 0–100 weighted final score
- `technical_score`, `behavioral_score`, `communication_score`, `problem_solving_score`: 0–100 category scores
- `ai_recommendation`: `strong_hire` | `hire` | `maybe` | `no_hire`
- `strengths`, `weaknesses`: JSONB arrays
- `detailed_feedback`: comprehensive text analysis

---

## Data Export (Excel)

The institute-admin panel supports **exporting AI Interview assessment results to Excel** via `POST /assessment/exportStudentListForAssessment/:instituteId` (handled by student-node `TpoDashBoard.exportExcelOfStudentListForAssessment`). The export **now correctly identifies AI Interview assessments** (as of 2026-06-19) and produces interview-specific columns:

| Column | Type | Source |
|---|---|---|
| Candidate Name | String | Student name from profile |
| Email | String | Candidate email |
| Degree | String | Course degree |
| Department | String | Course department |
| Assmt. Taken On | Date | Assessment submission date (DD/MM/YYYY) |
| Taken / Sent | String | X/Y count |
| **Overall Score** | Integer | `ai_interview_scores.overall_score` (0–100) |
| **[Parameter Name] (/5)** | Integer | Per-parameter rating from `ai_interview_scores.parameter_scores[*].rating` (1–5 scale) — one column per unique parameter across all candidates |
| Proctoring | String | Good / Bad |

**Key points:**
- **Type detection:** The export resolves the assessment type from the returned data (prefers `assessmentType` on each student record) rather than relying on the request parameter, so an empty/wrong `assessmentType` input does not fallback to a Communication-style report.
- **No suggestions:** The export includes only the overall score and parameter ratings. Analysis/recommendation text from `parameterScores[*].analysis` and `recommendation_text` are **intentionally excluded** to keep the Excel lightweight and focused on scores.
- **Dynamic columns:** Parameter names are collected as the union across all students, preserving first-seen order. Parameter names are title-cased and space-separated in column headers (e.g. `"role_fit"` → `"Role Fit (/5)"`).
- **Gotcha fixed (2026-06-19):** Previously, the export was missing the `aiInterviewSessions → scores` include in the assignment query, so the scoreMap never saw AI Interview data. The export would silently fall through to the Communication branch, producing Reading/Listening/Speaking/Writing columns and a `-` score. This is now fixed — assignments are queried with the session + score includes, and the scoreMap builds correctly for AI interviews.

---

## Migration

**SQL migration file:** `admin-node/migrations/add_ai_interview_tables.sql`

Creates:
1. Seeds `AI_Interview` assessment type and domain
2. `ai_interview_config` table (FK → `assessment_sets`)
3. `ai_interview_sessions` table (FK → `assessment_assigned_students`)
4. `ai_interview_interactions` table (FK → `ai_interview_sessions`)
5. `ai_interview_scores` table (FK → `ai_interview_sessions`)
6. All indexes on foreign keys and frequently queried columns

Run against the assessment database:
```bash
psql -h <host> -U <user> -d <assessment_db> -f migrations/add_ai_interview_tables.sql
```

---

## Frontend (Assessment-React)

The candidate-facing AI Interview UI lives in `Assessment-React/src/modules/Assessments/Partials/AIInterview/`:

- **`InviteStart.js`** — OTP-based invite start screen. A candidate opening an AI Interview invite link enters the OTP to authenticate and start the session (the invite API in `aiInterviewInviteAPI.js` calls auth + student services). Since 2026-06-11 this same screen also handles **all other corporate assessment types** under the generalized OTP-invite flow — see [otp-invite.md](otp-invite.md).
- **`interview.js`** — the live voice interview surface (TTS playback, mic capture, browser VAD auto-submit after ~1.8 s of silence).
- **`instruction.js`** — welcome / readiness / **resume** pre-start screens shown before the live interview.
- **`resumeUpload.js`** — shared, unit-tested handler for the pre-start resume upload (see gotcha below).
- **Completion behaviour is now flow-aware (since 2026-06-17)** — the Thank-You screen branches on whether the candidate is a logged-in student or an OTP invite candidate (`isInvite = !!readInviteScopedJwt()`):
  - **Logged-in student** — the completion screen shows a **"Back to Assessments"** primary button. `goHome()` exits fullscreen, marks the assignment completed locally (see below), calls `setAssessment(null)` (re-renders the inline dashboard list) **and** `navigate('/assessment')`. Returning to the dashboard re-fetches active + completed, so the just-finished interview drops out of **Active** and appears under **Completed** (the server already set `status=COMPLETED, submitted=true` in `completeSession`; the active-list query filters `submitted:false` in `student-node` `Assessment.js`). The standalone `/ai-interview/:id` exit fallback in `index.js` now `navigate('/assessment')` instead of `window.history.back()`.
  - **OTP invite candidate** — completion stays **terminal** ("You can now close this window"), no portal button. The earlier removal (2026-06-15) was because a blanket "Back to Home" cleared the scoped JWT and bounced invite candidates into `AuthPage` (which auto-fires `window.open(AUTH_URL)`); that hazard only applies to invite candidates, so the button is now gated to logged-in students only.
- **Completion reload guard (since 2026-06-17)** — on `completeSession` success, `interview.js` persists `localStorage['ai_interview_completed_<assignedId>'] = '1'` (helpers `markAiInterviewCompleted` / `isAiInterviewCompleted` in `aiInterviewInviteAPI.js`). On mount, `instruction.js` reads this flag so a **page reload no longer restarts the instructions/welcome flow**: a logged-in student is redirected to `/assessment` (renders nothing meanwhile to avoid a welcome-screen flash); an OTP candidate gets a terminal **"Your interview is already complete"** notice. This complements the server-side no-retake gate (409 from `startSession` once `status=COMPLETED`/`submitted=true`) and the `InviteStart` "already submitted" gate (see [otp-invite.md](otp-invite.md)).

### Candidate resume upload (pre-start)

On the instructions screen the candidate optionally attaches a resume (PDF/DOCX/TXT, ≤6 MB). The file is **POSTed directly to FastAPI** `${REACT_APP_FASTAPI_URL}/ai-interview/parse-resume` as multipart (`file` field) — it does **not** go through student-node and is **not** stored in S3. FastAPI extracts plain text (PyMuPDF for PDF, python-docx for DOCX) and returns `{ text, chars, truncated, filename }`. The text is held in component state and passed as `resumeText` to `POST /ai-interview/session/start` (and on each `session/turn`), giving the interviewer resume context. The endpoint requires **no auth** (`_verify` is disabled), so a missing invite JWT does not block it. Field config (`resume_policy`: `mandatory` / `optional` / `not_required`) comes from `ai_interview_config` and is surfaced via `config-info`.

### Frontend Gotcha — resume upload silently did nothing (Fixed 2026-06-12)

The pre-start upload stacked **two upload mechanisms**: an antd `<Upload.Dragger beforeUpload>` *wrapping* a nested `<label htmlFor>` + hidden `<input>` whose `onClick` did `e.preventDefault()` then a manual `input.click()`. The two fought each other — the label's default activation was cancelled and the programmatic click was swallowed inside the Dragger — so the **file dialog often never opened and the `parse-resume` request was never sent**. Symptom: "users can't upload a resume" while the FastAPI endpoint, CORS, and the baked-in URL are all healthy (the tell: **zero** `parse-resume` requests in the server logs).

**Fix:** collapse to a single path — antd's `Upload.Dragger` opens the dialog on click **and** handles drag-and-drop, both feeding one shared `handleResumeFile()` in `resumeUpload.js`; `beforeUpload` returns `false` so antd never auto-uploads. `ResumeDrop` changed from `<label>` to `<div>` (no input to pair with). Diagnose recurrences by checking whether any `parse-resume` request reaches FastAPI at all — if not, it's the client, not the server.

### Frontend Build Gotcha — `process.env` must use member access (Fixed)

Assessment-React is **webpack 5** and inlines env vars via `EnvironmentPlugin`. Env vars are only inlined for **explicit member-access** expressions like `process.env.API_URL`. Writing whole-object destructuring — `const { API_URL, STD_API_URL } = process.env` — combined with `X || fallback` usage can leave a **dangling bare `process.env`** statement in the production bundle. Webpack 5 does not polyfill `process`, so at module-eval the app throws **`ReferenceError: process is not defined`**, the SPA never mounts, and you get a **blank white screen on every route** (the build still succeeds — it's a runtime crash).

This bit `aiInterviewInviteAPI.js` and blanked the whole app on DEV and again on UAT (2026-06-10). **Rule:** in this repo, read env vars as `const API_URL = process.env.API_URL` (member access), never destructure `process.env`. Diagnose by grepping the built bundle for a non-member `process.env` token; the runtime `pageerror` is `process is not defined`.

---

## Key Concepts

- **Adaptive Questioning** — Each question adapts to the candidate's prior performance. Strong answers → harder questions. Weak answers → adjusted difficulty or deeper probing.
- **Follow-up Intelligence** — When a response is evaluated as needing deeper exploration (`needsFollowUp: true`), a targeted follow-up is generated probing the specific weak area.
- **Weighted Scoring** — Every response is scored on 4 dimensions (Technical 40%, Depth 25%, Communication 20%, Problem Solving 15%), not just right/wrong.
- **Automated Shortlisting** — Final report includes a `recommendation` field (`strong_hire`/`hire`/`maybe`/`no_hire`) based on overall performance, enabling automated candidate filtering.
- **Resume + JD Context** — Optional endpoints to parse resume and JD text into structured data for more personalized question generation.
- **Multi-Round Types** — Questions can be of type `technical`, `behavioral`, `situational`, or `case_study`, configured per assessment.
- **LLM Fallback** — Gemini 2.5 Pro is primary. If it fails, Groq Llama 3.3 70B is used as fallback. If both fail, 503 is returned.
- **Voice (Payal — Indian female, conversational)** — The AI interviewer speaks via ElevenLabs Flash v2.5 with the **Payal** voice (Hindi/Indian-English, casual tone), matched to the Indian candidate base. Deepgram Aura-2 Thalia (US English) is the failover. STT is Deepgram `nova-3` for both REST and live WebSocket modes. Browser VAD auto-submits the answer after ~1.8 s of silence.
- **PostHog Analytics** — All question generation, evaluation, and report events are tracked in PostHog for monitoring and analytics.
- **Standard Assignment Flow** — Uses the existing `AssessmentSet` → `AssessmentInstituteMap`/`AssessmentCorporateMap` → `AssessmentAssignedStudent` pipeline, same as Communication, Aptitude, and Role-Based assessments.

---

## Corporate ATS Candidate List Surfacing

When an `AI_Interview` assessment is mapped to a (drive, role, round) cell via the cell-assessment mapping (`assessment_corporate_map.mapped_to`), the corp-ATS candidate list (`POST /corporates/drive/:driveId/role/:roleId/candidate/list`) renders **one column per round**: **Overall Score** (a single 0–100 number).

This is unlike Communication or Role-Based rounds which expand into multiple sub-topic columns (Verbal/Reading/Listening/Writing/Total/CEFR for Communication; MCQ/Subjective/Video/Coding/Overall for Role-Based).

### Score Path

- `admin-node` `Assessment.getStudentAssessmentScores()` dispatches on `assessment_type.type_name`. The AI Interview branch reads the latest `assessment.ai_interview_scores.overall_score` (joined via `ai_interview_sessions.assessment_assigned_id`) and returns `aiInterviewScores: { overallScore }`.
- `corporate-node` `helpers/evaluationAssessmentOverlay.js` overlays that value into `parameters_score[round].overallScore` and seeds `topics[round].subTopic = ["overallScore"]` so the corp-ATS FE renders exactly one column titled "Overall Score" under the round.
- The FE (`corporate-react` `IndividualDriveTable`) treats `overallScore` as the round's overall sub-topic and suppresses the duplicate round-average column.

### Gotcha (Fixed)

Prior to this dispatch branch, `AI_Interview` matched none of the dispatcher's type checks (`behavi`/`aptitude`/`role`/`custom`) and fell through to the Communication else-branch — so AI Interview rounds rendered the 6 Communication sub-topic headers (Verbal/Reading/Listening/Writing/Total/CEFR) sourced from an empty `communication_scores` table. The dispatcher now has an explicit `AI_Interview` branch and the corp-ATS overlay's `STATIC_SUB_TOPIC_SCHEMA` includes `aiInterview: ["overallScore"]`.

### Round Score Filter

The Drive Role's Round Score / Passing Score filter (`GET /corporates/drive/:driveId/role/:roleId/score/list?stage=<round>`) is built from `job_role_student_map.parameters_score` joined against the role's interview workflow. Because AI Interview scores live in `assessment.ai_interview_scores` (not in `job_role_student_map`), the old behavior left `parameters_score` empty for AI Interview rounds and the filter panel rendered "No Data Found". The handler now seeds a topic entry from `getCellSubTopicSchema` whenever the round is mapped to an assessment but has no sheet-derived sub-topics — so the filter row always reflects `["overallScore"]` for AI Interview cells.

The corp-react Drive Role page also fetches `score/list` in a dedicated `useEffect` (separate from the long `fetchOptions` chain) so a transient failure in one of the other ~11 filter endpoints can't keep the Round Score panel empty.

### Applying the Round Score Filter

Applying the filter (e.g. `Assessment >= 50`) flows through `POST /corporates/drive/:driveId/role/:roleId/candidate/list` with `body.scores = [{ topic: { name: "Assessment", score: 50 } }]`. The default SQL filter compares against `jrsm.average_rounds_score` / `jrsm.parameters_score`, which are NULL for assessment-mapped rounds (AI Interview is the canonical case), so the query returned zero rows.

`interviewHandler.getCandidateListForHR` now pre-resolves each assessment-mapped score entry via `resolveAssessmentScoreFilter` (in `helpers/evaluationAssessmentOverlay.js`):

1. For each entry whose round is mapped to an assessment, call admin-node `getCellAssessments` + `getCellScoresBundle` for every candidate email on the role.
2. Apply the threshold (`selection: >= score`, `rejection: <= score`) using the bucket's headline key (`overallScore` → `overallPercentage` → `totalScore`).
3. Intersect the matched-email sets across every assessment-mapped score entry.
4. Translate the surviving emails to `corporate.job_role_student_map.student_id` via `student.student_personal_profile`.
5. Strip those entries from `body.scores` and pass `assessmentScoreStudentIds` to `DriveRoleCandidateMap.getCandForHR`, which adds `AND jrsm.student_id IN (...)` to both the count and data queries (`AND FALSE` when the intersection is empty so count + data agree).
