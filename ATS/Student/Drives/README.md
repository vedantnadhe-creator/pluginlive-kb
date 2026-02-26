# Drives Module

**Route:** `/drives`
**Frontend:** `student-react/src/modules/Drives/`

## Overview

The Drives module lists placement drives scheduled for the student. It supports two distinct API paths based on whether the student is an experienced candidate (`isExpCandidate`) or a fresher (institute-campus based). Drives can be filtered by occurrence (upcoming/ongoing/completed), drive mode, and date. Also provides a calendar view of drive dates.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Drive listing with filters and calendar |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

| Action | API (Exp Candidate) | API (Fresher) | Method | Purpose |
|--------|---------------------|---------------|--------|---------|
| `getDrivesList` | `/corporates/drive/{studentId}/list` | `/corporates/drive/{instituteCampusId}/{studentId}/list` | GET (Corp) | Paginated drive list. Filters: occurrence, driveMode, date, sort=createdAt desc, pageLimit=10 |
| `getDrivesList` (calendar) | Same endpoint without date filter | Same endpoint without date filter | GET (Corp) | Calendar date data (separate call without date filter for all dates) |

---

## Key Features

- **Dual API path:** Experienced candidates use `studentId` only; freshers use `instituteCampusId/studentId`
- **Occurrence filter:** Upcoming, ongoing, completed drives
- **Drive mode filter:** In-person, virtual, hybrid (uppercased with underscores)
- **Calendar view:** Separate API call fetches all drive dates for calendar rendering
- **Date filter:** Filter drives by specific date
- **Pagination:** `pageLimit=10`, `currentPage`
