# View Single Role Module

**Route:** `roles/viewrole/:CorpID/:JobID`
**Frontend:** `student-react/src/modules/ViewSingleRole/`

## Overview

The View Single Role module displays the detailed view of a job role accessed from the Roles listing page (pre-apply context). It shares the same role detail UI as ViewRole but is accessed from the main roles browse page rather than the applied roles section.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Role detail view from listing |

---

## Key Features

- **Pre-apply context:** Accessed from role browsing (not applied roles)
- **Actions file:** Empty — role data and actions are handled by the Roles and ViewRole modules
- **Shared components:** Uses shared role detail components
