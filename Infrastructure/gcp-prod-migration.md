# GCP PROD migration — PROD copy on `*.v2.pluginlive.com`

Status as of **2026-10-16**. PROD is still served from OCI (OKE k8s + `pl-prod-pg16`). A full copy of PROD
runs on Google Cloud for testing at `*.v2.pluginlive.com`; cutover (real DNS → GCP) has **not** happened.
Plan owner: Mariselvan. Approach: lift PROD onto two VMs (no Cloud Run); email and object storage stay
on OCI. The GCP copy now has isolated integration and performance fixes described below. Live OCI
PROD and DEV application deployments were not changed during this work.

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

- Code: `~/repositories/{api,frontend}/*` — the 23 repos PROD's builder uses, initially on PROD's branches;
  three now have local GCP integration branches (see below). The original release manifest is
  `~/repositories/repos.txt`; preserve local fixes before running `clone.sh`. Git auth = the org fine-grained PAT in
  `~/.git-credentials` (**rotate it here too** — see `github-access.md`).
- PROD config: `~/prod-config/` (k8s deploy/configmap/secret/ingress exports + builder `envs/`), mode 0700.
- Generator **`~/gen-v2.py`** turns that into `~/pl-v2/` (docker-compose, `env/`, `files/`, `ports.txt`);
  **`~/pl-v2/nginx_gen.py`** writes `/etc/nginx/sites-available/pl-v2` from `ports.txt`. Always re-run both
  together. Existing localhost ports are now preserved when services are added (fixed 2026-10-16),
  so adding a service no longer requires recreating every container. Never hand-edit `env/` or `files/`.
  Run-book: `~/pl-v2/README.md`.
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

## Integration state on `.v2` (updated 2026-10-16)

