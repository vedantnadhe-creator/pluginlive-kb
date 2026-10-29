---
type: runbook
created: "2026-10-27"
last_verified: "2026-10-27"
tags: [runbook, assessment, scoring, proctoring, reports]
---

# Runbook: adding a new assessment type (the cross-cutting checklist)

## When to Use

When you add a new assessment type (a new `assessment_type.type_name`) or a new scoring path for an
existing one. The type-specific work (questions, candidate UI, the calculator itself) is the easy
part. This list covers the **general plumbing that every type has to plug into**. Each item here
already broke once because a type skipped it.

## The rule behind it

`assessment_assigned_students.scores_calculated = true` means **the result is final: the score AND
the proctoring integrity report are both done.** Nothing else means "final". Most bugs on this
list come from code that invented its own readiness shortcut instead of reading that flag.

Incident that prompted this doc (UAT 2026-10-27, `jershini.y+gasga@pluginlive.com`, AI Interview in a
Mix & Match float): score stored 08:07:06, proctoring report 08:08:01. A recruiter downloading the PDF
in that minute got a report **with no proctoring section**. The hold was working, but corporate-node
`getReportTargets` and student-node `checkReportAvailability` each had a private
"AI Interview + score row exists → downloadable" fallback that ignored the hold. Fixed by giving
the readiness rule one owner (below). student-node DEV `4b1730d0` / UAT `151e04a6`, corporate-node
DEV `c3d0aba6` / UAT `471ef417`. PROD pending.

## Steps

### 0. Submission: persist during the sitting, never at submit
Answers save as they are given (with retry), recordings upload in the background on signed URLs,
and the final submit only registers takes, freezes the paper, stops proctoring and submits parts
once each. Follow the checklist in [submission-pipeline.md](submission-pipeline.md) §4.

### 1. Scoring: the calculator only stores the score
- Add the branch to student-node `Assessment.calculateAssessmentScore` (`app/models/Assessment.js`).
  Return `{ message: "success" }`, or `{ message: "error", isTransient, status }` so the worker
  and cron can classify retries.
- The calculator writes scores and sets `scores_calculated = true` (plus `is_processing=false`,
  `calculation_error=false`, `calculation_attempts=0`). **It must NOT call `notifyAssessmentScored`**
  and must not decide whether the result is final. AI Interview v1/v2 used to ping the corporate ATS
  from inside the calculator, before the hold, so the ATS heard "final" before proctoring was done.
- **Every caller that runs a calculator ends with `holdScoresUntilProctored(id)`**
  (`app/helpers/scoreRelease.js`). This is the only place that keeps the result final or holds it,
  and the only place that sends the ATS ping. The current callers are the calc worker
  (`app/queues/calculationWorker.js`), the legacy score cron (`script/calculatePendingAssessmentCron.js`)
  and the AI Interview drop-off cron (`script/updateDropoutStatusCron.js`). A new caller (a backfill or
  re-score script) must do the same.
- Any re-score reset (`scores_calculated=false`) must also set `scores_held_at = NULL`. Otherwise the
  claim (`scoresHeldAt: null`) skips the row until the hold times out.

### 2. Proctoring: tell the hold whether the type is proctored
- Proctored types are listed in `PROCTORED_TYPES` in `scoreRelease.js`. A proctored type is held until
  its `proctoring_reports` row exists. An unproctored type is never held.
- If the type never closes its proctoring log, as AI Interviews don't, also add it to
  `AI_INTERVIEW_TYPES`, or every result waits for the full 15-minute timeout.
- Whatever finalizes the type's proctoring report must call `releaseHeldScores(id)` afterwards.
  The proctoring finalize worker and the AI finalize worker already do. The 1-minute score sweeper
  force-releases after `SCORE_PROCTORING_WAIT_MS` (15 min) as a safety net only.
