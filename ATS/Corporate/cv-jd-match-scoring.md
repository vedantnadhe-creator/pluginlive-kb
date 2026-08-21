# CV vs JD Match (AI Resume Scoring)

How candidate resumes are scored against a role's job description in the
Corporate ATS. Spans **corporate-node** (orchestration) and
**fastapi-ai-engine** (the LLM scoring).

## What it does

When candidates are moved into a role's evaluation process, each candidate's
CV is scored against the role's JD using **Gemini 2.5 Flash** (LLM-as-a-judge,
not embeddings). The result (overall score, star rating, per-criterion
breakdown, strengths, gaps) is stored on the candidate's role mapping and shown
to recruiters.

Two phases:

1. **Extract criteria** (once per role, cached): the JD (structured role fields
   + optional JD PDF) is turned into 5–10 weighted criteria.
2. **Evaluate** (once per candidate): each criterion is scored 0–5; the overall
   score is the weighted average.

## Architecture (BullMQ + Redis)

Scoring runs **asynchronously on a Redis-backed BullMQ queue**, processed by a
dedicated worker at **concurrency 5** (≈5 candidates scored in parallel).

```
corporate-node (web)                Redis (BullMQ)            corporate-node (worker)        fastapi-ai-engine        Gemini
────────────────────                ──────────────            ───────────────────────        ─────────────────        ──────
candidates → evaluation
  getOrCreateCriteria(role) ──/resume-match/extract-criteria──────────────────────────────────────────────►  criteria (cached on role)
  enqueue 1 job/candidate ─────────►  cv-jd-match-<env>  ──────►  worker (concurrency 5)
                                                                    evaluateCandidate ──/resume-match/evaluate──►  score ──► save to DB
```

- **Trigger:** when candidates move from `all_candidates` → `TO_BE_SCHEDULED`
  (`corporateEvaluationHandler`), `triggerAiMatchForCandidates` extracts criteria
  once and enqueues one job per candidate. The HTTP response does not wait for
  scoring.
- **Worker:** runs as a child process auto-started by `index.js`
  (`npm run ai-match-worker`), self-heals on crash. Idempotent — skips
  candidates that already have a score.
- **Manual/batch:** `POST /corporates/drive/:driveId/role/:roleId/ai-match/trigger`
  (enqueues; `?forceRefresh=true` re-scores; also resets any dead-letter marker).
  Status: `GET .../ai-match/status` → `{ total, scored, failed, pending, queue:{...} }`
  (`pending` excludes terminally-`failed` candidates).

## Resume formats — PDF, DOC, DOCX

`/evaluate` takes **either** `resume_text` (used as-is) **or** `resume_url`
(downloaded, then text-extracted). `resume_text` wins when both are set and
skips the download/parse entirely — the response's `evidence_source` says which
was used (`RESUME_TEXT` / `RESUME_PDF` / `SYSTEM_PROFILE`). Note `RESUME_PDF` is
a historical label meaning "extracted from the uploaded file" — it is reported
for **any** supported format (a `.doc` also says `RESUME_PDF`). Nothing reads the
field today; it is stored in `ai_match_score` for debugging.

Format is detected from **magic bytes**, not the URL extension or Content-Type:
object storage serves every resume as `application/octet-stream`, candidates
upload `.doc` files named `.pdf`, and some stored `cvUrl`s carry no extension at
all. `utils/document_text.py` routes by signature:

| Detected | Extractor | Notes |
|---|---|---|
| `pdf` (`%PDF`) | PyMuPDF (`fitz`) | preamble/BOM before the header tolerated |
| `doc` (OLE2 `d0cf11e0`) | `antiword` (system pkg in the Dockerfile) | legacy Word 97–2003 |
| `docx` (zip + `word/document.xml`) | `python-docx` | **includes table cells** — resumes lean on tables, and `document.paragraphs` alone silently drops that text |
| anything else (images, `.odt`) | — | `422` naming the detected type; scanned images would need OCR |

Unit tests: `test_document_text.py` (standalone `unittest`; fixtures generated at
runtime so no candidate PII lives in the repo). Note `.dockerignore` excludes
`test*.py`, so tests are not shipped in the image.

## Data

- `corporate.job_roles.ai_match_criteria` (JSON) — cached criteria per role.
- `corporate.job_role_student_map.ai_match_score` (JSON) — per-candidate result
  (`overall_score`, `star_rating`, `criteria_matched/total`, `criteria_scores[]`,
  `strengths[]`, `gaps[]`, `evidence_source`).
- **Dead-letter columns on `job_role_student_map`** (migration `Corporate CV-JD
  Match Retry Cap/001`):
  - `ai_match_attempts` (int, default 0) — attempts made on the last job.
  - `ai_match_status` (text) — `NULL` = pending, `'failed'` = retry budget
    exhausted (do not auto-retry).
  - `ai_match_last_error` (text) — last failure message (truncated 500 chars).
