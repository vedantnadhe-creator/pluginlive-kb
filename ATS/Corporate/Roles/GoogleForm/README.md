# Google Form — Application Form for ITI/Diploma Roles

## Overview

When a corporate user selects **ITI** or **Diploma** in the Eligibility Criteria during role creation, the standard **"Qualifying Questions"** step (Step 5) is replaced with an **"Application Form"** step. This Application Form is powered by Google Forms and serves as the primary data collection mechanism for ITI/Diploma candidates who are not registered on the PluginLive platform.

**Key Difference from Regular Roles:**
- Regular roles (UG/PG): Candidates apply via the PluginLive student portal → Qualifying Questions are in-app
- ITI/Diploma roles: Candidates apply via a **Google Form link** shared by their college → responses are collected externally

---

## Current State (Codebase Analysis)

> **This feature does NOT exist yet.** The sections below document what currently exists and what needs to be built.

### What Exists Today

| Area | Current State | File |
|------|--------------|------|
| **Role creation steps** | Fixed 7-step flow; Step 5 is always "Qualifying Questions" (`QualifyQuestions` component) | `corporate-react-1/src/modules/Roles/NewRoleCreation/index.js` → `stepFlow` array |
| **Eligibility criteria** | Stores `eligibilityCriteria` JSON on `job_roles` table; includes `degreeType` field (UG, PG, DIPLOMA, etc.) — but no logic to switch step 5 based on degree type | `corporate-node-1/prisma/schema.prisma` → `jobRoles.eligibilityCriteria` (JSON) |
| **Role update handler** | `editJobRole` → calls `handleEligibility()` to process eligibility — no application form handling | `corporate-node-1/app/handlers/corporateJobRoleHandler.js:240` |
| **Publish handler** | `rolePublishCorporate` creates `jobRoleInstituteMap` entries per college — no Google Form creation | `corporate-node-1/app/handlers/corporateJobRoleHandler.js:1470` |
| **Google Drive auth** | Service account (`auth_creds.json`) with Google Drive API scope already configured for `uploadGoogleSheet` export feature | `corporate-node-1/app/helpers/utils.js:727` |
| **`job_role_institute_map`** | Has: `id`, `institute_campus_id`, `job_id`, `status`, `saved`, `rejected_reason`, `role_status` — **no form URL fields** | `corporate-node-1/prisma/schema.prisma` → `jobRoleInstituteMap` |
| **`job_roles`** | Has: `applicationFormTemplate` — **does not exist yet**, needs to be added | `corporate-node-1/prisma/schema.prisma` → `jobRoles` |

### Existing Google Auth Setup

The project already has Google API auth configured for candidate list export (Google Sheets):

```
File: corporate-node-1/app/helpers/utils.js → uploadGoogleSheet()
Auth: auth_creds.json (Service Account)
Scopes: ["https://www.googleapis.com/auth/drive"]
Package: googleapis
```

The `auth_creds.json` file is deployed via CI/CD:
- `.github/workflows/dev-corporate.yml` copies it from server credentials
- Listed in `.gitignore` (not committed to repo)

**To support Google Forms API**, the existing service account needs:
- Additional scope: `https://www.googleapis.com/auth/forms.body`
- Google Forms API enabled in the Google Cloud project

---

## Feature Flow

### 1. Role Creation — Application Form Step

During role creation, if ITI/Diploma is selected in Eligibility Criteria:

```
Corporate Details → Job Details → CTC & Job Location → Eligibility Criteria
    → [Application Form] ← (replaces Qualifying Questions)
    → Evaluation Process → Preview
```

**Frontend:** `corporate-react-1/src/modules/Roles/NewRoleCreation/`

**Current code to modify:** `NewRoleCreation/index.js` → `stepFlow` array:

```javascript
// Current (line 59-65):
{
  key: 5,
  activeKey: 4,
  title: 'Qualifying Questions',   // ← always this
  completed: false,
  component: QualifyQuestions,      // ← always this
}

// Needed: conditionally switch based on eligibility criteria degreeType
```

The `stepFlow` is currently a static array defined at module level. It needs to become dynamic, reacting to eligibility criteria changes from Step 4.

