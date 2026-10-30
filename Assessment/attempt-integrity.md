# Attempt integrity: live retries on UAT

> **HOLD — PROD requires separate approval.** Kushal approved UAT promotion on
> 2026-10-30 and then explicitly requested working live behavior for QA: “Not shadow
> mode, it will be tested by QAs so it should be working.” This releases the classifier,
> speech check, live resets, notifications and student/TPO UI to **UAT only**.
> Never promote this feature or its migrations to PROD/release/hotfix without separate approval.
>
> Feature commits start `[attempt-integrity]`. New trailers are
> `Hold: attempt-integrity (PROD only; separate approval required)`; earlier DEV-only
> trailers are historical and superseded only for the UAT work recorded here.
> Branches: `feat/attempt-integrity`, `feat/attempt-integrity-live` and selective
> `promote/attempt-integrity-live-uat`. Always check the commit markers before promotion:
> ```bash
> git log origin/Development --oneline --grep='\[attempt-integrity\]'
> git log origin/Development --format='%h %s' --grep='Hold: attempt-integrity'
> ```
> DB scripts: `PluginLive-Technologies/DB-Scripts/Attempt Integrity/`.
> Runtime default is still `INTEGRITY_CHECK_MODE=off`; **UAT is configured `live`**.

PRD (decision history; this document describes the implementation): https://bmv2bqg5gpcd.compat.objectstorage.ap-mumbai-1.oraclecloud.com/pl-uat-public-docs/prds/PRD-scheduled-attempt-error-reset.html

## Current behavior

Scope: institute **scheduled and diagnosis Communication/Aptitude**. Practice, corporate,
one-time and other assessment types retain their existing flow.

After submission, an in-scope live attempt remains `INPROGRESS` while scored and checked.
Only an accepted check changes it to `COMPLETED`; progression runs afterward. An error
creates a **new assignment on a different question set**, preserving the original as
`ERRORED` with its answers, scores and evidence. It never updates progression.

| Outcome | Cause | Live action |
|---|---|---|
| `CLEAN` | No problem detected | `COMPLETED`, normal progression |
| `PERFORMANCE` | Low NPS with no technical cause | `COMPLETED`, score stands, normal progression |
| `SYSTEM_RETAKE` | Scoring failure, primary STT lost real speech, or speech check unavailable | Original `ERRORED`, new-set retry, student email, no chance used |
| `STUDENT_RETAKE` | Missing recording, silence/too-short/no-speech recording, drop-off; fewer than three counted retries used | Original `ERRORED`, new-set retry, student email, one chance used |
| `PAST_LIMIT_ACCEPT` | Another student-side error after three counted retries | No reset; `COMPLETED`, result accepted and progression runs, team email |

The limit is **three counted retries per student for life, combined across both assessment
types**. Allocation is serialized per normalized email inside the action transaction, so
simultaneous errors cannot allocate a fourth retry. System-side retries remain free even
past the limit. Shadow decisions never consume the live budget.

The latest accepted policy applies the exhausted-limit rule to **both diagnosis and
scheduled assessments**. A diagnosis at that point can establish the starting level.
No manual review queue/admin panel is implemented. Limit emails reuse every active row in
`assessment.quota_alert_recipients`; there is no new Slack sender. Campus network problems
remain student-side; there is no cohort-based incident override. Students never see a count.

## Triggers and low scores

| Trigger | Condition |
|---|---|
| Scoring failure | Terminal scoring failure (`calculation_error=true`) |
| Missing media | An attempted/initialized required recording never arrived |
| Empty transcript | Video Response: “Transcription too short” / “No meaningful speech detected”; Paragraph Reading: zero with no recognized words |
| Drop-off | The existing dropout flow marks the live attempt `DROPOUT` |
| Score drop | Scheduled only: current per-attempt log NPS is **strictly below 75%** of the prior same-type baseline |

Low score is **a check trigger, never sufficient evidence for a reset**. With no technical
cause the outcome is `PERFORMANCE`, and the score counts. Genuine timed-out blank answers
that the backend marks not attempted are performance. Explicit skipped/not-attempted
recording answers are excluded from missing/silent-recording error evidence.

Per-attempt NPS is calculated from the paper actually served, before progression:
Communication `communicationNPS(set CEFR, final score)`; Aptitude
`difficultyAnchoredScore(set difficulty, percentage marks)`. `curveNPS` curves the current
value; `curvedMean` averages historical **linear** values and curves once. This is different
from the rolling/pair NPS stored in `progression_history`. Baseline: up to 20 earlier scored,
COMPLETED same-type institute attempts, excluding errored outcomes. **Diagnosis has no
score-drop comparison.**

Communication score evidence joins `assessment.sections` by **section name**. Section IDs
may belong to Hinglish even for Communication (recent scoring storage convention).

## Retakes, gates and recovery

- A retry has its own `valid_until`, **real UTC**, seven days after issue. The shared map's
  IST-as-UTC end date is untouched; an expired shared map does not expire the retry. A
  canceled map stays closed. `retakeValidUntil()` is the single policy function for future changes.
