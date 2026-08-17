# Mix & Match candidate journey (v2)

## DEV entry point

Universal Mix & Match OTP invites resolve to:

`https://assessment.dev.pluginlive.com/candidate-assessment-journey/v2?inviteToken=<signed-ticket>`

After OTP verification, the browser stores a candidate-scoped `assessment:run` JWT in session storage. The JWT identifies the owner assignment; it is not replaced with a second token.

## Candidate APIs

`student-node` exposes private Mix & Match routes. Every part-level route verifies that the requested assignment has the same Mix Match group and candidate email as the owner assignment in the scoped JWT.

- `GET /students/mix-match/summary`
- `GET /students/mix-match/assessment/:assessmentAssignedId/questions`
- `POST /students/mix-match/assessment/:assessmentAssignedId/submit`
- `POST /students/mix-match/assessment/:assessmentAssignedId/upload-audio`
- `POST /students/mix-match/assessment/:assessmentAssignedId/upload-video`
- `POST /students/mix-match/ai-interview/:assessmentAssignedId/start`
- `POST /students/mix-match/ai-interview/turn`
- `POST /students/mix-match/ai-interview/complete`

The existing single-assessment APIs are unchanged. `assessment-react-v2` calls the routes through same-origin `/api/assessment/*` BFF handlers.

## Implemented assessment runners

As of 2026-08-17, the v2 combined runner serves live questions for every assessment type. No backend change was needed for the last four: the Mix & Match part routes delegate to the same generic question and submit handlers the single-assessment flow uses, which already branch per type.

- Communication: live assigned questions/sections, signed listening audio, audio/video recording uploads, v1-compatible final response payload, and real submission.
- AI Interview: real session start, generated question turns, browser speech transcript submission, server completion, and camera/microphone checks.
- Aptitude: `questionsBySection`, an object keyed by lower-cased section name, one MCQ subsection each.
- Behaviour: `behaviors[]`, one subsection per behaviour.
- Custom: `sections[]`, with question and option artwork rendered from the signed `question_image_url` / `option_image_url` the API resolves.
- Role Based: `sections[]` mapped onto the surface each needs — MCQ Question to single-select, Subjective Question to free text, Video Response to the recording surface, Coding Question to the code editor. Taken section by section, as in v1.

### Submit payload per type

Each type is scored from a different shape, so the runner builds a different payload per part. These live in `assessment-react-v2/src/lib/examShapes.ts`, which imports only types so the transforms are unit-tested without a browser.

| Type | `response` shape | Answer identified by |
| --- | --- | --- |
| Aptitude, Behaviour | `{ [questionId]: answer }` | option **text** |
| Custom | `{ [questionId]: answer }` | option **id** |
| Role Based | `{ mcqQuestions, subjectiveQuestions, codingQuestions, videoResponses }` | option **id**; video by `objectKey` |
| Communication | one array per section (`paragraphReading`, …) | per-section |

Getting the option-id-versus-option-text distinction wrong scores a candidate zero without failing anything, so both directions are pinned by tests in `examShapes.test.ts`.

Coding answers submit `{ code, language, test_results: [] }`. The empty results are deliberate — the server re-runs the test cases itself and only trusts frontend results when they are supplied. The in-browser runner executes JavaScript only, so runnable languages are offered first and the rest are labelled "(no run)".

Role Based video clips are uploaded while recording; that upload already attaches the storage key to the attempt server-side, and the submit payload repeats it as a safety net exactly as v1 does.

Unanswered questions are omitted rather than sent blank: the server rejects an empty answer, and a missing row scores the same as an explicitly skipped one.

### Refresh and resume

The take-page loader is single-flight because fetching questions claims a single-shot assessment (`PENDING` to `INPROGRESS`). This prevents React remounts from issuing a second start request.

That claim happens for **every part in the group** the moment the combined test opens, so `INPROGRESS` is the normal state of a part the candidate has not reached yet. The start guard used to read that as "already running on another device", so one browser refresh answered `409 ALREADY_IN_PROGRESS` for every part at once and ended the sitting with no way back in.

`resolveAssessmentStartConflict` now takes an `isMixMatch` flag and treats an `INPROGRESS` Mix & Match part as a same-candidate resume. The flag is set only by `getMixMatchAssessmentQuestions`, after `assertMember` has verified the scoped invite JWT owns that assignment — a caller who merely knows an assignment id cannot set it. `COMPLETED` and `DROPOUT` are still refused, so a submitted or abandoned part cannot be reopened.

On the client, a restored attempt is re-seated against the test that actually loaded (`reconcileAttempt`). Questions are fetched again on every mount and a part can come back with different ones (Aptitude regenerates its set when the candidate's level has moved), so a persisted cursor could name a question that no longer exists — which rendered nothing at all and stranded the candidate on the loading skeleton. Answers are keyed by question id, so a refresh costs the candidate their place, not their work.

A combined final submission is blocked until AI Interview is complete. Every other part is submitted with one request each. The overall timer uses the same backend submission path as manual finish.

## DEV deployments

- `student-node` commits `e60c67b2`, `9f7dfca5`
- `assessment-react-v2` commits `4602376`, `c70bee7`, `d1822b4`, `b7c78b4`
