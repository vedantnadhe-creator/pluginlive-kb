# iOS / macOS Device Support (Assessment)

> Historically the assessment player **hard-blocked all iOS devices** at the device check. As of the iOS-enablement work (UAT, June 2026) the platform supports **iPhone (Safari), iPad, and macOS Safari** via a capability-tier model, with iPhone running a "lite" proctoring mode because Apple does not allow web fullscreen on iPhone.

This is cross-cutting across all assessment types. Frontend lives in **`Assessment-React`**, backend audio in **`student-node`** + **`fastapi-ai-engine`**.

---

## Device capability tiers

`Assessment-React/src/utils/deviceTier.js` resolves a tier at `ConfigCheck`:

| Tier | Devices | Fullscreen | Proctoring |
|---|---|---|---|
| `FULL` | Desktop Chrome/Edge/Firefox, **macOS Safari** | Enforced | Snapshots + tab/app-switch |
| `STANDARD` | **iPad** Safari (iPadOS 16.4+) | Enforced | Snapshots + tab-switch |
| `LITE` | **iPhone** Safari | **Skipped** (Apple blocks web fullscreen on iPhone) | Snapshots + tab/app-switch (no fullscreen-exit) |
| `BLOCKED` | In-app WKWebviews (Gmail/LinkedIn/WhatsApp) where `getUserMedia` is unavailable | — | Shows "open in Safari/Chrome" |

- `ConfigCheck.js` no longer hard-blocks iOS; it only stops `BLOCKED` (in-app browsers). Real iOS Chrome/Firefox/Edge are whitelisted; standalone PWAs are allowed.
- Each assessment runtime computes `enforceFullscreen = proctoringEnabled && shouldEnforceFullscreen()`. On iPhone (`LITE`) the fullscreen entry modal, fullscreen-exit violations, and re-entry-to-fullscreen are skipped, while **camera snapshots and tab/app-switch detection stay ON**. Desktop/iPad behaviour is unchanged (`enforceFullscreen === proctoringEnabled` there).

---

## Audio recording (speaking / dictation / AI-interview)

iOS Safari's `MediaRecorder` only supports **`audio/mp4` (AAC)** and **throws on `audio/webm`**, which previously made iPhone recordings fail outright.

- `Assessment-React/src/utils/audioFormat.js` negotiates a recordable container (`pickAudioMimeType` → mp4/AAC on iOS, webm elsewhere) instead of hard-coding `audio/webm`. The blob type + **upload filename extension are derived from the real container end-to-end** (no more forced `.webm`).
- `student-node` preserves the real container on upload: `app/helpers/audioUpload.js` + `oracleStorage.js` (`resolveAudioObjectName`/`resolveAudioContentType`) keep the true extension + `Content-Type` from the multipart mimetype (legacy webm unchanged; also fixed a latent `audio/mpeg` mislabel).
- Backend STT is unaffected: most scoring paths convert to WAV via **pydub/ffmpeg** (ffmpeg + AAC decoder confirmed present in `fastapi-ai-engine`); the AI-interview batch `/stt` forwards the real Content-Type to Deepgram, which accepts mp4/AAC natively.

---

## Listening / review audio playback (Communication, Hinglish)

`student-node/app/models/Assessment.js` branches on the Safari user-agent to build listening ("Audio Question") and recorded-answer-review audio URLs. Two Safari-branch helpers were **called but never defined**, so on iPhone Safari the audioUrl came back `null` (greyed-out player / `0:00`):

- **Question delivery:** `CommunicationCalculations.getSafariAudioURL` — now defined as a delegate to `getAudioURL`.
- **Answer review:** `oracleStorage.generateSafariCompatibleAudioURL` / `streamAudioForSafari` — now defined as delegates to `generatePreSignedURLAudio`.

No format change is needed: OCI presigned MP3 URLs honour HTTP Range (`206`) and Safari plays `audio/mpeg` natively. (Note: many DEV question-audio binaries are missing from the bucket — a separate data-sync issue, not a code bug.)

### Slow-network playback resilience (all browsers)

The listening (`AudioPlayer`) and dictation (`WaveformPlayer`) components now handle slow/stalled downloads instead of appearing frozen: `preload="auto"` (clip starts downloading on mount), a **"Loading audio…"** hint + 12 s slow-connection guard (`onWaiting`/`onStalled`), and an inline **"Retry audio"** button on error/play-rejection. Retry calls `<audio>.load()`, which re-fetches **only that one audio object** via its presigned URL (no question/state refetch). Retry never burns the 2-play limit (the play count only increments on playback end). PROD audit confirmed all listening files are present and valid — the "can't hear it" reports are delivery/UX on slow links, not missing files.

---

## AI Interview specifics (iPhone)

- **Streaming STT:** the capture `AudioWorklet` (`AIInterview/pcmWorklet.js`) **resamples mic PCM to 16 kHz** so live Deepgram STT matches the backend's `sample_rate=16000` even when iOS forces a 48 kHz `AudioContext`. Pure pass-through on desktop.
- **TTS voice:** iOS blocks `audio.play()` outside a user gesture, and the interviewer audio is fetched async (`await tts()`). `AIInterview/ttsAudio.js` keeps a **persistent `<audio>` element unlocked during the Start gesture** (`primeTtsAudio`), reused in `speak()`, so the voice plays on iPhone.
- Fullscreen is best-effort and never blocks the interview on iPhone (LITE).

---

## Identity verification (BiometricCheck)

`Assessment-React/src/components/BiometricCheck.js` records a phrase and calls `fastapi-ai-engine` `/proctoring/verify-frame` (face) + `/proctoring/detect-audio` (speech).

