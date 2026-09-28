# AI Interview — On call (phone delivery)

**Status:** DEV + UAT live (UAT since 2026-09-28). **PROD: not deployed** (needs the DB scripts, the call worker, env and a Plivo number there).

An AI Interview can be delivered by an **outbound phone call** instead of an emailed link. The interview itself is the
normal web AI Interview: the call worker drives student-node's own session endpoints, so questions, scoring and the
report are identical. Only the delivery channel differs.

## How an admin uses it

- **Create:** AI Interview config → **On call** switch (`interviewConfig.stageConfig.deliveryMode = 'call'`).
  Available in legacy admin (`CreateAIInterview.js`) and the v2 wizard (`@pluginlive-technologies/assessment-creation` ≥ 0.1.13).
- **Rules enforced at float (BFF + admin-node):** every candidate needs a mobile number; an on-call interview is floated
  **on its own** (not in a Mix & Match bundle) and never as a recurring schedule. **No invite email and no 24 h reminder**
  is sent for on-call floats.
- **Per-candidate call time (v2 wizard, Step 3):** every candidate gets a suggested *Call time (IST)* (2 calls per slot,
  10 AM–7 PM) that the admin can edit — any time from **now + 5 min** to the last start that still ends inside the
  assessment window (end date 23:59 when no end time). Sent as `bulkUploadData[].call_at`; admin-node validates it and
  books the slot at exactly that time. Without a picked time, the cron auto-plans inside 10:00–19:00.
- **Call schedule panel** (legacy admin → Assessment Details, and v2 `/assessment/call-schedule`): each candidate's
  call time, status, attempts, last outcome, **recording player(s)**; edit time / number, cancel, call again.
- Assessment list shows an **On call** tag on such interviews.

## Architecture

| Piece | Where |
|---|---|
| Slots + dispatcher | admin-node `AiInterviewCallService`, `models/AIInterviewCallSlot.js`, cron job `ai_interview_call_dispatch` (every minute, gated by `cron_config`, `cron_locks`, `FOR UPDATE SKIP LOCKED` claim) |
| Call worker | `fastapi-ai-engine/call_interview` (Pipecat 0.0.108, Python 3.10), runs as systemd `call-interview` on `127.0.0.1:8021`, public at `https://<env host>/call-interview/` (nginx location with WebSocket upgrade) |
| Telephony | Plivo, number **+91 80 3182 7332** (shared by DEV and UAT), bidirectional `<Stream>` μ-law 8 kHz |
| STT / TTS | Deepgram nova-3 live (`en`, or `multi` for any non-English interview — Hinglish on `en` was unusable); TTS via fastapi `/ai-interview/tts` with the interview's configured voice + language |
| Consent / reschedule NLU | fastapi `POST /ai-interview/call-brief`, `POST /ai-interview/call-intent` |
| Interview | student-node `POST /ai-interview/session/start|turn|complete` (keyed by `assessmentAssignedId`) |

Slot lifecycle: `SCHEDULED → DIALING → IN_CALL → COMPLETED | DROPPED`; no answer → retry +30 min (max 3 attempts) →
`UNREACHABLE`; candidate asks for another time → `RESCHEDULE`; admin → `CANCELLED`; no valid mobile → `NO_PHONE`.
Admin-picked times may be outside calling hours; automatic plans, retries and candidate callbacks stay inside 10–19 IST.

## Call flow

1. At the slot time the dispatcher posts to the worker `/dial/assessment` (shared secret `CALL_INTERVIEW_SECRET`).
   The worker prepares the job brief and **synthesises the introduction while the phone rings**, then dials.
2. Intro: who is calling (PluginLive on behalf of the company), "this call is recorded and evaluated by AI", the JD brief,
   "Is this a good time … yes or no?". Yes → interview; No → asks for a callback time → `RESCHEDULE`.
3. Interview: each question from student-node; the answer is submitted to `session/turn`; `complete` at the end.
   A dropped call finalises the session like a web drop-off (scored on what was answered).
4. Recording: both sides, mono MP3 32 kbps, uploaded to admin-node `POST /ai-interview/call-slots/:id/recording`
   → private OCI bucket `ai-interview-call-recordings/<map>/<slot>/…`; the slot's `recordings` jsonb lists them and the
   panel plays them through 1-hour signed links.

