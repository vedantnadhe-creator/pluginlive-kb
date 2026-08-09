# CEFR Levels — the Corporate view

> How the CEFR band a recruiter sees on a candidate is chosen, computed, filtered
> and sorted, end-to-end, for **corporate** assessments.

CEFR (Common European Framework of Reference) is the six-band language scale we
report on **Communication** assessments — no other assessment type produces one:

```
A1  <  A2  <  B1  <  B2  <  C1  <  C2
```

It is **ordinal, not numeric**. Every layer that treats it as a number breaks
(see *Gotchas*).

**Scope of this doc:** the corporate/ATS end only — pitching a level, what the
band means, and where it surfaces in Drives. **Progression is deliberately out
of scope**, and not because it was skipped: corporate Communication assessments
**never progress**. `student-node` `Assessment.js` gates the whole CEFR-replay
block on `(!isCorporate && !isOneTime) || is_practice`, and `isCorporate` is true
whenever `assessment_corporate_map.corporate_id` is set. So no
`progression_history` row is written, no `student_personal_profile.AssessmentCEFR`
is touched, and nothing a candidate does on a corporate paper changes the level
of the next one. The adaptive chain is an **institute** feature — see
`Assessment/communication.md` if you need it.

---

## The one rule to remember

**The reported band can never exceed the level the assessment was pitched at.**

`mapCEFRBasedOnQuestionSetAndScore` (admin-node `app/helpers/util.js`) is
*stay-or-down*: a perfect score on a B1 paper reports **B1**, never B2. Pitch the
level **at or above** the bar you are hiring against, or the column can never
show you the candidates who clear it. A B1 paper cannot identify a C1 speaker.

---

## Lifecycle

```
admin-react Create Assessment (entityType = corporate)
   └─ pick CEFR level A1–C2  +  enabled sections  +  accent  +  response language
        └─ assessment_corporate_map  +  assessment_set.cefr_level
             └─ candidate sits the paper (portal or OTP invite link)
                  └─ per-section scores  →  weighted total  →  BAND
                       └─ Drives evaluation table: CEFR Level column, filter, sort
```

### 1. Choosing the level

Corporate assessments are created from **admin-react → Assessment → Create
Assessment** (`Partials/CreateAssessment/AssessmentSelect.js`), the same screen
used for institutes, with `entityType = 'corporate'`.

| Field | Values | Notes |
|---|---|---|
| **Select CEFR Level** | `A1 A2 B1 B2 C1 C2` (radio) | **Mandatory** — create is blocked without it |
| **Sections** | `Reading`, `Listening`, `Speaking`, `Writing` | Group-level CEFR *skills* in the UI; **corporate requires at least one** (institutes do not) |
| **Listening Audio Accent** | `en-IN` (default), `en-US` | Non-default accents generate a fresh set — see `Assessment/communication.md` |
| **Response Language** | English / Hindi / Hinglish / … | Corporate-only option; Hinglish renders through a separate FE fork |

The UI stores **skill groups** and expands them to admin-node's real section
names on submit (`expandSectionsForBackend`). All four selected → sends `[]`,
which the backend reads as "everything enabled".

| Skill (UI) | Sections actually run (backend) |
|---|---|
| Reading | Paragraph Reading |
| Listening | Audio Question |
| Speaking | Video Response |
| Writing | Question Based Response, Email Writing, Dictation, Sentence Completion, Sentence Build |

The chosen level lands on `assessment_set.cefr_level` — that set row, not the
map, is what scoring reads back.

### 2. From section scores to a band

Computed in admin-node `Assessment.getStudentAssessmentScores` — the single
function behind every corporate score read.

**a. Group scores.** Writing is the average of the writing subsections that were
scored, over a **fixed divisor of 4** (not the number of subsections present).

**b. Weighted total**, renormalised over the enabled groups only:

| Group | Weight |
|---|---|
| Speaking (Video Response) | 0.4 |
| Writing | 0.3 |
| Reading (Paragraph Reading) | 0.2 |
| Listening (Audio Question) | 0.1 |

`totalScore = Σ(groupScore × weight/Σweights)` — so a Reading+Writing-only paper
splits 0.2/0.3 renormalised to 0.4/0.6, not 0.2/0.3 of a missing whole.

