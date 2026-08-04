# AI Interview Assessment

> AI Interview is a **real-time, adaptive interview** assessment type where an AI interviewer dynamically generates questions based on the candidate's previous answers, resume context, and job description. It supports multiple interview round types (technical, behavioral, situational, case study) and provides automated shortlisting with hire/no-hire recommendations.

---

## Overview

| Property | Value |
|---|---|
| **Assessment Type** | `AI_Interview` |
| **Domain** | `AI_Interview` (short form: `AI_INT`) |
| **Total Duration** | Configurable (default: 60 minutes) |
| **Question Count** | Configurable (default: 5–15 questions) |
| **Question Types** | Technical, Behavioral, Situational, Case Study |
| **Question Generation** | AI-powered, adaptive (Gemini 2.5 Pro + Groq Llama 3.3 70B fallback) |
| **Scoring** | AI-evaluated per-response: Technical Accuracy (40%), Depth (25%), Communication (20%), Problem Solving (15%) |
| **Shortlisting** | Automated: `strong_hire`, `hire`, `maybe`, `no_hire` |
| **Follow-ups** | AI generates probing follow-up questions when responses need deeper exploration |
| **Modality** | **Voice conversation** — AI speaks each question (TTS), candidate replies by voice (STT). Text transcripts are stored alongside. |
| **TTS (interviewer voice)** | **ElevenLabs Flash v2.5** (`eleven_flash_v2_5`) — voice **Payal** (Indian female, Hindi/Indian-English, conversational; voice ID `CpLFIATEbkaZdJr01erZ`). Falls back to **Deepgram Aura-2 `aura-2-thalia-en`** (US English female) if the ElevenLabs key/call fails. Overridable via `ELEVENLABS_VOICE_ID` / `ELEVENLABS_MODEL_ID` env vars on the FastAPI container. |
| **STT (candidate voice)** | **Deepgram `nova-3`** — REST upload (`POST /ai-interview/stt`) plus a WebSocket bridge (`/ai-interview/stt-stream`) that proxies live mic audio to Deepgram and forwards interim + final transcripts back to the browser. |
| **VAD** | Browser-side voice-activity detection auto-submits the answer after ~1.8 s of silence (`Assessment-React/.../AIInterview/interview.js`). |

---

## Assessment Structure

Unlike static assessments, AI Interview is a **conversation** — questions are generated one-at-a-time based on the candidate's performance in prior turns.

| Phase | Description |
|-------|-------------|
| **Initial Questions** | 3–5 questions generated from job role, skills, seniority, and JD |
| **Adaptive Questions** | Next questions adapt based on evaluation scores — harder if candidate performs well, easier if struggling |
| **Follow-ups** | When a response needs probing, a follow-up question targets the weak area |
| **Completion** | After all questions answered (or time expires), a comprehensive report is generated |

### Scoring per Response

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Technical Accuracy | 40% | Correctness of concepts, methods, facts |
| Depth of Knowledge | 25% | Level of detail, nuance, edge-case awareness |
| Communication Clarity | 20% | Structure, articulation, explanation quality |
| Problem Solving | 15% | Analytical approach, reasoning, alternatives |

### Final Recommendation

Verdict stored in `ai_interview_scores.ai_recommendation` as one of four labels
(not `strong_hire`/`hire`/`maybe`/`no_hire` — that enum was never shipped):

| Verdict | `overall_score` band |
|---|---|
| `Strong Fit` | ≥ 80 |
| `Fit` | 50–79 |
| `Borderline` | 35–49 |
| `Not Fit` | < 35 |

Exception: a **non-engagement** transcript (see below) always forces `Not Fit`
regardless of the numeric band. See the "score-final" section further down for
the full mechanics — as of 2026-07-16 both `overall_score` and `verdict` are
**recomputed deterministically in code** from the LLM's per-parameter ratings,
not taken from the model's own numbers.

### Why these bands — rationale

**These are not market benchmarks or industry percentiles.** If a client asks
"is 50 the industry threshold?", the honest and stronger answer is: it is a
defined point on our seniority-relative rating scale, and it derives as follows.

**The identity.** `overall_score` is a unit change on the 0–5 parameter ratings,
nothing more:

```
score = Σ(wᵢ · (rᵢ/5) · 100) / Σwᵢ  =  20 · r̄        (r̄ = weight-weighted mean rating)
```

So every band boundary is really a **mean-rating** threshold, readable in the
rating scale's own vocabulary (`Excellent 5 / Strong 4 / Adequate 3 / Concern 2 /
Weak 1 / No Response 0`):

| Verdict | Score | Mean rating r̄ | Reads as |
|---|---|---|---|
| Strong Fit | ≥ 80 | ≥ 4.00 | `Strong` or better on every weighted dimension |
| Fit | 50–79 | 2.50 – 3.99 | from halfway `Concern`→`Adequate` up to nearly all `Strong` |
| Borderline | 35–49 | 1.75 – 2.49 | around `Concern` — gaps worth probing |
| Not Fit | < 35 | < 1.75 | below `Weak`-to-`Concern` on average |

Useful anchors: **all-`Adequate` = 60** (mid-Fit), all-`Concern` = 40
(Borderline), all-`Weak` = 20 (Not Fit), all-`Strong` = 80 (Strong Fit floor).

**Core principle: the bands are absolute; seniority-relativity is injected at the
RATING step, not the band step.** The rating scale is defined relative to the
role — `3 Adequate` is literally *"meets the bar **for the seniority**"*. So
`r̄ = 3.0 → 60` means "meets the bar for this role" whether the role is Fresher
or Lead; the absolute difficulty differs, the score's meaning does not. This is
why there is **one** band table rather than a table per seniority — moving the
bands per seniority would double-count the relaxation that the rating
calibration already applies.

**Fit is deliberately wide, and is the relaxed band for lower-tier roles.** The
`SCORING CALIBRATION (FRESHER / ENTRY-LEVEL)` block (fires for seniority
`Fresher` and `Junior`) instructs that an engaged candidate who articulates
clearly and shows foundational understanding *"should score Adequate (3) or
above"* → 60 → mid-Fit. So for lower-tier roles **Fit ≈ "engaged, coherent,
foundations present"**, which is the correct signal at that tier: for volume
campus / entry hiring the decision needed is *"worth a human conversation?"*,
not a fine-grained ranking. Narrowing Fit would push trainable freshers into
Borderline — a false negative, which is the expensive error when the pool is
large and training is provided. At `Mid` / `Senior` / `Lead` the same band is
**not** relaxed: no leniency block applies and "meets the bar" is a much higher
absolute standard, so identical 60 reflects a far stronger candidate.

**Per-band justification:**
- **≥ 80 Strong Fit** — a fast-track signal that must survive a hiring manager's
  challenge, so it is deliberately strict: `Strong` across the board, and a
  single `Adequate` must be paid for with an `Excellent` elsewhere.
- **50–79 Fit** — proceed to a human round. The floor sits *below* the stated
  bar (r̄ 2.5) on purpose: the AI interview is a **screening** instrument, not
  the hiring decision. Its job is to protect the human interviewer's time, so it
  optimises **recall over precision** at this gate.
- **35–49 Borderline** — `Concern` territory; flagged for a human to overrule
  rather than auto-rejected, because a screening tool should not silently discard
  candidates whose weakness may be an artifact (nerves, audio quality, language).
- **< 35 Not Fit** — in practice reached mainly via the **non-engagement caps**
  (10 / 25), not by the rating arithmetic: r̄ < 1.75 requires mostly `Weak`/`No
  Response`. Honest description: Not Fit is predominantly a *non-participation*
  verdict, not a *low-competence* one.

**On the uneven widths** (in rating units: Strong Fit 1.0, Fit 1.5, Borderline
0.75, Not Fit 1.75) — precision is concentrated where the action changes. The top
band needs confidence, so it is narrow and strict. Everyone inside Fit gets the
same action (human interview), so width costs nothing there. The bottom is wide
but rarely reached by degrees because non-engagement dominates it. Fit's width is
only a defect if `Fit` is expected to **rank**; it is correct if `Fit` is a
**gate**, which is what it is. Where senior hiring needs finer discrimination,
use the numeric score and the per-parameter ratings (both already on the report)
rather than adding labels or per-seniority bands.

**Known caveat — not outcome-validated.** No correlation has been measured
against downstream outcomes (shortlisted / progressed / offered / on-job
performance). The bands are internally consistent with the rating scale, which is
a different and weaker claim than being predictive. The cheapest way to upgrade
this is retrospective: join PROD `ai_interview_scores` to whatever downstream
outcome signal exists and check whether the bands actually separate the groups.

**Provenance (for the record).** The four labels shipped 2026-05-18 (`618e2dc`)
with **no numeric bands** — the LLM picked a label freely. The numbers arrived as
a bug fix: `f12c454` (2026-05-30) added `<35` and `<50` as a downward-only clamp
because Gemini was labelling near-zero scores "Borderline"; `8a8af35`
(2026-06-02) added `80+` to complete the bucket table. The rating-scale alignment
documented above was recognised after the fact, not designed up front — it holds,
but it was not the original motivation.

---

## End-to-End Flow

1. **Admin assigns AI Interview**: Specifies job role, skills, seniority, industry domain, optional JD, interview duration, follow-up enabled
2. Backend creates `AIInterviewConfig` linked to `AssessmentSet`, assigns students via standard flow
3. Initial questions generated via FastAPI `/ai-interview/generate-questions`
4. **Student starts interview**: Creates `AIInterviewSession`, marks assignment as INPROGRESS
5. Student receives first question, submits text response
6. Response evaluated via FastAPI `/ai-interview/evaluate-response` → scores + feedback stored in `AIInterviewInteraction`
7. If evaluation says `needsFollowUp`, a follow-up question is generated via `/ai-interview/generate-follow-up`
8. Otherwise, next adaptive question generated via `/ai-interview/generate-next-question` based on full conversation history
9. Loop continues until all questions answered or time runs out
10. **Student completes interview**: Final report generated via `/ai-interview/generate-report`
11. `AIInterviewScore` record created with overall + category scores + recommendation
12. Assignment status updated to COMPLETED

---

## Current Orchestration Behavior (authoritative — student-node `aiInterviewHandler.js`)

The live interview is driven by `student-node` (`app/handlers/aiInterviewHandler.js`), not by per-response branching in FastAPI. Key rules as of 2026-06-16:

- **Parameter-driven progression.** The admin's evaluation parameters are probed round-robin (`nextParameter` picks the least-covered one). The interview ends on: all parameters covered, time up, the question cap, or trailing refusals (disengagement).
- **Admin-configurable question count (2026-07-17).** `ai_interview_config.max_questions` (integer, default 8, DB migration `Assessment OTP Invite/20260717T142616Z__ai_interview_max_questions.sql`) — admin sets the total question budget (incl. intro) on the create form, range **8–15**, default 8. Fixes: previously the total was hardcoded at `MAX_TOTAL_QUESTIONS = 8` AND further gated by `paramCount * QUESTIONS_PER_PARAM(2) + 1`, so e.g. a 3-param config capped at 7 regardless, and admins who listed several questions in "Question guidance" saw only ~5 actually asked (intro + follow-ups ate the rest of the 8-slot budget). `resolveQuestionBudget(config, paramList)` in `student-node`/`student-node-calcq`'s `aiInterviewHandler.js` now: clamps `maxQuestions` to `[8,15]`; scales `questionsPerParam = max(2, ceil((maxQuestions-1)/paramCount))` so the round-robin has enough slots to actually reach the cap before `isInterviewComplete` fires early; sets `totalExpected = maxQuestions`. Threaded through `nextParameter`/`isInterviewComplete`/`sectionProgress` (now take `questionsPerParam`/`totalExpected` params) and every call site: `startSession`, the reframe path, `submitTurn`, `completeSession`, the scoring cron (`runScoringForAssignment`). `admin-node` persists `maxQuestions` (clamped) on all 3 config-insert paths (sync/async assign, `saveDefinition`) + `getDefinition`. `admin-react`'s `CreateAIInterview.js` has a new "Number of questions" field (8–15, default 8) beside Max duration, plus a hint on the Question-guidance box ("up to 12 questions — extras may not all be asked", since intro+follow-ups also consume the budget). `Assessment-React`'s "Question X of Y" top-bar pill now reads `progress.totalExpected` (falls back to the section sum, then 8) instead of a hardcoded `min(8, …)`. **Old configs** (no `max_questions` row, or NULL) default to 8 — identical behavior to before this change. **`student-node-calcq`** is a **git worktree of the `student-node` repo** on the divergent `feat/calculation-queue` branch (same remote, same UAT branch) — not a separate deployed service; mirrored the fix there for whenever that branch lands, but nothing to redeploy for it today.

**Follow-up (2026-07-17): follow-ups were still crowding out admin questions.** Real UAT case — `max_questions=12`, 10 explicit questions in `question_guidance`, only 8 got asked. Cause: `resolveQuestionBudget` sized the total correctly, but the depth-follow-up decision (`wantFollowup` in `submitTurn`) had no awareness of how many admin questions needed a slot — 3 of the 12 turns went to follow-up drill-ins (+1 intro), leaving only 8 for the 10 questions. Fix: `countGuidanceQuestions(question_guidance)` (lines ending in "?") + a follow-up budget — `followupBudget = max(0, totalExpected - 1 - adminQuestionCount)`; `wantFollowup` now also requires `followupsSoFar < followupBudget`. With 10 questions in a 12 budget that's 1 follow-up max, so all 10 fit. Also strengthened the FastAPI `question_guidance_block`: when any admin question is still unasked, the model should ask the next unasked one instead of inventing a new question (only invent once all are covered). Applied to `student-node` + the `student-node-calcq` worktree + `fastapi-ai-engine`. **Still probabilistic** (LLM picks *which* unasked question, not code) but the slot math now guarantees the room exists. DEV+UAT live.

**Follow-up (2026-07-18): question_guidance questions now served DETERMINISTICALLY (the prompt-only approach was abandoned).** Real UAT case that forced this — Customer Support / Junior, `max_questions=12`, admin wrote a **structured question bank** in `question_guidance` (6 sections, each `#N — title` / `Q: <primary>` / `Adjacent: <variants>`), and the LLM asked **0 of the 6** primary questions — it invented its own scenarios and self-tagged 7 turns as follow-ups (`isFollowUp: wantFollowup || !!nextQ.is_followup` — the LLM's own `is_followup`, which the follow-up-budget doesn't control). Root lesson: **no amount of prompt tuning reliably makes the LLM ask the admin's questions, especially for non-flat guidance.** New approach in `student-node/submitTurn`: `extractPriorityQuestions(question_guidance)` parses the primaries out of the box — `Q:`-marked lines (multi-line joins until a blank/marker; drops `#` headers, `Adjacent:` labels + sub-bullets, `If experienced/fresher` branches, parentheticals) when `Q:` markers exist, else every question-shaped line (flat-list case). These merge with the explicit `sample_questions` column into one `priorityQuestions` list, and each is **served deterministically before any AI question** — routed through FastAPI's new **`must_ask_question` generate-question mode** so it's faithfully translated to the interview language + lightly smoothed for spoken flow (verbatim would drop an English question into a Hindi interview), preserving the exact concept/term (rotational shifts stays shifts, named brands/scenarios stay), never merged/generalised/turned into a follow-up. Coverage is tracked by a stable `priorityKey` (normalised original) stamped in each served turn's `questionMetadata` — needed because the *asked* text is adapted and can't string-match the original. Drain-before-complete and follow-up suppression both key off `nextPriority` (a pending admin question always beats a drill-in). Files: `student-node`/`student-node-calcq` `aiInterviewHandler.js` (`extractPriorityQuestions`, priority serving, `priorityKey`), `fastapi-ai-engine/routers/ai_interview.py` (`must_ask_question` request field + branch). **`student-node-calcq` NOT updated** for this one (older divergent branch without the priority-serving path; not deployed) — noted for whenever that branch lands. This finally makes admin questions a *guarantee* (they will be asked, in order, all of them) rather than an LLM request. DEV+UAT live.

**Follow-up (2026-07-18): two duplication bugs on top of the deterministic serving.** UAT test runs surfaced: (1) an admin priority question that is itself a plain "tell me about yourself" got asked **twice in a row** — the mandatory warmup already asks for a self-intro, then priority Q1 repeated it. Fix: `extractPriorityQuestions` drops a **bare** self-intro via `isPlainSelfIntro` (short, self-intro-shaped, no extra topic — a self-intro carrying extra content like "…and your last project" is kept). (2) An AI-generated **fill/wrap-up** question re-asked an already-asked one (e.g. earbuds/smartwatch as the *final* question) — the LLM's own anti-repeat slipped on the wrap-up turn. Fix: a code-level near-duplicate guard in `submitTurn` — `questionSimilarity` (Jaccard of stop-word-filtered content words) `>= 0.6` vs every asked question; on a hit for a **fresh** (non-follow-up, non-priority) turn, regenerate ONCE with FastAPI's new **`avoid_question`** field set (steers the model hard off the repeated question). Follow-ups and served priority questions are exempt (they legitimately share wording). Also strengthened the FastAPI FINAL-QUESTION wrap-up directive to forbid re-asking an earlier question. Files: `student-node/aiInterviewHandler.js` (`isPlainSelfIntro`, `questionSimilarity`/`isNearDuplicate`, retry), `fastapi-ai-engine/routers/ai_interview.py` (`avoid_question` field + `avoid_block` + wrap-up anti-repeat). Threshold 0.6 catches near-verbatim repeats (the actual bug) without false-positiving distinct questions (validated: earbuds-repeat = 1.00, unrelated pairs ≤ 0.14). DEV+UAT live.

