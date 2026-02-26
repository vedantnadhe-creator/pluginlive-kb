# Reports Module

**Routes:**

### Corporate Reports
- `/reports/corporate` — List of Corporates
- `/reports/corporate/empanelledinfotable` — List of Corp. Empanelled
- `/reports/corporate/top10index` — Top/Bottom Corporate

### Institute Reports
- `/reports/institute` — List of Institutes
- `/reports/institute/empanelledinfotable` — List of Inst. Empanelled
- `/reports/institute/top10index` — Top 10 Institutes

### Student Reports
- `/reports/students` — List of Students
- `/reports/students/listofstudentspalced` — List of Students Placed
- `/reports/students/studentplacedscoursewise` — Students Placed Course-Wise
- `/reports/students/studentskillwise` — Students Placed Skill-Wise

**Frontend:** `admin-react/src/modules/Reports/`

## Overview

The Reports module provides platform-wide reporting across three categories: Corporate, Institute, and Student. Each category has multiple sub-reports with shared filter patterns (state, city, sector/industry, date range) and Excel export support. Reports include both listing and empanelled/top-bottom variants.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Corporate list | List of corporates report |
| `Partials/Corporates/Container/index` | Empanelled | Corporate empanelled report |
| `Partials/Corporates/Container/TopBottomCorporateIndex` | Top/Bottom | Top/Bottom corporate report |
| `Partials/Institutes/Container/InstituteInfoIndex.js` | Institute list | List of institutes report |
| `Partials/Institutes/Container/index.js` | Empanelled | Institute empanelled report |
| `Partials/Institutes/Container/TopInstituteList.js` | Top 10 | Top 10 institutes report |
| `Partials/Students/Container/ListOfStudentTableIndex` | Student list | List of students report |
| `Partials/Students/Container/StudentPlacedTableIndex.js` | Placed | Students placed report |
| `Partials/Students/Container/StudentCourseBaseIndex.js` | Course-wise | Students placed course-wise |
| `Partials/Students/Container/StudentSkillWiseDetails.js` | Skill-wise | Students placed skill-wise |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Corporate Reports

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getCorporateListForReport` | `/corporates-report/lists` | GET | Corporate list with state, city, sector, industry, date range, search, sort. Supports `excel` flag for export |
| `getEmpanelledCorporateListForReport` | `/institute-report/lists` | GET | Institute empanelled list (also used for corp empanelled context) |
| `getTopBottomCorporateDetails` | `/topcorporatesreport/toplists` or `/bottomcorporatesreport/bottomlists` | GET | Top/Bottom corporates. `top` boolean switches endpoint |

### Filter APIs

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getSectorList` | `/corporate-filter/sectorindustrycorpmaster/lists` | GET | Sector filter options with flag and search |
| `getStateList` | `/corporate-filter/statecorpsmaster/lists` | GET | State filter options |
| `getCityList` | `/corporate-filter/citycorpmaster/lists` | GET | City filter options |
| `getIndustryList` | `/industrycorporatesmaster/lists` | GET | Industry filter options |
| `getSingleSectorList` | `/sectorcorporatesmaster/lists` | GET | Single sector details |
| `getSingleIndustryList` | `/industrycorporatesmaster/lists` | GET | Single industry details |
| `IndustrySectorUrl` | `/corporate-filter/sectorindustrycorpmaster/lists` | GET | Combined industry/sector filter with flag |

### Supporting

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `studentDetails` | `/students/{studentId}` | GET | Individual student details for drill-down |

---

## Common Filter Parameters

All report APIs share:
- **size/page:** Pagination (0-indexed pages)
- **sort/orderBy:** Column sorting
- **state, city, sector, industry:** Dimension filters
- **createdAtStart/createdAtEnd:** Date range
- **name:** Search text
- **excel flag:** When `true`, dispatches to `SET_EXCEL_DATA` for export

---

## Key Features

- **Three report categories:** Corporate, Institute, Student
- **10 distinct report views** across the three categories
- **Top/Bottom toggle:** Single action handles both top and bottom corporate reports
- **Excel export:** All reports support export via `excel=true` flag
- **Paginated filters:** Filter dropdowns themselves support search and pagination
- **Flag-based filter scoping:** Filters accept a `flag` parameter for context-specific options
