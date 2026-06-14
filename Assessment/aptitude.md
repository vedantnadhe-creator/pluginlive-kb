# Aptitude Assessment

> The Aptitude Assessment evaluates a student's **Quantitative Aptitude, Logical Reasoning, and Critical Reasoning** abilities using MCQ-based questions. Students are assigned an adaptive **proficiency level** (Beginner → Learner → Competent → Advanced) that evolves based on their performance.

---

## Overview

| Property | Value |
|---|---|
| **Assessment Type** | `Aptitude` |
| **Total Questions** | 30 MCQs |
| **Proficiency Levels** | Beginner, Learner, Competent, Advanced |
| **Difficulty Levels** | Easy, Medium, Hard |
| **Negative Marking** | Optional (configurable per assessment) |
| **Scoring Model** | Difficulty-weighted points |
| **Time Tracked** | Per-question time |

---

## Assessment Sections (3 Categories)

| Section | Default Questions | Subtopics (examples) |
|---------|------------------|----------------------|
| **Quantitative Aptitude** | 12 | Percentages, Profit & Loss, Time & Work, Averages, etc. |
| **Logical Reasoning** | 11 | Series, Coding-Decoding, Syllogisms, Blood Relations, etc. |
| **Critical Reasoning** | 7 | Analogies, Statement Analysis, etc. |

Questions are distributed across subtopics based on **weights** defined in the `sub_sections` table.

---

## Scoring System

### Difficulty Points

| Difficulty | Points (correct) | Negative Marking (wrong) |
|-----------|------------------|---------------------------|
| Easy | +1 | −0.25 |
| Medium | +2 | −0.50 |
| Hard | +3 | −0.75 |

Negative marking is **optional** — controlled by the `isMinusSystem` flag set during assessment creation. Skipped questions receive 0 points.

### Difficulty Distribution (auto-generated per level)

| Student Level | Easy | Medium | Hard |
|---------------|------|--------|------|
| Easy set | 15 | 8 | 7 |
| Medium set | 8 | 15 | 7 |
| Hard set | 10 | 10 | 10 |

---

## Level Determination

Levels are determined by the `getLevel()` function using the **difficulty** of the assessment and the **competency score** (weighted topic average).

### Difficulty → Level Matrix

| Difficulty | Score Range | Assigned Level |
|-----------|------------|----------------|
| **Easy** | 0–79% | Beginner |
| **Easy** | 80–100% | Learner |
| **Medium** | 0–39% | Beginner |
| **Medium** | 40–69% | Learner |
| **Medium** | 70–89% | Competent |
| **Medium** | 90–100% | Advanced |
| **Hard** | 0–39% | Beginner |
| **Hard** | 40–59% | Learner |
| **Hard** | 60–79% | Competent |
| **Hard** | 80–100% | Advanced |

> **Important:** For ongoing assessments (post-diagnosis), `getNewAssessmentLevel()` is used instead — it **prevents level downgrades**. Students can only maintain or improve their assessment level.

### Level → Difficulty Mapping (Adaptive)

When a student takes a new assessment, their level determines the base difficulty:

| Student Level | Assessment Difficulty |
|---------------|----------------------|
| Beginner | Easy |
| Learner | Medium |
| Competent | Medium |
| Advanced | Hard |

### ~~Difficulty Multipliers~~ (Removed)

Previously, difficulty multipliers (Easy 0.85×, Medium 1.15×, Hard 1.40×) were applied to topic rolling averages via `calculateWeightedPercentage()`. These were **removed** because `getLevel()` already uses difficulty-specific thresholds — applying multipliers on top double-counted difficulty, causing inconsistent level assignments.

Rolling averages now use raw percentages (gained/total × 100). The difficulty-specific thresholds in `getLevel()` handle difficulty adjustment.

---

## End-to-End Flow