**Follow-up (2026-07-17): "Question X of Y" flashed a wrong count on load.** `Assessment-React`'s progress state starts as `DEFAULT_PROGRESS` (3 placeholder sections × `total:2` = 6) until `startSession`'s real response replaces it — the pill briefly showed e.g. "1 of 6" for ~1-2s regardless of the actual `max_questions`, before snapping to the correct total. Fixed by hiding the pill entirely (`return null`) while `progress === DEFAULT_PROGRESS` (referential check — `setProgress` always replaces it with a new object, never reuses the placeholder), and again if `totalQuestions` still resolves to 0/falsy. `interview.js`. DEV+UAT live.

- **Depth follow-ups (one per parameter).** After each answer, `submitTurn` decides whether to probe the **same** parameter again instead of moving on. It asks a single follow-up when the answer **lacks depth** — a cheap deterministic word-count heuristic (`lacksDepth`, `< 25` words, refusals excluded — no extra LLM call). Guard rails: only on a real parameter (not the intro), **never chains** (the previous turn must not itself be a follow-up → at most one follow-up per parameter), and it is skipped if spending the turn would stop an as-yet-untouched parameter from getting at least one question within the 8-question budget. When triggered, it sends `force_followup: true` to `/ai-interview/generate-question`, which mandates a follow-up that drills into the candidate's previous answer and tags the response `is_followup`.

- **Steering acknowledgement on bad / off-topic answers (human flow).** When the candidate's last answer did NOT engage with the question (off-topic, irrelevant, a non-answer, or a refusal), the interviewer opens the next turn with ONE short, warm steering sentence ("Got it — let's bring it back to your experience with…") *then* asks the next question — instead of barreling straight into it. When the answer engaged normally, no acknowledgement is added. Implemented (2026-06-25) by: (a) student-node `submitTurn` computing `lastAnswerSignal` from the existing `isRefusal`/`lacksDepth` heuristics (`"refusal"` | `"shallow"` | `null`) and passing it as `last_answer_signal` to `/ai-interview/generate-question`; (b) FastAPI adding an `ACKNOWLEDGEMENT` directive to the generate-question prompt that, when `force_followup` is false, tells the model to add the steering acknowledgement for a disengaged last answer (off-topic relevance itself is judged by the LLM from history — no extra call). The two behaviours are mutually exclusive: a refusal already disables `wantFollowup` (so `force_followup` is false and the acknowledgement fires), while a shallow-but-on-topic answer sets `force_followup: true` (drill-in follow-up, no steering acknowledgement — it would double up with the follow-up that already references their answer). The whole spoken turn (acknowledgement + question) is the `question` field returned and TTS'd to the candidate.

- **Interview language — Hinglish is a code-mixed MODE, not a language name (fixed 2026-07-30).** The admin picks "AI speaks in" / "Candidate responds in" on the create form (`admin-react` `CreateAIInterview.js` + `AssessmentSelect.js`), stored as `ai_interview_config.stage_config.{language,responderLanguage}` and passed verbatim by student-node (`config.stageConfig?.language || "English"`) into FastAPI's `generate-question` as `language`. **Bug:** the string "Hinglish" was interpolated into the same single-language template every other language uses — *"Generate the ENTIRE thing in {language}. If {language} is not English, do not switch to English"* — and the **greeting** prompt was worse: *"do not mix in English words except the role title"*. Read literally ("Hinglish is not English → suppress English"), Gemini answered in **pure Devanagari Hindi**. Worse, it **locked in for the whole interview**: `prior_turns` + `asked_questions` are fed back into every later prompt, so whatever script turn 1 landed in became the style anchor. UAT evidence — every sampled Hinglish opening greeting was Devanagari; where turn 1 came out Devanagari **54%** of later turns stayed Devanagari vs **26%** where it came out Roman; session `…122862` ran start-to-finish in pure Hindi (`ठीक है, Vedant, आपने बताया कि…`), even translating work vocabulary (`कस्टमर`, `प्रोडक्ट`, `पॉलिसी`). **This was never a config/TTS problem** — `stage_config` stored `Hinglish` correctly, Sarvam STT was on `translit`, and ElevenLabs `eleven_flash_v2_5` is multilingual; it was purely the prompt, and Devanagari text is what made the TTS voice *sound* pure Hindi. **Fix (`ai_interview.py`, prompt-only — no extra LLM call, no latency cost):** `_language_rules(language)` gives Hinglish its own block — explicit ~50/50 mix with **Hindi carrying sentence structure/connectives and English keeping work/technical/product vocabulary as-is** (never `ग्राहक`/`grahak` for "customer"), plus a hard **Latin/Roman-script-only, never Devanagari** rule with good/bad examples; every other language keeps the original instruction (+ a proper-noun/role-title exception). Applied at **all four** generation sites — greeting (`is_warmup`), main probing, `is_reframe`, `must_ask_question`. Two supporting pieces: a line in the probing prompt stating the language instruction **overrides the conversation history** ("if earlier turns drifted into a different script, correct back — do NOT copy their style"), which breaks the turn-1 lock-in mid-interview; and `_language_reminder(language)`, a one-line restatement injected **immediately before the JSON spec** — the language block sits far from the end of these prompts (style rules, history and the 9 critical rules all follow it) and single Devanagari words still slipped through without it. Verified: greeting 5/5 Devanagari → 0/5; a deliberately pure-Devanagari history 5/5 pure Hindi → 0/5 (recovers mid-interview); 3 full 6-turn simulations = zero Devanagari; Hindi/Tamil/English output unchanged. A regenerate-on-Devanagari retry was **deliberately rejected** — it would double latency on a miss and the prompt fix alone was clean. DEV+UAT live 2026-07-30 (`0eb9f5a`); PROD pending. **Known gotcha unrelated to this fix:** the newer create path writes `stage_config = {}` on some rows (DEV's 8 most recent configs) — language selection lost, so those interviews silently fall back to English.
**Follow-up (2026-08-03): the mix was Hindi GRAMMAR with English nouns dropped in — fixed by switching at clause level.** Client feedback after the above shipped: *"1 English phrase then almost everything is in pure Hindi"*. Correct, and the MIX rule from that fix caused it — *"Hindi carries the sentence structure and connectives; English keeps the work, technical and product vocabulary as-is"* literally instructs a Hindi sentence with English nouns embedded (`"Aap customer ko product features kaise explain karte hain?"` — every verb, connective and clause Hindi). That is Hindi with loanwords, **not** code-mixing: real Hinglish alternates WHOLE CLAUSES between the two languages. Three prompt-only changes (`ai_interview.py`, same single Gemini Flash call, no retry, latency unchanged at 1.87s → 1.68s over 8 runs): (1) the **MIX rule now demands clause-level switching** — at least one run of 4+ consecutive English words forming a real clause AND a real Hindi clause, switched at a natural boundary (comma, dash, sentence break); examples replaced with clause-alternating ones (`"Tell me about a time when a customer was really upset — aapne us situation ko kaise handle kiya?"`) and the noun-embedding pattern added as an explicit BAD example. (2) The **warmup greeting gets `_greeting_language_example()`** — the opener ran markedly more Hindi than the body and anchors every later turn, and the cause was the STYLE block's "warm and welcoming", which reliably produced a pure-Hindi warmth phrase (`"Bahut achha laga aapse milkar"`) before the question even began. **Three** worked examples, not one: a single example fixed the blend but collapsed the phrasing (11 of 12 sampled greetings opened with the identical clause). (3) **`_language_reminder()` now restates the clause rule** alongside the script rule — these prompts put style rules, conversation history and the 9 critical rules AFTER the language block, so its rules lose to whatever sits nearer the end (the same reason stray Devanagari needed a trailing reminder). With the clause rule stated only at the top the body ignored it (real English clause in 2 of 8 turns) while the greeting, whose example sits close to the end of its own prompt, hit 10 of 10. **Measured by English RUN LENGTH, not a word ratio** — a ratio counts grammatical glue and cannot distinguish "Hindi sentence with English nouns" from "alternating clauses", which is exactly the defect reported. Greeting: real English clause **5/10 → 10/10**, median longest English run **4 → 7** words. Body: **4/24 → 15/24**, median run **3 → 4-5**. **The body number OVERSTATES the gain** — the measure counts `"product features explain"` as an English run, but that `explain` is an English verb inside Hindi grammar, not a clause switch; reading the samples, the greeting is properly fixed and visibly alternates clauses while the body is only partially there (~2 in 3 live samples switch properly, the rest revert to noun-embedding). The banned pure-Hindi warmth line also still surfaces occasionally (0/10 pre-deploy, 1/3 in a live UAT sample) — prompt-adherence limits, not bugs. Non-Hinglish prompts are **byte-identical** (all three helpers return `""` for every other language; verified English/Hindi/Tamil). DEV+UAT live 2026-08-03 (`cfad015`); PROD pending. **Do not attempt the remaining body work with another prompt pass** — see the failed attempt below.

**Follow-up (2026-08-03): Romanized Hindi collides with English words and the TTS reads them as English — fixed by spelling, NOT by script.** Reported from a real UAT interview (session `4fdfa175`, backend role, Hinglish): the voice mispronounces Hindi words. Turn 4 asked *"toh aap **use** kaise approach karenge aur kya steps lenge **use** master karne ke liye"* — both are Hindi **उसे** (it/that), but the TTS reads Latin script, so the candidate hears *"aap YOOZ kaise approach karenge"*. **Root cause is the Latin-script-only rule from `0eb9f5a`**: Romanized Hindi is spelled identically to English homographs (`use`/उसे, `us`/उस, `bare`/बारे, `rat`/रात) and the voice has no way to tell them apart. **ElevenLabs `language_code` is IGNORED by `eleven_flash_v2_5`** — byte-identical audio with and without it — so there is no API-level fix; spelling/script is the only lever. Devanagari for the Hindi spans WOULD fix pronunciation (`"use"` → 10075 bytes vs `"उसे"` → 10911 bytes, i.e. genuinely different audio) but is **explicitly ruled out by the client — Hinglish output must stay English/Latin script only**. **Spellings were chosen by ROUND-TRIP, not by guessing** — synthesize with ElevenLabs, transcribe the audio back with a Hindi STT, keep the spelling that returns the intended word. This is essential because plausible guesses are wrong: `wrote "use" → heard "तो आप use कैसे approach करेंगे"` (0/3 correct), `wrote "usse" → heard "तो आप उसे कैसे approach करेंगे"` (**3/3 correct**), `wrote "usey" → heard "तो आप music कैसे approach करेंगे"` (unintelligible). **The rule is deliberately NARROW.** Most Romanized Hindi is already read correctly from context (`is`, `me`, `par`, `main`, `bat`, `bare`, `char`, `man` all verified fine), and "correcting" them makes it worse — `uss` for उस came back as *"assus"*. So the prompt fixes only **usse / raat / baat / baare / kaam** and explicitly forbids touching the rest. It also keeps the two senses apart: `"tool use karte hain"` is the English verb and stays `use` — only the model knows which it meant, so this is a **prompt rule, not a Python substitution**. Added to `_HINGLISH_RULES` and to the trailing `_language_reminder()` FINAL CHECK. Result: `usse` appears 6 times across 15 sampled turns where it appeared 0 times before. Prompt-only, same single Gemini Flash call; latency n=12 per cell — greeting 1.68 → 1.67s median (p90 1.79 → 1.77), body 1.77 → 1.69s median (p90 1.89 → 1.89). DEV+UAT live 2026-08-03 (`8e83d79`); PROD pending. **Reusable tool:** the round-trip harness (TTS → STT → compare against the intended Devanagari) is the only way to validate a pronunciation change without listening, and should be re-run whenever a new spelling is added.

**Two other findings from that same interview, NOT yet fixed.** (1) **The STT is destroying English technical vocabulary and is probably the bigger quality problem.** Sarvam `hi-IN` translit on a backend-developer interview produced: *Redis* → `radius` / `Rennies` / `Red is` / `Reddy's` (four manglings of one word), *codebase* → `core base` / `WordPress`, *clean code* → `Incoding` / `Plane Pincode`, *DevOps* → `Devout`, *cache it* → `cassette`, *presigned S3 URL* → `just please sign S3 URL`. The candidate noticed and corrected it aloud (`"...in your current WordPress. Code base not WordPress."`). That garbage is what `generate-question` and `score-final` consume. This comes from `47d6425` (Hindi/Hinglish → Sarvam `translit`), which predates all the Hinglish prompt work — Sarvam was benchmarked on conversational Hinglish, not English-heavy technical speech. Candidate fixes: route English-heavy technical roles to Deepgram `nova-3` (which `communication.md` documents as handling Hindi/English code-switching natively, and which AI Interview used before `e64e74c`), or feed the JD's technical terms to Sarvam as a vocabulary hint. (2) That interview was configured for **8 questions and ended at 5**, last one unanswered, 355s total, no language-switch requested. **Smoothness ideas not yet actioned:** cache the greeting TTS (near-identical per role — removes the first-turn wait and saves quota), cap switches per sentence (ElevenLabs applies ONE language to the whole string, so every extra English↔Hindi boundary is a mispronunciation chance — the clause rule sets a floor but no ceiling), and stream the TTS instead of generating the full clip first.

**Follow-up (2026-08-04): "the AI feels disconnected" — filler openers and over-long questions.** Two causes measured on 99 real UAT Hinglish turns rather than guessed: **59% of turns opened with "Achha"** (27% with "Achha theek hai" alone), and the **median turn ran 33 words, p90 46, max 72** where a real interviewer asks in 10-15. Scoped by evidence: question length is a **global** problem (English interviews measured median 33 / p90 46, *worse* than Hinglish's 25) so the length rule went into the shared `QUESTION_STYLE_RULES`; the "Achha" tic is **Hinglish-only** (English's most common opener is just 8%) so that rule lives in the Hinglish block and other languages keep their prompt. Length is now a **countable ceiling** ("under 25 words, target 12-18, count them") — "keep it short and spoken" was already in the prompt and being ignored. **Three lessons worth keeping, each cost a round-trip to learn.** (1) **A straight ban makes it worse.** "Do NOT begin with Achha" moved it from 9/12 to **11/12**; what worked was supplying a rotation of concrete alternatives to choose from — same as the mix ratio, where worked examples bound and prohibitions did not. (2) **Varying a filler is not reducing it.** The rotation eliminated "Achha" but left **13 of 14** turns opening with *some* acknowledgement ("Got it,", "Theek hai,", "Okay so —") plus generic scene-setting ("customer support mein bahut zaroori hai ki..."). The fix was to invert the default: no preamble is now the stated norm, an acknowledgement is the explicit exception capped at one turn in three and only counts when it names something the candidate actually said — *"if your acknowledgement would work after ANY answer, it is filler, drop it"*. (3) **Adding a prompt rule is not free — it competes with what is already there, and the rules nearest the END win.** Adding the word-count and opener checks grew the trailing FINAL CHECK from 3 items to 5 and **crowded out the script rule sitting at item 1**: the Devanagari leak went from 1/14 to **5/14**, caught on UAT within minutes of deploying. Moving the script check from first to **last** (with an explicit override over the rules above it) restored it to 1/16. Net measured effect, n=18 against the same branch without this work: opens with "Achha" 16/18 → **0/18**, opens with any filler 16/18 → **9/18**, median words **32 → 23**, Devanagari 0/18 → 0/18. Prompt-only, same single Gemini Flash call; latency n=12 greeting 1.72 → 1.63s median, body 1.94 → 1.84s. **Honest limits:** filler rate is noisy across runs (3/14, 9/18, 5/12 live — true rate roughly a quarter to a half, deliberately NOT zero since an interviewer who never acknowledges reads as cold); "Achha" still slipped into 2 of 12 live samples despite scoring 0/18 in test; and roughly a third of turns still exceed the 25-word ceiling. Commits `de8b413`, `dc84a17`, `980f605`. **DEV + UAT live 2026-08-04; PROD pending.**

**Not done — the biggest remaining "disconnected" factor is dead air, not wording.** Measured on real sessions, the gap from the candidate's answer landing to the next question being asked is **1.4-2.8s** of Gemini generation, and TTS synthesis happens *after* that — so there are roughly **3-5 seconds of silence every turn** before the AI starts speaking. The fix is to **stream the TTS** instead of generating the whole clip first (ElevenLabs supports it, first audio in ~75ms), which *reduces* latency rather than adding any. Two cheaper wins alongside it: **cache the greeting TTS** (near-identical per role — removes the first-turn wait and saves quota) and **cap switches per sentence** (ElevenLabs applies ONE language to the whole string, so every extra English↔Hindi boundary is a mispronunciation chance; the clause rule sets a floor but no ceiling). Deferred to the next sprint.

