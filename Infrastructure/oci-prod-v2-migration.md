# OCI PROD v2 — isolated migration copy

Updated **2026-11-27**. The `*.v2.pluginlive.com` test hostnames reach the new
OCI environment, **not the earlier GCP copy**. Real PROD has not cut over; go-live
is planned for **Monday 2026-11-30** (see *Status and go-live checklist* below —
read that first; the sections after it are the history of how v2 got here).

## Status and go-live checklist (2026-11-27)

**Done**

| Area | State |
|---|---|
| Load / performance gate | Final full run on the go-live build **passed 2026-11-12**: 0 errors in 27,684 requests, submit p95 148 ms, DB CPU 64 %. Refresh rehearsals 8m23s / 8m42s (limit 30 min). Dress rehearsal 2026-11-09 passed. |
| Soak | 2026-11-04 → 11-18 finished; `tools/soak-report.sh` still runs daily from DEV cron. |
| Workers / security | `BACKGROUND_JOBS=off` web pods + 4 `<svc>-worker` containers on pl-v2-app; admin-node `isPrivate` restored on 40 routes (`e3b5bd91`); internal NLB `10.40.2.239` for mail-relay.v2 / corp-ats.v2. |
| Worker mail | Fixed: workers resolve `mail-relay.v2.pluginlive.com` to the internal NLB and reach it (returns 401 without the app key, i.e. reachable). The 11-04 "EMAIL_ENDPOINT unreachable" note is closed. |
| Role-metrics fix | `74b77e60` (the 10-30 `de7f1ed4` fix) is in corporate-node `v2-release` and deployed (`v2-release-0ed8a4e2`). **Not** in PROD `release-v1.43*` or `Development` — keep it when merging the new PROD release into `v2-release`. |
| Alerts | Topic `pl-v2-alerts`: 2 email subscribers ACTIVE, 2 PENDING confirmation. Budget `pl-prod-v2-monthly` ₹30,000 with 2 rules. |
| Weekend pause | Nodes + app VM stopped 11-21, restarted 11-23 by `~/pl-v2-setup/pause/v2-start.sh`. |

**Decisions (2026-11-27)**
- JWT: v2 keeps the **same JWT secret as PROD** (sessions survive the cut-over).
- Region: **Mumbai only**, no Hyderabad DR copy.

**PROD AWS uploads → OCI (`pl-prod-uploads`)** — bulk copy **done 2026-11-27** (10:27–11:20 UTC) from
pl-v2-app with `rclone copy aws:pluginlive-prod oci:pl-prod-uploads` (Docker `rclone/rclone`, config + log in
`~/s3copy/`, mode 600, start time in `bulk-started-at`). Verified exact: **201,036 objects / 68,650,291,757 bytes**
on both sides. Early PutObject 404s were IAM propagation and were retried by rclone. The v2 storage key
(group `pl-v2-storage`) was granted `manage objects` on `pl-prod-uploads` in tenancy policy `pl-v2-storage-policy`
(old statements backed up in `~/pl-v2-setup/pl-v2-storage-policy-backup-20261127.json`).
At cut-over, after PROD writes stop, run the same `rclone copy` again as the delta (it only copies new/changed objects).
The apps still point at `pl-v2-uploads`; switching upload/CV reads to `pl-prod-uploads` is a go-live step.