- On iPhone, a **combined video+audio `MediaRecorder` records a silent audio track**, so the speech check failed ("not detecting speech") even when the candidate spoke. Fix: record the mic with a **dedicated audio-only `MediaRecorder` on a cloned audio track** (reliable on iOS) and send that to `/proctoring/detect-audio`, falling back to the video blob. The combined video is still used for the verification-video upload.
- The backend decode is fine — `process_audio_upload` (ffmpeg) decodes iOS AAC/mp4 and detects audio; a silent track is the only thing that yields `audio_detected=false`.

### Failure handling — verification is mandatory

Verification is a **hard gate**: a candidate cannot enter the assessment until both the face and speech checks pass.

- On a failed check (`verificationStatus === 'failed'`) the UI shows the error, marks the failing Face/Speech status pill with a red ✗, and renders a single **"Try Again"** button (`RotateCcw` icon) that calls `resetRecording()` — clearing the error/statuses, restoring the live camera stream, and returning to the `idle` "Tap to Record" state. The candidate loops here until they pass.
- Only the `verified` state renders **"Start Assessment"**. There is **no Continue/bypass** on failure (the earlier single-attempt "Continue anyway" path was removed) — so there is no longer any way to start the assessment with a failed verification.
- `STRICT_MODE = true` (in `BiometricCheck.js`) drives the strict "Verification failed. Please ensure your camera and microphone are working and try again." copy.

---

## Video replay & playback

- Recorded-answer replay `<video>` elements (Communication, Hinglish, Role-based) and BiometricCheck now set **`playsInline`** (+ `webkit-playsinline`); without it iOS refuses inline playback, so candidates "couldn't replay" their recorded video. Live previews already had it.
- Listening audio uses `preload="auto"` with a Retry control (see slow-network section above).

---

## Background / foreground recovery (iPhone tab & app switch)

When the candidate leaves the assessment (switches Safari tabs or apps) on iPhone, iOS **suspends all media capture at the OS level** — the proctoring camera stream dies and any in-progress video-response `MediaRecorder` is cut. Two recovery behaviours were added across the three video runtimes (`Communicationassmt`, `Hinglishassmt`, `RoleBasedassmt` `assessment.js`):

- **Proctoring camera re-acquire (green light).** Proctoring keeps **one persistent `getUserMedia` stream** (`captureRef`, reused every 20 s) so the camera light stays on for the whole assessment. After backgrounding, that stream is dead, and the 20 s interval won't re-acquire because `captureRef` is still non-null. The `visibilitychange` handler nulls `captureRef` on return, **but iOS rejects a gesture-less `getUserMedia` re-acquire**, so the camera stayed off. Fix: re-acquire **inside the "Resume Assessment" tap** of the re-entry modal (`resumeProctoringAfterReentry()` in Communication/Hinglish; inlined in Role-based `handleReturnLite`) — a real user gesture iOS honours. It drops the dead stream and calls `captureImage()` **synchronously in the tap** (no `setTimeout`, so `getUserMedia` stays bound to the gesture) → green light returns, snapshots resume. The gesture-less visibility re-acquire is left as best-effort.
- **Video-response recording interruption.** A take cut by backgrounding can't be resumed (bytes are gone). The `visibilitychange:hidden` handler flags `interruptedRecordingRef` while a recording is live; on return the orphaned recorder is stopped and its `onstop` **discards the partial/corrupt take** — no upload, no attempt burned — resetting to the ready-to-record state. The re-entry warning already tells the candidate they left, so after dismissing it they get a live preview and **record again**. Refs added: `recordingRef`/`activeRecorderRef`/`interruptedRecordingRef` (Communication, Hinglish) and `videoRecordingRef`/`activeVideoRecorderRef`/`interruptedVideoRef` (Role-based, keyed per questionId). Normal submit / auto-submit flush paths are unaffected (they run the original save+upload branch).

All scoped to iPhone (`!shouldEnforceFullscreen()`); desktop/iPad untouched.

---

## Activate-link login redirect (student-react)

The "view assessment" email link lands on `student-react` `Onboarding/Components/ActivateAccount/index.js`. Routing keys off `studentDetails.currentState` (returned as a real number by the **public** `GET /students/:studentId` — no auth, no response schema, so not string-coerced): `currentState >= 1` (onboarded) → **redirect to login**; only `0 / -1` (brand-new) → **set-password** page.

A 6 s safety net redirects to **login** if the `getStudentData` fetch never resolves (seen on iPhone — iOS Mail's in-app browser / ITP can drop the request); it never defaults to set-password, so a returning user is not wrongly sent to set-password.

**Gotcha (fixed):** that safety-net `useEffect` was originally keyed on `[]`, so its `setTimeout` closed over the **first-render** `stateKnown === false` permanently. After the fetch resolved for a brand-new user, the stale timer still fired ~6 s later and **bounced new students to login** instead of letting them set a password. Fix: key the effect on `[stateKnown]` (early-return + cleanup once data loads) so the timer only fires when the fetch genuinely never resolves. `getStudentData` also swallows fetch errors silently, so a real failure looks identical to a slow load — both fall to the safety net.

---

## Known follow-ups (not yet shipped)

- **AI-interview final scoring (all platforms):** `fastapi-ai-engine/routers/ai_interview.py` `score-final` calls a non-existent model id (`gemini-3.5-flash`) with no fallback → 502. Should be `GEMINI_MODEL` (`gemini-2.5-pro`).
- **Code-runner sandbox:** role-based coding runs server-side on the `code-runner` container (port 9090, native subprocess, 10s timeout) — weak isolation (no per-run container / network egress block).
- **DEV bucket audio gap:** most DEV Communication sets reference `google_audio_*.mp3` objects missing from `pl_dev_poc`; verify per set with `~/scripts/check_set_audio.js`.
