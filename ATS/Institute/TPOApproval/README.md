# TPO Approval Module

**Routes:**
- `/tpoApproval` — Main TPO approval settings & dashboard
- `/tpoApproval/approval-listing` — Profile approval listing
- `/tpoApproval/student-resume/:studentId` — Student resume review

**Frontend:** `institute-react/src/modules/TPOApproval/`

## Overview

The TPO Approval module manages the student profile approval workflow. When enabled, students must get TPO approval before their profile changes are applied. The module provides field-level approval configuration (which fields require approval, which get frozen after verification), approval listings with search/sort/filter, individual student review with approve/reject actions, and student resume management.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `index.js` | Main page | TPO approval settings toggle and configuration |
| `Components/index.js` | Component hub | Shared components |
| `Components/ApprovalListing/` | Listing page | Paginated list of students with pending approvals |
| `Components/FilterDiv/` | Filter bar | Search, sort, year of passing, course filters |
| `Components/StudentResume/` | Resume review | Student resume view with approve/reject actions |
| `Uploader.js` | File upload | Document upload component |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Approval CRUD

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `approveApprovalRequest` | `/approval-requests/{requestId}/approve` | PUT | Approve a single profile change request |
| `rejectApprovalRequest` | `/approval-requests/{requestId}/reject` | PUT | Reject a request with reason payload |
| `bulkApproveApprovalRequests` | `/approval-requests/bulk-approve` | PUT | Bulk approve multiple requests |

### Approval Listing & Data

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getProfileApprovalListing` | `/institutes/{campusId}/profile-approval-listing` | POST | Paginated listing with search, sort, yearOfPassing, courses filters |
| `getApprovalRequests` | `/students/{studentId}/approval-requests?status=PENDING` | GET | Pending approval requests for a student |
| `getPendingDataByStudentId` | `/students/{studentId}/approval-requests?status=PENDING` | GET | Pending data for student detail view |
| `getStudentDataById` | `/students/{studentId}` | GET | Full student data for review |

### Filters

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getYearOfPassingFilter` | `/institutes/{campusId}/profile-approval-listing/year-of-passing` | GET | Year of passing filter options |
| `getDegreeHierarchyFilter` | `/institutes/{campusId}/profile-approval-listing/degree-hierarchy` | GET | Degree hierarchy for course filtering |

### TPO Approval Configuration

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getTPOApprovalConfig` | `/institutes/{campusId}/tpo-approval-config` | GET | Get current field-level approval configuration |
| `updateTPOApprovalConfig` | `/institutes/{campusId}/tpo-approval-config` | PUT | Save field-level approval settings |
| `toggleTPOApproval` | `/institutes/{campusId}/toggle-tpo-approval` | PUT | Enable/disable profile approval system |

### Student Data & Resume

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `updateStudentData` | `/students/{studentId}` | PUT | Update student data after approval |
| `getStudentResumeData` | `/students/{studentId}/resumes` | GET | Get student resume data |
| `upsertStudentResume` | `/students/{studentId}/resumes/batch` | POST | Create/update student resumes in batch |

### Field Mapping

`buildTPOApprovalPayload(values)` maps UI field keys to API field keys for approval configuration. Covers:
- **Personal:** CV, name, DOB, gender, email, phone
- **Address:** Permanent and current address fields
- **Education:** 10th, 12th, other education, pursuing course details
- **Experience:** Projects, internships, work experience
- **Certifications & Extracurricular**

Each field has two flags:
- `requiresApproval` — Changes need TPO approval
- `freezeAfterVerification` — Field is locked after verified

---

## Key Features

- **Field-level granularity:** Each profile field can independently require approval
- **Freeze after verification:** Lock fields once approved to prevent re-editing
- **Bulk approve:** Approve multiple pending requests at once
- **Student resume management:** View and edit resumes during approval flow
- **Cascading filters:** Year of passing, degree hierarchy for listing
