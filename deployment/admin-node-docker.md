# Admin-Node Docker Deployment Guide

## Critical: dotenv Load Order

The `index.js` entry point MUST have `require("dotenv").config()` as the **very first line**, before any other requires. Prisma clients validate `DATABASE_URL_ADMIN` and `DATABASE_URL_ASSESSMENT` at import time — if `dotenv` hasn't loaded `.env` yet, Prisma throws:

```
error: Error validating datasource `db`: the URL must start with the protocol `postgresql://` or `postgres://`
```

This was fixed in commit `b9ed0ae` — do NOT move the `require("dotenv").config()` line.

## Build Command

```bash
cd /home/ubuntu/api/admin-node
docker build -t admin-node:api --build-arg ENVIRONMENT=dev .
```

- Uses `--build-arg ENVIRONMENT=dev` → copies `.env.dev` as `.env` inside the container
- Use `--no-cache` if code changes aren't being picked up
- The Dockerfile runs `prisma generate` for both `schema-admin.prisma` and `schema-assessment.prisma` during build

## Deploy Command

```bash
# Stop and remove old container
docker rm -f admin 2>/dev/null

# Kill port if still in use from old process
sudo fuser -k 8000/tcp 2>/dev/null
sleep 1

# Start new container
docker run -d --name admin -p 8000:8000 --restart unless-stopped admin-node:api

# Connect to evolution-net (required for Redis access at 172.18.0.3)
sleep 2
docker network connect evolution-net admin
```

## Important Details

- **Container name**: `admin` (NOT `admin-node`)
- **Image tag**: `admin-node:api`
- **Port mapping**: `8000:8000` (container listens on 8000, NOT 8080)
- **Docker network**: Must be connected to `evolution-net` for Redis (BullMQ workers need it)
- **Base network**: `bridge` (default, connects to DB and other services)
- The systemd `admin-node.service` should be STOPPED when using Docker — they conflict on port 8000

## Verification

```bash
# Check container is running
docker ps | grep admin

# Test API
curl -s http://localhost:8000/assessment/getSubscribedInstitutes?pageNo=0\&pageLimit=1

# Check logs if issues
docker logs admin --tail 30
```

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `DATABASE_URL_ADMIN` error | dotenv not loaded before Prisma | Ensure `require("dotenv").config()` is first line in `index.js` |
| `EADDRINUSE :8000` | Old process on port | `sudo fuser -k 8000/tcp` then restart |
| Redis `ETIMEDOUT` | Container not on `evolution-net` | `docker network connect evolution-net admin` |
| Route 404 for new endpoints | Stale image | Rebuild with `--no-cache` |
| `free(): double free` crash | Prisma binary issue | Regenerate both Prisma clients, rebuild image |
