# Complete AI Interview (AI_Interview_v2)

> **State (2026-10-14):** LIVE on **DEV + UAT**. **PROD pending** (needs the DB script, the three gateway tasks,
> and every service below). Corporate floats only (the report lives in the corporate portal, not the institute one).

AI Interview and Role Based merged into one assessment: the recruiter builds an **Interview Flow** of ordered rows
(voice, subjective, single choice, multiple choice, coding, reading task, listening task, custom task), an LLM plans
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

1. **Wizard** (corporate-react-v2 wizard `0.1.2-bugfix.16` DEV / `0.1.2-bugfix.16-uat` UAT; admin-react-v2 wizard
   `0.1.16-custom.8` DEV / `0.1.12-custom.6` UAT). Role, skills, JD, evaluation parameters (Communication fixed 20%),
   languages, voice, and the Interview Flow rows. Reading / Listening / Custom rows **require instructions** (they
   describe the task). Single/multiple choice rows may carry hand-written questions. Count blank = "Auto".
2. **Float route** sends `assessmentType: "AI_Interview_v2"` with `interviewConfig.flow`.
3. **admin-node** `AIInterviewV2AssignmentService` **synchronously** calls fastapi `POST /ai-interview-v2/skeleton`
   (the creator waits for this, ~10–60 s; up to 3 LLM attempts with the validator's errors fed back). A plan still
   invalid after 3 attempts refuses the float (nothing saved). Then the Role Based async assign queues the job and the
   creator is told invites follow paper generation.
4. **Paper generation** (assignment worker, set generator `ai-interview-v2-generate`): Role Based questions for
   subjective / single choice / coding rows, fastapi `POST /ai-interview-v2/generate-slots` for task content
   (passages, TTS audio, questions), authored questions as written. Every **answering step of a task gets its own
   answer row** (`content[block].items[n]["@answer:<phaseId>"]`), so a task may have any number of steps.
5. Candidates are assigned and invited when the paper exists.

**Duplicate** rebuilds a v2 part from the config stored on its assignment job (flow rows, instructions, authored
questions) and pre-fills the corporate wizard.

### Planner rules (fastapi `QuestionGeneration/AIInterviewV2/skeleton.py`)
- Standard rows are code-built; task rows are planned as phases (`show` pieces, one `answer`, `buttons`, `timeLimitSec`)
  from a closed vocabulary. Validator: every parameter measured; audio plays once; a task step's own answer is
  `VoiceAnswer`/`VideoAnswer` (scorer `spoken` / `translation_spoken`), `TextAnswer` (`subjective`), `CodeAnswer`
  (`coding`, with `answer.codeLanguage`, e.g. `"R"`) or `PerQuestion` (`per_question`); never a bare `ChoiceAnswer`.
- Every block carries `transition` (one spoken line) and **`howTo`** (2–4 sentences, interview language, how to attempt
  the row — e.g. "these questions can have more than one correct answer").
- Content (`slot_content.py`) is sized to the step: the prompt states the minutes the part allows, one focused problem,
  ≤2 deliverables, ≤5 named columns; problem statements 40–120 words. Hard caps (passage 180, prompt 150, audio 200
  words) send content back to be shortened.

## Candidate (assessment-react-v2 `/assessment/take`)
- One `start` creates the voice session (re-used on reload / later voice blocks); the runner walks the skeleton block
  by block. Progress (`POST /students/mix-match/ai-interview-v2/:id/progress`) lets a fresh browser resume.
- On every change of question type the interviewer **speaks** the transition + how-to (TTS, same voice) and shows it;
  the block opens when speech ends or on Continue. Papers without `howTo` get a code-built description.
- Task steps render by answer type; a **code step** is an editor locked to the task's language whose **Run** executes
  the program and shows its output (no test cases). An "answer required" button never blocks a step with nothing to
  answer.
- Finishing completes the session (`complete`) and lands on the done screen; a reload submits the attempt from the
  guard screen and completes the session directly.

## Scoring (student-node `models/AIInterviewV2.js`)
Voice turns by the AI Interview scorer; Role Based questions by the Role Based pipeline; choices computed; task steps
by fastapi `POST /ai-interview-v2/score-answers` (spoken → transcript + judge; translation vs reference; written;
code judged against the task in its language). Combined per parameter → one row in `ai_interview_scores`, verdict
bands 80/50/40. **Abandoned attempts:** the drop-off cron finalizes the v2 session (`ABANDONED`, reason `dropout`) and
scores it with the same combined scorer.

## Report (student-node `reportV2` → corporate-node → corporate-react-v2 drawer)
Type `AI Interview v2`, the AI Interview report shape. Fixed steps follow the voice turns; each task step carries
`answer_mode` (`recorded` → transcript + its own clip, `written`, `code` → code) and task kind (`reading`, `listening`,
`custom` shown as "Task").

## Code runner
R answers can use **ggplot2, dplyr, tidyr, readr** (Debian `r-cran-*` in `student-node/code-runner/Dockerfile`).
DEV `code-runner:r-tidyverse`, UAT `pl-code-runner:c4d07afe`; previous containers kept stopped as
`code-runner-prev-tidyverse` for rollback.

## Commits (UAT branch heads, 2026-10-14)
fastapi-ai-engine 3376970 · admin-node ac3bc28 · student-node c4d07afe · corporate-node b94c6206 ·
assessment-react-v2 565f1fe · corporate-react-v2 bb86eff · admin-react-v2 e440dd5 · admin-react fb5c2f07 ·
design-system wizard sources (local only, push not permitted): `uat/aiv2-0.1.2`, `uat/aiv2-0.1.12`.
