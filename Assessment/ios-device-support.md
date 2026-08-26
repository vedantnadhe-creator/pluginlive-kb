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

When the candidate leaves the assessment (switches Safari tabs or apps) on iPhone, iOS **suspends all media capture at the OS level** — the camera stream dies and any in-progress video-response `MediaRecorder` is cut.

### Proctoring frame freeze fix — all assessment types (June 2026, UAT)

Root cause of "frozen" / byte-identical proctoring snapshots (one image repeated for a whole session — observed in PROD, 115 identical frames): the proctor capture `<video>` was created with `document.createElement` and **never inserted into the DOM**. WebKit/Safari (and backgrounded tabs on every engine) stop advancing frames for an offscreen/detached `<video>`, so `drawImage` silently re-copied the last painted frame. The platform-wide sweep showed this is **not Safari-only** (Chrome/Blink also froze, ~6%), so the fix is engine-agnostic. Shipped across **all** runtimes:

- **Hidden but *rendered* capture element.** `Assessment-React/src/utils/proctorVideo.js` `mountHiddenProctorVideo()` appends the capture `<video>` to the DOM at `2px` / `opacity:0.01` (NOT `display:none`, NOT detached; `playsinline`) so the browser keeps decoding frames. Self-cleans any prior element via the `data-pl-proctor` marker. Used by Aptitude, Custom, Communication, Hinglish, Role-based; AI-interview uses the same util on its proctor `<video>`.
- **Recover on track loss.** `watchProctorTrack` listens for `ended` / `mute` on the camera track (iOS releases the camera on background) and drops the refs so the next capture tick re-acquires a fresh stream.

### Single shared stream so proctoring keeps capturing during recording

Two cameras at once **fails on mobile** (the codebase notes "avoids opening a second stream which fails on mobile devices"), so proctoring + recording must share **one** `video+audio` `getUserMedia` stream. The first attempt at this broke recording on UAT ("camera permission" / `NotReadableError` / lost takes): the `[stream, isFullPageMode]` cleanup effect ran `stream.getTracks().forEach(stop)` + proctor teardown on **every** `setStream`/fullscreen change, killing the shared camera mid/after recording.

