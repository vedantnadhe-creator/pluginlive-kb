# Job Roles Module

**Route:** `/jobRoles`
**Frontend:** `institute-react/src/modules/JobRoles/`

## Overview

The Job Roles module is the primary interface for TPO users to manage and view job roles posted by corporates for their institute. It supports listing, filtering, detailed view, candidate export, role duplication, archiving, and eligibility criteria management via ElasticSearch.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Orchestrates job roles listing |
| `PageHeader/` | Header section | Title, filters, transfer, and action buttons |
| `PageHeader/JobRoleFilter/` | Filter panel | Status, role, schedule, domain, degree, department filters |
| `PageHeader/Components/` | Shared components | Reusable header sub-components |
| `PageHeader/Transfer.js` | Transfer | Student transfer functionality |
| `NewJobRole/` | Create/Edit | New job role creation flow |
| `NewJobRole/CompanyCard/` | Company info | Corporate company card display |
| `NewJobRole/CompanyDetails/` | Company details | Detailed corporate information |
| `NewJobRole/RolesForm/` | Role form | Job role creation form |
| `CustomDateRange.js` | Date picker | Custom date range selector |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Job Role Listing

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getJobRoleList` | `/corporates/instiuteCampus/{id}/jobs` | POST | Paginated job role listing with filters |
| `getCorporateData` | `/corporates/{corpId}` | GET | Corporate details for a role |
| `getInstituteData` | `/corporate/institute/{campusId}/company/{companyId}` | GET | Institute-company relationship data |

### Filters

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getStatusFilter` | `/corporates/filterStatus/instituteCampus/{id}/jobs` | GET | Available status filter options |
| `getRoleFilter` | `/corporates/filterRole/instituteCampus/{id}/jobs` | GET | Available role filter options |
| `getScheduleFilter` | `/corporates/filterEvaluation/instituteCampus/{id}/jobs` | GET | Evaluation schedule filter options |
| `getDomainList` | `/institutes/{campusId}/domain` | GET | Domain list for eligibility filters |
| `getDegreeList` | `/institutes/{campusId}/degree` | GET | Degree list filtered by domain |
| `getDepartmentList` | `/institutes/{campusId}/streams` | POST | Department/stream list |
| `getYear` | `/students/institutes/{id}/yearOfPassing` | GET | Year-of-passing list |

