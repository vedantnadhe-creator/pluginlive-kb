# Next.js v2 apps on UAT — topology and deployment

Production-truth as of 2026-08-19, when all four v2 apps were brought onto UAT
and given `deploy.sh` entries. Before this, only `institute-react-v2` was on the
box and it was deployed **by hand** — UAT's `deploy.sh` had no v2 entry at all.

Companion docs: [ATS/Institute/v2-strangler-fig.md](../ATS/Institute/v2-strangler-fig.md),
[ATS/Corporate/v2-strangler-fig.md](../ATS/Corporate/v2-strangler-fig.md).

## What runs where on UAT

| App | Checkout | Run mode | Port | Public URL |
|---|---|---|---|---|
| `assessment-react-v2` | `~/frontend/assessment-react-v2` | **Docker** `candidate-assessment-journey-v2` | `127.0.0.1:3015→3000` | `assessment.uat…/candidate-assessment-journey/v2` |
| `admin-react-v2` | `~/frontend/admin-react-v2` | systemd `admin-react-v2.service` | 3013 | `admin.uat…/v2` |
| `corporate-react-v2` | `~/frontend/corporate-react-v2` | systemd `corporate-react-v2.service` | 3014 | `corporate.uat…/v2` |
| `institute-react-v2` | `~/frontend/institute-react-v2` | systemd `institute-react-v2.service` | 3012 | `institute.uat…/v2` |
| `corporate-node-v2` | `~/api/corporate-node-v2` | systemd `corporate-node-v2.service` | 4001 | none — internal only |

**Ports differ from DEV.** On DEV, institute-react-v2 is :3011 and
corporate-react-v2 is :3012; on UAT, 3011 is taken by `pil-ai-learning`, so
everything shifts up. Never copy a port from a DEV unit file.

`assessment-react-v2` is the only v2 app in Docker. It is the one whose
`Dockerfile` already existed (standalone Next output), and it is bound to
`127.0.0.1` so only nginx can reach it.

## Deploying

```bash
ssh ubuntu@uat.pluginlive.com
./auto_deploy.sh candidate-assessment-journey-v2 UAT   # or assessment-react-v2
./auto_deploy.sh admin-react-v2 UAT
./auto_deploy.sh corporate-react-v2 UAT
./auto_deploy.sh institute-react-v2 UAT
```

Menu IDs 22–25 in `~/deploy.sh`. They do **not** use `TYPE=frontend` — that
branch builds a Docker image from `.env` and would miss what these apps need.
Two new types were added instead:

- `nextjs-docker` (22) — writes `.env.prod` from `.env.uat`, builds, greps the
  image for dev URLs, swaps the container.
- `nextjs-systemd` (23–25) — installs, builds, greps `.next/static` for dev
  URLs, `systemctl restart`.

`corporate-node-v2` has no menu entry; it is built and restarted by hand
(`npm ci && npm run build && sudo systemctl restart corporate-node-v2`).

### The build MUST run on the UAT box

`next build` inlines every `NEXT_PUBLIC_*` into the client bundle, so a
DEV-built bundle sends UAT users to DEV. Both new deploy branches therefore
**fail the deploy** if the built output contains `dev.pluginlive.com`, rather
than serving it. This is the same failure that once bounced UAT assessment-invite
recipients into DEV.

`NEXT_PUBLIC_DEMO_MODE` is baked the same way and must stay **absent** from
UAT's `.env.uat` / `.env.prod`: it is what switches on the invite-less demo
journey (mock assignments, OTP `123456`) that the v2 root serves when the URL
carries no invite token. Only the DEV box sets it — see
[[Assessment/mix-match-candidate-journey]].

Server-only vars (`STD_API_URL`, `AUTH_API_URL`, `CORP_V2_API_URL`, …) are read
at runtime and are *not* baked — which is why grepping the bundle for
`uat.pluginlive.com` correctly returns **nothing**. Absence of dev URLs is the
signal, not presence of uat ones.

### UAT's default node is v16 — Next 16 will not build under it

