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

`updateCurrentState` (from `modules/Onboarding/actions`, `PATCH /students/{studentId}/updateState`) is also mapped into the Dashboard container — see *Activation on opt-in* below.

---

## Placement opt-in popup and student activation

On first load, when `optedStatus.currentCourse.optOutStatus` is `null` (student has neither opted in nor out), the dashboard opens an `ActionRoleDrawer` configured from `showDrawerProps` (`utils/constants.js`) with two buttons:

- **Opt-out** (`closeText`) → opens the reason-selection drawer (`actionDrawerProps`).
- **Proceed** (`YesText`) → `handleCloseDrawer`: sets `isOptOut: false` via `updateOptedStatus`, then **activates the student**.

**Activation on opt-in.** Proceed sets `currentState = 4` (active / can apply for jobs) via `updateCurrentState(studentId, 4)`, but **only when the mandatory profile checklist items are complete**:

| Checklist item | Condition | Required to activate |
|---|---|---|
| Personal Information | `studentPersonalProfile.isAnywhere` **or** any `preferredJobLocation` entry with a `city_id`/`state_id` | **Yes** |
| Education | `education.length > 0` | **Yes** |
| Project & Internship | any `resume.projects` or `resume.internships` | No — displayed only |
| Work Experience | any `resume.workExperience` | No — displayed only |

Both conditions are evaluated as `hasPersonalInfo` / `hasEducation` in `modules/Dashboard/index.js` and drive **both** the green ticks in the right-hand panel and the activation gate, so the UI and the gate cannot drift apart. The call is skipped when `currentState >= 4` (already active) or `studentId` is missing; on success the dashboard re-fetches so the panel flips to "Start applying for jobs now!".

`studentId` comes from `state.auth.studentId` — the same id the student fetch uses.

> The gate is **client-side only**. `PATCH /students/{id}/updateState` in student-node does not itself validate the checklist.

Related: the same `currentState = 4` transition is set at the end of onboarding by `modules/Onboarding/Register/Notification` — see [Onboarding](../Onboarding/README.md).

---

## Key Features

- **Opt-out management:** Students can opt out of placement and withdraw opt-out
- **Activation on opt-in:** Proceed activates the student (`currentState = 4`) once Personal Information + Education are complete
- **Default route:** `/` and `*` both redirect to Dashboard
- **Status-driven UI:** Display changes based on opt-out/active status; the profile checklist and "Complete Now" button render only while `currentState < 4`
