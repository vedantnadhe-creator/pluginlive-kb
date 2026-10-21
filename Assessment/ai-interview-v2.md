# Complete AI Interview (AI_Interview_v2)

> **State (2026-10-16):** LIVE on **DEV + UAT**. **PROD pending** (needs the DB script, the three gateway tasks,
> and every service below, plus the `/ai-interview-v2/` ingress path; see *Proxy timeout* below). Corporate floats only (the report lives in the corporate portal, not the institute one).

AI Interview and Role Based merged into one assessment: the recruiter builds an **Interview Flow** of ordered rows
(voice, subjective, single choice, multiple choice, coding, custom task), an LLM plans
the paper, and the candidate sits it as one interview — voice turns with the AI interviewer plus fixed screens —
with one combined score and one report.

| Property | Value |
|---|---|
| Assessment type | `AI_Interview_v2` (`assessment.assessment_type` row + section `Interview Task`) — DB-Scripts `AI Interview v2/20261013T100315Z__ai_interview_v2_assessment_type.sql` (DEV + UAT applied, PROD pending) |
| Wizard type key | `complete-ai-interview` — "Complete AI Interview" (badge *New*) |
| Who can create it | Corporate entities **subscribed** to `AI_Interview_v2` in Feature Access (admin wizard and corporate wizard); never colleges |
| Gateway tasks | `pl/interview-skeleton` (planner), `pl/interview-slot` (content), `pl/interview-v2-score` (task answers) — Gemini 3.8 Flash → Luna fallback, granted to the fastapi key |

---

## Float (creation)

1. **Wizard** (corporate-react-v2 wizard `0.1.2-bugfix.19` DEV / `0.1.2-bugfix.19-uat` UAT; admin-react-v2 wizard
   `0.1.16-custom.10` DEV / `0.1.12-custom.8` UAT). Role, skills, JD, evaluation parameters (Communication fixed 20%),
   languages, voice, and the Interview Flow rows. **The question-type dropdown no longer offers Reading task or
   Listening task** (removed 2026-10-14/15 in both wizards, `FLOW_TYPE_OPTIONS` in
   `assessmentWizardConfigOptions.ts`). The `reading` / `listening` types, placeholders and payload mapping are kept,
   so a float or duplicate that already carries one still validates, submits and runs. Such a row still **shows its
   own type** ("Reading task" / "Listening task") and keeps it in that row's dropdown only (`typeOptionsFor` in
   `InterviewFlowTable.tsx`, 2026-10-15) — before that it rendered as "Select question type" and Enter re-typed it to
   Subjective. Reading / Listening / Custom
   rows **require instructions** (they describe the task). Single/multiple choice rows may carry hand-written questions. Count blank = "Auto".
2. **Float route** sends `assessmentType: "AI_Interview_v2"` with `interviewConfig.flow`.
3. **admin-node** `AIInterviewV2AssignmentService` only **validates** the flow and registers the Role Based async
   job — the float returns at once (~0.7 s); the creator is told invites follow paper generation. An omitted
   `interviewDuration` is normalised to 30 min at validation, so the invite, the planner target and the runner
   deadline all use one value. **One set generator per job plans**: it claims planning on the job row
   (`config_snapshot.aiInterviewV2PlanClaim`, epoch seconds, 240 s TTL so a dead claimer is taken over; released on
   failure), calls fastapi `POST /ai-interview-v2/skeleton` (up to 3 LLM attempts with the validator's errors fed
   back) and stores the plan (`config_snapshot.aiInterviewV2Plan`, compare-and-set). The other papers poll every 3 s
   for the stored plan, so a job costs **one planner call**. A failed plan throws and rides the queue's retries
   (8 attempts, exponential from 30 s). The error keeps the upstream status (`plan failed (HTTP 502): …`), so a
   planner outage (5xx / timeout / "timeout waiting for another set") is left in `preparing` for the
   transient-recovery reconciler, while a 4xx (no valid plan) fails the job and notifies like any generation
   failure. Jobs queued before this change carry their plan on `spec.payload.skeleton`.
4. **Paper generation** (assignment worker, set generator `ai-interview-v2-generate`): Role Based questions for
   subjective / single choice / coding rows, fastapi `POST /ai-interview-v2/generate-slots` for task content
   (passages, TTS audio, questions), authored questions as written. Every **answering step of a task gets its own
   answer row** (`content[block].items[n]["@answer:<phaseId>"]`), so a task may have any number of steps.
