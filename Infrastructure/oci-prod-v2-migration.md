# OCI PROD v2 — isolated migration copy

Updated **2026-10-30**. The `*.v2.pluginlive.com` test hostnames now reach the new
OCI environment, **not the earlier GCP copy**. Real PROD has not cut over.
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
