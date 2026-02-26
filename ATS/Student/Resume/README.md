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
