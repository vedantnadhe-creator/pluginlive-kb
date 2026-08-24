# System Config Module

**Routes:**
- `/systemConfig` — System config dashboard
- `/systemConfig/GeneralTableSettings/:GeneralCard/:id` — General table settings
- `/systemConfig/corporateSettings` — Corporate-specific settings
- `/systemConfig/instituteSettings/:institueCard/:id` — Institute-specific settings
- `/systemConfig/permissionSettings/:institueCard/:id` — Permission settings
- `/systemConfig/locationSettings/:locationCard/:id` — Location settings
- `/systemConfig/billingSettings` — Billing settings

**Frontend:** `admin-react/src/modules/Systemconfig/`

## Overview

The System Config module is the platform-wide configuration hub. It manages general table settings, corporate-specific settings, institute-specific settings, permission settings, location settings, and billing settings. Each setting category has its own route with parameterized card/id for sub-section navigation.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `index.js` | Main page | System config dashboard with setting categories |
| `Container/` | Container | Main settings container |
| `Partials/GeneralTableSettings/Container/` | General | General table settings management |
| `Partials/CorporateSettings/Container/` | Corporate | Corporate-specific configuration |
| `Partials/InstituteSettings/Container/` | Institute | Institute-specific configuration |
| `Partials/PermissionSettings/Container/` | Permissions | Permission management settings |
| `Partials/MyLocationSettings/Container/` | Locations | Location management settings |
| `Partials/BillingSettings/Container/` | Billing | Billing configuration |
| `Components/ActionDropdown/` | Actions | Reusable action dropdown |
| `Components/CommonFunction/` | Utilities | Shared helper functions |
| `Components/Drawer/` | Drawer | Settings edit drawers |
| `Components/Filter/` | Filters | Settings filter components |

---

## Saving an Institute Settings record triggers ten search syncs

`createInstituteSysConfig` (`Partials/InstituteSettings/actions.js`) is the shared create/update/delete action for every Institute Settings menu — College, University, Domain, Degree, Degree Type, Degree Level, Department, Specialisation. Because it is generic and does not know which dataset changed, after the write it posts to **all ten** search-service sync endpoints (`universities_master`, `institutes_master`, `degree_data`, `institute_degree`, `institute_streams`, `crud_degree_department`, `institute_specialisation`, `institute_campus_cources`, `locationsDetails`, `institute_locations`), then shows the success toast.

This is not cosmetic: the lists on these screens are read from search-service's materialized views, so **the save is genuinely not visible in the list until the refreshes finish**. The syncs cannot simply be dropped or made fire-and-forget without the new row appearing to vanish.

**They must, however, run concurrently.** Until 2026-08-24 they were ten sequential `await`s, and each one is a full `REFRESH MATERIALIZED VIEW CONCURRENTLY` — a college create measured **29.2 s** on PROD (`institutes_master` 11.2 s + `institute_campus_cources` 8.4 s + `institute_locations` 7.6 s + seven cheap ones). The record itself was written in **1.3 ms**; the entire wait was the refresh chain, which is why the college existed while the UI still spun. They now go out together via `Promise.allSettled`, bounded by the slowest, and `institutes_master` gained the 30 s debounce it was missing on the backend.

`allSettled` rather than `all` is deliberate: the record is already committed by that point, so a failing refresh must not surface as a failed save. Anything that does fail is picked up by the 12-hourly scheduled sync.

The same pattern (write, then post to a subset of `/sync/*`) exists in Onboarding → Institutes → Register, `InstituteInfoTable`, `Courses/actions.js` and `CollegeDrawer`. Those fire two or three endpoints rather than ten and are still sequential.

See [../../ElasticSearch/Sync/README.md](../../ElasticSearch/Sync/README.md) for per-endpoint refresh costs.

---

## Key Features

- **Multi-category settings:** General, Corporate, Institute, Permission, Location, Billing
- **Post-save search sync:** Institute Settings saves refresh the search matviews concurrently before reporting success (see above)
- **Parameterized routes:** `:GeneralCard/:id`, `:institueCard/:id`, `:locationCard/:id` for sub-section navigation
- **Shared components:** Common action dropdown, drawer, and filter components across all setting types
- **Platform-wide scope:** Settings applied across all corporates and institutes