5. Candidates are assigned and invited when the paper exists.

### Proxy timeout for `/ai-interview-v2/` (infra, every env)

`generate-slots` is **one LLM call plus one TTS call per spoken item, run one after another**
(`slot_content.py` `render()` → `speak()`), so a big voice block runs past 60 s. A 12-question
Communication & Language block on UAT took ~49 s for the LLM call alone (2026-10-21). admin-node waits
**300 s** (`FastAPIService.js`, `timeout: 300000`); the proxy in front of fast-api must wait at least that long.

- **Symptom:** the float stays in `preparing` with 0 assigned; admin-node logs
  `prepare-set <n> failed (attempt k/8): Request failed with status code 504` at **exactly 60 s**. fast-api logs the LLM
  `200 OK` but never the `generate-slots` access line, because nginx dropped the connection mid-TTS. Each retry
  regenerates from scratch, so retries never help. Small blocks finish under 60 s, which hides the problem.
- **Cause (DEV + UAT):** `/etc/nginx/sites-enabled/fast-api.conf` had a long-timeout block for `/ai-interview/` (v1)
  only. `/ai-interview-v2/` fell through to `location /` → nginx default `proxy_read_timeout 60s`.
- **Fix (DEV + UAT, applied 2026-10-21):** added `location /ai-interview-v2/` (connect 300, send/read/send_timeout 600,
  `client_max_body_size 50M`, `proxy_pass http://localhost:8011`), `nginx -t`, `systemctl reload nginx`. Backups:
  `/etc/nginx/fast-api.conf.bak.<UTC-ts>` (kept outside `sites-enabled/` so they are not loaded). No fast-api restart.
  Stuck `preparing` jobs resume on the next retry or reconciler pass with no reset needed.
- **PROD (k8s, checked read-only 2026-10-21):** `api-fast.pluginlive.com` has no `/ai-interview-v2/` path.
  It falls to `fast-api-prod-ingress` `/`, which sets `proxy-read-timeout: 300` and `proxy-send-timeout: 300`. That
  equals the admin-node client timeout, so the 60 s failure does not happen on PROD. **When v2 ships to PROD**, add
  `/ai-interview-v2/` to the `fast-api-ai-interview` ingress (already 600 s, same host) so nginx never cuts the call
  before the client does:
  `kubectl -n api patch ingress fast-api-ai-interview --type=json -p '[{"op":"add","path":"/spec/rules/0/http/paths/-","value":{"path":"/ai-interview-v2/","pathType":"Prefix","backend":{"service":{"name":"fast-api","port":{"number":80}}}}}]'`
  (on the PROD builder, `export PATH=$HOME/bin:$PATH` first).
- **Any new fast-api route prefix doing LLM/TTS/STT work needs its own long-timeout block on DEV/UAT nginx.** Same
  failure as the `/hinglish/` 504 → stored `0` (see [communication.md](communication.md)).

**Duplicate** rebuilds a v2 part from the config stored on its assignment job (flow rows, instructions, authored
questions) and pre-fills the corporate wizard.

### Input text limits

**DEV + UAT, 2026-10-16; PROD pending.** The first release has no per-field character caps on AI Interview v2
request strings in `POST /ai-interview-v2/skeleton`, `/generate-slots` and `/score-answers`. This covers flow
instructions, role and job details, evaluation parameter names/descriptions, question/context/reference text,
candidate answer text and string metadata. In particular, instructions over **4,000 characters** no longer fail
queued planning with HTTP 422, and long parameter descriptions, job descriptions or answers are accepted by
these request schemas. Planning and slot-generation prompts receive the **full job description**, rather than
only its first 6,000 characters.

Required fields, string types, nonempty required identifiers/names, allowed row/scorer types, evaluation weights,
collection/count bounds and duration validation still apply. Generated content retains the word budgets described
below; these are separate from recruiter-input character limits. No database migration or frontend change is required.

Release commits: fastapi-ai-engine **DEV `81a8a74` / UAT `aff0847`**. Verification: all **32 focused offline checks**
passed inside each deployed container, including long-text planning, slot generation and scoring; live OpenAPI
schemas showed no request-string character caps, and the three deployed source files matched their release commits.

