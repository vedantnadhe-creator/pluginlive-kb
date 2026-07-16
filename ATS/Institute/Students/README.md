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
| `Partials/StudentsBulkUpload/` | Bulk upload | ERP-file bulk student creation (normalization-driven, see below) |

---

## ERP Bulk Upload (institute-side, normalization-driven)

**Status:** live on DEV + UAT (2026-07-08), branch `feat/institute-erp-bulk-upload` across 5 repos. PROD pending.

The old degree/department-dropdown CSV bulk-upload flow has been **replaced** (no toggle) by an ERP-file flow: the TPO uploads their college ERP export **as-is** (any columns, no fixed template) and the `form-data-normalization` engine interprets it.

```
institute-react StudentsBulkUpload drawers (two-step UX)
   1. **Bulk Upload** drawer (title "Bulk Upload")
      → upload .xlsx to S3
      → POST /institutes/instituteCampus/:instituteCampusId/erp-upload   (institute-node)
           forwards { excelLink, instituteCampusId } to form-data-normalization,
           tagging rows source="institute_erp" + institute_campus_id
   2. **Upload Status** drawer opens automatically after a successful submit
      → campus-scoped "Recent uploads" table via
         GET /institutes/instituteCampus/:id/erp-upload/batches
         (+ /batches/:sheetId/rows), proxied through institute-node for tenant isolation

   → form-data-normalization worker (institute_erp branch, isolated from the
     existing corporate/Drive normalization path by the `source` column)
        resolves degree/stream/department scoped to the campus's own courses
        (campus already known → no college-resolution step, unlike corporate)
   → student-node POST /students/create-full  (institute journey)
        upsert by email (existing student with same email → overwritten with
        the new normalized payload), instituteCampusId stamped on every row
        (no hardcoding — resolved from the upload's campus context)
        canonical-or-NULL guarantee: unmapped enums/fields are stored NULL,
        never the raw ERP string, so the student's later profile-update API
        (which has strict validation) is never blocked by bad ERP data
   → user-management-node createUser (sendTempPassword) → welcome email with
     login email + auto-generated temp password
```

- **UI labels:** no "ERP" wording shown to the user; the feature is simply "Bulk Upload" with an "Upload File" section.
- **Status screen:** "Recent uploads" table lives in a separate **Upload Status** drawer. Two ways to open it:
  1. It opens automatically after a file is queued.
  2. A dedicated **"Upload Status"** button on the Manage Students top header opens it anytime.
- **Navigation:** from the status drawer, **"Upload new file"** returns to the upload drawer.
- **Match key:** email (mandatory per row — the only true minimum column; rows without a detectable email are skipped/failed).
- **Status screen columns:** the "Recent uploads" table shows `File | Uploaded | Total | Done | Pending | Failed | Skipped`. **Skipped** (default antd tag, plain `0` tag when zero) surfaces rows the worker marked `skipped` — currently this is the duplicate-candidate branch. Backend has always returned `skipped_count` from `candidate_service.get_raw_candidates`; the column was added 2026-07-16 so an upload that totals `500 / Done 485 / Failed 0` but shows 15 missing is now visible as `Skipped 15` instead of a silent gap. The File column is width-capped (200px) with an ellipsis + Tooltip on hover — full S3 key visible on hover.
- **Known gotcha — cross-source dedupe:** the worker's `is_candidate_duplicate` check matches on `email` against the `candidates` master scoped only by `role_id` (NULL passes through). Institute-ERP rows carry no role, so a campus student whose email already exists as a **corporate** candidate (or any other source) will be silently marked `skipped` even though no duplicate exists within the campus. Visible in the new Skipped column; fix tracked separately (campus/source-scoped dedupe).
- **Re-upload policy:** overwrite with the new normalized payload (ERP is source of truth).
- **Resume sub-entry ids:** the normalized payload's `resume.{workExperience,projects,courses,internships,awards}` items arrive without a per-item `id`. student-node's `sanitizeResumeForPersist` (shared by the create-full create + update paths) backfills a **`uuidv4()`** id on any item missing one — matching the format the regular resume-save handlers persist (they assign `uuidv4()` when `!item.id`), so ERP-created resume entries are addressable/editable like UI-created ones. Fill-only-when-missing, so payloads that already carry an id are untouched. (Note: the student-react resume drawers set a transient 8-char base36 id in local state, but the persisted id is always a UUID.) Existing pre-fix ERP rows are not retroactively backfilled.
- **DB migration (`candidate_ingestion_schema.candidates_raw_data`):** additive, `source TEXT NOT NULL DEFAULT 'corporate'` + `institute_campus_id TEXT` + index `ix_candidates_raw_data_source_campus`. Applied on the shared DEV/UAT Postgres (`140.238.245.202:5441/uat_pluginlive` — DEV's `form-data-normalization` points at this same DB); all pre-existing rows default to `source='corporate'`, so the existing corporate/Drive normalization flow is untouched.
- **New env vars (institute-node):** `NORMALIZATION_BE_BASE_URL`, `NORMALIZATION_API_KEY` (shared secret, X-API-Key header to form-data-normalization's ERP endpoints).
- **New form-data-normalization endpoints:** `POST /api/institute-erp/ingest`, `GET /api/institute-erp/batches`, `GET /api/institute-erp/batches/{sheet_id}/rows`.

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
