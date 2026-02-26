# Events Module

**Route:** `/events`
**Frontend:** `student-react/src/modules/Events/`

## Overview

The Events module displays campus events for the student. It supports paginated event listing, calendar view, category filtering, search, sorting, and event registration. Events are scoped to the student's institute campus.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Events listing with calendar and filters |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getEventsList` | `/institutes/instituteCampus/{campusId}/student/{studentId}/events` | GET (Inst) | Events list. Params: pageLimit, pageNo, search, category, sort, from, occurence, forCalendar, forRegisterEvent, forRecentlyAdded. Calendar mode uses `forCalendar=true` only |
| `getEventDetailsById` | `/institutes/events/{eventId}/student/{studentId}` | GET (Inst) | Single event detail with student-specific data |
| `registerEvent` | `/students/events/instituteCampusId/{campusId}/studentId/{studentId}/registration` | POST (Student) | Register for an event with payload |

---

## Key Features

- **Calendar view:** `forCalendar=true` returns dates-only data for calendar rendering
- **Category filtering:** Filter events by category
- **Occurrence filter:** Upcoming/ongoing/completed events
- **Recently added:** `forRecentlyAdded=true` with `sort=createdAt&order=desc`
- **Event registration:** Students can register for events directly
- **Institute-scoped:** Events are scoped to the student's institute campus
