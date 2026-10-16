# GCP PROD migration — PROD copy on `*.v2.pluginlive.com`

Status as of **2026-10-16**. PROD is still served from OCI (OKE k8s + `pl-prod-pg16`). A full copy of PROD
runs on Google Cloud for testing at `*.v2.pluginlive.com`; cutover (real DNS → GCP) has **not** happened.
Plan owner: Mariselvan. Approach: "lift" PROD onto two VMs (no Cloud Run, no code changes); email and
object storage stay on OCI.

## Infrastructure (GCP project `pl-prod-511404`, Mumbai `asia-south1-c`)

| | App VM `pl-prod-app-01` | DB VM `pl-prod-db-01` |
|---|---|---|
| Machine | e2-standard-4 (4 vCPU / 16 GB), 100 GB SSD | n2-standard-4 (4 vCPU = 2 cores / 16 GB) — resized 10-15 from e2-standard-2 |
| Network | `pl-prod-vpc` 10.20.0.0/24, **10.20.0.10**, static public IP **35.244.18.184** (`pl-prod-app-ip`), tag `pl-app` | **10.20.0.20**, no public IP, outbound via Cloud NAT `pl-prod-nat`, tag `pl-db` |
| Disks | boot only | 30 GB boot + 100 GB pd-ssd `pl-prod-db-data` at `/var/lib/postgresql` (Terraform `prevent_destroy`) |
| Snapshots | — | daily 21:00 UTC (02:30 IST), 14 days, Mumbai (`pl-prod-db-daily`) |

- **Terraform:** DB VM, data disk, service account `pl-prod-db` (log/metric writer only), firewall rules,
  router + NAT and snapshot policy are in Terraform, run from Cloud Shell (`~/pl-prod-db/main.tf`, state in
  `gs://pl-prod-511404-tfstate/db-vm`). The app VM and the VPC were created by hand in the console.
  Gotchas: snapshot `start_time` must be a whole hour; Cloud Shell no longer ships terraform (install 1.9.x to `~/bin`);
  a machine-type change needs `allow_stopping_for_update = true`.
- **Firewall:** 80/443 open to `pl-app`; SSH only from Google IAP (35.235.240.0/20) and the DEV box
  (129.154.231.72); Postgres 5432 and SSH to the DB only from `pl-app`.
- **Access:** `ssh ubuntu@35.244.18.184`; DB VM via `ssh -J ubuntu@35.244.18.184 ubuntu@10.20.0.20`.
  The DEV box/Claude has **no GCP API rights** — anything in the console/gcloud/terraform is done by a human.
- **DNS:** `pluginlive.com` is hosted on **AWS Route 53** (not OCI; only `uat.pluginlive.com` is delegated to OCI).
  Test record: `*.v2.pluginlive.com A 35.244.18.184`. One Let's Encrypt SAN cert `v2.pluginlive.com` covers the
  20 test hostnames; auto-renews (certbot timer, nginx reload hook).

## Database (`pl-prod-db-01`)

- PostgreSQL **16.15** (PGDG), matching OCI `pl-prod-pg16`; extensions as PROD: pg_trgm, pgcrypto, unaccent,
  vector (0.8.x) in `public`, **uuid-ossp in schema `student`**.
