# Resume Module

**Route:** `/resume`
**Frontend:** `student-react/src/modules/Resume/`

## Overview

The Resume module is the student's comprehensive profile and resume management hub. It handles fetching and updating student data, education records, skills, work experience, preferred cities, resume uploads/downloads, profile photo management, college lookups, and corporate master data. All student data mutations are synced to ElasticSearch for skill indexing.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Resume builder and profile editor |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Student Data

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getStudentData` | `/students/{studentId}` | GET (Student) | Fetch full student data. Also fetches last applied event/job details if present |
| `updateStudentData` | `/students/{studentId}` | PUT (Student) | Update student data. Syncs to ES: `student_crud_skill` and `skill_master` |
| `updateStudent` | `/students/{studentId}/updateStudent` | PUT (Student) | Lightweight student update. Clears external event data if no lastAppliedEventIds |
| `updateStudentProfile` | `/students/{studentId}/profile` | POST (Student) | Update student profile section |

### Resume Management

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getStudentResumeData` | `/students/{studentId}/resumes` | GET (Student) | Fetch student resume data |
| `upsertStudentResume` | `/students/{studentId}/resumes/batch` | POST (Student) | Batch upsert resumes |
| `resumeBulkDownload` | `/students/resume/bulkdownload` | POST (Student) | Bulk resume download (blob) |
| `resumeBulkDownloadJobRoles` | `/students/resume/bulkdownload/jobRoles` | POST (Student) | Bulk resume download scoped to a job role (`roleId` required). Per-student resume resolution reads `student_role_mapping` (`isSystemResume`/`cvUrl`) |
| `logResumeDownload` | `/students/resume/bulkdownload` | POST (Student) | Log resume download activity |

### Profile Data

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getPromotion` | `/students/{studentId}/promotion` | GET (Student) | Work-experience grouped into career-progression chains — see [Promotion grouping](#promotion-grouping-studentsstudentidpromotion) |
| `getPendingData` | `/students/{studentId}/pending-data` | GET (Student) | Fetch pending data fields |
| `getFrozenFields` | `/students/{studentId}/frozen-fields` | GET (Student) | Fetch frozen (non-editable) fields |
| `changePassword` | `/user/{userId}/password` | PATCH (Auth) | Change user password |

### Location & Master Data

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getCities` | `/search/states/cities` | GET (ES Sync) | Preferred city search |
| `getDegreeData` | `/institutes/search/degrees` | GET (Inst) | Degree list (pageLimit=500) with degreeType filter |
| `getCollege` | `/institutes/instituteCampus/{instituteId}` | GET (Inst) | Campus details for student's institute |
| `getListOfAllColleges` | `/institutes/crud/college` | GET (Inst) | Active college list with search |
| `getListOfAllCollegesCurCourse` | `/institutes/search/instituteCampuses` | GET (Inst) | Institute campus search with state/city filters |
| `getCorporateList` | `/students/crud/company` | GET (Student) | Corporate/company master list for work experience |
| `isCorporateMasterExist` | `/students/crud/company` | GET (Student) | Check if a company exists in master data |

---

## ElasticSearch Sync

After `updateStudentData`:
- `/sync/student_crud_skill` — Sync student skill data
- `/sync/skill_master` — Sync skill master index

---

## Key Features

