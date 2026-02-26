# Event Catalogue Module

**Route:** `/eventcatalogue`
**Frontend:** `admin-react/src/modules/EventCatalogue/`

## Overview

The Event Catalogue module manages the notification event system — events, sub-events, notification types, templates, and the mapping between them. Admins can configure which notification channels (email, SMS, WhatsApp, in-app) are available for each event, manage templates, and reorder event priority.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Event catalogue management page |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Event Management

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getEventList` | `/screens` | GET (Admin) | Paginated event/screen list filtered by journey. `pageLimit=500` |
| `DeleteEvent` | `/events/{id}` | DELETE (Admin) | Delete an event |
| `DeleteSubEvent` | `/subEvents/{id}` | DELETE (Admin) | Delete a sub-event |
| `reorderEvent` | `/screens` | PUT (Admin) | Reorder events/screens |

### Notification Types

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getNotificationType` | `/notificationType` | GET (Admin) | List notification types (pageLimit=10) |
| `getNotificationTypeByID` | `/notificationType/{id}` | GET (Admin) | Single notification type details |

### Notification Templates

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `GetAllNotificationTemplate` | `/notificationTemplate` | GET (Admin) | Template list filtered by notificationTypeId and eventId |
| `AddNewNotificationTemplate` | `/notificationTemplate` | POST (Admin) | Create new notification template |
| `EditNewNotificationTemplate` | `/notificationTemplate/{id}` | PUT (Admin) | Update existing template |
| `DeleteNewNotificationTemplate` | `/notificationTemplate/{id}` | DELETE (Admin) | Delete a template |

### Notification Catalogue Mapping

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getNotificationCatalogues` | `/notificationCatalogue` | GET (Admin) | Get catalogue entries (event-channel-template mappings) |
| `ManageNotificationCatalogue` | `/notificationCatalogue` | POST (Admin) | Map event to notification channel with template |

---

## Key Features

- **Event hierarchy:** Events → Sub-events with ordering support
- **Multi-channel:** Email, SMS, WhatsApp, in-app notification channels
- **Template management:** Full CRUD for notification templates per type
- **Event-channel mapping:** Connect events to notification channels with specific templates
- **Journey-scoped:** Events filterable by journey (ADMIN, CORPORATE, INSTITUTE)
- **Reordering:** Drag-and-drop event priority ordering
