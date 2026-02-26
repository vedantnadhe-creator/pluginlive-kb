# OnBoarding Module

**Route:** `/onboarding` (anonymous)
**Frontend:** `institute-react/src/modules/OnBoarding/`

## Overview

The OnBoarding module handles the initial institute registration and setup flow. New institutes go through this process to configure their campus details, education offerings, and other setup steps before gaining access to the main portal.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `index.js` | Main page | OnBoarding flow orchestration |
| `menu.js` | Menu/Steps | Step navigation for onboarding process |
| `Register/Education/` | Education setup | Education details configuration |
| `Register/EducationNew/` | Education setup (new) | Updated education registration flow |

---

## Redux Files

| File | Purpose |
|------|---------|
| `actions.js` | OnBoarding API actions (institute registration, course setup) |
| `reducer.js` | OnBoarding state reducer |

---

## Key Features

- **Anonymous route:** Accessible without full authentication (post-signup)
- **Multi-step flow:** Step-by-step institute setup wizard
- **Education configuration:** Set up degrees, streams, and courses during onboarding
- **Institute registration:** Initial campus details and configuration
