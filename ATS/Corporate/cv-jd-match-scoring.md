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

- **Response-schema drift via gateway** (UAT, 2026-07-01): Gemini through the
  in-cluster `http://litellm/v1` (Portkey/LiteLLM) shim **does not enforce**
  the google-genai `response_schema`/`response_mime_type=application/json`
  contract. `extract-criteria` and `/evaluate` may return:
  - a JSON object matching the schema (works),
  - a bare list of objects (`[{"criterion": "..."}]`),
  - or a list of strings. This causes Pydantic validation errors and 500s.
  Commit `c381b62` (deployed to DEV/UAT) disabled Gemini thinking and added
  `_parse_json` to tolerate markdown fences/outer JSON, but it still expects
  the top-level response to conform to the schema. A further manual coercion
  of list responses into the expected `CriteriaExtractionResult` /
  `EvaluationResult` shape is needed when the gateway ignores the schema.
- **Retry loop** (resolved 2026-07-01 in corporate-node via
  `ai_match_status='failed'` dead-letter columns): recovery no longer
  re-enqueues candidates whose job has exhausted its 3 attempts. Manual
  re-trigger clears the marker.

## Key files

- corporate-node: `app/handlers/aiMatchHandler.js`, `app/queue/aiMatchQueue.js`,
  `app/queue/aiMatchWorker.js`, `app/queue/aiMatchRecovery.js`, `index.js`.
- fastapi-ai-engine: `routers/resume_match.py`,
  `ResumeMatchScoring/resume_matcher.py`, `utils/executors.py`.
