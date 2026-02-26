# Auth Module

**Route:** `/signin` (anonymous)
**Frontend:** `institute-react/src/modules/Auth/`

## Overview

The Auth module handles user authentication for the institute portal. It provides the sign-in form and manages authentication state (tokens, user details, institute details) used across all other modules.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Sign-in page layout |
| `Components/UserSignin.js` | Sign-in component | Sign-in UI |
| `Components/SignInForm.js` | Sign-in form | Email/password form with validation |

---

## Redux Files

| File | Purpose |
|------|---------|
| `actions.js` | Auth API actions (login, logout, token refresh) |
| `reducers.js` | Auth state reducer (user, tokens, institute details) |
| `selectors.js` | Selectors used across all modules: `getInstituteDetails`, `getInstituteCampusId`, `getUserId`, etc. |

---

## Key Selectors (used by all modules)

| Selector | Purpose |
|----------|---------|
| `getInstituteDetails(state)` | Returns institute campus details (id, tier, instituteId) |
| `getInstituteCampusId(state)` | Returns the institute campus ID |
| `getUserId(state)` | Returns the authenticated user ID |

---

## Key Features

- **Anonymous route:** Accessible without authentication
- **Token management:** JWT token storage and refresh
- **Institute context:** Stores institute details used by all authenticated modules
- **Shared selectors:** `modules/Auth/selectors` is imported by virtually every other module
