# Offer Letter Module

**Routes:**
- `/offerReceived` — Offer listing
- `/offerReceived/:Status` — Offers filtered by status
- `/offerReceived/ExCand/:offerID` — Experienced candidate offer accept
- `/offerReceived/uploadDocument/:offerID` — Upload requested documents

**Frontend:** `student-react/src/modules/OfferLetter/`

## Overview

The Offer Letter module manages the full offer lifecycle for students — viewing received offers, accepting/rejecting, negotiating, uploading documents requested by corporates, and marking as joined. Supports both fresher (institute-based) and experienced candidate offer flows.

---

## UI Components

| Component | Path | Purpose |
|-----------|------|---------|
| `Container/index.js` | Main listing | Offer letter listing with status filter |
| `Style/OfferAccpect` | Offer accept | Experienced candidate offer accept page |
| `Style/OfferUploadDocument` | Document upload | Upload requested documents for an offer |

---

## Redux Actions & API Endpoints

**File:** `actions.js`

### Offer Listing & Metrics

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getOfferList` | `/corporates/student/{studentId}/OfferList` | GET (Corp) | Paginated offer list. Filter: status (ACCEPTED maps to ACCEPTED,JOINED). pageLimit=10 |
| `getOfferMetric` | `/corporates/student/{studentId}/offerMatrics` | GET (Corp) | Offer metrics (counts by status) |
| `SingleOffer` | `/corporates/student/offer/{offerId}` | GET (Corp) | Single offer details |

### Offer Actions (Fresher)

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `OfferAcceptReject` | `/corporates/role/{roleId}/student/{studentId}/offerAcceptReject` | POST (Corp) | Accept or reject an offer. Payload: `{ isAccept: boolean }`. Updates local state optimistically |

### Offer Actions (Experienced Candidate)

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `OfferAcceptExp` | `/corporates/role/{roleId}/drive/{driveId}/student/{studentId}/offerAcceptReject` | POST (Corp) | Accept/reject offer for experienced candidate (drive-scoped) |
| `OfferNegotiate` | `/corporates/role/{roleId}/drive/{driveId}/student/{studentId}/offerNegotiation` | POST (Corp) | Negotiate offer terms |
| `candidateJoined` | `/corporates/role/{roleId}/drive/{driveId}/student/{studentId}/offerStatus` | PATCH (Corp) | Mark as JOINED. Updates local state optimistically |

### Documents

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getCorporateRequestDoc` | `/corporates/{corpId}/drive/{driveId}/role/{roleId}/candidate/{studentId}/reqDocs` | GET (Corp) | Fetch documents requested by corporate |
| `getStudentDocumentList` | `/students/document/{studentId}` | GET (Student) | Fetch student's uploaded documents |
| `uploadDocumentRequested` | `/students/document` | POST (Student) | Upload requested documents. Navigates to `/offerReceived` on success |

### Supporting

| Action | API | Method | Purpose |
|--------|-----|--------|---------|
| `getUserCorpList` | `/user?coporateId={corpId}` | GET (Auth) | Corporate user list for context |

---

## Key Features

- **Dual offer flow:** Separate APIs for fresher (role-based) and experienced (drive-based) offers
- **Offer negotiation:** Experienced candidates can negotiate offer terms
- **Document upload:** Upload corporate-requested documents per offer
- **Joining confirmation:** Students mark themselves as JOINED after accepting
- **Status mapping:** ACCEPTED filter includes both ACCEPTED and JOINED statuses
- **Optimistic updates:** Accept/reject/join update local Redux state immediately
