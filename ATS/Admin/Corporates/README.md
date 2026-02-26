# Corporates Module

**Route:** `/corporates`
**Frontend:** `admin-react/src/modules/Corporates/`

## Overview

The Corporates module provides admin-level management of all corporate portals on the platform. Admins can view, search, filter, and access individual corporate portals. It supports role-based data fetching (ADMIN role uses ElasticSearch, other roles use admin API with user-scoped access). Includes portal switching to impersonate/access a corporate's portal.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Corporate listing and management |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Corporate Listing

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getUserCorporatePortalsList` | `/users/{userId}/CORPORATE` (non-admin) or `corporates/list` (admin, ES) | GET | Paginated corporate list with search, sort, status, state, city, active status, ranking filters. ADMIN role uses ES endpoint |
| `getActiveCorporatePortalsList` | Same endpoints with `isRankingActive=true` | GET | Active corporates with ranking enabled |

### Corporate Details & Portal Switching

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getSingleCorporateData` | `/corporate/{corporateId}` | GET (Admin) | Fetch single corporate details. Also calls `user/portal/signin` to get redirect link |
| `userPortalSwitchingToken` | `/user/portal/signin` | POST (Auth) | Generate portal switching token. Payload: `{ email, journey: 'CORPORATE', journeyId }` |

### Location Filters

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getCorporateBasedPlaces` | `/corporate/location` | GET (ES) | Corporate locations grouped by city/state for filtering |
| `getCitiesWithPagination` | `/search/cities` | GET (Auth) | Paginated city search |

---

## Key Features

- **Role-based data access:** ADMIN role fetches from ElasticSearch; other roles fetch user-scoped data from admin API
- **Portal switching:** Admin can generate a redirect link to access any corporate's portal
- **Ranking filter:** `isRankingActive` flag filters corporates with ranking enabled
- **State/City filtering:** Geographic filters with ES-backed location search
- **Pagination:** `pageLimit=10`, `currentPage` (0-indexed)
