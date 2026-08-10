# Report-Only Proctoring

Behavioural / integrity proctoring that runs **silently during an assessment** and produces an **after-the-fact integrity report** for human review. It never interrupts, warns, or auto-submits the candidate — that existing in-exam flow (tab-switch / fullscreen warnings → auto-submit at `MAX_TAB_SWITCH_WARNINGS`) is unchanged. Proctoring here only *collects signals* and *computes a report*.

**Live on:** DEV + UAT. PROD pending.
**Enabled for assessment types:** Aptitude, AI Interview, Communication, Role_Based (the `PROCTORED_TYPES` set in `student-node/app/models/ProctoringReport.js`). Other types are short-circuited.

## What it detects

Two cheat classes, because gaze alone only catches one:

| Cheat | Looks like | Caught by |
|---|---|---|
| **Second device** (phone beside laptop) | Eyes/head leave the screen plane (down/side) | Gaze + head-pitch tracking |
| **Same device** (another tab: ChatGPT/Google) | Eyes stay on screen | Interaction telemetry (tab-hidden) — gaze is blind to this |
| **Reading an answer aloud** (speaking/video) | Fast, even, disfluency-free speech | Deepgram WPM + filler analysis, confirmed by an LLM verification layer (see below) before it's flagged |

## Architecture

### Client collector — `assessment-react/src/utils/useProctoringCollector.js`
MediaPipe **FaceLandmarker** (loaded from CDN at runtime; `baseOptions.modelAssetPath` is **mandatory** — without it the landmarker throws and the collector silently no-ops) runs **on-device** on the existing hidden proctor `<video>`. No video leaves the browser for gaze — only derived, time-bounded **events** are batch-POSTed every 30s to `students/assessments/proctoring/events`.
- **Gaze + head pose**: horizontal/vertical iris ratio + **head pitch** (the dominant "looking down at a phone" signal) + yaw. Calibrated from the first 3s of detected-face time (a per-candidate baseline; "weak" if too few samples).
- **Event types**: `eye_contact_lost`, `gaze_off_side`, `gaze_below_screen`, `head_turned`, `no_face`, `multi_face`, `spoof_suspected`, `calibration`, plus interaction/fusion types below.
- **Per-question read-from-device fusion** (`setActiveQuestion` / `recordAnswer`): counts read-glance cycles + off-screen dwell ratio + answer-right-after-glance, and emits `external_reference_suspected` only when **≥2 independent signals agree** (low false positives). "Off-plane" (a glance away from the screen) is direction-agnostic — down, up, or either side all count, since a second device/notes can sit anywhere around the webcam, not just below it.
- **Tier-1 interaction signals** (tee'd from the page's existing handlers, not duplicated): `tab_hidden` (the same-device cheat), `fullscreen_exit`, `second_display` (`window.screen.isExtended`).
- **Adaptive snapshot burst**: on a high-signal suspicion the page densifies server CV snapshots (e.g. 20s→5s / 13s→4s) to try to catch the device on camera.

### Server CV — `fastapi-ai-engine`
The periodic snapshot cron runs server-side CV (YOLO phone / multi-face / no-face) and emits `source:'server'` events. The admin timeline previously rendered a **"CV"** (then "Computer Vision") badge for these; that badge was removed entirely — the `source` field is still stored on events but no longer surfaced in the UI (only the timeline label + severity tag are shown). For the AI Interview, `routers/ai_interview.py` `stt-stream` surfaces Deepgram per-word timings (`speech` summary) so the client computes accurate WPM from real spoken duration.

