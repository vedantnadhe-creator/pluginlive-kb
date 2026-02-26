# Students Module

**Route:** `/students`
**Frontend:** `corporate-react-1/src/modules/Students/`

## Overview

The Students module provides a student listing view for corporate users. Unlike the institute-side Students module, this is primarily a read-only view of students who have applied or been shortlisted for the corporate's roles.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Student listing page |

---

## Key Features

- **Read-only view:** Corporate users view student data; management is done via Roles/Drives modules
- **Student data:** Sourced from role applications and drive evaluations
- **Actions file:** Empty (`actions.js` has no actions) — student data is fetched through Roles module actions