```mermaid
flowchart TD
    A["Admin Creates Assessment"] --> B["Select Sections & Subtopics"]
    B --> C["Set Difficulty & Negative Marking"]
    C --> D["Backend Selects 30 Questions"]
    D --> E["Assign to Students"]
    E --> F["Student Opens Assessment"]
    F --> G["Config Check + Biometric"]
    G --> H["Fullscreen Mode"]
    H --> I["Student Answers 30 MCQs"]
    I --> J["Submit Assessment"]
    J --> K["Calculate Score (difficulty-weighted)"]
    K --> L["Update Topic Rolling Averages"]
    L --> M["Calculate Competency Score"]
    M --> N["Determine Level via getLevel()"]
    N --> O["Store in aptitudeTopicProgress"]
    O --> P["Generate PDF Report"]
```

---

## File Reference

### 1. Assessment Creation (Admin)

#### Frontend — `AssessmentSelect.js`
**Path:** `admin-react/src/modules/Assessment/Partials/CreateAssessment/AssessmentSelect.js`

- Admin selects **assessment type** = `Aptitude`
- Configures: name, dates, sections (Quantitative/Logical/Critical), subtopics, difficulty, negative marking, proctoring
- Supports **one-time** and **scheduled** distribution

#### Backend — `Assessment.js` → `assignAptitudeAssessment()`
**Path:** `admin-node/app/models/Assessment.js` (line ~6338)

**Key steps:**
1. Validates input: entity, assessment type, aptitude types, subtopics
2. Fetches students via `getAssessmentAssignedParticipants()`
3. Classifies students: new, existing first-time aptitude, returning
4. Calls `selectAptitudeQuestionsForAssessment()` to select 30 questions
5. Creates assessment records (institute/corporate map, assessment set, assigned students)
6. Creates students in the system if they don't exist (auto-registration)

#### Question Selection — `selectAptitudeQuestionsForAssessment()`
**Path:** `admin-node/app/models/Assessment.js` (line ~7153)

**Algorithm:**
1. Maps aptitude types to `sections` table
2. Maps subtopics to `sub_sections` table (with weights)
3. Distributes 30 questions across sections based on fixed allocation (12/11/7)
4. Within each section, distributes by subtopic weight
5. For each subtopic, selects questions by the configured difficulty distribution (easy/medium/hard)
6. Avoids previously seen questions per student (`excludeQuestionIds`)
7. Randomizes selection within each pool

---

### 2. Student-Facing Frontend

**Path:** `Assessment-React/src/modules/Assessments/Partials/aptitudeassmt/`

| File | Purpose |
|------|--------|
| `index.js` | Entry point — shows assessment name, deadline, **ConfigCheck** (camera/mic), then **BiometricCheck**, Start button |
| `instruction.js` | Instructions page — general aptitude assessment instructions, fullscreen request |
| `assessment.js` | **Main assessment UI** — full-screen MCQ interface with collapsible sidebar question navigator, per-question timer, answer tracking, violation detection |
| `assessment-solution.js` | Post-assessment solution review — shows correct answers and explanations |
| `completion.js` | Results page — overall score card, difficulty analysis, per-section & per-topic breakdown, retry support with auto-polling |
| `styles.js` | Shared styled-components |

**Key behaviors in `assessment.js`:**
- **Sidebar navigation** — collapsible question list with status indicators (answered, skipped, current)
- **Per-question timing** — tracks `timeTaken` for each question
- **Anti-cheat** — fullscreen enforcement, tab-switch detection (max 3 warnings → auto-submit)
- **Question states** — answered (green), skipped (gray), current (blue), unanswered (default)
- **Markdown support** — questions can include formatted math/code via markdown rendering

**Key behaviors in `completion.js`:**
- **Auto-polling** — polls server for scores with exponential backoff (max 5 retries every few seconds)
- **Score breakdown** — shows correct/wrong/unanswered counts, gained vs total marks
- **Difficulty analysis** — separate breakdown by Easy/Medium/Hard
- **Topic analysis** — per-subtopic performance with percentage bars
- **Solution review** — navigates to `assessment-solution.js` for detailed answer review

