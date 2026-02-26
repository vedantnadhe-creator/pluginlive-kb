# Approvals Module

**Route:** `/approvals`
**Frontend:** `institute-react/src/modules/Approval/`

## Overview

The Approvals module serves as a centralized hub for all TPO approval workflows. It presents four approval categories as cards with real-time metrics, each linking to its respective management page.

---

## Approval Categories

### 1. Profile Setting Approvals
- **Route:** `/tpoApproval`
- **Description:** Review and act on student profile update requests (personal, academic, placement-related details)
- **Metrics:** `approval_pending_count` from student metrics

### 2. Opting Out Approvals
- **Route:** `/students?optedStatus=opt-out`
- **Description:** Manage student requests to opt out of placements or re-enter the placement process
- **Metrics:**
  - `optOut_pending` — Pending TPO approval
  - `optIn_pending` — Re-opting in requests
  - `optOut_count` — Currently opted-out candidates

### 3. Job Specific Approvals
- **Route:** `/tpoRequests`
- **Description:** Process approval requests related to specific job roles (eligibility exceptions, special permissions)
- **Metrics:**
  - `pending_count` — Total requests pending
  - `urgent_count` — Urgent requests

### 4. Other Restriction Approvals
- **Route:** `/students?isRestricted=true`
- **Description:** Approve or update student restrictions as per institute policy
- **Metrics:**
  - `restricted_count` — Restricted candidates

---

## UI Structure

**File:** `index.js`

The module renders a card-based layout using Ant Design's `Row`/`Col` grid. Each card displays:
- Icon (profile, opt-out, job, restriction)
- Title and subtitle
- Description text
- Stats section with label-value pairs
- "Enter" button navigating to the relevant page

---

## Data Dependencies

| Dispatch | Source | Purpose |
|----------|--------|---------|
| `studentsMetricsData()` | `Students/actions` | Fetches student metrics (approval_pending, optOut, restricted counts) |
| `getTPOMetrics()` | `TPORequests/actions` | Fetches TPO request metrics (pending_count, urgent_count) |

---

## Key Features

- **No dedicated API actions:** This module aggregates data from Students and TPORequests modules
- **Card-based navigation:** Visual dashboard with real-time stats
- **Deep linking:** Each card navigates to the appropriate filtered view
- **Responsive grid:** Uses Ant Design responsive column spans