**c. Band** = `mapCEFRBasedOnQuestionSetAndScore(set.cefr_level, totalScore)`:

| Set pitched at | → A1 | → A2 | → B1 | → B2 | → C1 | → C2 |
|---|---|---|---|---|---|---|
| **A1** | any | — | — | — | — | — |
| **A2** | ≤ 75 | > 75 | — | — | — | — |
| **B1** | ≤ 60 | ≤ 80 | > 80 | — | — | — |
| **B2** | ≤ 50 | ≤ 67 | ≤ 83 | > 83 | — | — |
| **C1** | ≤ 43 | ≤ 57 | ≤ 71 | ≤ 86 | > 86 | — |
| **C2** | ≤ 30 | ≤ 40 | ≤ 50 | ≤ 60 | ≤ 70 | > 70 |

An unrecognised or missing set level falls back to **A1**.

**d. The `-` gate.** The band is only reported when **every enabled group scored
> 0**. One zeroed group (a skipped Video Response, a blank Writing tab) and the
column reads `-` even though the numeric scores render. `-` therefore means
*"incomplete evidence"*, not *"below A1"*, and the CEFR filter never matches it.

### 3. What the corporate sees

In **Drives → View Drive Role → evaluation table**, on a round mapped to a
Communication assessment, the columns after **Assessment Status** are:

> **Total Score → CEFR Level → Verbal → Reading → Listening → Writing**

(`totalScore` and `cefrLevel` are floated to the front via `HEADLINE_SUBTOPICS`
in `IndividualDriveTable`; the rest follow the backend `topics[].subTopic` order.)

Scores read **`NA`** until the candidate's `assessment_status` is `Completed` —
a candidate who has not started shows `NA`, not a misleading `0`/`-`.

**Filter (Round Score → CEFR Level).** Rendered as a six-option Ant `Select`,
never a number box. Backend `resolveAssessmentScoreFilter` compares by **rank**:

- `selection` mode → candidate rank **≥** the chosen band ("B2 and above")
- `rejection` mode → candidate rank **≤** the chosen band
- candidates with no band (`-`) never match either way

**Sort.** Clicking the CEFR column sorts through `resolveAssessmentSort`, which
pulls every applied candidate's scores from admin-node, ranks by CEFR band and
hands corporate-node an ordered `student_id` list — the SQL `parameters_score`
sort cannot do it, because assessment scores never live in that column.
Unscored candidates sink to the bottom in both directions. Falls back silently
to no sort if admin-node does not answer within 1s.

**Export.** The evaluation export resolves the *currently filtered* candidate
set first, so a CEFR-filtered view exports exactly what is on screen.

### 4. Plumbing

| Hop | Call |
|---|---|
| corporate-node → admin-node (scores) | `POST /corporate/:corporateId/cell-scores` → `getCellScoresBundle` |
| corporate-node → admin-node (single assessment) | `POST /corporate/assessment/:mapId/scores/batch` |
| corporate-node → admin-node (status) | `POST /corporate/:corporateId/cell-statuses` |
| Merge into the candidate list | `applyAssessmentScoreOverlay` (`app/helpers/evaluationAssessmentOverlay.js`) → `parameters_score[round]` |

Only rows with `scores_calculated = true` come back at all. The overlay seeds the
Communication sub-topic schema statically —
`englishVerbalScore, readingAbilityScore, listeningAbilityScore, writingScore,
totalScore, cefrLevel` — so the header keeps its shape on pages where nobody is
scored yet.

---

## corporate-node-v2 (agentic workflows) — **DEV only**

The v2 stack treats the CEFR level as a per-stage knob rather than a create-time
form field. See `ATS/Corporate/v2-strangler-fig.md` before assuming any of this
runs on UAT/PROD.

- `CEFR_LEVELS` in `src/modules/workflows/assessmentSettings.ts` is the single
  vocabulary shared by the workflow-design LLM, the stage builder and dispatch;
  `cefrLevel` is forwarded verbatim to admin-node's `assignAssessment`.
- The designer prompt is told to **pitch the level to the job** — frontline
  support / field roles around A2–B1, analyst / client-facing / managerial
  around B2–C1 — explicitly "do not default everything to B2". The scaffold
  default is `B1`.