---

### 3. Question Delivery (Student Backend)

#### `getAptitudeAssessmentQuestions()`
**Path:** `student-node/app/models/Assessment.js` (line ~3294)

**Key logic:**
1. Receives `assessment_set_id` and `assessment_assigned_id`
2. **Level-based difficulty adaptation** for institute assessments (not practice):
   - Looks up student's `AssessmentLevelOfStudent` from `aptitudeTopicProgress`
   - If level maps to a different difficulty than the assigned set → generates a **new question set** via `generateSingleStudentAssessmentSet()`
3. Fetches questions grouped by section
4. Returns `isMinusSystem` flag along with question data

#### `generateSingleStudentAssessmentSet()`
**Path:** `student-node/app/models/Assessment.js` (line ~2907)

Dynamically generates a new 30-question set at the required difficulty:
- Uses same section distribution (12/11/7)
- Applies difficulty configs per level
- Creates new `assessmentSet` and `assessmentQuestionMap` records
- Updates the student's `assessmentAssignedStudent` record to point to the new set

**Concurrency guard (set-regeneration race fix).** This runs on the re-callable
question-fetch path, so a duplicate/overlapping fetch (double-click Start, reload,
React re-invoke) could previously regenerate **twice** — both calls read the same
seed set and each created its own random set, with last-write-wins on
`assessment_set_id`. The student then answered set #1 while the assignment pointed
at set #2 (different random questions, 0 overlap). Because `student_answers` is keyed
only by `question_id` (no `set_id`), scoring read the wrong set's questions and
counted the answers as unattempted → **0 / under-counted marks** (e.g. Christ Univ:
21 fully-zeroed + partial cases like 29 answered / 3 counted). Now hardened:
- **R1:** the create+update runs under a per-attempt advisory lock
  `pg_advisory_xact_lock(42, hashtext(assessment_assigned_id))`; after acquiring it the
  code re-reads state and **reuses** the existing set if the required-difficulty set
  already exists, or the student has `submitted`, or any `student_answers` exist.
  Result: exactly one set per attempt.
  - ⚠️ **Gotcha:** `pg_advisory_xact_lock()` returns SQL type `void`. It **must** be
    invoked with `prisma.$executeRaw` (which does not deserialize a result set), **not**
    `prisma.$queryRaw`. With `$queryRaw`, Prisma 4.16.2 throws `P2010 — Failed to
    deserialize column of type 'void'`, which is the **first** statement in the
    generation transaction, so it aborts before any set is created. The whole
    `getAssessmentQuestions` call returns an error, the assignment never flips to
    `INPROGRESS`, and the student is stuck on **"Preparing your assessment…"**. This
    shipped broken on `release-v1.33-hotfix-1` (image `2026-06-08…`) and was fixed
    `2026-06-14` by switching `$queryRaw` → `$executeRaw` on that line.
- **R2:** `getAptitudeAssessmentQuestions()` skips regeneration entirely once answers
  exist for the attempt.
- **Frontend:** `Assessment-React` de-duplicates `fetchAssessmentQuestions` per
  `assessment_assigned_id` (in-flight request reuse) so duplicate fetches collapse to one.

---

### 4. Score Calculation

#### `calculateAptitudeScore()`
**Path:** `student-node/app/models/Assessment.js` (line ~11212)

**Processes each question:**
1. Looks up section/subsection mapping
2. Calculates difficulty-weighted points (+1/+2/+3)
3. Applies negative marking if enabled (−0.25/−0.50/−0.75)
4. Builds comprehensive `statistics` object with:
   - **Summary**: total questions, attempted, right, wrong, unattempted, marks by difficulty
   - **Categories** (sections): per-section totals with difficulty breakdown
   - **Topics** (subtopics): per-topic totals with difficulty breakdown and time spent

