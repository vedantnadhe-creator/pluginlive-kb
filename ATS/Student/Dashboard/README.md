# Dashboard Module

**Routes:** `/dashboard`, `/`
**Frontend:** `student-react/src/modules/Dashboard/`

## Overview

The Student Dashboard is the authenticated landing page. It manages the student's opt-out status — allowing students to opt out of placement, withdraw opt-out, or handle rejected one-time updates. The dashboard serves as the entry point after login.

---

## Redux Actions & API Endpoints

**File:** `actions.js`

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `studentOptedStatus` | `/students/{studentId}/optedStatus` | GET | Fetch current opt-out status |
| `updateOptedStatus` | `/students/{studentId}/optedStatus` | PUT | Update opt-out status (opt in/out) |
| `updateOptedWitdrawStatus` | `/students/{studentId}/optedStatus/withdraw` | PUT | Withdraw opt-out request |
| `rejectStudentStatus` | `/students/{studentId}/optedStatus/rejectedOneTimeUpdate` | PUT | Handle rejected one-time status update |

---

## Key Features

- **Opt-out management:** Students can opt out of placement and withdraw opt-out
- **Default route:** `/` and `*` both redirect to Dashboard
- **Status-driven UI:** Display changes based on opt-out/active status