**ROLLBACK PLAN for the Hinglish work (tested 2026-08-03, exercised in full 2026-08-03/04).** Commit chain: `0eb9f5a` (2026-07-30, pure-Hindi fix) → `cfad015` (clause-level mix) → `8e83d79` (TTS spelling) → `de8b413`/`dc84a17`/`980f605` (naturalness). **All of it is preserved on the branch `feature/hinglish-code-mixing`**, which is kept tree-identical to UAT — that branch, not a revert commit, is the canonical home for this work. **Reverting the prompt commits is clean;** it was done and re-applied once already, so the mechanics are proven. **Reverting `0eb9f5a` CONFLICTS** and must not be attempted casually: the language-switch feature (`ec27902`, 2026-07-31) was built on top of it and calls `_language_rules()`, so removing it breaks that feature too. **Beware the revert-on-release-branch trap:** because a revert lands on UAT as a *later* commit, merging Development into UAT afterwards will **not** bring the changes back — git sees them as already merged. Restoring requires an explicit revert-of-the-revert (`git revert --no-edit <revert-sha>...`), which is exactly what was needed on 2026-08-04. Back-merging UAT into Development after such a cycle **will conflict** on `ai_interview.py` (revert vs re-revert of the same lines); resolve with `git checkout origin/UAT -- routers/ai_interview.py`, which is what makes the trees match again. **Note:** reverting restores the *previous* defects — Hindi-grammar-with-English-nouns, the `use`/उसे mispronunciation, and the "Achha" tic all come back together.

**Failed attempt, recorded so it is not repeated: candidate-adaptive mix banding (2026-08-03, NOT shipped).** Before the clause-level fix, the balance problem was attacked by adapting the interviewer's blend to the candidate's — a `_hinglish_band()` reading the last 3 answers out of `prior_turns` (already in the payload, so no contract change and no extra call), banding them English-leaning / balanced / Hindi-leaning against cut-offs calibrated on 91 real Romanized UAT answers, and injecting a per-band worked example. It was **reverted**: with an LLM judge at n=10 per cell the interviewer scored 54.5% / 45.0% / 50.0% Hindi across the three candidate registers — **not monotonic**, i.e. no adaptation. An earlier n=6 run had shown a clean 50 → 65 → 67 gradient that did not replicate, and the same BEFORE cell scored 55.5 in one batch and 70.0 in the next, so batch noise exceeded the effect. Reading the output confirmed it: English-leaning and Hindi-leaning candidates got near-identical questions. **Two measurement lessons worth keeping.** First, the Hindi *function-word* share used to find the original Devanagari bug is fine for gross discrimination (pure-Devanagari vs Roman) but **invalid for measuring balance** — it cannot see Hindi content words (`gusse`, `mushkil`, `samjhana`), so it partly measures grammatical glue and can invert the reading; two instruments disagreed on the same outputs. Second, a Latin-only tokenizer scores a Devanagari answer 0.00 and would band a Hindi-speaking candidate as English-leaning, the exact inverse of the truth (Devanagari must count as Hindi outright). The patch and its 15 unit tests are on the DEV box at `/tmp/hinglish-balance-attempt.patch`. **Prerequisite for any further balance work: a real eval harness** — a human-labelled set of turns, a judge validated against those labels, and enough samples per condition to clear the noise. Without it a prompt change can be made *different* but not demonstrably *better*, which is how this round was lost.

- **Candidate can switch OFF Hinglish mid-interview (added 2026-07-31).** A Hinglish interview assumes the candidate follows both halves of the code-mix; some don't. Previously the interview just carried on in a language they couldn't follow — and worse, "I don't understand Hindi" **matches `isConfusion()`**, so it triggered a reframe that re-asked the SAME question in the SAME Hinglish. Now, when the candidate says they can't follow one half, the interview switches to the other (**English or Hindi only** — the two halves of Hinglish; a request for Tamil/Marathi/etc. is ignored) for every remaining question, and the request is recorded on the report. **Hinglish-only** — `canSwitchLanguage()` gates on `stage_config.language === "Hinglish"`, so every other interview type is untouched. **Detection is an LLM verdict, deliberately NOT a regex** — candidates ask for this in far too many ways, across two languages and both scripts ("mujhe English samajh nahi aati", "can we do this in English?", "I'd be more comfortable in Hindi"), for a phrase list to cover. It is **folded into the `generate-question` call the orchestrator already makes every turn** (new request field `detect_language_change`, response fields `language_change_request` / `language_change_target` / `language_change_evidence`) rather than a separate classifier pass: a dedicated call would add a round-trip to EVERY turn to catch something that happens on roughly one turn in a hundred, and the live turn is deliberately a single Gemini call. Only the turn where a switch actually fires pays for an extra call (the re-ask). The block is injected **only** when `detect_language_change` is set, so every non-Hinglish interview's prompt and output are byte-identical to before. **The evidence quote is load-bearing, not decorative:** `_sanitize_language_change()` (FastAPI) drops any verdict lacking a verbatim quote or naming a target outside English/Hindi — requiring the model to quote the candidate before the flag counts is what suppresses hallucinated positives, and it is what the recruiter sees on the report. The prompt also draws a hard line against the adjacent failure mode: "I didn't get the question" / "can you repeat?" is **content** confusion (→ existing reframe path), not a language request. **Mechanics** (`student-node/app/helpers/aiInterviewLanguage.js`, new): the switch is stored as `ai_interview_sessions.session_metadata.languageSwitch = {from, to, evidence, at}` — **no DB migration**, the column is already jsonb. `effectiveLanguage(session, config)` is now the single read point for interview language, replacing the 5 direct `config.stageConfig?.language` reads in `submitTurn`, so the switch holds for the rest of the interview; the pre-existing "LANGUAGE INSTRUCTION overrides the conversation history" line makes it actually stick despite a Hinglish transcript. The switch **re-asks the current question** in the new language via the `is_reframe` path (+ new `language_switched` flag so the opener acknowledges the language instead of apologising for being unclear), and **releases the interaction** (`candidate_response = NULL`) so the request is never scored as an answer — nobody is marked down for not speaking Hindi. **One switch per session** (a second request is treated as an ordinary answer, so a candidate can't ping-pong the interview into a stall), and it is handled in **both** entry points — the `isConfusion` reframe branch and the normal turn — plus carried across the admin-priority branch, which rebuilds `nextQ` by hand. **Deliberately kept OUT of scoring** (never passed to `score-final`): it's a fact the recruiter should see, not a mark against the candidate. **Frontend:** `submitTurn` returns `languageSwitch` alongside the re-asked question; `Assessment-React` writes **`sttLanguageCodeRef`** (not just state — the STT websocket opens fresh per answer off the ref, and the state→ref effect hasn't run by the time the candidate starts speaking) so the next recording routes to the right provider, plus a "Continuing in English." toast. **TTS needs no change** — ElevenLabs `eleven_flash_v2_5` with voice `CpLFIATEbkaZdJr01erZ` ("Payal", a *native Hindi* conversational voice), multilingual and keyed by voice id, not language. **Reported on all four surfaces**, each reading `session_metadata`. **Heading is "Language barrier"** (renamed from "Language changed mid-interview" on 2026-07-31) on the two admin views and the PDF; the PDF keeps a `: <from> → <to>` suffix so the direction reads at a glance, matching the sibling proctoring banner's `Proctoring: <band>` idiom, and a test pins that exact string so it cannot drift from the admin views. The **candidate-facing** card is deliberately left as **"Interview language"** — it is the candidate's own report, and labelling them with a "barrier" cuts against the design intent that this is a neutral record of an honoured request, never a penalty. Surfaces: `admin-react` `AIInterviewReport.js`, `admin-react` `StudentReport` modal (both the scored AND not-completed branches — a candidate who switched then dropped out is exactly the case needing context), the candidate's own `AIInterviewReportCard.js`, and — since 2026-07-31 — the **downloadable report PDF**, which is the artefact a recruiter actually forwards and was the one place the context was missing. In the PDF it is `_renderLanguageSwitchHtml()` (`student-node/app/models/Assessment.js`, sibling of `_renderIntegritySummaryHtml`) injected as `{{{languageSwitchHtml}}}` in `public/aiInterviewReport.html` **directly after the proctoring banner on page 1** — same class of fact (how the interview was *conducted*, not how it scored), and it must sit above the transcript because it explains why the transcript changes language partway through. Deliberately a muted indigo, **not** a proctoring-style risk band, and it carries an explicit "not scored" line so it never reads as a mark against the candidate. The verbatim quote is reproduced (it is what lets a recruiter judge the request) and goes through `_escHtml` first — it is candidate-supplied text landing in a Puppeteer-rendered page. Returns `""` when no switch happened, so the ~99% of reports that never switched are byte-identical. `session_metadata` needed no query change: `generateAIInterviewReport` already loads the session with `findFirst` + `include` (no `select`). Corporate ATS v2 has no AI-Interview report view (`ai_interview` is only a stage label there), so nothing to change. **Known edge:** the completion gate runs *before* question generation, so a request on the very last turn ends the interview without switching and that utterance stays as an answer — accepted, since switching has no value once nothing is left to ask (and confusion-shaped phrasings are caught earlier, before the gate). Tests: `student-node/test/aiInterviewLanguageSwitch.spec.js` (**25** — 18 for the switch itself, 7 for the PDF banner covering the renders-nothing default, the quote escaping and the exact heading), `fastapi-ai-engine/tests/test_language_change_guard.py` (12). Files: `fastapi-ai-engine/routers/ai_interview.py`, `student-node` `aiInterviewLanguage.js` + `aiInterviewHandler.js` + `Assessment.js` + `public/aiInterviewReport.html`, `admin-node/app/handlers/aiInterviewHandler.js`, `admin-react` (2 report views), `Assessment-React` (`interview.js`, `AIInterviewReportCard.js`). Switch itself and the PDF banner are both **DEV+UAT live 2026-07-31**; PROD pending. The PDF banner was verified by rendering a real report on DEV against a session temporarily given a `languageSwitch` (reverted straight after): 173 KB PDF, banner on **page 1** between the proctoring block and the Executive Summary, arrow and smart-quotes rendering correctly.

