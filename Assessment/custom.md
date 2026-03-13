# Custom Assessment

> Custom Assessments allow institutes and corporates to create **fully admin-defined MCQ assessments** with custom sections, questions (with image support), and per-section configuration for marks, time, and question count. Unlike other assessment types, there is no AI involvement — the admin controls the entire question bank.

---

## Overview

| Property | Value |
|---|---|
| **Assessment Type** | `Custom_Assessment` |
| **Question Format** | MCQ only (4 options, 1 correct) |
| **Image Support** | Yes — questions and options can have images (OCI Object Storage) |
| **Sections** | Admin-defined (unlimited) |
| **Scoring** | Simple correct/incorrect (no difficulty weighting, no negative marking) |
| **Domain** | Always `Universal` |

---

## End-to-End Flow

1. Admin creates custom sections and uploads MCQ questions (with optional images)
2. Admin configures assessment: selects sections, sets marks/time/numQuestions per section
3. Backend creates `customAssessmentConfig` records and selects random question subsets per section
4. Students get assigned via email — student accounts auto-created if needed
5. Student goes through ConfigCheck → BiometricCheck → Fullscreen → takes assessment
6. Assessment is section-based: each section has its own time limit and marks
7. On submit, simple MCQ scoring (correct answer = option with `optionValue = 1`)
8. Results available in "Completed Assessment" tab

---

## File Reference

### 1. Admin Backend — `customAssessment.js`
**Path:** `admin-node/app/models/customAssessment.js`

#### Key Functions

**`createSectionquestions({ entity_id, entity_name, sections })`**
- Creates custom sections in `customSection` table
- Creates questions in `question` table with `customSectionId` link
- Creates options in `questionOption` table (`optionValue: 1` = correct)
- Supports `question_image_key` and `option_image_key` for image-based questions
- All within a transaction (120s timeout)

**`addQuestionToCustomSection({ section_id, questions })`**
- Adds more questions to an existing section

**`editCustomAssessmentQuestion({ question_id, question_text, question_image_key, options, correct_opt })`**
- Edits an existing question's text, image, and options

**`deleteCustomAssessmentQuestion({ question_id })`**
- Soft-deletes a question (sets `isActive: false`)

**`getCustomSections({ entity_id })`**
- Returns all custom sections for an entity

**`getQuestionsForCustomSection({ section_id, pageNo, pageLimit })`**
- Paginated question listing for a section (with presigned image URLs)

**`assignCustomAssessment({ students, assessmentName, assessmentConfig, adminEmail, entityType, entityId, startTime, endTime, allowProctoring, companyLogoUrl })`**

Assignment flow:
1. Validates input (students, name, entityId, assessmentConfig)
2. Resolves assessment type (`Custom_Assessment`) and domain (`Universal`)
3. Builds per-section config from `assessmentConfig.customSectionConfig`:
   - `numQuestions` — how many questions from this section
   - `totalMarks` — marks for this section
   - `sectionTime` — time in minutes for this section
4. Creates `customAssessmentConfig` records in DB
5. Fetches active questions per section from `customSection.questions`
6. Picks **random subset** (`numQuestions`) from each section using `pickRandomSubset()`
7. Creates students if they don't exist via `createStudentsIfNeeded()` (auto-registration with email invites)
8. Creates `assessmentInstituteMap` or `assessmentCorporateMap`
9. Creates `assessmentSet` → `assessmentQuestionMap` (maps selected questions to set)
10. Creates `customConfigSetMap` (links config to set)
11. Creates `assessmentAssignedStudent` records with `assessmentSetId`
12. Processes students in **dynamic batches** (see Batch Size Logic below)

**`getCustomAssessmentReport({ assessmentAssignedId })`**
- Generates PDF report using Handlebars template and Puppeteer

#### Helper Functions

- `normalizeStudentsInput(arrayInput)` — handles both `[{email, ...}]` and `[[email, ...]]` formats
- `normalizeDate(value, label)` — parses ISO strings, Date objects, or epoch timestamps
- `buildSectionConfigMap(assessmentConfig)` — transforms config array into `Map<sectionId, config>`
- `chunkArray(items, size)` — splits array into chunks for batch processing
- `pickRandomSubset(items, limit)` — Fisher-Yates shuffle + slice for random selection

---

### Batch Size Logic (Dynamic)

The batch size determines how many students share the same question set. It is **dynamically calculated** as 10% of total students (minimum 1):

```js
const BATCH_SIZE = Math.max(1, Math.ceil(normalizedStudents.length * 0.10));
```

| Total Students | Batch Size | Unique Sets | Max % Sharing Same Set |
|---------------|-----------|-------------|------------------------|
| 100 | 10 | 10 | 10% |
| 50 | 5 | 10 | 10% |
| 28 | 3 | 10 (last batch has 1) | ~10.7% |
| 10 | 1 | 10 | 10% |
| 5 | 1 | 5 | 20% (minimum 1 per batch) |
| 1 | 1 | 1 | 100% |

**Key rules:**
- `Math.ceil` rounds up — ensures no more than ~10% share a set
- `Math.max(1, ...)` ensures at least 1 student per batch (no empty batches)
- Last batch may have fewer students than `BATCH_SIZE` (handled naturally by `chunkArray`)
- Each batch gets a **unique randomly-selected question set** per section

---

### Question Order Shuffling (Client-Side)