**Fix (Communication, Hinglish, Role-based — UAT June 2026):**
- Video-response recording records the **same** live proctoring stream (`captureRef.current.srcObject`, opened `video+audio`); proctoring is **not** stopped on record-start and **not** restarted on record-stop — so snapshots keep uploading **throughout** the video answer.
- **Communication & Hinglish only:** the camera-teardown was moved **out** of the `[stream, isFullPageMode]` effect into an **unmount-only (`[]`) effect**; the per-change effect now only clears timers / restores layout. This is what stops the shared stream being killed mid-assessment. (Role-based's proctor-teardown effect was already `[]`-keyed, so no change needed there.)
- **Communication & Hinglish only:** reading-section voice records a **clone** of the shared mic track (`new MediaStream([track.clone()])`) — no second mic; stopping the clone never touches proctoring. (Role-based has no reading-audio section.)
- **OTP / email-invite studentId (all three):** `uploadProctorImage` falls back to `sessionStorage 'assessment_invite_assigned_id'` → `assessmentAssignedId` (mirrors AIInterview) — previously bailed with "No student ID found" in the invite flow, uploading nothing.

**Status:** shipped to **UAT** for **Communication, Hinglish, and Role-based** — proctoring captures continuously through the video answer on all three. Validated end-to-end on Communication (incl. iOS); Hinglish/Role-based use the identical pattern. AI-interview records audio-only (separate mic) and proctoring runs continuously already. The DOM-mounted hidden `<video>` freeze fix (above) is in **all** types. PROD promotion pending.

### iPhone tab/app-switch re-entry

- **Camera re-acquire (green light).** After backgrounding the shared stream is dead, and iOS **rejects a gesture-less `getUserMedia` re-acquire**, so re-acquire happens **inside the "Resume Assessment" tap** of the re-entry modal (`resumeProctoringAfterReentry()` in Communication/Hinglish; inlined in Role-based `handleReturnLite`) — a real user gesture iOS honours, run synchronously in the tap (no `setTimeout`). The `visibilitychange` gesture-less re-acquire is left best-effort.
- **Video-response recording interruption.** A take cut by backgrounding can't be resumed (bytes are gone). `visibilitychange:hidden` flags `interruptedRecordingRef` while a recording is live; on return the orphaned recorder is stopped and its `onstop` **discards the partial take** — no upload, no attempt burned — resetting to ready-to-record. Refs: `recordingRef`/`activeRecorderRef`/`interruptedRecordingRef` (Communication, Hinglish), `videoRecordingRef`/`activeVideoRecorderRef`/`interruptedVideoRef` (Role-based, keyed per questionId).
- **Incoming calls no longer auto-submit mobile assessments (2026-08-26, `Assessment-React` `448f87f`).** Mobile operating systems expose an incoming call, notification takeover, and deliberate app switch as the same `visibilitychange:hidden`; there is no browser API that reveals the cause. Previously that event entered the three-warning tab-switch counter, and Android/iPad could also emit a companion fullscreen exit, allowing one call to consume two warnings and eventually auto-submit. `utils/deviceTier.js` now classifies mobile OS interruptions (`markMobileInterruption`) and suppresses their companion fullscreen exit (`isMobileInterruptionFullscreenExit`, including hidden/unfocused and a 3-second event-order grace). All five proctored runners — Aptitude, Custom, Communication, Hinglish, and Role-based — bypass the punitive warning/auto-submit counter for mobile backgrounding. Where report-only proctoring is wired, the hidden event is retained as a low-confidence signal (`severity: low`, `confidence: 0.25`); desktop tab-switch/fullscreen enforcement is unchanged. An interrupted live recording is still flagged/discarded before the bypass, preserving the no-corrupt-upload behavior above. Regression coverage: `src/utils/__tests__/deviceTier.test.js` plus `mobileInterruptionAssessmentRunners.test.js`. **Ported to the v2 candidate app** (`assessment-react-v2` `078241a`, then corrected by `17bfa86`; DEV + UAT 2026-08-26) — the two apps share no code, so this had to be fixed twice. **v2 diverges from v1 here on purpose:** v2 exempts only the `visibilitychange`, and counts a fullscreen exit as a violation on every device, because a phone reports a deliberate app switch as a fullscreen exit and nothing else — exempting both (as v1 still does) lets a candidate switch away for free. v2 keeps `isMobileDevice()` in `src/lib/deviceTier.ts`, guards only `watchVisibility` in `src/app/assessment/take/page.tsx`, and covers it in `src/lib/deviceInterruption.test.ts`. **v1 has not had this correction** — worth applying if a single-assessment invite (which still lands on v1) is ever reported the same way. See [candidate-frontend-v2.md](candidate-frontend-v2.md).

Re-entry behaviour scoped to iPhone (`!shouldEnforceFullscreen()`); desktop/iPad untouched. The shared-stream camera model applies on **all** platforms.

---

## Activate-link login redirect (student-react)

The "view assessment" email link lands on `student-react` `Onboarding/Components/ActivateAccount/index.js`. Routing keys off `studentDetails.currentState` (returned as a real number by the **public** `GET /students/:studentId` — no auth, no response schema, so not string-coerced): `currentState >= 1` (onboarded) → **redirect to login**; only `0 / -1` (brand-new) → **set-password** page.

A 6 s safety net redirects to **login** if the `getStudentData` fetch never resolves (seen on iPhone — iOS Mail's in-app browser / ITP can drop the request); it never defaults to set-password, so a returning user is not wrongly sent to set-password.

**Gotcha (fixed):** that safety-net `useEffect` was originally keyed on `[]`, so its `setTimeout` closed over the **first-render** `stateKnown === false` permanently. After the fetch resolved for a brand-new user, the stale timer still fired ~6 s later and **bounced new students to login** instead of letting them set a password. Fix: key the effect on `[stateKnown]` (early-return + cleanup once data loads) so the timer only fires when the fetch genuinely never resolves. `getStudentData` also swallows fetch errors silently, so a real failure looks identical to a slow load — both fall to the safety net.

---

## Reaching the bottom action buttons (iPhone scroll)

On iPhone the assessment runs in **full-page mode** (`isFullPageMode`) with a `height:100vh` overlay. Safari's bottom toolbar can't be hidden for web apps, so the Next / Submit / Record footer sits *behind* it. The fix is two-part:

- **App.js scroll-unlock CSS** (gated on `body.assessment-mobile`, added only on iPhone via `deviceTier`): for the assessment shell/scroll containers it flips `height:100vh` / `position:fixed` → `height:auto; overflow:visible; position:relative` and adds `padding-bottom: calc(104px + env(safe-area-inset-bottom))` so the footer scrolls into reach and clears the toolbar + home indicator. Class hooks `exam-shell` / `exam-scroll` / `exam-actions` are on every runtime's shell/scroll/footer.
- **Body scroll must stay unlocked.** The scroll-unlock CSS only works if the page itself can scroll. **Communication and Hinglish** (only these two) lock it in `hideLayoutElements()` with `document.body.style.overflow='hidden'` + same on `documentElement` — an inline style that trapped the Next button on iPhone with no way to scroll to it. Fix: gate that lock on `shouldEnforceFullscreen()` so it runs only on desktop/iPad; iPhone (LITE) keeps body scroll. Aptitude / Behaviour / Custom / Role-based never locked body scroll, so they were unaffected.

## Known follow-ups (not yet shipped)

- **AI-interview final scoring (all platforms):** `fastapi-ai-engine/routers/ai_interview.py` `score-final` calls a non-existent model id (`gemini-3.5-flash`) with no fallback → 502. Should be `GEMINI_MODEL` (`gemini-2.5-pro`).
- **Code-runner sandbox:** role-based coding runs server-side on the `code-runner` container (port 9090, native subprocess, 10s timeout) — weak isolation (no per-run container / network egress block).