| Item | Current control | Where |
|---|---|---|
| WhatsApp + SMS | Provider switches are on (`WHATSAPP_DISABLED=false`, `SMS_ENABLED=true`), but an **empty required phone allowlist blocks every recipient** before contacting MSG91 or the legacy SMS Lambda | auth-node `OUTBOUND_ALLOWED_PHONE_NUMBERS`, populated from `~/pl-v2/test-recipients.env` by the generator |
| Corporate v2 reminders | `REMINDER_ENABLED=false` | → corporate-node-v2 (+ worker) `.env` |
| Slack activity alerts | `SLACK_ACTIVITY_WEBHOOK_URL=` (blank), `SLACK_ACTIVITY_ENV=gcp-v2` | → admin-node `.env` |
| Email to candidates | Restricted to `@pluginlive.com`; subject tag `[GCP-V2]`; relay environment label `gcp-v2` | → `env/mail-server.env` |
| Automatic assessment reminders | `assessment_auto_reminder=false` in the GCP copy's `assessment.cron_config` | Disabled 2026-10-16 before enabling provider switches |
| Automatic phone dispatch | `ai_interview_call_dispatch=false` in the GCP copy's `assessment.cron_config` | Worker is deployed; dispatch stays off pending an internal test number |
| Phone dialing | Worker `CALL_ALLOWED_NUMBERS` is present and empty, so `/dial`, `/dial/assessment`, and the carrier call function reject all numbers | Same `V2_TEST_PHONE_NUMBERS` setting in `~/pl-v2/test-recipients.env` |
| FDN Drive cron + worker | containers not started (would read PROD's Google Drive change feed) | — |

Running: 32 containers, including `call-interview`, `question-manager`, `corporate-node-ai-match-worker`
(CV/JD match), and `corporate-node-v2-worker`. An unused compose one-off admin container
(`pl-v2-admin-node-run-e724e98f426f`, no published port or service alias) was stopped on 2026-10-16;
it had been running a second scheduler since setup.

### Phone AI Interview

- Deployed at `https://call-interview.v2.pluginlive.com`; `/health` returns
  `ok:true`, `telephony:plivo`, `assessment:true`. Unauthenticated dialing returns 401; a valid token
  with an unlisted number returns 403 before brief generation, TTS or carrier access.
- Source: exact PROD `fastapi-ai-engine` commit **`64898cd`**, archived into
  `~/repositories/extra/call-interview-build`, plus the environment phone allowlist guard.
  The running FastAPI checkout is on a different release; do not silently substitute it for this worker.
- Port 8021 in the container; localhost 30008; nginx has TLS, WebSocket upgrade and 3600-second timeouts.
  Sessions persist in the compose `call-sessions` volume.
- Existing PROD credentials were copied through the generator, never committed. `PUBLIC_BASE` is
  `https://call-interview.v2.pluginlive.com`; engine, student and admin URLs use compose service names.
  Current STT selection is `scribe`. Plivo account authentication passed.
- **47 offline conversation/allowlist tests passed. No real phone call was made.** Internal test number
  and authorization for one call are still needed. Check copied slots before enabling the dispatch cron;
  at setup all four existing slots were already COMPLETED/DROPPED.
- Add approved full country-code numbers to `V2_TEST_PHONE_NUMBERS` in
  `~/pl-v2/test-recipients.env`, re-run the generator, then recreate `auth-node` and `call-interview`.
  An empty list means **block all**. Removing the environment variable entirely means unrestricted
  sending; reserve that for an authorized cutover.

### WhatsApp, SMS and email

- WhatsApp uses the existing MSG91 configuration. Template API authentication passed (HTTP 200).
  SMS template details also loaded through MSG91's `getTemplateVersions` API. OCI SMTP `/ready`
  authenticated successfully without sending email.
- Phone restrictions cover all three auth-node sending paths: WhatsApp, MSG91 SMS OTP, and legacy
  Lambda SMS. A mixed batch containing an unlisted recipient is rejected as a whole. Empty-list and
  mixed-batch checks passed before deployment.
- **No test WhatsApp, SMS, email or call was sent during this integration session.** End-to-end delivery
  checks still need an approved internal phone number and mailbox. Candidate-wide sending stays restricted.
- WhatsApp delivery: the shared MSG91 webhook still serves OCI PROD. Do not add/reorder/disable it for
  `.v2` tests: MSG91 has historically delivered to only one destination per event. Instead, GCP runs
  `gcp-v2-delivery-sync.timer` every two minutes. `~/pl-v2/delivery_sync.py` reads pending `.v2` send IDs,
  fetches MSG91 delivery reports, and posts matching IDs only to the `.v2` receiver. It makes no provider
  request when nothing is pending. The lookup is bounded to two days and 20 pages; older sends need
  manual reconciliation. It cannot send messages and rejects a live-PROD webhook destination.
  Inspect with `journalctl -u gcp-v2-delivery-sync.service`; four focused checks passed.
- Email delivery: a **separate ACTIVE CUSTOM_HTTPS subscription** was added to the existing
  `pl-email-delivery-prod` OCI Notifications topic for the `.v2` email receiver. The original PROD
  subscription remains active. The new subscription confirmed itself through the GCP handler.
  Resource ID is in `~/pl-v2/changes/20261016/oci-email-subscription.json` on GCP.
- Both `.v2` delivery receivers returned 200 to authenticated empty batches. Callback settings are
  stored privately at `~/pl-v2/provider-webhooks.txt`; do not put their secrets or tokenized URLs in the KB.

### Question Manager

- Running at **`https://question.v2.pluginlive.com`**. Its environment selector contains only **GCP v2**;
  API requests use same-origin `/questionManager/`, proxied by nginx to the GCP admin service.
  The bundle contains no DEV/UAT/live-PROD admin API targets, and invalid old saved environment
  selections are discarded.
- Independent login: username `gcp-v2-admin`; password is only in
  `~/pl-v2/question-manager-login.env` on the GCP app VM (0600), injected by the generator.
  Login, authenticated cron listing and question listing returned HTTP 200.
- A headless browser completed environment selection, login and question loading with no JavaScript
  errors; all observed Question Manager API requests stayed on `question.v2.pluginlive.com`.
- Generation/review cron flags remain disabled; enabling the UI does not enable generation jobs.
- FastAPI's `DATABASE_URL_ASSESSMENT` was corrected **on GCP only** through `SERVICE_OVERRIDES` in
  the generator. It now points to `10.20.0.20/prod_pluginlive`, not UAT. FastAPI was recreated and
  `/health/ready` reports the face model ready. Live OCI PROD's original setting remains unchanged.

## Performance work on the copy

### Indexes (2026-10-15)

- 9 missing indexes added on the copy; scripts in DB-Scripts `Assessment Performance Indexes/`
  (`20261015T033232Z__proctoring_and_resume_lookup_indexes.sql`, `…__job_role_institute_map_and_ingestion_fk_indexes.sql`) —
  **UAT and PROD pending** (the first is also on DEV).

### Proctoring and role-float fixes (2026-10-16)

- **Proctoring loop fixed on GCP:** the sweeper finds unfinished older sessions, but the worker formerly
  finalized only the newest session. The worker now checks evidence across all ended sessions, validates
  each unfinished session, emits its events, then builds the combined report once. Report failures are
  propagated for retry. Five worker checks passed, including a multi-session regression. The backlog
  fell to **zero**, and repeated sweeper ticks now show `snapshots=0 finalizations=0`.
- **Role-float CPU reduced:** both `student` and `corporate` versions of
  `check_eligibility_criteria_role_float` now use native PL/pgSQL JSON iteration instead of repeated SQL
  subqueries and no longer emit debug NOTICEs for every candidate. Eligibility rules are preserved.
  **73,500 comparisons had zero mismatches**; two captured real queries returned identical candidate sets.
  On the same GCP DB, query 1 was **11.119 s → 5.329 s**, query 2 **1.409 s → 0.873 s**. This does not
  establish a latency guarantee for every assessment screen.
- Migration + commented rollback pushed to DB-Scripts, commit **`d907a69`**:
  `Assessment Performance Indexes/20261016T083555Z__optimize_role_float_eligibility_functions.sql`.
  **DEV, UAT and live PROD remain pending.** No additional index was needed for these two fixes.
- Original function definitions and trial/regression logs are in `~/gcp-v2-performance/` on the **DB VM**.
  App VM changes, rollback image tags and runnable checks are under `~/pl-v2/changes/20261016/`.
- Source changes are committed **locally on GCP**, branch `gcp-v2/integrations-20261016` in three repos:
  auth-node **`69be867`**, student-node **`9fb8d3d4`**, question-manager **`ec66aff`**. They were not pushed
  to DEV/UAT/PROD release branches. Preserve/cherry-pick these commits before refreshing those checkouts
  with `clone.sh`. Phone worker allowlist source is in the separate build context above.

## Cutover (not started)

Freeze PROD writes → take a fresh dump/restore → reapply **both the indexes and the function migration**
and re-check disabled cron flags (a restore overwrites them) → deploy/promote the reviewed source fixes →
configure messaging and explicitly remove test-only phone/domain restrictions → enable the dispatch and
reminder jobs, FDN cron/worker and other required services → switch Route 53 to 35.244.18.184 and issue
certificates for real hostnames → give partners the GCP egress IPs → verify end to end. Keep OCI as fallback.
After the production webhook hostname reaches GCP, disable the temporary WhatsApp reconciliation timer
and remove the extra GCP email subscription if the original subscription already feeds the same backend.

## PROD bugs found during the migration (exist on live PROD; not fixed)
- `fast-api` live PROD config `DATABASE_URL_ASSESSMENT` points at the **UAT** DB (140.238.245.202:5441);
  fixed only on the GCP copy.
- Live PROD still has the multi-session proctoring requeue bug described above; the source fix currently
  exists only on the GCP branch.
- Student resume education update returns 400 "Body/CurrentCourse/Specialisation Must Be String" when no
  specialisation is selected (`student-react` EducationalDrawer sends `null`; `student-node` schema requires string).
- `Resume_parser` repo commits an OCI private key (`USING API/oci_api_key.pem`) — rotate and remove.
- `assessment-react` / `student-react` hardcode `https://api-std.staging.pluginlive.com` in `utils/localRequest.js`.