**Key files for step flow:**
- `corporate-react-1/src/modules/Roles/NewRoleCreation/index.js` — `stepFlow` definition, `stepData` state
- `corporate-react-1/src/modules/Roles/NewRoleCreation/Partials/RoleCreateForm/index.js` — Form orchestration, `currentStep`, `setStepData`
- `corporate-react-1/src/modules/Roles/NewRoleCreation/Partials/RoleCreateForm/Partials/EligibiltyCriteria/index.js` — Where degree type is selected

### 2. Application Form Template

The Application Form consists of **Mandatory Questions** (predefined template) and **Custom Questions** (user-added).

#### Mandatory Questions — Diploma Template

| # | Question | Response Type | Required |
|---|----------|---------------|----------|
| 1 | First Name | Short Answer | Yes |
| 2 | Last Name | Short Answer | Yes |
| 3 | Date of Birth | Date | Yes |
| 4 | Gender | Multiple Choice (Male, Female, Others) | Yes |
| 5 | Primary Email Address | Short Answer | Yes |
| 6 | Secondary Email Address | Short Answer | No |
| 7 | Mobile Number | Short Answer | Yes |
| 8 | Alternative Mobile Number | Short Answer | No |
| 9 | Permanent Address – State | Dropdown (state list) | Yes |
| 10 | Permanent Address – City | Short Answer | Yes |
| 11 | Permanent Address – Pincode | Short Answer | Yes |
| 12 | Current Address – State | Dropdown (state list) | Yes |
| 13 | Current Address – City | Short Answer | Yes |
| 14 | Current Address – Pincode | Short Answer | Yes |
| 15 | 10th – Year | Short Answer | Yes |
| 16 | 10th – Marks (in %) | Short Answer | Yes |
| 17 | 12th – Year | Short Answer | No |
| 18 | 12th – Marks (in %) | Short Answer | No |
| 19 | 12th – Marks (in %) | Short Answer | No |
| 20 | Diploma – College Name | Short Answer | Yes |
| 21 | Diploma – City | Short Answer | Yes |
| 22 | Diploma – Degree | Short Answer | Yes |
| 23 | Diploma – Department/Trade | Short Answer | Yes |
| 24 | Diploma – End Year | Short Answer | Yes |
| 25 | Diploma – Marks (in %) | Short Answer | Yes |
| 26 | Diploma – No. of Current Arrears/Backlogs/KT | Short Answer | Yes |
| 27 | Diploma – No. of Past Arrears/Backlogs/KT | Short Answer | Yes |

#### Mandatory Questions — ITI Template

| # | Question | Response Type | Required |
|---|----------|---------------|----------|
| 1 | First Name | Short Answer | Yes |
| 2 | Last Name | Short Answer | Yes |
| 3 | Date of Birth | Date | Yes |
| 4 | Gender | Multiple Choice (Male, Female, Others) | Yes |
| 5 | Primary Email Address | Short Answer | Yes |
| 6 | Secondary Email Address (Non-Mandatory) | Short Answer | No |
| 7 | Mobile Number | Short Answer | Yes |
| 8 | Alternative Mobile Number (Non-Mandatory) | Short Answer | No |
| 9 | Permanent Address – State | Dropdown (state list) | Yes |
| 10 | Permanent Address – City | Short Answer | Yes |
| 11 | Permanent Address – Pincode | Short Answer | Yes |
| 12 | Current Address – State | Dropdown (state list) | Yes |
| 13 | Current Address – City | Short Answer | Yes |
| 14 | Current Address – Pincode | Short Answer | Yes |
| 15 | ITI – College name | Short Answer | Yes |
| 16 | ITI – City | Short Answer | Yes |
| 17 | ITI – Degree | Short Answer | Yes |
| 18 | ITI – Department/Trade | Short Answer | Yes |
| 19 | ITI – End Year | Short Answer | Yes |
| 20 | ITI – Marks (in %) | Short Answer | Yes |
| 21 | ITI – No. of Current arrears/Backlogs/KT | Short Answer | Yes |
| 22 | ITI – No. of Past Arrears/Backlogs/KT | Short Answer | Yes |

