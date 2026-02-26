# Corporate Dashboard Module

**Routes:**
- `/corporate-dashboard` — Corporate Dashboard (main)
- `/corporateDashboardPage2` — Corporate Dashboard Page 2

**Frontend:**
- `corporate-react-1/src/modules/Corporate-dashboard/` (Page 1)
- `corporate-react-1/src/modules/CorporateDashboardPage2/` (Page 2)

## Overview

The Corporate Dashboard provides advanced analytics and reporting views for corporate hiring. It includes chart-based visualizations with PDF export capabilities. Both pages share the same `CorporateDashboardPage2/Container` component in routes but originate from different source modules.

---

## UI Components

### Corporate Dashboard (Page 1)
| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Dashboard layout |
| `Container/components/` | Chart components | Various chart and data components |
| `Container/Style/` | Styles | Styled components |

### Corporate Dashboard Page 2
| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main container | Dashboard page 2 layout |
| `Container/components/` | Chart components | Analytics chart components |
| `Container/exportPdf.js` | PDF export | Dashboard PDF generation |
| `Container/Style/` | Styles | Styled components |

---

## Key Features

- **Analytics charts:** Visual hiring data representations
- **PDF export:** Export dashboard charts and data as PDF
- **Multi-page:** Split across two pages for different analytics views
