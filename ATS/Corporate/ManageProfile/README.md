# Manage Profile Module

**Route:** `/manageprofile`
**Frontend:** `corporate-react-1/src/modules/ManageProfile/`

## Overview

The Manage Profile module allows authenticated corporate users to manage their own account — update personal details, change passwords, configure notification preferences, upload files, and verify phone numbers via OTP.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Profile management page |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Profile Management

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `updateUserData` | `/user/{userId}` | PUT | Update user profile. Shows success message, refreshes user info via `getUserInfo()` |
| `changePassword` | `/user/{userId}/password` | PATCH | Change user password |
| `updateNotification` | `/user/{userId}/notification-preference` | PUT | Update notification preferences |

### Phone Verification

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `SendOtp` | `/users/{userId}/sendotp` | POST | Send OTP to phone. Uses `authRequested` util |
| `checkOtp` | `/users/{userId}/phone` | PATCH | Verify OTP and update phone number. Uses `authRequested` util |

### File Management

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `uploadFile` | `/signedURL` | POST | Get signed URL for file upload, then uploads to S3 via `axios.put` |
| `deleteFile` | `/deleteFile` | DELETE | Delete an uploaded file |
| `getFile` | (S3 signed URL) | PUT | Upload file to S3 using signed URL |

---

## Key Features

- **S3 file upload:** Two-step process — get signed URL, then PUT file to S3
- **OTP phone verification:** Uses `authRequested` (separate auth service) for OTP
- **User info refresh:** `getUserInfo()` dispatched after profile update to refresh auth state
- **Content-type handling:** File uploads set correct MIME type from `file.type`
