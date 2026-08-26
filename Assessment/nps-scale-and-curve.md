# NPS — the ladder, the logarithmic curve, and where each lives

**LIVE on DEV + UAT since 2026-08-25. PROD pending.**

NPS ("Normalised Progress Score", also written "progress score" on the v2 TPO
screens) is the platform's difficulty-anchored 0–100 number. It exists so that a
**higher level always outranks a higher raw percentage** — an A1 student at 80%
must not sit above an A2 student at 60%.

Companion docs: [aptitude.md](aptitude.md), [communication.md](communication.md),
[admin-frontend.md](admin-frontend.md),
[../ATS/Institute/v2-strangler-fig.md](../ATS/Institute/v2-strangler-fig.md).

## NPS exists for Communication and Aptitude ONLY

Those are the only two assessment types with a level ladder to anchor on.
Role_Based, Custom_Assessment, AI_Interview and Behavior have **no NPS at all** —
they are not "NPS 0", they are NULL, and every surface must render them as a
raw percentage on a clearly separate scale (or as "—"). Mixing an NPS and a
percentage in one column is how the original ranking bug was reported.

Behavior additionally has **no score of any kind**, only levels.

## The two-stage definition

The single rule, enforced everywhere: **aggregate linear, curve last, curve once.**

### Stage 1 — the linear ladder (STORED)

```
ladderScore(levelIndex, rawScore, bandCount) = (levelIndex × 100 + rawScore) / bandCount
```

| Ladder | Levels | bandCount | Helper |
|---|---|---|---|
| Communication (CEFR) | A1 A2 B1 B2 C1 C2 | 6 | `communicationNPS(cefrLevel, rawScore)` |
| Aptitude (competency) | Beginner Learner Competent Advanced | 4 | `aptitudeNPS(aptitudeLevel, rawScore)` |
| Question difficulty | easy medium hard | 3 | `difficultyAnchoredScore(difficulty, rawScore)` |

This linear value is what `progression_history` holds
(`assessment_communication_progress_score`, `assessment_aptitude_progress_score`).
**Storage was never migrated and there is no backfill, ever.**

### Stage 2 — the logarithmic curve (PRESENTATION ONLY)

```
curveNPS(nps, k) = 100 × ln(1 + k × nps/100) / ln(1 + k)
```

Applied at **read time**, never written. `k` comes from `NPS_CURVATURE_K`.

Why it exists: the linear ladder is honest but unreadable. Real level
distributions are bottom-heavy (at Swadha, Communication was **A1 = 1,343 /
A2 = 10**, i.e. 99.3% A1), so linear NPS collapses every cohort into single
digits — four distinct Communication schedules read 8 / 10 / 10 / 10. The curve
is **strictly monotonic**, so ranking is identical to linear; it only restores
separation (those same four become 17 / 21 / 22 / 20).

Reference point, useful as a smoke test: **`curveNPS(10)` = `20.91` at k=4.**

## `NPS_CURVATURE_K` — defaults to 4, and unset ≠ zero

| Value | Meaning |
|---|---|
| unset / unparseable | **4** (`DEFAULT_CURVATURE_K`) — the value the PRD specifies |
| explicit `0` | identity, the documented rollback to the linear scale |
| any k > 0 | that curvature |

`DEFAULT_CURVATURE_K` was originally `0`, which meant the curve stayed dormant
until every environment set the variable by hand. Because env files are
gitignored, one unset variable silently served the **linear** number (a cohort
reading 31 drops to 16) with no error anywhere — and two services could disagree
about the same student. Changed to 4 on 2026-08-25 (`63aa6ce2` student-node).

Note the distinction between *unset* and *explicit zero*: the earlier
`parsed > 0` test collapsed them into one answer and would have re-enabled the
curve on the exact box where someone had just switched it off.

**Verify on any box:**

```bash
docker exec institute node -e \
  'console.log(require("/app/app/helpers/npsScale.js").curveNPS(10))'   # => 20.91
```

## `npsScale.js` is duplicated by design — and MUST stay byte-identical

There is no shared package to hold it, and a partial copy is how the previous
drift started. It is duplicated across:

`student-node` · `admin-node` · `institute-node` (and the abandoned
`student-node-calcq` checkout, which deploys nowhere)

A student's NPS must not depend on which service rendered it, nor on whether
`CALCULATION_ASYNC` routed their submission through the queue. This file
replaced **four** already-drifting copies of the ladder (student-node `utils.js`,
student-node `Assessment.js`, the calcq mirrors, admin-node `Assessment.js`).

**Verify:**

```bash
md5sum */app/helpers/npsScale.js          # locally
docker exec <c> md5sum /app/app/helpers/npsScale.js   # per running container
```

## Curved band boundaries (k=4)

Because the curve is applied to the number, the **band cutoffs move with it**.
Colour thresholds and band labels must use these, never an even split and never
the old `AVG_OK = 70`:

| Ladder | Boundaries |
|---|---|
| Communication | A1 `0–31.74` · A2 `31.74–52.65` · B1 `52.65–68.26` · B2 `68.26–80.73` · C1 `80.73–91.11` · C2 `91.11–100` |
| Aptitude | Beginner `0–43.07` · Learner `43.07–68.26` · Competent `68.26–86.14` · Advanced `86.14–100` |

Derived at runtime by `communicationBandBoundaries(k)` / `aptitudeBandBoundaries(k)`
— do not hardcode them.

Cross-type comparability **improves but is not solved**: Aptitude's bottom band
is 43.07 wide against Communication's 31.74, so "Aptitude 29" and
"Communication 17" are both bottom-band cohorts that look 12 points apart.

## Averaging: `curvedMean`, and why order matters