### Planner rules (fastapi `QuestionGeneration/AIInterviewV2/skeleton.py`)
- Standard rows (subjective / single / multiple choice / coding) are code-built as **one `perQuestion` phase showing a
  `QuestionList` with answer `PerQuestion`** — the same contract as a task's question list; each question's own type
  (`text` / `single` / `multiple` / `code`) picks its surface. Scorer and question type per row are unchanged
  (`subjective`, `mcq_single`, `mcq_multiple`, `coding`). Papers planned before 2026-10-16 name the row's component
  (`TextAnswer` / `ChoiceAnswer` / `CodeAnswer`) instead; the runner treats them the same (below).
- Task rows are planned as phases (`show` pieces, one `answer`, `buttons`, `timeLimitSec`)
  from a closed vocabulary. Validator: every parameter measured; audio plays once; a task step's own answer is
  `VoiceAnswer`/`VideoAnswer` (scorer `spoken` / `translation_spoken`), `TextAnswer` (`subjective`), `CodeAnswer`
  (`coding`, with `answer.codeLanguage`, e.g. `"R"`) or `PerQuestion` (`per_question`); never a bare `ChoiceAnswer`.
- Question blocks carry `transition` (one spoken line) and **`howTo`** (2–4 sentences, interview language, how to
  attempt the row — e.g. "these questions can have more than one correct answer"). **Voice** rows carry neither: the
  interviewer starts with the question or current activity instruction. Other **task** rows' `howTo` describes the task;
  each task phase carries its own **`say`** — what the interviewer says as that step opens (never step counts). A blank `say` on any task
  phase is a validation error (passage-/audio-only steps would otherwise open in silence), so the planner retries.
- Content (`slot_content.py`) is sized to the step: the prompt states the minutes the part allows, one focused problem,
  ≤2 deliverables, ≤5 named columns; problem statements 40–120 words. Hard caps (passage 180, prompt 150, audio 200
  words) send content back to be shortened.

### Recorded activities in Voice response rows

**DEV + UAT, 2026-10-16; PROD pending.** A recruiter can choose **Voice response → Instructions** on a row
after the fixed Introduction and describe an interviewer-led activity. The instructions describe the activity;
the recruiter does not have to author each question. Supporting content and the sequence of stages are planned
once per job, then executed through the existing task runner.

- A `voice` row with nonblank instructions becomes `kind: "task", rowType: "voice"`. Voice rows without instructions
  remain live conversational blocks. The fixed first Voice row remains the **Introduction**, even when it has
  instructions: admin-node derives `isIntroduction` from the row position when building the skeleton request,
  including for jobs queued before this flag existed.
- Count is the number of **activity repetitions**, not the number of sub-steps. Set it to **1** for one activity;
  an omitted count defaults to one. The wizard may prefill a count, so check it explicitly.
- The interviewer speaks every stage's `say`, asks the generated question, and coordinates the existing passage,
  audio, instruction and question-list components. All answering stages collect recordings: `VoiceAnswer`,
  `VideoAnswer` when a filmed response is requested, or `PerQuestion` with only `voice` questions. Typed answers,
  clickable choices and code editors are rejected for these Voice activities. Content-only preparation can have
  no answer; a separate welcome/overview phase is rejected, and the block's `transition` / `howTo` are empty.
- A generated question/scenario can use an `Instruction` pointing to a `prompt` ref with empty `text`. The runner
  speaks that item's actual prompt after `say`. A voice question list advances one question at a time, speaking
  each actual question, including later questions in the list. Supporting passages and hidden/blurred prompts
  are not read by the interviewer. The current stage's instruction stays visible while the candidate answers.
- **Reading → Translation → Summary** is one supported case: show the paragraph and record reading aloud; keep it
  visible and record translation into the secondary language; blur it and record a summary from memory. There
  are three answering stages and three separate answer slots/recordings, with no extra activity introduction.
  Scenario responses and listening followed by recorded comprehension questions use the same general mechanism.
- Grading and reports retain the stage's spoken instruction and generated prompt. Translation grading retrieves
  the reference translation from the source passage shown in that stage, rather than from its separate answer
  slot; multiple passage refs are supported. Per-question recordings respect the phase's answer language.
  Reports label Voice activities as **Task**, with a transcript and playable clip for each recorded answer.
- Existing floated papers and already stored plans keep their saved flow. Create a new assessment to use the new
  planning behavior. Other row types and their answer formats are unchanged. No database migration, new gateway
  task or wizard package update is required.

UAT release commits: fastapi-ai-engine `aa21215`, admin-node `6aee9f3`, student-node `2867b2ae`,
assessment-react-v2 `afdcd4a`. DEV commits: `e2286cf`, `cf182f3`, `c020f776`, `3f0cc86`, respectively.

