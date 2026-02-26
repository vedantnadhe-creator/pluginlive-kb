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

## Key Features

- **Multi-category settings:** General, Corporate, Institute, Permission, Location, Billing
- **Parameterized routes:** `:GeneralCard/:id`, `:institueCard/:id`, `:locationCard/:id` for sub-section navigation
- **Shared components:** Common action dropdown, drawer, and filter components across all setting types
- **Platform-wide scope:** Settings applied across all corporates and institutes
