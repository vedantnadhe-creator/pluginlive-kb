# Attempt integrity: shadow classifier and planned retakes

> **HOLD — PROD promotion still requires separate approval.**
> Kushal explicitly approved the **existing shadow implementation for UAT on 2026-10-30**.
> That approval covers the classifier, speech check and decision-log table only; it does
> not turn on automatic resets, progression exclusion, notifications or new UI.
> **Do not promote this feature or its DB migration to PROD / release / hotfix branches
> without separate approval.** Future live-action phases also need their own UAT approval.
>
> **How to recognise its commits:**
> - Subject starts with **`[attempt-integrity]`**
> - Trailer line: **`Hold: attempt-integrity (DEV only; do not promote to UAT/PROD without Kushal's go-ahead)`**
> - Branch: **`feat/attempt-integrity`** (in every repo it touches)
>
> Find them before any UAT promotion:
> ```bash
> git log origin/Development --oneline --grep='\[attempt-integrity\]'
> git log origin/Development --format='%h %s' --grep='Hold: attempt-integrity'
> ```
> The original DEV-only trailers are historical: the UAT approval above overrides them
> for the released shadow commits. UAT equivalents: student-node `ddad55b7`, `2c6f8632`,
> `22e0ff54`; fastapi `cec5b30`, `3339e59`. Continue checking markers before promotion.
> DB-Scripts live in `Attempt Integrity/`; UAT is applied and PROD remains pending/on hold.
>
> Runtime safety net: everything is behind `INTEGRITY_CHECK_MODE` (student-node),
> default **`off`** = behaviour identical to before the feature.

PRD (final, with the PROD simulation): https://bmv2bqg5gpcd.compat.objectstorage.ap-mumbai-1.oraclecloud.com/pl-uat-public-docs/prds/PRD-scheduled-attempt-error-reset.html

## What it does

After an institute **scheduled** or **diagnosis** Communication / Aptitude attempt is scored,
and before progression runs, a classifier decides whether the attempt was spoiled by **our
system**, by the **student's side**, or is plain **performance**.

**Current implementation is shadow only:** it writes a decision and evidence. It does not
reset/reassign attempts, change status or scores, exclude results from progression, or send
notifications. Even `live` currently behaves as shadow. The actions below are the planned
live behavior, not actions performed by the deployed code.

| Outcome | When | Planned live effect (not implemented) |
|---|---|---|
| `CLEAN` | No trigger | Progression as today |
| `PERFORMANCE` | Score-drop trigger only, no technical evidence | Progression as today |
| `SYSTEM_RETAKE` | Our error (scoring failure, speech-to-text failed on real audio) | Retake on a new set, not counted |
| `STUDENT_RETAKE` | Student-side error, retakes used < 3 | Retake on a new set, counted |
| `PAST_LIMIT_ACCEPT` | Student-side error, retakes used ≥ 3 | Accepted as the result (COMPLETED, progression runs; on a diagnosis it initialises the level) + email to the team |

## Decisions (Kushal, 2026-10-28)

- Retry limit: **3 student-side retakes per student, lifetime**. Our errors are never counted.
- No human in the loop; the team is only notified (email to every active row in
  `assessment.quota_alert_recipients` + `#platform-activity`, the support-ticket path). No admin list/panel.
- Student side is student side: **no cohort-incident rule** (a campus-wide network failure still counts).
- Past the limit, the attempt is **accepted** (scheduled and diagnosis alike), not discarded.
- A blank answer at a genuine time-out (stored as not attempted) with no technical error is
  **performance**, not an error.
- **Loudness check required** for Paragraph Reading and Video Response: decides "our STT failed on
  real speech" (ours) vs "no speech captured" (student).
- Diagnosis: no score-drop trigger (no level/baseline yet).
- Retake window 7 days from issue, via a policy function so it can become dynamic.
- Student never sees a retry count.

## Triggers

| Trigger | Condition |
|---|---|
| Scoring failure | `calculation_error = true` after retries |
| Recording never landed | a Video Response answer with `error` "Video not uploaded within timeout period" |
| Silent recording | Video Response with empty transcript ("Transcription too short" / "No meaningful speech detected"), or Paragraph Reading scored 0 with no recognised words |
| Drop-off | scheduled attempt flipped to `DROPOUT` |
| Score drop | scheduled only: attempt log NPS < 75% of the student's average log NPS over prior COMPLETED, non-errored same-type attempts |

**Per-attempt NPS** (not the stored pair NPS in `progression_history`): Communication
`communicationNPS(set CEFR level, final score)`, Aptitude `difficultyAnchoredScore(set difficulty, % marks)`,
curved with `curveNPS`; the average is `curvedMean` of the linear values (`npsScale.js`).

**Gotcha — match sections by name.** Since 2026-01-11 Communication attempts store
`communication_scores` under the **Hinglish**-owned `section_id`s (all of them since May 2026). Any
rule keyed on Communication section ids is blind to recent attempts; join `assessment.sections` and
use `section_name`.