Release verification: 120 focused checks passed against the UAT code. The candidate app was rebuilt on UAT
with UAT configuration, with no DEV URLs in its static bundle or browser script errors in the public-page
smoke check. A live UAT skeleton request preserved the Introduction and produced three recorded-answer
stages for reading, translation and summary, with the passage blurred for the summary.

## Candidate (assessment-react-v2 `/assessment/take`)
- One `start` creates the voice session (re-used on reload / later voice blocks); the runner walks the skeleton block
  by block. Progress (`POST /students/mix-match/ai-interview-v2/:id/progress`) lets a fresh browser resume.
- No briefing screens. A step opens on the interviewer **speaking** its instruction in place (TTS, same voice): a
  questions part says its transition + how-to once; a task says its transition (if any) before its first step, then each
  step's own `say`. The step's questions / passage / answer surface — and its timer — appear when she finishes or the
  candidate presses Continue. Voice parts are not announced. Papers without `howTo`/`say` get a code-built line.
  A **proctoring warning holds all of it** (`lib/aiInterviewV2/instructionGate.ts`): the voice pauses (even if the
  warning came up while it was loading), its playback deadline stops counting, and the step — with its timer —
  opens only after the warning is acknowledged.
- **Question rendering reuses the shared exam components** (2026-10-16): a `perQuestion` phase always answers through
  `PerQuestion` (`flow.ts` `answerComponentOf`), and each question renders its stem (`.qstem`) with the same component
  Role Based / Aptitude / Behaviour / Custom use in `QuestionPanel` — `_components/exam/ChoiceOptions` (single /
  multiple, rich text, option images), `_components/exam/TextAnswer` (typed answer), `CodeAnswer`, `RecordingAnswer`;
  passages use `RichText`, listening clips `AudioPrompt`. There are no v2-only copies. Before this, a subjective row's
  `TextAnswer` rendered a bare box with **no question above it** (UAT QA, corp assessment 1c62a706).
- Task steps render by answer type; a **code step** is an editor locked to the task's language whose **Run** executes
  the program and shows its output (no test cases).
- **Every question is mandatory** (2026-10-16, `lib/aiInterviewV2/flow.ts` `canMoveOn` / `answerTargets`): any button
  that moves on (Next / Submit) stays disabled until the step is answered — on top of the planner's own
  `enabledWhen`. Applies to standard MCQ, multi-select, subjective and coding steps (whose planner buttons are
  ungated, `enabledWhen ""`) and to task steps; a list of questions on one screen needs every one answered. Answered =
  an option picked / ≥1 tick, non-blank text, code edited (untouched starter code does not count), a recording.
  There is no Skip (voice activities excepted, see below). A step with nothing to answer (read the passage, listen to the clip) is never held, and a phase
  with its own `timeLimitSec` still auto-submits whatever it has when the clock ends. Runner-only, so it applies to
  already-floated papers. Gotcha: answers live in per-step state, so a reload mid-step shows an empty answer and the
  candidate must answer that question again.
- **Voice activities run hands-free, like a voice turn** (2026-10-19, DEV 167c8ff / UAT e38fd0a; PROD pending). In a
  task block with `rowType: "voice"` (Read → Translate → Summary, listening + questions, scenarios):
  - every spoken answer — a `VoiceAnswer`/`VideoAnswer` step or a per-question `voice` question
    (`flow.ts` `isHandsFreeRecording`) — **starts recording by itself 2 s after the interviewer's line**
    (`V2_HANDS_FREE_START_SEC`, shown as "Recording begins in 0:02"). The recorder shows no Start / Stop / Re-record
    (only "Try again" after a microphone error);
  - the bar has a single **Submit response**, which stops the take and moves on. It runs the planner's own `next`
    button actions, so lock/blur still apply. As in a simple voice turn there is **no minimum length and no mandatory
    answer**: an empty or short take moves on, and the backend scores it 0 ("No answer was given");
  - the take also ends and submits itself at the step's recording limit (`maxSeconds`, recorder default 120 s) or its
    `timeLimitSec`. Both are still chosen by the planner per step from the recruiter's instructions; there is no fixed
    per-stage time;
  - a clip-only step (`AudioPlayer`, answer `None`) **plays the clip by itself, once**, and moves on when it ends. If the
    browser blocks autoplay, the play button remains. When questions follow, the step's line gets "It plays once, and
    then I'll ask you some questions about it." appended (`briefing.ts`), unless it already mentions questions;
  - per-question steps after the clip (or after any earlier step) speak **only the question**, not the step's
    "answer each question…" line.

  This is a runner-only change in `useV2Step.ts`, `RecordingAnswer` (`autoStartAfterSec` / `stopRef`, opt-in) and
  `AudioPrompt` (`autoPlay`, opt-in), so it applies to already-floated papers. Other assessment types are unchanged.
