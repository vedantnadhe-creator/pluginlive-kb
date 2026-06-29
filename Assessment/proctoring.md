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
- **Admin dashboard**: `admin-react` `StudentReport/ProctoringReportPanel.js` fetches `GET /assessment/:assessmentAssignedId/proctoring-report` (admin-node `proctoringReportHandler`) — integrity band, score, an external-reference (cheating) metrics grid, gaze metrics, and the timeline.
- **Report PDFs**: all four report PDFs (aptitude, communication, role-based, AI interview) carry a brief **proctoring-status banner at the top** (band + score + plain-English headline) plus a detailed **"Integrity & Proctoring"** section. Built once via `Assessment.js _renderIntegrityHtml` / `_buildIntegrityHtmlFor` (inline-styled, injected via a single `{{{integrityHtml}}}` placeholder). Self-gating: nothing renders when no finalized report exists.

## Gotchas
- `pctEyeContact` is stored 0–100 — do **not** re-multiply when rendering (the old admin `fmtPct` showed `10000%`).
- A missing MediaPipe model asset makes the whole gaze layer silently dead while reports still show a clean 100% — surface landmarker-creation failures, never swallow them.
- Thresholds (WPM 170, disfluency ≤1.5%, gaze angles) are tunable policy in `useProctoringCollector.js` (`THRESH`, `GLANCE`, `READ_ALOUD`) and `ProctoringReport.js` (`PENALTY`); calibrate against real attempts to avoid flagging fast natural speakers.
- AI-interview **OTP-invite** scoped-token auth (`AI_INTERVIEW_SCOPED_SECRET`) is a separate concern and is **not configured on UAT** — it only affects OTP-invite AI interviews, not logged-in candidates or the proctoring feature itself.
