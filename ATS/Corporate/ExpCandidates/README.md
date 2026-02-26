# Exp-Candidates (Experienced Candidates) Module

**Routes:**
- `/expcandidates` — Experienced candidate listing
- `/expcandidatedrive/:expcandidatesId` — Drives for an experienced candidate
- `/expcandidates/:expcandidatesId/role/:roleId` — Individual drive details
- `/expcandidates/:expcandidatesId/role/:roleId/role` — Drive role details

**Frontend:** `corporate-react-1/src/modules/Exp-Candidates/`

## Overview

The Exp-Candidates module manages the evaluation pipeline for experienced (non-fresher) candidates. It provides a separate workflow from the standard institute-based placement drives, handling candidate listing, drive management, and role-level evaluation for experienced hires.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main listing | Experienced candidate listing |
| `Container/ExpCandidateDrives.js` | Drives | Drives for an experienced candidate |
| `Container/individualDrive.js` | Individual drive | Single drive details |
| `Container/individualDriveRole.js` | Drive role | Drive-role level view |
| `Components/DriveTable/` | Table | Candidate data table |
| `Components/DriveTable/Actions/` | Actions | Table action buttons |
| `DriveTable/Actions/` | Actions | Drive table action handlers |
| `ViewDriveRole/` | Drive role view | Role-specific evaluation view |
| `ViewDriveRole/CandidateDocumnets/` | Documents | Candidate document management |
| `ViewDriveRole/IndividualDriveTable/` | Individual table | Per-candidate evaluation table |

---

## Redux Files

| File | Purpose |
|------|---------|
| `actions.js` | Exp-candidate API action creators |

---

## Key Features

- **Separate pipeline:** Independent from fresher/institute-based hiring
- **Multi-level navigation:** Candidates → Drives → Role → Evaluation
- **Candidate documents:** Document review and management
- **Drive-role evaluation:** Same evaluation flow as fresher drives but for experienced candidates
- **`isExpCandidate` flag:** Differentiates from fresher candidates in API calls
