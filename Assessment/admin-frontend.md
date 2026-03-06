# Admin-React Assessment Frontend

> Documents the admin-react Assessment module (`src/modules/Assessment/`), covering institute and corporate assessment management, student reports, NPS scoring, and the unified assessment table.

---

## File Reference

**Module Root:** `admin-react/src/modules/Assessment/`

| File | Purpose |
|------|---------||
| `index.js` | Main Assessment page -- tabs for institutes/corporates, routes to dashboards, handles assessment/diagnosis click routing |
| `actions.js` | Redux action creators for fetching institutes, corporates, assessments, student data |
| `reducers.js` | Redux reducer for assessment state |
| `selectors.js` | Redux selectors for assessment state |
| `Style/style.js` | Shared styled-components (CustomStyledTable, SearchSection, TableTop, ShowingText, AssessmentName, etc.) |

### Partials

| File | Purpose |
|------|---------||
| `Partials/ActiveCollegeList/index.js` | Institute list with AntdAvatar, search, pagination. Clicking opens InstituteAssessmentDashboard |
| `Partials/ActiveCollegeList/InstituteAssessmentDashboard.js` | Per-institute assessment dashboard -- info cards, UnifiedAssessmentTable, Add Candidate drawer |
| `Partials/ActiveCollegeList/InstituteAssessmentDetails.js` | Charts + cascading filters for a specific institute assessment |
| `Partials/ActiveCollegeList/UnifiedAssessmentTable/index.js` | Main assessment table -- supports both institute and corporate records, expandable rows, search, pagination, Add Candidate button |
| `Partials/ActiveCollegeList/UnifiedAssessmentTable/ExpandableContent.js` | Expanded row content showing assessment schedule details |
| `Partials/ActiveCollegeList/TpoStudentListTable.js` | Student list table with sortable columns including NPS scores |
| `Partials/ActiveCollegeList/CandidateList/index.js` | Student candidate list within an assessment -- clicking opens StudentReportModal |
| `Partials/ActiveCollegeList/DiagnosisList/index.js` | Diagnosis assessment student list |
| `Partials/ActiveCorporateList/index.js` | Corporate list with AntdAvatar, search, pagination |
| `Partials/ActiveCorporateList/CorporateAssessmentDashboard.js` | Per-corporate assessment dashboard -- reuses UnifiedAssessmentTable |
| `Partials/StudentReport/index.js` | Student report drawer -- shows scores, personal details, download report |

### Shared Components

| Component | File | Purpose |
|-----------|------|---------||
| `AssessmentProgressBar` | `components/AssessmentProgressBar.js` | Progress bar showing sent vs taken counts (active assessments) |
| `CompletedAssessmentProgressBar` | `components/CompletedAssessmentProgressBar.js` | Progress bar for completed assessments |
| `InfoCardsUpdate` | `components/InfoCardsUpdate/cardDetails.js` | Dashboard info cards (total candidates, sent, taken, expired) |
| `AntdAvatar` | `components/Avatar/index.js` | Avatar component with letter fallback via `IconName` prop |
| `TreeSelect` | `components/TreeSelect/index.js` | Cascading tree select for filters |
| `CollegeCard` | `components/CollegeCard/index.js` | Institute card with logo and letter avatar fallback |

---

## UnifiedAssessmentTable

The core assessment listing table used by both institute and corporate dashboards.

### Props

| Prop | Type | Purpose |
|------|------|---------||
| `activeAssessments` | Array | Currently active assessments |
| `completedAssessments` | Array | Completed assessments |
| `loading` | Boolean | Spinner state |
| `filters` | Object | Current filter state |
| `onFilterChange` | Function | Called when filters change |
| `onPageChange` | Function | Called on pagination |
| `onAssessmentClick` | Function | Called when assessment name is clicked |
| `onAddCandidate` | Function | Called when "Add Candidate" button is clicked |
| `stateCityPairs` | Array | State/city pairs for geographic filters |

### Institute vs Corporate Record Handling

The table handles both institute and corporate assessment records with different field names:

