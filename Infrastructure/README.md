---
type: hub
tags: [infrastructure, servers, access, devops]
---

# Infrastructure & Access

> Server access, cloud config, deployment pipelines, and tooling available to Claude Code.

---

## Environments

| Environment | Domain | Purpose |
|-------------|--------|--------|
| **Dev** | `*.dev.pluginlive.com` | Development — this is the local server where Claude Code runs |
| **UAT** | `*.uat.pluginlive.com` | User Acceptance Testing — mirrors prod for QA |
| **Prod** | `*.pluginlive.com` | Production — live customer-facing |

---

## Server Access

### Dev Server (Local)
- **This machine** — Claude Code runs directly here
- All repos, Docker, services are local
- Frontend builds run locally via systemd or Docker
- See [[Infrastructure/servers|Server Details]] for ports and services

### UAT Server
- **SSH:** `ssh ubuntu@uat.pluginlive.com`
- **Deploy Script:** `~/auto_deploy.sh <app_name> [branch_name]` (default branch: `UAT`)
- **17 services** across ports 3000-8084
- See [[Infrastructure/servers|Server Details]] for full service list

### Prod Builder Server
- **SSH:** `ssh ubuntu@140.245.25.134`
- Used for production builds and deployments
- Access for build operations

---

## Cloud Access

### Oracle Cloud Infrastructure (OCI)
- **Region:** `ap-mumbai-1`
- **CLI Config:** `~/.oci/config`
- **API Key:** `~/.oci/oci_api_key.pem`
- **Tenancy OCID:** `ocid1.tenancy.oc1..aaaaaaaaqth4pixible6gykzj2mmnxkurwcwrsgusg6catecbjoqjglskxza`
- **Commands:** `oci` CLI available for all OCI operations (compute, storage, networking, etc.)

### Kubernetes
- **Cluster:** `cluster-coxkbkui6va` on OCI
- **API Server:** `https://141.148.220.199:6443`
- **Config:** `~/.kube/config`
- **Auth:** OCI CLI token-based
- **Commands:** `kubectl` available

### Docker Registries
| Registry | URL | Account |
|----------|-----|--------|
| Oracle Container Registry | `bom.ocir.io` | `kesavan.m@icanio.com` |
| Docker Hub | `index.docker.io` | `peterselva23` |

---

## Quick Reference

- [[Infrastructure/servers|Servers & Services]] — All ports, services, systemd units
- [[Infrastructure/mcp-servers|MCP Servers]] — All MCP integrations available to Claude Code
- [[Infrastructure/skills|Skills Catalog]] — All automation skills
- [[Infrastructure/deployment|Deployment Guide]] — How to deploy to each environment
