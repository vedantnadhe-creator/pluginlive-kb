# Drives Module

**Routes:**
- `/drives/role/:roleId` — Drive for a specific role (fresher)
- `/drives/:driveId/role/:roleId` — Specific drive for a role (fresher)

**Frontend:** `corporate-react-1/src/modules/Drives/`

## Overview

The Drives module manages placement drives — the scheduled evaluation events where corporates interview candidates from institutes. It provides drive-level candidate management, interview scheduling, evaluation forms, result uploads, offer management, conflict resolution, and bulk actions. This is the execution layer of the hiring pipeline.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main listing | Drive listing per role |
| `Container/individualDrive.js` | Individual drive | Single drive details |
| `Container/individualDriveRole.js` | Drive role | Drive-role combination view |
| `Components/DrivePage/` | Drive page | Drive overview page |
| `Components/DriveStatus/` | Status | Drive status display |
| `Components/DriveTable/` | Table | Drive data table |
| `Components/EvaluationForm/` | Eval form | Candidate evaluation form |
| `Components/ResolveConflict.js` | Conflicts | Resolve scheduling conflicts |
| `ViewDrive/DriveDetails/` | Drive details | Detailed drive information |
| `ViewDrive/DriveRightPart/` | Right panel | Drive detail right section |
| `ViewDrive/DriveTimeDrawer/` | Time drawer | Schedule time management |
| `ViewDrive/AddInterviewerDrawer/` | Interviewer | Add interviewer to drive |
| `ViewDriveRole/` | Drive role view | Role-specific drive view |
| `ViewDriveRole/IndividualDriveTable/` | Individual table | Per-candidate drive table |
| `ViewDriveRole/GroupDiscussionTable/` | GD table | Group discussion table |
| `ViewDriveRole/BulkActionDrawer/` | Bulk actions | Bulk status updates |
| `ViewDriveRole/Header/` | Header | Drive role page header |
| `DownloadAndUpload/` | Upload/Download | Bulk operations hub |
| `DownloadAndUpload/DownloadCandidateDrawer/` | Download | Download candidate data |
| `DownloadAndUpload/UploadResultDrawer/` | Results | Upload evaluation results |
| `DownloadAndUpload/UploadShortlistedDrawer/` | Shortlist | Upload shortlisted candidates |
| `DownloadAndUpload/UploadOfferDrawer/` | Offers | Upload offer details |
| `DownloadAndUpload/UploadAssessmentDrawer/` | Assessment | Upload assessment results |

---

## Redux Files

| File | Purpose |
|------|---------|
| `actions.js` | Drive API action creators |
| `reducers.js` | Drive state reducer |
| `selectors.js` | Drive state selectors |
| `utils.js` | Drive utility functions |

---

## Key Features

- **Drive pipeline:** Create drive → Schedule interviews → Evaluate → Upload results → Offer
- **Fresher evaluation:** Route prefix indicates this is for fresher candidate drives
- **Bulk uploads:** CSV-based uploads for results, shortlists, offers, and assessments
- **Interviewer assignment:** Add interviewers to drives with time scheduling
- **Group discussion:** Dedicated GD round management
- **Conflict resolution:** Resolve scheduling conflicts across drives
- **Candidate downloads:** Export candidate data from drives