Stores result in `aptitudeScores` table via **upsert keyed on the unique
`assessment_assigned_id`** — exactly one score row per assignment. (The old
find-then-create "retake" branch could write a second row, which is why duplicate
aptitude_scores rows accumulated; cleaned up + a `UNIQUE(assessment_assigned_id)`
index now backstops it — DB-Scripts `Aptitude Set Regeneration Race Fix/002`. The
unique index must exist before the upsert code deploys, or `INSERT .. ON CONFLICT` errors.)

**Integrity guard (R4).** Before scoring, it checks that the student's real
(non-SKIPPED) answers are all contained in the assigned set. If the assigned set
contains fewer of them than another set does (set-regeneration race — disjoint OR
partial), it auto-resolves: re-points `assessment_set_id` to the set whose
`assessment_question_map` actually matches the answers (must be *strictly better* and
contain *all* of them) and re-scores. If fully disjoint and no matching set is found
it returns `integrity_mismatch` (never persists a false 0); partial-with-no-better-set
scores on the overlap and warns. This both prevents new bad scores and self-heals on
any re-score.

**Backfill endpoint.** `POST /students/assessments/aptitude/backfill-set-mismatch`
(`aptitudeBackfillHandler.backfillAptitudeSetMismatch`) recovers already-affected
assessments. Detects victims via `distinct_real_answers > scored attempted`, finds the
best-matching set, and (when `dryRun:false`) re-points + deletes the old score +
recalculates. `dryRun:true` (default) previews only; non-resolvable cases (current set
already complete) are returned as `needs_review` and left untouched. Body:
`{ dryRun?:bool=true, assessment_assigned_ids?:string[], limit?:int=200, includeRescore?:bool=false }`.
With `includeRescore:true`, rows whose set already contains all answers but whose stored score
under-counted (the duplicate-answer bug below) are re-scored in place (no re-point) → status `rescored`.

**Duplicate-answer dedup.** `student_answers` can hold multiple rows per question (re-answer /
re-submit). Scoring previously used `.find()` (first match), which could pick a `SKIPPED` duplicate and
count a genuinely-answered question as unattempted (off-by-1..3 under-count). Scoring now builds a
per-question map preferring a non-`SKIPPED` (and latest `submittedAt`) row before counting.

**Index:** `assessment.student_answers(assessment_assigned_id)` backs the per-attempt
answer lookups (scoring, guard, backfill) — see DB-Scripts `Aptitude Set Regeneration
Race Fix/001`.

**Transaction model:** Score calculation and `updateAptitudeProgression()` run inside a single Prisma `$transaction` (timeout: 30s). This is critical because aptitude scores are calculated on-the-fly after submission (not via cron), so there is **no retry mechanism** — if progression fails, the student's level won't update. The transaction ensures atomicity: either both scoring and progression succeed, or neither does.

> **Key difference from Communication:** Communication progression is `await`ed but outside a transaction. If it fails, the cron job retries the entire calculation. Aptitude has no such safety net, hence the transactional approach.

---

### 5. Level Update & Progression

#### `updateAptitudeProgression()`
**Path:** `student-node/app/models/Assessment.js` (line ~11080)

**The progression system uses `diagnosis_number` to track phase:**

| `diagnosis_number` | Phase | Description |
|---------------------|-------|-------------|
| 1 | Diagnosis #1 | First assessment — initial topic data, no level yet |
| 2 | Diagnosis #2 | Second assessment — pair complete, first level assigned |
| 3 | Post-diagnosis | All subsequent assessments |

**Phase details:**

1. **Diagnosis #1** (`diagnosis_number = 1`):
   - Creates `aptitudeTopicProgress` record with initial topic data from this assessment
   - No level assigned yet — stored as null
   - Creates ProgressionHistory with `isSecondInPair = false`

