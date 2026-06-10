# Students Module

**Route:** `/students`
**Frontend:** `institute-react/src/modules/Students/`

## Overview

The Students module allows TPO users to manage the student database for their institute campus. It supports full CRUD operations, bulk upload, blacklisting, opt-out approvals, notifications (email, WhatsApp, in-app), and student metrics.

> **Field requirement (current):** When adding or editing a student, **only First Name and Email are mandatory**. **Last Name is optional** — the Add/Edit Student drawer (`StudentDetails`) no longer marks it with `*` or rejects an empty value (the last-name validator now allows blanks and only blocks digits when a value is given). Bulk upload (`/students/bulkcreate` in student-node) does **not** require the "Last Name" column either; rows with a blank last name are accepted and the student's `fullName` is built null-safely. The backing `student.last_name` column is nullable (`String?`).

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Orchestrates student list and data fetching |
| `Partials/StudentsInfoTable/` | Student table | Paginated table with student details |
| `Partials/AddNewStudentDrawer/` | Drawer | Form to add a new student |
| `Partials/SettingsDrawer/` | Drawer | Student settings configuration |
| `Partials/StudentsBulkUpload/` | Bulk upload | CSV-based bulk student creation |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Student CRUD

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getStudentsListData` | `/students/{instituteId}/lists` | GET | Paginated student listing with query filters |
| `getStudentsListResume` | `/students/{instituteId}/lists` | GET | Student list for resume download (returns raw data) |
| `createStudent` | `/students/{instituteId}/{courseId}` | POST | Create a new student, optionally linked to an event |
| `editStudent` | `/students/{studentId}` | PUT | Update student details |
| `deleteStudent` | `/students/{studentId}` | DELETE | Delete a single student |
| `deleteBulkStudents` | `/students/deletebulk` | DELETE | Bulk delete students by IDs |
| `getSingleStudentData` | `/students/{studentId}` | GET | Fetch individual student details |
| `bulkUploadStudents` | `/students/bulkcreate` | POST | Bulk create students from CSV |

### Student Status

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `blacklistStudent` | `/students/{studentId}/blacklist` | POST | Blacklist a student with reason |
| `activeInactivateStatus` | `/students/{studentId}/status` | POST | Toggle student active/inactive status |
| `SelectBlacklist` | `/student/corporates/blacklist` | PUT | Corporate-level blacklist |
| `SelectUnRestricted` | `/corporates/student/unRestrict` | POST | Remove restriction from student |
| `SelectOptOutlist` | `/students/approveOptedStatus` | PUT | Approve student opt-out/opt-in request |

### Notifications

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `sendNotificationEmail` | `/notification/email` | POST | Send email notification to a student |
| `sendNotificationBulkEmail` | `/notification/bulkEmail` | POST | Bulk email notification |
| `sendNotificationBulkEmailWhatsapp` | `/notification/bulkWhatsapp` | POST | Bulk WhatsApp notification |
| `sendInAppNotification` | `/users/createNotification` | POST | In-app notification |
| `reInviteStudent` | `/user/student/{id}/studentreinvitation` | POST | Re-invite a student |
| `bulkReInviteStudent` | `/user/student/{id}/bulk/studentreinvitation` | POST | Bulk re-invite students |

### Metrics & Degrees

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `studentsMetricsData` | `/students/{instituteId}/metrics` | GET | Student metrics (counts, opt-out, restricted, etc.) |
| `getDegreeData` | `/institutes/instituteCampus/{id}/courses` | GET | Degree-stream list for student assignment |
| `getNotificationCatalogues` | `/notificationCatalogue` | GET | Available notification templates |
| `getConsentDrawerList` | `/corporate/student/{id}/requestDrawer` | POST | Consent/request drawer data |

---

## State Shape

```js
{
  studentsList: {},
  singleStudentData: {},
  studentsMetrics: {},
  studentsDegreeList: [],
  notificationCatalogues: []
}
```