- Finishing completes the session (`complete`) and lands on the done screen; a reload submits the attempt from the
  guard screen and completes the session directly.

### Question count: a task is one question (UAT 2026-10-21; DEV + PROD pending)
The candidate intro ("YOUR ASSESSMENT · N questions") and the corp Manage panel ("Question types … Total") use the same
rule. student-node `MixMatchJourney.getSummary` counts an AI_Interview_v2 part with `candidateQuestionCount(skeleton)`
(helpers/aiInterviewV2.js), reading `stage_config.aiInterviewV2.skeleton`:
- `voice_interview` block → its `questionCount`
- `questions` block → the sum of its `questions` refs' `questionCount` (× `repeat`)
- `task` block → **1 per `repeat`**, however many steps it has (listen → recall ×6, read → translate → summarise)

Before this, it counted `COUNT(DISTINCT assessment_question_map.question_id) + max_questions`. That counted every
task sub-question **and the task's stimulus rows** (the audio script / passage are stored as question rows). Example:
UAT corp assessment 270ff468 ("check that data in the mw"): Manage panel showed 8, candidate showed 17 (now 8). Checked
against all 44 UAT papers: matches the creator's flow total on 43. The other one has a task row with count "AI decides";
the Manage panel leaves it out of the total, while the candidate count includes it as 1.
Papers without a skeleton keep the old SQL count.
**Not changed:** the in-test header "Question N of M" (assessment-react-v2 `lib/aiInterviewV2/flow.ts` `questionProgress`)
still counts every answering step (15 for 270ff468).

## Scoring (student-node `models/AIInterviewV2.js`)
Voice turns by the AI Interview scorer; Role Based questions by the Role Based pipeline; choices computed
(`choiceScore`: single = 100/0; multiple = **0 if any wrong option is picked** — so ticking every option never earns
marks — otherwise right picks ÷ correct options, e.g. 1 of 2 correct = 50; since 2026-10-15, older attempts not
re-scored); task steps
by fastapi `POST /ai-interview-v2/score-answers` (spoken → transcript + judge; translation vs reference; written;
code judged against the task in its language). One request carries every task answer of the attempt: up to **1,000 items** (was 60 until 2026-10-16, which failed scoring for a 77-answer interview on UAT), graded **24 at a time** so a long interview does not flood the LLM gateway / STT (DEV + UAT 2026-10-16, PROD pending). A judged step mapped to **several parameters** sends them to
score-answers and gets `parameterScores` (id → 0–100; a **required** schema field, so the OpenAI fallback keeps
strict json_schema and cannot drop it), so each parameter is credited with its own score (an omitted or
unknown id falls back to the step's overall score; older stored results and choice / Role Based steps keep one
score). Combined per parameter → one row in `ai_interview_scores`, verdict
bands 80/50/40. **Abandoned attempts:** the drop-off cron finalizes the v2 session (`ABANDONED`, reason `dropout`) and
scores it with the same combined scorer.

### Scores appear only after combined scoring finishes

The voice score and Role Based marks are intermediate results, not a finished v2 score. `AIInterviewV2.scoreRoleBased`
calls `Assessment.calculateRoleBasedScore` with `{ markCalculated: false }`, passed through to
`RoleBasedCalculations.storeRoleBasedScores`. Normal Role Based assessments keep the default `true`. The v2 scorer
sets `scores_calculated = true` only after `writeCombinedScore` succeeds; a scoring failure leaves it `false` so the
calculation worker can retry.

Corporate v2's shared score SQL withholds both the AI Interview and Role Based score rows for a v2 attempt until
that flag is true. The roster's AI fitness verdict and report availability follow the same rule. A completed attempt
therefore shows **Preparing Report** while scoring is running, without exposing the temporary voice-only score
(e.g. 26 followed by the combined 40). Unfinished marks do not enter score averages. After 15 minutes without a
score the existing status becomes **Report Delayed**. Only legacy `AI_Interview` retains its report fallback based on
the existence of a score row.