### Eligibility & ElasticSearch

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getEligibilityCriteriaQualification` | `/search/degrees/streams/specialisations` | POST | ElasticSearch-based qualification lookup for eligibility criteria |

### Export & Actions

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `exportCandidate` | `/students/role/{roleId}/instituteCampus/{id}/candidate/{type}/export` | PUT | Export candidates (CSV/Google Sheets) |
| `getExportFiledData` | `/students/institutes/heading/export` | GET | Available export field headings |
| `exportCSV` | `/corporates/instituteCampus/{id}/export/{type}` | GET | Export job roles data |
| `duplicateRole` | `/corporates/{corpId}/jobs/{jobId}/duplicate` | POST | Duplicate an existing job role |
| `archiveJobRole` | `/corporates/instiuteCampus/{id}/jobs/{jobId}/archive` | PATCH | Archive an institute-published role |
| `unarchiveJobRole` | `/corporates/instiuteCampus/{id}/jobs/{jobId}/unarchive` | PATCH | Restore an archived institute-published role |

---

## Archive / Restore (institute-published roles)

Mirrors the corporate RolePage archive flow, but scoped to **institute-published roles only** (`role_published_by === 'INSTITUTE'`). Institute-created roles have **no `corporateId`** (the corporate archive endpoint `/corporates/{corporateId}/jobs/{jobId}/archive` cannot be used for them), so dedicated institute endpoints keyed by `instituteCampusId` + `jobId` were added in **corporate-node** (`getRolesForCampus` model + `archiveInstituteJobRole`/`unarchiveInstituteJobRole` handlers).

- **Storage:** reuses the **global** `job_roles.is_archived` / `archived_at` / `archived_by` columns (same column as corporate archive — no new column/table).
- **List behaviour:** `getJobRoleList` (`POST /corporates/instiuteCampus/{id}/jobs`) accepts an `archived` flag — omitted/`false` hides archived rows (default), `true` returns only archived, `all` returns both. The list also returns `isArchived` and a derived `canArchive` per role.
- **`canArchive` rule:** `isArchived === false && appliedCandidates === 0` — a role with applied students (`is_applied ∈ {1,-1}`) cannot be archived (button disabled with tooltip "Can't archive — students have already applied").
- **UI:** an **Archive** tab (pseudo-category `ARCHIVED`) appended to the job-category toggle; per-row archive icon (and restore icon when archived) shown only on INSTITUTE-published roles, with antd confirm dialogs identical to corporate. Files: `PageHeader/DemoData/TableData.js`, `PageHeader/index.js`, `components/icons/ArchiveIcon.js`.
- **Scope caveat:** because the flag is global on `job_roles`, archiving is intentionally restricted to institute-published roles to avoid hiding a corporate's role from the corporate / other institutes.

---

## Role Float Notifications (publish / update)

When a TPO publishes or updates a role, `NewJobRole/RolesForm/index.js` → `notificationTrigger()` fans out to the candidates returned by `getInEligibleCandidates(roleId)` (`roleReceivingCandidates`) across three channels:

| Channel | Endpoint | Notes |
|---------|----------|-------|
| Email | `POST /notification/bulkEmail` (auth service) | via `sendNotificationBulkEmail` in `modules/Students/actions.js` |
| In-app | `sendInAppNotification` | tagged `Role`, deep-links to the role |
| WhatsApp | `POST /notification/bulkWhatsapp` | templates `tpo_application_create` / `tpo_application_updated` |

Ineligible candidates receive a parallel email + `tpo_role_update_ineligible` WhatsApp pair from the same function.

### Email is sent in batches of 50

The email body is rendered per recipient with `ReactDOMServer.renderToString` (~7KB each), so a role floated to a few hundred students builds a very large array. A real 309-student float produced a single **2.25MB** request, which is rejected with **413** at *two* independent 1MB ceilings:

- **nginx** `client_max_body_size` — defaults to 1MB, and `sites-enabled/auth-node.conf` sets no override (unlike `admin-node.conf` / `fast-api.conf`, which set `50M`). This layer rejects first, returning nginx HTML rather than a JSON error.
- **Fastify** `bodyLimit` — defaults to 1MB; `user-management-node/index.js` sets no override. Returns `FST_ERR_CTP_BODY_TOO_LARGE`.

Because `sendNotificationBulkEmail` swallows errors, this failed **silently**: no student received the mail and the UI still reported success.

`sendNotificationBulkEmail` now chunks the array into `BULK_EMAIL_BATCH_SIZE = 50` recipients per request (matching the batch size corporate-node already uses in `bulkUploadInviteCandidates`) and issues the chunks concurrently. 309 recipients → 7 requests of ~380KB each, comfortably under both ceilings. Chunking lives in the shared action, so every bulk-email caller (JobRoles, Drive, ViewAndConfirm, ConfirmDrive) inherits it. Non-array payloads pass through unchanged.

Note the payload is intentionally **not** de-duplicated: every record carries its own copy of the identical rendered body, so the wire format is unchanged.

### Candidates without a usable mobile number are filtered out

`candidate.contact_number` may be null, blank, or a non-string (numeric). Calling `.replace()` on it threw inside the WhatsApp payload `.map()`, and because `notificationTrigger` is invoked without `await`/`.catch()`, the throw surfaced only as an unhandled rejection. The effect was all-or-nothing: **one** student missing a number meant **nobody** received the WhatsApp message.

Candidates whose number yields fewer than 10 digits are now dropped before the map — on both the eligible and ineligible paths — and the value is coerced with `String()` so a numeric field cannot throw.

### Known gap

Email and WhatsApp send failures are still swallowed (`catch (error) {}`), so a failed batch remains invisible to the TPO. Any future growth in per-recipient body size should be checked against the 1MB ceilings above.

---

## Key Features

- **Job category filter:** `jobCategory` param (e.g., PLACEMENT)
- **ElasticSearch integration:** Qualification search uses `elasticSearchRequest` with `systemConfig.degree_streams_specialisation`
- **Export options:** CSV blob download or Google Sheets integration
- **Role duplication:** Clone existing roles with `instituteCampusId`
- **Archive/restore:** Soft-hide institute-published roles via the global `is_archived` flag; Archive tab + per-row archive/restore icons (see Archive section above)
- **Filters:** Status, role type, evaluation schedule, domain, degree, department, year
