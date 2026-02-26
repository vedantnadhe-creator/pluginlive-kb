# DataSearch Module

**Controller Prefix:** `/` (root — no prefix)
**Auth:** User (API key)
**Source:** `search-service-1/src/modules/dataSearch/`

## Overview

The DataSearch module provides specialized, purpose-built search endpoints for frontend filter dropdowns and listing pages across the ATS platform. Unlike the generic Search module, DataSearch endpoints are tailored to specific UI contexts — student filters, institute reports, corporate filters, campus previews, and CRUD lookups. The service layer (~184KB) contains complex ES queries optimized for each use case.

---

## API Endpoints

### Student Filter Endpoints

| Method | Route | Parameters | Description |
|--------|-------|------------|-------------|
| GET | `/student-filter/universities/lists` | `search`, `size`, `page` | University list for student filter dropdowns |
| GET | `/student-filter/degreedepartmentmaster/lists` | `search`, `size`, `page` | Degree-department master list for student filters |
| GET | `/student-filter/specializationmaster/lists` | `search`, `size`, `page` | Specialisation master list for student filters |
| GET | `/student-filter/collegenamemaster/lists` | `search`, `size`, `page` | College name master list for student filters |
| GET | `/student-filter/statemaster/lists` | `search`, `size`, `page` | State master list for student filters |
| GET | `/student-filter/citymaster/lists` | `search`, `size`, `page` | City master list for student filters |
| GET | `/student/skillsmaster/lists` | `search`, `size`, `page` | Student skill master list |

### Institute Filter/Report Endpoints

| Method | Route | Parameters | Description |
|--------|-------|------------|-------------|
| GET | `/institute-filter/universityinstmaster/lists` | `search`, `size`, `page` | University-institute master list for institute filters |
| GET | `/institute-report/degreedepartmentlist` | `search`, `size`, `page`, `instituteId`, `instituteCampusId` | Degree-department list filtered by institute |
| GET | `/institute-report/specializationlists` | `search`, `size`, `page`, `instituteId`, `instituteCampusId`, `degreeId`, `streamId` | Specialisation list filtered by institute + degree + stream (CAS context) |

### Institute CRUD/Master Endpoints

| Method | Route | Parameters | Description |
|--------|-------|------------|-------------|
| GET | `/institutes` | `search`, `pageLimit`, `pageNo`, `order`, `orderBy` | Master institute list with search and ordering |
| GET | `/institutes/degree` | `search`, `pageLimit`, `pageNo`, `instituteCampusId` | Degree data for an institute campus |
| GET | `/institutes/crud/universities` | `search`, `pageLimit`, `pageNo` | University master list |
| GET | `/institutes/crud/degree` | `search`, `pageLimit`, `pageNo`, `instituteCampusId` | Institute degree list |
| GET | `/institutes/crud/specialisation` | `search`, `pageLimit`, `pageNo`, `instituteCampusId` | Institute specialisation list |
| GET | `/institutes/crud/streams` | `search`, `pageLimit`, `pageNo`, `instituteCampusId` | Institute streams list |
| GET | `/institutes/crud/college` | `search`, `pageLimit`, `pageNo` | Institute college list (reuses master institutes query) |
| GET | `/institutes/crud/degree/dept` | `search`, `pageLimit`, `pageNo`, `instituteCampusId` | CRUD degree-department data |
| GET | `/institutes/instituteCampus/:instituteCampusId/courses` | `pageLimit`, `pageNo`, `search` | Courses for a specific institute campus |
| POST | `/institutes/campus/preview/list` | `pageLimit`, `pageNo`, `searchBy`, `location`, `tier`, `tpoCollegeList`, `publishedOrNot`, `corporateId`, `roleId` | Campus preview list with advanced filtering (body + query params) |

### Geography Endpoints

| Method | Route | Parameters | Description |
|--------|-------|------------|-------------|
| GET | `/countries` | `search`, `pageLimit`, `currentPage`, `is_active`, `sort`, `order`, `groupBy` | Country list (delegates to SearchServices) |
| GET | `/crud/states` | `search`, `countryId`, `pageLimit`, `currentPage` | States with country data |
| GET | `/crud/cities` | `search`, `countryId`, `stateId`, `pageLimit`, `currentPage` | Cities with state/country data |
| GET | `/crud/locations` | `search`, `countryId`, `stateId`, `cityId`, `pageLimit`, `currentPage` | Full location details |
| GET | `/cities` | `search`, `countryId`, `stateId`, `pageLimit`, `currentPage` | Cities data (default pageLimit=10000) |

### Corporate Endpoints

| Method | Route | Parameters | Description |
|--------|-------|------------|-------------|
| GET | `/corporate/crud/functions` | `search`, `pageLimit`, `pageNo` | Job functions list for corporate |
| GET | `/corporate/crud/sector` | `search`, `pageLimit`, `pageNo` | Sector list for corporate |
| GET | `/corporate/location` | `search`, `pageLimit`, `pageNo` | Corporate locations list |
| GET | `/corporates/list` | `search`, `pageLimit`, `currentPage` | Corporate list |
| GET | `/collegenamecorporatesfilter/lists` | `search`, `size`, `page` | College name filter for corporates (default size=500) |
| GET | `/cityrolecorporatesmaster/lists` | `search`, `size`, `page` | City-role corporate master list |

### Student CRUD

| Method | Route | Parameters | Description |
|--------|-------|------------|-------------|
| GET | `/students/crud/skill` | `search`, `pageLimit`, `pageNo` | Student CRUD skill list |
| GET | `/institute/location` | `search`, `pageLimit`, `pageNo` | Institute locations |

---

## Key Features

- **No controller prefix:** Routes are at the root level (e.g., `/institutes`, `/countries`)
- **Dual pagination styles:** Some endpoints use `size`/`page`, others use `pageLimit`/`pageNo` or `pageLimit`/`currentPage`
- **Context-specific queries:** Each endpoint has a tailored ES query optimized for its UI use case
- **Campus preview:** Advanced filtering with `tpoCollegeList`, `publishedOrNot`, `corporateId`, `roleId` for role publishing flow
- **Cross-module dependency:** Uses both `DataSearchServices` and `SearchServices` for country lookups
