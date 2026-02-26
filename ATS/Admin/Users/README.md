# Users Module

**Routes:**
- `/users` — User listing and role management
- `/users/:id` — Individual user detail view

**Frontend:** `admin-react/src/modules/User/`

## Overview

The Users module manages admin portal users and roles/permissions. It provides full CRUD for users, role creation with journey-based scoping (ADMIN, CORPORATE, INSTITUTE), permission management per journey, and user-role bulk updates. Also manages event-based permissions.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main listing | User listing and role management tabs |
| `Partials/UsersView/Container/index` | User detail | Individual user detail view |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### User CRUD

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getUserMetrics` | `/users` | GET (Admin) | Paginated user list with search, sort, role filter, status filter |
| `getUserList` | `/users` | GET (Admin) | User list scoped by instituteId with search, sort, role, status |
| `createUser` | `/users` | POST (Admin) | Create user with admin details (firstName, lastName trimmed) |
| `updateUser` | `/users/{userId}` | PUT (Admin) | Update user with authId from current session |
| `getSingleUser` | `/users/{userId}` | GET (Admin) | Fetch individual user details |
| `updateUserStatus` | `/user/{userId}/status` | PATCH (Admin) | Activate/deactivate user |
| `deleteUser` | `/user/{userId}` | DELETE (Admin) | Delete user |

### Role Management

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getRoleList` | `/roles` | GET (Admin) | Paginated role list with search, sort, journey filter, status |
| `getRoles` | `/roles/journey/{journeyName}` | GET (Admin) | Roles by journey (ADMIN/CORPORATE/INSTITUTE). Supports `isActiveRole`, `forInternalUser` flags |
| `createRoles` | `/roles` | POST (Admin) | Create new role |
| `updateRoles` | `/permissions/roles/{roleId}` | PUT (Admin) | Update role and permissions |
| `getSingleRole` | `/roles/{roleId}` | GET (Admin) | Fetch individual role details |
| `deleteRolesAndPermission` | `/permissions/roles/{roleId}` | DELETE (Admin) | Delete role and associated permissions |
| `updateUsersRole` | `/users/journey/roleUpdation` | PUT (Admin) | Bulk update user roles for a journey |

### Permissions

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getEvent` | `/permissions?journey={journey}` | GET (Admin) | Get permission events/screens for a journey |

---

## Key Features

- **Journey-based roles:** Roles scoped to ADMIN, CORPORATE, or INSTITUTE journeys
- **Permission management:** Event-based granular permissions per role
- **Internal user flag:** `forInternalUser` distinguishes internal vs external users
- **Bulk role update:** Update roles for multiple users in a journey at once
- **User detail view:** Dedicated route `/users/:id` for individual user management
- **Pagination:** `pageLimit=10`, `pageNo` (0-indexed)
