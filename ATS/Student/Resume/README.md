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
| `getPromotion` | `/students/{studentId}/promotion` | GET (Student) | Fetch promotion data |
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
- **Promotion data:** Academic promotion/year advancement tracking
- **Profile image caching:** Stores profile image in localStorage as base64
- **ES sync on update:** Every student data mutation syncs skills to ElasticSearch
- **Resume download:** Supports PDF, DOC, DOCX with correct MIME types
- **External event tracking:** Fetches last applied event/job details for contextual display

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
- **No-resume case** now returns a clean `422 "No resume available for the selected
  student"` for single-student requests instead of a noisy 500, matching the existing
  guard in `bulkResumeDownload`.
