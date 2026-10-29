---
type: reference
created: "2026-10-29"
last_verified: "2026-10-29"
tags: [assessment, candidate-frontend-v2, submission, proctoring, uploads, scoring]
---

# Final submission pipeline — the contract every assessment type follows

How a candidate's sitting is handed in by the v2 candidate app (`assessment-react-v2`) and stored by
`student-node`, and the rules a **new assessment type must follow** to plug into it. The goal: a
submit takes seconds, not minutes; nothing the candidate does on the "Submitting…" screen counts as a
violation; and no answer or recording is lost or written twice.

Incident that prompted it (2026-10-29): the final submit held candidates for **up to 10 minutes**
(`SUBMIT_UPLOAD_WAIT_MS`) waiting for recordings to upload, and during that wait the
fullscreen/tab/focus watchers were still live — pressing **Esc** (which exits full screen) or closing
the tab on "Submitting…" was recorded as a proctoring violation and spent a warning.

## 1. The work is done during the sitting, not at submit

| What | When it is persisted | Status kept where |
|---|---|---|
| Typed / selected answers | As given: `saveAnswer` → `POST /students/mix-match/assessment/:id/save-response` (MCQ on the click, typed answers debounced 800 ms) | `src/lib/answerSaves.ts` — per answer `saving / saved / failed`; a failed save **retries with backoff** (2/5/10/20/30 s) while the candidate carries on; a newer answer to the same question replaces a pending retry |
| Audio / video takes | The blob goes into a durable IndexedDB queue the moment recording stops (`uploadQueue.ts`), and uploads **in the background, 3 at a time** (`UPLOAD_CONCURRENCY`), each with its own backoff, so a stuck take never holds the others. Two takes of one question go up oldest-first, never together | IndexedDB record (`attempts`, `nextAttemptAt`, `registered`); landed object keys in `localStorage` `pl.v2.uploads.landed` (survives reload); server-side the `student_answers` row: **`object_key IS NULL` = upload in flight, set = stored** |
| Recording upload path | Signed URL, no proxy: `recording-upload/init` (creates/re-opens the answer row with `object_key = NULL`, returns a signed Oracle PUT URL) → browser `PUT`s the bytes to Object Storage → `recording-upload/complete` (verifies the object, sets `object_key`, wakes/re-scores the calculation). Exceptions on the multipart path through student-node: AI Interview **session audio** (needs server-side transcoding/chapters) and temporary AI answer evidence (no `student_answers` row) | — |

## 2. What the final submit does (`finish()` in `src/app/assessment/take/page.tsx`)

1. **Freeze, synchronously.** `submittingRef = true` and reducer `BEGIN_SUBMIT` (`attempt.submitting`).
   While frozen the reducer ignores every edit/navigation/clock/violation action (only
   `COMPLETE_PART` / `MARK_PART_SUBMITTED` bookkeeping passes), the exam `<main>` is `inert`, and
   `answerCurrent`, `finishCurrentModule`, `expireCurrentAssessment` and `expireCommunicationTimer`
   all return early. Answer-save retries pause.
