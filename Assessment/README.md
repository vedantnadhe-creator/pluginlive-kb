# Assessment Platform

This folder contains detailed documentation for each assessment type and cross-cutting infrastructure in the PluginLive Assessment platform.

## Assessment Types

- `communication.md` -- Communication Assessment (reading, listening, speaking, writing with CEFR levels)
- `aptitude.md` -- Aptitude Assessment (quantitative, logical, critical reasoning with adaptive difficulty)
- `rolebased.md` -- Role-Based Assessment (AI-generated MCQ/subjective/video with Gemini scoring)
- `behaviour.md` -- Behaviour Assessment (pending)
- `custom.md` -- Custom Assessment (admin-defined sections with MCQs and image support)
- `ai-interview.md` -- AI Interview Assessment (real-time adaptive interview with shortlisting)
- `schedule.md` -- Assessment Scheduling (recurring auto-assignment via cron)
- `admin.md` -- Admin Assessment Workflow (dashboard, listing, assignment, analytics, proctoring review)
- `admin-frontend.md` -- Admin-React Assessment Frontend (UnifiedAssessmentTable, StudentReport, NPS, pagination, corporate clickability)

---

## Common Assessment Features

All assessment types share these core features, implemented in **`student-node/app/models/Assessment.js`** (13,350 lines, 109 methods).

### Student-Facing Lifecycle

| Function | Purpose |
|----------|--------|
| `getActiveAssessments({ studentId, filters })` | Lists unattempted assessments for a student. Filters: `assessmentType`, `search`, `duration` (lt3, lt5, gt10 days). Merges institute + corporate assignments. Returns assessment name, type, dates, proctoring flag |
| `getCompletedAssessments({ studentId, filters })` | Lists submitted assessments with scores. Filters: `dateFilter` (today, week, month, custom). Includes score type, CEFR level, aptitude level |
| `getCompletedAssessmentsAll({ studentId, filters })` | Variant returning all completed assessments across types |
| `getDropoutAssessments({ studentId, filters })` | Lists expired/missed assessments (endTime < now, not attempted) |
| `checkPracticeAccess(studentId)` | Checks if student has access to practice assessments |
| `getAssessmentQuestions({ assessment_assigned_id })` | Routes to type-specific question fetch (Communication/Aptitude/RoleBased/Behavior/Custom) |

### Response Saving

| Function | Purpose |
|----------|--------|
| `saveResponse({ questionId, answer, assessment_assigned_id, timeTaken, objectKey })` | Generic response saver -- detects type and delegates |
| `saveAptitudeResponse(...)` | Saves aptitude answers with dedup check |
| `saveCommunicationResponse(...)` | Saves communication responses including audio/video `objectKey` |
| `saveCommunicationTextResponse(...)` | Saves text-only communication responses (no sub-question) |
| `saveRoleBasedResponse(...)` | Saves role-based responses (MCQ/subjective/video) |
| `saveBehaviorResponse(...)` | Saves behavior assessment responses |
| `saveMissingResponses(...)` | Bulk-saves any unanswered questions on submit |

### Submission & Scoring

| Function | Purpose |
|----------|--------|
| `submitAssessment({ response, assessment_assigned_id, full_name, totalTakenTime })` | Main submit handler -- saves missing responses, marks `submitted = true`, handles retake detection. Checks `allowProctoring` flag. Routes to appropriate scoring pipeline |
| `calculateAssessmentScore({ assessment_assigned_id })` | Score routing: detects assessment type -> calls type-specific scorer (Communication/Aptitude/RoleBased/Behavior/Custom) |
| `calculateCustomAssessmentScore(assessment_assigned_id)` | MCQ auto-grading for custom assessments |
| `calculateAptitudeScore(assessment_assigned_id)` | Difficulty-weighted aptitude scoring with level progression |
| `calculateRoleBasedScore(assessment_assigned_id)` | Orchestrates MCQ + Subjective + Video scoring for role-based |

### Reports

| Function | Purpose |
|----------|--------|
| `generatePDFReport({ assessment_assigned_id, student_id })` | Routes to type-specific PDF generator |
| `generateCommunicationReport(...)` | Communication report with CEFR levels, section abilities |
| `generateAptitudePDFReport(...)` | Aptitude report with topic-level scores and progression |
| `generateBehaviorPDFReport(...)` | Behavior assessment report |
| `generateRoleBasedReport(...)` | Role-based report with skill scores and AI feedback |
| `getAssessmentReport({ assessment_assigned_id })` | Fetches structured report data (for frontend display, not PDF) |

### Progression & Levels

