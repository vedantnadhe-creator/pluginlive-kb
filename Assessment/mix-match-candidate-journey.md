# Mix & Match candidate journey (v2)

## DEV entry point

Universal Mix & Match OTP invites resolve to:

`https://assessment.dev.pluginlive.com/candidate-assessment-journey/v2?inviteToken=<signed-ticket>`

After OTP verification, the browser stores a candidate-scoped `assessment:run` JWT in session storage. The JWT identifies the owner assignment; it is not replaced with a second token.

## The candidate is invited to "an assessment", never to a "Mix & Match" (2026-08-20)

A float that bundles several types is still **one assessment** to the person
sitting it. The parts are how the sitting is built, not a second kind of
assessment the candidate has to learn — so no candidate-facing string names the
internal concept. Both invite channels were saying otherwise and were corrected
on the same day.

`sendMixMatchGroupInvites` (`admin-node/app/queues/assignmentWorker.js`) sends
**one** email per group, after every part is terminal, and picks the channel
from `svc.mixMatchInviteChannel(entityType)`:

| Entity | Channel | Template |
|---|---|---|
| corporate | `otp` | `sendAssessmentInviteEmail` → `mixMatchAssessmentInvite` |
| college | `reminder` | UMS `assessmentRemainder` (the portal reminder every college assignment sends) |

**OTP channel** (`app/helpers/assessmentInviteEmail.js`, commit `d4f5f44`):

    Your combined assessment invite from X   ->  Your assessment invite from X
    You're invited to a combined assessment  ->  You're invited to an assessment
    Start Combined Assessment                ->  Start Assessment

The subject's Mix & Match branch was deleted rather than left identical to the
plain one, so the two cannot silently drift. The **body** still names the parts
(`You have been invited to <title>, containing Communication Assessment, AI
Interview`) — the candidate should know what is coming, they just should not
meet a new noun for it.

**Reminder channel** (`svc.assessmentReminderCopy`, commit `1a128d1`): this path
is easy to miss because it does not use the invite template at all, and it
leaked the internal name twice — the template renders `${assessment_type}
Assessment` as the heading *and* an `Assessment Type:` details row, and
`assessment_type` was the literal string `'Mix & Match'`. It now carries the
part names, humanised from the enum values:

    Mix & Match Assessment                   ->  Communication, AI Interview Assessment
    Assessment Type: Mix & Match             ->  Assessment Type: Communication, AI Interview
    You have been assigned a combined
      assessment containing AI_Interview     ->  You have been assigned an assessment "<title>",
                                                 containing Communication, AI Interview.

A **single-part** float keeps the legacy single-assessment wording. A College
float is single by design, and "complete all parts in one go" describes a bundle
that candidate was never sent — hence `assessmentReminderCopy` branches on
`partTypes.length < 2`, not on whether the job carried a `mixMatchGroupId`.

The copy lives in `AssignmentJobService` rather than inline in the worker so it
is testable without the worker's DB (`test/mixMatchAssignment.spec.js`).

### The float writes its invite channel onto every part's map (2026-08-20)