`curvedMean(values, k)` averages the **linear** values and curves the result.
Averaging already-curved values is a different (and wrong) number — Jensen's
inequality means a group mean can in principle reorder even when no individual
does. Sorting and `MAX()` are exempt from the rule: the curve is strictly
monotonic, so `ORDER BY <linear nps column>` stays correct and is cheaper.

In SQL, `NPS_EXPR` in `institute-node/app/helpers/assessmentScoreSql.js` is
deliberately the **linear** column. Never curve in SQL.

## Bugs this consolidation fixed

1. `Number(null) === 0` — a missing NPS was averaged in as a **zero**, dragging
   cohort means down, and a missing raw score minted a real-looking **0 ladder
   score**. Both now return `null`.
2. An unrecognised level defaulted to index `0` (`|| 0`), silently anchoring the
   student at the **bottom band**. Now `null`, which `progression_history` allows.
3. Curvature was cached at module load, so a require-before-dotenv race would
   **silently disable the curve**. Now read from env per call.
4. `_calculateImprovement` emitted `+X%` for a value its own docstring called
   `+X pts`.

## Known gap: Communication diagnosis #1 has no NPS, by design

Communication NPS is the mean of two level-anchored halves, so diagnosis #1 has
no predecessor and no confirmed level yet — `communicationProgression.js` writes
`nps: null` and `assessment_cefr: null` for it deliberately.

**Aptitude does not have this gap**: at `diagnosis_number = 2` it backfills
`progression_history` for *both* assessments, because Aptitude pairs at the
**topic rolling-average** level rather than the assessment level.

Measured on UAT (non-practice, scored rows):

| attempt # | students | with NPS | missing |
|---|---|---|---|
| 1 | 104 | **0** | **104** |
| 2 | 54 | 54 | 0 |
| 3+ | 31 | 31 | 0 |

So **48% of Communication students have taken exactly one assessment and have
zero NPS** — they are invisible to every NPS-based metric, not merely
under-weighted. Any cohort average over "whatever has NPS" silently describes
only the students who came back for a second sitting: a returning-student
survivorship bias, and the more able half. Surface `n` alongside any
Communication NPS average. Backfilling diagnosis #1 from the completed pair
(mirroring Aptitude) is a write-path change and is **not** done.

## Also still open

The **Aptitude diagnosis baseline is on a different ladder than the NPS it is
compared against** — `/3` difficulty vs `/4` competency, inside the same
admin-node institute report ("baseline → peak → % of change"). Pre-existing, and
deliberately not silently changed; it is now at least named as
`DIFFICULTY_BAND_COUNT` in `npsScale.js`. Needs a product call.

## Where the progress score is surfaced (institute v2)

As of **26 Aug 2026 (UAT)**, every institute-v2 surface that reports a
Communication or Aptitude result speaks in the **curved progress score**, and
every other type keeps its raw percentage. Before this, `curveNPS` existed in
only two of five `institute-node` models, so one student read **53** on the
Students table and **21** on the assessment they had actually sat.

| Surface | Model | Reports |
|---|---|---|
| Dashboard → Active Assessments "Avg progress" | `DashboardV2` | curved NPS + band |
| Dashboard → Student at-risk donut | `DashboardV2` | banded by **ladder position** |
| Dashboard → Competency ladder | `DashboardV2` | placed on the progression ladder |
| Dashboard → Year-on-year (`b6`) | `DashboardV2.getYoy` | one series **per type** |
| Assessments list → "Avg progress" | `AssessmentV2` | curved NPS + band |
| Students (institute-wide) | `StudentWiseV2` | curved NPS, score **and** delta |
| Assessment detail (all tabs) | `AssessmentDetailV2` | curved NPS |

### Three rules that are easy to get wrong

1. **A delta is `curve(latest) − curve(first)`, never `curve(latest − first)`.**
   The curve is concave and defined on 0–100 band space; a delta does not live
   there, and curving one clamps every decline to zero.
2. **Never band a progress score against `assessmentBands.LADDERS`.** Those are
   the raw-percentage cutoffs (Communication `30/45/60/75/90`) and they do
   **not** match the curved boundaries `npsScale` derives
   (`31.74 / 52.65 / 68.26 / 80.73 / 91.11`). Band via `npsBandOf`, which reads
   the derived values, or re-tuning `NPS_CURVATURE_K` silently desyncs the
   colours.
3. **Risk bands on an NPS type are ladder POSITIONS, not a 40/70 cut.** A flat
   "below 40 is high risk" paints an A2 cohort the same red as an A1 one,
   because after the curve A1 alone spans `0–31.74`. The dashboard's risk
   sub-labels therefore read "Lowest level / Mid levels / Top level" and no
   longer quote a percentage.

### Year-on-year is per type, one at a time

`getYoy` used to average **every** type into a single line labelled `/100` —
Aptitude against Communication against Role_Based, on ladders that mean
different things. It now returns **one series per assessment type**, ordered
longest-history-first (ties broken on sample size), each carrying `unit`
(`""` for a progress score, `"/100"` for a percentage) and `isProgressScore`.

Both scales round to **1 dp**: `curveNPS` returns 2 dp, which printed `63.98`
beside a percentage series reading `42.7` in the same panel.

The panel renders **one series at a time** behind a type tab strip (the same
control the Competency block above it uses). Rendering a card per type shrank
each chart to a third of the panel width, where the line is a smudge and the
axis labels are illegible. One full-width chart, and still never two scales on
one axis.

**Types with no `SCORE_EXPR` entry produce no series at all** — AI_Interview and
Behavior. On UAT that silently drops 25 submitted AI_Interview attempts from the
panel. Pre-existing, unchanged, and consistent with those types being absent
from every other score roll-up.
