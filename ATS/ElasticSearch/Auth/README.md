# Auth Module

**Type:** Internal guard (no HTTP endpoints)
**Source:** `search-service-1/src/modules/auth/`

## Overview

The Auth module implements API key-based authentication and role-based authorization for the search service. It uses a global NestJS guard that validates the `api-key` header on every request. Two access levels are supported: User (read-only search) and Admin (sync, ingest, synonyms).

---

## Components

### AuthGuard (`auth.guard.ts`)

Global guard applied to all routes via `APP_GUARD`.

**Authentication flow:**
1. Check if route is marked `@Public()` → allow if true
2. Extract `api-key` from request headers
3. Compare against `API_KEY_TOKEN` (User) and `ADMIN_API_KEY_TOKEN` (Admin) env vars
4. If neither matches → `401 Unauthorized`
5. If User key matches but route requires Admin role → `403 Forbidden`

### Roles (`auth.enum.ts`)

```typescript
enum Role {
  User = 'user',
  Admin = 'admin',
}
```

### Decorators (`auth.decorator.ts`)

| Decorator | Usage | Description |
|-----------|-------|-------------|
| `@Roles(Role.Admin)` | Controller/method | Restrict to Admin API key only |
| `@Public()` | Controller/method | Allow unauthenticated access |

---

## Module Auth Levels

| Module | Auth Level | Notes |
|--------|-----------|-------|
| Search | User | Any valid API key |
| DataSearch | User | Any valid API key |
| Sync | Admin | `@Roles(Role.Admin)` on controller |
| Ingest | Admin | `@Roles(Role.Admin)` on controller |
| Synonyms | Admin | `@Roles(Role.Admin)` on controller |
| Cleanup | User | Any valid API key |

---

## Key Features

- **API key auth:** No JWT/OAuth — simple header-based API key comparison
- **Two-tier access:** User keys can only access search endpoints; Admin keys access everything
- **Global guard:** Applied via `APP_GUARD` provider — no per-route setup needed
- **Public routes:** `@Public()` decorator bypasses auth entirely