> **Note:** ITI template does not include 10th or 12th standard fields, focusing directly on ITI education details.

### 3. Supported Response Types

The Application Form builder supports the following response types for both mandatory and custom questions:

| Response Type | Description | Example |
|---------------|-------------|---------|
| **Short Answer** | Single-line text input | First Name, Mobile Number |
| **Paragraph** | Multi-line text input | Address details |
| **Multiple Choice** | Radio button selection (single select) | Gender (Male / Female / Others) |
| **Checkboxes** | Checkbox selection (multi select) | Skills, Preferences |
| **Dropdown** | Dropdown selection (single select) | Permanent Address – State |
| **Date** | Date picker (Month, Day, Year) | Date of Birth |

### 4. Custom Questions

Corporate users can add custom questions beyond the mandatory template:

- Click **"Add Custom Questions"** button at the bottom of the Application Form
- Select response type from the supported types above
- Enter question text
- For Multiple Choice / Checkboxes / Dropdown: add options with add/delete capability
- Toggle **Required** on/off per question
- Custom questions can be duplicated or deleted (trash/copy icons)

### 5. Expand and Edit Mandatory Questions

- Corporate users can click **"Expand and Edit"** on the Mandatory Questions section
- This opens an editable view where each mandatory question can be:
  - Modified (question text)
  - Toggled required/non-required
  - Response type changed
- Click **"Save and Collapse"** to save changes

---

## Data Storage

### Application Form Template — New Column on `job_roles` Table

The application form template (mandatory + custom questions) needs to be stored as JSON against the job role.

**Table:** `corporate.job_roles`
**New Field:** `application_form_template` (JSONB) — **does not exist yet**

**Current `job_roles` schema** (`corporate-node-1/prisma/schema.prisma:103-204`):
- Already has `eligibilityCriteria Json?` which stores degree type info including `degreeType` (UG, PG, DIPLOMA, etc.)
- Already has `priorityDegree String?` — stores priority degree type like `UG_DIPLOMA`
- The `applicationFormTemplate` field needs to be added

```json
{
  "templateType": "DIPLOMA",
  "mandatoryQuestions": [
    {
      "id": "q1",
      "question": "First Name",
      "responseType": "SHORT_ANSWER",
      "required": true,
      "options": []
    },
    {
      "id": "q4",
      "question": "Gender",
      "responseType": "MULTIPLE_CHOICE",
      "required": true,
      "options": ["Male", "Female", "Others"]
    },
    {
      "id": "q9",
      "question": "Permanent Address – State",
      "responseType": "DROPDOWN",
      "required": true,
      "options": ["Karnataka", "Tamil Nadu", "Kerala", "Pondicherry", "Andhra Pradesh", "Telangana", "..."]
    },
    {
      "id": "q3",
      "question": "Date of Birth",
      "responseType": "DATE",
      "required": true,
      "options": []
    }
  ],
  "customQuestions": [
    {
      "id": "cq1",
      "question": "Do you have a laptop?",
      "responseType": "MULTIPLE_CHOICE",
      "required": true,
      "options": ["Yes", "No"]
    }
  ]
}
```

**Template Types:** `ITI`, `DIPLOMA`

**Response Type Enum Values:**
- `SHORT_ANSWER`
- `PARAGRAPH`
- `MULTIPLE_CHOICE`
- `CHECKBOXES`
- `DROPDOWN`
- `DATE`

### Google Form URL — New Columns on `job_role_institute_map` Table

After role publish, a unique Google Form is created per college. The form URL needs to be stored in the institute mapping.

**Table:** `corporate.job_role_institute_map`

