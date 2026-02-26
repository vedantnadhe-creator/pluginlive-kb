# Onboarding Module

**Routes (Anonymous):**
- `/onboarding/activate/:studentId` — Account activation
- `/not-interested/:studentId` — Not interested flow
- `/not-interested/final/:studentId` — Not interested confirmation

**Routes (Authenticated):**
- `/onboarding/final/:studentId` — Activation final page
- `/onboarding/register/:studentId` — Registration form
- `/onboarding/notification/:studentId` — Notification preferences setup

**Frontend:** `student-react/src/modules/Onboarding/`

## Overview

The Onboarding module manages the complete student activation and registration flow. It handles account activation (OTP verification, password creation), student data collection (personal info, education, skills, work experience), file uploads, not-interested opt-out, and initial notification setup. This is the largest student module (~813 lines in actions.js) with extensive master data lookups.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/activateContainer` | Activation | Account activation flow (OTP + password) |
| `Container/registerContainer` | Registration | Student registration form |
| `Components/ActivateAccount/FinalPage/FinalPage` | Final | Activation success page |
| `Components/NotInterested/NotIntrested/NotIntrested` | Not interested | Not interested form |
| `Components/NotInterested/FinalPage/FinalPageNI` | NI final | Not interested confirmation |
| `Register/Notification/Notification` | Notifications | Notification preference setup |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Student Data

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getStudentData` | `/students/{studentId}` | GET (Student) | Fetch student data. Also fetches last applied event/job if present |
| `updateStudentData` | `/students/{studentId}` | PUT (Student) | Update student profile. Syncs ES: `student_crud_skill`, `skill_master` |
| `updateCurrentState` | `/students/{studentId}/updateState` | PATCH (Student) | Update onboarding state (step tracking) |
| `updateStatusPending` | `/students/{studentId}/changeStatusToPanding` | PATCH (Student) | Change status to pending after registration |
| `updateCvDetails` | `/students/{studentId}/cvUpdate` | PUT (Student) | Update CV/resume URL |
| `updateUserProfile` | `/students/{studentId}/profileUpdate` | PUT (Student) | Update profile photo URL |
| `deleteEducation` | `/students/education/{educationId}` | DELETE (Student) | Delete education record. Validates: blocks 12th deletion for UG students |

### Authentication

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `sendOtp` | `/user/sendotp/{studentId}` | POST (Auth) | Send OTP for account activation |
| `checkOtp` | `/user/verifyotp/{studentId}/{otp}` | POST (Auth) | Verify OTP. Sets token, initializes app |
| `resetPwd` | `/user/resetpassword/studentRegistration` | PUT (Auth) | Create password during registration |

### Not Interested & Status

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `notInterested` | `/students/{studentId}/notintrested` | POST (Student) | Submit not interested status |
| `activeStatus` | `/students/{studentId}/status` | POST (Student) | Update student active status |

### Master Data (ElasticSearch/Search)

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getListOfCountries` | `/search/countries` | GET (Search) | Country list with search (pageLimit=50) |
| `getListOfState` | `/search/states` | GET (Search) | State list filtered by countryId |
| `getListOfCity` | `/search/cities` | GET (Search) | City list filtered by countryId, stateId |
| `getSkillList` | `/students/search/skills` | GET (Student) | Skill search (pageLimit=500) |
| `getListOfSkills` | `/students/skills/list` | POST (Student) | Skill list with IDs filter |
| `searchAPI` | `/search/{type}` or `/students/crud/skill` | POST/GET (Search) | Generic search. Skills use GET with params; others use ES POST |
| `getEligibilityCriteria` | `/search/degrees/streams/specialisations/events` | POST (Search) | Degree-stream-specialisation search with institute campus filter |

### Education & Career Data

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getDegreeData` | `/institutes/search/degrees` | GET (Inst) | Degree list with type filter (UG/PG/PHD/DIPLOMA/P_G_DIPLOMA) |
| `getCrudDegreeData` | `/institutes/search/degrees?status=1` | GET (Inst) | Active degrees only |
| `getCrudDepartmentData` | `/institutes/search/streams` | GET (Inst) | Active departments/streams |
| `getCrudSpecialisationData` | `/institutes/search/specialisations` | GET (Inst) | Active specialisations |
| `getUniversityList` | `/institutes/search/universities` | GET (Inst) | University search |
| `getCollege` | `/institutes/campus/{campusId}` | GET (Inst) | Campus details |
| `getFunctionsList` | `/functions` | GET (Corp) | Job functions list |
| `getDesignationsList` | `/designations` | GET (Corp) | Designations filtered by functionId |
| `getIndustryList` | `/industries` | GET (Corp) | Industry list |

### File Management

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `uploadFile` | `/signedURL` | POST (Auth) | Get S3 signed URL, then PUT file |
| `deleteFile` | `/deleteFile` | DELETE (Auth) | Delete uploaded file |

### Notification

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `updateNotification` | `/user/{userId}/notification-preference` | PUT (Auth) | Set notification preferences during onboarding |

---

## Key Features

- **Multi-step onboarding:** Activation → OTP → Password → Registration → Notification setup
- **State tracking:** `updateCurrentState` tracks which onboarding step the student is on
- **Not interested flow:** Separate anonymous flow for students who don't want placement
- **Education validation:** Blocks deletion of mandatory 12th standard for UG students
- **Degree type mapping:** `pgdiploma` → `P_G_DIPLOMA`, `ug`/`pg`/`phd` uppercased
- **Skill search dual path:** Skills use REST GET; other types use ElasticSearch POST
- **ES sync:** Student data updates sync `student_crud_skill` and `skill_master`
- **Token initialization:** After OTP verification, sets token and calls `initializeApp`
- **External event tracking:** Fetches last applied event/job for contextual display
