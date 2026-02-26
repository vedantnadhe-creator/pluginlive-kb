# TPO Dashboard Module

**Route:** `/tpoDashboard`
**Frontend:** `institute-react/src/modules/TPODashboard/`

## Overview

The TPO Dashboard is the primary analytics dashboard for Training & Placement Officers. It provides comprehensive placement analytics including job profile status, CTC analysis, active job roles, and student placement statistics — all with comparison support, PDF export, and donut chart visualizations. Data is filterable by year of passing, domain, degree, department, specialisation, and job category.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Dashboard layout and data orchestration |
| `Components/PageHeader.js` | Header | Dashboard header with filter controls |
| `Components/FilterComponent.js` | Filters | Year, domain, degree, department, specialisation, job category filters |
| `Components/TPOGraphs.js` | Graphs | Chart container for all dashboard visualizations |
| `Components/GraphDetails.js` | Graph details | Detailed graph data display |
| `Components/DonutWithCustomLegend.js` | Donut chart | Custom donut chart with legend |
| `Components/ActiveJobRoles.js` | Active roles | Active job roles table/card |
| `Components/StudentPlacement.js` | Placement stats | Student placement status breakdown |
| `Components/StyledComponent.js` | Styles | Styled components |
| `Components/CommonFunction.js` | Utilities | Color configs, label mapping, formatting helpers |
| `DashboardPopup/ShortList.js` | Popup | Shortlist details popup |

### PDF Export Components

| Component | Purpose |
|-----------|---------|
| `Components/ExportPDF.js` | PDF generation orchestrator |
| `Components/DonutChartPDF.js` | Donut chart for PDF |
| `Components/PDFHeader.js` | PDF header section |
| `Components/PDFFooter.js` | PDF footer section |
| `Components/PDFTable.js` | PDF table rendering |
| `Components/PDFTitleDetails.js` | PDF title details |
| `Components/PDFImageWithLegend.js` | PDF chart with legend |
| `Components/Font.js` | PDF font configuration |

---

## Redux Actions & API Endpoints

**File:** `action.js`

### Primary Data

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getTpoPrimaryCardData` | `/corporate/institute/tpo/{campusId}` | POST | Primary dashboard card metrics. Supports filter vs non-filter dispatch |
| `getJobProfileStatus` | `/corporate/institute/tpo/jobProfileStatus/{campusId}` | POST | Job profile status percentages (applied, shortlisted, selected, etc.) with compare mode |
| `getCTCAnalysis` | `/corporate/institute/tpo/ctcAnalysis/{campusId}` | POST | CTC range distribution and stats (min, max, median, average). Supports PA/PM period based on job category |
| `getActiveJobRoles` | `/corporate/institute/tpo/activeJobRoles/{campusId}` | POST | List of active job roles with status counts |
| `getStudentPlacement` | `/corporate/institute/tpo/studentPlacement/{campusId}` | POST | Student placement breakdown by degree-stream with placed/unplaced/opted-out counts and gender split |

### Supporting Data

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getYear` | `/students/institutes/{campusId}/yearOfPassing` | GET | Year of passing filter options |
| `getSpecializationList` | `/institutes/{campusId}/specialisations` | POST | Specialisation filter options |
| `getInstituteDetailsFromCampusId` | `/institutes/{campusId}` | GET | Institute details for PDF header |

---

## State Shape

```js
{
  dashboardDetails: {},
  filteredDashboardDetails: {},
  jobProfileStatus: [],
  compareJobProfileStatus: [],
  ctcCategory: [],
  compareCtcCategory: [],
  ctcAnalysis: [],
  compareCtcAnalysis: [],
  activeJobRoles: [],
  studentPlacement: {},
  compareStudentPlacement: {}
}
```

---

## Key Features

- **Compare mode:** Side-by-side comparison of metrics across different filter sets
- **Job categories:** PLACEMENT, INTERNSHIP, APPRENTICESHIP, GIGS — affects labels and CTC period (PA vs PM)
- **CTC analysis:** Range-based distribution with color-coded charts, min/max/median/average stats
- **Gender breakdown:** All placement metrics include male/female/other splits
- **Opt-out analysis:** Family, entrepreneur, higher education, and other reasons
- **PDF export:** Full dashboard export with charts, tables, headers, and footers
- **Color configurations:** `ctcAnalysisColors`, `ruleEngineColors`, `ctcCategoryColors` for consistent chart styling
