# Users Module

**Route:** `/users`
**Frontend:** `institute-react/src/modules/Users/`

## Overview

The Users module manages TPO/admin users within the institute. It provides CRUD operations for user accounts, role assignment, status management, and user metrics.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | User listing and data orchestration |
| `FilterDiv/` | Filter bar | Search and filter controls |
| `Partials/UsersTable/` | User table | Paginated user listing table |
| `Partials/AddUserDrawer/` | Drawer | Create/edit user form |
| `Partials/UsersFilter/` | Filter panel | Role and status filter options |
| `Partials/ViewUserRoleDrawer/` | Drawer | View user role details |
| `Partials/constant.js` | Constants | Module-level constants |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getUserMetrics` | `/users/metrics?instituteCampusId={id}` | GET | User count metrics for the institute |
| `getUserList` | `/user?pageLimit=10&currentPage={n}&instituteId={id}` | GET | Paginated user listing with search, sort, role filter, status filter |
| `createUser` | `/user` | POST | Create a new user with instituteId, instituteCampusId, eventId |
| `getSingleUser` | `/user/{userId}` | GET | Fetch individual user details |
| `updateUser` | `/user/{userId}` | PUT | Update user details |
| `updateUserStatus` | `/user/{userId}/status` | PATCH | Activate or deactivate a user |
| `deleteUser` | `/user/{userId}` | DELETE | Delete a user |

---

## State Shape

```js
{
  userMetrics: {},
  userList: {},
  singleUser: {}
}
```

---

## Key Features

- **Full CRUD:** Create, read, update, delete user accounts
- **Role filter:** Filter users by assigned role (`&Role=`)
- **Status filter:** Filter by active/inactive status (`&status=`)
- **Search & Sort:** Text search with column-based sorting (asc/desc)
- **Pagination:** `pageLimit=10`, `currentPage` (0-indexed)
- **Success/Error messaging:** Uses `SuccessMessage` and `ErrorMessage` utilities