- **Per-turn scoring is off the critical path.** `score-turn` is fire-and-forget from `submitTurn` (its signals are a soft hint only) and, in FastAPI, now runs on the **background executor** (`_gemini_json_background`, behind the scoring semaphore) instead of the priority pool — so it can never contend with the live `generate-question` call. This removed a visible slowdown on the turn after the first substantive answer (the candidate's "3rd question"). Each live turn is a single Gemini call.

- **AI-only verdict (changed 2026-07-03, REVERTED 2026-07-16 — superseded, kept for history).** Briefly the LLM was the sole decision-maker for the fit verdict — FastAPI `score-final` didn't clamp/override a valid verdict the model returned, relying only on prompt discipline (an explicit VERDICT RUBRIC + `temperature=0.5`). Python only filled in a verdict when the model's field was missing or unrecognized. **This did not hold up**: the model's own arithmetic on weighted-average `overall_score` frequently disagreed with the correct computation (e.g. a `4,3,3,4,4` / `10,10,15,10,55`-weighted config computes to 75 but the model sometimes returned 60) — enough to shift a candidate across a verdict band boundary (Fit vs Strong Fit, Fit vs Borderline) on identical transcript content.
  **Current behaviour (`e31ead3`, 2026-07-16, DEV+UAT+release-v1.36):** `score-final` still asks Gemini for per-parameter `rating`s (0–5) and prose (strengths/concerns/analysis/quotes), but `overall_score` is **recomputed in Python** as the weighted average of `(rating/5)*100` across the admin's configured parameters (iterating the *config*, not the LLM's output list, so a parameter the model skipped can't skew the total) — the model's own `overall_score` number is discarded. A **non-engagement cap** then applies to the recomputed score using a word-count proxy (not an LLM judgement): average answer length `< 8` words, or `≥ 25%` of answers `≤ 3` words, caps the score at 25; `≥ 50%` of answers `≤ 3` words caps it at 10 (intro turns excluded from the count). The **verdict is then derived mechanically** from that final score against the same four bands, and forced to `Not Fit` whenever the non-engagement condition fires — the model's own `verdict` field is never read. `score-final` still runs Gemini at `temperature=0.5` (lower prose variance is still worth having even though the verdict itself is no longer model-decided). student-node's `deriveVerdictFromScore` (`aiInterviewHandler.js`) and `verdictFromScore` (`Assessment.js`) are unchanged and remain fallback-only (fire when no `aiRecommendation` is stored at all — e.g. a pre-existing row — never overriding a stored verdict). Test coverage: `fastapi-ai-engine/tests/test_score_final_recompute.py`.

- **Parameter name is authoritative from config, not the LLM (fixed 2026-07-03).** The report's per-parameter label comes from `parameter_scores[].name`. The score-final prompt asks Gemini to echo each parameter's `name`, but the model intermittently returned it **blank** (or echoed the id). Nothing re-filled it, so the PDF renderer's fallback `name: p.name || p.id` surfaced the raw admin id (e.g. **"PARAM_XYRD"**) instead of the human label. Two-part fix: (1) **FastAPI `score-final`** now backfills each `parameter_scores[].name` from the input `evaluation_parameters` by matching `id` (`name_by_id = {p.id: p.name ...}`), right before `return ScoreFinalResponse(...)` — the admin config name is the source of truth, the LLM's `name` is ignored whenever the id matches (the prompt guarantees every input param appears carrying its id). This fixes **all future reports**, both the PDF and the JSON report UI, since the DB row is then stored with the correct name. (2) **student-node PDF path** (`Assessment.js` `generateAIInterviewReport`) loads the config's `evaluation_parameters` (raw query joining `ai_interview_config` on `assessment_set_id`) into an id→name map and resolves the label as `paramNameById[p.id] || p.name || p.id` — this repairs **already-scored historical rows** whose stored name is blank (the FastAPI fix alone only helps rows scored from then on). DEV+UAT live; PROD pending.

- **Per-Parameter Detail table — page 2, weight-sorted (2026-07-24).** Client wanted this key table seen early, so in `public/aiInterviewReport.html` the "Per-Parameter Detail" `<div class="section">` was **moved up to directly after the Executive Summary** (above Strengths/Concerns) and given a `params-section` class with `page-break-before: always`, so it always starts at the **top of page 2** of the Puppeteer-rendered PDF (light content — header, verdict/score strip, proctoring summary, exec summary — stays on page 1). Added `table.params tr { page-break-inside: avoid }` (row-level only — never the whole table, which could leave a large empty page) so a single parameter row doesn't split across a page boundary. Rows are now **sorted by config weight descending, ties broken by parameter name ascending** (case-insensitive). Weight is **not** stored on the score's `parameter_scores` JSON — it lives on `ai_interview_config.evaluation_parameters[].weight`; `Assessment.js` `generateAIInterviewReport` builds a `paramWeightById` map in the same raw-query loop that already builds `paramNameById` (join `ai_interview_config` on `assessment_set_id`), attaches `weight` to each mapped param, and sorts. Params whose id isn't in the config (no weight) sort to the bottom (`-Infinity`). DEV+UAT live 2026-07-24; PROD pending.

- **Admin guidance fields (free-text, optional).** Columns on `ai_interview_config`, threaded through admin-node → student-node → FastAPI:
  - `question_guidance` — set by the admin on the create form; injected into the **generate-question** prompt as an "ADMIN QUESTION GUIDANCE" block (sample questions, topics, how to ask). The model adapts samples rather than asking them verbatim; still respects role/JD/seniority. **Fixed (2026-07-03):** when the guidance text listed multiple sample questions, the model would sometimes merge two of them into one spoken turn. The block now explicitly frames the guidance as a POOL to draw ONE topic from per turn — never merge (`fastapi-ai-engine/routers/ai_interview.py`, `question_guidance_block`). **Bigger fix (2026-07-10):** admin questions in this field could be silently skipped ENTIRELY across the whole interview — this is the *only* guidance box the admin UI currently exposes (the dedicated `sample_questions`/"Priority questions" field was removed from the UI 2026-06-30 — see below), so it was a soft prompt hint competing against the much stronger per-turn "probe THIS parameter" instruction. Real incident: 2 questions in `question_guidance`, 0 asked across all 8 turns (Abhimanyu Sharma / Product Designer, UAT). Fix stayed prompt-only (no student-node/API changes, LLM keeps full control of *when*, per explicit product decision to not force a deterministic queue here): `question_guidance_block` now marks literal questions (ending in "?") as HIGH PRIORITY / must-cover with self-tracking against `QUESTIONS ALREADY ASKED`; `wrapup_directive` adds a last-turn catch-up clause forcing an unused priority question in if any remain unasked going into the final turn; new `CRITICAL RULES` #9 as a standing per-turn reminder. Known limit: still probabilistic, not guaranteed — an interview that ends early (time-up / candidate disengagement) before reaching the "last question" turn can still skip them. DEV+UAT live.
  - `scoring_guidance` — injected into the **score-final** prompt as an "ADMIN SCORING GUIDANCE" block (how to weight/interpret answers). Bounded: it cannot override the non-engagement / anti-cheat rules. Removed from the admin-react create form on 2026-06-30, then **re-added (2026-07-02)**: a single optional "Scoring guidance (optional)" textarea in the Evaluation Parameters step of `CreateAIInterview.js`, wired to the existing `scoringGuidance` state key and `AssessmentSelect.js` payload (`interviewConfig.scoringGuidance`) — no backend changes needed since the column/wire field/prompt-injection were never removed. DEV+UAT live; PROD admin-react not touched.

- **Narration voice (admin-selectable).** The admin picks the AI interviewer's spoken voice from a curated set on the create form, with inline ▶ sample preview (MP3 clips on OCI at `pl-uat-public-docs/ai-interview/voice-samples/`). **As of 2026-06-30 the picker is trimmed to 2 voices — Payal and Anika** (both Hindi female; Payal is the default, `CpLFIATEbkaZdJr01erZ`). The list previously had 10 (Payal, Anika, Monika, Alisha — Hindi female; Raj, Tarun, Aman — Hindi male; Sarah, Eric, Daniel — English); the other 8 were removed from `VOICES` per client request. Their MP3 samples still exist on OCI and the `voice_id` values still resolve in `/tts`, so any of them can be re-added to the array later without other changes. The `voice_id` values are ElevenLabs IDs (account voices + shared-library voices, which work directly in `/tts` without adding them to the account). The curated list lives in `admin-react/src/modules/AIInterview/CreateAIInterview.js` (`VOICES`). The chosen `voice_id` is stored on `ai_interview_config` and threaded admin-node → student-node (`startSession`/`getConfigInfo` return it as `voiceId`) → Assessment-React → FastAPI `/ai-interview/tts`, which uses it as the ElevenLabs `voice_id`. When null, `/tts` falls back to its env default (`ELEVENLABS_VOICE_ID`). **Gotcha (fixed 2026-06-25):** the candidate-side `tts()` previously sent a hardcoded `voice: 'aura-2-thalia-en'` (Deepgram) on every call, which silently overrode the admin's voice choice and forced the Deepgram fallback path — so ElevenLabs voice selection never reached the candidate. Now `tts(text, voiceIdRef.current)` passes the admin voice; null falls back to the backend default. **Second gotcha (fixed 2026-06-25):** admin-node's `app/models/Assessment.js` has **two** `INSERT INTO assessment.ai_interview_config` paths — the sync path (`assignAIInterviewAssessment`) and the async/queue path (`assignAIInterviewAssessmentAsync`, used when `AI_Interview` async assignment is enabled — the corporate OTP flow). The async INSERT had drifted out of parity and was missing `voice_id` (also `scoring_guidance`, `question_guidance`), so on the async path `voice_id` was silently lost → `startSession` returned `voiceId: null` → candidate heard the FastAPI env default (Payal) regardless of the admin's selection. Both INSERTs now carry the full column set — keep them in parity when adding any new `ai_interview_config` column. **OPERATIONAL GOTCHA — ElevenLabs billing (2026-06-29):** the voice picker, persistence and threading are all correct, but if the ElevenLabs subscription has a **failed/incomplete payment**, every `/tts` ElevenLabs call returns **401 `payment_required`** and FastAPI falls back to **Deepgram `aura-2-thalia-en`** — a single fixed voice that ignores the admin's selection entirely. Symptom: "I picked Tarun but the candidate hears the same default voice." This is NOT a code bug — resolve the ElevenLabs invoice. Verify with: `curl -X POST https://api.elevenlabs.io/v1/text-to-speech/<voice_id> -H "xi-api-key: $KEY" -d '{"text":"hi","model_id":"eleven_flash_v2_5"}'` → a 401 payment_required body confirms it.

- **Admin priority/sample questions (2026-06-29).** `ai_interview_config.sample_questions` (jsonb, default `[]`) holds questions the recruiter wants asked **verbatim, in order, before any AI-generated question** — distinct from `question_guidance` (style hints the AI adapts). admin-react splits the value into an array on `interviewConfig.sampleQuestions`; admin-node persists it on all three config INSERT paths; student-node `loadConfig` reads it and, on each fresh-question turn (never a depth follow-up), serves the next unused sample verbatim (case-insensitive de-dup vs already-asked) with **no LLM call**, then falls back to AI generation once samples are exhausted. DB migration: `Assessment OTP Invite/006_ai_interview_sample_questions.sql`. **Fixed (2026-07-09):** samples were sometimes silently dropped — the completion gate (parameter coverage / 8-question cap / time-up) could fire before all samples were asked. The gate now yields to `samplesRemaining` (candidate-unwilling / trailing refusals still ends the interview absolutely), and a sample's dimension falls back to the last param the candidate was probed on (or the first param) when round-robin is exhausted, so the sample still counts toward `counts[]` / scoring. `student-node/app/handlers/aiInterviewHandler.js` (`submitTurn`). DEV+UAT live. **The admin-react "Priority questions" input was removed (2026-06-30)** — the create form no longer exposes it, so new interviews send `sampleQuestions: []`. The column, the wire field, and the full student-node verbatim-serving path all remain in place (empty array = no priority questions), so it can be re-surfaced later without backend changes.

- **`/assessment/exportStudentData` — AI Interview columns (fixed 2026-06-30).** The export had no AI_Interview branch in its type dispatcher — AI Interview assessments fell into the role-based branch by default and produced **Communication section columns** in the Excel. Fix: add `isAIInterviewAssessment` flag (parallel to behavioral/aptitude/role-based/custom) in both `getAssessmentDetails` sites and propagate through `assessmentInfo`. The export now emits **Overall Score + Verdict + one column pair (Rating + Label) per admin-configured evaluation parameter** resolved once across all completed students. Row cells pull from `ai_interview_scores.parameter_scores` (jsonb); unscored parameters stay blank. Patch: admin-node `app/models/Assessment.js` (`getAssessmentDetails` AI score fetch now also reads `ai_recommendation`, `parameter_scores`, `executive_summary`; the export adds an AI branch before the role-based branch).

- **Resume in question generation.** The candidate's resume is sent on every `generate-question` turn and is now **used** to personalise questions (a `CANDIDATE RESUME` block, capped ~6000 chars) — anchored to role/JD. (Earlier the prompt explicitly ignored the resume; that instruction was removed.) `score-final` still does not receive the resume.

- **Off-topic acknowledgement (human-like steering).** `generate-question` makes the interviewer behave like a real human when a candidate drifts: before writing the next question, the model judges whether the previous answer engaged with the question (returned as `last_answer_engaged` in the JSON / `GenerateQuestionResponse`). If it did NOT (off-topic, irrelevant, a joke/song, a non-answer, a refusal), the `question` field MUST open with one short, warm steering sentence ("No worries — let's bring it back to the role: …") then ask the next question; if it did engage, no acknowledgement is added (so it never feels robotic). Still a single Gemini-Flash call — no extra latency. **Why this was needed (2026-06-26):** the steer-back previously only fired strongly for regex-detectable `refusal`/`shallow` signals from student-node (`isRefusal`/`lacksDepth`, `last_answer_signal`); a long off-topic answer (>25 words, no refusal phrase) got `last_answer_signal=null` and the soft "judge from history" hint was often skipped, so the interviewer asked the next question as if nothing was wrong. Making `last_answer_engaged` an explicit required field forces the judgement. The cheap deterministic `refusal`/`shallow` signals still short-circuit and set the hint; true off-topic detection is semantic and left to the model (score-turn's `relevance` is fire-and-forget and not available in time for the live turn).

- **Final-question wrap-up cue (2026-06-26).** student-node computes `is_last_question` for the upcoming turn (true when the `MAX_TOTAL_QUESTIONS` cap leaves no room after it, or asking it completes coverage of every parameter) and passes it to `generate-question`. When set, the interviewer opens with a short warm wrap-up cue ("Alright, last question before we wrap up — …") so the candidate isn't caught off guard when the interview ends right after their answer. Composes with the off-topic acknowledgement: steer-back first, then the wrap-up cue, then the question.

- **Candidate "evaluating" status after Done answering (2026-06-26, Assessment-React `interview.js`).** When the candidate clicks **Done answering**, the rotating status loader (`QLoader`) now shows for both the between-question pause (`thinkingPhase === 'next'`) and the final wrap-up (`'finalise'`), each with its own rotating copy ("Evaluating your response…", "Putting together your summary…"). Previously the loader only rendered when there was no question text, so the *previous* question stayed on screen during the few-second wait and it read as a frozen screen. The `finalise` phase is excluded from the secondary `HintRow` spinner to avoid a duplicate.

- **Per-question context window + anti-repeat.** `generate-question` is sent the **last 4 turns** of full Q&A (`RECENT_TURNS_FOR_LLM = 4`) for follow-up context — a deliberate latency/cost tradeoff (full Q&A history pushes Flash latency to 5s+ by Q8). Separately it receives **`asked_questions`** — the text of *every* question asked this interview (no answers, so cheap) — and a prompt block forbidding repeats/rewordings. **Why (fixed 2026-06-27):** with only the recent turns in context, by Q8 the model no longer saw Q1-Q4 and re-asked them (commonly Q3 and Q8 repeated). The full asked-questions list is the authoritative anti-repeat signal. `score-final` receives the **full** transcript.

- **Live captions (streaming STT) — keep audio actually flowing (fixed 2026-06-27).** Candidate answers stream to FastAPI `/ai-interview/stt-stream` (Deepgram nova-3, `interim_results=True`) over a WS; each interim/final carries a `running` field the client renders live (`interview.js` `setTranscriptLine`). Symptom seen: captions box stayed empty during the answer and only filled at "Done answering" — that's the **batch-STT fallback** (MediaRecorder → `POST /ai-interview/stt`) firing because the live WS never delivered transcripts. Root causes hardened: (1) the WS-open timeout was **3s**, too tight for a cold WSS handshake on mobile, so `openSttSocket()` rejected and the turn went batch-only → raised to **8s**; (2) a **suspended AudioContext** never runs the capture worklet's `process()`, so no PCM is sent and Deepgram returns nothing → now `resume()` is retried and re-applied on `onstatechange` if the context is auto-suspended mid-turn (mobile backgrounding). The server/nginx WSS path itself is fine (verified end-to-end) — nginx `/ai-interview/` already does `proxy_http_version 1.1` + Upgrade/Connection headers on DEV and UAT.

- **Turn latency — Gemini "thinking" was silently ON (root-caused & fixed 2026-06-30).** Candidates reported an ~8s lag between answering and the next question on `POST /ai-interview/session/turn` (→ FastAPI `/ai-interview/generate-question`). Root cause was **not** load, proctoring contention, or the scoring semaphore (`/ai-interview/` is a `PRIORITY_PATH` and bypasses `MAX_CONCURRENT_SCORING`). The code calls `_no_think_config()` to disable Gemini 2.5 thinking (`thinking_budget=0`, its own comment: "saves 3-7s per call"), but the **`PortkeyGeminiClient` shim** in `utils/portkey_gateway.py` that translates google-genai config → LiteLLM's OpenAI schema **never forwarded `thinking_config`** — so it was dropped and Flash kept thinking on *every* question-gen and score-turn call. Measured on UAT: isolated Gemini call = 0.96s, but `generate-question` = 6-8s; with `reasoning_effort="disable"` = ~1.5s; 8 concurrent turns went from ~7s each → 2.2s total. **Fix:** `_ShimModels.generate_content` now reads `thinking_config.thinking_budget` and emits `reasoning_effort="disable"` (LiteLLM maps that back to Gemini `thinking_budget=0`); a positive budget forwards as `thinking={type:enabled,budget_tokens}`. Also added a **startup pre-warm** (`@app.on_event("startup")` in `main.py`) that fires one cheap Gemini call on boot so the SDK + TLS handshake to the gateway is warm before the first real turn (removes the ~1.5-2.5s cold-start the first candidate after a deploy hit). Net: live turn dropped **~8s → ~1.5s**. Same fix automatically speeds up `score-turn` (also a no-think priority call); `score-final` is unaffected (it deliberately uses `no_think=False` for quality). **General rule:** any latency win from `_no_think_config()` only takes effect if the gateway path forwards the thinking config — don't assume the google-genai `thinking_config` survives the LiteLLM hop.

- **Full-session mixed audio recording (added 2026-07-01, Q1-silent gotcha fixed 2026-07-02).** The admin Student Report's existing "Audio" button (already worked for Communication/Paragraph Reading via `student_answers.object_key`) never had anything to play for AI Interview. `Assessment-React/.../AIInterview/sessionRecorder.js` now records the **entire interview** — interviewer TTS + candidate mic — mixed into one continuous track via Web Audio API (`MediaStreamAudioDestinationNode` fed by both a `createMediaStreamSource(micStream)` and a `createMediaElementSource(ttsAudioEl)`, captured by one `MediaRecorder`) and uploads it through the same existing upload endpoint (filename containing "audio" so admin's pattern-matcher picks it up) — no admin-side UI change needed. `createMediaElementSource` only works because `interview.js` reuses one module-level TTS `<audio>` element (`ttsAudio.js`, gesture-unlocked in `instruction.js` via `primeTtsAudio` for iOS) for the whole session, never a fresh `new Audio()`. **Gotcha:** question 1's audio was silent — `startSessionRecording()`/`attachTtsToSessionRecording()` were only ever called inside `startRecord()`, which fires when the candidate's mic opens, and that happens *after* `speak()` finishes playing the AI's question (`autoStartMicIfReady` runs post-playback). So the very first question had already finished playing before the recording tap got wired up; every later question worked because the tap was already wired from the prior turn. Fix: `speak()` now calls `startSessionRecording({ ttsAudioEl: getTtsAudio(), mimeCandidate })` itself, before playback starts, on every call (idempotent — only wires branches not already connected); `micStream` is attached later via `attachMicToSessionRecording` once `startRecord()` acquires it. Admin reads recordings via `GET /assessment/getAudioVideoProctoring?assessmentAssignedId=...` (admin-node). Interviews given before this fix (or before the Q1 fix) have no/partial audio — the recorder can't retroactively capture a session that already ran.

- **Durable, reload-surviving upload (fixed 2026-07-17).** Diagnosed why ~10% of *completed* interviews (both UAT and PROD, consistent rate) had **no audio object in the bucket at all** — not a DB-write failure like the earlier gotchas, the upload never reached the server. Root cause: `finalize()` fired the upload as an **unawaited in-memory POST** (fire-and-forget), while `completeSession` + `fetchReport` land in ~1-3s and drop the candidate on the "Thank you" screen with no indication a multi-MB upload is still in flight. Any reload / tab-close / OS-backgrounding at that moment aborts the plain `fetch` (no `keepalive`, no `sendBeacon`, no `beforeunload` guard) and the blob — which only ever existed in that tab's memory — is lost forever. Confirmed via session_metadata: e.g. `completionReason: "admin_forced"` (candidate tab already gone when an admin ended it server-side) produces exactly this. Fix: **`sessionUploadQueue.js`** — a durable IndexedDB store (`ai_interview_uploads`/`pending`, keyed by `assessmentAssignedId`). On recording stop, `finalize()` now `enqueueRecording()`s the blob + chapters + a **snapshot of the scoped invite JWT** (sessionStorage is cleared on tab-close, so the token is stored alongside so a later drain can still auth via an explicit `Authorization` header — `uploadSessionAudio` gained an `extraConfig` param for this), then `drainPendingUploads()` attempts it; success deletes the record, failure leaves it queued. `initUploadQueueResumption()` (called from both `interview.js` and `instruction.js` mounts — the latter is the reload-landing page for already-completed OTP candidates) registers resume triggers: an immediate drain, a `window 'online'` listener, and a 30s tick. Net: the recording survives any number of reloads / a tab-close-and-reopen (within the ~12h token life) and keeps retrying until it lands, as long as the browser reopens the app with a connection. The only unrecoverable case left is a candidate who closes the tab and *never* returns (true fix for that would be chunked upload *during* the interview — not built). Verified the enqueue → failed-drain-stays-queued → retry-drain-succeeds flow + blob/auth/chapters integrity end-to-end in a headless browser before deploy.

- **"Time's up" audio silently lost — stopSessionRecording could hang (fixed 2026-07-17).** Even with the durable queue above, interviews that ended via the **client countdown timer** ("time's up") still lost audio. Root cause is a distinct bug from the upload issue: the client timer (`interview.js` `startElapsedTimer`, at `remaining <= 1`) calls `finalize()` **while the candidate is still mid-answer** — mic actively recording, STT socket open, audio graph under load — whereas normal completion (`submitTurn` → `dat.complete`) only finalizes *after* the answer was submitted and the graph is idle. `finalize()` starts with `stopSessionRecording()`, whose promise resolved **exclusively inside the MediaRecorder's `onstop`**. Under that mid-answer load some browsers are slow to, or never, fire `onstop`, so the promise **hung forever** → the `.then()` that persists+uploads the blob never ran → no audio, even though `completeSession`/`fetchReport`/the "Thank you" screen (all independent of that promise) proceeded normally, so the interview looked fine. Note there is *also* a server-side time-up (`aiInterviewHandler.js` ~L861 `isTimeUp`, `completionReason:"time_up"`, returned from `submitTurn` when `elapsedSec >= interview_duration`) — that path finalizes cleanly because it goes through the submit handler with the graph idle; the hang was specific to the *client* timer firing mid-answer. Fix (`sessionRecorder.js` `stopSessionRecording`): call `recorder.requestData()` to force-flush the tail as a `dataavailable` **before** `stop()`, add a **3s timeout** that resolves with whatever chunks exist if `onstop` is late/absent, and salvage buffered chunks even when the recorder is already `inactive` (return them instead of `null`). The promise can no longer hang, so the recording is always enqueued. Verified hang / normal / already-inactive-salvage / truly-empty cases in isolation before deploy.

- **Jump-to-question chapters in the admin audio player (added 2026-07-06).** Extends the full-session recording above: `interview.js`'s `speak()` now also drops a chapter marker `{n, offsetMs, text}` on every genuine question (skips the "couldn't hear you" retry apology) using `sessionRecorder.getRecordingElapsedMs()` — the SAME clock that drives the recording, so there's no client/server clock-skew risk. The accumulated array is sent once at `finalize()` as a `chapters` multipart field alongside the session-audio upload (`uploadSessionAudio`). student-node's `uploadAudio` handler stashes it (as-is, already a JSON string) into `student_answers.answer_text` — unused for this row otherwise, so **no schema change**. admin-node's `getAudioVideoProctoring` now also selects `answer_text` and best-effort `JSON.parse`s it into a `chapters` field per row (silently `null` if it's not valid chapters JSON — e.g. a real text answer from another assessment type). admin-react's chain (`StudentReport.getMediaKeys` → `actions.js` `fetchMediaUrls` → `AudioVideoModal`) carries `chapters` through to the modal, which now renders a clickable "Jump to question" list under the `<audio>` element — clicking a row sets `audioEl.currentTime` and plays from there. Recordings made before this fix (or any non-AI-Interview audio/video row) simply have no `chapters` → plain player, unchanged. Two class-body-duplicate `getAudioVideoProctoring` methods exist in `admin-node/app/models/Assessment.js` (~12742 and ~13411) — only the **second** one is live (JS re-declares the method); the first is dead code, intentionally left untouched.

- **Chapters shipped but never worked — `@fastify/multipart` `fieldSize: 100` (fixed 2026-07-07).** The chapters feature above deployed clean but every candidate's chapter list still came back empty. Root cause: student-node's `index.js` registers `@fastify/multipart` with `limits.fieldSize: 100` (bytes) — a global cap on every multipart **text field**, not just files. `assessmentAssignedId`/`questionId` are UUIDs (~36 chars) so this ceiling was invisible for years; the `chapters` JSON field is the first field ever to exceed it, and `@fastify/multipart` **silently truncates** rather than erroring, so `answer_text` got cut off mid-question-1-text with no closing brackets — malformed JSON, `JSON.parse` in admin-node's `getAudioVideoProctoring` throws internally and is caught, returning `chapters: null`, indistinguishable from "no chapters stored." No error anywhere in the request path on either side. Fix: raised `fieldSize` to `1 * 1024 * 1024` (1MB, matching the library's own default). Verified live end-to-end post-deploy: minted a scoped JWT + posted a 346-byte `chapters` field through `POST /students/assessments/uploadAudio` on UAT, confirmed the full untruncated JSON round-tripped into `student_answers.answer_text`. **Interviews given between the chapters feature's deploy and this fix have permanently-truncated/lost chapter data** (the original full offsets only ever existed transiently in the candidate's browser) — no backfill possible, only the plain player works for those; new interviews are unaffected going forward.

