# Attempt integrity: classify errored attempts, retake, keep them out of progression

> **🚫 HOLD — DEV ONLY. Do not move to UAT or PROD.**
> This feature is being built on DEV only. **No session or agent may cherry-pick, merge,
> rebase onto, or deploy any of its commits to a `UAT` / `PROD` / release / hotfix branch,
> or apply its DB scripts to UAT/PROD, until Kushal explicitly says so.** When promoting
> other work from `Development`, leave these commits out.
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
> When cherry-picking a range, exclude every SHA these commands list. If a merge would
> carry them in, cherry-pick instead. DB-Scripts for this feature live in the
> `Attempt Integrity/` folder with `UAT — on hold` / `PROD — on hold` in the header.
>
> Runtime safety net: everything is behind `INTEGRITY_CHECK_MODE` (student-node),
> default **`off`** = behaviour identical to before the feature.

PRD (final, with the PROD simulation): https://bmv2bqg5gpcd.compat.objectstorage.ap-mumbai-1.oraclecloud.com/pl-uat-public-docs/prds/PRD-scheduled-attempt-error-reset.html

## What it does

After an institute **scheduled** or **diagnosis** Communication / Aptitude attempt is scored,
and before progression runs, a classifier decides whether the attempt was spoiled by **our
system**, by the **student's side**, or is plain **performance**. Errored attempts are retaken on
a new set and never reach progression.

| Outcome | When | Effect |
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

## Build status (DEV)

| Phase | Scope | Status |
|---|---|---|
| 1 | Decision log table, pure classifier, evidence + per-attempt NPS, shadow-mode hook before progression and on terminal scoring failure | **done on branch** `feat/attempt-integrity` (student-node `9c20b0d8`, worktree `~/api/_wt-attempt-integrity`, not pushed / not merged to Development); table applied on DEV DB; DB-Scripts `1525de1` |
| 2 | Loudness / speech check (Reading + Video) | **done on branch** (student-node `f1dd06be`, fastapi `066351c` in `~/api/_wt-attempt-integrity-fastapi`); not pushed. Recorder telemetry (stop reason + client duration) not started |
| 3 | Live mode: `ERRORED` status, COMPLETED-after-check, retake service, gate changes, limit, notifications | not started |
| 4 | UI: student retry card, institute-v2 chips/drawer/KPI | not started |

### Code map (student-node)

- `app/helpers/attemptIntegrity.js` — pure rules: mode flag, scope, per-attempt NPS, triggers, cause, outcome. Spec: `test/attemptIntegrity.spec.js`.
- `app/models/AttemptIntegrity.js` — evidence (sections by name), prior NPS history (last 20 valid same-type attempts), chronological retake count (only attempts taken before this one, same mode), idempotent upsert into `assessment.attempt_integrity_decisions`.
- `app/queues/calculationWorker.js` — `runIntegrityCheck` after a successful score (before the progression job) and on a terminal scoring failure; errors are logged, never thrown. Stage is `drop_off` for a DROPOUT row.
- Async calc path only (`CALCULATION_ASYNC=true`); the legacy inline cron is not hooked.
- `live` currently behaves as `shadow` (no ERRORED/retake/notify yet).

### Speech-presence check (silent recordings)

A Video Response / Paragraph Reading answer whose transcript came back empty is
checked before the classifier decides. student-node signs the recording URL
(`generatePreSignedURLVideo` / `generatePreSignedURLAudio`) and calls fastapi
`POST /attempt-integrity/speech-presence` (fastapi `routers/attempt_integrity.py`,
analysis in `Proctoring/speech_presence.py`).

- Speech detection: **Silero VAD v5.1.2** (MIT), vendored at `Proctoring/models/silero_vad.jit`,
  runs on the torch already in the image. No new pip dependency (the image's torch is unpinned,
  so rebuilding with new packages is risky).
- Auth: any valid platform JWT with `user.role == "system"`. student-node's `RestClient` always
  overwrites `authorization` with the shared `SYSTEMJWT` (role system, a real `_id`), so a
  per-call minted token never arrives; `verify_service_token` in `ai_interview_v2.py` also requires
  `_id == "system"` and therefore 403s student-node calls (**unverified whether the AI Interview v2
  score-answers / summarize calls from student-node are affected**).
- Only HTTPS `*.oraclecloud.com` URLs are fetched (no SSRF); 300 MB and 10 recordings per call.

| Verdict | Meaning | Rule | Side |
|---|---|---|---|
| `speech` (≥ 2 s of VAD speech) | candidate spoke, our STT missed it | S2 | ours, free |
| check failed | our check could not run | S2b | ours, free (benefit of the doubt) |
| file not in storage | upload never landed | U1 | student |
| `no_audio_track` | file has no decodable audio | U2 | student |
| `digital_silence` (peak ≤ −60 dBFS or ≥ 95% zero samples) | mic muted / blocked / denied | U2 | student |
| `too_short` (< 3 s, no speech) | recording stopped almost at once | U2 | student (**see open gap**) |
| `no_speech` | mic worked, nobody spoke | U2 | student |

DEV check (2026-10-28): full-transcript controls measured 46 s / 69 s and 100 s / 120 s of speech;
of 7 surviving empty-transcript videos, 1 had 8.5 s of speech (our miss), 1 loud audio without
speech, 5 were 0.7–2.5 s clips. In-scope DEV silent recordings had all been removed by retention,
so the surviving ones were corporate attempts.

**Open gap — "cut short" attribution.** A clip under 3 s is either the student stopping early or
the recorder/upload losing data. The v2 app knows (`RecordingAnswer.tsx`: stop by user / max time /
section timer / track ended / interrupted, and its own `durationSec`) but sends `timeTaken: 0` and
no stop reason, so the server cannot tell. Fix: report stop reason + client duration per recording;
client duration ≫ file duration means data was lost (ours).

### Config

| Var (student-node) | Values | Default |
|---|---|---|
| `INTEGRITY_CHECK_MODE` | `off` / `shadow` (classify + log only) / `live` | `off` |