## Turn-taking rules (product-set, 2026-09-25/28)

- Only speech **after** the bot's question has finished playing counts as the answer — the bot counts as speaking from
  the moment speech is queued (a pickup "hello?" was being taken as the consent answer). Half-duplex: speech over the
  bot is ignored (the line echoes the bot's own voice back).
- **Before an answer:** 6 s of silence → *"Take your time. Please go ahead whenever you are ready."* → 6 s more → next question.
- **After an answer:** 3 s of silence ends it (4.5 s if it trails off on and/so/but/aur/toh or has no full stop).
- **Jev decides each turn** (TypeSafe System One, hosted classifier, ~0.3 s, `call_interview/jev.py`; key
  `TYPESAFE_API_KEY` in the worker `.env`). Once an interview answer settles, Jev reads it with the question:
  **complete** → next question straight away · **incomplete** (stopped mid-thought, trailing off, "umm let me think")
  → *"Are you done with your answer, or would you like to add more?"* · **repeat** ("can you repeat the question",
  "sawal dobara bolna") → *"Sure. <question>"*, nothing said so far counts as the answer.
  Replies to "are you done?": done → next question; not yet / wait → *"Sure, please go ahead."*; more content →
  appended and re-judged; repeat → question re-read; 6 s silence → the answer stands.
- **Consent** (yes/no) is Jev too: yes / no / repeat (re-asks the question) / unclear; only a reply naming another
  time still goes to the LLM intent call (`/ai-interview/call-intent`) to read the callback time.
- **Without Jev** (no key, >1.5 s, error) the call falls back: every answer gets "are you done?", replies go through
  phrase rules (`turn_taking._reply`), consent through the LLM intent call.
- **Cost:** ~480 input tokens per decision at $0.042/M → ≈ $0.0002 (₹0.02) per interview, ≈ ₹18 per 1,000 interviews.
  Open-source alternatives were benchmarked on 21 real replies (2026-09-28): Laya 12–13/21 at 1.3–2.4 s,
  Llama 3.2 1B 7/21, mDeBERTa too slow on the 4-core boxes; Jev 21/21.
- No filler between questions. Latency from last word to next question ≈ pause + ~2 s question generation + ~0.7 s TTS
  (student-node no longer waits on per-turn scoring before generating the next question).

## Data

- `assessment.ai_interview_call_slots` — one row per assignment (unique `assessment_assigned_id`), `scheduled_at` is a
  true instant (map `start_time`/`end_time` are IST digits stored as UTC), `recordings jsonb`.
- DB-Scripts folder **"AI Interview Call Delivery"**: `20260923T065054Z__ai_interview_call_slots.sql` (table + cron row, disabled),
  `20260923T065849Z__aas_assessment_set_id_index.sql`, `20260923T095522Z__ai_interview_call_slot_recordings.sql`.
  DEV + UAT applied; PROD pending. Enable with `update assessment.cron_config set is_enabled=true where job_name='ai_interview_call_dispatch'`.

## Deploy / config

- admin-node env: `CALL_INTERVIEW_URL=https://<env host>/call-interview`, `CALL_INTERVIEW_SECRET` (same value as the worker).
- Worker `~/call-interview/.env`: `ENGINE_URL`, `PUBLIC_BASE`, `PORT=8021`, `DIAL_TOKEN`, `DEEPGRAM_API_KEY`,
  `PLIVO_AUTH_ID/PLIVO_AUTH_TOKEN/PLIVO_FROM_NUMBER`, `CALL_INTERVIEW_SECRET`, `STUDENT_API_URL`, `ADMIN_API_URL`.
- The worker is **not in any CI**: `git archive <branch> call_interview | tar -x`, rsync into `~/call-interview`
  (exclude `.env .venv sessions`), `sudo systemctl restart call-interview`. Needs `ffmpeg` on the box. First start takes ~2 min.

## Gotchas

- Plivo `machine_detection: hangup` hung up on real humans ("Machine Detected") — removed.
- A timer that cancels its own task dies silently: the no-answer path awaited `_dispatch`, which cancelled the timer
  → dead air for the rest of the call. Dispatch now runs in its own task.
- A student-node restart mid-call used to end the call; transport errors now retry for ~30 s.
- Test calls dial real numbers: cancel leftover `SCHEDULED` test slots.
