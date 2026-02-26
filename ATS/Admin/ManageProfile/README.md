# Manage Profile Module

**Route:** `/manageprofile`
**Frontend:** `admin-react/src/modules/ManageProfile/`

## Overview

The Manage Profile module allows authenticated admin users to manage their own account — update personal details, change passwords, and verify phone/email via OTP.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `index.js` | Main page | Profile management UI |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Profile Management

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getUserPreference` | `/user/{userId}` | GET (Auth) | Fetch current user data |
| `updateUserData` | `/user/{userId}` | PUT (Auth) | Update personal info. Refreshes via `getUserInfo()` on success |
| `changePassword` | `/user/{userId}/password` | PATCH (Auth) | Change user password |

### OTP Verification

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `SendOtp` | `/users/{userId}/sendotp` | POST (Auth) | Send OTP for phone/email verification |
| `checkPhoneOtp` | `/users/{userId}/phone` | PATCH (Auth) | Verify phone OTP |
| `checkEmailOtp` | `/users/{userId}/email` | PATCH (Auth) | Verify email OTP |

---

## Key Features

- **Dual OTP verification:** Both phone and email OTP flows (unlike Institute/Corporate which only have phone)
- **Auth service:** All calls go through `authRequest` utility
- **User info refresh:** Calls `getUserInfo()` after profile update
