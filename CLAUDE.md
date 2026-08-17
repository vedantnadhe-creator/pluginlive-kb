# PluginLive Knowledge Base

This directory contains domain documentation for the PluginLive platform.

When working on a feature, check the relevant file here **before asking the user for context**:

- `pluginlive.md` — company overview (SaaS hiring platform, Assessment + ATS products)
- `Assessment/README.md` — assessment system overview
- `Assessment/aptitude.md` — aptitude test scoring, flow, proctoring
- `Assessment/communication.md` — video/audio assessment scoring
- `Assessment/custom.md` — custom question assessments
- `Assessment/rolebased.md` — role-based assessment scoring and calculations
- `Assessment/schedule.md` — assessment scheduling and cron jobs
- `Assessment/admin.md` — admin panel, assessment management, TPO/corporate flows
- `Assessment/admin-frontend.md` — admin-react Assessment module (UnifiedAssessmentTable, StudentReport, subscription filtering, heading display)
- `Assessment/institute.md` — institute TPO view, two-API architecture, score format differences, PDF browser pool
- `Obsidian.md` — Obsidian knowledge base tool: setup, pricing, plugins, team collaboration, vault structure

**Infrastructure & DevOps:**
- `Infrastructure/github-access.md` — GitHub credentials for every checkout (fine-grained PAT, ≤90-day expiry, rotation steps) — **read this on any `git` 403**
- `Infrastructure/README.md` — server access overview (Dev, UAT, Prod)
- `Infrastructure/servers.md` — all servers, ports, services, systemd units
- `Infrastructure/mcp-servers.md` — all MCP integrations (browser-agent, GitHub, Slack, Linear, Notion, WhatsApp, S3, Postgres, etc.)
- `Infrastructure/skills.md` — all Claude Code skills catalog (~30 skills)
- `Infrastructure/deployment.md` — deployment guide (Dev → UAT → Prod, Docker, OCI, K8s)
- `Infrastructure/form-data-normalization.md` — Form Data Normalization service (Python/FastAPI, Google Drive ingestion, LLM normalization, entity matching, port 5013)
- `Infrastructure/document-parsers.md` — CV & JD parsers, now inside fastapi-ai-engine (`/cv-parser/*`, `/jd-parser/*`); per-route PDF extractors are pinned, retired `CV_BE_BASE_URL`/`JD_BE_BASE_URL`, retirement checklist for the old standalone services
- `Infrastructure/pg-vector-search.md` — PG Vector Search / Entity Normalizer service (Python/FastAPI, multi-signal RRF ranking, pgvector, port 8002)
- `Infrastructure/uat-docker-build.md` — UAT image builds failing on apt (`exit code: 100`), the deb.debian.org HTTP stall, why the package layer rebuilds every deploy, rollback tagging

Read only what's relevant to the current task. Do not read all files upfront.