**Current schema** (`corporate-node-1/prisma/schema.prisma:234-249`):
```prisma
model jobRoleInstituteMap {
  id                String          @id @default(uuid())
  createdAt         DateTime        @default(now()) @map("created_at")
  updateAt          DateTime        @updatedAt @map("updated_at")
  instituteCampusId String          @map("institute_campus_id")
  status            Int             @default(0)
  saved             Int             @default(0)
  rejectedReason    rejectedReason? @map("rejected_reason")
  otherReason       String?         @map("other_reason")
  jobId             String          @map("job_id")
  roleStatus        roleStatus      @default(DRAFT) @map("role_status")
  jobRoles          jobRoles        @relation(fields: [jobId], references: [id])
  // ⬇️ NEW FIELDS NEEDED:
  // googleFormId          String?  @map("google_form_id")
  // googleFormUrl         String?  @map("google_form_url")
  // googleFormResponseUrl String?  @map("google_form_response_url")
}
```

**New Fields Needed:**

| Column | Type | Description |
|--------|------|-------------|
| `google_form_id` | `String?` | Google Form ID (from Google Forms API) |
| `google_form_url` | `String?` | Public URL of the Google Form for this college |
| `google_form_response_url` | `String?` | Google Sheets response URL linked to the form |

---

## Publish Flow — Google Form Creation

### Current Publish Flow (`corporate-node-1`)

**Handler:** `corporateJobRoleHandler.rolePublishCorporate` (`corporate-node-1/app/handlers/corporateJobRoleHandler.js:1470`)
**Route:** `POST /corporates/jobs/:jobId/publish` (`corporate-node-1/app/routes/corporateJobRole.js:58-63`)

Current flow:
1. Receives `instituteCampusIds`, `corporateId`, `groupIds`, `degreeStreamMapIds`
2. Resolves institute IDs from groups via `instituteService.getInstituteCampusIdByGroup`
3. Combines and deduplicates campus IDs
4. Gets matching IDs based on `degreeStreamMapId` + `campusIds`
5. Filters out already-existing mappings
6. Creates `jobRoleInstituteMap` entries per college via `jobRoleInstituteMap.create({ jobId, instituteCampusId })`
7. Also creates `driveRoleMap` and `interview` records

**Model:** `JobRoleInstituteMap.create()` (`corporate-node-1/app/models/JobRoleInstituteMap.js:49-57`)
```javascript
async create({ jobId, instituteCampusId }) {
  const data = await prisma.jobRoleInstituteMap.create({
    data: { jobId, instituteCampusId },
  });
  await this.jobRoleMetricsModel.createOrUpdate({ jobId, instituteCampusId });
  return data;
}
```

### New Publish Flow (To Be Built)

After the existing `jobRoleInstituteMap.create()`, add Google Form creation:

```
1. Corporate selects colleges in "Select Colleges" drawer
2. Clicks "Publish"
3. For each selected college (instituteCampusId):
   a. Create jobRoleInstituteMap entry (existing)
   b. [NEW] Check if role has applicationFormTemplate (ITI/Diploma)
   c. [NEW] If yes, call Google Forms API to create a new form
   d. [NEW] Set form title: "{Role Title} - {College Name} Application Form"
   e. [NEW] Add all mandatory + custom questions to the Google Form
   f. [NEW] Update jobRoleInstituteMap with google_form_id and google_form_url
4. Each college gets a unique Google Form link
5. TPO/College shares this link with their ITI/Diploma students
6. Students fill the form externally (no PluginLive login needed)
```

### Frontend Publish Flow

**Current publish:**
- `corporate-react-1/src/modules/Roles/actions.js` → `publishRole` action
- Calls `POST /corporates/jobs/${roleId}/publish` with payload: `{ instituteCampusIds, corporateId, groupIds, degreeStreamMapIds }`
- College selection happens in `NewRoleCreation/Partials/SelectCollegesDrawer/`

No frontend changes needed for publish — form creation happens server-side.

### API Flow

| Step | API | Method | Service | Status | Description |
|------|-----|--------|---------|--------|-------------|
| Save template | `/corporates/{corpId}/jobs/{jobId}` | PUT | corporate-node | **Existing** (add `applicationFormTemplate` to `handleJobDetails`) | Save application form template in job_roles |
| Publish with forms | `/corporates/jobs/{roleId}/publish` | POST | corporate-node | **Existing** (extend `rolePublishCorporate` to create forms) | Create Google Forms per college during publish |
| Get form URL | `/corporates/jobs/{roleId}/institute/{instituteCampusId}/form` | GET | corporate-node | **New** | Retrieve Google Form URL for a specific college |
| Sync responses | `/corporates/jobs/{roleId}/form/responses/sync` | POST | corporate-node | **New** | Sync Google Form responses back to candidate data |