Released on **DEV + UAT**, runtime files verified 2026-10-16: student-node `e8455c13` / UAT `2464366f`;
corporate-node `f9576df2` / UAT `9cbd84cb`. No DB migration or frontend change is required. PROD pending.

### Parameter mapping and per-parameter scores (DEV + UAT 2026-10-21, PROD pending)

**Who maps what.** The planner LLM (`pl/interview-skeleton`) maps every Interview Flow row (or task step) to the
parameters it measures, with a weight split per row; the validator only checks ids and that every parameter is mapped
somewhere. All questions of a row share the row's mapping. Inside the voice interview, code (`apportionByWeight`)
splits the voice question budget across the voice parameters by weight and tags each turn with its parameter id.

**Voice question budget covers every voice parameter.** admin-node `withVoiceCoverage`
(`helpers/aiInterviewV2SetBuilder.js`) tops the last voice block's `questionCount` up to 1 (warm-up) + one question per
voice role parameter (`voiceParameters`: the role parameters mapped to voice rows, or all of them when none are), and
`max_questions` follows. Before this, a 2-question voice row for 3 role parameters asked one of them and the others
read "Not assessed" (UAT 57e74d08, c83ed529). Applies to sets generated after the deploy only.

**Voice scores count for role parameters.** The voice scorer (`score-final`) returns role parameters as a 0–5
`rating` with no `score`; until 2026-10-21 `scoreVoice` dropped every entry without a numeric `score`, so no v2
attempt ever got role-parameter evidence from the voice interview (0 of 41 on UAT). Now `voiceParameterScore`
reads `rating × 20`; a parameter the scorer flags `not_assessed` **or** labels `rating_label: "Not Assessed"` (its
rating is an inferred average) carries no evidence. `section_scores.aiInterviewV2.voiceVersion = 2` marks rows
combined with this rule; re-scoring an older combined row re-runs the voice scorer without writing a row
(`runScoringForAssignment({ returnReport: true })`), because the original role ratings were overwritten.

**How a parameter's score is derived** (`combineScores`, `helpers/aiInterviewV2.js`): average per row first (each row
= the mean of its questions for that parameter; a voice row = the session's voice score for it), then the weighted
mean of the rows by each row's weight for the parameter. A row's question count is not its weight (3 MCQs are one
row, not 3 votes). Overall = parameters weighted by the recruiter's weights; a parameter with no evidence is
"Not assessed" and left out. Unanswered questions score 0.