2. **Proctoring stops.** `spendWarning` and the fullscreen / visibility / blur handlers return early,
   so Esc, closing or switching the tab while submitting is neither recorded nor counted.
   `useProctoring(partId, active = !paperFrozen)` stops event recording, camera snapshots, gaze
   tracking and environment watchers (the camera stream itself stays until the page unmounts, so
   the AI Interview's final cut is not cut short). The fullscreen and reload-notice guards are
   hidden. The browser's own "Leave site?" prompt stays, because closing mid-submit would lose it.
3. Waits for Communication time-out saves; ends the AI Interview if one is open (its own completion).
4. **Registers recordings — does not wait for them.** `registerPendingRecordings(partIds)` calls
   `recording-upload/init` for every queued take of this sitting that student-node has not heard
   of yet (one small request each, bounded 15 s). That guarantees every take has its
   `object_key = NULL` row before the part is submitted. Registration and upload never overlap for
   one take (a late `init` after `complete` would reopen the row with no key).
5. **Submits the parts in parallel**, dispatching `MARK_PART_SUBMITTED` as each succeeds. A retry
   after one part fails only re-sends the parts not yet in — important, because student-node
   treats a second submit of a submitted-but-unscored part as a *resubmission* and deletes that
   part's `student_answers` rows first.
6. `FINAL_SUBMIT` → completion screen. On failure: `SUBMIT_FAILED` unfreezes, proctoring and
   answer-save retries resume, the dialog offers retry.

The **completion screen** keeps the upload queue running, shows *"Your recordings are still
uploading (N left). Please keep this window open"*, raises a "Leave site?" prompt while any are
pending, and holds the student-dashboard redirect until they have landed (`usePendingUploads`).

## 3. Why skipping the upload wait is safe (server side)

- **Scoring barrier** — `queues/calculationWorker.js processCalc` defers a part while any
  `Paragraph Reading` / `Video Response` answer row has `object_key IS NULL` (covers Communication
  and Role Based video). The scorers (`helpers/videoUploadWait.js`, `RoleBasedCalculations`) also
  wait briefly for an attempted-but-not-landed take; a skipped take (no row) scores 0 at once.
- **Late arrival** — upload completion calls `rescoreLateRecording` (`helpers/lateRecordingRescore.js`):
  if the part was already scored it is reset and re-scored; if not yet scored the queued calc is
  woken (`wakePendingCalculation`).
- **Answers written once** — final submit still carries the whole paper as a safety net, but
  `saveMissingResponses` now writes only answers that differ from the stored row
  (`helpers/submitAnswerDiff.js changedAnswers`) for Aptitude and Role Based (Communication and
  Behaviour already skipped stored ones). Aptitude still marks questions missing from the payload
  `SKIPPED`. Custom Assessment is scored inside the submit request, but it is DB-only and fast.

## 4. Checklist for a new assessment type

- [ ] **Answers**: save each answer as it is given through `answerSaves.track(key, () => saveAnswer(…))`
      — never fire-and-forget. Add the type to `saveResponsePayload` (`src/lib/examShapes.ts`) and
      make sure `saveResponse` in student-node stores it in the same text the submit would
      (`storedAnswerText`), so the submit diff can skip it.
- [ ] **Recordings**: hand blobs to `uploadRecording` / `enqueueRecording` (direct signed-URL path).
      Do **not** POST them yourself and do not wait for them before submit. Use a
      `questionId` that has an `assessment_question_map` row (init checks it).
- [ ] **Scoring barrier**: if the type's recordings live in a section other than `Paragraph Reading` /
      `Video Response`, add that section to the `processCalc` pending-media query, and make the
      scorer read the key from the `student_answers` row (not only from the submit payload).
- [ ] **Late takes**: make sure `calculateAssessmentScore` for the type can be reset and re-run
      (`resetAssessmentForRecalculation`) so `rescoreLateRecording` works.
- [ ] **Submit idempotency**: the part must be submittable once; rely on `submittedParts` and never
      re-send a part already in.
- [ ] **Freeze**: any new reducer action that changes the paper must be in `EDIT_ACTIONS`
      (`src/app/_mock/exam.ts`) so it is frozen while submitting; any new timer/auto-advance handler
      must return early on `submittingRef.current`.
- [ ] **Proctoring**: any new violation source must check `submittingRef.current` before recording
      or calling `spendWarning`; any new watcher inside `useProctoring` must be started/stopped by
      its `active` effect, not the mount effect.
- [ ] Tests: `src/app/_mock/exam.test.ts` (freeze), `src/lib/uploadQueue.test.ts` (scheduling,
      registration), `src/lib/answerSaves.test.ts`, `src/lib/deviceInterruption.test.ts`
      (no violations while submitting), student-node `test/submitAnswerDiff.spec.js`.

## 5. Not covered yet

- **AI Interview v2** still waits (up to `V2_UPLOAD_WAIT_MS`, 10 min) inside its own completion
  (`useAiInterviewV2Session.finish`) for its answer clips and session audio, because its
  finalizer (reading judge, full recording) reads them at completion. Moving it onto the same
  barrier is a separate student-node change.
- AI Interview session audio still uploads through student-node (multipart), so its bytes cross
  the box twice.
- The v1 app (`Assessment-React`) is unchanged.

## Rollout

| Repo | Change | DEV | UAT | PROD |
|---|---|---|---|---|
| assessment-react-v2 | freeze + proctoring stop + no upload wait + parallel queue + answer-save retry | `9c9746f` | `3e67371` (2026-10-29) | pending |
| student-node | submit writes only changed answers | `39f415bb` | `8e66a56d` (2026-10-29) | pending |

Verified 2026-10-29: unit tests (reducer freeze, queue scheduling/registration, answer-save
retry, no-violation-while-submitting, submit diff); DEV AI Interview sitting through the new
submit → `COMPLETED`, `calc:done`, `ai_finalize:done`, `scores_calculated = t`; UAT bundle built on
the UAT box with no DEV hostnames and no page errors. The Jev admin-float specs are stale against
the current admin wizard (combined Degree & Department picker, moved Aptitude section step, Ask Oli
over Continue — `JEV_HIDE_OLI=1`), so the four-type sanity chain could not float on DEV that day.

Deploy student-node before the frontend: the frontend change is safe against the old backend
(it only stops waiting), but the backend diff is what removes the redundant writes.