- An auto-pilot stage can order a **re-test** at a chosen `cefrLevel`
  (`stageDecision.service.ts`), one of only two instruments it may build.
- **Section-name trap:** admin-node's Communication sections are question
  *types*, not CEFR *skills*. A stage configured with `"Reading"`/`"Writing"`
  produces an assessment with **no questions in it**. `toCommunicationSections`
  translates skills → real sections, and `dispatch.ts` retires (revokes invite
  links + closes the window on) any map whose enabled sections are unfillable.
  Speaking and Listening map to nothing in v2 — their sections need media we
  cannot author — so asking for them silently shortens the paper.

---

## Gotchas

- **Two different CEFR mappings exist in the platform.** The corporate-visible
  band comes from admin-node's `mapCEFRBasedOnQuestionSetAndScore`
  (*stay-or-down*, table above). fastapi-ai-engine has its own `map_cefr_level`
  (`routers/communication.py`, `routers/communication_deepgram.py`,
  `CommunicationScoreCalculation/video_calculation.py`) which **can promote one
  band above the paper's level**; it is returned inside per-section scoring
  payloads and does **not** feed the corporate column. Never quote the two side
  by side as if they agree.
- **`Number("A1")` is `NaN`** — this broke the CEFR filter at every layer once
  (FE payload builder coerced it to `null`, the backend's `Number.isFinite`
  guard then dropped the entry, and the filter silently matched *everyone*).
  Anything new that touches sub-topic values must special-case `cefrLevel`,
  including the request schema: `scores[].subTopics[].score` is
  `{ type: ["number", "string"] }`, and narrowing it back to `"number"` returns
  a `400 FST_ERR_VALIDATION` before the handler ever runs.
- **`mapCEFRBasedOnQuestionSetAndScore` has no `break` statements.** Every case
  currently returns because its last comparison is `<= 100`, but that only holds
  for a real number — a `NaN` total would fall through every case and return
  `"C2"`. The caller guards against null/undefined, not `NaN`; keep it that way.
- **Writing's divisor is hard-coded to 4** while the group has five subsections.
  A paper running all five under-reports Writing, which drags `totalScore` down
  and can cost the candidate a band.
- **`-` is not a score.** It means an enabled group scored 0, so filters, sorts
  and any downstream gate must treat it as "no evidence", never as the bottom
  band.
- **Set-swap is accent-blind (open).** A delivery-time validation swap can
  replace a corporate paper's set with one from the `en-IN` pool. It preserves
  the CEFR level (that is what it filters on) but not the accent — see
  `Assessment/communication.md`.

---

## Key files

| File | Role |
|---|---|
| `admin-react/src/modules/Assessment/Partials/CreateAssessment/AssessmentSelect.js` | CEFR + sections + accent picker (corporate create) |
| `admin-node/app/helpers/util.js` → `mapCEFRBasedOnQuestionSetAndScore` | score + set level → band (**the corporate-visible mapping**) |
| `admin-node/app/models/Assessment.js` → `getStudentAssessmentScores` | weights, `-` gate, `communicationScores` bucket |
| `admin-node/app/models/Assessment.js` → `getCellScoresBundle` | per-cell score fetch for the evaluation overlay |
| `corporate-node/app/helpers/evaluationAssessmentOverlay.js` | `CEFR_RANK`/`cefrRank`, overlay, ordinal filter + sort |
| `corporate-node/app/schemas/interview.js` | `subTopics[].score` accepts number **or** string |
| `corporate-react/src/modules/Drives/ViewDriveRole/IndividualDriveTable/` | column order, `NA` gate, filter payload |
| `corporate-node-v2/src/modules/workflows/assessmentSettings.ts` | `CEFR_LEVELS`, skill → section translation (DEV) |
| `student-node/app/models/Assessment.js` | the `!isCorporate` gate that keeps corporate off progression |

## Related

- `Assessment/communication.md` — the assessment itself, set generation, accents,
  and the institute-side progression chain this doc excludes
- `ATS/Corporate/Drives/README.md` — the evaluation table the band renders in
- `ATS/Corporate/v2-strangler-fig.md` — what is actually live in v2