### Read-aloud (speaking / video responses)
- **AI Interview** (live WS): client computes WPM + disfluency + time-to-first-word per turn → `reading_pace_suspected` (fast + clean) and `delayed_fluent_answer` (long pause then a fast polished answer = read-while-thinking).
- **Communication / Role_Based** (batch STT): FastAPI already returns WPM (`speech_rate_analysis.words_per_minute`) / word + filler counts; `ProctoringReportService.emitReadingPaceFromWpm()` is called per question from `CommunicationCalculations.js` + `RoleBasedCalculations.js` and emits a server-source `reading_pace_suspected` when WPM is high and disfluency unnaturally low. `Role_Based`'s `rolespecific.py` originally only had a placeholder `estimated_wpm` (word_count / fixed 240s) that was never even returned, so this never fired for Role_Based — fixed to compute real WPM from Deepgram word timings (`words[-1].end - words[0].start`), same approach as Communication's `video_calculation.py`.

### LLM verification layer (second layer, before a "reading" flag is trusted)
The WPM/gaze heuristic alone false-positives on fast, articulate speakers who glance away to think — it's a *suspicion*, not a verdict. Every `reading_pace_suspected` / `delayed_fluent_answer` hit is passed through a second-layer LLM check before it counts toward the integrity score, appears in the timeline, or is shown as flagged next to a specific answer:
- **`POST /proctoring/verify-reading`** (`fastapi-ai-engine routers/proctoring.py`) takes the question, the transcribed answer, and the delivery telemetry (WPM, disfluency rate, spoken duration, silence-before-first-word) and judges `"read" | "human" | "uncertain"` via Gemini (through the LiteLLM gateway, reusing `_gemini_json_background` from `ai_interview.py`). Defaults to NOT flagging when ambiguous — a wrong "read" verdict is the worse mistake.
- **`ProctoringReportService.verifyReadingConfirmation()`** (student-node `ProctoringReport.js`) calls that endpoint and writes the verdict onto the flagging event's `meta.confirmedReading` (+ `meta.llmVerdict`). Called from: `CommunicationCalculations.js` / `RoleBasedCalculations.js` right after `emitReadingPaceFromWpm` creates an event (awaited, so it lands before the post-scoring re-finalize); and `aiInterviewHandler.submitTurn` fire-and-forget when the client's `interview.js` sends `deliverySignals` (only populated when its own heuristic suspected the turn — the client also force-`flush()`s the collector first so the event is already ingested before the server looks it up, since the collector otherwise batches every 30s).
- **`_buildReport()`** in `ProctoringReport.js` filters `reading_pace_suspected` / `delayed_fluent_answer` events down to `meta.confirmedReading === true` before they contribute to `summary` counts, the integrity-score penalty loop, or the timeline — an unconfirmed (or LLM-rejected) suspicion is dropped entirely, never scored, never shown. `summary.readingFlaggedQuestionIds` lists the `questionId`/`interactionId` of every confirmed answer.
- **Per-answer badge**: `Assessment.js` fetches `ProctoringReportService.getConfirmedReadingQuestionIds()` (a **live** query against `proctoring_events`, not the frozen `proctoring_reports` snapshot — so it's correct even if this question's verification finishes after finalize) and stamps `readingFlagged: true/false` onto each transcript/answer entry before rendering the AI Interview / Communication / Role_Based PDF templates, which render a small "Reading detected" badge next to that specific answer when true.
- **Scope note**: `external_reference_suspected` (the gaze-only glance+answer-timing fusion, which also fires for Aptitude MCQs with no answer text) is deliberately **not** gated by this LLM layer — gating it would silently zero out Aptitude's proctoring (it has no text to verify). It still scores and still appears in the timeline as "Suspected reading from another device."

### Aggregation + report — `student-node/app/models/ProctoringReport.js`
`finalizeProctoringReport(assessmentAssignedId)` aggregates all events + snapshots into a `proctoring_reports` row: summary metrics, a denormalised timeline, an **integrity band** (`clean` ≥85 / `review` ≥60 / `high_concern`) and an **integrity score** (0–100, per-type capped penalties). Finalize is triggered on submit (`submitAssessment`), after scoring (`calculateAssessmentScore` re-finalizes communication/role_based so server read-aloud events land), and on interview completion (`completeSession`, fire-and-forget). Idempotent.