**Question Manager** — deployed 2026-11-27 at `https://question.v2.pluginlive.com` (Helm `question-manager` in `pl-web`,
values `deploy/values/question-manager.yaml`). Frontend only; calls admin-node `/questionManager/*`. Image
`pl-question-manager:v2-main-750cb2d` = PROD's image with the hardcoded "Production" admin URL changed to
`api-admin.v2.pluginlive.com` (otherwise v2 would edit live PROD's question bank). **At go-live switch back to
PROD's unchanged image.** Its GET routes (e.g. `getCountInfoOfQuestions`) answer without login, same as PROD.

**Release workflow** — `.github/workflows/v2-release.yml` in `pl-oci-v2-infra` (`release-v2`, manual trigger only,
self-hosted `pl-v2-runner`), script `deploy/release/v2-release.sh`, service list `deploy/release/services.txt`,
how-to + rollback in `deploy/RELEASE.md`. Builds arm64 image `<ref>-<sha8>` from the app repo (default `v2-release`),
writes backend `.env.prod` from Vault, re-applies the `oci-uploads` S3_ENDPOINT edits (corporate/student `v2-release`
lack them), fails a frontend whose bundle has non-`*.v2` pluginlive hosts, `helm upgrade --atomic` + host check with
auto `helm rollback`, updates matching worker containers on pl-v2-app. Deployer SA `pl-release/v2-deployer`
(only pl-api/pl-web/pl-ai). Proven 2026-11-27 with admin-react-v2 (same commit, Helm rev 5). Before first use:
add repo secret **`V2_SOURCE_TOKEN`** (fine-grained, Contents: read on the app repos) and start the runner
(`python3 tools/runner.py start`). fast-api needs `retinaface.h5` + `credentials.json` in `~/build-extras/fast-api/`
on the runner; institute-node uses a stored `package-lock.json` in `~/build-extras/institute-node/`;
student-node's Dockerfile runs `prisma migrate deploy` against the v2 DB during the build (same as PROD's build).

**Rollback replay** — `tools/rollback/` (`rb.py snapshot|diff|replay`, `changelog-install.sql`,
`changelog-remove.sql`, README). At cut-over, after the final restore and before DNS moves: install the change-log
triggers, run `snapshot`, keep old PROD frozen. To roll back: stop v2 writes → `diff` → `replay` (dry run) →
`--check` → `--apply` (one transaction) → DNS back. Timestamps alone miss updates on 140 of 291 tables and all
deletes, so the change log is required. Tested on scratch DBs (13/13 changes replayed, md5 match); never run against
old PROD. Not covered: files uploaded to v2 buckets after cut-over, v2-only schema changes, trigger cost under exam load.

**Unauthenticated admin-node routes (SQL reviewed 2026-11-27)**
- `POST /assessment/assign-practice-assessment` — all SQL is Prisma tagged templates (parameterised), no injection. But it has no auth: anyone can create practice assignments for any email. Caller: Assessment-React `src/utils/assignPracticeAssessment.js` (axios without a token). Fix = send the student token and check the body email against it; needs a frontend + backend change.
- `GET /admin/curd/export/:key` — Prisma ORM only, `key` picks a `switch` branch; no injection. Exports system-config tables (screens/events/sub-events). No auth because admin-react opens it with `window.open` (no token). Low risk.

**Cost (actual OCI usage, 2026-11-23 → 26)** — ≈ **₹1,075/day ≈ ₹32,300/month**, above the ₹30k budget
and the old ₹21–23k estimate (which assumed 1 OCPU DB). PostgreSQL ≈ ₹684/day (64 %; 2 OCPU/16 GB E5
plus the per-OCPU service fee), compute A1 ≈ ₹281/day, block storage ≈ ₹66/day, LB ≈ ₹28/day, logging ≈ ₹14/day.
Add after go-live: `pl-prod-uploads` storage (~69 GB + versions) and the build runner when it runs.

**Monday 2026-11-30 (go-live day), in order**
1. Merge PROD's current release branch (keep corporate-node `74b77e60`) (`release-v1.43-hotfix-*`) into each repo's `v2-release`, rebuild and deploy through the v2 release workflow; apply the DB-Scripts PROD got after the v2 copy, and the `Assessment Performance Indexes` scripts still "PROD — pending".
2. Stop PROD crons/background jobs; final PROD dump → v2; reset `drive_state` webhook + `start_page_token`; install rollback change log + `rb.py snapshot`.
3. Delta copy of `pluginlive-prod` → `pl-prod-uploads`; point uploads at it; switch question-manager back to PROD's image.
4. Messaging switches: auth-node `SMS_ENABLED`, `WHATSAPP_DISABLED`, `WA_OTP_ENABLED` to PROD values; remove `MAIL_ALLOWED_RECIPIENT_DOMAINS` and the `[v2]` tag; `SLACK_ACTIVITY_ENV` to PROD's; MSG91 delivery webhook → v2.
5. Move `*.pluginlive.com` DNS to the v2 LB `130.210.5.156`. Certificates are HTTP-01, so each live host only gets its certificate after its DNS points at v2 — expect a short TLS gap per host unless certificates are pre-issued with DNS-01 (needs a Route 53 key).
6. Cut a new release branch; run Jev sanity on the live hosts.
The current rebuild plan is `~/oci-plan/pluginlive-oci-rebuild-plan-2026-10-27.html`
(version 2.0, 2026-10-28). Phase 5 is load testing, regression, refresh rehearsals
and a two-week soak; go-live remains a separately approved phase.

