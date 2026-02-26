# Manage Profile Module

**Route:** `/manageprofile`
**Frontend:** `institute-react/src/modules/ManageProfile/`

## Overview

The Manage Profile module allows authenticated TPO/admin users to manage their own account profile. It supports updating personal details, changing passwords, configuring notification preferences, and updating phone numbers with OTP verification.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Profile management page |
| `Components/PhoneModel/` | Phone modal | Phone number update with OTP flow |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `updateUserData` | `/user/{userId}` | PUT | Update user profile details (name, email, etc.) |
| `changePassword` | `/user/{userId}/password` | PATCH | Change user password |
| `updateNotification` | `/user/{userId}/notification-preference` | PUT | Update notification preferences |
| `SendOtp` | `/users/{userId}/sendotp` | POST | Send OTP to phone number. Rate-limited to 1 per minute |
| `checkOtp` | `/users/{userId}/phone` | PATCH | Verify OTP and update phone number |
| `deleteFile` | `/deleteFile` | DELETE | Delete an uploaded file (e.g., profile image) |

---

## Key Features

- **OTP-based phone verification:** Send OTP → verify → update phone number
- **Rate limiting:** OTP requests limited to once per minute (400 error if too frequent)
- **Notification preferences:** Toggle email/push notification settings
- **File management:** Delete uploaded files (profile pictures, etc.)
- **Password change:** Separate PATCH endpoint for password updates