## Database (`assessment` schema)
- `proctoring_logs`, `proctoring_snapshots` — session + per-frame CV (pre-existing).
- `proctoring_events` — every behavioural/interaction event. Unique dedup index `(assessment_assigned_id, source, type, start_ms)` makes ingest idempotent.
- `proctoring_reports` — one finalized report per `assessment_assigned_id`.
- Identity is the assignment's `primary_email` — there is **no hard student_id FK** on these tables.
- Migration: `DB-Scripts/Aptitude Proctoring Report/001_proctoring_events_report.sql`. Applied DEV + UAT. PROD pending.

## Where it surfaces
- **Candidate guidance**: the "How to take this assessment honestly" panel (eye-contact / stay-in-frame / don't read from notes-or-phone / camera-on rules) is shown on the **assessment instruction page**, not the verification (BiometricCheck) screen. It's a reusable `Assessment-React/src/components/ProctoringGuidelines.js`, imported into each proctored type's `instruction.js` (aptitude, communication, role-based, behaviour, hinglish, custom) and rendered only when proctoring is enabled (`assessment?.allowProctoring !== false`). **AI Interview is intentionally excluded** (its instruction screen omits it). The old duplicate `ExpectationsPanel` on `BiometricCheck.js` was removed.
- **Camera guard**: `useCameraGuard.js` detects camera loss for all four proctored types. As of 2026-07-15 there is **no blocking popup and no pause** — the old `CameraRequiredModal.js` (which froze the timer/mic and forced the candidate to click "Resume assessment") was removed. Instead, on camera loss each assessment/interview screen silently retries re-acquiring the proctor stream every 5s in the background (`reacquireCameraSilently`, one instance per screen in `aptitudeassmt/assessment.js`, `Communicationassmt/assessment.js`, `RoleBasedassmt/assessment.js`, `AIInterview/interview.js`) — the candidate's session is never interrupted, and the pre-start camera-on gate is now best-effort (won't block starting the assessment if the camera isn't yet live). The guard still deliberately ignores `document.visibilityState === 'hidden'` while evaluating track state, because browsers suspend/mute the camera track on tab-switch (which is handled separately by the in-exam tab-switch flow, not the camera-guard).
- **Multi-face is server-CV only.** The client (MediaPipe per-frame `faces.length > 1`) is too noisy — sub-50ms double-hits from glasses re-detect, hands near face, re-alignment opened/closed a fresh `multi_face` incident on the client and accumulated 60+ spurious rows per session while the actual snapshot images (server YOLO) showed a single person. Client now tracks only `no_face` (candidate left the frame). The snapshot cron's YOLO on a real frame is the only source of `multi_face` events.
- **Admin dashboard**: `admin-react` `StudentReport/ProctoringReportPanel.js` fetches `GET /assessment/:assessmentAssignedId/proctoring-report` (admin-node `proctoringReportHandler`) — integrity band, score, an external-reference (cheating) metrics grid, gaze metrics, and the timeline.
- **Snapshot gallery** (the "Proctoring Data → Snapshots" grid in `StudentReport/index.js`, both `admin-react` and `institute-react`): fed by `GET /assessment/getProctoringDetails` (admin-node `getProctoringDetails`), which returns **`sessions[]` newest-first** plus an `overallSummary` aggregated across all of them. The screen reads **every** session — `StudentReport/proctoringView.js` (`collectSnapshots` / `primarySession` / `collectIpAddresses`) flattens snapshots oldest-capture-first, takes face-detection stats from `overallSummary`, and shows session details from the session with the most snapshots. It used to read `sessions[0]` only, which showed **exactly one image** on any attempt that ended with a straggler session (see Gotchas).
- **Report PDFs**: all four report PDFs (aptitude, communication, role-based, AI interview) carry a brief **2–3 line proctoring summary at the top** of the report (band + score + plain-English headline, noting the detailed report is at the bottom) and the full **"Integrity & Proctoring" detail section at the end**. `Assessment.js _buildIntegrityHtmlFor` returns `{ summary, detail }` (via `_renderIntegritySummaryHtml` / `_renderIntegrityDetailHtml`), injected through two placeholders `{{{integritySummaryHtml}}}` (top) and `{{{integrityDetailHtml}}}` (bottom). Self-gating: nothing renders when no finalized report exists, and a `no_data` band (band/score null) is used instead of fabricating a clean/100 when no events/log/snapshots were captured. The banner headline must **not** point at the detail section itself — `_renderIntegritySummaryHtml` already appends "Full event timeline is at the end of this report" gated on `hasEvents`; the headline used to hardcode the same sentence, so a report whose detail section rendered empty still promised a breakdown that wasn't there.
- **What goes in the end-of-report event table** (`_shapeIntegrityForPdf` → `events` / `hasEvents`): every **discrete band-driving incident at any severity** (`external_reference_suspected`, `tab_hidden`, `fullscreen_exit`, `second_display`, `phone_detected`, `multi_face` — the `INCIDENT_TIMELINE_TYPES` set, matching `hardCheatSignal` in `ProctoringReport.js`), plus **continuous gaze noise only at `high`** (`eye_contact_lost` / `gaze_*` are already summarised as the eye-contact percentage in the banner, so listing every medium glance would bury the real incidents). `behavioralOnly` (aptitude) still narrows this to `BEHAVIORAL_TIMELINE_TYPES` on top. The table was previously filtered on `severity === "high"` alone, which **suppressed the whole section on every Role_Based report** in practice: role-based's dominant signal `external_reference_suspected` is emitted as `medium` unless 3+ independent signals agree (`useProctoringCollector.js` `finalizeQuestion`), and its gaze/`no_face` events land low–medium, so only `tab_hidden` ever qualified. Communication / AI Interview routinely produce high-severity gaze and `no_face` events and so rendered the table normally — which is why this read as "role-based is missing the proctoring table". On UAT at the time of the fix: 6 of 12 role-based reports had a high-severity event, and the two most recent attempts produced a "Needs Review 84/100" banner with a zero-byte detail section.
- **`external_reference_suspected` is named in the headline.** It sets `integrityBand = review` via `hardCheatSignal` but was absent from the `concerns` list, so a role-based PDF could read "Proctoring: Needs Review — 84/100. No integrity concerns flagged." while the one signal that drove the verdict appeared nowhere in the document. It is now listed as "N suspected reading(s) from another device" (skipped under `behavioralOnly`, since device-fusion isn't meaningful for aptitude). It is still deliberately kept **out** of the "Suspected reading detected" metric — that metric stays LLM-confirmed-only (next bullet).
- **Reading detected** (both PDF banner and admin panel metric) = `summary.readingFlaggedQuestionIds.length` — i.e. only LLM-confirmed `reading_pace_suspected` / `delayed_fluent_answer` hits (see LLM verification layer above). It previously summed in raw `externalReferenceSuspectedCount` too, which could show e.g. "reading detected on 5 answer(s)" in the PDF headline while zero answers were actually badged in the transcript (the gaze-only fusion signal fires with zero reading-pace evidence) — fixed so the headline number, the admin metric, and the per-answer badges always agree.
- **Status consistency**: the admin badge reads the same `integrityBand` the PDF headline uses, so a "high concern" PDF can't show as "Good" in the UI. Download is gated on report availability (`checkReportAvailability` / `getProctoringDetails`), with an AI-Interview fallback to "a finalized score exists" because `scores_calculated` lags for interviews.

## Gotchas
- **An attempt can hold more than one `proctoring_logs` row.** Sessions are created lazily by the first snapshot (`student-node Assessment.js storeProctoringSnapshot`) and closed by `endProctoringSession` on submit. The webcam capture taken as the candidate submits is still in flight when submit lands, so it used to arrive after `session_end` was stamped, match no open session, and open a **new session holding that single snapshot**. On PROD this hit **89 of 828 attempts in the last 30 days** and, combined with the old `sessions[0]` read, made the proctoring section show one image instead of the real 60–250. Session lookup now goes through `app/helpers/proctoringSession.js` `buildOpenSessionWhere` — still-open **or** closed within a **30s grace window**, newest first. The window is deliberately well under the ~90s a genuine re-attempt takes, so a real second session still gets its own row. Historic attempts keep their stray sessions; the frontend reading across all sessions is what makes them render correctly (no data backfill).
- `student-node Assessment.js detectFaces` still resolves the session with a bare `proctoringLog.findFirst` (no `orderBy`) and computes `is_valid` from that one session — on a multi-session attempt the row it picks is arbitrary. Not a regression and not yet fixed; it only feeds the Good/Bad proctoring flag, not the snapshot gallery.
- `pctEyeContact` is stored 0–100 — do **not** re-multiply when rendering (the old admin `fmtPct` showed `10000%`).
- A missing MediaPipe model asset makes the whole gaze layer silently dead while reports still show a clean 100% — surface landmarker-creation failures, never swallow them.
- Thresholds (WPM 170, disfluency ≤1.5%, gaze angles) are tunable policy in `useProctoringCollector.js` (`THRESH`, `GLANCE`, `READ_ALOUD`) and `ProctoringReport.js` (`PENALTY`); calibrate against real attempts to avoid flagging fast natural speakers.
- A real UAT test attempt with zero "reading detected" isn't necessarily broken — the WPM heuristic requires ≥170 WPM / ≥25 words / ≤1.5% filler rate, which normal conversational answers (~85–110 WPM) never reach. Check `proctoring_events` for `reading_pace_suspected`/`delayed_fluent_answer` rows before assuming the LLM layer is misconfigured; if those rows don't exist, the heuristic itself never fired and there was nothing to verify.
- AI-interview **OTP-invite** scoped-token auth (`AI_INTERVIEW_SCOPED_SECRET`) is a separate concern and is **not configured on UAT** — it only affects OTP-invite AI interviews, not logged-in candidates or the proctoring feature itself.

## Device verification gate (face + audio, before the assessment starts)

Separate from report-only proctoring: this is the blocking check on
`Assessment-React/src/components/BiometricCheck.js`. The candidate records ~5s of
webcam video, and the client fires **two unauthenticated FastAPI calls in
parallel**, letting them through only if **both** pass:

| Check | Endpoint | Payload | Pass condition |
|---|---|---|---|
| Face | `POST /proctoring/verify-frame` | `{ student_id, frame_number, image_data, min_confidence }` — bare base64 JPEG, frame grabbed at 2.5s via `canvas.toDataURL('image/jpeg', 0.8)` | `success && face_detected` |
| Audio | `POST /proctoring/detect-audio` | `{ student_id, audio_data }` — bare base64 Opus/webm | `success && audio_detected` |

The clip is then uploaded fire-and-forget to `students/assessments/uploadVerificationVideo`,
which stores it at `verification/<studentId>.webm` in the assessment bucket.

**Both endpoints return HTTP 200 with `success:false` on internal errors** — status
code alone is not a health signal; read the body.

FastAPI hosts: DEV `fast-api.dev`, UAT `fast-api.uat`, **PROD `api-fast.pluginlive.com`**
(note the reversed name on PROD — `fast-api.prod.pluginlive.com` does not exist).

### Capacity characteristics

Face is the bottleneck and it does **not** scale within a pod. `/verify-frame` runs
RetinaFace on `priority_executor` (`utils/executors.py`, `PRIORITY_WORKERS=16` on
PROD), a bounded thread pool. Measured on PROD 2026-08-10 with the load-test
dashboard: **1 student ≈ 3.7s; 10 simultaneous students ≈ 15s median, 25s p95**.
Audio (`/detect-audio`, FFT-based VAD) is cheap at ~0.3s throughout.

Under that burst each pod drew only **0.5–1.4 cores of the 4 on its node**, and the
nodes sat at 6–12% CPU — the ceiling is inside the pod (GIL / single uvicorn
worker), not the cluster. **Worker count must stay 1**: each worker holds its own
~2.9GB RetinaFace model against a 5Gi container limit, so a second worker OOMs.

### Cold-start and readiness (changed 2026-08-10)

The model used to be materialised lazily on a pod's **first request** — ~2GB
resident and several seconds of graph build. With no readiness probe on the
`fast-api` deployment, a freshly scheduled pod joined the Service immediately and
served that cost to a real candidate: **12.7s for the first `/verify-frame` vs
3.6s once warm**. HPA scale-ups therefore *raised* p95 instead of lowering it
(a 10-student PROD burst measured 15.6s p95 on 3 warm pods, 25.2s p95 once 3 cold
pods joined).

Now:
- `warm_up_face_model()` (`Proctoring/ImageProctoring/face_detection.py`) builds the
  graph and runs one throwaway inference at startup, off the event loop.
- **`GET /health`** — liveness, always 200 once bound. Deliberately *not* gated on
  the model, so a slow warm-up cannot get the container restart-looped.
- **`GET /health/ready`** — returns **503** (`{"ready":false,"faceModel":"pending"}`)
  until the model is resident, then 200. A *failed* warm-up reports ready on
  purpose: the lazy path still works, and holding the pod out of the Service
  would turn a latency problem into an outage.
- Warm-up takes **~18s after the HTTP port binds** (~33s from container start).

`uvicorn.run(..., reload=True)` was hardcoded on, **including in production** — the
dev-only file-watching reloader. Now defaults off; opt in with `UVICORN_RELOAD=true`.

### PROD scheduling constraint

`fast-api` requests `cpu: 1000m` per replica. That figure is deliberate and
documented in `pl-oks-cluster/api-ns/fast-api.yaml`: at 250m the scheduler priced a
pod at a quarter of its real cost and packed four onto one 4-core node. Measured
draw (0.5-1.4 cores) confirms 1000m is honest pricing, **so do not lower it to make
more replicas fit.**

The 5-node `VM.Standard.A1.Flex` pool is at 74-87% *requested* CPU (while only
6-12% *used*), which fits exactly **6** `fast-api` replicas. HPA `maxReplicas` was
`8` - unreachable, so two pods sat in `Pending` (`0/5 nodes are available:
5 Insufficient cpu`) indefinitely.

That also **deadlocked the 2026-08-10 rolling update**: with `maxSurge: 50%` the
controller created 6 unschedulable new pods and then refused to retire any old one,
because scale-down requires `available > desired - maxUnavailable` and 6 was not
greater than `8 - 2`. The rollout sat at "6 out of 8 new replicas have been
updated" until unstuck. Both settings were corrected:

- HPA `maxReplicas: 8` -> **6** (honest; raising it again needs cluster capacity).
- Deployment strategy `maxSurge: 50%/maxUnavailable: 25%` -> **`maxSurge: 0`/
  `maxUnavailable: 1`**, so a replacement pod is scheduled into the CPU freed by
  retiring the pod it replaces, instead of waiting for headroom that never comes.

Note also that HPA cannot help an exam-start burst at all: scale-up takes ~110s to
schedule plus ~25s warm-up, against a burst that lasts seconds. **Pre-scale ahead of
scheduled assessments**; `minReplicas: 3` is the real capacity during one.

**`kubectl apply -f fast-api.yaml` used to be dangerous** - the file's `image:` was
pinned at a 2025 tag while `deploy.sh` sets the real one via `kubectl set image`.
It has been re-synced (0-line `kubectl diff`), but it drifts again on every deploy;
check the image line before applying.

### Load testing it

`https://dev.pluginlive.com/load-test` → **Verification (Face + Audio)** tab
simulates 1–200 students against DEV/UAT/PROD. Fixtures are real production
recordings pulled from `oci://pl-prod-assessment/verification/` and split into a
JPEG frame + Opus clip with ffmpeg. See
`load-test-dashboard/VERIFICATION-LOAD-TEST.md` on the DEV box.