2. **Diagnosis #2** (`diagnosis_number = 2`):
   - Calculates rolling average per topic (last 2 attempts)
   - Calculates weighted **competency score** across all topics
   - Determines level via `getLevel(difficulty, competencyScore)`
   - Calculates **Aptitude NPS**: `((levelIndex × 100) + competencyScore) / 4`
   - Sets `AssessmentLevelOfStudent`, `LevelOfStudent`, and `MaxLevelOfStudent`
   - Backfills ProgressionHistory for **both** assessments (A1 and A2)

3. **Ongoing assessments** (`diagnosis_number = 3`):
   - **Assessment mode**: Uses `getNewAssessmentLevel()` — only allows upgrades (no-downgrade)
   - **Practice mode**: Uses `getLevel(assessmentDifficulty, competencyScore)` with the actual assessment difficulty — allows level changes up/down, tracks `MaxLevelOfStudent`
   - Creates ProgressionHistory with `isSecondInPair = true` (every post-diagnosis assessment completes a "pair" immediately using topic rolling averages)

**Key difference from Communication:** Aptitude uses **topic-level rolling averages** (pairs of 2 topic scores) rather than assessment-level pairs. Every post-diagnosis assessment immediately produces a level update because the rolling averages already incorporate the pair logic at the topic level.

#### Topic Rolling Average
- Keeps **last 2 scores** per topic
- Calculates raw percentage for each (gained_marks / total_marks × 100), averages them
- No difficulty multiplier applied — `getLevel()` handles difficulty via its threshold table
- Status thresholds: < 50% = weak, 50-74% = moderate, ≥ 75% = strong

#### Competency Score
- Weighted average of all topic rolling averages
- Weights come from `sub_sections.weight` table
- Formula: `Σ(topic_rolling_avg × topic_weight) / Σ(topic_weight) × 100`

**ProgressionHistory fields stored (aptitude):**

| Field | Description |
|-------|-------------|
| `assessmentAptitudeLevel` | Confirmed aptitude level |
| `assessmentAptitudeProgressScore` | NPS score |
| `aptitudeDifficulty` | Assessment difficulty (Easy/Medium/Hard) |
| `aptitudeLevelAtTime` | Student's level at the time |
| `aptitudeCompetencyScore` | Weighted competency score |
| `aptitudeFinalScore` | Individual assessment score |
| `isSecondInPair` | `true` for A2 (pair complete) |
| `isPractice` | Practice vs assessment mode |

#### `fetchAptitudeProgression()`
**Path:** `student-node/app/models/Assessment.js` (line ~276)

Replays the entire assessment history to compute progression for the **detail view** (individual student progression page):
- Fetches all submitted aptitude assessments (chronologically)
- Simulates topic-by-topic rolling averages step by step
- Compares target assessment vs previous to show deltas

> **Note:** This method is used for the individual student progression detail view only. The **dashboard list views** (TPO student lists, pie charts) read aptitude level and NPS directly from `ProgressionHistory` records for consistency and performance. See "Dashboard Data Sources" below.

---

### 6. Cron Job

Same cron job as Communication: `student-node/script/calculatePendingAssessmentCron.js`

For aptitude, `calculateAssessmentScore()` routes to `calculateAptitudeScore()` when `assessmentType === "aptitude"`.

---

### 7. PDF Report

#### `generateAptitudePDFReport()`
**Path:** `student-node/app/models/Assessment.js` (line ~7827)

- Renders HTML template via Handlebars
- Converts to PDF using Puppeteer
- Report includes:
  - Student info and assessment details
  - Overall score and proficiency level
  - Difficulty-wise breakdown (Easy/Medium/Hard)
  - Section-wise performance
  - Topic-wise detailed analysis
  - Progression comparison (if previous assessment exists)

---

### 8. Backfill API

#### `POST /assessment/backfill-aptitude-progression`
**Handler:** `assessmentHandler.backfillAptitudeProgressionHistory`
**Method:** `Assessment.backfillAptitudeProgression(batchSize)`

