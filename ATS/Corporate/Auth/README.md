# Auth Module

**Route:** `/signin` (anonymous)
**Frontend:** `corporate-react-1/src/modules/Auth/`

## Overview

The Auth module handles user authentication for the corporate portal. It provides the sign-in interface and manages authentication state (tokens, user details, corporate ID) used across all other modules.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Sign-in page layout |

---

## Redux Files

| File | Purpose |
|------|---------|
| `actions.js` | Auth API actions (login, logout, token refresh, `getUserInfo`) |
| `reducers.js` | Auth state reducer (user, tokens, corporate details) |
| `selectors.js` | Selectors used across all modules: `getCorporateId`, `getUserId`, etc. |

---

## Key Selectors (used by all modules)

| Selector | Purpose |
|----------|---------|
| `getCorporateId(state)` | Returns the authenticated corporate ID — used in virtually every API call |
| `getUserId(state)` | Returns the authenticated user ID |

---

## Key Features

- **Anonymous route:** Accessible without authentication
- **Token management:** JWT token storage and refresh
- **Corporate context:** Stores corporate ID used by all authenticated modules
- **`getUserInfo` action:** Refreshes user info from server (called by ManageProfile after updates)