---

## Schema Changes Required

### 1. `job_roles` Table — New Column

```sql
ALTER TABLE corporate.job_roles
ADD COLUMN application_form_template JSONB DEFAULT NULL;
```

**Prisma Schema (`corporate-node-1/prisma/schema.prisma`):**
```prisma
model jobRoles {
  // ... existing fields (line 103-204) ...
  applicationFormTemplate Json? @map("application_form_template")
}
```

### 2. `job_role_institute_map` Table — New Columns

```sql
ALTER TABLE corporate.job_role_institute_map
ADD COLUMN google_form_id VARCHAR(255) DEFAULT NULL,
ADD COLUMN google_form_url TEXT DEFAULT NULL,
ADD COLUMN google_form_response_url TEXT DEFAULT NULL;
```

**Prisma Schema:**
```prisma
model jobRoleInstituteMap {
  // ... existing fields (line 234-249) ...
  googleFormId          String?  @map("google_form_id")
  googleFormUrl         String?  @map("google_form_url")
  googleFormResponseUrl String?  @map("google_form_response_url")
}
```

### 3. Prisma Migration

```bash
cd corporate-node-1
npx prisma migrate dev --name add_google_form_fields
```

---

## Google Forms API Integration

### Service Account Setup

The project already has a Google Service Account (`auth_creds.json`) used for Google Sheets export.

**Current setup** (`corporate-node-1/app/helpers/utils.js:727-782`):
```javascript
const KEYFILEPATH = "auth_creds.json";
const SCOPES = ["https://www.googleapis.com/auth/drive"];
const auth = new google.auth.GoogleAuth({ keyFile: KEYFILEPATH, scopes: SCOPES });
```

**Changes needed:**
1. Add Google Forms API scope: `https://www.googleapis.com/auth/forms.body`
2. Enable **Google Forms API** in the Google Cloud Console project
3. The `googleapis` npm package is already installed

### Key Operations

| Operation | Google API | Purpose |
|-----------|-----------|---------|
| Create Form | `forms.create` | Create a blank Google Form |
| Update Form | `forms.batchUpdate` | Add questions, set title, configure settings |
| Get Responses | `forms.responses.list` | Fetch submitted responses |
| Watch Responses | `forms.watches.create` | (Optional) Set up push notifications for new responses |

### New Utility Function (add to `corporate-node-1/app/helpers/utils.js`)

```javascript
const { google } = require('googleapis');

exports.createGoogleForm = async (roleTitle, collegeName, questions) => {
  const KEYFILEPATH = "auth_creds.json";
  const SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/forms.body",
  ];
  const auth = new google.auth.GoogleAuth({ keyFile: KEYFILEPATH, scopes: SCOPES });
  const client = await auth.getClient();
  const forms = google.forms({ version: 'v1', auth: client });

  // 1. Create blank form
  const form = await forms.forms.create({
    requestBody: {
      info: { title: `${roleTitle} - ${collegeName} Application Form` },
    },
  });

  const formId = form.data.formId;

  // 2. Add questions via batchUpdate
  const requests = questions.map((q, index) => ({
    createItem: {
      item: {
        title: q.question,
        questionItem: {
          question: {
            required: q.required,
            ...buildQuestionType(q.responseType, q.options),
          },
        },
      },
      location: { index },
    },
  }));

  await forms.forms.batchUpdate({ formId, requestBody: { requests } });

  // 3. Make form public
  const driveService = google.drive({ version: 'v3', auth: client });
  await driveService.permissions.create({
    fileId: formId,
    resource: { type: 'anyone', role: 'writer' },
  });

  return {
    formId,
    formUrl: `https://docs.google.com/forms/d/${formId}/viewform`,
  };
};

