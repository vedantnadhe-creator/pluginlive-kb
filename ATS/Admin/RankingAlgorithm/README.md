# Ranking Algorithm Module

**Route:** `/rankingAlgorithm`
**Frontend:** `admin-react/src/modules/RankingAlgorithm/`

## Overview

The Ranking Algorithm module configures the student ranking system. Admins manage ranking templates (academic, skill bucket, etc.), configure ranking parameters, update their ordering and status, and map ranking configurations to corporates. The ranking determines how students are scored and ranked for job roles.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Ranking algorithm configuration page |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Ranking Templates

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getTemplateListStudent` | `/students/rankingConfig` | GET (Student) | List all ranking config templates |
| `updateStudentTemplateList` | `/students/rankingConfigOrderAndStatus` | PUT (Student) | Update template ordering and active/inactive status |

### Academic & Skill Configuration

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getAcademicStudentData` | `/students/rankingConfig/{id}` | GET (Student) | Get specific ranking config (academic parameters) |
| `updateAcademictData` | `/students/rankingConfig/{mainbase}` | PUT (Student) | Update academic ranking parameters |
| `getSkillBucketData` | `/students/rankingConfig/{id}` | GET (Student) | Get skill bucket ranking configuration |
| `updateSkillBucketsData` | `/students/rankingConfig/SKILL_BUCKET` | PUT (Student) | Update skill bucket ranking parameters |

### Corporate Mapping

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `updateRankingCorporate` | `/corporates/mapRankingToCorporate` | PATCH (Corp) | Map ranking configuration to corporates. After success, refreshes both ranking-disabled and ranking-active corporate lists |

---

## State Shape

```js
{
  templateListStudent: [],
  academicStudentData: [],
  skillBucketData: []
}
```

---

## Key Features

- **Template-based ranking:** Multiple ranking templates (academic, skill bucket, etc.)
- **Ordering & status:** Drag-and-drop ordering with active/inactive toggle per template
- **Corporate mapping:** Enable/disable ranking for specific corporates via batch PATCH
- **Automatic list refresh:** After corporate mapping, refreshes both ranking-enabled and disabled lists
- **Skill bucket config:** Separate configuration for skill-based ranking parameters