- Queue + recovery lock live in **Redis**, not Postgres.

## Resilience

- **Retries — capped at 3, then dead-lettered:** each job retries 3× with
  exponential backoff (BullMQ `attempts`). When a job **exhausts its attempts**,
  the worker's `failed` handler sets `ai_match_status='failed'` (+ `ai_match_attempts`,
  `ai_match_last_error`) on the candidate row. This is a **hard cap** — after 3
  attempts a candidate is **not** retried automatically again.
- **Loop-breaker:** the recovery sweep **excludes `ai_match_status='failed'`
  rows**. Before this, the sweep re-enqueued any `ai_match_score IS NULL`
  candidate every 2 min, so BullMQ's 3-attempt cap reset endlessly — a
  persistently-failing candidate (or an engine outage) looped forever and
  hammered `fastapi-ai-engine`. Now a failure is recorded and left alone.
- **Manual override / re-score:** an explicit trigger
  (`triggerAiMatchForCandidates` and the `/ai-match/trigger` endpoint)
  **resets** the marker (`ai_match_status=NULL, ai_match_attempts=0,
  ai_match_last_error=NULL`) before enqueuing, granting a fresh retry budget.
  So after fixing an engine issue, re-scoring a role/candidate is a deliberate
  human action. For a bulk re-score of an outage backlog:
  `UPDATE corporate.job_role_student_map SET ai_match_status=NULL, ai_match_attempts=0 WHERE ai_match_status='failed';`
- **Crash-safe:** jobs live in Redis, so a corporate-node restart resumes them;
  in-flight jobs of a dead worker are reclaimed via BullMQ stalled-job recovery
  (`lockDuration` 130s > the 120s axios timeout).
- **Recovery sweep:** every 2 min (and on worker boot) a distributed-lock sweep
  (modelled on admin-node `generationRecovery.js`) re-enqueues candidates that
  are in evaluation, unscored, **not dead-lettered**, and have no live queue job.
  **Scoped to a recent window** (`AI_MATCH_RECOVERY_WINDOW_HOURS`, default 24h) so
  it recovers recently-lost jobs only — it does NOT backfill historical backlog.
  (Historical backfill, if ever wanted, must be a deliberate throttled operation.)
- **Rate limiter:** worker capped at 5 jobs/sec to protect the Gemini rate limit.

## Concurrency coupling (important)

Real parallelism needs **both** sides aligned:

| Setting | Service | Value |
|---|---|---|
| worker `concurrency` (`AI_MATCH_CONCURRENCY`) | corporate-node | 5 |
| `MAX_CONCURRENT_SCORING` | fastapi-ai-engine | **5** |
| `BACKGROUND_WORKERS` | fastapi-ai-engine | 6 |

If `MAX_CONCURRENT_SCORING` stays at 1, FastAPI serializes the 5 requests behind
its scoring semaphore → scoring still works but with **no speedup**. Live
proctoring / AI-interview endpoints are `PRIORITY_PATHS` and bypass that
semaphore, so raising it does not affect live traffic.

## Shared Redis — per-environment queue namespacing

DEV and UAT **share one Redis instance** (`129.154.231.72:6377`) but have
**separate databases**. The queue and recovery lock are therefore namespaced by
`QUEUE_ENV` (`cv-jd-match-dev` vs `cv-jd-match-uat`), set in `.env.dev` /
`.env.uat`. Without this, one environment's worker could consume the other's job
and look the candidate up in the wrong DB.

## Key env vars

**corporate-node:** `QUEUE_ENV` (dev|uat — namespaces the queue),
`RUN_AI_MATCH_WORKER` (default on; set `false` on extra replicas so total
concurrency stays = FastAPI limit), `AI_MATCH_CONCURRENCY`,
`AI_MATCH_RECOVERY_WINDOW_HOURS`, `AI_MATCH_RECOVERY_INTERVAL_MS`,
`AI_MATCH_LOCK_DURATION_MS`, reuses `REDIS_URL` + `FASTAPI_AI_ENGINE_URL`.

**fastapi-ai-engine:** `MAX_CONCURRENT_SCORING=5`, `BACKGROUND_WORKERS=6` (set in
both `.env` and `.env.uat`).

## Skipped roles

Roles open **only** to ITI / Diploma candidates skip AI match entirely
(vocational-only exclusion).

## Known gotchas / recent issues

