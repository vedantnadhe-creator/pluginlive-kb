# Aptitude Question Verification — Validate-and-Repair

> Part of the Aptitude question pipeline (see `aptitude.md`). A verification cron audits
> **auto-generated** aptitude questions before they are usable and **repairs defects in place**
> (not just accept/reject).

## Problem it solves

Auto-generated aptitude questions occasionally shipped **broken** to students. Three failure
modes the *old* verifier was structurally blind to:

| # | Defect | Why the old verifier missed it |
|---|--------|--------------------------------|
| 1 | **Missing question stem** — a passage/statement with no actual question (e.g. a reading-comprehension item that jumps straight to options) | It handed the LLM the options and asked *"which option is correct?"*, so the model **back-filled the missing question** in its head and passed it. |
| 2 | **Answer not in the options** — e.g. the maths implies `1500/1200` but options show `500/200` | It asked only for an option **index**, forcing a pick among existing options, so it could never flag *"the real answer isn't here."* |
| 3 | **Wrong answer key** | "Pass" only meant the LLM agreed with the stored key; a mismatch merely **deactivated** (never repaired). |

Generation itself had no question-text validation (only a regex on the explanation's formatting),
so the verification step is the safety net.

## Pipeline

```
verify cron (admin-node/script/scheduler.js → questionManagerJob, COMMENTED by default)
  └─ admin-node/script/verifyWorker.js  verifyPendingQuestions()
       • fetches isReviewed = null aptitude questions, 5 at a time, with an in-memory lock
  └─ QuestionManager.verifyQuestionWithLLM(questionId)   (admin-node/app/models/QuestionManager.js)
  └─ FastAPI  POST /validate-question                    (fastapi-ai-engine/routers/aptitude.py)
```

## FastAPI `/validate-question` (model `gpt-5-mini`)

- **Solves the question from the stem first**, then reconciles its derived answer with the options.
- **Adds a missing stem**, **corrects options** so the right answer is present exactly once, and fixes the key.
- **Deactivates** (`isSolvable=false`) only if genuinely unsalvageable — it does **not** fabricate a brand-new question.
- Injects **per-subtopic reasoning scaffolds** (`fastapi-ai-engine/QuestionGeneration/Aptitude/verify_scaffolds.py`:
  3 category bases + 30 subtopic guides) by `subtopic`, so the model approaches each aptitude type with the
  right method. Scaffolds are **guidance, not a closed pattern list** (explicit non-exhaustive clause — verified
  on off-list patterns like Fibonacci, factorial, primes, 2ⁿ−1).
- Returns a **strict Structured Output** (OpenAI `json_schema`, `strict:true`) — always exactly these fields:
  `isSolvable, questionText, options, correctOption, correctAnswer, wasCorrected, changes, explanation, reason`.
- Request body: `{ question_text, options, difficulty, subtopic }`.

## admin-node apply (`QuestionManager.verifyQuestionWithLLM`)

- Keys the correct option by the derived **answer TEXT** (`correctAnswer`) matched against the final options —
  **robust to the model reordering options**. If it can't match exactly one option, the question is
  **deactivated** rather than keyed wrongly.
- Applies repairs in a single DB transaction (question text/explanation, rebuild option rows + key,
  set `isActive`/`isReviewed`).
- Writes one **audit row per outcome** to `assessment.question_verification_audit`.

## Audit table — `assessment.question_verification_audit`

| Column | Type | Purpose |
|--------|------|---------|
| `audit_id` | uuid PK | row id |
| `question_id` | uuid FK → `questions` (cascade) | which question |
| `outcome` | varchar(20) | `corrected` / `verified` / `deactivated` / `error` |
| `was_corrected` | boolean | whether anything changed |
| `correct_option_index` | integer | final keyed index |
| `changes` | jsonb | list of edits made |
| `before_snapshot` / `after_snapshot` | jsonb | full text + options + key, before vs after |
| `reason` | text | why deactivated |
| `error_detail` | text | failure detail |
| `created_by`, `created_at` | varchar / timestamp | `system-cron-verify`, time |

Indexed on `question_id`, `outcome`, `created_at`. Migration: DB-Scripts
`Aptitude Question Verification Audit/001_create_question_verification_audit.sql`.

## Status / gating

- The verify cron (`questionManagerJob`) is **commented out** in `admin-node/script/scheduler.js` — it must be
  uncommented to run, and a live `OPENAI_API_KEY` must be present in the FastAPI env.
- **Deployed:** DEV + UAT. **PROD:** pending.
- **Audit table:** applied on DEV + UAT. **PROD:** pending.

## Cost

~$0.0039 per question on `gpt-5-mini` with scaffolds (~85% cheaper than `gpt-5`). Output/reasoning tokens
dominate, so prompt/context caching gives only a marginal saving; the real levers are the smaller model and
the scaffolds (which also cut wasted reasoning).