**Report shows what assessed each parameter.** Each parameter row in `parameter_scores` carries
`evidence: [{blockId, title, score, questions}]` and its `analysis` starts "Scored N/100 from: Voice interview 60;
Troubleshooting 0 (3 questions)." Each fixed (non-voice) transcript turn's `dimension` is
`<row title> — <parameter names>` with `parameters: [{id, name, score}]` (this answer's score per parameter); voice
turns already show their parameter. Corporate/institute v2 and the PDF render `dimension` unchanged.

Commits: student-node DEV `5c4b3a5a` + `feec8e7c` / UAT `3db2a3f0` + `febe0eac`; admin-node DEV `b3640d6` / UAT
`2d7b9d1`. Existing attempts keep their old scores until re-scored (`new AIInterviewV2().calculateScore(id)` in the
student container).

## Report (student-node `reportV2` → corporate-node → corporate-react-v2 drawer)
Type `AI Interview v2`, the AI Interview report shape. Fixed steps follow the voice turns; each task step carries
`answer_mode` (`recorded` → transcript + its own clip, `written`, `code` → code) and task kind (`reading`, `listening`,
`custom` shown as "Task").
Every step of one task item carries `task_id` (`<blockId>:<itemIndex>`) and `task_title`. The corp drawer's
"Candidate's Response" (`TranscriptPanel` + `_lib/transcriptItems.ts`) shows a task as **one numbered question**:
the passage or clip once, then Step 1…N, each with its answer. Turns without `task_id` (older reports) render one
per question as before. UAT 2026-10-21 (student-node cdcbfe3b, corporate-react-v2 5955c31); DEV + PROD pending.
Institute v2 is unchanged (it has the older plain AI Interview transcript).

### Speech measurements

**DEV + UAT, 2026-10-16; PROD pending.** Speech measurements cover conversational answers and
recorded fixed steps, including translation tasks. During fixed-step scoring, student-node requests
`include_delivery` from the AI engine and reuses the same downloaded recording for transcription
and delivery telemetry. The result is stored under
`section_scores.aiInterviewV2.steps[questionId:phaseId].delivery` and combined with conversational
`ai_evaluation.delivery` when building the session speech profile. Written and choice answers do
not enter spoken-word totals. A telemetry failure preserves the transcript and task grade, with
partial measurement coverage.

The report distinguishes **short pauses (0.3 ≤ gap < 0.8 seconds)** and **long pauses (gap ≥ 0.8
seconds)** from the long-pause rate per 100 words. Counts also include short answers that are too
brief for fluency scoring. English vocal fillers are measured where supported; a Tamil or other
unsupported filler count stays unavailable. `hasPartialCounts` and report-v2's `partial_coverage`
make that limitation visible. No database migration or new short-pause grading penalty is required.

Historical recordings need telemetry reprocessing to recover counts that were never stored;
reopening an old report alone cannot recover them. The reported UAT QA interview was refreshed
from its three retained recordings: **212 measured words, 9 short pauses, 1 long pause**, and **0.47
long pauses per 100 words**. All grades, scores, feedback and the verdict were preserved. Timing
coverage is now full; filler coverage remains partial because two recordings are in Tamil.

Fix commits (DEV / UAT): fastapi-ai-engine `cb2576a` / `3652e07`;
student-node `ac7093d1` / `0569e670`; assessment-react-v2 `f80eda2` / `90237f7`;
corporate-react-v2 `86bb844` / `729adac`. Both frontends were rebuilt for their own environment;
UAT bundles were checked for DEV URLs. The corporate UAT runtime also includes the subsequent
`14c3c87` verdict-label fix. The real report-v2 API and the deployed corporate renderer were checked
for separate short/long counts and rate, with no browser script errors.

### PDF download
student-node `generatePDFReport` → `generateAIInterviewV2Report` (before 2026-10-15 it threw
`Unsupported assessment type: ai_interview_v2`, so every corp v2 download / bulk zip failed). Same
`public/aiInterviewReport.html` as AI Interview, over the combined score row; the transcript ("Interview Transcript")
appends `AIInterviewV2.reportTurns` after the voice turns via helper `pdfTranscriptTurns`: a type tag (Single/Multiple
choice, Written, Coding, Reading/Listening task, Task), every option with **Picked / Correct** marks (wrong pick in red),
code with its language, passage, per-step `Scored N/100 — feedback`, and "No answer given" for an empty step. Served via
corporate-node `/candidates/report/download` (no corp-node/FE change needed). Commits: DEV 8591f221, UAT 90f39e7d.

**Answer key is withheld while the attempt is open.** `generatePDFReport` and `reportV2` are unauthenticated
student-node routes, so `AIInterviewV2.reportTurns` drops each turn's `correct` array until the attempt is closed
(`submitted = true` or status `COMPLETED` / `DROPOUT`, helper `isAttemptClosed`). Without a key the PDF shows picks
only (nothing marked Correct or red); the corp drawer reads a missing `correct` as `[]`. The route-wide auth gap itself
(all assessment types) is still open — callers include admin/institute/student/assessment React apps directly.

**PDF counts cover every step.** "Questions answered: N of M" and the not-completed banner add the fixed steps to the
voice session counters (`combinedAnswerTotals`: each fixed question = one expected question, and the steps of one
task (same `taskId`) count as one, answered once any step is (UAT 2026-10-21); if the voice expected count is unknown,
the total stays unknown). The PDF transcript still lists task steps one by one. A fixed-only attempt no longer reads 0, and the "No answers were captured" reason
is replaced when fixed steps were answered. A recorded step whose clip was stored but has no transcript carries
`recording_submitted: true` (also in `reportV2`) and prints "Recorded response submitted; transcript unavailable."
instead of "No answer given". Commits: DEV c4838165, UAT dc7f8a55 (2026-10-15).

## QA fixes (Jershini, 2026-10-16 → DEV + UAT 2026-10-19; PROD pending)

| # | Behaviour now | Where (DEV / UAT) |
|---|---|---|
| Report delay | A completed AI Interview / Complete AI Interview score is released as soon as the proctoring report exists and reading analysis is not pending/running (`helpers/scoreRelease.js`). Before, AI interviews never closed their proctoring log, so every score waited for the 900 s sweeper (~16 min → "Report Delayed"). The 15-min timeout stays as a backstop. | student-node f6484128 / dccf51da |
| Answer language | Every answering step's spoken `say` names the answer language; in a two-language interview a step that does not gets "Please answer in X." appended in code. Summary defaults to the primary language unless the recruiter's instructions say otherwise. | fastapi 58ac82e / d7bcb2e |
| Reading stage scored | A reading stage in any task row (e.g. Read → Translate → Summary) is a **recorded read-aloud** step (`scorer=spoken`), graded for accuracy against the passage and fluency. A recruiter who wants silent reading must say "read silently". | fastapi 58ac82e / d7bcb2e |
| Executive summary | `combinedSummary` (helpers/aiInterviewV2.js) never names one parameter as both strongest and weakest: one assessed parameter → "…based on X (N), the only parameter this interview assessed"; ties → "Every assessed parameter scored N"; lists not-assessed parameters. Applies when a score is written (old rows keep old text). | student-node e780158a / efa84235 |
| Min recording | Recorded steps outside voice activities need ≥ 5 s (voice activities have no minimum since 2026-10-19, see Candidate); the recorder enforces it ("Speak for at least 0:05") and always offers "Record again" for a short take (before: stop at 0:01 → Submit disabled until the timer ran out). | assessment-react-v2 1fa0533 / e03a615 |
| Progress counter | Header counts **questions** (voice turns, per-question stops, answering task steps), 1-based — not blocks. | assessment-react-v2 1fa0533 / e03a615 |
| Candidate label | Candidate pages and invite emails say **"Complete AI Interview"** (type value unchanged). Reminder emails for multi-part sittings still say "AI Interview v2". | runner 1fa0533 / e03a615, admin-node e782e23 / a0aa8cb |
| Candidate instructions | Send-step "Additional Instructions" are written to the part's instructions row at float (async Role Based too) and shown as bullets on the candidate instructions screen. The settings-panel **Additional Inclusions → Additional instructions** text is **not** shown as bullets (it was 10-19 → 10-21, reverted); it becomes the spoken **opening note** below. | admin-node e782e23 / a0aa8cb; revert student-node 57f94474 / f69e7f14 |
| Opening note (2026-10-21) | admin-node sends the panel text to the planner as `additionalInstructions`; the same `pl/interview-skeleton` call returns a plan-level **`openingNote`**: ≤2 sentences / 240 chars, primary language, only what is meant for the candidate (interviewer directives like "ASK whether willing to work in Chennai" dropped), `""` when nothing applies or no text. student-node passes it in the runner payload; on a fresh attempt the runner **speaks it in the interviewer voice with a caption before the first block** (Introduction included), via the step-instruction component (proctoring gate applies, Continue skips). The AI interviewer still gets the full text as guidance. New floats only — older plans have no note. | fastapi b7f898a / 2ef8dcf, admin-node ff6deaa / 9a0a3a4, student-node f925005c / 20152fea, assessment-react-v2 6992253 / 1b272e5 |
| Manage drawer | admin-node `getAssessmentConfiguration` has an AI_Interview_v2 branch reading the job's stored config (role, flow rows with instructions, parameters, languages, voice, extras; read-only). | admin-node d588c85 / 7fb758c, corporate-react-v2 698ab2a / 7a7b0c4 |
| Duplicate count | Duplicate pre-fill derives Question count from the flow rows (`flowTotals`), not the wizard default 8. | corporate-react-v2 698ab2a / 7a7b0c4 |
| Scroll bounce | Corp detail page KPI row and institute student-report drawer stat grid stay collapsed while there is nothing left to scroll (a short roster could never reach its last row); wheel-up at top restores them. | corporate-react-v2 bcd20c5 / eaa692d, institute-react-v2 43b4279 / 93a7fde |

Already-floated papers keep their saved plan (silent reading, no language in `say`) — float a new one to see those two.

## Code runner
R answers can use **ggplot2, dplyr, tidyr, readr** (Debian `r-cran-*` in `student-node/code-runner/Dockerfile`).
DEV `code-runner:r-tidyverse`, UAT `pl-code-runner:c4d07afe`; previous containers kept stopped as
`code-runner-prev-tidyverse` for rollback.

## Commits (UAT branch heads, 2026-10-14)
fastapi-ai-engine 68c30d5 · admin-node d1b21b8 · student-node 0b8c7d04 · corporate-node b94c6206 ·
assessment-react-v2 175aa5f (mandatory answers, 10-16; DEV 1fb7ea7) · corporate-react-v2 bb86eff · admin-react-v2 e440dd5 · admin-react fb5c2f07 ·
design-system wizard sources (local only, push not permitted): `uat/aiv2-0.1.2`, `uat/aiv2-0.1.12`.