`/usr/local/bin/node` on the UAT box is **v16.19.0**. The systemd units all
hardcode `/home/ubuntu/.nvm/versions/node/v20.20.2/bin/node`, and the
`nextjs-systemd` deploy branch prepends that same nvm bin to `PATH` before
installing or building. `pnpm` also lives only under that nvm node.

## nginx

Each v2 app is a `location` block **above** `location /` on the v1 host, so the
prefix is not swallowed by the v1 SPA. Assessment additionally needs:

```nginx
client_max_body_size 100M;    # candidate audio/video posts through the app
proxy_request_buffering off;
proxy_read_timeout 300s;
```

Corporate needs `proxy_read_timeout 300s; proxy_buffering off;` for the board's
SSE stream, which otherwise drops and reconnects every 60s.

### Do not leave nginx backups in `sites-enabled/`

nginx includes **every** file in that directory, so a `foo.conf.bak.<ts>` next
to `foo.conf` is a duplicate `server_name` and nginx silently ignores one of
them — you can edit the live file and see no change. Backups go in
`/home/ubuntu/nginx-backups/`. Several pre-existing `.bak` files still sit in
`sites-enabled/` on both DEV and UAT and are the cause of the standing
`conflicting server name` warnings.

## corporate-node-v2 on UAT

Brought up 2026-08-19. Config assembled **on the box** from the other UAT
services' env files, because every secret must belong to the UAT estate:

| Var | Sourced from |
|---|---|
| `JWT_SECRET` | admin-node `.env.uat` → `JWT_SECRET_KEY` |
| `ADMIN_SYSTEM_TOKEN`, `AUTH_SYSTEM_TOKEN` | user-management-node `.env.uat` → `SYSTEMJWT` |
| `OCI_*` | student-node `.env.uat` |
| `LITELLM_VIRTUAL_KEY` | existing UAT `.env.uat` |

A DEV-signed system token is rejected by UAT auth-node and **every candidate
email fails silently** — nothing crashes, mail just never arrives.

Ships with the dangerous levers off, matching PROD: `REMINDER_ENABLED=false`,
`EVALUATION_AGENT_ENABLED=false`, `EVALUATION_AGENT_SHADOW=true`, and
`DEV_CORPORATE_ID` **absent** (set, it scopes untokened requests to a corporate
anyway — unauthenticated access to real hiring data).

`QUEUE_ENV=uat`. **DEV and UAT share one Redis**, so this string is the only
thing keeping their BullMQ jobs apart; wrong, and one estate's worker eats the
other's jobs and mails candidates from the wrong estate.

`QUEUE_INLINE_WORKER=true` on UAT (one process, like DEV). PROD runs the worker
as its own deployment.

### The 11 agentic migrations are already applied to UAT

Verified 2026-08-19: the `corporate` schema on UAT holds 58 tables and every v2
table (`candidate_probes`, `candidate_memory`, `assessment_reminders`,
`interview_records`, `job_heartbeats`, `screening_results`, `application_forms`,
`stage_runs`, `job_errors`) is present. `corporate-node-v2`'s
`deploy/prod/RELEASE-v1.37.md` still says *"UAT is still pending for all 11"* —
that note is **stale**. Check the database, not the runbook.

### student-node → ATS score webhook

`student-node`'s `.env.uat` gained three keys so the v2 pipeline advances on
scoring instead of waiting for its hourly reconciler:

```bash
CORPORATE_ATS_URL=http://172.17.0.1:4001    # NO /v2 suffix — the helper appends it
CORPORATE_ATS_TOKEN=<equals corporate-node-v2 REMINDER_TICK_TOKEN>
CORPORATE_ATS_TIMEOUT_MS=3000
```

The receiver constant-time compares the token against its own
`REMINDER_TICK_TOKEN`. A mismatch **401s silently** — scoring is unaffected,
student-node logs and moves on, and the ATS quietly falls back to hourly
reconciliation. Both keys blank = the helper is completely inert, which is the
rollback lever.
