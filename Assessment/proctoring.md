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
| **Reading an answer aloud** (speaking/video) | Fast, even, disfluency-free speech | Deepgram WPM + filler analysis |

## Architecture

### Client collector — `assessment-react/src/utils/useProctoringCollector.js`
MediaPipe **FaceLandmarker** (loaded from CDN at runtime; `baseOptions.modelAssetPath` is **mandatory** — without it the landmarker throws and the collector silently no-ops) runs **on-device** on the existing hidden proctor `<video>`. No video leaves the browser for gaze — only derived, time-bounded **events** are batch-POSTed every 30s to `students/assessments/proctoring/events`.
- **Gaze + head pose**: horizontal/vertical iris ratio + **head pitch** (the dominant "looking down at a phone" signal) + yaw. Calibrated from the first 3s of detected-face time (a per-candidate baseline; "weak" if too few samples).
- **Event types**: `eye_contact_lost`, `gaze_off_side`, `gaze_below_screen`, `head_turned`, `no_face`, `multi_face`, `spoof_suspected`, `calibration`, plus interaction/fusion types below.
- **Per-question read-from-device fusion** (`setActiveQuestion` / `recordAnswer`): counts read-glance cycles + off-screen dwell ratio + answer-right-after-glance, and emits `external_reference_suspected` only when **≥2 independent signals agree** (low false positives).
- **Tier-1 interaction signals** (tee'd from the page's existing handlers, not duplicated): `tab_hidden` (the same-device cheat), `fullscreen_exit`, `second_display` (`window.screen.isExtended`).
- **Adaptive snapshot burst**: on a high-signal suspicion the page densifies server CV snapshots (e.g. 20s→5s / 13s→4s) to try to catch the device on camera.

### Server CV — `fastapi-ai-engine`
The periodic snapshot cron runs server-side CV (YOLO phone / multi-face / no-face) and emits `source:'server'` events (shown with a **CV** tag). For the AI Interview, `routers/ai_interview.py` `stt-stream` surfaces Deepgram per-word timings (`speech` summary) so the client computes accurate WPM from real spoken duration.

### Read-aloud (speaking / video responses)
- **AI Interview** (live WS): client computes WPM + disfluency + time-to-first-word per turn → `reading_pace_suspected` (fast + clean) and `delayed_fluent_answer` (long pause then a fast polished answer = read-while-thinking).
- **Communication / Role_Based** (batch STT): FastAPI already returns WPM (`speech_rate_analysis.words_per_minute`) / word + filler counts; `ProctoringReportService.emitReadingPaceFromWpm()` is called per question from `CommunicationCalculations.js` + `RoleBasedCalculations.js` and emits a server-source `reading_pace_suspected` when WPM is high and disfluency unnaturally low.

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
- **Camera guard**: `useCameraGuard.js` + `CameraRequiredModal.js` gate the start of all four proctored types — the assessment won't begin unless the camera is on, and if the camera is stopped mid-assessment it pauses and blocks until the camera is turned back on. The guard deliberately ignores `document.visibilityState === 'hidden'` while evaluating track state, because browsers suspend/mute the camera track on tab-switch (which is handled separately by the in-exam tab-switch flow, not the camera-guard).
- **Multi-face is server-CV only.** The client (MediaPipe per-frame `faces.length > 1`) is too noisy — sub-50ms double-hits from glasses re-detect, hands near face, re-alignment opened/closed a fresh `multi_face` incident on the client and accumulated 60+ spurious rows per session while the actual snapshot images (server YOLO) showed a single person. Client now tracks only `no_face` (candidate left the frame). The snapshot cron's YOLO on a real frame is the only source of `multi_face` events.
- **Admin dashboard**: `admin-react` `StudentReport/ProctoringReportPanel.js` fetches `GET /assessment/:assessmentAssignedId/proctoring-report` (admin-node `proctoringReportHandler`) — integrity band, score, an external-reference (cheating) metrics grid, gaze metrics, and the timeline.
- **Report PDFs**: all four report PDFs (aptitude, communication, role-based, AI interview) carry a brief **2–3 line proctoring summary at the top** of the report (band + score + plain-English headline, noting the detailed report is at the bottom) and the full **"Integrity & Proctoring" detail section at the end**. `Assessment.js _buildIntegrityHtmlFor` returns `{ summary, detail }` (via `_renderIntegritySummaryHtml` / `_renderIntegrityDetailHtml`), injected through two placeholders `{{{integritySummaryHtml}}}` (top) and `{{{integrityDetailHtml}}}` (bottom). Self-gating: nothing renders when no finalized report exists, and a `no_data` band (band/score null) is used instead of fabricating a clean/100 when no events/log/snapshots were captured.
- **Reading detected** is a single merged metric in both PDF and admin UI — `reading_pace_suspected` + `external_reference_suspected` + `delayed_fluent_answer` counts are summed and shown as one "Reading detected" figure (the separate read-aloud-pace / read-from-device / pause-then-polished labels were merged).
- **Status consistency**: the admin badge reads the same `integrityBand` the PDF headline uses, so a "high concern" PDF can't show as "Good" in the UI. Download is gated on report availability (`checkReportAvailability` / `getProctoringDetails`), with an AI-Interview fallback to "a finalized score exists" because `scores_calculated` lags for interviews.

## Gotchas
- `pctEyeContact` is stored 0–100 — do **not** re-multiply when rendering (the old admin `fmtPct` showed `10000%`).
- A missing MediaPipe model asset makes the whole gaze layer silently dead while reports still show a clean 100% — surface landmarker-creation failures, never swallow them.
- Thresholds (WPM 170, disfluency ≤1.5%, gaze angles) are tunable policy in `useProctoringCollector.js` (`THRESH`, `GLANCE`, `READ_ALOUD`) and `ProctoringReport.js` (`PENALTY`); calibrate against real attempts to avoid flagging fast natural speakers.
- AI-interview **OTP-invite** scoped-token auth (`AI_INTERVIEW_SCOPED_SECRET`) is a separate concern and is **not configured on UAT** — it only affects OTP-invite AI interviews, not logged-in candidates or the proctoring feature itself.