| Function | Purpose |
|----------|--------|
| `updateCurrCERFlevelOfStudent(studentId, is_practice, assessmentAssignedId)` | Calculates and updates student's CEFR level after communication assessment |
| `updateAptitudeProgression(...)` | Updates aptitude level (Beginner/Learner/Competent/Advanced) and rolling averages |
| `fetchCommunicationProgression(...)` | Progression data between communication assessments with section deltas |
| `fetchAptitudeProgression(...)` | Progression data between aptitude assessments with category deltas |
| `checkRetakeEligibility(assessment_assigned_id)` | Checks if student is eligible for a retake |

### Other Utilities

| Function | Purpose |
|----------|--------|
| `getPrimaryEmail(studentId)` | Resolves student ID -> email |
| `getFullName(primaryEmail)` | Resolves email -> full name |
| `getResultScreenInfo(assessmentAssignedId)` | Data for the post-assessment result screen |
| `getActivityMap(primaryEmail, is_practice, startDate, endDate)` | Student assessment activity calendar |
| `getScoreInfoOfStudent(primaryEmail)` | Aggregate score overview across all types |
| `resetAssessmentForRecalculation(assessment_assigned_id)` | Deletes existing scores and resets `scoresCalculated = false` for recalculation |

**File:** `student-node/app/models/Assessment.js`

---

## Proctoring System

Proctoring monitors students during assessments via periodic screen snapshots. When `allowProctoring = true`, the frontend captures images at intervals, uploads them to OCI Object Storage, and a background pipeline processes them for face detection.

### Architecture

```
Frontend (captures snapshots) -> OCI Storage (snapshot images)
                                       |
                                       v
Cron job (every cycle) -> picks 5 unprocessed snapshots
                                       |
                                       v
FastAPI /proctoring/detect-faces -> face detection -> results saved
                                       |
                                       v
When all snapshots processed -> finalize isValid for proctoring log
```

### FastAPI Proctoring Endpoints

**File:** `fastapi-ai-engine/routers/proctoring.py`

| Endpoint | Method | Purpose |
|----------|--------|--------|
| `/proctoring/detect-faces` | POST | Batch face detection from snapshot keys. Downloads images from OCI, processes concurrently (semaphore limit: 5), returns face count per snapshot. Used by cron |
| `/proctoring/verify-device` | POST | Pre-assessment device verification. Takes 5 frames, passes if face detected in >= 3 frames. Uses `priority_executor` for responsiveness |
| `/proctoring/detect-audio` | POST | Audio/speech detection from base64 audio. Analyzes audio levels + speech activity + human voice verification (FFT frequency analysis, needs 3+ seconds) |
| `/proctoring/ws/verify/{student_id}` | WebSocket | Real-time device verification. Streams frames, returns per-frame face/audio results, final aggregate on "complete" message |
| `/proctoring/verify-frame` | POST | Single-frame face detection for HTTP-based verification |

**Executor Model:**
- `priority_executor` -- used for real-time verification (device check, audio check, WebSocket, single frame) to avoid blocking
- `background_executor` -- used for batch proctoring (detect-faces) which is non-urgent

### Node.js Proctoring Processing

**File:** `student-node/app/models/Assessment.js`

| Function | Purpose |
|----------|--------|
| `storeProctoringSnapshot(data)` | Stores snapshot metadata (objectKey, timestamp). Sets `faceDetected = -1` as "unprocessed" marker |
| `endProctoringSession(assessmentAssignedId)` | Marks the proctoring session as ended |
| `processPendingProctoring()` | **Cron-driven batch processor** -- finds up to 5 unprocessed snapshots (`faceDetected = -1`), sends to FastAPI `/detect-faces`, saves results immediately, finalizes `isValid` when all snapshots for a proctoring log are done |
| `sendProctoringBatchToFastAPI(snapshots, proctoringLogId, assessmentAssignedId)` | Sends batch of snapshot keys to FastAPI, updates each snapshot's `faceDetected` count |
| `finalizeProctoringValidation(proctoringLogId, assessmentAssignedId)` | When all snapshots processed: calculates overall `isValid` based on face detection results |

### Proctoring Cron Job

**File:** `student-node/script/processProctoringCron.js`

- Runs on a cron schedule (configured externally)
- Processes 5 images per cycle to avoid blocking
- Calls `Assessment.processPendingProctoring()`
- Logs processed/failed counts per cycle

### Database Tables

| Table | Purpose |
|-------|--------|
| `proctoring_log` | Per-assessment proctoring session. Contains `isValid` (null -> unprocessed, true/false -> final result) |
| `proctoring_snapshot` | Individual snapshots with `objectKey` (OCI path), `faceDetected` (-1 = unprocessed, 0+ = face count), `timestamp` |

---

## Question Generation Cron System