- **Session-audio upload silently failed the DB write (fixed 2026-07-02).** The `questionId` sent with the full-session audio upload (see above) was the literal string `'ai_interview_full_session'` — not a UUID. `student_answers.question_id` is `uuid NOT NULL` with an FK into `assessment.questions`, so the Prisma insert threw; the handler's surrounding try/catch (`app/handlers/assessmentHandler.js` `uploadAudio`, intentionally non-fatal — audio upload must never block interview completion) swallowed it and still returned 200. Net effect: Oracle Object Storage upload genuinely succeeded (`audio/AI_Interview_audio_<assessmentAssignedId>-<ts>.webm` in the bucket) but **no row ever appeared in `student_answers`**, so admin's `getAudioVideoProctoring` (which just does `SELECT ... WHERE assessment_assigned_id = $1`) returned 404 and the Student Report's mic icon stayed empty — even though the recording existed. Fix: seeded a permanent placeholder row in `assessment.questions` (fixed id `a55c5db4-a546-41a4-b103-c17401e82b4e`, domain+type = existing `AI_Interview`/`AI_INT`, `is_active=false`) in every env, and `aiInterviewAPI.js` now sends that real UUID as `questionId`. `object_key` stored is the bare filename (no `audio/` folder prefix — matches the Communication/Paragraph-Reading convention already in the table). **4 UAT candidates backfilled** (2026-07-02) by cross-referencing `assessment_assigned_id`-prefixed objects already sitting in the `pl-uat-assessment` bucket under `audio/` against missing `student_answers` rows: `37c02d71-9b57-426a-bddd-7bcb1f67951d`, `51ede23f-2a12-4255-9869-b4ad3e8bf7c0`, `3d66bb04-203f-4603-a82c-e20264d90069`, `f89e30a3-bc64-4de4-bedc-40002793b4d6`. Earlier candidates (before the recording feature existed, or before this fix's UAT deploy) have nothing in the bucket to backfill — 404 for those is correct, not a bug.

