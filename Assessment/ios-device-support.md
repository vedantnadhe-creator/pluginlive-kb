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

---

## Video replay & playback

- Recorded-answer replay `<video>` elements (Communication, Hinglish, Role-based) and BiometricCheck now set **`playsInline`** (+ `webkit-playsinline`); without it iOS refuses inline playback, so candidates "couldn't replay" their recorded video. Live previews already had it.
- Listening audio uses `preload="metadata"`; iOS shows `0:00` until the first user tap (no preload) — expected, not a bug.

---

## Known follow-ups (not yet shipped)

- **AI-interview final scoring (all platforms):** `fastapi-ai-engine/routers/ai_interview.py` `score-final` calls a non-existent model id (`gemini-3.5-flash`) with no fallback → 502. Should be `GEMINI_MODEL` (`gemini-2.5-pro`).
- **Code-runner sandbox:** role-based coding runs server-side on the `code-runner` container (port 9090, native subprocess, 10s timeout) — weak isolation (no per-run container / network egress block).
- **DEV bucket audio gap:** most DEV Communication sets reference `google_audio_*.mp3` objects missing from `pl_dev_poc`; verify per set with `~/scripts/check_set_audio.js`.
