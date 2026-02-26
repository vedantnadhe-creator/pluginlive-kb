# Admin Portal

This folder contains module-wise documentation for the PluginLive Admin Portal — the super-admin interface used to manage onboarding, corporates, institutes, assessments, reports, system configuration, event catalogues, ranking algorithms, and course mappings across the platform.

**Frontend:** `admin-react`
**Route prefix:** `/` (authenticated admin user)

## Modules

### Core Modules (Nav Menu)

| Module | Folder | Route(s) | Description |
|--------|--------|----------|-------------|
| Onboarding | `Onboarding/` | `/onboarding`, `/onboarding/corporate`, `/onboarding/institute`, `/onboarding/corporate/:corporateId`, `/onboarding/institute/:instituteId`, `/onboarding/corporate/registeredSuccessfully`, `/onboarding/registeredSuccessfully` | Corporate & institute registration and onboarding |
| Corporates | `Corporates/` | `/corporates` | Corporate portal listing, detail view, portal switching |
| Institutes | `Institutes/` | `/institutes` | Institute portal listing, detail view, portal switching |
| Assessment | `Assessment/` | `/assessment`, `/assessment/create`, `/assessmentAssignSubscription`, `/assessmentAssignSubscription/institute/:id`, `/assessmentAssignSubscription/corporate/:id`, `/assessmentAccess` | Assessment management, subscriptions, feature access |
| Reports | `Reports/` | `/reports/corporate`, `/reports/corporate/empanelledinfotable`, `/reports/corporate/top10index`, `/reports/institute`, `/reports/institute/empanelledinfotable`, `/reports/institute/top10index`, `/reports/students`, `/reports/students/studentplacedscoursewise`, `/reports/students/listofstudentspalced`, `/reports/students/studentskillwise` | Corporate, institute, and student reports |
| Users | `Users/` | `/users`, `/users/:id` | Admin user and role management with permissions |
| System Config | `SystemConfig/` | `/systemConfig`, `/systemConfig/GeneralTableSettings/:GeneralCard/:id`, `/systemConfig/corporateSettings`, `/systemConfig/instituteSettings/:institueCard/:id`, `/systemConfig/permissionSettings/:institueCard/:id`, `/systemConfig/locationSettings/:locationCard/:id`, `/systemConfig/billingSettings` | Platform-wide configuration settings |
| Courses | `Courses/` | `/coursemapping` | Global course (degree-stream) mapping and management |
| Event Catalogue | `EventCatalogue/` | `/eventcatalogue` | Notification event and template management |
| Ranking Algorithm | `RankingAlgorithm/` | `/rankingAlgorithm` | Student ranking configuration and corporate mapping |

### Supporting Modules

| Module | Folder | Route(s) | Description |
|--------|--------|----------|-------------|
| Dashboard | `Dashboard/` | `/dashboard` | Admin overview dashboard |
| Settings | `Settings/` | `/settings` | Admin settings |
| Manage Profile | `ManageProfile/` | `/manageprofile` | Admin user profile, password, OTP phone/email verification |

---

## Architecture

- **State Management:** Redux (actions → reducers → selectors pattern)
- **API Layers:** Multiple Axios instances — `adminRequest`, `corporateRequest`, `instituteRequest`, `studentRequest`, `elasticSearchRequest`, `elasticSearchSyncRequest`, `authRequest`
- **UI Framework:** Ant Design (antd) + styled-components
- **Routing:** React Router (with `authenticatedWithNav` and `authenticatedWithoutNav` route groups)

## Documentation Structure

Each module folder contains a `README.md` covering:
- Overview & purpose
- Key UI components
- Redux actions & API endpoints
- Filters, sorting, pagination
- Related backend services
