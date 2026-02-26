# ATS (Applicant Tracking System)

This folder contains detailed module-wise documentation for the PluginLive ATS platform — a comprehensive campus and lateral recruitment system connecting Institutes, Corporates, Students, and Admins.

## Portal Documentation

| Portal | Folder | Frontend | Description |
|--------|--------|----------|-------------|
| **Admin** | `Admin/` | `admin-react-1` | Platform administration — onboarding, user management, reports, system config, courses, assessments |
| **Corporate** | `Corporate/` | `corporate-react-1` | Employer portal — job role creation, candidate management, drives, interviews, offers, reports |
| **Institute** | `Institute/` | `institute-react-1` | TPO/placement cell portal — student management, corporate relations, approvals, events, reports |
| **Student** | `Student/` | `student-react` | Student portal — job discovery, applications, resume, drives, offers, events, onboarding |
| **ElasticSearch** | `ElasticSearch/` | `search-service-1` | Search service — ES sync, search APIs, data ingestion, index management |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PluginLive ATS                              │
├─────────────┬─────────────┬─────────────┬─────────────┬─────────────┤
│   Admin     │  Corporate  │  Institute  │   Student   │   Search    │
│   Portal    │   Portal    │   Portal    │   Portal    │   Service   │
├─────────────┴─────────────┴─────────────┴─────────────┴─────────────┤
│                        API Gateway / Auth Service                    │
├─────────────────────────────────────────────────────────────────────┤
│  Institute Service  │  Corporate Service  │  Student Service        │
├─────────────────────────────────────────────────────────────────────┤
│                    PostgreSQL + MongoDB + ElasticSearch              │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Workflows

### Campus Recruitment Flow
1. **Corporate** creates job role → publishes to institutes
2. **Institute (TPO)** reviews → accepts/rejects role for campus
3. **Institute** floats role to eligible students
4. **Students** apply → questionnaire → shortlisting
5. **Corporate** schedules drives → interviews → evaluations
6. **Corporate** extends offers → **Students** accept/negotiate
7. **Students** upload documents → join

### Lateral Recruitment Flow
1. **Corporate** creates experienced role
2. Candidates apply directly (no institute intermediary)
3. Drive-based interview scheduling
4. Offer management with negotiation

## Module Summary

### Admin Portal (14 modules)
Dashboard, Onboarding, Corporates, Institutes, Assessment, Reports, Users, SystemConfig, Settings, Courses, EventCatalogue, RankingAlgorithm, ManageProfile

### Corporate Portal (12 modules)
Dashboard, Roles, RolePage, Drives, InterviewerDashboard, Exp-Candidates, Report, Users, Settings, ManageProfile, Auth

### Institute Portal (15 modules)
TPODashboard, Corporate, Roles, Students, Approvals, Drives, Events, Reports, Users, Settings, ManageProfile, Onboarding, Auth

### Student Portal (12 modules)
Dashboard, Roles, ViewRole, ViewSingleRole, AppliedRoles, Resume, Drives, DriveDetails, OfferLetter, ManageProfile, Events, Onboarding

### ElasticSearch Service (9 modules)
Search, DataSearch, Sync, Ingest, Synonyms, Client, Auth, Jobs, Cleanup

## Documentation Structure

Each portal folder contains:
- **Main README.md** — Portal overview, route table, architecture
- **Module folders** — Detailed README per module covering:
  - Overview & purpose
  - Routes & UI components
  - Redux actions & API endpoints
  - Filters, pagination, key features
