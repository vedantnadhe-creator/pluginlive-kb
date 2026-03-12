# Institute Assessment (TPO View)

> Documents the institute-side assessment management — how TPOs view assessments, student lists, and scores. Covers `institute-node/StudentListInfo.js` (assessment schedules) and `student-node/TpoDashBoard.js` (student list API).

---

## Architecture

Institute assessments use a **two-API architecture**:

| Assessment Types | Backend API | Frontend Action |
|-----------------|-------------|------------------|
| Communication, Aptitude | student-node `specific-assessment-student-list` | `fetchSpecificAssessmentStudentListAction` |
| Role_Based, Custom, Behavior, AI_Interview, etc. | admin-node `getAssessmentDetails` | `fetchAssessmentDetailsAction` |

This split exists because Communication and Aptitude are "standard" types with schedules, progression tracking, and CEFR/aptitude levels. Other types are standalone assignments without scheduling infrastructure.

---

## Institute-Node: `StudentListInfo.js`

**File:** `institute-node/app/models/StudentListInfo.js`

### `getSchedulesInfo(instituteId, passingYear, ...)`

Fetches all assessment schedules and standalone assessments for the institute dashboard.

**Key logic in Step 4 SQL query:**
```sql
WHERE aim.schedule_id = ANY($1::uuid[])           -- scheduled assessments
   OR (aim.institute_id = $2 AND aim.is_one_time = true)  -- one-time assessments
   OR (aim.institute_id = $2 AND aim.schedule_id IS NULL
       AND (aim.is_one_time IS NULL OR aim.is_one_time = false)
       AND LOWER(at.type_name) NOT IN ('communication', 'aptitude'))  -- standalone other types
```

**Assessment type classification:**
- **Scheduled**: Communication/Aptitude with `schedule_id` set — belong to assessment schedules
- **One-time**: Any type with `is_one_time = true` — shown individually
- **Diagnosis**: Communication/Aptitude with `schedule_id = NULL` and `is_one_time = false` — these are auto-created diagnosis assessments that belong to schedules
- **Standalone other types**: Role_Based, Custom, Behavior, AI_Interview, etc. with `schedule_id = NULL` and `is_one_time = false` — these are NOT diagnosis; they never have schedules. Shown as individual rows.

### Diagnosis Count Query (Step 5 — `diagnosisCompleted` / `totalDiagnosisTaken`)

Counts how many students completed diagnosis (submitted >= 2 assessments of the same type for the institute).

**Critical:** The query MUST use `INNER JOIN` on `assessment_institute_map` and filter by `aim.institute_id` to prevent corporate assessments from leaking into the count. Corporate assessments have `assessment_institute_map_id = NULL`, so a `LEFT JOIN` with `aim.is_one_time IS NULL` would match them (NULL evaluates to true).

```sql
SELECT aas.primary_email, COUNT(*) as submitted_count
FROM assessment.assessment_assigned_students aas
JOIN assessment.assessment_sets aset ON aas.assessment_set_id = aset.assessment_set_id
JOIN assessment.assessment_institute_map aim ON aas.assessment_institute_map_id = aim.assessment_institute_map_id
WHERE aas.primary_email = ANY($1::text[])
  AND aset.assessment_type_id = $2::uuid
  AND aas.submitted = true
  AND aim.institute_id = $3::text
  AND (aim.is_one_time IS NULL OR aim.is_one_time = false)
GROUP BY aas.primary_email
```

**Bug fixed (2026-03-12):** Previously used `LEFT JOIN` without `institute_id` filter — corporate assessment submissions were counted toward institute diagnosis totals.

### TPO Student List: Communication/Aptitude Taken/Sent

**File:** `student-node/app/models/TpoDashBoard.js` — `getStudentListForTpoDashboard()`

The per-student communication/aptitude taken/sent counts shown in the "Total Candidates" list are correctly isolated. All four queries (commSent, commTaken, aptSent, aptTaken) filter by:
```javascript
assessmentInstituteMap: { instituteId: instituteId, isOneTime: false }
```
This ensures corporate assessments are excluded.

