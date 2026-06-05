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
| **Input Modality** | Text (audio/video support via `responseObjectKey` for future STT integration) |

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
|----------------|----------|
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

## File Reference

### 1. AI Engine (FastAPI)

#### Router — `ai_interview.py`
**Path:** `fastapi-ai-engine/routers/ai_interview.py`

**Endpoints:**

| Endpoint | Purpose |
|----------|--------|
| `POST /ai-interview/generate-questions` | Generate initial question set from role/skills/seniority/JD |
| `POST /ai-interview/generate-next-question` | Generate adaptive next question based on conversation history |
| `POST /ai-interview/evaluate-response` | Evaluate a candidate response with weighted scoring |
| `POST /ai-interview/generate-follow-up` | Generate follow-up question probing weak areas |
| `POST /ai-interview/generate-report` | Generate comprehensive interview report with recommendation |
| `POST /ai-interview/parse-resume` | Extract structured data from resume text |
| `POST /ai-interview/parse-jd` | Extract structured requirements from job description |

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
- Fallback: Groq Llama 3.3 70B (`llama-3.3-70b-versatile`)
- Temperature: 0.3 (for consistency)
- PostHog tracking on all endpoints

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

---

## Database Tables

| Table | Purpose |
|-------|--------|
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

## Key Concepts

- **Adaptive Questioning** — Each question adapts to the candidate's prior performance. Strong answers → harder questions. Weak answers → adjusted difficulty or deeper probing.
- **Follow-up Intelligence** — When a response is evaluated as needing deeper exploration (`needsFollowUp: true`), a targeted follow-up is generated probing the specific weak area.
- **Weighted Scoring** — Every response is scored on 4 dimensions (Technical 40%, Depth 25%, Communication 20%, Problem Solving 15%), not just right/wrong.
- **Automated Shortlisting** — Final report includes a `recommendation` field (`strong_hire`/`hire`/`maybe`/`no_hire`) based on overall performance, enabling automated candidate filtering.
- **Resume + JD Context** — Optional endpoints to parse resume and JD text into structured data for more personalized question generation.
- **Multi-Round Types** — Questions can be of type `technical`, `behavioral`, `situational`, or `case_study`, configured per assessment.
- **LLM Fallback** — Gemini 2.5 Pro is primary. If it fails, Groq Llama 3.3 70B is used as fallback. If both fail, 503 is returned.
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
