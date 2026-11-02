# Progression guardrails — HARD RULE

> **HARD RULE.** If a change's blast radius touches **progression** (Communication CEFR or
> Aptitude level progression, NPS, or anything that feeds or reads them), you must prove the
> algorithm is undisturbed **before you push to any branch that deploys** (`Development`,
> `UAT`, a release/hotfix branch). "Tests pass" is not enough on its own. Skipping this is
> how the 2026-06 regression below shipped to PROD and sat there for 4½ months.

## Why this rule exists

| When | What happened |
|---|---|
| 2026-04-06 `418b76dd` (kesavan) | Diagnosis rule set: confirmed level = **lower of the paper level and the calculated level**. B1 papers at 86%+ → confirmed **B1**, suggested **B2**. |
| 2026-06-16 `132c2697` (Ravi) | "Rewrite CEFR progression as deterministic chain replay". It was a refactor, but it silently changed the diagnosis rule to confirmed = suggested (C2 capped at C1). The paper cap was lost and the KB was rewritten to match the new code, so the regression was then documented as if it were the spec. |
| 2026-10-15 → 2026-11-02 | PROD: `sshrayanika@gmail.com` sat two **B1** diagnosis papers (avg 85.795 → 86) and the institute drawer showed **Achieved level B2, current difficulty B1**. 3 PROD diagnoses were affected in total. Fixed in `student-node` `559f5bfd`: LIVE DEV + UAT 2026-11-02, PROD pending (see `communication.md` → Level derivation). The fix itself followed this rule: pinned tests, then an old-vs-new replay diff on a seeded copy of the PROD chain on DEV and UAT, then a predicate count of every affected row per environment. |

What went wrong: a refactor changed a business rule, no test pinned that rule, nobody diffed the
replayed output against the stored data, and the KB was updated from the new code instead of
being checked against it.

## What counts as "touching progression"

Treat the change as in scope if it edits, or changes the inputs or outputs of, any of these:

- **Core algorithm:** `student-node/app/helpers/communicationProgression.js`, `app/config/newCERFmapping.js`
  (`cerfMapping`, `assessmentCefrMapping`), `getNewCERFlevel` / Aptitude level helpers in `app/helpers/utils.js`,
  `app/helpers/npsScale.js`.
- **Live and backfill paths:** `Assessment.replayCommunicationProgression` / `updateCurrCERFlevelOfStudent`,
  `updateAptitudeProgression`, `CommunicationCalculations.backfillAllStudentProgression`,
  `backfillAptitudeProgression`.
- **Inputs:** final/section score calculation, the eligibility filter (`isCommunicationProgressionEligible`),
  chain ordering (`submittedAt`), `is_diagnosis` / `is_practice` flags, the set level served
  (`communicationSetSwap.js`, `isAdaptiveDelivery`, set selection), the diagnosis pair (`diagnosisPair.js`).
- **Gates:** `progressionGate.js`, `diagnosisGate.js`, the calculation queue.
- **Readers:** anything that reads `progression_history` (`assessment_cefr`, `suggested_cefr`,
  `*_progress_score`) or the profile CEFR (`AssessmentCEFR`/`PracticeCEFR`): student/institute/corporate/admin
  dashboards, the institute v2 drawer, PDF reports, exports.
- **Schema/data:** any migration or data fix on `assessment.progression_history`, `assessment_assigned_students`
  scoring columns, or `student_personal_profile` CEFR columns.

A refactor counts. "No behaviour change" is something you have to prove, not something you can assume.

## Required before pushing

1. **Invariants hold.** Check the change against every invariant below. If an invariant has to change,
   that's a product decision: get explicit sign-off and update this doc and `communication.md`/`aptitude.md`
   **first**, in the same PR.
2. **Pinned tests pass, and new ones were added.** Run
   `npx mocha --exit test/communicationProgression.spec.js test/npsScale.spec.js test/progressionGate.spec.js test/diagnosis*.spec.js test/aptitude*.spec.js`.
   Every invariant you rely on must have a test. If the change exposes a rule with no test, add one before
   changing code. Never edit an existing expectation to make it pass without a sign-off as in step 1.
3. **Replay diff against real data.** Run the backfill with `dryRun: true` (Communication:
   `POST /assessment/backfill-progression {"dryRun": true}`) on DEV/UAT with the new code. Alternatively,
   run the pure core over a PROD read-only export (`ssh ubuntu@140.245.25.134 '/home/ubuntu/scripts/prod-readonly-query.sh …'`).
   Count rows where `changed = true`.
   - For a refactor, the expected count is **0**. Any non-zero count is a regression until each changed row is explained.
   - For an intended rule change, the changed rows must be exactly the predicted set. Record the count and
     examples in the commit/PR, and list the PROD rows that will need a re-derive.
4. **State the blast radius in the commit/PR.** Say which of the areas above it touches, the replay-diff count,
   and the backfill needed per environment (`primaryEmails` scoped; remember the `simulate:true` warning in
   `communication.md` §8).
5. **Treat the KB as the spec.** Read `communication.md` → "Level derivation" (and the Aptitude equivalent)
   **before** coding. If the code you're replacing disagrees with the KB, stop and resolve which one is right.
   Don't rewrite the KB to match the new code.

## Invariants (Communication)

- The diagnosis is the first two eligible assessments of a chain. Diagnosis #1 stores no level and no NPS.
- **The diagnosis never confirms above the paper level:** `progression = min(calculated, paper level)`,
  capped at C1. A top-band diagnosis score only raises `suggested_cefr`. Downgrades confirm at the lower level.
- `suggested_cefr` drives the next test level. `assessment_cefr`/`practice_cefr` is the confirmed level shown
  to users. The two are never interchangeable in readers.
- Post-diagnosis: derive only on a same-level pair (otherwise carry forward). Confirmed = one rank below suggested.
  Assessment chains never downgrade; practice chains may.
- NPS = average of the two halves, each anchored at its own confirmed level (linear stored value; the curve is applied
  only at display time).
- Assessments with a 0 in any core ability (reading, listening, speaking, writing) never enter the chain.
- Live and backfill call the same pure core, so a replay of an untouched chain is byte-identical.

## Invariants (Aptitude)

See `aptitude.md` → "Level Update & Progression" and `nps-scale-and-curve.md`. The same process applies:
pin the rule with a test, run a replay dry-run, and state the blast radius.