## Build status

| Phase | Scope | Status |
|---|---|---|
| 1 | Decision log table, pure classifier, evidence + per-attempt NPS, shadow-mode hook before progression and on terminal scoring failure | Built and promoted to DEV and UAT; table applied in both environments. UAT student-node `22e0ff54`, DB-Scripts `7bd92dc` |
| 2 | Loudness / speech check (Reading + Video) | Built and promoted to DEV and UAT; UAT fastapi `3339e59`. Recorder telemetry (stop reason + client duration) not started |
| 3 | Live mode: `ERRORED` status, COMPLETED-after-check, retake service, gate changes, limit, notifications | not started |
| 4 | UI: student retry card, institute-v2 chips/drawer/KPI | not started |

### DEV deployment (2026-10-30)

- student-node `f4cc682b` and fastapi `2cdc113` are on `origin/Development` and **LIVE on DEV**, with
  `INTEGRITY_CHECK_MODE=shadow` in `~/api/student-node/.env` **and** `.env.dev` (CI copies `.env` → `.env.dev`,
  `auto_deploy.sh` copies `.env.dev` → `.env`; the flag must be in both).
- Shadow = every scored in-scope attempt gets a row in `assessment.attempt_integrity_decisions`; nothing
  else changes (no ERRORED status, no retake, scores/progression untouched).
- student-node CI failed on the divergent shared checkout (`git pull` without a reconcile strategy);
  deployed by merging `origin/Development` into `~/api/student-node` then `./auto_deploy.sh student-node`.
- PROD is still on hold; the existing shadow implementation was approved for UAT on 2026-10-30.

### UAT promotion (2026-10-30)

- Only the three student-node feature commits and two fastapi feature commits were cherry-picked
  onto the existing UAT branches. No Development-wide merge was used.
- student-node UAT `22e0ff54`; fastapi UAT `3339e59`. UAT student-node `.env.uat` and `.env`
  both specify `INTEGRITY_CHECK_MODE=shadow`; `CALCULATION_ASYNC=true` is required.
- Applied `Attempt Integrity/20261028T080732Z__attempt_integrity_decisions.sql` to
  `uat_pluginlive` using a transaction and bounded lock/statement timeouts. The migration is
  additive and has no Prisma changes. DB-Scripts status commit: `7bd92dc`; PROD pending/on hold.
- Fastapi deployed through `CENTRAL_LLM_RELEASE=1 ~/auto_deploy.sh fast-api UAT`, retaining
  the running dependencies, env, mounts and ports. The host helper now also copies
  `Proctoring/models/` assets and compiles only Python files; otherwise it would omit Silero's
  bundled `.jit` model. The source checkout may lag; verify image files/release artifacts.
- Deployment logs and private rollback configuration are under
  `~/releases/attempt-integrity-uat-20261030/` on UAT; fastapi's immutable release artifacts
  are under `~/releases/fastapi-ai-engine/UAT-3339e59816e7-20261030T082333Z/`.
- student-node deployed with `~/auto_deploy.sh student-node UAT`; the calculation and
  progression queue workers started successfully with `CALCULATION_ASYNC=true`.
- Before promotion: classifier/NPS unit checks **40 passed**. On UAT, the speech model
  loaded and classified synthetic silence as `digital_silence`; an unauthenticated endpoint
  call returned **401**. The new student-node client reached `fast-api.uat.pluginlive.com`
  with its service token (**200**) and the endpoint refused an external recording URL.
- A completed scheduled Aptitude attempt was checked through the deployed model: one
  **shadow / CLEAN** decision was stored, while its status, set, scores and progression
  remained identical before/after. Runtime hashes matched the promoted source for four
  student-node files and six fastapi files, including the bundled model and license.
- Broad Jev regression was not run as part of the deployment smoke checks.

Check on DEV or UAT:
```sql
SELECT created_at, assessment_type, is_diagnosis, stage, outcome, rule, triggers,
       counts_as_chance, attempt_nps, avg_nps, evidence->'silentRecordings' AS silent
  FROM assessment.attempt_integrity_decisions ORDER BY created_at DESC LIMIT 20;
```
Logs: `docker logs student 2>&1 | grep '\[INTEGRITY\]'`; AI container is `fastapi` on DEV
and `fastapiai` on UAT (`docker logs <container> 2>&1 | grep speech-presence`).

### Code map (student-node)

- `app/helpers/attemptIntegrity.js` — pure rules: mode flag, scope, per-attempt NPS, triggers, cause, outcome. Spec: `test/attemptIntegrity.spec.js`.
- `app/models/AttemptIntegrity.js` — evidence (sections by name), prior NPS history (last 20 valid same-type attempts), chronological retake count (only attempts taken before this one, same mode), idempotent upsert into `assessment.attempt_integrity_decisions`.
- `app/queues/calculationWorker.js` — `runIntegrityCheck` after a successful score (before the progression job) and on a terminal scoring failure; errors are logged, never thrown. Stage is `drop_off` for a DROPOUT row.
- Async calc path only (`CALCULATION_ASYNC=true`); the legacy inline cron is not hooked.
- `live` currently behaves as `shadow` (no ERRORED/retake/notify yet).

