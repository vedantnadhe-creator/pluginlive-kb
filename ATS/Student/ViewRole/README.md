# View Role Module

**Route:** `appliedroles/viewrole/:CorpID/:JobID`
**Frontend:** `student-react/src/modules/ViewRole/`

## Overview

The View Role module displays the detailed view of a job role accessed from the Applied Roles section. It shows full role details, eligibility information, and provides actions to apply, save/unsave, share via email, request TPO approval, and mark roles as viewed.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Role detail view with actions |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Role Details

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getSingleRoleDetails` | `/corporate/role/{jobId}/{studentId}` | GET (Corp) | Fetch role details with student-specific data (applied status, eligibility) |
| `getSingleEligibleRoleDetails` | `/corporate/eligiblerole/{jobId}/{studentId}` | GET (Corp) | Fetch eligibility-specific role details |
| `getViewedRoleUpdate` | `/students/{studentId}/viewed/{jobId}` | PUT (Student) | Mark role as viewed by the student |

### Role Actions

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `ApplyRole` | `/students/role/apply` | POST (Student) | Apply for role. Payload includes roleId, studentId, corporateId, accessLevel, cvUrl, isSystemResume |
| `SaveRole` | `/students/role/save` | POST (Student) | Save/unsave a role |
| `jobSharingEmail` | `/users/{adminId}/jobSharing` | POST (Auth) | Share role via email |
| `getTPOApprovalRequest` | `/students/{studentId}/role/{jobId}/tpoApproval` | PUT (Student) | Request TPO approval for a role. Removes cvUrl if isSystemResume |

---

## Key Features

- **Resume selection:** Apply with uploaded CV (`cvUrl`) or system-generated resume (`isSystemResume`)
- **TPO approval flow:** Students can request TPO approval before applying
- **Job sharing:** Share role details via email
- **Viewed tracking:** Marks roles as viewed when opened
- **Optimistic state updates:** Save/apply actions update local state immediately