`mixMatchInviteChannel` decides how the float invites — but until this fix
nothing wrote that decision down, and **every later flow reads the column, not
the function**. `assessment_corporate_map.is_otp_invite` kept its `false`
default (no caller sent the flag; the v2 wizard's BFF does not send it), so a
corporate float invited candidates with a no-login `/s/` link and then, for
anything that happened afterwards, was treated as a portal-credentials campaign:

| Flow | Reads | Was doing |
|---|---|---|
| `_addStudentsToOneTimeAssessment` | `assessmentMap.isOtpInvite` | created a portal account + activation/credentials email, then `sendRemindersToStudents` |
| `resendInvitesToStudents` | same column | portal reminder instead of the OTP link |
| `AutoReminderService` | `m.is_otp_invite` | portal "log in to view" reminder |

Worse than a wrong template: `provision` (`assignmentWorker.buildUserData`)
always sets `skipActivationEmail: true`, so those candidates have **no portal
password at all** — they were being sent to a login they cannot pass.

`assignMixMatchAssessment` (`assessmentHandler.js`) now stamps each part's body
with `isOtpInvite: svc.mixMatchInviteChannel(body.entityType) === "otp"` before
delegating to `assignAssessment`, so the column records the channel the invite
actually uses and the two cannot drift. College is unaffected — the institute
map has no such column and `assignAssessment` ignores the flag for it.

**Existing float maps needed a data fix** (DEV 2026-08-20, UAT 2026-08-20; PROD
pending):

```sql
UPDATE assessment.assessment_corporate_map SET is_otp_invite = true
 WHERE mix_match_group_id IS NOT NULL AND is_otp_invite = false;
-- DEV 79 rows, UAT 46 rows
```

### A candidate added to a float is invited ONCE, not once per part (2026-08-20)

`/assessment/addStudentsToAssessment` resolves a float id to its part maps
(`mixMatchPartMapIds`) and adds the candidate to **every** part — so letting the
parts mail meant one email per part for a single addition. The parts now take
`deferInvite: true` and skip their notification block entirely; the handler then
calls `Assessment.sendFloatInvites({groupId, partMapIds, entityType, emails})`
once every part has taken the candidate. It mirrors `sendMixMatchGroupInvites`:

- channel from `mixMatchInviteChannel` — corporate `sendAssessmentInviteEmail`
  (with `mixMatch: {title, assessmentTypes}` only when ≥2 parts assigned),
  college the portal reminder via `assessmentReminderCopy`
- the link is minted from the **first floated part** the candidate landed on;
  `MixMatchJourney.assertMember` resolves the group from any member assignment,
  so any part's link opens the whole journey
- a part whose assignment failed leaves no row, so it neither supplies the link
  nor is named in the email
- `AI_Interview` owners still get `role` / `durationMinutes` / the IST deadline
  label via `_getAiInterviewEmailMeta`
- non-critical: a send that throws is logged per candidate; the addition stands

The per-candidate plan is a pure function — `app/helpers/floatInvitePlan.js`
`planFloatInvites({parts, assignedRows})` — so ordering, partial assignment and
the bundle threshold are tested without a DB
(`test/floatAddCandidateInvite.spec.js`).

Verified on UAT: floating Behaviour + Aptitude to a corporate, then adding a
candidate, produces exactly one `mixMatchAssessmentInvite` per candidate and no
portal reminder.

### The WhatsApp invite names every part (2026-08-20)

The email above listed all the parts from day one; **WhatsApp did not**, and the
two channels disagreed about what the candidate had been floated. A candidate
sent Aptitude + Communication got *"You have been invited to complete the
Communication Assessment"* and was never told the Aptitude part existed.

Two independent causes, both in the WhatsApp leg only:

- `sendMixMatchGroupInvites` passes `assessmentType: assigned[0].assessmentType`
  — the **first** part, in `created_at` order, which is the order the admin
  added them in the wizard. Reverse the selection and the message names the
  other part instead.
- `sendAssessmentInviteEmail` forwarded that `assessmentType` to
  `sendAssessmentInviteWhatsapp` but **dropped `mixMatch` entirely**, so the
  part list never reached the template even though the caller had built it.

Every WhatsApp template predating Mix & Match is built around a single
assessment, so there was nothing correct to select. Two Meta UTILITY templates
were added, submitted and **approved 2026-08-20**:

| Intent | Template | Meta ID |
|---|---|---|
| invite | `corporate_multi_assessment_invite_deadline_v1` | 1794306421754329 |
| reminder | `corporate_multi_assessment_reminder_deadline_v1` | 1753818855768401 |

```
Hi {{1}},

You have been invited to complete {{2}} at {{3}}.

Assessment: {{4}}

{{5}}.

Open assessment: {{6}}

Registered email: {{7}}

All the best!
```

`{{1}}` name · `{{2}}` float title · `{{3}}` company · `{{4}}` part list ·
`{{5}}` deadline sentence · `{{6}}` link · `{{7}}` email.

**There is no role param**, unlike every other assessment template. A bundle is
floated against the group, not a role, so `role || "open"` rendered the literal
*"for the open role"* to real candidates on UAT before this.

`resolveTemplateName(assessmentType, intent, isMixMatch)` gained the bundle
axis, and it **outranks** the per-type AI Interview choice — a bundle containing
an AI Interview is still a bundle, and `aiinterview_*` can only name one part
either. The gate is **2-or-more parts**, not "has a `mixMatchGroupId`": the same
reason `assessmentReminderCopy` branches on `partTypes.length < 2` above.

Part labels are **bare** (`Aptitude, Communication`) because the template already
prints the word *Assessment* on that line — `MIX_MATCH_WA_PART_LABELS`, distinct
from the email's `MIX_MATCH_PART_LABELS` which keeps the full noun phrase.
Hinglish maps to Communication and duplicates collapse, so a float holding both
does not print it twice. An unmapped type degrades to its de-underscored name
rather than vanishing — a silently short list is the exact bug being fixed.
Neither `{{2}}` nor `{{4}}` can ever be blank (Meta rejects an empty body param):
they fall back to `your assessment` and `Assessment`.

Selection is env-gated on `WA_MIX_MATCH_INVITE_TEMPLATE` /
`WA_MIX_MATCH_REMINDER_TEMPLATE`, **set on DEV and UAT, PROD pending**. Unset
reproduces the old behaviour exactly, so rollback is commenting one line out and
restarting — no rebuild. Templates are WABA-scoped, so both already exist in
PROD; only the env vars are missing there.

Verified on UAT by replaying the worker's own invite construction against a real
five-part group (`all assesmnet`): `Aptitude, Communication, AI Interview, Role
Based, Custom` in one message, `email_events` row `whatsapp / delivered /
corporate_multi_assessment_invite_deadline_v1`. Before the fix that group would
have said only *"the Aptitude Assessment"*.

**The reminder template has no caller yet.** Auto-reminders fire per assignment,
so a five-part bundle still sends five reminders, each naming one part — the
same class of bug in a different place. Collapsing them to one group-level
reminder is unbuilt.

admin-node `54e1a21` (Development) / `3871fcd` (UAT).

## A signed-in student enters from the v1 dashboard (2026-08-20)

Corporate candidates arrive by invite and v2 is the whole journey for them.
**Institute students do not** — they sign in, see a dashboard of their
assessments, and pick one. v2 has no screen that lists a student's assessments,
so v1 keeps the dashboard and hands the chosen assignment over.

- **v1** (`Assessment-React`, `src/modules/Assessments/index.js` — the single
  funnel where a picked assessment becomes an instruction screen) redirects to
  `/candidate-assessment-journey/v2/assessment?assigned=<id>&back=<path>`, but
  **only** when there is a signed-in student *and* an assignment id. Otherwise
  it falls through to the existing v1 instruction screens, which is what keeps
  the practice journeys and invite routes working. The path is relative on
  purpose: an absolute one built from an env var is how a DEV URL ends up baked
  into a UAT bundle.
- **v2** trades the signed-in token (same origin, so readable) for the same
  scoped `assessment:run` session an invited candidate holds, via
  `POST /students/assessments/:assessmentAssignedId/session`. Everything past
  that first screen is identical for both — the runner has one way in, not two.
- The completion screen is a dead end by design, with one exception: a student
  who came from their own dashboard gets a **"Back to dashboard"** button. The
  return path is captured from `?back=`, **restricted to this origin** so the
  screen cannot become an open redirect, and held in the module so clearing the
  session does not take the button with it.

**Ownership is proved server-side.** The login token carries `student_id` and
*no email*, so the exchange resolves that student's primary email and requires
the assignment to be addressed to it. A completed or dropped-out assignment is
refused (409) rather than reopened; another student's assignment is 403.

**An assignment that belongs to no float is a sitting of one part.** Both
`assertMember` and `getSummary` treated a NULL `mix_match_group_id` as "no
rows", which is every assessment the institute dashboard hands out. The summary's
two per-entity branches collapse into one, with the group joined optionally and
its title falling back to the assignment's own assessment name.

## Candidate APIs

`student-node` exposes private Mix & Match routes. Every part-level route verifies that the requested assignment has the same Mix Match group and candidate email as the owner assignment in the scoped JWT.

- `GET /students/mix-match/summary`
- `GET /students/mix-match/assessment/:assessmentAssignedId/questions`
- `POST /students/mix-match/assessment/:assessmentAssignedId/submit`
- `POST /students/mix-match/assessment/:assessmentAssignedId/save-response`
- `POST /students/mix-match/assessment/:assessmentAssignedId/proctoring/image`
- `POST /students/mix-match/assessment/:assessmentAssignedId/proctoring/events`
- `GET  /students/mix-match/pre-assessment`
- `POST /students/mix-match/pre-assessment`
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

## How each type gets its questions at assign time

The runner can only serve what assignment created, and each type sources its questions differently. The Mix & Match wizard (`admin-react-v2`, `POST /api/assessments/mix-match`) must therefore send a different payload per part; `assignMixMatchAssessment` runs each one through the normal single-assessment dispatcher.

| Type | Where questions come from | What the assign payload must carry |
| --- | --- | --- |
| Communication | a pre-generated set, picked by CEFR level + domain + accent | `cefrLevel`, `accent`, `responseLanguage`, `enabledSections` |
| Behaviour | a pre-made active set for the stream's domain | `assessmentDomain` (Engineering / Management) |
| Aptitude | composed at assign time from sub-topics | `aptitudeSubtopics` — **sub-topic IDs, any number ≥1**; admin-node 400s if the picked topics hold fewer live questions than the paper needs |
| Role Based | generated at assign time from the role | `roleName`, `skills`, `seniority`, `jobDescription`, `industry_domain`, `questionConfig` |
| AI Interview | none stored — asked live, turn by turn | `interviewConfig` |
| Custom | admin-authored sections, questions uploaded ahead of time | `sectionConfigurations` with **persisted** `section_id`s |

### enabledSections is two different vocabularies

This is what served candidates an empty Communication paper. The wizard picks the four **skills** — Reading / Listening / Speaking / Writing — but student-node filters the assigned set by each question's **question section**: `Paragraph Reading`, `Audio Question`, `Video Response`, `Question Based Response`, `Email Writing`, `Dictation`, `Sentence Completion`, `Sentence Build`. Storing skill names on the assignment map matches nothing, so every question is filtered out and the API returns `communications: []`.

Skills expand as follows (`src/lib/assessments/communicationSections.ts`, mirroring v1's `SECTION_GROUP_MAP`):

- Reading → Paragraph Reading
- Listening → Audio Question
- Speaking → Video Response
- Writing → Question Based Response, Email Writing, Dictation, Sentence Completion, Sentence Build

**All four selected must store `[]`**, not the expansion: an empty list means "no filter", so any section the map does not enumerate is still served. Existing DEV maps holding skill names were cleared to `[]`.

### Known gaps

- **Custom Assessment cannot be floated from v2 yet.** It needs `sectionConfigurations` pointing at sections already persisted with their questions, and the wizard still holds both client-side under generated ids with no endpoint to save them. The BFF now refuses it with that reason — previously it sent the draft shape, admin-node threw `No valid section configurations provided`, and the **whole group** failed, taking every other type with it.
- **Aptitude sub-topics are all-or-nothing per topic.** Production opens a sub-topic modal per topic card; v2 has no such modal, so choosing a topic sends every selectable sub-topic under it. Critical Reasoning has only 7, so selecting it alone is refused by the BFF for falling under the 10 minimum.

### Communication sections with missing media

Listening audio and question images live in Oracle object storage and are presigned per request. When the object is gone the API **still returns the section**: `getAudioURL` throws `NotFound` and the error is swallowed to `audioUrl: null`, while `generatePreSignedURLImage` signs without checking existence at all, so it returns a URL that 404s on fetch. Candidates got a listening question with no audio, a dictation with nothing to transcribe, and an image question with no image.

The runner now drops a section whose required media the API did not resolve — Audio Question without `audioUrl`, Dictation missing audio on any sentence, Question Based Response without `imageUrl` — and an image that fails to load renders an explanatory panel instead of a broken tile. Sections needing no media are never dropped. If every section drops, the part fails with "No Communication questions are available for this assignment."

Sets generated around 2026-03-31 on DEV have DB rows pointing at audio/image objects that are no longer in the bucket; sets from 2026-06 presign fine. A set that looks fine in the admin UI can therefore still serve a half-empty paper — check the objects, not just the question count.

### Sub-question text is not always the question

Two sections carry the *answer* in their sub-question text, so it must never be used as the prompt:

- **Dictation** — `sentence` is the sentence to transcribe. Printing it as the question handed the candidate the answer.
- **Sentence Completion** — `sentence` is the fill-in-the-blank surface, so using it as the question rendered the same line twice.

Both use a fixed instruction from `SECTION_PROMPTS` instead (`src/lib/examShapes.ts`).

### Video Response is filmed

Video Response maps to `communicationMode: "speaking"`, which captures camera **and** microphone and uploads under `kind=video`. The runner shows a live camera preview while filming and asks for camera permission by name — without the preview it was indistinguishable from an audio answer.

### The AI Interview speaks in ElevenLabs

The interviewer's questions are spoken by the ElevenLabs voice the admin chose, **not** by the browser's `speechSynthesis` — that read every question in whatever voice the candidate's OS shipped.

The chain: the admin picks a voice in the wizard → its **ElevenLabs `voice_id`** is sent as `interviewConfig.voiceId` at assign → stored on `ai_interview_config.voice_id` → returned as `voiceId` by `POST /students/mix-match/ai-interview/:id/start` → the runner posts `{ text, voice }` to its own `/api/assessment/ai-interview/tts`, which proxies FastAPI `/ai-interview/tts` and streams back `audio/mpeg`.

The two curated voices (ElevenLabs Creator tier) are:

| Voice | `voice_id` |
| --- | --- |
| Payal (default) | `CpLFIATEbkaZdJr01erZ` |
| Anika | `RABOvaPec1ymXz02oDQi` |

Samples for the admin picker live at `…/pl-uat-public-docs/ai-interview/voice-samples/{payal,anika}.mp3`. Placeholder ids like `"payal"` must never be stored — the speech endpoint cannot resolve them.

`FASTAPI_URL` is a **server-side** var on `assessment-react-v2` (v1's `REACT_APP_FASTAPI_URL`), read at request time by the proxy route, so it is not baked into the bundle. The typing reveal is only a floor: audio decides when the candidate may answer, and if speech fails the response still opens rather than stalling.

### Full screen is a condition of sitting, not a button

The runner requests full screen as the attempt opens. Browsers only grant that
during a user gesture, so when the automatic request is refused the guard dialog
covers the exam until the candidate clicks — it appears whenever full screen is
inactive, not only after they leave it.

**"Full screen" is not the same question as `document.fullscreenElement`**
(fixed 2026-08-20). That property only answers for full screen entered through
the **Fullscreen API**. A candidate who pressed **F11**, or who is on a device
whose browser has no window chrome (a kiosk, a tablet), is looking at a page
that fills the screen while the API insists it is not full-screen — so the guard
covered an exam that was already exactly as the guard wants it, and the only way
past was to leave real full screen and click the button to re-enter it a
different way.

`src/lib/fullscreen.ts` answers it as **"the API says so, OR the viewport fills
the screen"**. The threshold (`FILL_RATIO = 0.95`) sits between the two cases it
has to separate: a *maximised* desktop window still shows tabs and an address
bar and lands around 88% of screen height, while F11 and kiosk are ~100%. It
excludes the first and tolerates a scrollbar or a thin system bar in the second.

Two related faults fixed with it:

- The `fullscreenActive` state started `false` and nothing corrected it until
  something happened to fire `fullscreenchange`, so a page that opened *already*
  full-screen wore the guard regardless. It syncs on mount.
- Leaving F11 fires **`resize`**, not `fullscreenchange`, so the guard could
  never come back once dismissed. `resize` is watched too — and because it fires
  constantly (a rotated phone, a shown keyboard), a `fullscreen_exit` proctoring
  event is recorded only on a real transition **out**, not on every event.

`enterFullscreen` no longer asks the API for something the candidate already
has: that request can be refused, and a refusal read as a failure.

### Interview evaluation parameters come from the model

The wizard's "AI Suggestion based on Role" calls `POST /ai-interview/suggest-parameters` on admin-node (which forwards to the FastAPI engine), through the BFF route `/v2/api/assessments/ai-interview/suggest-parameters`. It answers `data.parameters[]` of `{id, name, description, weight, min_pass_rating}`; the wizard takes the first five names and weights, and only splits 100 evenly if the engine omits weights. Note the admin-node route is **not** auth-gated upstream, though the BFF still requires an admin session.

### Answers are saved per question, not only at submit

v1 writes every answer as the candidate gives it, via `POST /students/assessments/saveResponse` with `{ payload: { questionId, answer, assessment_assigned_id, timeTaken } }`. The Mix & Match runner does the same through `POST /students/mix-match/assessment/:id/save-response`, debounced and best-effort — the final submit still sends the whole attempt, so this is the recovery copy, not the record of truth. Without it a browser that dies mid-test loses everything.

The scoped route exists rather than reusing the student one because `saveResponse` trusts whatever `assessment_assigned_id` the body carries. That is safe for a logged-in student, who only holds their own token; an invite token is scoped to one group, so membership is checked before the answer is stored. Verified: a token for one candidate saving to another's assignment gets `403 Assessment is not part of this Mix & Match invite`.

Answer shape per type — the same values the submit sends, so the two cannot disagree:

| Type | `answer` |
| --- | --- |
| Communication, sub-question | `{ subQuestionId, selectedOption }` |
| Communication, single-response (Email Writing, Question Based Response) | the plain value |
| Aptitude, Behaviour | the option **text** |
| Role Based | option **id** (MCQ), trimmed text (subjective), `{code, language, test_results}` JSON (coding) |

Not sent through this path: **recordings** (the media upload already writes the row, with a storage key this endpoint has no field for), **Role Based video**, and **Custom Assessment** — `saveResponse` throws `Unsupported assessment type: custom_assessment`, which is why Custom stores only at submit.

### Two answer values that were unscoreable

Both were found in `assessment.student_answers` on DEV and are fixed in the shared value transform:

- **Sentence Build** stored the drag handles' ids (`"…-item-1 …-item-0"`) because the reorder answer keeps ids rather than words. v1 saves the arranged content, which is what the scorer compares against.
- **Recordings** stored `{"durationSec":3}` as the answer text, overwriting the row the upload had already written with the real storage key.

### Recordings are uploaded from a queue that outlives the page (2026-08-20)

A recording used to be POSTed straight from MediaRecorder's `onstop`, and
nothing else held the blob. On a phone that is a coin toss: a video response
over a mobile link takes tens of seconds, and the moment the candidate switches
app, the screen locks, the page navigates or the assessment is submitted, the
in-flight request is killed and the take is gone — with a toast as the only
trace. The nginx logs for a failed sitting show **no upload request at all**.

The blob is now written to **IndexedDB** (`pl.v2.uploads`, store `pending`)
first and uploaded from there, so it survives a reload, a crash, a lost
connection and the submit itself, and is picked up again by whatever page loads
next — including the completion screen. Retries back off across eight attempts
and resume on `online` and on the tab becoming visible.

- v1 tracked in-flight uploads and drained them before finalising
  (`createInflightUploads`). That guarantee is kept: the final submit awaits the
  queue, **bounded** (20s) so a dead network can never trap a candidate on a
  submit button. Outliving the page is the part v1 never had.
- Each record carries the **scoped token it was made under**, because the
  completion screen drops the session on purpose and a recording still going up
  at that moment must not be stranded by it.

**The upload goes straight to student-node, not through the candidate app.**
The body used to cross the box twice, which meant two `client_max_body_size`
limits to keep in step — and the one covering the Mix & Match upload routes was
never raised, so a video came back **413** while the identical upload succeeded
on the v1 path. The browser now posts to
`POST /students/mix-match/assessment/:id/upload-audio|upload-video` directly,
carrying the same scoped token, and the BFF `media/[kind]` route is gone.

The base URL is asked of the server per session
(`GET /api/assessment/upload-url`, derived from `STD_API_URL`) rather than
compiled into the bundle — the same reason the live-transcription socket URL is
(see `ai-interview/stt-url`): a build-time constant pins the host per build,
which is how UAT traffic ended up pointed at DEV.

Two things the proxy had been doing quietly, which going direct exposed:

- student-node verifies `authorization` **verbatim**. A `Bearer ` prefix fails
  the check — send the RAW token.
- The handler only writes its `student_answers` row when **both**
  `assessmentAssignedId` and `questionId` are in the multipart body, *before*
  the file boundary (fastify-multipart only exposes parts parsed before it).
  Without the assignment id the upload answers **200 with `storedInDb: false`**:
  the recording reaches object storage and is never linked to the attempt.

**nginx.** `/students/mix-match/assessment/:id/(upload-audio|upload-video|proctoring/image)`
now has its own `client_max_body_size` on both DEV (100M) and UAT (150M),
matching the v1 `/students/assessments/upload{Audio,Video}` locations next to
it. Without it those routes inherit `location /`'s **1M** default.

### A recorded answer keeps the container it was recorded in (2026-08-20)

Safari — which is every browser on iOS — records **MP4**, not WebM. Three
places assumed otherwise, and together they are why a video that uploaded
perfectly well still came back "Video not available" in the report:

1. the client named the part `.webm` regardless;
2. `uploadToOracle` appended `.webm`, so an MP4 landed as `video-x.mp4.webm`
   while the answer row recorded `video-x.mp4`;
3. `generatePreSignedURLVideo` appended `.webm` too, signing a valid URL for a
   key nothing was ever written to.

All three now resolve the real container (`resolveVideoContentType`,
`resolveVideoObjectName`, and the client's `recordingFilename`). The audio path
had been fixed for this long before; video never was.

### The read-aloud is recorded once, and it closes its own passage (2026-08-20)

Paragraph Reading was judged against a 15-second minimum it offered no way to
meet: the take could only be replaced *while* it was too short, and every
question on that passage stayed locked until it wasn't. A candidate who stopped
early got "Record again" and a section that would not open.

The flow is now: **record → stop starts the 90-second silent reading
immediately, whatever the take's length → the questions on that passage open.**
No re-record is offered. Length is deliberately not a gate, because the
recording cannot be retaken.

- The gate reads the silent-reading **deadline** (`silentReadingEndsAt`) rather
  than a flag the on-screen timer clears, so leaving the passage mid-window no
  longer strands it — an elapsed window is finished whether or not anything was
  mounted to notice.
- The passage is open while it is being read (aloud, then silently) and
  **closed again once the silent reading ends**, so returning to the question is
  not a way to re-read it while answering. The text carries `aria-hidden` when
  closed.
- A still-sealed question carries a **"Go to the passage"** button rather than
  instructions for finding it.

### A listening question holds navigation until the recording is done (2026-08-20)

The palette already refused to open a sealed listening question; Previous and
Next were the way around it. Both are now disabled until the candidate is done
with the recording, and Next says why ("Finish the recording to continue").

That lock needs an exit when the recording itself is broken — DEV has lost
question audio before, and a signed URL for a missing object looks valid until
it is fetched. A recording that fails to load or play now says so and offers
**"Continue without it"**, rather than leaving the candidate on a question they
can neither answer nor leave.

### Question text is Markdown, and is rendered as such (2026-08-20)

Aptitude questions are authored in Markdown and were printed raw, so a candidate
read literal asterisks and backticks — and, worse, **every line break was lost**.
A coding-and-decoding question collapsed its digit/code table and its numbered
conditions into one wall of prose. Of 2,558 aptitude questions, **864 carry line
breaks**, 250 bold, 106 code runs and 288 lists; Role Based goes through the
same panel.

Six constructs cover the bank: paragraphs, hard breaks, bulleted and numbered
lists, `**bold**`, `` `code` ``, and `$…$` — which is **not** maths but a LaTeX
habit of the generator wrapped around plain text (exactly one question in the
bank contains a LaTeX command), so its delimiters are dropped and the text kept.
That is not worth a Markdown library, let alone a maths one: it is a small
parser (`_components/exam/markdown.ts`) with the constructs pinned by tests.

Question text stays **data**: it is parsed to spans and rendered as React
elements, never HTML, so a stem cannot introduce markup. Code runs keep their
spacing, which is what lines the code table's columns up. The stem cannot be an
`<h1>` any more — it is regularly several paragraphs and a list — so it carries
the heading role explicitly.

### Proctoring

Report-only, as in v1: nothing warns, interrupts or auto-submits, and the whole runner is inert unless the invite carried `allowProctoring`. Two streams, at v1's cadences:

- **Snapshots** — a hidden camera sampled every **13s**, uploaded as multipart to `POST /students/mix-match/assessment/:id/proctoring/image`. Lands in `assessment.proctoring_snapshots` (`snapshot_key`, joined to `proctoring_logs`).
- **Events** — batched and flushed every **30s**, plus on submit and teardown (`keepalive`, so a closing page does not drop the last batch), to `POST /students/mix-match/assessment/:id/proctoring/events`. Lands in `assessment.proctoring_events`.

Snapshots follow whichever part is open when they fire. The event envelope must match what the report scores: `{ type, source, startMs, endMs, durationMs, severity, confidence, evidenceObjectKey, meta }`, with `startMs` relative to the start of the sitting.

Only **`tab_hidden`** and **`fullscreen_exit`** are reported — the signals the screen genuinely observes. v1's gaze, head-turn and no-face events come from a MediaPipe FaceLandmarker collector loaded from CDN, which v2 does not run; emitting them without it would put unearned findings into a report a human acts on.

Both upstream endpoints (`/students/assessments/proctoring/{image,events}`) take the assignment **from the request body and never check ownership** — safe for a logged-in student, not for an invite token scoped to one group. The candidate routes verify membership first. The snapshot route cannot rewrite a streamed multipart body, so it passes the verified id out-of-band and `uploadImage` prefers `req.proctoringAssignmentId` over the form field. Verified on DEV: no auth `401`, another candidate's assignment `403`, own assignment `200` with rows written.

Note `studentId` is optional upstream and deliberately so — OTP-invite candidates have no portal student id, and requiring it used to 400 them and skip proctoring entirely.

### Pre-Assessment Registration

The admin builds a field list in the wizard; the candidate fills it in at `/assessment/start` before the sitting.

**The overview decides whether that route is reached at all.** It originally called `preStages` on the *demo scenario* config, so an invited candidate's real form was never consulted and registration silently never appeared. It now fetches the float's actual form and the interview's resume policy, and routes on what the float carries. The form belongs to the **group**, not a part — it is collected once per float however many assessments it contains.

- **Storage** — `assessment.pre_assessment_forms` (one row per group, `fields` is the admin's `FormField[]` verbatim) and `assessment.pre_assessment_responses` (one row per candidate per form, upserted on re-submit). Migration `20260818T063235Z__pre_assessment_registration.sql`.

  **Neither table is in any Prisma schema** — both are reached only by raw SQL
  (`admin-node` `assessmentHandler.assignMixMatchAssessment`, `student-node`
  `models/PreAssessmentForm.js`), so `prisma migrate` will never create them and
  a deploy cannot self-heal a missing one. The migration has to be applied to
  each environment by hand.

  **If it is missing, the whole float 500s.** The insert runs immediately after
  `mix_match_groups.create` and is *not* in the same transaction, so the group
  row is already committed when the raw insert throws
  `42P01 relation "assessment.pre_assessment_forms" does not exist`. The admin
  sees only a failed float; the database is left with an **orphaned
  mix_match_group carrying no parts**, one per retry. This hit UAT on
  2026-08-19 11:56–12:09 UTC ("Pre assessment submission is not able to
  assign") and left 18 such rows before the migration was applied. Floats
  *without* a registration form are unaffected, which is what makes it look
  intermittent.

  **PROD is still pending this migration** — the same 500 is waiting there the
  first time someone floats with a registration form.
- **Admin** — `admin-react-v2` sends `preAssessmentForm: { fields }` as a **top-level** field of the Mix & Match payload, not as a part, since registration is not an assessment. `assignMixMatchAssessment` writes it against the new group.
**Routing to it.** The overview decides whether a float has pre-assessment steps from the **real** form and the interview's resume policy. It used to call `preStages` on the demo `?pre=` scenario config, so an invited candidate's authored form was never consulted and the step silently never appeared.

- **Candidate** — both routes take the candidate from the scoped token and the float from that candidate's own assignment, so there is no id to tamper with: an invite can only ever read or write its own float's form. Answers already on file come back with the form and take precedence over the local draft, so returning to a half-finished registration shows what was actually submitted.

Before this, the wizard collected the field list and `partFor` returned `null` for it, so the config never left the browser and the candidate journey fell back to its `?pre=` scenario mock. That mock still drives the demo route, which has no invite to ask.

### The readiness check verifies a face and a voice, not just permission

The device check used to mark Camera and Microphone "ok" the moment `getUserMedia` resolved — true of a lens pointed at a wall or a muted mic. It now asks the same engine v1's `BiometricCheck` uses, proxied through `/api/assessment/verify/[kind]` so the engine URL stays server-side:

| Check | Upstream | Passes on |
| --- | --- | --- |
| Camera | `POST /proctoring/verify-frame` | `success && face_detected` |
| Microphone | `POST /proctoring/detect-audio` | `success && audio_detected` |

`detect-audio` needs a few seconds of speech before it can judge a human voice, so the mic row records a ~3.5s sample while showing "Say a few words…".

**The rows wait for the verdict** (fixed 2026-08-20). They used to flip to
"Ready" the moment permission was granted and only *then* ask the engine, so the
candidate was told they had passed a check that had not been made and "Begin
assessment" was live throughout it — which is why it looked like nothing was
being checked at all. Both rows now stay running until the answer lands, and the
camera preview follows the **stream** rather than the check's status, because the
candidate has to see themselves to get in frame while the check runs.

The face check looks at up to **three frames** rather than the first one it can
grab: a candidate is usually still settling when the camera produces that, and
one unlucky frame should not be the difference between Ready and a dead end. Any
frame with a face passes; only a run of clean no-face verdicts fails.

An engine that cannot answer — unreachable, 5xx, or no invite token on the demo
route — returns `unchecked`, which **leaves the permission result standing**: a
service blip must never become a locked door in front of a candidate who is
ready to sit. It is no longer dressed up as a pass, though — the row reads
"Camera on — face check unavailable" rather than claiming a detection that never
happened.

Requires `FASTAPI_URL` (server-side only, v1's `REACT_APP_FASTAPI_URL`).

### Leaving mid-test

`beforeunload` raises the browser's own confirmation while an attempt is live, dropped once it is submitted so the completion page never argues about leaving. No site can choose that prompt's wording — every major engine has shown fixed text since 2016 — so the consequence is also stated in plain sight next to the timer: *"Don't reload or close this tab — your assessment will be submitted as it stands."*

### The completion page is a dead end, deliberately

It used to offer a Done button routing to `/`, which is the sign-in screen: a candidate who had just submitted could enter their email, take a fresh OTP and walk back into a finished assessment. The invite and candidate sessions are now cleared on arrival and the button is gone, so neither it nor the back button leads anywhere that can reopen the sitting.

### The resume step is the AI Interview's call

The resume screen follows the AI Interview's `resumePolicy` (`mandatory` / `optional` / `not_required`), surfaced on the summary — **not** a `file` field on the registration form. The interview is the only part that reads a resume, so a float without one, or with the policy set to `not_required`, no longer asks for a document nobody will open.

### Duration is a sum of what is known

`totalDurationMinutes` used to require *every* part to have a configured duration, so one unknown blanked the whole total: the candidate saw no duration and the runner fell back to a hard-coded 60-minute clock regardless of the sitting. It now sums the parts that have one, with `durationPartial` flagging that the real sitting is at least that long.

### The candidate is quoted the length and count the admin set (2026-08-20)

Only **Role Based, AI Interview and Custom** store a duration — Role Based on
`assessment_config.duration_minutes`, AI Interview on
`ai_interview_config.interview_duration`, Custom summed from its section times.
On DEV, of sets created in the preceding ten days: Aptitude 39 sets / 0 with a
stored duration, Communication 2 / 0, Role Based 4 / 4.

Everything else falls through `estimatedDuration()` in
`student-node/app/models/MixMatchJourney.js`, and that estimate had nothing to
do with what the admin picked — Aptitude used its *question count* as minutes
(a 60-minute paper read as 40) and Communication used 12 minutes per section.
Both now derive the admin's own number:

| Type | Candidate clock |
|---|---|
| Aptitude | inverted blueprint — 25 questions → 30 min, 30 → 45, 40 → 60 |
| Communication | summed from the sections enabled — 30 min for the full paper (see [communication.md](communication.md#duration-is-summed-from-the-enabled-sections-2026-08-21)) |
| Behavior | 20 min |

The Aptitude blueprint is 1:1 and invertible, so reading it backwards returns
exactly the duration that was chosen. **Nothing is persisted per assignment on
purpose:** Communication sets come from a shared pre-generated pool and
`assessment_config` is 1:1 with a set, so writing one assignment's duration
there would change it for every other assignment reusing that set. The rule
lives in two places and the two must agree — `estimatedDuration()` here and
`assessmentMetrics()` in `admin-react-v2/src/lib/assessments/typeSummary.ts`.

`estimatedDuration()` takes the map's `enabled_sections` as its third argument
for Communication and delegates to
`student-node/app/helpers/communicationDuration.js`. **Empty means the whole
paper, not no sections** — see the Communication doc; reading its length as a
section count is what made the fullest paper the shortest one.

### Communication is counted in questions, and the count is 7

A Communication set holds **one question per section** — the set rows confirm
it, 8 sections and 8 mapped questions — so the number the admin used to see
labelled "7 sections" was already the question count wearing the wrong unit. It
reads "7 questions" on both sides now.

The candidate side was separately reporting **8**: it counted the mapped rows,
but student-node serves exactly one of **Email Writing** or **Dictation** per
candidate (the `IsEmailWriting` flag drops the other, `Assessment.js` ~3165), so
the raw count was always one too many. A `comm_counts` lateral in the summary
subtracts the twin when both sections are present.

**Behaviour still disagrees:** the summary reports the whole domain bank (115 on
DEV) while the wizard shows a hardcoded 15. The two *times* agree at 20 min.
Unresolved — neither number has been checked against what the Behaviour runner
actually serves.

### A module is finished explicitly, then goes read-only

Every module's last question carries a **"Finish <Module>"** control rather than
a plain Next. `isPartComplete` is now the same explicit-finish signal for every
module — previously only the AI Interview worked that way.

**The question is asked before anything is committed** (fixed 2026-08-20). It
originally locked the module and moved the candidate on, then raised the dialog
saying so — meaning every way *out* of that dialog (Cancel, the scrim, Escape)
still left them in the next module, because the decision had already been taken.
On the last module it was worse: that path opens the final review, so "Keep
working" returned to a module that was already closed. `commitModule` is now the
single place a module closes, both dialogs route through it on confirm, and
neither does anything on the way out. The copy follows the same logic —
"Finish Aptitude?" not "Aptitude submitted", "your answers *will be* locked in"
not "are locked in".

Confirming opens either a **Module Complete** summary ("Begin <Next Module> →")
or, on the last module, the Review and submit dialog.

**A finished module stays open to revisit, but every answer surface renders
disabled** — options, textareas, the reorder list, the code editor, recording
controls. This is enforced **in the reducer** (`SELECT` / `CLEAR` /
`TOGGLE_MARK` refuse a locked module), not only in the UI, so a stale component
or a devtools poke cannot write to a module the candidate has closed. Only one
module is open at a time (`canOpenAssessment`, gated in both the track and the
`SWITCH_ASSESSMENT` reducer case).

**Negative marking is surfaced, and changes the finish prompt.** Aptitude
questions carry `negativeMarking` and show a "Negative Marking" tag. A module
flagged with it **skips the unanswered-count caution** on finish — leaving a
question blank there may be a deliberate choice to avoid a penalty, not an
oversight, so nagging about it would push candidates into guessing.

### Communication locks its subsections one at a time

`loadCommunication` in `liveExam.ts` was hardcoded to `freeNavigation: true` on
the **live** path while the mock build already sequenced them, so the two
disagreed about the same assessment. Communication now matches Role Based.

Previous/Next are also disabled while a recording (read-aloud, speaking, video)
or a dictation playback is actively running, and Previous now respects the
post-read-aloud silent-reading window that Next already did.

### A stale chunk reloads instead of killing the attempt

"Begin assessment" crashed to the root error boundary whenever a candidate's tab
had loaded its JS **before** a deploy replaced that build: a client-side
navigation then 404s on a chunk hash that no longer exists (`ChunkLoadError`).
`global-error.tsx` swallowed it silently and its "Try again" only reset the
boundary — re-rendering the same stale tree asking for the same missing chunk,
so it could never recover.

It now logs the error and, when the shape is chunk-load-like, **hard-reloads
once** to fetch the current build, with a 15-second guard against looping if the
server itself is broken. The detector is a pure function in
`lib/staleChunkError.ts` with tests. This matters here more than in most apps:
deploying mid-sitting is normal on DEV/UAT, and the candidate cannot simply be
told to start over.

`reconcileAttempt` also backfills `completedParts` on a restored attempt — it
backfilled `audioSettled` and `tabViolations` but not this, and the module lock
reads it unguarded on every render, so a record stored before the lock existed
took the whole screen down on resume.

### Drop-off is a property of the sitting, not of a part (2026-08-20)

Opening a float claims **every** part at once: `fetchLiveTest` (`lib/liveExam.ts`)
runs one `Promise.all` over the whole float, and fetching a part's questions is
what marks it started. So every non-AI part is `INPROGRESS` from the first
second, long before the candidate reaches it — `helpers/assessmentStartGuard.js`
already relies on exactly this to treat an `INPROGRESS` part as a resume rather
than a second device.

`script/updateDropoutStatusCron.js` did not know that, and timed each part from
its own `assessment_started_at`. **Live candidates were therefore declared
dropped mid-sitting**, and `DROPOUT` is terminal (`NOT_STARTABLE`), so the start
guard then refused to let them back into parts they had never opened. One DEV
sitting started its four parts 70ms apart:

```
Communication      14:49:45.211      Custom_Assessment  14:49:45.243
Role_Based         14:49:45.234      Aptitude           14:49:45.278
```

Under the old rule three of the four were dropped at **t+23 min** while the
candidate was still working; the fourth at t+61. The DB signature is two parts
started milliseconds apart and dropped 38 minutes apart.

**The rule now:** a float's open parts share one clock.

- **clock** — the last thing we saw the candidate do anywhere in the float: the
  latest part start **or part submission**. Submitting Communication at minute
  20 restarts the clock there, instead of pretending Aptitude began at minute 0.
- **allowance** — the sum of the per-type timeouts of the parts **still open**
  (60 aptitude, 60 AI Interview, 22 everything else). Finishing a part shortens
  what is left to wait for.

Every still-open part of an expired sitting is dropped **together**. Nothing is
dropped earlier than the per-part rule dropped it — only later. A float with a
single open part is unchanged by construction (allowance = that part's own
timeout), which is what the first UAT sweep after deploy exercised: one
abandoned Aptitude part, started 60 minutes earlier, correctly dropped.

The decision is a pure function — `app/helpers/mixMatchDropout.js`
(`splitMixMatchParts`), tested in `test/mixMatchDropout.spec.js`. The cron
selects **every** part of any sitting that has an open one (submitted parts
included — they carry the submission that moves the clock) and holds the open
ones out of the three per-part sweeps by id. Raw SQL, because student-node's
Prisma schema does not carry `mix_match_group_id` on either map.

An AI Interview part is **not** claimed at sitting open — `loadAssessment`
returns it without fetching questions — so it starts when the candidate reaches
it. Its single-attempt guard in `aiInterviewHandler.startSession` (flip to
`DROPOUT` on a second `start`) is unchanged and is not float-specific;
`startInterviewOnce` dedupes in memory, so it only fires on a real reload.

### Finishing is the candidate's call

Finish is always available. It used to be disabled until every part was complete and refused outright while the AI Interview was unfinished; the confirm dialog already lists what is unanswered, which is where that belongs rather than in a button that cannot be pressed.

### The readiness check verifies, it does not just ask permission

The device check used to confirm only that camera and microphone permission had been granted. It now asks the same FastAPI engine v1's `BiometricCheck` uses:

- **Face** — `POST /proctoring/verify-frame` with `{student_id, frame_number, image_data, min_confidence}` → `face_detected`. Uses MediaPipe (`detect_face_fast`), not RetinaFace: this is the gate every candidate hits, so it needs liveness, not landmarks.
- **Voice** — `POST /proctoring/detect-audio` with `{student_id, audio_data}` → `audio_detected`. Needs 3+ seconds, so the check records ~3.5s.

Both are proxied through `/api/assessment/verify/{face,audio}` so `FASTAPI_URL` stays server-side, and both return a flat `{ ok }`.

**An engine that cannot answer leaves the permission result standing.** A timeout, a 502 or a missing token resolves to `unchecked`, never `failed` — a service blip must not become a locked door in front of a candidate. Only a positive "no face" / "no voice" downgrades the check.

### Leaving the exam

Browsers no longer let a page choose the wording of an unload prompt, so the consequence is stated next to the timer where the candidate is already looking, and `beforeunload` raises the browser's own confirmation while an attempt is live. The listener is dropped once `finalSubmitted` is set, so the completion page never argues about leaving.

### The completion page is a dead end, deliberately

It used to offer a Done button that routed to `/` — the sign-in screen — where a candidate who had just submitted could enter an email, take a fresh OTP and walk back into a finished assessment. The invite session is now cleared on arrival and there is no button: nothing leads anywhere that can reopen the sitting.

### Submit payload per type

Each type is scored from a different shape, so the runner builds a different payload per part. These live in `assessment-react-v2/src/lib/examShapes.ts`, which imports only types so the transforms are unit-tested without a browser.

| Type | `response` shape | Answer identified by |
| --- | --- | --- |
| Aptitude, Behaviour | `{ [questionId]: answer }` | option **text** |
| Custom | `{ [questionId]: answer }` | option **id** |
| Role Based | `{ mcqQuestions, subjectiveQuestions, codingQuestions, videoResponses }` | option **id**; video by `objectKey` |
| Communication | one array per section (`paragraphReading`, …) | per-section |

Getting the option-id-versus-option-text distinction wrong scores a candidate zero without failing anything, so both directions are pinned by tests in `examShapes.test.ts`.

Coding answers submit `{ code, language, test_results: [] }`. The empty results are deliberate — the server re-runs the test cases itself and only trusts frontend results when they are supplied.

Nothing executes in the browser. Pressing **Run** posts `{ questionId, language, code }` to the v2 BFF route `POST /api/assessment/parts/:assessmentAssignedId/run-code`, which forwards to student-node and on to the code-runner sandbox; all six languages the sandbox runs are offered, and the same harness scores the attempt at submit time. See [Role Based → Coding runs server-side](rolebased.md#coding-runs-server-side-test-case-inputs-and-outputs-are-now-graded-correctly-2026-08-20-dev--uat) for the whole chain.

Role Based video clips are uploaded while recording; that upload already attaches the storage key to the attempt server-side, and the submit payload repeats it as a safety net exactly as v1 does.

Unanswered questions are omitted rather than sent blank: the server rejects an empty answer, and a missing row scores the same as an explicitly skipped one.

### Refresh and resume

The take-page loader is single-flight because fetching questions claims a single-shot assessment (`PENDING` to `INPROGRESS`). This prevents React remounts from issuing a second start request.

That claim happens for **every part in the group** the moment the combined test opens, so `INPROGRESS` is the normal state of a part the candidate has not reached yet. The start guard used to read that as "already running on another device", so one browser refresh answered `409 ALREADY_IN_PROGRESS` for every part at once and ended the sitting with no way back in.

`resolveAssessmentStartConflict` now takes an `isMixMatch` flag and treats an `INPROGRESS` Mix & Match part as a same-candidate resume. The flag is set only by `getMixMatchAssessmentQuestions`, after `assertMember` has verified the scoped invite JWT owns that assignment — a caller who merely knows an assignment id cannot set it. `COMPLETED` and `DROPOUT` are still refused, so a submitted or abandoned part cannot be reopened.

On the client, a restored attempt is re-seated against the test that actually loaded (`reconcileAttempt`). Questions are fetched again on every mount and a part can come back with different ones (Aptitude regenerates its set when the candidate's level has moved), so a persisted cursor could name a question that no longer exists — which rendered nothing at all and stranded the candidate on the loading skeleton. Answers are keyed by question id, so a refresh costs the candidate their place, not their work.

A combined final submission is blocked until AI Interview is complete. Every other part is submitted with one request each. The overall timer uses the same backend submission path as manual finish.

### Delivery status on the consolidated report

A Mix & Match row represents several `assessment_assigned_students` rows, but
the bundle sends one invitation and records its `email_events` against only the
owner part. The consolidated report must therefore resolve delivery across all
part assignment ids. It uses the normal precedence (`Opened` > `Sent` >
`Processing` > `Failed`) and merges the channel detail for the hover. Looking up
only one arbitrary part produces a false untracked dash even when another part
owns the email/WhatsApp event.

Fixed and deployed to DEV in `admin-node` `8c8464e` (2026-08-21). Verified on
the live `Test assessment` float: `vedantmnadhe+ss@gmail.com` now resolves to
`Opened` with its email leg present instead of `—`.

## DEV deployments

- `student-node` commits `e60c67b2`, `9f7dfca5`, `1f43c573`, `b6eeeb63`, `5fd5e9d7`, `69470352`
- `assessment-react-v2` commits `4602376`, `c70bee7`, `d1822b4`, `b7c78b4`, `da1432a`, `518203e`, `936a10d`, `6fafe50`, `8b0d903`, `2b5c9b3`, `19fe1e4`, `071666e`, `d2484f1`, `52e0aa1`
- `admin-react-v2` commits `741a9b4`, `c17e420`, `892f520`, `5e44c23`
- `admin-node` commits `8d04f84`, `d4f5f44`, `1a128d1`, `8c8464e` (delivery status on consolidated rows; DEV 2026-08-21, UAT/PROD pending)