- The retry inherits diagnosis/configuration and the original occurrence's `attemptNumber`;
  answers start empty. Question content must differ, not just the set UUID. Existing
  compatible active sets are reused; Aptitude can generate a replacement from its existing
  question bank. If no compatible complete Communication set exists, the check remains
  pending with an explicit error and the recovery sweep retries; it never silently reuses
  the failed paper.
- Retakes do not charge an additional institute assessment credit. The existing contract
  window still applies, and candidate soft locks mirror that rule.
- The live gate blocks a subsequent scheduled assessment of that type while classification,
  progression or an outstanding retry is pending; it does not stop blocking after 30 minutes.
  Errored originals are ignored. **Diagnosis #2 remains startable.** Another available retry
  may also start while a retry is outstanding, avoiding mutual blocking.
- After `PAST_LIMIT_ACCEPT`, no case remains pending: progression runs and the student can
  continue once it finishes. No admin verdict is required.
- Scoring/progression workers never process `ERRORED` originals. Clean results still honor
  the existing proctoring score-release hold. Late queued jobs cannot restore a failed result.
- Actions are transactional, with a unique retry-parent link and a durable decision receipt;
  duplicate checks return the same retry. Submission timestamps distinguish a later resubmission.
- The minute score cron reconciles submitted scored/failed and dropped live attempts and
  enqueues missing progression work. Notifications use an outbox lease, five deliveries per
  sweep, and retain errors for retry. Mail delivery is at least once: a process crash after
  relay acceptance but before receipt persistence can duplicate an email.

## Student and TPO screens

Candidate dashboard: **Assessment-React** at
`https://assessment.uat.pluginlive.com/assessment` (not student-react's unused assessment
route). Scheduled and diagnosis cards display “Retry available”, reason and deadline;
action is “Retry Assessment”. No retry count is exposed. The runner itself is unchanged.

Institute v2: `https://institute.uat.pluginlive.com/v2/assessments`. The assessment student row
shows the issue chip (“Errored · retry available”, “Retry limit reached · result accepted”,
or prior error). The report drawer's **Attempt issues** section preserves the errored entry,
reason and linked retry. Errored results are excluded from overview/roster/report score,
NPS, trend and attempt aggregates. A limit-accepted result counts normally. Institute CEFR
behavior is unchanged. There is no new admin action panel or errored KPI/filter.

## Release state (2026-10-30)

Only feature commits were cherry-picked onto UAT; no Development-wide merge was used.

| Repository | Development source tip | UAT deployed source |
|---|---|---|
| student-node | `8d3a4bba` | `7c6c7541` |
| admin-node (assessment Prisma schema) | `d742dff` | `1fda4a2` |
| institute-node | `aa1be42` | `ba39e30` |
| Assessment-React | `8c84c38` | `f4af526` |
| institute-react-v2 | `97d5564` | `ba6c1c2` |
| fastapi (earlier speech release, unchanged by live phase) | `2cdc113` | `3339e59` |

UAT config in **both** `~/api/student-node/.env.uat` and `.env`:
`INTEGRITY_CHECK_MODE=live`, `INTEGRITY_LIVE_SINCE=2026-10-30T09:32:23Z`,
`CALCULATION_ASYNC=true`. Existing results before that cutoff are not reset retroactively.
The worker normalizes an unclassified post-cutoff submission made during the image build
from the former `COMPLETED` submission state to `INPROGRESS` before scoring.

DEV runtime remains **shadow** (verified 2026-10-30), although the live source/schema
changes were pushed to Development. The shared DEV checkout has unrelated local commits;
this release did not overwrite them. PROD is unchanged and held.

Migrations, applied DEV and UAT, **PROD pending**:

- `20261028T080732Z__attempt_integrity_decisions.sql` — decision log (earlier release).
- `20261030T084703Z__live_attempt_integrity.sql` — `ERRORED` enum;
  `assessment_assigned_students.integrity_retry_of_id` (unique, self-FK), `valid_until`,
  `integrity_checked_at`; decision action/notification receipt columns and pending-mail index.
  DB-Scripts commit `e9dffde`. Student/admin Prisma schemas match; institute API uses raw SQL.

UAT deploys use `~/auto_deploy.sh`. Backend/candidate build logs, private config backups and
rollback tags are recorded under `~/releases/attempt-integrity-live-20261030/`.
Student/institute/candidate old images were tagged `attempt-integrity-live-rollback/<name>:20261030`.
Institute v2 builds in an isolated release through the shared Next helper; see
[UAT topology](../Infrastructure/v2-apps-uat-topology.md). Fastapi retains its earlier
immutable dependency/model release, described in [deploy traps](../Infrastructure/uat-deploy-traps.md).

## Checks and QA

- Classifier/NPS/window/gate checks: **82 passed**. A subsequent contract-lock-only fix
  reran the affected 61 checks successfully.
- `script/checkAttemptIntegrityLive.js` passed against isolated DEV and UAT database
  fixtures, including actual deployed Prisma 4.16 on UAT: original preservation/new paper,
  expired-parent retry deadline, idempotence, combined budget, fourth-error acceptance,
  free system errors past the limit, low-score performance, notification receipts and
  **four simultaneous errors allocating exactly three retries**. Injected mail prevented
  student/team emails; all fixtures were removed.
