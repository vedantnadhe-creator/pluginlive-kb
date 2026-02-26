# Reports Module

**Route:** `/reports`
**Frontend:** `institute-react/src/modules/Reports/`

## Overview

The Reports module provides management and student-level reporting capabilities for the institute. TPO users can generate filtered reports, export them as CSV or to Google Sheets, and access custom report builders with selectable fields.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Report selection and orchestration |
| `Partials/ManagementReports/` | Management reports | Institute-level placement reports |
| `Partials/StudentReports/` | Student reports | Individual student-level reports |
| `Partials/CommonData/` | Shared data | Common report data, field mappings, URL mappings |

---

## Redux Actions & API Endpoints

**File:** `action.js`

### Filter APIs

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getDomainList` | `/instituteReportFilter/instituteCampusId/{id}/domain` | GET | Domain filter options for reports |
| `getDegreeList` | `/instituteReportFilter/instituteCampusId/{id}/degree` | GET | Degree filter options (filtered by domain) |
| `getDepartmentList` | `/instituteReportFilter/instituteCampusId/{id}/streams` | POST | Department/stream filter options |
| `getSpecializationList` | `/instituteReportFilter/instituteCampusId/{id}/specialisations` | POST | Specialisation filter options |

### Export

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `exportCSV` | `instituteReport/instituteCampusId/{id}/export/{reportKey}` | POST | Export standard report (CSV blob or Google Sheets) |
| `exportCSV` (custom) | `/students/instituteCampus/{id}/customReport/{type}/export` | PUT | Export custom report with selected fields |
| `customerReportDataList` | `/students/institutes/heading/export?forReport=true` | GET | Available field headings for custom report builder |

---

## Report Types

Reports are mapped via `reportUrlMapping` in `Partials/CommonData/reportData`:

| Report Key | Description |
|------------|-------------|
| Standard reports | Pre-defined report templates (management/student) |
| `custom` | Custom report with user-selected columns via `downloadList` |

---

## Export Flow

1. User selects report type and applies filters (domain, degree, department, specialisation, jobCategory)
2. `isMetrics=true` → returns summary/count data; `isMetrics=false` → returns full data as blob
3. Export types: `csv` (blob download) or `googlesheet` (Google Sheets integration)
4. Default `jobCategory` is `PLACEMENT` if not specified

---

## Key Features

- **Dual report views:** Management reports and student reports
- **Custom report builder:** Select which columns to include in export
- **Multiple export formats:** CSV download or Google Sheets
- **Cascading filters:** Domain → Degree → Department → Specialisation
- **Metrics mode:** Toggle between summary counts and full data export
