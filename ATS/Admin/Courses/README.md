# Courses (Course Mapping) Module

**Route:** `/coursemapping`
**Frontend:** `admin-react/src/modules/Courses/`

## Overview

The Courses module manages the global degree-stream-specialisation mapping across the platform. Admins can add, edit, delete, and toggle course status for specific institute campuses. It also manages the system-level CRUD for degree/department mappings (used in SystemConfig context). All mutations are synced to ElasticSearch.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Course mapping management page |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Course CRUD (Institute-Campus Level)

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getCoursesList` | `/institutes/instituteCampus/{campusId}/courses` or `/institutes/crud/degree/dept` (systemConfig mode) | GET (ES/Inst) | Paginated course list with degree, department, domain, specialisation, skill, status, duration, examType filters |
| `AddCourses` | `/institutes/instituteCampus/{campusId}/course` | POST (Inst) | Add course to campus. Syncs to ES `institute_campus_cources` |
| `EditCourses` | `/institutes/instituteCampus/{campusId}/course/{id}` | PUT (Inst) | Edit course. Syncs to ES `institute_campus_cources` |
| `DeleteCourses` | `/institutes/instituteCampus/{campusId}/course/{id}` | DELETE (Inst) | Delete course. Syncs ES deletion via `del_index_institute_campus_cources`. Has 3s delay after sync |
| `ActiveIsCourses` | `/institutes/course/{id}/status` | PATCH (Inst) | Toggle course active/inactive. Syncs to ES |
| `AddMultiCourses` | `/institutes/instituteCampus/{campusId}/courses` | POST (Inst) | Bulk add courses. Syncs to ES. Handles duplicate detection |
| `DeleteSpecialization` | `/institutes/instituteCampus/{campusId}/course/{courseId}/specialisation/{id}` | DELETE (Inst) | Delete specialisation from course. Syncs to ES |

### System Config Level CRUD

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `AddCoursesInSysConfig` | `/institutes/crud/degree/dept` | POST (Inst) | Add degree/department at system level. Syncs to ES `crud_degree_department` |
| `EditCoursesInSysConfig` | `/institutes/crud/degree/dept/{id}` | PUT (Inst) | Edit system-level degree/department. Syncs to ES |
| `EditCoursesStatusInSysConfig` | `/institutes/crud/degree/dept/status/{id}` | PUT (Inst) | Toggle status at system level. Syncs to ES |

### Supporting Data

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getDegreeData` | `/institutes/degree` | GET (Inst) | Degree list with search, degreeType, domainId (pageLimit=500) |
| `getDegreeDataValue` | `/institutes/instituteCampus/{campusId}/courses` | GET (Inst) | Degree-stream tree for a campus (pageLimit=100). Transforms into nested structure |
| `getSkillList` | `/students/search/skills` | GET (Student) | Skill list for course skill mapping |
| `getSkill` | `/students/search/skills` | GET (Student) | Skill search (pageLimit=50) |

---

## ElasticSearch Sync

| Trigger | ES Sync Endpoint | Purpose |
|---------|-----------------|---------|
| Add/Edit/Status campus course | `/sync/institute_campus_cources` | Sync campus-level course changes |
| Delete campus course | `/sync/del_index_institute_campus_cources` | Delete from ES index |
| Add/Edit/Status system course | `/sync/crud_degree_department` | Sync system-level degree/dept changes |

---

## Key Features

- **Dual context:** Campus-specific courses vs system-level degree/department CRUD
- **Nested degree structure:** Degree → Stream → Specialisation hierarchy
- **Bulk upload:** Add multiple courses at once with duplicate detection
- **ElasticSearch sync:** Every mutation syncs to corresponding ES index
- **Post-delete delay:** 3-second delay after ES sync on deletion for index consistency
- **Comprehensive filters:** Degree, department, domain, specialisation, skill, status, duration, examType