### Speech-presence check (silent recordings)

A Video Response / Paragraph Reading answer whose transcript came back empty is checked
before the classifier decides. student-node signs the recording URL
(`generatePreSignedURLVideo` / `generatePreSignedURLAudio`) and calls fastapi
`POST /attempt-integrity/speech-presence` (`routers/attempt_integrity.py`, signal checks in
`Proctoring/speech_presence.py`).

1. **Signal checks** (ffmpeg + numpy): `no_audio_track`, `digital_silence` (peak ≤ −60 dBFS or
   ≥ 95% zero samples), `too_short` (< 3 s). These decide alone: student side.
2. **Second transcription** for everything else, with the existing Scribe integration
   (`routers.ai_interview._scribe_batch`, `scribe_v2`, audio-only 48 kbps MP3): if it hears a
   **scoreable answer** (Video Response ≥ 30 words = the scorer's own `MIN_TRANSCRIPT_WORDS`;
   Paragraph Reading ≥ 20) the verdict is `speech` → our primary STT lost a real answer → **our error**.
   Otherwise `no_speech` → student side. Only the word count leaves fastapi, never the transcript.
3. Silero VAD v5.1.2 speech seconds are kept as evidence only (see calibration: it is not a reliable judge).
4. If the check cannot run (Scribe down, download error) → `checkError` → rule S2b, our error
   (benefit of the doubt).

Auth: any valid platform JWT with `user.role == "system"` (student-node's `RestClient` always sends
the shared `SYSTEMJWT`). Only HTTPS `*.oraclecloud.com` URLs are fetched; 300 MB / 10 recordings per call.

| Verdict | Rule | Side |
|---|---|---|
| `speech` (Scribe heard a scoreable answer) | S2 | ours, free retake |
| check failed | S2b | ours, free retake |
| file not in storage | U1 | student |
| `no_audio_track` / `digital_silence` / `too_short` / `no_speech` | U2 (named per verdict) | student |

#### PROD calibration (2026-10-28, read-only)

400 recent Communication recordings (2026-06-16 → 2026-10-28): 150 empty-transcript videos,
150 empty-transcript readings, 100 normal answers as controls. Read straight from Object Storage with
the jump host's `oci` CLI (no pod, no PROD service touched), analysed on the DEV box in a
`--network none --cpus 2` throwaway container, audio deleted afterwards; aggregates only.

| | Result |
|---|---|
| Controls (normal answers) | 100 / 100 detected as speech by VAD |
| VAD "speech" on silent videos (47) | Scribe heard ≥ 30 words in 26 (55%); 0 words in 14 (also 0 with auto language: mumbling / noise); 1–29 words in 7 |
| VAD "no speech" on silent videos (20 sampled) | 1 had a full answer (quiet mic, VAD 0.26 s → Scribe 128 words) |
| **Silent videos → our error (final rule)** | **27 of 150 confirmed (+~3 estimated in the 61 not transcribed) ≈ 20%** |
| Silent videos → student side | ~80%: 16 digital silence, 6 too short, 40 no answer, rest no speech |
| **Silent readings → our error** | **8 of 150 confirmed (≈ 5–7%)**; 55 too short (median clip 6 s), 19 digital silence |

So about **1 in 5 empty-transcript videos is a real answer our STT pipeline (Deepgram nova-3, then nova-2
on loudness-normalised audio) lost**. Recommended at-source fix (not built, changes the scoring path):
try Scribe in `video_calculation.py` before scoring a < 30-word transcript as 0, so these students are
scored instead of needing a retake.

AI Interview v2 auth (checked 2026-10-28, **not affected**): student-node's `score-answers` / `summarize`
calls get `SYSTEMJWT`, and those routes only need a valid token. The strict `verify_service_token`
(`_id == "system"`) guards `generate-slots` / `complete-choices`, which only admin-node's set-generation
queue calls, with its own minted token via plain axios. A new student-node caller of a strict route
would get 403.

**Open gap — "cut short" attribution.** A clip under 3 s is either the student stopping early or the
recorder/upload losing data. The v2 app knows (`RecordingAnswer.tsx`: stop by user / max time / section
timer / track ended / interrupted, and its own `durationSec`) but sends `timeTaken: 0` and no stop reason.
Fix: report stop reason + client duration per recording; client duration ≫ file duration = data lost (ours).
Readings make this urgent: 55 of 150 silent readings are under 3 s.

### Config

| Var (student-node) | Values | Default |
|---|---|---|
| `INTEGRITY_CHECK_MODE` | `off` / `shadow` (classify + log only) / `live` | `off` |
| `INTEGRITY_SCORE_DROP_RATIO` | Ratio in (0, 1); trigger is strictly below this fraction of the baseline | `0.75` |
