# Users Module

**Route:** `/users`
**Frontend:** `corporate-react-1/src/modules/Users/`

## Overview

The Users module manages corporate portal user accounts. It provides full CRUD operations, role assignment, status management, and multi-channel notification capabilities (email, WhatsApp, in-app).

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | User listing and management |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### User CRUD

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getUserMetrics` | `/users/metrics?corporateID={corpId}` | GET | User count metrics for the corporate |
| `getUserList` | `/user?pageLimit=10&currentPage={n}&coporateId={corpId}` | GET | Paginated user list with search, sort, role filter, status filter |
| `createUser` | `/user` | POST | Create user with `corporateId` and `journey: 'CORPORATE'` |
| `getSingleUser` | `/user/{userId}` | GET | Fetch individual user details |
| `updateUser` | `/user/{userId}` | PUT | Update user with `corporateId` |
| `updateUserStatus` | `/user/{userId}/status` | PATCH | Activate/deactivate a user |
| `deleteUser` | `/user/{userId}` | DELETE | Delete a user |

### Notifications

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getNotificationCatalogues` | `/notificationCatalogue` | GET | Available notification templates (filtered by eventId, subEventId) |
| `sendNotificationEmail` | `/notification/email` | POST | Send email notification |
| `sendNotificationBulkEmail` | `/notification/bulkEmail` | POST | Bulk email notification |
| `sendNotificationBulkEmailWhatsapp` | `/notification/bulkWhatsapp` | POST | Bulk WhatsApp notification |
| `sendNotificationWhatsapp` | `/notification/whatsapp` | POST | Single WhatsApp notification |
| `sendInAppNotification` | `/users/createNotification` | POST | In-app notification |
| `getUserCorpList` | `/user?instituteCampusId={id}&status=true` | GET | Active users for a corporate |

---

## Key Features

- **Corporate journey:** Users are created with `journey: 'CORPORATE'`
- **Multi-channel notifications:** Email, WhatsApp, in-app, and bulk variants
- **Role & status filters:** Filter users by role and active/inactive status
- **Notification catalogues:** Template-based notifications with event/sub-event filtering
- **Pagination:** `pageLimit=10`, `currentPage` (0-indexed)