- DB `prod_pluginlive`, owner role `plproduction` (new password, not PROD's). Credentials only in
  `/root/pl-prod-db.env` (DB VM) and `~/.pl-prod-db.env` (app VM).
- Data = PROD snapshot **2026-10-14 06:27:49 UTC** (pg_dump 2.5 GB, 459 tables, 0 restore errors).
  Restore recipe: pre-create the extensions in their PROD schemas as superuser, then `pg_restore -j4
  --no-owner --no-acl -L list` with extension / `COMMENT ON EXTENSION` / `SCHEMA student` entries removed.
- Settings: PROD planner values (`random_page_cost=4`, `work_mem=4MB`, `effective_io_concurrency=1`);
  `shared_buffers=4GB`, `effective_cache_size=12GB`, `max_connections=200`, slow log ≥1 s.
  `pg_hba`: `host` from 10.20.0.10 only (TLS optional — PROD URLs mix `sslmode=disable/no-verify`).
- LiteLLM keeps its own Postgres container on the app VM (virtual keys restored from PROD).
- **Not set up yet:** nightly `pg_dump` to OCI Object Storage (needs a bucket + write-only OCI user).

## Application stack (app VM)

- Code: `~/repositories/{api,frontend}/*` — the 23 repos PROD's builder uses, on PROD's branches
  (`~/repositories/repos.txt`, refresh with `~/repositories/clone.sh`). Git auth = the org fine-grained PAT in
  `~/.git-credentials` (**rotate it here too** — see `github-access.md`).
- PROD config: `~/prod-config/` (k8s deploy/configmap/secret/ingress exports + builder `envs/`), mode 0700.
- Generator **`~/gen-v2.py`** turns that into `~/pl-v2/` (docker-compose, `env/`, `files/`, `ports.txt`);
  **`~/pl-v2/nginx_gen.py`** writes `/etc/nginx/sites-available/pl-v2` from `ports.txt`. Always re-run both
  together (ports renumber when services are added). Never hand-edit `env/` or `files/`. Run-book: `~/pl-v2/README.md`.
- Rewrites applied by the generator: DB host/creds → GCP DB; `<host>.pluginlive.com` → `<host>.v2.pluginlive.com`;
  `*.prod.pluginlive.com` → `*.v2.pluginlive.com`; k8s service DNS → compose `service:port`.
- Local deviations from PROD: x86 (PROD is ARM) — `student-node` builds from an untracked `Dockerfile.amd64`
  (`FROM arm64v8/` stripped); `fast-api` image is ~17 GB (CUDA torch on x86); LiteLLM = `ghcr.io/berriai/litellm:v1.90.1`
  (PROD's version); sql-sandbox = `postgres:16-alpine`; one replica per service, so memory limits are raised
  (`MEM_OVERRIDE` in gen: student 3g, corporate/admin 2g, institute 1.5g, auth 1g — PROD per-pod limits OOM-killed here).
- CORS shim: `form-data-normalization/api/main.py` hardcodes `allow_origins` (no `.v2`), so nginx answers CORS for
  `admin.v2` on `data-normalization.v2` (`CORS_SHIM` in nginx_gen). Not needed after cutover.

### Test URLs
Frontends: `auth`, `admin` (+`/v2`), `corporate` (+`/v2`), `institute` (+`/v2`), `assessment`
(+`/candidate-assessment-journey/v2`), `student` — all `.v2.pluginlive.com`. APIs: `api-auth`, `api-admin`, `api-stud`,
`api-corp`, `api-inst`, `api-fast`, `search`, `parser`, `llma-api`, `ai-gateway`, `vector-search`, `data-normalization`.
Logins = PROD logins (users were copied). JWT secrets/issuer are PROD's, so a PROD token is also valid on `.v2`.

## Deliberately OFF on `.v2` (real PROD data — must not reach real people or PROD resources)

| Item | How it is switched off | Where |
|---|---|---|
| WhatsApp + SMS (all go through auth-node) | `WHATSAPP_DISABLED=true`, `SMS_ENABLED=false` | `OUTBOUND` dict in `~/gen-v2.py` → `files/auth-node/app/.env` |
| Corporate v2 reminders | `REMINDER_ENABLED=false` | → corporate-node-v2 (+ worker) `.env` |
| Slack activity alerts | `SLACK_ACTIVITY_WEBHOOK_URL=` (blank), `SLACK_ACTIVITY_ENV=gcp-v2` | → admin-node `.env` |
| Email to candidates | mail-server `MAIL_ALLOWED_RECIPIENT_DOMAINS=pluginlive.com`, `MAIL_SUBJECT_TAG=[GCP-V2]` (non-pluginlive recipients dropped) | → `env/mail-server.env` |
| Phone AI Interview worker | `call-interview` **not built/deployed** (nginx returns 503 on `call-interview.v2`) | — |
| FDN Drive cron + worker | containers not started (would read PROD's Google Drive change feed) | — |
| question-manager | stopped — its "PROD" target writes to live `api-admin.pluginlive.com` | — |

Running: all other backends incl. `corporate-node-ai-match-worker` (CV/JD match) and `corporate-node-v2-worker`.

## Next session — hand-off

### A. Phone AI Interview (`call-interview`) on `.v2`
- Source: `fastapi-ai-engine` repo, `call_interview/Dockerfile`; PROD image tag `…-hotfix-3-oncall-64898cd`
  (branch `release-v1.41-hotfix-3-oncall`). Port **8021**, PROD memory limit 2Gi.
- Env: secret `call-interview-env` (keys: `PLIVO_AUTH_ID/AUTH_TOKEN/FROM_NUMBER`, `DEEPGRAM_API_KEY`,
  `ELEVENLABS_API_KEY`, `AZURE_SPEECH_KEY/REGION`, `CALL_STT`, `CALL_INTERVIEW_SECRET`, `DIAL_TOKEN`, `PUBLIC_BASE`,
  `TYPESAFE_API_KEY`) + plain `ENGINE_URL`, `STUDENT_API_URL`, `ADMIN_API_URL`. The generator already rewrites
  `PUBLIC_BASE` and the k8s URLs; add a `BUILD` entry in `~/gen-v2.py`, rebuild, re-run nginx_gen (route already
  defined: `call-interview.v2`, 3600 s timeouts, websocket upgrade).
- Plivo answer/stream URLs come from `PUBLIC_BASE` per call, so `.v2` calls should use `call-interview.v2`; confirm
  nothing on the Plivo account is pinned to `call-interview.prod.pluginlive.com`.
- Calls cost money and ring real phones: test only with internal numbers; admin-node's `ai_interview_call_dispatch`
  cron dials scheduled slots from the copied PROD data — check for pending slots before enabling.
- Known PROD issue: worker sometimes receives zero caller audio after days up → redeploy (see memory/KB notes on the worker).

### B. Real WhatsApp / SMS / email to candidates
- Flip the switches in the table above (edit `OUTBOUND` in `~/gen-v2.py`, re-run gen, `docker compose up -d --no-build`
  the affected services). Do this **only at cutover** or with a test allow-list: the DB holds real PROD candidates,
  and admin-node/student-node schedulers send reminders/invites on their own.
- MSG91 delivery webhooks are configured once per account and point at PROD — `.v2` sends would show
  "Processing" (see `whatsapp-messaging.md`). Email delivery tracking goes OCI logs → Connector Hub → webhook.
- Email itself stays on OCI Email Delivery (same credentials) — no GCP change needed.

### C. Cutover (not started)
Freeze PROD writes → fresh dump/restore (~20 min for 12 GB) → set OUTBOUND to PROD values, start FDN cron/worker,
question-manager, call-interview → switch Route 53 records to 35.244.18.184 and re-issue certs for real hostnames →
give partners the new egress IP (app VM 35.244.18.184; DB VM uses Cloud NAT) → keep OCI PROD as fallback.

## Performance work done on the copy (2026-10-15)
- 9 missing indexes added on the copy; scripts in DB-Scripts `Assessment Performance Indexes/`
  (`20261015T033232Z__proctoring_and_resume_lookup_indexes.sql`, `…__job_role_institute_map_and_ingestion_fk_indexes.sql`) —
  **UAT and PROD pending** (the first is also on DEV).
- Role-float eligibility queries are slow on PROD too (8–23 s): cost is the PL/pgSQL
  `check_eligibility_criteria_role_float` / `are_mandatory_skills_present` per candidate — code, not indexes.

## PROD bugs found during the migration (exist on live PROD; not fixed)
- `fast-api` PROD config `DATABASE_URL_ASSESSMENT` points at the **UAT** DB (140.238.245.202:5441).
- Proctoring sweeper (`student-node script/processProctoringCron.js`) re-queues attempts with several proctoring
  sessions forever (finalizer only sets `is_valid` on the latest log) — ~400 extra finalizations per attempt per 6 h.
- Student resume education update returns 400 "Body/CurrentCourse/Specialisation Must Be String" when no
  specialisation is selected (`student-react` EducationalDrawer sends `null`; `student-node` schema requires string).
- `Resume_parser` repo commits an OCI private key (`USING API/oci_api_key.pem`) — rotate and remove.
- `assessment-react` / `student-react` hardcode `https://api-std.staging.pluginlive.com` in `utils/localRequest.js`.