function buildQuestionType(responseType, options = []) {
  switch (responseType) {
    case 'SHORT_ANSWER':
      return { textQuestion: { paragraph: false } };
    case 'PARAGRAPH':
      return { textQuestion: { paragraph: true } };
    case 'MULTIPLE_CHOICE':
      return { choiceQuestion: { type: 'RADIO', options: options.map(o => ({ value: o })) } };
    case 'CHECKBOXES':
      return { choiceQuestion: { type: 'CHECKBOX', options: options.map(o => ({ value: o })) } };
    case 'DROPDOWN':
      return { choiceQuestion: { type: 'DROP_DOWN', options: options.map(o => ({ value: o })) } };
    case 'DATE':
      return { dateQuestion: { includeTime: false } };
    default:
      return { textQuestion: { paragraph: false } };
  }
}
```

---

## Frontend Components

### New Components Needed

| Component | Path | Purpose |
|-----------|------|---------|
| `ApplicationForm/index.js` | `RoleCreateForm/Partials/ApplicationForm/` | Main Application Form step component |
| `ApplicationForm/MandatoryQuestions.js` | Same folder | Renders mandatory question list with expand/edit |
| `ApplicationForm/CustomQuestions.js` | Same folder | Custom question builder (add/edit/delete) |
| `ApplicationForm/QuestionCard.js` | Same folder | Single question card with type selector, options, required toggle |
| `ApplicationForm/templates.js` | Same folder | ITI and Diploma mandatory question templates |

**Base path:** `corporate-react-1/src/modules/Roles/NewRoleCreation/Partials/RoleCreateForm/Partials/ApplicationForm/`

### Step Flow Modification

**File:** `corporate-react-1/src/modules/Roles/NewRoleCreation/index.js`

Current `stepFlow` (line 30-80) is a static array. Step 5 (index 4, activeKey 4) is always `QualifyQuestions`.

**Change:** Make `stepFlow` dynamic based on eligibility criteria `degreeType`:

```javascript
// Current (line 59-65):
{
  key: 5,
  activeKey: 4,
  title: 'Qualifying Questions',
  completed: false,
  component: QualifyQuestions,
}

// New: conditionally switch based on eligibility criteria
{
  key: 5,
  activeKey: 4,
  title: isITIOrDiploma ? 'Application Form' : 'Qualifying Questions',
  completed: false,
  component: isITIOrDiploma ? ApplicationForm : QualifyQuestions,
}
```

The `isITIOrDiploma` flag is derived from the eligibility criteria `degreeType` field set in Step 4 (`EligibiltyCriteria` component).

### Backend Handler Modifications

**File:** `corporate-node-1/app/handlers/corporateJobRoleHandler.js`

1. **`handleJobDetails()` (line 497)** — Add `applicationFormTemplate` to `fieldsToUpdate` object
2. **`rolePublishCorporate()` (line 1470)** — After `jobRoleInstituteMap.create()`, check for `applicationFormTemplate` and call `createGoogleForm()` for each college

**File:** `corporate-node-1/app/models/JobRoleInstituteMap.js`

1. **`create()` (line 49)** — After creating the map entry, optionally pass back the created record for form URL update
2. Add new method: `updateFormUrl(id, { googleFormId, googleFormUrl })` for updating form URLs after creation

---

## Summary

| Aspect | Detail | Status |
|--------|--------|--------|
| **Trigger** | ITI or Diploma selected in Eligibility Criteria (Step 4) | To be built (frontend) |
| **Replaces** | Qualifying Questions (Step 5) | To be built (frontend) |
| **Template** | Predefined mandatory questions per type (ITI / Diploma) | To be built (frontend + backend) |
| **Custom Questions** | Supported with 6 response types | To be built (frontend) |
| **Storage (Template)** | `job_roles.application_form_template` (JSONB) | Schema change needed |
| **Storage (URLs)** | `job_role_institute_map.google_form_url` (per college) | Schema change needed |
| **Google Auth** | Service account already exists (`auth_creds.json`) — needs Forms API scope | Config change needed |
| **Form Creation** | Google Forms API at publish time — one form per college | To be built (backend) |
| **Candidate Access** | Public Google Form link — no PluginLive login needed | To be built |
| **Response Sync** | Google Form responses synced back to candidate data | To be built (backend) |
