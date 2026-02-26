# Drive Details Module

**Route:** `/driveDetails/:RoleID/:DriveID`
**Frontend:** `student-react/src/modules/DriveDetails/`

## Overview

The Drive Details module shows the interview schedule and details for a specific drive. Students can view their interview rounds, select preferred interview dates, and reschedule existing date selections.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Drive interview details and date selection |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getDriveDetails` | `/corporates/role/{roleId}/drive/{driveId}/student/{studentId}/interview` | GET (Corp) | Fetch interview details for a drive — rounds, timings, status |
| `DriveDateSelection` | `/corporate/drive/interview/{driveId}` | PUT (Corp) | Select preferred interview date/time slot |
| `ResheduleDriveDate` | `/corporates/role/{roleId}/drive/{driveId}/candidate/{studentId}` | PUT (Corp) | Reschedule an already selected interview date |

---

## Key Features

- **Interview round view:** See all rounds in the drive with timings
- **Date selection:** Choose preferred interview date/time
- **Rescheduling:** Change previously selected date
- **Drive-role-student scoped:** All APIs are scoped to the specific drive, role, and student