The **Assessment Scheduler** (`admin-node/script/scheduler.js`) orchestrates background jobs for question generation, assessment scheduling, and question verification.

### Entry Point

**File:** `admin-node/script/assessmentCronWorker.js`

Simple worker that instantiates `AssessmentScheduler` and starts all cron jobs. Runs as a separate Node.js process.

### Scheduler -- `scheduler.js`

**File:** `admin-node/script/scheduler.js`

**`AssessmentScheduler` class** manages all cron jobs:

| Job | Schedule | Status | Purpose |
|-----|----------|--------|--------|
| Communication Set Generation | Every 10 min | **Commented out** | Checks if fresh (unassigned) assessment sets < 100, generates new sets if needed |
| Aptitude Question Generation | Every 10 min | **Commented out** | Checks per-subtopic question counts (min 6 per subtopic per difficulty), generates deficient topics in batches of 3 |
| **Scheduled Assessment Assignment** | **Every 30 min** | **Active** | Calls `AssessmentSchedulerService.processScheduledAssessments()` to auto-assign due assessments |
| Question Verification | Daily at 1:00 AM | **Commented out** | Verifies unreviewed aptitude questions via LLM |

**Key thresholds:**
- `minFreshSetsThreshold = 100` -- minimum unassigned communication sets before generation triggers
- `minAptitudeQuestionsPerSubtopic = 6` -- minimum fresh questions per subtopic per difficulty
- `minTotalFreshAptitudeQuestions = 540` -- minimum total unassigned aptitude questions
- `aptitudeBatchSize = 3` -- questions generated per difficulty per cron run

### Communication Assessment Generator -- `generateCommunicationAssessment.js`

**File:** `admin-node/script/generateCommunicationAssessment.js`

**`AssessmentSetGenerator` class:**
- Generates complete communication assessment sets for all CEFR levels (A1-C2)
- Calls FastAPI AI endpoint to generate questions per section type
- Validates generated questions structure
- Stores in database within a single transaction per set
- Features: exponential backoff on failures, generation locking (prevents concurrent generation), retry with configurable delays

### Aptitude Assessment Generator -- `generateAptitudeAssessment.js`

**File:** `admin-node/script/generateAptitudeAssessment.js`

**`AptitudeAssessmentGenerator` class:**
- 3 aptitude types x 10 subtopics x 3 difficulties = 90 category slots
- Fetches subtopics from DB per aptitude type (Critical Reasoning, Logical Reasoning, Quantitative)
- Checks current fresh question counts per category
- Generates only for deficient categories (targeted generation)
- Calls FastAPI to generate questions via AI
- Validates explanations with regex
- Stores questions with section/sub-section mapping
- Creates audit entries for all generation runs
- Retry logic with configurable attempt limits

### Role-Based Question Generator -- `generateRoleBasedQuestions.js`

**File:** `admin-node/script/generateRoleBasedQuestions.js`

- **Not a cron job** -- called on-demand when admin assigns a role-based assessment
- `generateRoleBasedQuestions(questionsData, assessmentInfo)` -- takes AI-generated question data and stores in DB
- `createRoleBasedAssessment(data)` -- full assessment creation: creates assessment maps, sets, question mappings, student assignments in a transaction
- Handles student creation/retrieval, institute campus mapping, date/time parsing

### Question Verification Worker -- `verifyWorker.js`

**File:** `admin-node/script/verifyWorker.js`

- Fetches 5 unreviewed aptitude questions (`isReviewed = null`)
- Uses in-memory locking to prevent concurrent verification of same questions
- Calls `QuestionManager.verifyQuestionWithLLM(questionId)` -- validates question quality via LLM
- Generates fresh JWT token for system-cron authentication

### Embedding Service -- `embeddingService.js`

**File:** `admin-node/script/embeddingService.js`

**`EmbeddingService` class:**
- Uses **Gemini text-embedding-004** model for question embedding
- Detects **duplicate questions** using cosine similarity
- Preprocesses question text (normalization for consistent embeddings)
- Key methods:
  - `generateEmbedding(text)` -- generates vector embedding
  - `checkQuestionSimilarity(questionText, assessmentTypeId, prisma)` -- checks against existing questions in DB using pgvector
  - `isQuestionDuplicate(...)` -- boolean duplicate check
  - `calculateTextSimilarity(text1, text2)` -- direct pair comparison
- Configurable similarity threshold (default stored in class)
- Used by question generation pipeline to prevent storing duplicate questions

---

## Documentation Structure

Each assessment file covers:
- Overview & section types
- End-to-end flow (creation -> scoring -> reporting)
- File references (frontend, backend, AI engine)
- Scoring logic & weights
- Progression calculation
- Cron job & retry handling
- Database tables
