# Manage Profile Module

**Route:** `/manageprofile`
**Frontend:** `student-react/src/modules/ManageProfile/`

## Overview

The Manage Profile module provides account settings for students — view user preferences, verify phone and email via OTP, manage notification preferences, and send notifications. It supports multi-channel notifications (email, WhatsApp, in-app).

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Profile settings page |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Profile & Preferences

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getUserPreference` | `/user/{userId}` | GET (Auth) | Fetch user preference data |

### OTP Verification

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `SendOtp` | `/users/{userId}/sendotp` | POST (authRequested) | Send OTP for verification. Uses `authRequested` util |
| `checkEmailOtp` | `/users/{userId}/email` | PATCH (authRequested) | Verify email OTP |
| `checkPhoneOtp` | `/users/{userId}/phone` | PATCH (Auth) | Verify phone OTP |

### Notifications

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getNotificationCatalogues` | `/notificationCatalogue` | GET (Admin) | Available notification templates |
| `sendNotificationEmail` | `/notification/email` | POST (Auth) | Send email notification |
| `sendNotificationBulkEmail` | `/notification/bulkEmail` | POST (Auth) | Bulk email notification |
| `sendNotificationBulkEmailWhatsapp` | `/notification/whatsapp` | POST (Auth) | WhatsApp notification |
| `sendInAppNotification` | `/users/createNotification` | POST (Auth) | In-app notification |

---

## Key Features

- **Dual OTP:** Both email and phone verification via OTP
- **Multi-channel notifications:** Email, bulk email, WhatsApp, in-app
- **Two auth utils:** `authRequested` for OTP send/email verify, `authRequest` for phone verify
- **Notification catalogues:** Template-based notification selection
