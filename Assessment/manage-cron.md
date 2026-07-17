# Manage Cron — DB-driven scheduler on/off

> Turn the assessment scheduler crons on/off **per environment** from the Question Manager
> UI, without a redeploy. Supersedes the old approach of commenting the jobs in
> `scheduler.js`.

## The three managed jobs
| `job_name` | Cron | Schedule |
|------------|------|----------|
| `communication_gen` | Communication question/set generation | every 10 min |
| `aptitude_gen` | Aptitude question generation | every 10 min |
| `question_verification` | Aptitude question **review/verification** (validate-and-repair, see `question-verification.md`) | every 11 min |

## How it works
- `admin-node/script/scheduler.js` registers each job with `node-cron`, but **every tick first
  checks `assessment.cron_config.is_enabled`** for that `job_name` (`isCronEnabled()`).
  Fail-safe: missing row / read error ⇒ the job does **not** run.
- Flipping the flag takes effect on the **next tick** (≤ ~10–11 min) — no redeploy.
- All jobs seed **disabled**, so promoting the code changes nothing until someone enables a job.
- Multi-replica safety: the existing `assessment.cron_locks` table + `tryLock()`/`releaseLock()`
  ensures only one replica's tick actually runs.

## Tables (`assessment` schema)
- **`cron_config`** — `id`, `job_name` (unique), `is_enabled`, `description`, `updated_by`,
  `updated_at`, `created_at`. One row per job.
- **`cron_locks`** — `lock_name` (PK), `locked_by`, `locked_at`. Cross-node coordination
  (was referenced by the scheduler but previously never created).

Migration: DB-Scripts `Question Manager Cron Config/…__cron_config_and_locks.sql`.

## API (admin-node, question-manager module)
- `GET  /questionManager/cronConfig` — list all jobs with enabled state + last-changed-by/at.
- `PUT  /questionManager/cronConfig/:jobName` — `{ isEnabled }`, records `updated_by` from the token.
- **Auth:** both require a valid question-manager **JWT** (issued by that env's
  `/questionManager/LogIn`, role `question_manager`, verified against the env's `JWT_SECRET_KEY`).
  Cron toggling is more sensitive than the other (open) question-manager endpoints, so it is gated.
  Requires `QUESTION_MANAGER_USERNAME` / `QUESTION_MANAGER_PASSWORD` in the env.

## UI — Question Manager (`question.pluginlive.com`, PROD-only)
- **Environment-first login:** choose the environment, then log in; the login request (and all API
  calls) go to **that env's** admin-node. Token is stored **per env** (`authToken_<env>`) — logging
  into DEV does not log you into UAT/PROD; each env is asked once and persists until storage is cleared.
- **"Manage Cron"** button (top header) → modal listing the 3 jobs with on/off toggles + which env
  you're managing. Toggling calls the API above.
- The single PROD-deployed UI can drive **any** env via the env selector (admin-node CORS is `*`),
  but that env must have the cronConfig backend + `cron_config` table + QM creds.

## Manage Buffers — sibling feature (aptitude generation targets)

The same Question Manager UI + auth pattern now also drives **per-topic × per-difficulty generation buffer targets** for the aptitude cron (how many questions it maintains per cell). See `aptitude.md` → "Dynamic generation buffers".
- **UI:** "Manage Buffers" button (header, next to "Manage Cron") → modal table of topic / difficulty / in-bank count / editable target, for the selected env.
- **API:** `GET /questionManager/generationTargets` (list) · `PUT /questionManager/generationTargets` (`{ updates: [{ subSectionId, difficulty, target }] }`) — same question-manager JWT gate, target range 0–500.
- **Backing:** `assessment.aptitude_topic_band_config.buffer_target`. Band cells default 6; non-band cells use a small insurance floor (2) in the generator.
- **Status:** DEV + UAT ready (2026-07-17). PROD backend (admin-node endpoints + `buffer_target` column) **pending**, same as cron config.

## Per-environment status
Each env's flags live in its own DB. Readiness (backend + table + creds):
- **DEV** — ready. (`question_verification` was enabled here for testing.)
- **UAT** — ready (2026-07-10).
- **PROD** — **pending** (backend + `cron_config` table + QM creds not yet deployed).
