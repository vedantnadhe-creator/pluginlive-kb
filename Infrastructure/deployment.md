---
type: runbook
tags: [deployment, devops, uat, prod]
---

# Deployment Guide

## Environment Overview

```
Development (this server) → UAT (uat.pluginlive.com) → Prod (140.245.25.134)
```

---

## The `auto_deploy.sh` Pattern

Every server has an `auto_deploy.sh` script that wraps an interactive `deploy.sh`. Usage is identical across environments:

```bash
~/auto_deploy.sh <app_name> [branch_name]
```

It maps the app name to a numeric ID and feeds it to `deploy.sh` automatically. If called without arguments, it lists all available apps.

---

## Dev Server (Local) Deployment

**SSH:** This machine (local)
**Default branch:** `Development`

### Using auto_deploy.sh
```bash
~/auto_deploy.sh <app_name> [branch_name]
# branch_name defaults to Development
```

### Available Apps (Dev)
| App Name | ID | Type |
|----------|-----|------|
| admin-node | 1 | api |
| student-node | 2 | api |
| corporate-node | 3 | api |
| institute-node | 4 | api |
| user-management-node | 5 | api |
| admin-react | 6 | frontend |
| student-react | 7 | frontend |
| corporate-react | 8 | frontend |
| institute-react | 9 | frontend |
| auth-react | 10 | frontend |
| static-website | 11 | frontend |
| search-service | 12 | search |
| resume-parser | 13 | api |
| jd-parser | 14 | api |
| fast-api | 15 | api |
| assessment-react | 16 | frontend |
| llama-jd-parser | 17 | api |

### Manual Frontend Build (Alternative)
```bash
cd /home/ubuntu/frontend/<project>
source ~/.nvm/nvm.sh && nvm use 20
npm run build
sudo systemctl restart <project>  # e.g., admin-react, institute-react
```

### Manual Docker Build (Alternative)
```bash
cd /home/ubuntu/api/<project>
docker build -t <project> --build-arg ENVIRONMENT=dev .
# Use --no-cache if changes aren't picked up
```

> Note: Use `.env.dev` not `.env.development` — use `--build-arg ENVIRONMENT=dev`

---

## UAT Deployment

**SSH:** `ssh ubuntu@uat.pluginlive.com`
**Default branch:** `UAT`

### Using auto_deploy.sh
```bash
ssh ubuntu@uat.pluginlive.com
~/auto_deploy.sh <app_name> [branch_name]
# branch_name defaults to UAT
```

### Available Apps (UAT)
| App Name | ID | Type |
|----------|-----|------|
| admin-node | 1 | api |
| student-node | 2 | api |
| corporate-node | 3 | api |
| institute-node | 4 | api |
| user-management-node | 5 | api |
| admin-react | 6 | frontend |
| student-react | 7 | frontend |
| corporate-react | 8 | frontend |
| institute-react | 9 | frontend |
| auth-react | 10 | frontend |
| static-website | 11 | frontend |
| search-service | 12 | search |
| resume-parser | 13 | api |
| jd-parser / llama-jd-parser | 14 | api |
| assessment-react | 15 | frontend |
| fastapi-ai-engine / fast-api | 16 | api |
| mail-server | 17 | mail |

### Git Workflow for UAT
```bash
# From dev, push Development branch to UAT
git push origin Development:UAT

# If rejected (UAT has diverged):
git fetch origin
git merge origin/UAT  # resolve conflicts
git push origin Development:UAT
```

### One-liner (Deploy from Dev without SSH)
```bash
ssh ubuntu@uat.pluginlive.com "~/auto_deploy.sh admin-react UAT"
```

---

## Prod Deployment

**SSH:** `ssh ubuntu@140.245.25.134`
**Default branch:** prompted interactively

### Using deploy.sh (Interactive)
Prod has `deploy.sh` directly (no `auto_deploy.sh` wrapper). It prompts for the app number and branch.

```bash
ssh ubuntu@140.245.25.134
~/deploy.sh
# Then enter: app number, branch name
```

### Available Apps (Prod)
| ID | App Name | OCR Image Name |
|----|----------|----------------|
| 1 | admin-react | pl-admin-react |
| 2 | auth-react | pl-auth-react |
| 3 | student-react | pl-student-react |
| 4 | corporate-react | pl-corporate-react |
| 5 | institute-react | pl-institute-react |
| 6 | admin-node | pl-admin-api |
| 7 | student-node | pl-student-ap |
| 8 | corporate-node | pl-corporate-api |
| 9 | institute-node | pl-institute-api |
| 10 | user-management-node | pl-user-management-api |
| 11 | resume-parser | pl-resume-parser |
| 12 | search-service | pl-search-service |
| 13 | fast-api | pl-fast-api |
| 14 | question-manager | pl-question-manager |
| 15 | assessment-react | pl-assessment-react |
| 16 | llama-jd-parser | pl-llama-jd-parser |

> Prod `deploy.sh` builds Docker images and pushes to Oracle Container Registry (`bom.ocir.io`) then deploys to Kubernetes.

### Kubernetes Cluster
- **Cluster API:** `https://141.148.220.199:6443`
- **kubectl** configured locally via `~/.kube/config`
- **Docker registry:** `bom.ocir.io` (Oracle Container Registry)

---

## Oracle Cloud CLI

```bash
# List compute instances
oci compute instance list --compartment-id <compartment-id>

# Object storage operations
oci os object put --bucket-name <bucket> --file <path>
oci os object list --bucket-name <bucket>

# Kubernetes
kubectl get pods
kubectl get services
kubectl logs <pod-name>
```

---

## Special Cases

### pluginlive-kb (Knowledge Base) Repo
- Owned by `vedantnadhe-creator` GitHub account
- Claude Code's git CLI (Alex-PluginLive account) lacks push access
- **Must use:** GitHub MCP `push_files` tool instead of `git push`