Even when students share the same question set (same batch), **question order is randomized per student** on the frontend using Fisher-Yates shuffle:

**File:** `Assessment-React/src/modules/Assessments/Partials/customassmt/assessment.js`

```js
function shuffleArray(array) {
  const shuffled = [...array]
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
  }
  return shuffled
}

const sections = useMemo(() => {
  const raw = questions?.sections || []
  return raw.map(section => ({
    ...section,
    questions: shuffleArray(section.questions || []),
  }))
}, [questions])
```

**Effect:** Questions within each section are shuffled when the assessment component mounts. Two students with the same `assessmentSetId` will see the same questions but in a **different random order**.

---

### 2. Admin Frontend — `AssessmentSelect.js`
**Path:** `admin-react/src/modules/Assessment/Partials/CreateAssessment/AssessmentSelect.js`

- Admin selects assessment type = `Custom_Assessment`
- Configures: assessment name, dates/times, section selection, per-section marks/time/numQuestions
- Supports proctoring toggle
- Same shared component used for all assessment type creation

---

### 3. Student-Facing Frontend
**Path:** `Assessment-React/src/modules/Assessments/Partials/customassmt/`

| File | Purpose |
|------|--------|
| `index.js` | Entry point — assessment name/deadline display, ConfigCheck (camera/mic), BiometricCheck, fullscreen + start |
| `instruction.js` | Instructions page with fullscreen request |
| `assessment.js` | **Main assessment UI** — fullscreen MCQ interface with collapsible sidebar, section-based navigation, per-section timer, markdown rendering, image support, tab-switch violation detection (max 3 warnings → auto-submit), **client-side question shuffle** |
| `completion.js` | Thank-you page — exits fullscreen, shows "result being processed" message, Next button reloads page |
| `styles.js` | Shared styled-components |

**Key behaviors in `assessment.js`:**
- Section-based layout — questions grouped by custom section in sidebar
- Per-section time tracking
- **Question order shuffled per student** via Fisher-Yates on component mount
- Question status indicators (answered/skipped/current/unanswered)
- Image rendering for question images and option images (presigned URLs)
- Anti-cheat: fullscreen enforcement, tab-switch detection (MAX_TAB_SWITCH_WARNINGS = 3)
- Markdown support for question text

---

### 4. Student Backend — `customAssessment.js`
**Path:** `student-node/app/models/customAssessment.js`

**`getCustomAssessmentQuestions({ assessmentAssignedId })`**

Question delivery:
1. Gets `assessmentSetId` from `assessmentAssignedStudent`
2. Gets section config from `customConfigSetMap` → `customAssessmentConfig` (section name, marks, time)
3. Gets questions from `assessmentQuestionMap` → `question` with options
4. Groups questions by `customSectionId`
5. Generates presigned URLs for question images and option images from OCI Object Storage
6. Returns structured response:
```json
{
  "sections": [
    {
      "section_id": "...",
      "section_name": "Section A",
      "total_marks": 10,
      "section_time": 15,
      "questions": [
        {
          "id": "...",
          "questionText": "...",
          "question_image_url": "...",
          "options": [
            { "id": "...", "optionText": "...", "optionValue": 0, "option_image_url": "..." }
          ]
        }
      ]
    }
  ]
}
```

---

### 5. Score Calculation

Custom assessment scoring is simpler than other assessment types:
- MCQ auto-graded: correct answer = option with `optionValue > 0`
- No difficulty weighting
- No negative marking  
- No AI involvement
- No adaptive levels or progression

Triggered by the same cron job: `student-node/script/calculatePendingAssessmentCron.js`

---

### 6. PDF Report

Report logic in `getCustomAssessmentReport()` in `admin-node/app/models/customAssessment.js` — same Handlebars + Puppeteer pipeline.

---

## Database Tables (Key)

| Table | Purpose |
|-------|--------|
| `custom_sections` | Admin-defined sections (`name`, `entityID`, `totalQuestions`) |
| `questions` | Question bank with `customSectionId`, `objectKey` (image) |
| `question_options` | Options with `optionValue` (1 = correct, 0 = wrong), `objectKey` (image) |
| `custom_assessment_config` | Per-section config: `customSectionId`, `marks`, `timeInMinutes`, `numberOfQuestions` |
| `custom_config_set_map` | Links config records to `assessmentSet` |
| `assessment_set` | Generated question pack |
| `assessment_question_map` | Maps randomly selected questions to the set |
| `assessment_assigned_students` | Per-student assignment |
| `student_answers` | Student responses with `answerText` |

---

## Key Concepts

- **Fully Admin-Controlled** — unlike other assessment types, the admin creates all questions manually. No AI generation.
- **Section-Based** — each section has independent marks, time limit, and question count. Sections are presented sequentially.
- **Random Subset** — if a section has more questions than `numQuestions`, a random subset is selected per student batch via Fisher-Yates shuffle.
- **Dynamic Batch Size** — batch size is 10% of total students (min 1). Ensures no more than ~10% of students share the exact same question set.
- **Client-Side Question Shuffle** — even within the same batch, each student sees questions in a different random order (Fisher-Yates on component mount).
- **Image Support** — questions and options can have images stored in OCI Object Storage, delivered via presigned URLs.
- **Auto-Registration** — students are automatically created if they don't exist when assigned via `createStudentsIfNeeded()`.
- **Simple Scoring** — no difficulty weighting, no negative marking, no levels, no progression tracking.
