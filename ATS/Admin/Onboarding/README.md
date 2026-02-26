# Onboarding Module

**Routes:**
- `/onboarding` — Onboarding listing/dashboard
- `/onboarding/corporate` — Register new corporate
- `/onboarding/institute` — Register new institute
- `/onboarding/corporate/:corporateId` — Edit corporate (no nav)
- `/onboarding/institute/:instituteId` — Edit institute (no nav)
- `/onboarding/corporate/registeredSuccessfully` — Registration success
- `/onboarding/registeredSuccessfully` — Registration success (no nav)

**Frontend:** `admin-react/src/modules/Onboarding/`

## Overview

The Onboarding module manages the registration of new corporates and institutes onto the PluginLive platform. Admins can initiate onboarding, fill in registration forms (company details, address, contacts), upload documents, send onboarding links, and view registration success. The module also provides master data lookups for countries, states, cities, industries, sectors, and universities.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main listing | Onboarding listing/dashboard |
| `Partials/Corporates/Register/Container/` | Corporate form | Corporate registration form |
| `Partials/Institutes/Register/Container/` | Institute form | Institute registration form |
| `Components/RegisterSuccessful/RegisterSuccessfulPage` | Success page | Post-registration success view |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Master Data (ElasticSearch)

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getListOfCounties` | `/search/countries` | GET (ES) | Country list with search (pageLimit=50 or 500) |
| `getListOfCountryCode` | `/search/countries?groupBy=phone_code` | GET (ES) | Phone code list |
| `getListOfState` | `/search/states` | GET (ES) | State list filtered by countryId |
| `getListOfCity` | `/search/cities` | GET (ES) | City list filtered by countryId, stateId |
| `getCitiesWithPagination` | `/search/cities` | GET (Auth) | Paginated city search |
| `getListOfInstituteLocation` | `/institute/location` | GET (ES) | Institute locations grouped by field |
| `getListOfCorporateLocations` | `/corporate/location` | GET (ES) | Corporate locations grouped by field |

### Industry & University

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getIndustryList` | `/industries` | GET (Corp) | Industry list with search |
| `getSectorList` | `/corporate/crud/sector` | GET (Corp) | Sector list with search |
| `getUniversityList` | `/institutes/crud/universities` | GET (Inst) | University list with search |
| `searchAPI` | `/search/{type}` | POST (ES) | Generic ElasticSearch master data search |
| `getMasterSearchApi` | `/search/{type}` | POST (ES) | Master search with payload |

### Onboarding Actions

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `sendOnboardingLink` | `/users/onboardingLinkSharing` | POST (Admin) | Send onboarding invite link to corporate/institute |

### File Management

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `uploadFile` | `/signedURL` | POST (Auth) | Get signed URL for S3 upload |
| `deleteFile` | `/deleteFile` | DELETE (Auth) | Delete uploaded file |
| `getFile` | (S3 signed URL) | PUT | Upload file to S3 |

---

## Key Features

- **Dual onboarding:** Separate flows for corporates and institutes
- **Onboarding links:** Send email invites for self-registration
- **Master data:** Full country → state → city cascading lookups via ElasticSearch
- **S3 file uploads:** Document upload via signed URLs
- **Location lookups:** Both institute and corporate location searches