## Topology and access

| Component | Current setup |
|---|---|
| Compartment / VCN | `pl-prod-v2`, `10.40.0.0/16`, Mumbai |
| Kubernetes | OKE Basic `pl-v2-oke`, v1.36.4, private API `10.40.2.252:6443` |
| Node pool | `pl-v2-pool-a1`, 2 × A1 3 OCPU / 12 GB, autoscaler range 2–3 |
| Public ingress | OCI flexible LB `130.210.5.156`, **10–100 Mbps**, ingress-nginx 4.15.1 |
| Ingress replicas | Two, one per worker node; revision-aware hard topology spreading |
| PostgreSQL | `pl-v2-pg16`, E5, private `10.40.3.233`, database `prod_pluginlive`; **2 OCPU / 16 GB**, Active after the 12m24s resize |
| PostgreSQL backup | Daily 21:30 UTC, 30 days |
| App server | `pl-v2-app`, public SSH `150.230.233.167`, key `~/.ssh/pl_v2_app` |
| App-server containers | Redis, code runner, SQL sandbox, corporate AI-match worker, corporate-v2 worker, normalization worker |
| Uploads | Separate bucket **`pl-v2-test-uploads`**; tests must never delete from live buckets |
| Build runner | `pl-v2-runner`, A1 4 OCPU / 24 GB, private `10.40.1.118`, on demand |

From DEV: `~/pl-v2-setup/k` runs kubectl and `~/pl-v2-setup/h` runs Helm through
the app server's SSH tunnel. Infrastructure source is `~/pl-oci-v2-infra`;
Terraform binary is `~/pl-v2-setup/terraform` (1.17.1). State is in versioned OCI
bucket `pl-v2-tfstate`, key `pl-prod-v2/terraform.tfstate`. Never commit state,
Vault values, API keys, test JWTs or test-attempt backups.

Web, API and AI services are separate deployments in `pl-web`, `pl-api` and
`pl-ai`. Existing backend release images still start some crons in process, so
student/admin/corporate/institute APIs remain at one replica. Student-node's
single replica is the exam-path baseline; do not raise its HPA maximum until its
crons are separated. FastAPI scales 1–3 and the assessment frontends have two copies.

## Pre-test infrastructure changes

- Raised the load-balancer maximum from 10 to 100 Mbps; OCI reports the flexible
  shape Active. This prevents the original fixed-10-Mbps bandwidth limit from
  dominating the candidate-burst test.
- Installed standalone cluster autoscaling (Basic clusters cannot use the
  managed add-on). A temporary 1500m CPU probe caused 2 → 3 nodes; it was deleted.
  The smoke test also scaled FastAPI 1 → 3 → 1, and the node pool returned to 2.
  Terraform ignores the autoscaler-owned node count. The v2 dynamic groups and
  runtime/autoscaler IAM policies are imported into Terraform.
- Applied all nine indexes from DB-Scripts `Assessment Performance Indexes/20261015*.sql`
  to v2 and verified they are valid. This does **not** mean the scripts have been
  applied to live PROD.
- Added 11 OCI soak alarms and a **₹30,000/month** compartment budget. The
  custom-metrics collector runs on the app server once a minute under
  `pl-v2-metrics.timer`, namespace `pl_v2`. It tracks ingress requests/5xx,
  container restarts/readiness, timestamped BullMQ failures and app-container state.
  Counters are tracked by identity so pod replacement does not distort totals.

