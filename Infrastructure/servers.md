---
type: reference
tags: [servers, ports, services, infrastructure]
---

# Servers & Services

## Dev Server (This Machine)

Claude Code runs directly on this server. All repos, builds, and services are local.

### Key Directories
| Path | Purpose |
|------|--------|
| `/home/ubuntu/api/` | Backend API repos (student-node, institute-node, etc.) |
| `/home/ubuntu/frontend/` | Frontend repos (admin-react, institute-react, etc.) |
| `/home/ubuntu/pluginlive-kb/` | Knowledge base (this vault) |
| `/home/ubuntu/.claude/skills/` | Claude Code skills |
| `/home/ubuntu/browser-mcp/` | Browser automation MCP server |
| `/home/ubuntu/browser_snapshots/` | Screenshots from browser automation |

### Frontend Services (Dev)
| Service | Port | Build Tool | Systemd Unit |
|---------|------|------------|-------------|
| admin-react | 3004 | Webpack | `admin-react.service` |
| institute-react | — | Webpack | `institute-react.service` |

**Build command (both):**
```bash
cd /home/ubuntu/frontend/<project> && source ~/.nvm/nvm.sh && nvm use 20 && npm run build
```

### Docker Builds (Dev)
```bash
# student-node
cd /home/ubuntu/api/student-node && docker build -t student-node --build-arg ENVIRONMENT=dev .

# institute-node
cd /home/ubuntu/api/institute-node && docker build -t institute-node --build-arg ENVIRONMENT=dev .
```
> Use `--no-cache` if code changes aren't picked up. Use `.env.dev` not `.env.development`.

---

## UAT Server

**SSH:** `ssh ubuntu@uat.pluginlive.com`

### All Services
| Service | Port | Type |
|---------|------|------|
| auth-react | 3000 | frontend |
| corporate-react | 3001 | frontend |
| institute-react | 3002 | frontend |
| student-react | 3003 | frontend |
| admin-react | 3004 | frontend |
| search-service | 3005 | ElasticSearch |
| assessment-react | 3006 | frontend |
| static-website | 5001 | frontend |
| mail-server | 5010 | mail |
| resume-parser | 5011 | api |
| admin-node | 8000 | api |
| corporate-node | 8080 | api |
| institute-node | 8081 | api |
| student-node | 8083 | api |
| user-management-node | 8084 | api |
| fastapi-ai-engine | 8011 | api |
| jd-parser | 8012 | api |

### UAT Deployment
```bash
ssh ubuntu@uat.pluginlive.com
~/auto_deploy.sh <app_name> [branch_name]  # default branch: UAT
```

---

## Prod Builder Server

**SSH:** `ssh ubuntu@140.245.25.134`
**Private IP:** `10.0.4.44`

Used for production build operations and deployments. Runs Elasticsearch (port 9200) and Postgres (port 5441) in Docker.

---

## Kubernetes Cluster

- **Provider:** Oracle Cloud (OCI)
- **API Server:** `https://141.148.220.199:6443`
- **Region:** `ap-mumbai-1`
- **Auth:** OCI CLI token-based (`~/.kube/config`)
- **Context:** `context-coxkbkui6va`

---

## Git Workflow

- All repos use `Development` branch for dev work
- Push to UAT: `git push origin Development:UAT`
- If UAT push rejected: merge `origin/UAT` into Development first
- `pluginlive-kb` repo: owned by `vedantnadhe-creator`, use GitHub MCP `push_files` tool (not git push from CLI)
