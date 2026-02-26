# Courses Module

**Route:** `/courses`
**Frontend:** `institute-react/src/modules/Courses/`

## Overview

The Courses module manages the degree-stream-specialisation mapping for an institute campus. TPO users can add, edit, delete, activate/deactivate courses, manage specialisations, perform bulk operations, and search degree data. All changes are synced to ElasticSearch for search consistency.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Course listing and data orchestration |
| `Partials/CoursesTable/` | Course table | Paginated course listing |
| `Partials/CoursesStatus/` | Status cards | Course metrics and status overview |
| `Partials/CourseFilter/` | Filter panel | Degree, skill, duration, exam type, domain, specialisation filters |
| `Partials/AddCourseDrawer/` | Drawer | Add/edit course form |
| `Partials/StudentFilter/` | Student filter | Student-specific filter within courses |
| `Partials/StudentsBulkUpload/` | Bulk upload | CSV-based student bulk upload for courses |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Course CRUD

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getCoursesList` | `/institutes/instituteCampus/{id}/courses` | GET | Paginated course listing with filters (search, duration, examType, degree, skills, status, domain, specialisation) |
| `AddCourses` | `/institutes/instituteCampus/{id}/course` | POST | Add a single course (degree-stream mapping) |
| `AddMultiCourses` | `/institutes/instituteCampus/{id}/courses` | POST | Add multiple courses at once |
| `EditCourses` | `/institutes/instituteCampus/{id}/course/{courseId}` | PUT | Edit course details, handles mapped specialisation warnings |
| `DeleteCourses` | `/institutes/instituteCampus/{id}/course/{courseId}` | DELETE | Delete a course, with ES index cleanup |
| `DeleteSpecialization` | `/institutes/instituteCampus/{id}/course/{courseId}` | DELETE | Delete a specialisation mapping |
| `ActiveIsCourses` | `/institutes/course/{id}/status` | PATCH | Toggle course active/inactive status |

### Degree & Skill Data

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getDegreeData` | `/institutes/search/degreeStreams` | GET | Search degree-stream data with filters (degreeType, domain, mappedSpecialisation) |
| `getSkillList` | `/students/skills/list` | GET | Paginated skill list for course tagging |
| `getSkill` | `/students/skills/list` | GET | Skill search with keyword |
| `dropDownValues` | `/institutes/{url}` | GET | Generic dropdown data fetcher |

### ElasticSearch Sync

All course mutations trigger ES sync operations:

| Operation | ES Endpoint | Purpose |
|-----------|-------------|---------|
| Add/Edit/Status change | `/sync/institute_campus_cources` | Sync course data to ES index |
| Delete | `/sync/del_index_institute_campus_cources` | Remove course from ES index |

**Note:** A 3-second delay (`delay(3000)`) is applied after delete operations before re-syncing to ensure index consistency.

---

## State Shape

```js
{
  coursesList: {},
  degreeList: [],
  listOfSkill: {}
}
```

---

## Key Features

- **Degree-stream mapping:** Courses represent degree + stream + specialisation combinations
- **ElasticSearch sync:** Every mutation syncs to `institute_campus_cources` ES index
- **Duplicate detection:** `degreeStreamMapId isAlready Exists` error handling
- **Multi-course add:** Batch create multiple courses in one request
- **Mapped name warnings:** Edit warns if specialisations are assigned to candidates
- **Filters:** search, duration, examType, degree, skills, status, domain, specialisation
- **Pagination:** `pageLimit=10`, `pageNo` (0-indexed)
