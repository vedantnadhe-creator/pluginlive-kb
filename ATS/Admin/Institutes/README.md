# Institutes Module

**Route:** `/institutes`
**Frontend:** `admin-react/src/modules/Institutes/`

## Overview

The Institutes module provides admin-level management of all institute portals on the platform. Admins can view, search, filter, and access individual institute portals. Like Corporates, it supports role-based data fetching and portal switching.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Institute listing and management |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Institute Listing

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getUserInstitutePortalsList` | `/users/{userId}/INSTITUTE` (non-admin) or `institutes` (admin, ES) | GET | Paginated institute list with search, sort, status, state, city, active status filters. ADMIN role uses ES endpoint |

### Institute Details & Portal Switching

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getSingleInstituteData` | `/institutes/{instituteId}` | GET (Admin) | Fetch single institute details. Also calls `user/portal/signin` to get redirect link for portal switching |

---

## Key Features

- **Role-based data access:** ADMIN role fetches from ElasticSearch; other roles fetch user-scoped data
- **Portal switching:** Admin can generate redirect link to access any institute's portal
- **State/City filtering:** Geographic filters
- **Status filtering:** Active/inactive and onboarding status
- **Pagination:** `pageLimit=10`, `pageNo` (0-indexed)
