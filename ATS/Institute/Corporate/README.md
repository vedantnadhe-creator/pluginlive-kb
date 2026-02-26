# Corporate Module

**Route:** `/corporate`
**Frontend:** `institute-react/src/modules/Corporate/`

## Overview

The Corporate module allows TPO users to manage institute-level corporate/company records. Institutes can create, edit, delete, and bulk-upload companies they work with for placements. This is separate from the global corporate database — it manages the institute's own corporate relationships.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `index.js` | Main page | Corporate listing with search and filters |
| `NewCorporate/` | Create/Edit | Form for creating or editing a corporate entry |
| `NewCorporate/Header/` | Header | Page header for new corporate flow |
| `SectorFilter/` | Filter | Sector-based filter dropdown |
| `Bulkupload/ResultUploader.js` | Bulk upload | CSV upload result handler |
| `Bulkupload/ViewCorporate.js` | Preview | Preview uploaded corporate data |
| `Upload/` | Upload | File upload component for corporate data |
| `StyleComponents/` | Styles | Styled components for corporate pages |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getCorporateList` | `/corporate/institute/{campusId}/company` | GET | Paginated corporate list with search, sort, sector filter |
| `getCorporateFilter` | `/corporate/institute/{campusId}/filtercompany` | GET | Filter options for corporate listing |
| `getSingleCoporate` | `/corporate/institute/{campusId}/company/{corporateId}` | GET | Single corporate details |
| `createCorporate` | `/corporate/institute/createcompany` | POST | Create a new corporate entry |
| `updateCorporate` | `/corporate/institute/updatecompany/{corporateId}` | PUT | Update corporate details |
| `deleteCoprorateDetails` | `/corporate/institute/deletecompany/{companyId}` | DELETE | Delete a corporate entry |
| `bulkUploadCorporate` | `/corporate/institute/companybulkupload` | POST | Bulk create corporates from CSV |
| `getSectorMaster` | `/corporate/crud/sector` | GET | Sector master list for filtering |
| `getUserMetrics` | `/users/metrics` | GET | User metrics for the institute |
| `getUserList` | `/user` | GET | User listing (shared action) |
| `updateUserStatus` | `/user/{userId}/status` | PATCH | Toggle user active/inactive status |

---

## Key Features

- **CRUD:** Full create, read, update, delete for institute corporates
- **Bulk Upload:** CSV-based mass corporate creation
- **Sector Filter:** Filter corporates by industry sector
- **Search & Sort:** Text search with column-based sorting
- **Pagination:** `pageLimit=10`, `pageNo` (0-indexed)