**Alert delivery is incomplete:** no recipient has been supplied. The topic
`pl-v2-alerts` has no subscriber, and budget email rules are not created without
`alert_emails`. Configure an ignored local `alerts.auto.tfvars` file, review/apply
Terraform and have each recipient confirm the OCI subscription. Metrics arriving
and alarms reporting OK do not verify that a person will receive alerts.

## Database gate and prepared application correction

The per-campus eligibility probe on 1 OCPU reached a maximum of **11.753 s**,
within the plan's 13-second limit. It did not prove that the broader role report
passes. That report currently references the missing relation
`corporate.drive_role_candidate_map`; the relation is in `student`. A read-only
check confirmed the same missing corporate relation on current live PROD, so this
is an existing application issue rather than a missing v2 restore table.

A corporate-node correction is committed locally on branch
`fix/oci-v2-role-metrics-20261030`, commit `de7f1ed4`, worktree
`~/worktrees/oci-v2-role-metrics`. It fixes the schema references, restricts work to
the role's metric rows, computes predicates once, preserves closed-role snapshots
and avoids serializing unused/full role records for restriction checks.
It has **not** been deployed or pushed to any release branch.

Five comparisons against the release model with only its schema typo corrected
matched every stored business field. They cover actual/open roles, frozen and
unfrozen campuses, and a cohort with enabled institute rules. Each comparison
verified rollback, so no report metrics persisted from those checks.

The approved fallback to 2 OCPU / 16 GB is complete. Also applied the **student
function only** from DB-Scripts
`Assessment Performance Indexes/20261016T083555Z__optimize_role_float_eligibility_functions.sql`.
Compared the old and new student eligibility functions on **11,410 actual inputs**
(7,604 + 3,806), with zero mismatches, before committing the replacement in the
same transaction. The original function is backed up at
`~/oci-loadtest/eligibility-before.sql`. This operation changed neither the
corporate-schema function nor live PROD.

The selected full reports with prepared application source now run in **12.299 s**
and **0.953 s**, within the 13-second limit, with all report updates rolled back.
The running application still needs its reviewed image built and deployed after
explicit approval. These two query measurements do not establish full-load p95
or complete the end-to-end performance gate.

## Load-test kit and first smoke

The GCP runner was ported to OCI in `~/pl-oci-v2-infra/tools/loadtest/`, with
runtime files under `~/oci-loadtest/`. It pins TLS traffic to **130.210.5.156**,
verifies certificates, checks token sufficiency/uniqueness and reports incomplete
candidate tasks as failures. Tokens are minted inside the v2 student-node pod
for existing internal Demo College Aptitude attempts; 330 were prepared. This
does not send invitations or create real candidates.

`data.js` backs up selected internal attempts and their dependent rows, validates
the database IP/map/email prefix, and restores the snapshot after testing. Test
uploads must be verified against recorded exact keys and byte sizes, then deleted
only from `pl-v2-test-uploads`. Keep JWTs and backups private and out of git.

First smoke: **10/10 completed and scored**, **488 HTTP requests, zero errors**,
**42/42 proctoring uploads stored at the expected size**. All 10 attempts were
restored and the 42 objects deleted. Reports: `~/oci-loadtest/smoke10/`.
Submit p95 was **703 ms**, upload p95 **232 ms**, invite p95 **111 ms**. This is a
functional smoke, not the full workload or a passed latency comparison.

After the completed resize and student-function optimization, a second smoke
completed **10/10**, **484 requests / zero errors**, **40/40 uploads** at the expected
size. The attempts were restored and the 40 exact object keys removed. Reports:
`~/oci-loadtest/smoke10-afterdb/`; p95 invite **125 ms**, submit **468 ms**, upload
**229 ms**. This still does not pass the full workload/latency gate, and the
historical GCP submit p95 (402 ms) is lower.

Cold scaling still needs validation: a fresh node's FastAPI image pull was
**15m11.935s** for a **10,956,650,165-byte** image during the second smoke. HPA
returned to one replica before the extras started; they stopped and were removed,
while the primary stayed healthy. The readiness metric excludes terminating pods
so intended scale-down does not become a false outage. Check cold workload
readiness separately from node scale-up during the full load run.