| Field | Institute Record | Corporate Record |
|-------|-----------------|-----------------||
| Map ID | `latestAssessmentInstituteMapId` | `latestAssessmentCorporateMapId` |
| Assessment ID | `assessmentInstituteMapId` | `assessmentCorporateMapId` |
| Name | `scheduleName` | `name` |
| Schedule details | `assessmentDetails[]` array | No assessment details (flat record) |
| Schedule ID | `scheduleId` | N/A |
| Row key | `scheduleId` | `assessmentCorporateMapId` |

### Click Flow

1. **Corporate assessments**: Passes record directly with `id = assessmentCorporateMapId` to `onAssessmentClick`
2. **Institute diagnosis** (no `latestAssessmentInstituteMapId`): Passes record with `isDiagnosis: true`
3. **Institute regular**: Finds matching detail from `assessmentDetails`, passes with `assessmentInstituteMapId` and `scheduleNumber`
4. **Upcoming with map ID**: Click blocked (greyed out)

### Parent Routing (Assessment/index.js)

- `handleDashboardAssessmentClick`: Routes institute clicks to `InstituteAssessmentDetails` (charts), corporate clicks to existing `AssessmentDetails`
- `handleDiagnosisClick`: Opens diagnosis view
- `handleAssessmentClick`: Direct assessment detail view

---

## Student Report Drawer (StudentReport/index.js)

### Props

| Prop | Type | Purpose |
|------|------|---------||
| `visible` | Boolean | Drawer visibility |
| `student` | Object | Student data with scores |
| `isDiagnosis` | Boolean | Whether this is a diagnosis report |
| `onClose` | Function | Close handler |

### Score Format Handling

The component handles two data formats:

**New format** (`sectionScores` object):
```javascript
student.sectionScores = {
  reading: { average: 75 },
  listening: 80,
  critical: { average: 65 },
  quantitative: 70,
  logical: { average: 60 }
}
```

**Old format** (flat fields):
```javascript
student.englishVerbalScore = 75
student.readingAbilityScore = 80
```

The `getScore(newKey, oldKey)` helper checks `sectionScores` first, falling back to flat fields.

### Assessment Type Detection

- **Communication**: Default when not aptitude
- **Aptitude**: Detected if `student.aptitudeScores` exists OR `sectionScores` contains keys like `critical`, `quantitative`, `logical`

### Aptitude Score Cards

Priority order for aptitude data:
1. `student.aptitudeScores` object (has `criticalReasoningPercentage`, `quantitativePercentage`, `logicalReasoningPercentage`)
2. `student.sectionScores` mapped: `critical` -> Critical Reasoning, `quantitative` -> Quantitative Ability, `logical` -> Logical Reasoning
3. Fallback to empty

### Diagnosis Report

When `isDiagnosis = true`:
- Checks `assessmentAssignedId1` and `assessmentAssignedId2` for report availability
- Shows dropdown button with "Assessment #1" / "Assessment #2" options
- `handleDownloadReport(assignedId)` downloads the specific assessment report

---

## NPS Score Columns

NPS (Net Promoter Score) columns are displayed in `TpoStudentListTable`:

| Column | Field | Source |
|--------|-------|--------|
| COMM. NPS | `communicationNPS` | `student-node/app/models/TpoDashBoard.js` |
| APT. NPS | `aptitudeNPS` | `student-node/app/models/TpoDashBoard.js` |

Both columns are sortable. Backend sorting is server-side (sorts ALL students before pagination, not just current page).

### Backend (student-node)

In `TpoDashBoard.js`, the NPS fields are included in the formatted student response:
```javascript
communicationNPS: nps.communicationNPS != null ? Math.round(nps.communicationNPS * 100) / 100 : null,
aptitudeNPS: nps.aptitudeNPS != null ? Math.round(nps.aptitudeNPS * 100) / 100 : null,
```

---

## Pagination

The student list API (`student-node/TpoDashBoard.js`) returns flat pagination fields:
```javascript
{
  students: [...],
  totalCount: 150,
  pageNumber: 1,
  pageSize: 10
}
```