Recalculates all aptitude progression history for every student:
1. Finds all students with calculated aptitude assessments
2. For each student, fetches all assessments ordered by `submittedAt`
3. Separates into practice vs assessment chains
4. Replays each chain: rebuilds topicInfo, rolling averages, competency scores, levels, and NPS
5. Deletes old `ProgressionHistory` aptitude records and creates new ones
6. Updates `AptitudeTopicProgress` with final state

**Request body:** `{ "batchSize": 50 }` (optional, default 50)

Use this after fixing scoring/level bugs to recalculate all historical data.

---

### 9. Dashboard Data Sources (TpoDashBoard.js)

| Data | Source | Notes |
|------|--------|-------|
| **Aptitude NPS** | `ProgressionHistory.assessmentAptitudeProgressScore` | Scoped by `assessmentAssignedId` for per-assessment views |
| **Aptitude Level** | `ProgressionHistory.assessmentAptitudeLevel` | A2 record preferred, fallback to A1. Same source as NPS for consistency |
| **Assigned Difficulty** | `assessmentSet.difficulty` | From the specific assessment being viewed |
| **Pie Chart (Aptitude)** | `ProgressionHistory.assessmentAptitudeLevel` | Batch query per assessment, scoped by assignedId |

> **Why not `fetchAptitudeProgression` for dashboard?** That method replays history with its own independent calculation which can diverge from the stored NPS. Reading both level and NPS from the same `ProgressionHistory` record guarantees consistency.

#### Progression Query Scoping

Per-assessment views (`getStudentListForAssessment`) scope progression queries by `assessmentAssignedId` — ensuring the level shown is for that specific assessment, not the student's latest level. Total candidate views (`getStudentListForTpoDashboard`) use latest-by-email.

---

## Database Tables (Key)

| Table | Purpose |
|-------|--------|
| `sections` | Top-level categories (Quantitative Aptitude, Logical Reasoning, Critical Reasoning) |
| `sub_sections` | Subtopics within sections (with `weight` for distribution) |
| `questions` | Question bank with `difficulty` (easy/medium/hard) and `explanation` |
| `section_question_map` | Maps questions to sections/subsections |
| `assessment_set` | Generated question pack with `difficulty` level |
| `assessment_question_map` | Maps questions to assessment sets |
| `assessment_assigned_students` | Per-student assignment (tracks `isMinusSystem`, `totalTakenTime`) |
| `student_answers` | Individual question responses with `answerText` and `timeTaken` |
| `aptitude_scores` | Aggregated scores with full `statistics` JSON (sections, topics, difficulty breakdown) |
| `aptitude_topic_progress` | Per-student adaptive state: `AssessmentLevelOfStudent`, `LevelOfStudent`, `MaxLevelOfStudent`, `topicInfo` |
| `progression_history` | Historical level/NPS snapshots per assessment |

---

PDF report template: student-node\public\aptitudeReport.html

## Key Concepts

- **Diagnosis Phase** — First 2 assessments establish the student's baseline level. No level is assigned after just 1 assessment.
- **Adaptive Difficulty** — After diagnosis, the system auto-selects question difficulty based on the student's current level.
- **No Downgrades** — In assessment mode (post-diagnosis), `getNewAssessmentLevel()` prevents the student from dropping levels. Practice mode allows free level movement.
- **Rolling Average** — Per-topic proficiency uses only the last 2 assessment scores (raw percentages, no difficulty multiplier), providing a responsive measure of current ability.
- **Competency Score** — The master metric: a weighted average of all topic rolling averages (using `sub_sections.weight`), used to determine the overall level.
- **NPS (Normalized Progress Score)** — Formula: `((levelIndex × 100) + competencyScore) / 4`. Ranges: Beginner 0–25, Learner 25–50, Competent 50–75, Advanced 75–100. Level and NPS are always stored together in `ProgressionHistory` for consistency.
- **Topic Status** — Each subtopic gets a status: weak (< 50%), moderate (50–74%), strong (≥ 75%) based on rolling average.
- **Set Rotation** — Question sets exclude previously seen questions to prevent repetition.