### `getCorporateAssessmentStudents(instituteId, assessmentMapId, ...)`

Fetches student list for a specific assessment (used by corporate view). Includes scores for all types.

---

## Student-Node: `TpoDashBoard.js`

**File:** `student-node/app/models/TpoDashBoard.js`

### `getStudentListForAssessment()` (TPO method, lines ~1014-2235)

Returns student list with scores for Communication and Aptitude assessments. Also includes scores for other types when accessed via institute view.

**Prisma includes for score fetching:**
```javascript
behaviorScores: true,
roleBasedScores: { include: { section: { select: { sectionName: true } } } },
customAssessmentScores: true
```

**Score calculation by type:**

| Type | Score Source | Total Score | Section Scores |
|------|------------|-------------|----------------|
| Communication | `communicationScores` | Percentage from sections | reading, listening, speaking, writing |
| Aptitude | `aptitudeScores` | Percentage from sections | critical, quantitative, logical |
| Behavior | `behaviorScores[0].totalScores` | Average of all scores | Parsed from JSON `totalScores` field |
| Role_Based | `roleBasedScores[]` | Average of section scores | Dynamic from `section.sectionName` (e.g., mcq, subjective, video) |
| Custom | `customAssessmentScores[0]` | `percentage` field | `gainedMarks`, `totalMarks`, `percentage`, `sectionWiseStats` |

**Response includes:** `assessmentType` field (`mapData.assessmentType.typeName`) for frontend type detection.

### `getStudentListForCorporateAssessment()` (Corporate method, lines ~2237-2658)

Same as TPO method but for corporate assessments. Already had all score types from the beginning.

---

## Frontend: Institute-React

### Assessment Details (`AssessmentDetails/index.js`)

- Uses `isStandardType = ['communication', 'aptitude'].includes(assessmentTypeLower)` to guard:
  - Charts/graphs: only shown for standard types
  - Assigned difficulty column: only shown for standard types
  - Progression level column: only shown for standard types
  - Page heading: standard types show `{scheduleName}-schedule-{scheduleNumber}`, non-standard types show assessment name directly

### CandidateList (`CandidateList/index.js`)

- Dynamic column extraction for Role_Based/Behavior: scans all student rows for keys in `sectionScores` OR `roleBasedScores`
- Total Score column: `r.totalScore ?? r.totalAvgScore ?? r.roleBasedScores?.overallScore ?? r.customAssessmentScores?.percentage`
- Assigned Difficulty and Progression Level hidden for non-standard types

### StudentReport (`StudentReport/index.js`)

- Renders type-specific score cards:
  - `renderRoleBasedScoreCards()`: shows MCQ, Subjective, Video scores from `roleBasedScores` or `sectionScores`
  - `renderCustomAssessmentScoreCards()`: shows gained/total marks and percentage
  - `renderBehaviorScoreCards()`: existing behavior score display
- Report download routes to type-specific PDF generator

---

## Data Format Differences Between APIs

The two APIs return scores in different formats:

| Field | student-node (Communication/Aptitude) | admin-node (Other types) |
|-------|---------------------------------------|-------------------------|
| Section scores | `sectionScores: { reading: 75, ... }` | `roleBasedScores: { mcqScore: 80, ... }` |
| Total score | `totalScore: 75` | `roleBasedScores.overallScore: 80` |
| Custom scores | N/A | `customAssessmentScores: { percentage, gainedMarks, totalMarks }` |

Frontend CandidateList handles both formats by checking multiple score sources.

---

## PDF Report Performance

**Optimization:** All PDF report methods use a shared Puppeteer browser pool (`getSharedBrowser()` in `student-node/app/models/Assessment.js`) instead of launching a new Chromium instance per report. This significantly reduces PDF generation time for concurrent requests.

```javascript
// Singleton browser pool — reuses one Chromium instance
const browser = await getSharedBrowser();
const page = await browser.newPage();
try {
  // ... generate PDF
} finally {
  await page.close(); // close page, NOT browser
}
```
