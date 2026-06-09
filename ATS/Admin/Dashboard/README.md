# Dashboard Module

**Route:** `/dashboard`
**Frontend:** `admin-react/src/modules/Dashboard/`

## Overview

The Admin Dashboard provides a high-level overview of platform activity — onboarding status, corporate/institute counts, and key metrics. It serves as the authenticated landing page (though currently commented out in nav items).

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Dashboard layout and data orchestration |

---

## Key Features

- **Platform overview:** Aggregate metrics for corporates, institutes, and students
- **Activity summary:** Recent onboarding and platform activity

---

## Real-Time "Online / Active Users" (Admin Dashboard)

**Route:** `/admin-dashboard` · **Frontend:** `admin-react/src/modules/AdminDashboard/`
**Backend:** `user-management-node` (`/dashboard/metrics`, `/dashboard/users`)

The Admin Dashboard shows **Total** and **Online** counts for four populations —
Corporates, Institutes, Students, Admin — plus an "Online users" list. "Online"
means **currently active right now**, driven by a presence heartbeat.

### Why (history)
Previously "Online/active" was computed as `last_login_date >= 15 minutes ago`.
This was wrong in both directions:
- A user active for >15 min **dropped off** (timestamp was only stamped at login).
- A user who **logged out** still showed online for the rest of the 15-min window.

It was replaced with heartbeat-based presence (the `last_login_date` field still
exists and is still stamped at login, but is **no longer used** for the online count).

### Data model — single central `users` collection (MongoDB)
All four populations live in one `users` collection in `user-management-node`,
distinguished by `corporate_id` / `institute_id` / `student_id` / (none = admin).
Two presence fields on `app/models/User.js`:

| Field | Type | Meaning |
|-------|------|---------|
| `last_active_at` | Date | Refreshed by the heartbeat while the user is active |
| `is_online` | Boolean | `true` on login/heartbeat; `false` on signout |

Index: `{ is_online: 1, last_active_at: -1 }`.

### Definition of "online"
```
is_online === true  AND  last_active_at >= now() - 3 minutes
```
`PRESENCE_WINDOW_MINUTES = 3` (`app/handlers/user.js`, `presenceCutoff()`). The
window is ~3× the heartbeat interval so a crashed/closed tab ages out on its own.

### Backend (`user-management-node`)
- **`POST /users/heartbeat`** (private) — `exports.heartbeat`: sets
  `last_active_at=now(), is_online=true` for `req.user._id` (id comes from the
  JWT, never the request body).
- **Login** (`completeLoginForUser`) — also stamps `last_active_at` + `is_online=true`.
- **Signout** (`/users/signout`) — sets `is_online=false, last_active_at=null` →
  immediate drop-off.
- **`GET /dashboard/metrics`** + **`GET /dashboard/users`** — count/list users by
  the online definition above (no longer `last_login_date`).

### Frontend — heartbeat in all 5 React apps
Each app (`admin-react`, `corporate-react`, `institute-react`, `student-react`,
`Assessment-React`) has `src/utils/presenceHeartbeat.js`:
- Pings `POST /users/heartbeat` **every 60s, only while `document.visibilityState
  === 'visible'`** (idle/background tabs are not counted), via the app's
  user-management request util (`authRequest` for admin/student/assessment,
  `request` for corporate/institute).
- `startPresenceHeartbeat()` is called on login (`SignIn`) and on reload
  (`authMiddleware` REHYDRATE); `stopPresenceHeartbeat()` on `signOut`.
- The 4 non-admin apps already call `users/signout` on logout (clears presence);
  admin-react's `signOut` also fires a best-effort `markOffline()`.
- Hard tab-close has no logout signal → handled by the 3-min staleness window.

### Admin dashboard UI
- `AdminDashboard/index.js`: header caption is **"Active now"** and the page
  **auto-refreshes every 60s** (was 15 min).
- `actions.js` calls `/dashboard/metrics?timeRange=15min` — the `timeRange` param
  is now ignored by the backend (fixed 3-min window).

### Gotchas
- New `last_active_at`/`is_online` populate only as users log in / heartbeat after
  deploy; pre-existing sessions show offline until their next heartbeat.
- This is MongoDB (Mongoose) — no SQL migration; fields apply automatically.