- **Cached criterion text can outlive a display fix** (UAT, 2026-08-21): role
  `e3905f0a-2000-4502-9508-549802a479ed` had 9 older `ai_match_score` JSON
  records whose `criteria_scores[].text` still ended in `(weight: N/10)`, while
  2 newer scores were already clean. The running UAT AI engine contained the
  `_clean_criterion_text` fix, so this was stale persisted output rather than a
  current generation bug. The 9 affected records were cleaned in place without
  changing scores, reasons, or the role's internal criterion weights; post-fix
  verification was 11 scored records, 0 containing `weight:`. For the same
  symptom on an older role, inspect persisted `ai_match_score` before redeploying
  or re-scoring—the internal `ai_match_criteria[].weight` remains intentional and
  must not be removed because it drives the weighted average. **Follow-up:** DB
  cleanup alone did not reliably remove the already-returned text from the v1
  candidate drawer. Corporate React commit `cc6c052a8` (UAT merge `130c44f5e`)
  adds a final presentation-layer guard to both the criteria tooltip and Risk
  Signals chips, stripping a trailing `(weight: …)` before rendering. Deployed
  to UAT on 2026-08-21; use this UI guard as defence-in-depth even though the AI
  engine also cleans newly generated criterion text.
- **Response-schema drift via gateway** (UAT, 2026-07-01, **fixed**): Gemini
  through the in-cluster `http://litellm/v1` (Portkey/LiteLLM) shim did not
  enforce the google-genai `response_schema`/`response_mime_type=application/json`
  contract. `extract-criteria` and `/evaluate` returned bare lists, dicts keyed
  by criterion id, or even invalid JSON (missing commas). Commit `c381b62`
  (Mari Selvam) disabled thinking and added markdown/outer-JSON tolerance; a
  follow-up patch added `_repair_jsonish` + `_coerce_to_schema` to normalize
  lists, dict-keyed scores, `evaluated_criteria`/`criterion`/`rationale`/`evidence`
  keys, and mixed scalar+dict responses. Deployed to DEV/UAT 2026-07-01.
- **Criteria lost category/weight + garbled strengths** (DEV+UAT, 2026-07-03,
  **fixed**): the root cause behind the drift above — `utils/portkey_gateway.py`'s
  shim collapsed **any** `response_schema` into `response_format={"type":
  "json_object"}` (unconstrained "return some JSON"), so Gemini stopped honouring
  the strict Pydantic contract entirely. The `_coerce_to_schema` fallbacks kept
  the endpoints from 500ing but only *masked* it: every criterion rendered
  `[other]` category + `weight 5/10` (the fallback defaults), and when the model
  omitted `strengths`/`gaps`/`match_summary` the code synthesized them from raw
  criterion text — so the "Why to Shortlist" / Strengths panel showed dumps like
  `c3. [other] Experience in B2B or B2C sales. (weight: 5/10) (score 5)` instead
  of clean sentences. Fix: the shim now forwards the Pydantic schema as an OpenAI
  `response_format={"type":"json_schema","json_schema":{...,"strict":true}}`,
  which LiteLLM passes to Gemini as native structured output. Criteria come back
  with real categories (`experience`/`education`/`skills`/…) and varied weights,
  and strengths/summary are proper sentences. Non-Pydantic / mime-only callers
  keep the old `json_object` path (backward compatible; the `_coerce_to_schema`
  net stays as defence-in-depth). `fastapi-ai-engine` Development→UAT.
- **Non-PDF resumes 422'd forever** (all envs, **fixed 2026-07-15**, DEV+UAT):
  `fetch_and_parse_pdf` wrote *every* download to a `.pdf`-suffixed temp file and
  handed it to PyMuPDF regardless of the actual bytes, so any non-PDF resume died
  with `Unable to fetch/parse resume: Failed to open file '/tmp/x.pdf' as type
  pdf` → 422 → 3 attempts → `ai_match_status='failed'` → **0 stars / "NA" in the
  corporate UI forever**. It reads like an engine outage but is not: the file
  downloads fine (200) and other candidates on the same role score normally —
  **check the `cvUrl` extension first**. Fixed by magic-byte detection + per-format
  extractors (see *Resume formats* above); `fetch_and_parse_pdf` is now
  `fetch_and_parse_document`. PROD exposure at the time: **553 `.doc` + 1766
  `.docx` + 3 `.odt`** of ~40k stored resumes. **No backfill was run** — affected
  candidates re-score on the next trigger (`?forceRefresh=true`, or clear
  `ai_match_status`/`ai_match_score` and re-enqueue); until then they keep showing
  their stale 0/NA.
- **Retry loop** (resolved 2026-07-01 in corporate-node via
  `ai_match_status='failed'` dead-letter columns): recovery no longer
  re-enqueues candidates whose job has exhausted its 3 attempts. Manual
  re-trigger clears the marker.
- **Pycache gotcha during hot-patches**: replacing a `.py` in a running uvicorn
  container can leave stale `__pycache__` loaded. Validate by deleting the
  pycache and restarting the container; production deploys via fresh image
  avoid this.

## Key files

- corporate-node: `app/handlers/aiMatchHandler.js`, `app/queue/aiMatchQueue.js`,
  `app/queue/aiMatchWorker.js`, `app/queue/aiMatchRecovery.js`, `index.js`.
- fastapi-ai-engine: `routers/resume_match.py`, `utils/document_text.py`
  (format detection + text extraction), `ResumeMatchScoring/resume_matcher.py`,
  `utils/executors.py`.