- Candidate and institute v2 browser smoke: both HTTP 200, no page exceptions, no DEV
  request hosts. Candidate built bundle contains no DEV URLs. This is not the broad Jev suite.
- On the deployed live container, an isolated diagnosis scoring-failure fixture for the
  dedicated UAT QA student was handled by the **actual minute cron**, without a manual
  classifier call: `SYSTEM_RETAKE`, original `ERRORED`, fresh-set child `PENDING`, no original
  progression row, seven-day deadline. The **real UAT mail relay accepted its retry email**
  (`notified_at` persisted). Student HTTP list returned its retry card without a count despite
  an expired parent map; the questions API started it successfully. TPO roster/report HTTP
  APIs returned the error/pending-retry metadata and audit event without an errored score.
  Test maps/papers/assignments/decisions were removed; existing assignments were untouched.
- Runtime hashes matched all 14 checked student/admin/institute source/schema files.
  Workers are running in `live`, with the expected cutoff and mail/portal config.
  Authenticated student-to-fastapi speech-check HTTP call succeeded and refused an external URL.
  Redis instance IDs were checked: these student services use different host-local Redis
  instances on DEV and UAT, so their existing queue labels do not share jobs across hosts.

For QA, use only dedicated UAT test candidates. Submit a normal attempt, an empty/silent
recording, a missed upload, and a dropped attempt; check decision/status and student retry
card plus TPO issue chip. Retake should have a different paper and a personal seven-day
deadline, and its original should have no progression row. Repeat student-side failures
across both types to verify the shared three-retry budget; the fourth is accepted and
alerts the configured team recipients. A low score with no technical error must never reset.
A diagnosis never triggers the score-drop rule and its second paper remains startable.

Debug queries (read only):
```sql
SELECT created_at, assessment_assigned_id, assessment_type, is_diagnosis, mode,
       stage, outcome, rule, triggers, counts_as_chance, retake_assigned_id,
       action_applied_at, notified_at, notification_attempts, last_notification_error,
       attempt_nps, avg_nps
FROM assessment.attempt_integrity_decisions ORDER BY created_at DESC LIMIT 20;
```
Logs: `docker logs student 2>&1 | grep '\[INTEGRITY\]'`.
Fastapi container: `fastapiai` on UAT, `fastapi` on DEV.

Do not simply switch live off while classified work is pending: drain/resolve outstanding
INPROGRESS checks and retry chains before rollback. Keep the additive columns and evidence;
never undo the migration to make old code read the new records.

## Code map

- `app/helpers/attemptIntegrity.js`: pure rules/NPS/trigger/cause; specs in `test/attemptIntegrity.spec.js`.
- `app/helpers/attemptIntegrityPolicy.js`: live cutoff, seven-day policy, public reason text.
- `app/models/AttemptIntegrity.js`: scope, answer/media evidence, prior NPS, shadow decision persistence.
- `app/models/AttemptIntegrityActions.js`: transactional statuses/retries/budget, replacement selection,
  live receipts, recovery queries, recipient/outbox database operations.
- `app/services/AttemptIntegrityService.js`: workflow, Aptitude replacement generation, email relay, recovery.
- `app/models/Assessment.js` / quota/window/diagnosis/progression helpers: submission/list/start boundaries.
- `app/queues/calculationWorker.js`, `script/calculatePendingAssessmentCron.js`, dropout cron:
  score/check/progression ordering and missed-work recovery (`CALCULATION_ASYNC=true` required).
- institute-node `AssessmentDetailV2.js` / `assessmentScoreSql.js`: error visibility and score exclusion.
- Assessment-React `RetryNotice.js`: candidate retry notices; institute-v2 `IntegrityNotice.tsx` and report drawer:
  TPO issue chip/history.

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

| student-node variable | Purpose | Default |
|---|---|---|
| `INTEGRITY_CHECK_MODE` | `off`, `shadow` (log only), `live` (apply actions) | `off` |
| `INTEGRITY_LIVE_SINCE` | Required ISO UTC cutover in live mode; preserve on future deploys | None |
| `INTEGRITY_SCORE_DROP_RATIO` | Trigger strictly below this fraction of the baseline | `0.75` |
| `CALCULATION_ASYNC` | Use the scoring/progression workers | Must be `true` for this feature |
| `EMAIL_ENDPOINT`, `EMAIL_SENDER` | Environment's existing mail relay and sender | Configured on UAT from its admin service |
| `INTEGRITY_MAIL_AUTH_KEY` | Mail relay auth; falls back to existing `AUTH_KEY` | Set separately on UAT; do not alter the student API auth key |
| `INTEGRITY_STUDENT_URL` | HTTPS candidate dashboard URL in retry emails | `https://assessment.uat.pluginlive.com/assessment` on UAT |

There is no retry-count/deadline setting yet: limit is three in the classifier; deadline
is seven days behind `retakeValidUntil()`. Historical decisions keep their mode/evidence.
