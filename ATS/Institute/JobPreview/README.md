# Job Preview Module

**Route:** `/jobRoles/jobPreview/:roleId`
**Frontend:** `institute-react/src/modules/JobPreview/`

## Overview

The Job Preview module provides a detailed view of a specific job role. It displays job details, candidate lists, placement history, role status, and student resume viewing capabilities. Accessed from the Job Roles listing.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Job preview page orchestration |
| `PageHeader/` | Header | Job preview header with actions |
| `PageHeader/Components/` | Header components | Reusable header sub-components |
| `Components/JobDetails.js` | Job details | Full job role details display |
| `Components/JobCandidateList.js` | Candidate list | Candidates applied/shortlisted for the role |
| `Components/PlacementHistory.js` | Placement history | Historical placement data for the role |
| `Components/PlacementTable.js` | Placement table | Tabular placement data |
| `RoleStatus/` | Role status | Current role status and metrics |
| `ViewResumeDrawer/` | Resume drawer | Student resume side drawer |
| `ViewResumeDrawer/StudentResumeDetailsAction.js` | Resume actions | Resume-related API actions |
| `ViewResumeDrawer/StudentResumeDrawerContent/` | Resume content | Resume display content |

---

## Redux Files

| File | Purpose |
|------|---------|
| `action.js` | API action creators |
| `reducer.js` | State reducer |
| `selector.js` | State selectors |
| `constant.js` | Module constants |

---

## Key Features

- **Role detail view:** Comprehensive job role information
- **Candidate tracking:** View candidates and their status for the role
- **Placement history:** Historical placement data
- **Resume viewer:** Side drawer for viewing student resumes
- **Role status metrics:** Current status of the job role