- **Frozen fields:** Certain fields are non-editable (institution-controlled)
- **Pending data:** Tracks which profile fields need completion
- **Promotion data:** Career progression, not academic year advancement — see
  [Promotion grouping](#promotion-grouping-studentsstudentidpromotion) below
- **Profile image caching:** Stores profile image in localStorage as base64
- **ES sync on update:** Every student data mutation syncs skills to ElasticSearch
- **Resume download:** Supports PDF, DOC, DOCX with correct MIME types
- **External event tracking:** Fetches last applied event/job details for contextual display

---

## Education dates render as bare years (student-react)

Every education row — on screen and in the downloaded resume — shows **year only**
(`2027`, or `2023 - 2027` when `startedOn` is set). There are **three independent
copies** of that formatting in `student-react`, and all three must be changed together;
each one had its own `MMM YYYY` path until 2026-08-03:

| File | Surface |
|---|---|
| `src/modules/Resume/Style/EducationSection.js` (`getEducationDate`) | On-screen *My Resume → Education* |
| `src/modules/Resume/Components/ResumeDownload.js` (`startDate`/`endDate` mapping) | Client-side resume **download** |
| `src/modules/Resume/Style/ExpCandidateEducation.js` (`getEducationDate`) | react-pdf template for **experienced** candidates (via `Style/DownloadResume.js`) |

The offending pattern was a `isCurrentCourse` special case (`edu?.isCurrentCourse ? 'MMM YYYY' : 'YYYY'`,
or a dedicated `isCurrentCourse` branch), so the **currently-pursuing** row rendered as
e.g. `Jun 2026` while every completed row rendered `2026`. `currentCourse` is unshifted
into the education list with `isCurrentCourse: true` only when the student is **not** an
experienced candidate, which is why the bug only showed on the current-course row.

`src/modules/Resume/Style/Education.js` is a fourth near-identical copy but is **imported
nowhere** — dead code, left as-is.

The same fix applies to institute-react's candidate drawer
(`src/modules/Students/.../StudentDrawerContent/Partials/EducationSection/index.js`),
where the 10th/12th fallback branch was `MMM YYYY` too.

---

## Resume Resolution & PDF Generation (bulk download)

Both bulk-download handlers (`bulkResumeDownload`, `bulkResumeDownloadJobRoles` in
`student-node/app/handlers/resumeDownload.js`) resolve each student's file in this
order, then zip the results (single student streams the file directly; >5 students
upload the zip to S3 and email a link):

1. **Uploaded CV** — job-role download uses `student_role_mapping.cvUrl` when
   `isSystemResume = false` **and** `cvUrl` is non-null. The plain bulk download
   uses the default `UPLOADED` resume from `student_resumes`.
2. **Stored SYSTEM resume** — a `student_resumes` row whose `file_url.url` is set.
3. **Generate a fresh PDF** — `formatStudentData` → `formatResumeData` (`app/handlers/utils.js`)
   → `generatePDF` (renders via `@react-pdf/renderer`, uploads to S3). Hit when no
   uploaded/stored file exists, e.g. a SYSTEM resume with `file_url.url = null`.

### Gotchas
- **Non-array `skill_set`/`skills` crashed PDF generation.** `formatResumeData`
  aggregated skills with `course?.skill_set?.forEach(...)`. Optional chaining only
  guards null/undefined — resumes that store `skill_set` as a **string** (e.g. `""`,
  the default for courses with no skills, since `updateSkillSet` skips falsy values
  and never coerces `""` → `[]`) made `.forEach` throw
  `"... is not a function"` → the whole request 500'd with
  `{"message":"Something went wrong"}`. Fixed by iterating only when the value is
  actually an array (`eachOf`/`asArray` helpers), applied to every `skill_set`/`skills`
  loop and to the render blocks (`workExperience`/`internships`/`projects`/`courses`/`education`).
  This is **data-shape dependent** — only resumes that fall into the generate-PDF
  branch *and* carry a non-array resume sub-field were affected.
- **`null` *entries inside* a skills array are a separate, still-live data defect.**
  `student.current_course.skills` can be `[null]` (ERP import writes it), which is a
  perfectly good array — so the `asArray` guards above pass — but any renderer that
  reads `skill.name` unguarded then throws. This white-screened the corporate candidate
  drawers and the corporate resume PDFs; fixed frontend-side 2026-07-30 with
  `getNamedSkills()`, see `ATS/Corporate/README.md`. The write path is unfixed, so
  **assume skills arrays can contain nulls** in any new consumer.
- **No-resume case** now returns a clean `422 "No resume available for the selected
  student"` for single-student requests instead of a noisy 500, matching the existing
  guard in `bulkResumeDownload`.

---

## Promotion grouping (`/students/{studentId}/promotion`)

`getStudentPromotion` (`student-node/app/handlers/common.js`) reads the resume's
`work_experience` JSON and groups it into **career progression chains** — consecutive
roles at the same employer collapse into one group so the UI can render them as a
single promotion track. Despite the name it has nothing to do with academic year
advancement.

The grouping lives in `student-node/app/helpers/promotionSorting.js` (extracted from
`app/helpers/utils.js` on 2026-07-30 so it is unit testable — `utils.js` requires the
generated Prisma clients and cannot be loaded outside a built container;
`utils.promotionSorting` still re-exports it). Unit tests:
`student-node/test/promotionSorting.spec.js`.

Shape: entries are sorted `isCurrentlyWorking` first, then newest `ended_in`, then
newest `started_in`; the response is an **array of arrays**, one inner array per group.

### Gotchas

- **Resumes with no employer fields 500'd.** `GET /students/{id}/promotion` returned
  `500 "Cannot read properties of undefined (reading 'split')"` for any student whose
  work-experience entries carried no `industry` / `corporateId` (the common shape for
  self-entered experience — e.g. PROD student `7ab6cba0-609c-4d4f-817d-9f159fe24ee4`
  with a single A.T.E Group row). The first entry (`i = 0`) has no predecessor, so
  `lastIndustry`/`lastCorporateId` were `undefined`; when the entry itself also lacked
  them, both loose comparisons were false, so instead of opening a new group the loop
  fell through to the continuation check and called `.split()` on the non-existent
  previous entry. Fixed 2026-07-30: `i = 0` always opens a new group, and
  `checkContinuation` returns `Infinity` for missing/unparseable dates rather than
  throwing. The same guard covers `isCurrentlyWorking` entries, which carry no
  `ended_in`.
- **The gap check never splits a group.** `checkContinuation` is called as
  `(workExp[i].started_in, workExp[i-1].ended_in)`, but entries are sorted
  newest-first, so `workExp[i]` is the *older* role. The difference is therefore
  always negative and always `<= 1`, and same-employer roles chain regardless of how
  many years separate them. Pre-existing and **deliberately left alone** by the 500
  fix (correcting it changes promotion output for every student); pinned by a test so
  any future change is intentional.
- **Differing-organization `OTHERS` entries are dropped.** Two same-industry entries
  both using the `OTHERS` placeholder `corporateId` but with different `organization`
  names match no branch in the grouping loop, so the second one is silently omitted
  from the response. Also pre-existing, also pinned by a test; the one-line fix is
  noted as a `ponytail:` comment in `promotionSorting.js`.