Frontend extracts these directly (NOT nested under `data.pagination`):
```javascript
setPagination({
  pageNumber: data?.pageNumber || page,
  totalCount: data?.totalCount || 0,
  pageSize: data?.pageSize || 10,
})
```

---

## Institute & Corporate List Avatars

Both institute and corporate lists use the same `AntdAvatar` component from `components/Avatar`:
```jsx
<AntdAvatar
  src={record.logoUrl}
  IconName={record.name?.charAt(0)?.toUpperCase()}
  size={40}
/>
```

This provides an image avatar with letter fallback when no logo URL is available.

---

## API Endpoints Used

| Endpoint | Method | Purpose | Source |
|----------|--------|---------|--------|
| `/assessment/admin/institutes` | GET | List subscribed institutes | admin-node |
| `/assessment/admin/corporates` | GET | List corporates | admin-node |
| `/assessment/admin/active` | GET | Active assessments for entity | admin-node |
| `/assessment/admin/completed` | GET | Completed assessments for entity | admin-node |
| `/assessment/admin/details` | GET | Assessment student details | admin-node |
| `/assessment/tpo/students` | GET | TPO student list with NPS | student-node |
| `/assessment/report/download` | GET | Download student report PDF | student-node |
| `/assessment/addStudentsToAssessment` | POST | Add candidates to existing assessment | admin-node |
| `/assessment/backfill-progression` | POST | Backfill progression data | student-node |

---

## Passing Year Race Condition (yearLoaded Pattern)

Both `InstituteAssessmentDashboard.js` (admin-react) and `Assessment/index.js` (institute-react) use a `yearLoaded` state gate to prevent API calls before the passing year is fetched and set.

**Problem:** React 17 does NOT batch setState in async callbacks. Without guards, effects fire with `selectedYear=''`, fetching all years' data and mixing results.

**Pattern:**
```javascript
const [selectedYear, setSelectedYear] = useState('')
const [yearLoaded, setYearLoaded] = useState(false)

// 1. fetchYearList sets selectedYear AND yearLoaded (no selectedYear in useCallback deps)
const fetchYearList = useCallback(async () => {
  const years = await fetchYears()
  setSelectedYear(defaultYear)  // set BEFORE yearLoaded
  setYearLoaded(true)           // gate opens
}, [instituteCampusId])          // NO selectedYear in deps

// 2. Reset on institute change
useEffect(() => {
  setYearLoaded(false)
  fetchYearList()
}, [instituteCampusId])

// 3. ALL API-calling effects AND callbacks guard on BOTH yearLoaded AND selectedYear
useEffect(() => {
  if (instituteId && yearLoaded && selectedYear) { fetchData() }
}, [instituteId, selectedYear, yearLoaded, fetchData])

// 4. Callbacks also guard internally (belt-and-suspenders for React 17)
const fetchData = useCallback(async () => {
  if (!instituteId || !selectedYear) return  // internal guard
  // ... API call with passingYear: selectedYear
}, [instituteId, selectedYear])
```

**Key rules:**
- `fetchYearList` must NOT have `selectedYear` in its useCallback deps (causes infinite loop)
- `setYearLoaded(true)` must be in the `finally` block (after `setSelectedYear`)
- Every effect and callback that uses `selectedYear` must guard on both `yearLoaded` AND `selectedYear`
- Internal guards inside callbacks prevent calls with empty year even if effects fire unexpectedly

---

## Key Design Patterns

- **Unified Table**: `UnifiedAssessmentTable` handles both institute and corporate records by checking for entity-specific field names
- **Dual Score Format**: Student reports support both `sectionScores` (new) and flat score fields (old) for backward compatibility
- **AntdAvatar Pattern**: Both institute and corporate lists use the same avatar component with letter fallback
- **Redux + Connect**: Module uses `connect()` pattern with `actions.js`, `reducers.js`, `selectors.js`
- **Styled Components**: Shared styles in `Style/style.js` (CustomStyledTable, SearchSection, etc.)
- **Server-Side Sorting**: NPS and other column sorts send `sortBy` to API; backend sorts all records before pagination
- **yearLoaded Gate**: See "Passing Year Race Condition" section above
