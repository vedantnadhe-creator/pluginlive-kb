# Rule Engine Module

**Route:** `/ruleEngine`
**Frontend:** `institute-react/src/modules/RuleEngine/`

## Overview

The Rule Engine module allows TPO users to define and manage placement eligibility rules for their institute. Rules are created per degree/department combination and govern campus eligibility, job application criteria, and job approval workflows. Supports rule creation, editing, deletion, overwriting, and draft management.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Orchestrates rule engine dashboard |
| `Components/Dashboard/` | Dashboard | Rule engine overview with metrics |
| `Components/RulesSetTable/` | Rules table | Table of configured rule sets |
| `Components/YetToSetRulesTable/` | Pending table | Degrees/departments without rules |
| `Components/RuleEngineDraft/` | Drafts | Draft rule management |
| `Components/RulesCreationIndex/` | Creation flow | Step-by-step rule creation |
| `Components/SettingNewRules/` | Rule settings | Configure rule parameters |
| `Components/CampusEligibility/` | Eligibility | Campus eligibility rule configuration |
| `Components/ApplyJob/` | Apply job rules | Job application rule settings |
| `Components/JobApproval/` | Job approval | Job approval workflow rules |
| `Components/AlreadySetPopup/` | Popup | Warning for already-set degree rules |
| `Components/NewRuleModal.js` | Modal | New rule creation modal |
| `Components/RuleHeader.js` | Header | Rule engine page header |
| `Components/RuleEngineCommonFunction.js` | Utilities | Shared helper functions |

---

## Redux Actions & API Endpoints

**File:** `action.js`

### Rule CRUD

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `createRules` | `/institutes/{id}/rules` | POST | Create a new rule set |
| `updateRules` | `/institutes/{id}/rule/{ruleId}` | PUT | Update an existing rule |
| `deleteRule` | `/institutes/{id}/rule/{ruleId}` | DELETE | Delete a rule set |
| `ruleOverwrite` | `/institutes/{id}/rule/overwrite` | PUT | Overwrite existing degree rules with new rule |
| `getInstituteRulesById` | `/institutes/{id}/rules/{ruleId}` | GET | Fetch a single rule by ID |

### Rule Listing & Metrics

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getRuleSetData` | `/institutes/{id}/rules/list` | GET | Paginated rule list with status, sort, search filters |
| `setUpNewRules` | `/institutes/{id}/rules/degrees/metrics` | GET | Degree-level metrics for rule setup (yet-to-set counts) |
| `checkRuleSet` | `/institutes/{id}/rules/degrees` | GET | Check which degrees already have rules set |

### Rule Engine Config

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getRuleEngine` | `/institutes/{id}/rule` | GET | Get current rule engine configuration |
| `updateRuleEngine` | `/institutes/{id}/rule` | PUT | Update rule engine configuration |

### Supporting Data

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getRolesListData` | `/designations` | GET | Designation/role list for rule assignment |
| `getCorporateListFromCorporate` | `/corporates/list` | GET | Corporate list for rule context |
| `degreeStreamMap` | `/institutes/degreeStreamMap` | POST | Degree-stream mapping with pagination |

---

## State Shape

```js
{
  rolesList: {},
  ruleEngine: {},
  corporateList: {},
  ruleList: {},
  ruleListWay: {},
  ruleDetails: {},
  alreadySetDegreeList: [],
  rulesDegreesMetrics: {},
  selectedDegreeDepartment: {},
  degreeStreamMap: [],
  ruleStaticDetails: {},
  isRuleEdited: false
}
```

---

## Key Features

- **Degree-department scoping:** Rules are defined per degree-stream combination
- **Rule overwrite:** When a degree already has rules, TPO can overwrite or skip
- **Status filter:** Active (1) or inactive rules
- **Metrics dashboard:** Shows degrees with rules vs yet-to-set
- **Draft support:** Rules can be saved as drafts before activation
- **Pagination:** `pageLimit=10`, `pageNo` (0-indexed, offset by -1 in action)