- **Session recording was forward-only, no scrubbing/speed control — transcoded to MP3 (2026-07-03).** The uploaded full-session recording (see above) is raw `MediaRecorder` output — webm/opus on Chrome, mp4/aac on Safari — which `MediaRecorder` writes as a live stream with no duration header or seek index. Any player (including the admin Student Report's audio widget and a plain download) can only play it forward: no scrub-back, no playback-rate change. Fix: `student-node`'s `uploadAudio` handler (`app/handlers/assessmentHandler.js`) now detects this specific upload by its fixed placeholder `questionId` (`a55c5db4-a546-41a4-b103-c17401e82b4e`, same id used for the DB-write fix above) and re-encodes the buffer to a proper MP3 via a new `app/helpers/audioTranscode.js` (shells out to the system `ffmpeg` binary — `libmp3lame`, 128k — no new npm dependency) before it reaches Oracle Object Storage. `filename`/`mimetype`/`Content-Type`/`student_answers.object_key` all switch to `.mp3`/`audio/mpeg`. Best-effort: if ffmpeg fails, the original container is uploaded unchanged rather than losing the recording. Scoped to only this upload — Communication/Paragraph-Reading audio (different `questionId`s) are untouched and still store their native container. Requires `ffmpeg` in the `student-node` Docker image (`RUN apt-get install ... ffmpeg`, added to the Dockerfile alongside the existing chromium/libreoffice deps) — deployed DEV + UAT 2026-07-03. Recordings uploaded **before** this fix remain in their original webm/mp4 container (not retroactively transcoded).

- **Report PDF rendered non-English answers as tofu boxes — missing Indic fonts in the image (fixed 2026-07-06).** AI-Interview report PDFs (and the other Puppeteer-rendered report types) showed □□□ boxes for Tamil/Hindi/etc. answer + question text. The report is rendered by **Puppeteer/headless-Chromium** printing `public/aiInterviewReport.html` (`student-node` `Assessment.js` `generateAIInterviewReport`), and glyph coverage depends entirely on the fonts installed in the Docker image. Root cause: the image only ever got Indic **Noto** fonts *incidentally* via `libreoffice`'s recommended deps, and the report templates declared only `Inter`/`Arial` with **no Indic fallback** — so any image built slimmer / without those recommends lost every Indic + Nastaliq script and rendered tofu. AI Interview supports **14 response languages / 10 scripts** (enum source of truth: `admin-node/app/schemas/assessment.js` `responseLanguage`): English, Hindi, Hinglish, Tamil, Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, Odia, Assamese, Urdu. Two-part fix in `student-node`: (1) **Dockerfile** now explicitly installs `fonts-noto-core fonts-noto-ui-core fonts-noto-extra fonts-noto-color-emoji fonts-indic` (note: `fonts-noto-extra` carries **Noto Nastaliq Urdu** on bullseye — the standalone `fonts-noto-nastaliq-urdu` package does **not** exist there), guaranteeing all 10 scripts independent of libreoffice; (2) the 4 report templates (`aiInterviewReport.html`, `communicationReport.html`, `hinglishReport.html`, `roleBasedReport.html`) append a Noto Indic + Nastaliq fallback chain to the `body` font stack (additive — English still resolves to Inter/Arial first). **Because the real fix is fonts baked into the image, it only takes effect on an image rebuild** — a template-only change won't rescue an image lacking the fonts. Verified end-to-end: the rendered PDF embeds `NotoSans{Tamil,Devanagari,Telugu,Kannada,Malayalam,Bengali,Gujarati,Gurmukhi,Oriya}` + `NotoNastaliqUrdu` as subsetted fonts and shows clean glyphs for all scripts. Deployed **DEV + UAT 2026-07-06**; **PROD pending** (needs the student-node image rebuilt there — `~/autodeploy.sh` / no-cache build).

- **Scoring models — must exist in the LiteLLM gateway (gotcha, fixed 2026-06-27).** `routers/ai_interview.py` defines `GEMINI_MODEL = "gemini-2.5-pro"` (score-final, quality) and `GEMINI_FAST_MODEL = "gemini-2.5-flash"` (generate-question, score-turn, suggest-params — speed). Every `/ai-interview/*` LLM call must use one of these constants. **Do not hardcode a model string** — `score-final` had `model="gemini-3.5-flash"` hardcoded, a model group that does **not exist** in the LiteLLM gateway and has **no fallback group**, so litellm fell through to a direct Vertex AI attempt and 500'd on missing Google ADC creds. Symptom: AI interviews **completed but were never scored** — `assessment_assigned_students.calculation_error=true`, `calculation_attempts` maxed at 10, no `ai_interview_scores` row, blank report. question-gen/score-turn were fine because `gemini-2.5-flash` exists. Fix = use `GEMINI_MODEL`. If adding a new model, confirm it's a configured group in the gateway first. To recover a stuck row: reset `calculation_error=false, calculation_attempts=0, scores_calculated=false` and let the score cron retry (or call `aiInterviewHandler.runScoringForAssignment({assessmentAssignedId})` directly).

- **Confusion handling — reword at most once, then move on (changed 2026-07-10).** When a candidate answers with a confusion-shaped reply ("I don't understand", etc., `isConfusion()`), the interviewer rewords the current question **at most once** — `MAX_REFRAMES_PER_QUESTION` was reduced **2 → 1** (`student-node/app/handlers/aiInterviewHandler.js`). If the candidate is *still* confused by the reworded version, the code no longer reframes again; instead it advances to a **genuinely new parameter** and never issues a same-parameter depth follow-up (a `stillConfused` answer now suppresses `wantFollowup` — drilling into "I still don't get it" makes no sense). A new `last_answer_signal = "confused"` is emitted (alongside the existing `refusal`/`shallow`) so `generate-question` steers appropriately. Rationale: a perpetually-"confused" candidate could previously stall a single question through repeated rewordings; one reframe is enough before moving the interview forward. (Trailing-refusal / candidate-unwilling termination is unchanged and still ends the interview absolutely.) **Since 2026-07-31 this branch is also the first entry point for the Hinglish mid-interview language switch** — "I don't understand Hindi" matches `isConfusion()`, so the reframe call now carries `detect_language_change` + the candidate's utterance in `prior_turns`, and an honoured language switch pre-empts the reword (and does NOT consume the one reframe). See the language-switch entry above.

---

## File Reference

### 1. AI Engine (FastAPI)

#### Router — `ai_interview.py`
**Path:** `fastapi-ai-engine/routers/ai_interview.py`

**Endpoints:**

| Endpoint | Purpose |
|----------|--------|
| `POST /ai-interview/suggest-parameters` | Suggest skills / topics / seniority defaults from a job role |
| `POST /ai-interview/generate-question` | Generate next adaptive question (initial + follow-ups handled in one path, based on conversation history) |
| `POST /ai-interview/score-turn` | Score a single candidate turn (used during the interview for adaptive routing) |
| `POST /ai-interview/score-final` | Generate the final report — overall + category scores + recommendation |
| `POST /ai-interview/parse-resume` | Extract structured data from resume text |
| `POST /ai-interview/tts` | **Text-to-speech** — ElevenLabs Payal (Flash v2.5); auto-falls-back to Deepgram Aura-2 (`aura-2-thalia-en`). Body: `{ text, voice? }`. Returns audio bytes (mp3). |
| `POST /ai-interview/stt` | **Speech-to-text (REST)** — upload an audio file, Deepgram `nova-3` returns the transcript. |
| `WS   /ai-interview/stt-stream` | **Live STT bridge** — proxies browser mic frames to Deepgram `nova-3` live transcription, forwards interim + final transcripts back over the socket. |

**Key payloads:**

`GenerateQuestionsRequest`:
```python
jobRole: str
skills: List[str]
seniority: str
jobDescription: Optional[str]
domain: Optional[str]
numberOfQuestions: Optional[int] = 5
questionTypes: Optional[List[str]]  # technical, behavioral, situational, case_study
```

`EvaluateResponseRequest`:
```python
question: str
answer: str
questionType: Optional[str] = "technical"
jobRole: Optional[str]
skills: Optional[List[str]]
seniority: Optional[str]
domain: Optional[str]
expectedTopics: Optional[List[str]]
```

`GenerateReportRequest`:
```python
jobRole: str
skills: List[str]
seniority: str
domain: Optional[str]
jobDescription: Optional[str]
conversationHistory: List[Dict]  # [{question, answer, evaluation}, ...]
candidateName: Optional[str]
```

**AI Model Strategy:**
- Primary: Gemini 2.5 Pro via `genai.Client`
- Fast path: Gemini 2.5 Flash (`GEMINI_FAST_MODEL`) for question gen + score-turn (latency-sensitive paths)
- Fallback: Groq Llama 3.3 70B (`llama-3.3-70b-versatile`)
- Temperature: 0.3 (for consistency)
- PostHog tracking on all endpoints

**Voice Stack (TTS + STT):**

| Concern | Provider | Model / Voice | Env Var |
|---|---|---|---|
| TTS primary | ElevenLabs | `eleven_flash_v2_5` + voice **Payal** (`CpLFIATEbkaZdJr01erZ`, Indian female, hi/Indian-English, conversational) | `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_ID` |
| TTS fallback | Deepgram | `aura-2-thalia-en` (US English female) — used if `ELEVENLABS_API_KEY` is missing or the ElevenLabs call errors | `DEEPGRAM_API_KEY` |
| STT (file + live) | Deepgram | `nova-3` (REST `/stt` + WebSocket `/stt-stream`) | `DEEPGRAM_API_KEY` |

The `/tts` endpoint also accepts an optional `voice` body param — values starting with `aura` route to Deepgram; anything else is treated as an ElevenLabs voice ID. The Assessment-React frontend sends the admin-chosen `voice_id` from the session config (falls back to backend default when null). **Don't** hardcode an `aura-*` voice in the frontend `tts()` call — that forces the Deepgram path and silently overrides the admin's ElevenLabs voice selection (this was a bug, fixed 2026-06-25).

Source-code defaults in `routers/ai_interview.py` are `EXAVITQu4vr4xnSDxMaL` (Sarah / US English) for the voice ID and `eleven_flash_v2_5` for the model — these are only effective when the env vars are not set. All deployed environments (DEV today) override the voice to Payal via `.env`.

---

### 2. Admin Backend

#### Model — `AIInterview.js`
**Path:** `admin-node/app/models/AIInterview.js`

**`assignAIInterviewAssessment()`**
Parameters: `entityId, entityType, name, startTime, endTime, bulkUploadData, interviewConfig, allowProctoring`

In a transaction:
1. Finds `AI_Interview` assessment type (must exist — run migration first)
2. Finds or creates `AI_Interview` assessment domain
3. Calls FastAPI to generate initial questions
4. Creates `AssessmentSet` with `roleName` and `seniority`
5. Creates `AIInterviewConfig` with job role, skills, seniority, domain, JD, duration, follow-up settings
6. Creates assessment sections and stores generated questions
7. Creates `AssessmentInstituteMap` or `AssessmentCorporateMap`
8. Assigns each student via `AssessmentAssignedStudent`

**`startInterviewSession(assessmentAssignedId)`**
- Gets assignment with config
- Creates `AIInterviewSession` (status: IN_PROGRESS)
- Updates assignment status to INPROGRESS
- Returns session ID and initial screening questions

**`submitInterviewAnswer({ sessionId, questionId, candidateResponse, responseObjectKey })`**
- Creates `AIInterviewInteraction` record
- Sends to FastAPI for evaluation with conversation context
- Updates interaction with scores
- Generates follow-up if `needsFollowUp` is true

**`completeInterview(sessionId)`**
- Gets all interactions
- Calls FastAPI `/ai-interview/generate-report`
- Creates `AIInterviewScore` record
- Updates session to COMPLETED, assignment to COMPLETED

**`getInterviewProgress(assessmentAssignedId)`**
- Returns session status, question count, answered count, scores

#### FastAPIService methods
**Path:** `admin-node/app/service/FastAPIService.js`

| Method | FastAPI Endpoint |
|--------|------------------|
| `generateAIInterviewQuestions()` | `POST /ai-interview/generate-questions` |
| `evaluateAIInterviewResponse()` | `POST /ai-interview/evaluate-response` |
| `generateFollowUpQuestion()` | `POST /ai-interview/generate-follow-up` |
| `generateInterviewReport()` | `POST /ai-interview/generate-report` |

#### Routes
**Path:** `admin-node/app/routes/aiInterview.js`

| Method | Path | Handler |
|--------|------|--------|
| `POST` | `/ai-interview/assign` | `assignAIInterview` |
| `GET` | `/ai-interview/progress/:assessmentAssignedId` | `getAIInterviewProgress` |
| `GET` | `/ai-interview/results/:assessmentAssignedId` | `getAIInterviewResults` |
| `GET` | `/ai-interview/analytics/:assessmentMapId` | `getAIInterviewAnalytics` |
| `GET` | `/ai-interview/config/:assessmentSetId` | `getAIInterviewConfig` |

---

### 3. Student Backend

#### Model — `AIInterview.js`
**Path:** `student-node/app/models/AIInterview.js`

| Method | Purpose |
|--------|--------|
| `startInterview({ assessmentAssignedId })` | Create session, get initial questions from FastAPI, create interaction records |
| `submitAnswer({ sessionId, interactionId, candidateResponse, responseObjectKey })` | Evaluate response, generate follow-up if needed |
| `getNextQuestion({ sessionId })` | Get adaptive next question based on conversation history |
| `completeInterview({ sessionId })` | Generate final report, create score record, mark complete |
| `getInterviewStatus({ assessmentAssignedId })` | Get session progress |
| `getInterviewResult({ assessmentAssignedId })` | Get full completed interview data |

#### Routes
**Path:** `student-node/app/routes/aiInterview.js`

| Method | Path | Handler |
|--------|------|--------|
| `POST` | `/ai-interview/start` | `startInterview` |
| `POST` | `/ai-interview/submit-answer` | `submitAnswer` |
| `POST` | `/ai-interview/next-question` | `getNextQuestion` |
| `POST` | `/ai-interview/complete` | `completeInterview` |
| `GET` | `/ai-interview/status/:assessmentAssignedId` | `getInterviewStatus` |
| `GET` | `/ai-interview/result/:assessmentAssignedId` | `getInterviewResult` |

#### Final Scoring Pipeline (production truth)

Final scoring does **not** run on the candidate's request path. It is driven by the
generic assessment-scoring cron, the same one used for aptitude/communication:

1. `aiInterviewHandler.completeSession()` (`student-node/app/handlers/aiInterviewHandler.js`)
   marks the session `COMPLETED`, sets the assignment `submitted=true`, and flips
   `scores_calculated=false` whenever **at least one turn was answered** (see
   thresholds below).
2. `script/calculatePendingAssessmentCron.js` runs **every minute**, picks **one** pending
   assignment (`attempted=true, submitted=true, scores_calculated=false, is_processing=false`),
   atomically locks it (`is_processing=true`), and calls
   `Assessment.calculateAssessmentScore({ assessment_assigned_id })`.
3. For `assessmentType === "ai_interview"`, that delegates to
   `aiInterviewHandler.runScoringForAssignment()`, which calls FastAPI
   `POST /ai-interview/score-final` (Gemini `gemini-2.5-pro`) and persists one
   `ai_interview_scores` row (`overall_score`, `ai_recommendation`, `parameter_scores`,
   `strengths`, `weaknesses`, `executive_summary`, `recommendation_text`).
4. On success the cron sets `scores_calculated=true`. On error it increments
   `calculation_attempts`; after the max it sets `calculation_error=true` and **stops
   retrying** (so the row silently disappears from the cron's pickup query).

**Scoring threshold: unchanged bar, now applied to BOTH endings (2026-08-04).** The bar is
still `MIN_ANSWERS_FOR_SIGNAL = 4` answered turns (intro counts) **AND** ≥ **50% coverage** of
`totalExpected`, with the 4-answer floor capped at `totalExpected` so small configs stay
clearable. What changed is *who it applies to*: a **drop-off is now held to exactly the same
bar as an early exit**. Below it, the assignment is marked `scores_calculated=true` with **no
score row** — legitimately skipped, not an error — and the report shows the incomplete marker
plus the attempted questions. At or above it the interview is scored even though it is
partial, and `score-final` receives `completion_ratio` / `total_answered` / `total_expected` /
`completion_reason` so it grades what it actually got.

> A brief intermediate state on 2026-08-04 lowered the gate to "one answered turn is enough".
> That was **reverted the same day** — a 1-or-2-answer transcript produces a number that reads
> as a judgement of the candidate rather than of the coverage. Don't reintroduce it.

The rules live in `student-node/app/helpers/aiInterviewOutcome.js` —
`classifyInterviewOutcome(totalAnswered, totalExpected)` returns
`{isPartial, hasEnoughSignal, canScore}` and is the single source of truth shared by
`completeSession` and `finalizeAbandonedSession`. Pure, no I/O; unit tests in
`student-node/test/aiInterviewOutcome.spec.js` (11), one of which pins `canScore ===
hasEnoughSignal` across the whole 0–8 range so the two can't drift apart.

- `canScore` (the scoring gate) and `hasEnoughSignal` are deliberately the **same** bar.
- `isPartial` (`totalAnswered < totalExpected`) is **independent** — an interview can be
  partial *and* comfortably scorable, which is the whole point of the recruiter marker.
- `session_metadata.interviewIncomplete` stores `!hasEnoughSignal` and remains the
  **candidate-facing** flag, so `AIInterviewReportCard.js` behaves exactly as it always has.
  Recruiter surfaces read `partialInterview` instead.

- **Drop-offs are now finalized and scored (2026-08-04).** A candidate who closes the tab
  never reaches `completeSession`, so the session row kept **no terminal metadata** (status
  stuck at `INPROGRESS`) and the assignment stayed `submitted=false` — which the score
  sweeper's `submitted: true` filter excludes. Net effect: an abandoned interview produced
  **no report at all**, even one where the candidate had answered 7 of 8 questions, and the
  Download button stayed greyed (`checkReportAvailability` needs a score row). Fixed by
  `aiInterviewHandler.finalizeAbandonedSession(assessmentAssignedId)`, called from
  `script/updateDropoutStatusCron.js` right after the `DROPOUT` flip. It writes the same
  terminal metadata `completeSession` writes (`status='ABANDONED'`, `completedAt`,
  `totalDuration`, `interviewIncomplete`, `partialInterview`, `totalAnswered`,
  `totalExpected`, `completionReason:'dropout'`), so **a drop-off and an early exit render
  identically**. Idempotent — a session already carrying a `completionReason` is left alone.
  - The assignment deliberately **stays `status='DROPOUT'`, `submitted=false`**. Flipping
    `submitted` would have let the change reuse the existing score queue, but it would also
    have silently moved every dropout into the completion-rate dashboards. So the cron calls
    `runScoringForAssignment()` **directly**, serially (concurrent `$queryRaw` panics on
    ARM64 — see the Prisma gotcha), each row in its own try/catch.
  - **Retry sweep.** Once flipped to `DROPOUT` a row no longer matches the cron's
    `INPROGRESS` selection, so a single transient scoring failure would strand the report
    permanently. `retryAiInterviewDropoutScoring()` runs at the **top** of each cron pass
    (before anything new is flipped, so a retry isn't immediately re-attempted in the same
    run) over `status='DROPOUT' AND scores_calculated=false AND
    session_metadata->>'completionReason' = 'dropout'`, capped at 50.
  - That `completionReason='dropout'` predicate is also what scopes this to **new drop-offs
    only** — historical dropouts carry no such metadata and are intentionally never picked
    up. **No backfill was run** (deliberate: one `gemini-2.5-pro` call per row).
  - **The coverage bar gates drop-offs exactly as it gates early exits** — a drop-off with
    fewer than 4 answers (or under 50% coverage) is finalized and marked, but **never sent to
    the scorer**. `finalizeAbandonedSession` returns `canScore` and the cron `continue`s on
    false, so no LLM call is made. The retry sweep re-derives the same verdict from the stored
    counters via `classifyInterviewOutcome`, so it can't resurrect a below-bar row either.
  - `runScoringForAssignment` no longer short-circuits on the `interviewIncomplete` flag —
    the bar is enforced by its callers through `scores_calculated`, so anything reaching it is
    meant to be scored (its own `noAnswers` guard remains as a backstop).
  - `submitAnswer` now rejects `ABANDONED` as well as `COMPLETED`, so a client that wakes up
    after the cron finalized a session cannot append a turn to an already-graded transcript.
  - Live **DEV + UAT 2026-08-04**; PROD pending.

- **Recruiter report: partial-interview marker + attempted questions (2026-08-04).** The
  "Interview Not Completed" banner used to **replace** the score card entirely, so an
  unfinished interview showed a recruiter nothing actionable. It now sits **above** the score
  rather than instead of it, because a partial interview that clears the coverage bar IS
  scored. Below the bar there is no score and the banner plus the attempted questions are the
  whole report — which is still far more than the nothing a drop-off used to produce.
  - **New flag `session_metadata.partialInterview`** = `totalAnswered < totalExpected`,
    surfaced by `admin-node` `getReportByAssignment` (falls back to `interviewIncomplete`
    for sessions finalized before the flag existed). Distinct from `interviewIncomplete`:
    `partialInterview` does **not** imply the absence of a score. No DB migration —
    `session_metadata` is already jsonb.
  - **Admin UI** (`admin-react` `StudentReport/index.js`): banner wording now distinguishes a
    drop-off ("did not return to finish this interview — it was closed automatically") from a
    deliberate early exit, and states "X of Y questions were answered". Three new render
    helpers — `renderAIInterviewCandidateCard` (extracted so the scored and unscored branches
    share it), `renderAIInterviewIncompleteBanner`, `renderAIInterviewTranscript`.
  - **New "Questions attempted" section.** The admin modal **never rendered a transcript at
    all**, despite the old banner copy literally saying "the transcript below shows what was
    captured". `getReportByAssignment` had always returned `transcript`; nothing consumed it.
    Now rendered on both branches (keyed on the stable `interactionId`).
  - **PDF** (`student-node/app/models/Assessment.js` `generateAIInterviewReport` +
    `public/aiInterviewReport.html`): amber `.incomplete-note` block above the score strip,
    header reads "Questions answered: **3 of 8**", and the score strip is now wrapped in
    `{{#if hasScore}}`. **That last one was an active bug** — `const score = session.scores?.[0] || {}`
    meant an unscored session rendered a confident **`0` / "Not Fit"** hero, a wrong number on
    the artefact a recruiter forwards, not merely a missing one. The `{{else}}` branch shows a
    "Not scored" note instead.
  - **Candidate side is deliberately untouched.** `AIInterviewReportCard.js` still gates on
    `interviewIncomplete`, whose meaning was preserved exactly, so candidates see what they
    always saw and are never shown a partial score. Partial scores are recruiter-only.
  - **Three distinct "no score" messages**, on both the admin banner and the PDF's `Not
    scored` block, driven by `notScoredReason`: nothing answered / below the coverage bar (no
    score will *ever* come) / scorable but not yet landed. Conflating the last two is the easy
    mistake — a recruiter told to "check back shortly" for a below-bar interview waits forever.
  - **GOTCHA — the Excel export blanked Score/Verdict for drop-offs while the report showed
    both (fixed 2026-08-04).** Two independent gates in `admin-node/app/models/Assessment.js`,
    both keyed on the wrong signal, and each sufficient on its own to blank the cells:
    1. The score enrichment inside `getAssessmentDetails` runs under `if (is_submitted)`. A
       drop-off deliberately keeps `submitted=false` / `status=DROPOUT`, so
       `aiInterviewScores` came back **`undefined`** — the row was never enriched at all.
    2. `exportStudentData` fills score cells only when the status label is `"Completed"`; a
       drop-off is labelled `"Dropped Off"`, so even an enriched row would have been blanked.
    Fix: the export keys the AI Interview cells off **a score actually existing**
    (`typeof aiInterviewScores?.overallScore === "number"`) rather than off the status label,
    and **AI Interview is enriched unconditionally** — see the rule below. Applied to **both**
    the college and corporate paths (they are separate ~1000-line blocks that drift; always
    check both). No other assessment type changes behaviour. Same change also fixes the blank
    Score column for drop-offs in the on-screen CandidateList, which reads the same enrichment.
    **Note the `typeof === "number"` test is load-bearing**: a legitimately-scored drop-off can
    have `overall_score = 0`, and a truthiness check would blank it.

- **RULE — never gate AI Interview score enrichment on the assignment flags (2026-08-04).**
  Gating on `is_submitted` was first patched to `is_submitted || is_attempted` to cover
  drop-offs; that was still wrong. Rows exist with a **finalized `ai_interview_scores` row**
  whose assignment has `submitted=false` **AND** `attempted=false` (seen on DEV:
  `vedantmnadhe+demob1/2/3/7@gmail.com`, `status=COMPLETED`, scores 84/76/64/49). The report
  (`getReportByAssignment`) and the PDF (`generateAIInterviewReport`) both read the session +
  score row **directly and never consult these flags**, so every such row renders marks on
  screen and in the PDF while the Excel cells come out empty — the exact "report shows it,
  Excel doesn't" bug, reported repeatedly and mis-diagnosed twice as a drop-off-only issue.
  The flags simply cannot be made to agree; `is_submitted || isAIInterviewAssessment` is the
  guard, i.e. always enrich for this type. Costs one indexed lookup per candidate and yields
  the pre-existing empty shape when there is no score.
  **Diagnostic that finds these instantly** — any row where the export and the report can
  disagree:
  ```sql
  SELECT aas.primary_email, aas.status, aas.submitted, aas.attempted, sc.overall_score
  FROM assessment.assessment_assigned_students aas
  JOIN assessment.ai_interview_sessions s ON s.assessment_assigned_id = aas.assessment_assigned_id
  JOIN assessment.ai_interview_scores sc ON sc.session_id = s.id
  WHERE aas.submitted = false;
  ```
  - **Download button needs no change** — `checkReportAvailability`'s AI_Interview branch
    already requires `(submitted || attempted)` + a score row, and the dropout cron sets
    `attempted=true`. It ungreys by itself once scoring lands. A below-bar interview never gets
    a score row, so its Download stays greyed — same as a below-bar early exit always has.

- **GOTCHA — a missing model field in `score-final` 500s ALL scoring → silent queue backlog (regression seen + fixed 2026-06-30).** `ScoreFinalResponse` had several **required** fields (`executive_summary`, `recommendation_text`, `strengths`, `concerns`, `parameter_scores`). When the score-final **prompt JSON template** stopped listing one of them (a `score_rationale` edit accidentally *replaced* the `executive_summary` line instead of inserting alongside it), Gemini stopped emitting that field and **every** score-final call raised `pydantic ValidationError … executive_summary Field required [missing]` → HTTP 500. Effect: interviews **completed but never scored** — in async mode the calc worker logged `[CALC WORKER] NON-TRANSIENT fail … Failed to score interview` and rows piled up `scores_calculated=false`. Two-part fix: (1) keep every field in the prompt template, AND (2) **defensive defaults** after the verdict/score guardrails fill any missing `executive_summary` / `recommendation_text` (from `score_rationale`) and coerce `strengths`/`concerns`/`parameter_scores` to `[]`, so a single absent model field can never again 500 the whole call. **Rule:** when editing the score-final response shape, change the Pydantic model, the prompt JSON template, AND the defensive defaults together.

- **GOTCHA — BullMQ stable-jobId dedup blocks the sweeper from retrying a "completed-but-failed" row (2026-06-30).** Async scoring uses `jobId = calc__<assessment_assigned_id>` (stable, so duplicate submits/sweeper re-enqueues collapse onto one job). The calc worker does **not throw** on a scoring failure — it releases via DB flags so BullMQ marks the job **completed** (retained by `removeOnComplete: {count: 500}`). The per-minute sweeper then re-`add`s the same jobId, but **BullMQ treats an `add` with an existing jobId as a no-op** — so a row that failed scoring (e.g. the 500 above) but whose BullMQ job "completed" is **never re-run**, even though `scores_calculated=false`. Symptom: `[SCORE SWEEPER] enqueued N` every minute yet the queue shows `wait=0 active=0` and N rows stay pending forever. (Harmless in normal operation — successful scoring sets `scores_calculated=true`, so the sweeper never re-enqueues; it only bites when a job completes while scoring failed.) **Recovery:** fix the underlying scoring error, then either `calculationQueue.clean(0, 1000, 'completed')` so the sweeper can re-enqueue, or — most reliable — score each stuck row directly, bypassing BullMQ:
  ```
  docker exec student node -e 'require("/app/app/handlers/aiInterviewHandler").runScoringForAssignment({assessmentAssignedId:"<id>"}).then(r=>console.log(r)).then(()=>process.exit(0))'
  ```
  (UAT calc queue env: `CALCULATION_ASYNC=true`, `REDIS_URL=redis://172.17.0.1:6379`; `QUEUE_ENV` is unset → defaults to `dev` → queue name `assessment-calculation-dev`. Inspect with `docker exec redis redis-cli ZCARD bull:assessment-calculation-dev:completed`.)

- **"Why this score" rationale line under the report (2026-06-30).** Every report now includes
  a one-or-two-line plain-English statement below the per-parameter reasons that explains
  the numeric score and the verdict in human terms — e.g. *"Scored 57/100 — Not Fit: answers
  were scripted and lacked real depth."* or *"Scored 82/100 — Strong Fit: clear, example-backed
  answers across all areas."* Built into the FastAPI `score-final` schema as a mandatory
  `score_rationale` field, with a deterministic `Scored X/100 — <verdict>.` fallback after the
  post-guardrail logic so the report always has something to show. Storage uses the existing
  `ai_interview_scores.detailed_feedback` column (previously an unused duplicate of
  `executive_summary` — returned to no frontend). Rendered as a highlighted **"Why this
  score"** card in both `admin-react` (`AIInterviewReport.js`) and `Assessment-React`
  (`AIInterviewReportCard.js`), positioned directly under the per-parameter reasons and above
  the recommendation block. Always populated for new interviews; pre-existing scored rows
  retain their old text until re-scored.

#### Gotcha — corporate candidates with no student profile (fixed 2026-06-12)

`Assessment.calculateAssessmentScore()` called `getFullName(primaryEmail)`
**unconditionally before** the assessment-type branch. `getFullName()` reads the student
micro-service profile and **throws `"Student not found"`** when none exists. AI-interview
candidates are **corporate applicants invited by email** (e.g. `name+alias@…`) who often have
no student profile in that DB — so scoring threw before ever reaching the `ai_interview`
branch (which never uses `full_name`). The cron classified it as non-transient, retried 3×,
then set `calculation_error=true` — leaving completed interviews permanently unscored.

**Fix:** compute `assessmentType` first, then make `getFullName()` non-fatal for
`ai_interview`/`ai-interview` (the original throw is preserved for every other type). Also
added an `ai_interview` case to `resetForRecalculation` (it previously fell through to the
communication-scores fallback and timed out the Prisma transaction), so manual recalc now
deletes `ai_interview_scores` cleanly.

**To re-score a stuck interview:** clear the flags on `assessment_assigned_students`
(`scores_calculated=false, is_processing=false, calculation_error=false,
calculation_attempts=0`) — the cron re-picks it within ~1 minute.

#### Gotcha — report/UI showed the email instead of the candidate name (fixed 2026-06-12)

Root cause of the **same** missing-profile problem: `assignAIInterviewAssessment()`
(`admin-node/app/models/Assessment.js`) **skipped student-account creation** — by design it
was "OTP-invite-only, no portal accounts". But every name lookup (the report header in both
`getReport` / `getReportByAssignment`, and the admin StudentReport modal + client-side PDF)
joins `student_personal_profile → students` by `primary_email`. With no profile row, the name
resolved to empty and the UI fell back to the **raw email** — so the report showed
`email — email` where `name — email` belongs.

**Fix (the right one, not a display patch):** AI-interview assignment now creates a student
profile for each **new** candidate exactly like the other corporate/college assessment types
(Aptitude / Communication / Role-Based all call `studentService.createPublicStudent`), using
the `first_name`/`last_name` already present in `bulkUploadData`. `skipActivationEmail` follows
the entity (see the invite-delivery split below). Payload lives in the pure, unit-tested helper
`admin-node/app/helpers/aiInterviewStudentPayload.js`. No change to the report code — the name
now resolves naturally from the profile.

#### Gotcha — closing-screen greeting showed the assessment name, not the candidate (fixed 2026-07-01)

The `STEP_DONE` closing screen in `Assessment-React` `AIInterview/interview.js` built its
greeting name from `sessionStorage.getItem('assessment_invite_name')`. But that key
legitimately holds the **assessment title** — `InviteStart.js` stores `assessmentName` there
on purpose, and `Invite/InviteAssessmentRunner.js` reads it as "the real assessment name."
So the farewell rendered **"Thanks for your time, &lt;Assessment Name&gt;."** (e.g. "…, Google
Software Engineer Assessment.") instead of the candidate's first name.

**Fix:** the greeting now derives from the candidate identity the backend already returns —
`getReport` (`student-node/app/handlers/aiInterviewHandler.js`) sends `candidateName` +
`candidateEmail` in the report payload, which `interview.js` already holds in `report`. The
new fallback chain is: `report.candidateName` → `report.candidateEmail` → legacy
`ai_interview_candidate_email` session key → clean nameless greeting ("Thanks for your
time."). The backend's `"Candidate"` default is filtered out so a nameless record shows the
no-name greeting rather than "Thanks for your time, Candidate." No backend change was needed
— `getReport` already resolves the real name from `student_personal_profile → students`.

**Rule:** `assessment_invite_name` / `INVITE_SESSION_KEYS.name` is the assessment title, never
a person's name — don't reuse it for candidate-facing greetings.

#### Quick Summary line removed — unsubstantiated claim (fixed 2026-07-16)

The `STEP_DONE` closing screen's "Quick Summary" showed 4 bullet lines. 3 are backed by real
data (questions answered, transcription status, duration); the 2nd — "Examples and detail
came through in your answers." — was a hardcoded string with no signal behind it, shown to
every candidate regardless of actual answer quality. Removed from the `summaryLines` array in
`Assessment-React/src/modules/Assessments/Partials/AIInterview/interview.js`. DEV+UAT live.

**Deploy gotcha hit while shipping this:** Assessment-React's GitHub Actions self-hosted
runner fires a `notify.sh "Deployment Started"` on every push to `Development`, but on the
DEV box that hook does **not** reliably rebuild/restart the actual serving container
(`assesment`, port 3006) — the bundle stayed stale after the notify fired and the process
exited. Don't trust the notify hook alone; verify the live bundle (`docker exec assesment
grep -rl "<changed string>" /app/build`) and manually `docker build --no-cache --build-arg
ENVIRONMENT=dev -t assesment:frontend .` + swap if stale, same as the documented UAT
`auto_deploy.sh` recipe.

#### Invite delivery splits by entity type — OTP for corporate, portal for institute (2026-06-17)

`assignAIInterviewAssessment()` (`admin-node/app/models/Assessment.js`) was OTP-invite-only for
**every** AI Interview, regardless of who it was assigned to. It now branches on `isCollege`
(derived from `entityType` ∈ `college`/`institute`/`university`):

- **Corporate** (`!isCollege`) — unchanged passwordless flow. Fires the
  `sendAssessmentInviteEmail(..., assessmentType: "AI_Interview")` OTP invite per candidate, and
  the student account is created **silently** (`skipActivationEmail: true`) so the OTP invite is
  the candidate's only email. Candidate authenticates with the 6-digit OTP and runs the
  interview straight from the invite link — see [otp-invite.md](otp-invite.md).
- **Institute** (`isCollege`) — **no OTP invite**. Uses the normal student-portal flow like
  Aptitude / Communication institute assignments, and splits emails **by new-vs-existing**
  exactly like `assignCommunicationAssessment`:
  - **New** candidates → only the **account-creation/activation email**, sent by
    `createPublicStudent` (`skipActivationEmail: false`, now `!isCollege` in
    `aiInterviewStudentPayload.js`). They do **not** also get a reminder. **Gotcha
    (fixed 2026-06-17):** student-node `createPublicStudent` **requires `degreeStreamMap`
    (`degreeId` + `streamId`) for non-corporate students** — without it `POST /students`
    returns `400 "degreeId and departmentId is required"`, the account is never created,
    and **no activation email is ever sent** (corporate skips this — the check is gated on
    `!isCorporate`). `aiInterviewStudentPayload.js` therefore populates `currentCourse` +
    `degreeStreamMap` from the upload's `degree`/`department` objects
    (`cand.degree?.degreeId || cand.degree_id`, `cand.department?.streamId || cand.stream_id`),
    exactly like the customAssessment / communication institute flows. **Second gotcha
    (fixed 2026-06-17):** the institute payload must **not** set `student.currentState = 1`.
    `current_state >= 1` marks a student as already-onboarded, so the activation email's
    `/onboarding/activate/:studentId` link **bounced to login instead of the account-setup
    flow**. Institute now omits `currentState` (student-node defaults `current_state` to 0 →
    onboarding runs), matching communication/customAssessment; only the corporate OTP path
    keeps `currentState: 1` (it never uses portal onboarding).
  - **Existing** candidates (already have a portal account) → only the standard
    **assessment-reminder email** via `this.sendRemindersToStudents(assessment.id, "college",
    existingUsers, …)`. No activation email (they're already activated).

#### Corporate OTP invite email — role name, dynamic duration, layout (fixed 2026-07-11)

The shared OTP invite template (`admin-node/app/helpers/assessmentInviteEmail.js`, used for
every `assessmentType`, not just `AI_Interview`) had three bugs specific to the AI Interview
copy:
1. **Role missing when adding/resending on an EXISTING assessment.** The create-new-assessment
   path (`assignAIInterviewAssessment`) always passed `role: roleName` correctly, but the two
   flows that operate on an assessment that already exists —
   `_addStudentsToOneTimeAssessment` (admin's "add student to existing assessment") and
   `resendInvitesToStudents` — hardcoded `role: null` because neither has `interviewConfig` in
   scope. Fixed with a new `Assessment._getAiInterviewEmailMeta(assessmentAssignedId)` (raw join
   `assessment_assigned_students → assessment_sets → ai_interview_config`, best-effort/never
   throws) called from both, gated on `assessmentType(Name) === "AI_Interview"`.
2. **Duration was hardcoded "about 25 minutes"** in the email tip regardless of the admin's
   configured `interviewDuration`. `buildHtml`/`sendAssessmentInviteEmail` now take
   `durationMinutes` and render "This interview takes about N minutes." dynamically (omitted if
   unavailable — no more false 25-min fallback). Threaded through all 4 AI Interview send paths:
   sync create (`assignAIInterviewAssessment`, from `interviewConfig.interviewDuration`), async
   create (`assignAIInterviewAssessmentAsync` stores `configSnapshot.interviewDurationSec`,
   `assignmentWorker.js` reads it back), add-to-existing and resend (via the new
   `_getAiInterviewEmailMeta` lookup — `interview_duration` is stored in seconds, converted to
   minutes with `Math.round(.../60)`).
3. **Duration + end-date now render ABOVE the CTA button** (`buildHtml`'s `durationLine` /
   `deadlineLine`, moved from below the "copy link" text to above the "Start AI Interview"
   button) — candidate sees the commitment (how long, by when) before clicking through, not
   after. This reorder applies to the shared template for every `assessmentType`, not just
   AI_Interview (only the duration line itself is AI_Interview-gated).

Scope note: this only covers the **corporate OTP invite** path (`isCorporateOtpInvite`).
Institute/college AI Interview assignments don't use this template at all (see the
entity-type split above) — they get the normal student-portal activation/reminder emails,
untouched by this fix. DEV+UAT live.

**Follow-up (2026-07-14): end time in IST on the deadline line.** The "Please complete the
interview by" line now shows date **+ time (AM/PM), labelled IST**, not date-only. Critical
detail: AI Interview `end_time` (and the corporate map `end_time`) is stored as **IST
wall-clock digits in a UTC `:00Z` field** (the `combine()`/`combineDateTime()` convention —
6 PM IST is persisted as `18:00:00Z`). So every send path formats it with
`moment.utc(...).format("DD MMM YYYY, hh:mm A [IST]")` — `moment.utc` reads the stored digits
back as-is and the `[IST]` literal labels them; a plain `moment()` would re-convert and break
on any non-UTC host (UAT/PROD app containers happen to be UTC today, so plain moment looked
fine, but it was fragile). Four paths: sync create (`endDateTime`), add-to-existing (AI-only
override from `assessmentMap.endTime`), resend (`_getAiInterviewEmailMeta` now also returns
`acm.end_time` since `assessmentInfo.endDate` was date-only), async worker
(`configSnapshot.endDateLabel` pre-formatted, worker prefers it over date-only `cfg.endDate`).
Non-AI corporate-OTP emails keep their existing date label (the IST reformat is AI-gated).
Note: on UAT `ASSIGNMENT_ASYNC_TYPES`/`ASSIGNMENT_ASYNC_ENABLED` are empty → AI Interview
assign runs the **sync** path, not the queue worker.

  New-vs-existing is determined by a `student_personal_profile`/`students` lookup on the
  candidate emails (`newUsers` / `existingUsers`). The reminder links to the student portal
  (`/onboarding/activate/:studentId` or `/login`); the candidate logs in and takes the AI
  Interview from inside the authenticated portal. The reminder send is wrapped in try/catch so a
  reminder failure never aborts the assignment.

  - **Gotcha — blank "From" (was "Sender") in the institute reminder, async path (fixed 2026-06-30):**
    when `ASSIGNMENT_ASYNC_ENABLED=1`, AI_Interview assignment runs through the queue
    (`assignAIInterviewAssessmentAsync`), not the sync `sendRemindersToStudents`. The async job's
    `configSnapshot` carried `companyName` but **no `entityName`**, and for a college it only
    resolved the campus **id** (`instituteCampusId`), never the campus **name**. The reminder
    worker (`admin-node/app/queues/assignmentWorker.js`) reads `college_name: cfg.entityName`, so
    the invite email's entity row rendered **blank**. Fix: `assignAIInterviewAssessmentAsync`
    (`Assessment.js`) now also selects `campus_name` for college / corporate `name`, sets
    `entityName` in the snapshot, and the worker falls back to `cfg.entityName || cfg.companyName`.
    Same change renamed the template label `Sender:` → `From:` and dropped the dangling colon on
    the `Assessment Details` heading (`user-management-node/src/utils/emailTemplates/assessmentRemainder.js`).

Net: corporate candidates get **one** email (OTP invite); institute candidates get **one**
portal email each — activation for new students, reminder for existing — and never see the OTP
screen. (Earlier the institute branch wrongly sent the reminder to *all* candidates, so new
students got a reminder instead of their activation email — fixed 2026-06-17 to match
Communication.)

Forward-looking only: candidates assigned **before** this fix still lack a profile (no upload
names are stored to backfill from). If names are missing from the upload, the profile is
created without them (same as other types) and the report shows the email until a name exists.

---

#### Resend invite must NOT re-roll the assessment set (fixed 2026-08-04)

**The assessment_set IS the AI Interview configuration.** `ai_interview_config` is 1:1 with
`assessment_set_id` and holds `job_role`, `job_description`, `skills[]`, `seniority`,
`interview_duration`, `max_questions` and `stage_config.language` (the Hinglish / Hindi /
Marathi / Tamil selector read by `student-node/app/helpers/aiInterviewLanguage.js`). There is
no per-candidate copy of any of it.

`Assessment.resendInvitesToStudents` ("Resend invite" on dropped-off candidates) used to hand
each candidate a **random different set**, filtered only on `assessment_type_id +
assessment_domain_id + is_active` (plus `cefr_level` / `difficulty` / `accent` when non-null).
That filter was written for **Aptitude**, where ~10k sets in one domain really are
interchangeable question banks. For AI Interview it is catastrophic: on PROD **all 192 active
AI_Interview sets sit in one domain and 191 share `accent='en-IN'` with NULL cefr/difficulty**,
so the candidate pool was "every AI Interview ever created, for every company" — 87 distinct
job roles, 5 languages. A resend therefore moved candidates onto another company's interview:
**different job role AND different spoken language** (e.g. a "Business Development Manager /
Hinglish" campaign resent as "Investment Banking Analyst / English").

Nothing surfaced the swap: the invite email is built **after** the re-roll, and
`_getAiInterviewEmailMeta` joins through the *new* `assessment_set_id`, so the email
confidently advertised the wrong role instead of erroring.

Fix (`admin-node/app/models/Assessment.js`):
- `CONFIG_BOUND_SET_TYPES = { AI_Interview, Role_Based, Custom_Assessment }` — types whose set
  carries campaign configuration (`Role_Based` → `role_name`/`seniority` on the set;
  `Custom_Assessment` → `custom_config_set_map`). A resend for these **keeps the assigned set**
  and only resets the attempt. Question-bank types (Aptitude, Communication, Hinglish,
  Behavior) keep the fresh-set behaviour, which is the point of the feature.
- The attempt-state reset moved out of the per-assignment set loop into a single `updateMany`,
  so an assignment whose set has since been deactivated still gets reset instead of being
  silently skipped by the loop's `continue`.
- An AI_Interview resend now also deletes the abandoned `ai_interview_interactions`,
  `ai_interview_scores` and `ai_interview_sessions` rows. **These three tables carry no foreign
  keys, so nothing cascades** — they must be deleted explicitly, children first, and admin-node
  reaches them by raw SQL (it has no Prisma models for them; same as `_getAiInterviewEmailMeta`).
  Previously the reset flipped the row to PENDING while the old session survived, and the
  report / TPO dashboard kept reading it.

Regression cover: `admin-node/test/resendInvitesSetPreservation.spec.js`.

**Not backfilled.** Candidates already mis-assigned by a pre-fix resend keep the wrong set until
someone repoints `assessment_assigned_students.assessment_set_id` back to the campaign's set.
To find them, group a campaign's assignments by `assessment_set_id` — a single campaign should
only ever have one for AI Interview.

---

## Database Tables

| Table | Purpose |
|---|---|
| `ai_interview_config` | Per-assessment-set interview configuration: job role, skills, seniority, duration, AI model, evaluation criteria. **1:1 with the set — the set IS the campaign config, never swap it on a resend** |
| `ai_interview_sessions` | Per-student session: status (PENDING/IN_PROGRESS/COMPLETED), start/end times, duration, metadata |
| `ai_interview_interactions` | Per-question interaction log: question text, response, score, AI evaluation, follow-up tracking |
| `ai_interview_scores` | Final scores: overall, technical, behavioral, communication, problem-solving, recommendation, strengths, weaknesses |

### Schema Relationships

```
AssessmentSet
  └─ AIInterviewConfig (1:1)

AssessmentAssignedStudent
  └─ AIInterviewSession (1:many)
       ├─ AIInterviewInteraction (1:many)
       └─ AIInterviewScore (1:many)
```

### Key Fields

**AIInterviewConfig:**
- `job_role`, `seniority`, `skills[]`, `industry_domain`
- `job_description` (full JD text for context)
- `interview_duration` (seconds; admin-react create-form default 900s/15min, admin-node INSERT fallback 1500s/25min if omitted). admin-react range was 15–30 min (946e9a19, 2026-06-30), **loosened back to 10–30 min (2026-07-07)** — default still 15. No backend clamp on the value; `interview_duration` is stored as-sent.
- `enable_follow_up` (boolean, default true)
- `ai_model` (e.g., "gemini-2.5-pro")
- `evaluation_criteria` (JSONB for custom weight overrides)
- `scoring_guidance`, `question_guidance` (free-text admin guidance injected into score-final / generate-question prompts — see Orchestration)
- `voice_id` (ElevenLabs voice_id the AI narrator speaks in; admin-selectable, null → backend default)

**AIInterviewInteraction:**
- `question_type`: TECHNICAL, BEHAVIORAL, SITUATIONAL, CASE_STUDY
- `score`: 0–100 overall weighted score per response
- `ai_evaluation`: JSONB containing `{ technicalAccuracy, depthOfKnowledge, communicationClarity, problemSolving, strengths, areasForImprovement, needsFollowUp }`
- `is_follow_up`: boolean, true if this was a follow-up question
- `parent_interaction_id`: links follow-up to original question

**AIInterviewScore (`ai_interview_scores`):**
- `overall_score`: 0–100 weighted final score, recomputed in code from `parameter_scores` ratings + config weights (see verdict section above) — not trusted as-returned from the LLM
- `ai_recommendation`: `Strong Fit` | `Fit` | `Borderline` | `Not Fit` (not `strong_hire`/`hire`/`maybe`/`no_hire`)
- `parameter_scores`: JSONB array, one entry per evaluation parameter — `{ id, name, rating (0-5), rating_label, analysis, supporting_quote, not_assessed }`. `rating_label` ∈ `Excellent`(5) / `Strong`(4) / `Adequate`(3) / `Concern`(2) / `Weak`(1) / `No Response`(0) / `Not Assessed` (uncovered parameter — rating backfilled to the rounded average of covered parameters, never a hard 1/5)
- `strengths`, `weaknesses`: JSONB arrays of `{ claim, quote }`
- `executive_summary`, `recommendation_text`: prose fields from score-final
- `detailed_feedback`: "why this score" one-liner (`score_rationale`), e.g. *"Scored 57/100 — Not Fit: answers were scripted and lacked real depth."* — repurposed column, previously an unused duplicate of `executive_summary`

There is no separate `technical_score`/`behavioral_score`/`communication_score`/
`problem_solving_score` — per-category scoring lives entirely in `parameter_scores`,
keyed by the admin's configured evaluation parameters (which vary per assessment).

---

## Data Export (Excel)

The institute-admin panel supports **exporting AI Interview assessment results to Excel** via `POST /assessment/exportStudentListForAssessment/:instituteId` (handled by student-node `TpoDashBoard.exportExcelOfStudentListForAssessment`). The export **now correctly identifies AI Interview assessments** (as of 2026-06-19) and produces interview-specific columns:

| Column | Type | Source |
|---|---|---|
| Candidate Name | String | Student name from profile |
| Email | String | Candidate email |
| Degree | String | Course degree |
| Department | String | Course department |
| Assmt. Taken On | Date | Assessment submission date (DD/MM/YYYY) |
| Taken / Sent | String | X/Y count |
| **Overall Score** | Integer | `ai_interview_scores.overall_score` (0–100) |
| **[Parameter Name] (/5)** | Integer | Per-parameter rating from `ai_interview_scores.parameter_scores[*].rating` (1–5 scale) — one column per unique parameter across all candidates |
| Proctoring | String | Good / Bad |

**Key points:**
- **Type detection:** The export resolves the assessment type from the returned data (prefers `assessmentType` on each student record) rather than relying on the request parameter, so an empty/wrong `assessmentType` input does not fallback to a Communication-style report.
- **No suggestions:** The export includes only the overall score and parameter ratings. Analysis/recommendation text from `parameterScores[*].analysis` and `recommendation_text` are **intentionally excluded** to keep the Excel lightweight and focused on scores.
- **Dynamic columns:** Parameter names are collected as the union across all students, preserving first-seen order. Parameter names are title-cased and space-separated in column headers (e.g. `"role_fit"` → `"Role Fit (/5)"`).
- **Gotcha fixed (2026-06-19):** Previously, the export was missing the `aiInterviewSessions → scores` include in the assignment query, so the scoreMap never saw AI Interview data. The export would silently fall through to the Communication branch, producing Reading/Listening/Speaking/Writing columns and a `-` score. This is now fixed — assignments are queried with the session + score includes, and the scoreMap builds correctly for AI interviews.

---

## Migration

**SQL migration file:** `admin-node/migrations/add_ai_interview_tables.sql`

Creates:
1. Seeds `AI_Interview` assessment type and domain
2. `ai_interview_config` table (FK → `assessment_sets`)
3. `ai_interview_sessions` table (FK → `assessment_assigned_students`)
4. `ai_interview_interactions` table (FK → `ai_interview_sessions`)
5. `ai_interview_scores` table (FK → `ai_interview_sessions`)
6. All indexes on foreign keys and frequently queried columns

Run against the assessment database:
```bash
psql -h <host> -U <user> -d <assessment_db> -f migrations/add_ai_interview_tables.sql
```

---

## Frontend (Assessment-React)

The candidate-facing AI Interview UI lives in `Assessment-React/src/modules/Assessments/Partials/AIInterview/`:

- **`InviteStart.js`** — OTP-based invite start screen. A candidate opening an AI Interview invite link enters the OTP to authenticate and start the session (the invite API in `aiInterviewInviteAPI.js` calls auth + student services). Since 2026-06-11 this same screen also handles **all other corporate assessment types** under the generalized OTP-invite flow — see [otp-invite.md](otp-invite.md).
- **`interview.js`** — the live voice interview surface (TTS playback, mic capture, browser VAD auto-submit after ~1.8 s of silence).
- **`instruction.js`** — welcome / readiness / **resume** pre-start screens shown before the live interview.
- **`resumeUpload.js`** — shared, unit-tested handler for the pre-start resume upload (see gotcha below).
- **Completion behaviour is now flow-aware (since 2026-06-17)** — the Thank-You screen branches on whether the candidate is a logged-in student or an OTP invite candidate (`isInvite = !!readInviteScopedJwt()`):
  - **Logged-in student** — the completion screen shows a **"Back to Assessments"** primary button. `goHome()` exits fullscreen, marks the assignment completed locally (see below), calls `setAssessment(null)` (re-renders the inline dashboard list) **and** `navigate('/assessment')`. Returning to the dashboard re-fetches active + completed, so the just-finished interview drops out of **Active** and appears under **Completed** (the server already set `status=COMPLETED, submitted=true` in `completeSession`; the active-list query filters `submitted:false` in `student-node` `Assessment.js`). The standalone `/ai-interview/:id` exit fallback in `index.js` now `navigate('/assessment')` instead of `window.history.back()`.
  - **OTP invite candidate** — completion stays **terminal** ("You can now close this window"), no portal button. The earlier removal (2026-06-15) was because a blanket "Back to Home" cleared the scoped JWT and bounced invite candidates into `AuthPage` (which auto-fires `window.open(AUTH_URL)`); that hazard only applies to invite candidates, so the button is now gated to logged-in students only.
- **Completion reload guard (since 2026-06-17)** — on `completeSession` success, `interview.js` persists `localStorage['ai_interview_completed_<assignedId>'] = '1'` (helpers `markAiInterviewCompleted` / `isAiInterviewCompleted` in `aiInterviewInviteAPI.js`). On mount, `instruction.js` reads this flag so a **page reload no longer restarts the instructions/welcome flow**: a logged-in student is redirected to `/assessment` (renders nothing meanwhile to avoid a welcome-screen flash); an OTP candidate gets a terminal **"Your interview is already complete"** notice. This complements the server-side no-retake gate (409 from `startSession` once `status=COMPLETED`/`submitted=true`) and the `InviteStart` "already submitted" gate (see [otp-invite.md](otp-invite.md)).

### Candidate resume upload (pre-start)

On the instructions screen the candidate optionally attaches a resume (PDF/DOCX/TXT, ≤6 MB). The file is **POSTed directly to FastAPI** `${REACT_APP_FASTAPI_URL}/ai-interview/parse-resume` as multipart (`file` field) — it does **not** go through student-node and is **not** stored in S3. FastAPI extracts plain text (PyMuPDF for PDF, python-docx for DOCX) and returns `{ text, chars, truncated, filename }`. The text is held in component state and passed as `resumeText` to `POST /ai-interview/session/start` (and on each `session/turn`), giving the interviewer resume context. The endpoint requires **no auth** (`_verify` is disabled), so a missing invite JWT does not block it. Field config (`resume_policy`: `mandatory` / `optional` / `not_required`) comes from `ai_interview_config` and is surfaced via `config-info`.

### Frontend Gotcha — resume upload silently did nothing (Fixed 2026-06-12)

The pre-start upload stacked **two upload mechanisms**: an antd `<Upload.Dragger beforeUpload>` *wrapping* a nested `<label htmlFor>` + hidden `<input>` whose `onClick` did `e.preventDefault()` then a manual `input.click()`. The two fought each other — the label's default activation was cancelled and the programmatic click was swallowed inside the Dragger — so the **file dialog often never opened and the `parse-resume` request was never sent**. Symptom: "users can't upload a resume" while the FastAPI endpoint, CORS, and the baked-in URL are all healthy (the tell: **zero** `parse-resume` requests in the server logs).

**Fix:** collapse to a single path — antd's `Upload.Dragger` opens the dialog on click **and** handles drag-and-drop, both feeding one shared `handleResumeFile()` in `resumeUpload.js`; `beforeUpload` returns `false` so antd never auto-uploads. `ResumeDrop` changed from `<label>` to `<div>` (no input to pair with). Diagnose recurrences by checking whether any `parse-resume` request reaches FastAPI at all — if not, it's the client, not the server.

### Frontend Build Gotcha — `process.env` must use member access (Fixed)

Assessment-React is **webpack 5** and inlines env vars via `EnvironmentPlugin`. Env vars are only inlined for **explicit member-access** expressions like `process.env.API_URL`. Writing whole-object destructuring — `const { API_URL, STD_API_URL } = process.env` — combined with `X || fallback` usage can leave a **dangling bare `process.env`** statement in the production bundle. Webpack 5 does not polyfill `process`, so at module-eval the app throws **`ReferenceError: process is not defined`**, the SPA never mounts, and you get a **blank white screen on every route** (the build still succeeds — it's a runtime crash).

This bit `aiInterviewInviteAPI.js` and blanked the whole app on DEV and again on UAT (2026-06-10). **Rule:** in this repo, read env vars as `const API_URL = process.env.API_URL` (member access), never destructure `process.env`. Diagnose by grepping the built bundle for a non-member `process.env` token; the runtime `pageerror` is `process is not defined`.

---

## Key Concepts

- **Adaptive Questioning** — Each question adapts to the candidate's prior performance. Strong answers → harder questions. Weak answers → adjusted difficulty or deeper probing.
- **Follow-up Intelligence** — When a response is evaluated as needing deeper exploration (`needsFollowUp: true`), a targeted follow-up is generated probing the specific weak area.
- **Weighted Scoring** — Every response is scored on 4 dimensions (Technical 40%, Depth 25%, Communication 20%, Problem Solving 15%), not just right/wrong.
- **Automated Shortlisting** — Final report includes a `recommendation` field (`strong_hire`/`hire`/`maybe`/`no_hire`) based on overall performance, enabling automated candidate filtering.
- **Resume + JD Context** — Optional endpoints to parse resume and JD text into structured data for more personalized question generation.
- **Multi-Round Types** — Questions can be of type `technical`, `behavioral`, `situational`, or `case_study`, configured per assessment.
- **LLM Fallback** — Gemini 2.5 Pro is primary. If it fails, Groq Llama 3.3 70B is used as fallback. If both fail, 503 is returned.
- **Voice (Payal — Indian female, conversational)** — The AI interviewer speaks via ElevenLabs Flash v2.5 with the **Payal** voice (Hindi/Indian-English, casual tone), matched to the Indian candidate base. Deepgram Aura-2 Thalia (US English) is the failover. STT is Deepgram `nova-3` for both REST and live WebSocket modes. Browser VAD auto-submits the answer after ~1.8 s of silence.
- **PostHog Analytics** — All question generation, evaluation, and report events are tracked in PostHog for monitoring and analytics.
- **Standard Assignment Flow** — Uses the existing `AssessmentSet` → `AssessmentInstituteMap`/`AssessmentCorporateMap` → `AssessmentAssignedStudent` pipeline, same as Communication, Aptitude, and Role-Based assessments.

---

## Corporate ATS Candidate List Surfacing

When an `AI_Interview` assessment is mapped to a (drive, role, round) cell via the cell-assessment mapping (`assessment_corporate_map.mapped_to`), the corp-ATS candidate list (`POST /corporates/drive/:driveId/role/:roleId/candidate/list`) renders **one column per round**: **Overall Score** (a single 0–100 number).

This is unlike Communication or Role-Based rounds which expand into multiple sub-topic columns (Verbal/Reading/Listening/Writing/Total/CEFR for Communication; MCQ/Subjective/Video/Coding/Overall for Role-Based).

### Score Path

- `admin-node` `Assessment.getStudentAssessmentScores()` dispatches on `assessment_type.type_name`. The AI Interview branch reads the latest `assessment.ai_interview_scores.overall_score` (joined via `ai_interview_sessions.assessment_assigned_id`) and returns `aiInterviewScores: { overallScore }`.
- `corporate-node` `helpers/evaluationAssessmentOverlay.js` overlays that value into `parameters_score[round].overallScore` and seeds `topics[round].subTopic = ["overallScore"]` so the corp-ATS FE renders exactly one column titled "Overall Score" under the round.
- The FE (`corporate-react` `IndividualDriveTable`) treats `overallScore` as the round's overall sub-topic and suppresses the duplicate round-average column.

### Gotcha (Fixed)

Prior to this dispatch branch, `AI_Interview` matched none of the dispatcher's type checks (`behavi`/`aptitude`/`role`/`custom`) and fell through to the Communication else-branch — so AI Interview rounds rendered the 6 Communication sub-topic headers (Verbal/Reading/Listening/Writing/Total/CEFR) sourced from an empty `communication_scores` table. The dispatcher now has an explicit `AI_Interview` branch and the corp-ATS overlay's `STATIC_SUB_TOPIC_SCHEMA` includes `aiInterview: ["overallScore"]`.

### Round Score Filter

The Drive Role's Round Score / Passing Score filter (`GET /corporates/drive/:driveId/role/:roleId/score/list?stage=<round>`) is built from `job_role_student_map.parameters_score` joined against the role's interview workflow. Because AI Interview scores live in `assessment.ai_interview_scores` (not in `job_role_student_map`), the old behavior left `parameters_score` empty for AI Interview rounds and the filter panel rendered "No Data Found". The handler now seeds a topic entry from `getCellSubTopicSchema` whenever the round is mapped to an assessment but has no sheet-derived sub-topics — so the filter row always reflects `["overallScore"]` for AI Interview cells.

The corp-react Drive Role page also fetches `score/list` in a dedicated `useEffect` (separate from the long `fetchOptions` chain) so a transient failure in one of the other ~11 filter endpoints can't keep the Round Score panel empty.

### Applying the Round Score Filter

Applying the filter (e.g. `Assessment >= 50`) flows through `POST /corporates/drive/:driveId/role/:roleId/candidate/list` with `body.scores = [{ topic: { name: "Assessment", score: 50 } }]`. The default SQL filter compares against `jrsm.average_rounds_score` / `jrsm.parameters_score`, which are NULL for assessment-mapped rounds (AI Interview is the canonical case), so the query returned zero rows.

`interviewHandler.getCandidateListForHR` now pre-resolves each assessment-mapped score entry via `resolveAssessmentScoreFilter` (in `helpers/evaluationAssessmentOverlay.js`):

1. For each entry whose round is mapped to an assessment, call admin-node `getCellAssessments` + `getCellScoresBundle` for every candidate email on the role.
2. Apply the threshold (`selection: >= score`, `rejection: <= score`) using the bucket's headline key (`overallScore` → `overallPercentage` → `totalScore`).
3. Intersect the matched-email sets across every assessment-mapped score entry.
4. Translate the surviving emails to `corporate.job_role_student_map.student_id` via `student.student_personal_profile`.
5. Strip those entries from `body.scores` and pass `assessmentScoreStudentIds` to `DriveRoleCandidateMap.getCandForHR`, which adds `AND jrsm.student_id IN (...)` to both the count and data queries (`AND FALSE` when the intersection is empty so count + data agree).
