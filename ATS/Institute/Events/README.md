# Events Module

**Route:** `/events`
**Frontend:** `institute-react/src/modules/Events/`

## Overview

The Events module enables TPO users to create, manage, and track placement events (campus drives, job fairs, etc.). It supports event creation with eligibility criteria, calendar and list views, draft management, bulk student upload for events, conflict resolution, and event duplication.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `index.js` | Main page | Event listing and navigation |
| `Header/` | Page header | Title, filters, create button |
| `ListView/` | List view | Events displayed as a list |
| `WeekView/` | Calendar view | Weekly calendar display of events |
| `New Event/` | Create flow | Event creation form and steps |
| `New Event/EventForm/` | Form | Event details form (dates, eligibility, etc.) |
| `EventRole/` | Event roles | Roles associated with an event |
| `EventRole/EventUpload.js` | Upload | Event-specific file upload |
| `EventRole/Table/` | Table | Event role tabular data |
| `Partials/Drafts/` | Drafts | Draft event management |
| `Partials/EventDetails/` | Details | Detailed event view |
| `Partials/EventDraft/` | Draft view | Single draft event view |
| `Preview/` | Preview | Event preview before publishing |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Event CRUD

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `eventCreation` | `/institutes/events` | POST | Create a new event with instituteCampusId |
| `editEvent` | `/institutes/events/{eventId}` | PUT | Update event details |
| `deleteEvent` | `/institutes/events/{eventId}` | DELETE | Delete an event |
| `duplicateEvent` | `/institutes/events/{eventId}/duplicate` | POST | Duplicate an existing event |
| `updateEventStatus` | `/institutes/events/{eventId}/status` | PUT | Change event status (draft → active, etc.) |

### Event Listing

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getListofEventsForCollege` | `/institutes/events/instituteCampus/{id}/list` | GET | Main event listing with filters (category, year, degree, department, search, occurrence, calendar mode, drafts) |
| `getListOfEventsForStudent` | `/institutes/events/instituteCampus/{id}/list?status=1` | GET | Active events for student context |
| `getEventByEventID` | `/institutes/events/{eventId}` | GET | Single event details |
| `getListofEventsFiltersForCollege` | `/institutes/eventsFilter/instituteCampus/{id}/list` | GET | Available filter options for events |

### Eligibility & ElasticSearch

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getEligibilityCriteria` | `/search/degrees/streams/specialisations/events` | POST | ElasticSearch-based eligibility lookup for event creation. Filters by instituteCampuseId, course status, degree type |

### Bulk Upload & Conflicts

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `bulkUploadForEvents` | `/students/event/{eventId}/instituteCampus/{id}/bulkUpload` | POST | Bulk upload students for an event |
| `resolveConflict` | `/institutes/instituteCampus/{id}/event/{eventId}/conflict/candidates` | GET | List conflicting candidates for an event |

### Candidate Export

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| — | `/students/event/{eventsId}/instituteCampus/{id}/export/{downloadType}` | PUT | Export the event's candidate list (Invited / Registered students) as an Excel file or Google Sheet |

**Backend:** `student-node` → `app/handlers/companymasterHandler.js` → `exportEventCandidateList`
(`exportEventCandidateList_old` is dead code, kept only for reference.)

Query params: `eventName`, `instituteName`, `displayname` (e.g. `Invited Student` — used for the
"<displayname> Count" row), `forPage`, and `Reg` which selects the column set:

| `Reg` | Columns |
|-------|---------|
| `1` | Registered Date, Registration No., Student Name, Email, Mobile, Degree Type, Degree, Department, Specialisation, Batch (+ `Status` = Paid/UnPaid when the event has a `registerAmount`) |
| `0` | Same, without Registered Date and Status |
| unset | Same as `0`, with Registered Date prepended when the event is a registered event |

Rows 1–3 of the sheet carry Event Name, `<displayname> Count`, and College Name; the header row is row 4.

**Batch column:** built by `getBatchLabel(currentCourse.startedOn, currentCourse.endedOn)`. Both are epoch
timestamps (seconds or ms). A `0`/missing timestamp means "not set", so it is dropped rather than
formatted — a student with no `startedOn` shows `2026`, not `1970 - 2026`. Both present → `2022 - 2026`;
both missing → empty cell.

### Other

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getSpecialisationList` | `/institutes/specialitationList` | POST | Specialisation list for eligibility |

---

## Key Features

- **Calendar view:** `forCalendar=true` returns all active events for calendar rendering
- **Draft support:** Events can be saved as drafts (`status=0`) before publishing
- **Occurrence filter:** upcoming / ongoing / completed
- **Sorting:** `showAll` (desc by createdAt), `dateWise` (asc by createdAt), `forRecentlyAdded`
- **Register event mode:** `forRegisterEvent=true` for registration flow
- **Conflict resolution:** Detect and resolve student scheduling conflicts across events