Remaining Phase-5 work after preflight: full **240 starts/hour for 30 minutes
(120 starts), then 100 starts within 60 seconds**, real sittings with answers and
proctoring; Jev regression against v2; two timed refresh rehearsals (≤30 min);
two-week soak with working alert delivery; repricing from actual bills. The
original **₹21.3–23.3k/month** estimate used 1 OCPU and must be revised after resizing.

The detailed runnable procedure and rollback-aware checks are in
`~/pl-oci-v2-infra/deploy/PERFORMANCE.md`.

## v2 fixes, 2026-11-04 to 2026-11-16

Config lives in OCI Vault `pl-v2-svc-<service>`; generator `tools/gen_v2_config.py` and guard `tools/check_v2_config.py` in `pl-oci-v2-infra` (branch `release-v2`); details in its `deploy/DEV-HANDOFF-20261103.md`.

| Area | Current v2 behaviour |
|---|---|
| Uploads (`/signedURL`, server-side S3 uploads) | Go to private OCI bucket `pl-v2-uploads` through the S3-compatible API (`S3_ENDPOINT`, OCI keys in the `AWS_*` variables); read through a bucket-scoped read-only pre-authenticated link set as `CLOUDFRONT_URL` (listing denied, expires 2027-11-04). AWS is not used. |
| Public student documents (CVs) | `PUBLIC_OCI_BUCKET_NAME=pl-v2-public-docs`, public read without listing (PROD: `pl-uat-public-docs`, ObjectRead). 25 CVs uploaded earlier to the private bucket were moved and their links rewritten. |
| CV parse-and-store / JD parse | fast-api `cv-parser/parseResumeAndUpload` stores to `pl-v2-uploads` with an API key of `pl-v2-storage-bot`; form-data-normalization `PDF_PARSER_URL` points at it. |
| Search-service writes | institute, corporate and student services use `ELASTICSEARCH_URL=http://search-service.pl-api.svc.cluster.local` (workers on pl-v2-app: `https://search.v2.pluginlive.com`) with search-service's admin key, as PROD does. Blank values made college/degree/stream create fail after saving. |
| Normalisation | API and worker use v2 values for `BASE_URL`, `ENTITY_NORMALIZER_API_URL`, `EXPORT_LINK_BASE_URL` and LiteLLM (own key `v2-form-data-normalization`); the code defaults point at live PROD. `form-data-normalization-cron` runs on pl-v2-app and registers v2's own Drive webhook; the copied PROD `drive_state.webhook_data` was cleared first because registration stops the previous channel. The Google Forms API 403 per form (also on PROD) only slows ingest. After copying a PROD database, also reset `drive_state.start_page_token` to Drive's current start token: v2 kept the 28 Oct token, so every webhook began a catch-up that never finished and real-time ingest inserted nothing until it was reset on 2026-11-17. |
| Email, SMS, WhatsApp, Slack | PROD keys copied. Slack is live (posts tagged V2). SMS, WhatsApp and WhatsApp OTP stay off (`SMS_ENABLED=false`, `WHATSAPP_DISABLED=true`, `WA_OTP_ENABLED=false`) and mail-server only delivers to `@pluginlive.com` until go-live. v2 auth-node has no phone allow-list code. |
| Google sign-in | OAuth client `641154247196-9b3p…` lists `https://auth.v2.pluginlive.com` and `https://api-auth.v2.pluginlive.com/auth/google/callback` (added 2026-11-16). |

Go-live order for messaging: stop PROD crons and background jobs, turn on the three auth-node switches, remove the mail domain rule and `[v2]` tag, set PROD's Slack tag, point the MSG91 delivery webhook at v2.

### Branch policy (2026-11-16)
v2 deploys from a `v2-release` branch in each repo: `release-v2` (v2-only fixes) merged with PROD's current release branch, so v2 runs PROD code plus what v2 needs, against its PROD-copy schema. First build: PROD `release-v1.42-hotfix-4` (admin/corporate/institute/student), with `scoring_issues` applied to the v2 DB. Later PROD hotfixes: merge into `v2-release`, rebuild what changed, apply any DB script PROD applied after the copy. A new release branch is cut at go-live. Not UAT: UAT code needs 46 UAT-only DB scripts and carries Attempt Integrity, which is held for PROD.