- If the type is part of a Mix & Match float, the whole-assessment report
  (`proctoring_assessment_reports`) is rebuilt after every part's finalize. See `proctoring.md`.

### 3. Reports and readiness: never write your own "is it ready?" check
- **student-node:** `isResultReleased({ typeName, scoresCalculated, scoresHeldAt, hasScore })` in
  `scoreRelease.js`. `checkReportAvailability` (`app/handlers/common.js`) uses it.
- **corporate-node:** `RESULT_RELEASED_SQL` in `app/helpers/assessmentScoreSql.js`, the SQL twin of
  the same rule. `getReportTargets.renderable` uses it, and that drives the corp v2 Download button
  and `reportV2`. It expects the aliases `aas` and `at`.
- Keep the two identical. The only exception to "flag is true" is `LEGACY_SCORE_EXISTS_TYPES`
  (`AI_Interview` only): old rows where a score was stored but the flag never flipped. That
  exception never applies to a held row (`scores_held_at IS NOT NULL`). **Do not add a new type to it.**
  A new type has no legacy rows; if its flag doesn't flip, fix the calculator.
- PDF: add the type's branch to student-node `generatePDFReport`. If the platform renders no PDF for
  the type (as with Custom), make `checkReportAvailability` answer `false` and handle the type in
  corp v2 `ReportDownloadMenu` (`EXCEL_ONLY`).
- Type name spellings vary by which service answered (`Custom`, `Custom Assessment`,
  `Custom_Assessment`). Register the new type in corporate-react-v2 `lib/dashboard/format`
  (`TYPE_LABEL`) and match on the raw `type_name` server-side.

### 4. Scores on dashboards and exports
- corporate-node and institute-node `app/helpers/assessmentScoreSql.js` (kept as near-twins):
  add the score table to `SCORE_JOINS`/`RAW_SCORE`. **Pre-aggregate** any table with more than one
  row per assignment (per section or per session) before joining, or every COUNT/AVG fans out.
  A NULL score must stay NULL (see the `SCORE_EXPR` CASE). Types written in several passes need a
  "settled" guard like `AI_V2_SETTLED`.
- Gate displayed results on the released rule, not on "a score row exists".

### 5. Drop-offs and expiry
- `attempt-expiry.md`: the per-attempt `expires_at` and the drop-off cron. A drop-off that is scored
  goes through the same step 1. A non-`COMPLETED` row counts as proctoring-settled, so it is never held.

### 6. Tests
- Add your type's cases to the `isResultReleased` table test in student-node
  `test/scoreRelease.spec.js` (held → not released, flag true → released).
- If the type has its own scoring caller, add a test that it ends with the hold step.

## Verify (any env)

Right after a test attempt is submitted, watch the four timestamps in order:

```sql
SELECT a.scores_calculated, a.scores_held_at, a.submitted_at,
       (SELECT max(created_at) FROM assessment.ai_interview_scores s WHERE s.assessment_assigned_id = a.assessment_assigned_id) AS scored_at, -- or the type's score table
       (SELECT generated_at FROM assessment.proctoring_reports r WHERE r.assessment_assigned_id = a.assessment_assigned_id) AS report_at
FROM assessment.assessment_assigned_students a
WHERE a.assessment_assigned_id = '<id>';
```

Expected: between `scored_at` and `report_at` the row shows `scores_calculated=false` with
`scores_held_at` set, and the corp v2 Download button answers "still being scored". After `report_at`
the flag is true, `scores_held_at` is NULL, and the PDF includes the proctoring section.

## Rollback

Code-only (no schema change). Revert the two commits on the affected branch and redeploy student-node
and corporate-node.

## Related
- `assignment-calculation-queue.md`: calc worker, the `scores_calculated` hold, sweeper, retries
- `proctoring.md`: report-only proctoring, finalize workers, whole-assessment report
- `attempt-expiry.md`: drop-offs
- `ai-interview.md`, `ai-interview-v2.md`: AI Interview scoring paths
