# Auto-submit on the Fourth Proctoring Violation

**Status:** Live on DEV + UAT (2026-08-27); PROD pending

**Commits:** implementation — `Assessment-React` Development `07b7f81`, UAT `8524995`; `assessment-react-v2` Development `9dd66d4`, UAT `d805c3c`. Modal-copy refinement — legacy Development `2e9c287`, UAT `bab42ea`; v2 Development `8adf92b`, UAT `21f2b06`.

## Requirement

Change the candidate assessment violation flow so that an assessment is auto-submitted on the **fourth** proctoring violation instead of the third.

- Violations 1, 2, and 3 show the existing warning experience and do not submit the assessment.
- On violation 4, stop normal assessment interaction and show a modal with this message:

  > You've violated the rules more than 3 times, so your assessment will be auto-submitted.

- The modal has one action: **Understood**.
- The modal contains only the violation message and **Understood** action; it does not repeat instructions explaining the button or five-second timeout.
- Clicking **Understood** submits the assessment immediately.
- If the candidate does not click it, the modal remains visible for **5 seconds** and the assessment is then submitted automatically.
- The submit path must be idempotent so the button and five-second timeout cannot create duplicate submissions.
- The timeout must be cleared when submission begins or the component unmounts.
- The modal cannot be dismissed with Escape, backdrop click, browser navigation within the app, or a close icon.

## Scope

Apply the behavior consistently anywhere the existing tab-switch/fullscreen violation counter can auto-submit an assessment, including:

- Aptitude
- Custom
- Communication, including the separate Hinglish runner
- Role-Based
- AI Interview
- The v2 candidate assessment runner

The v1 and v2 candidate applications do not share this logic, so each must be changed and tested independently. Existing mobile interruption exemptions remain unchanged; only events already counted as punitive violations contribute to the four-violation threshold.

## Acceptance Criteria

1. After each of the first three counted violations, the candidate can acknowledge the existing warning and continue.
2. The assessment is not submitted on violation 3.
3. Violation 4 displays the blocking modal with the required message and **Understood** button.
4. Clicking **Understood** before five seconds submits immediately.
5. With no click, submission begins five seconds after the modal appears.
6. Clicking at the same time as the timeout produces only one final-submission request.
7. Further visibility/fullscreen events while the modal is open do not create additional warnings, timers, or submissions.
8. Manual submission and assessment-timer expiry continue to work as before.
9. Automated tests cover violations 1–4, immediate acknowledgement, timeout submission, and the button/timeout race.

## Implementation Note

The legacy runners use `MAX_TAB_SWITCH_WARNINGS = 4`; AI Interview uses `MAX_FULLSCREEN_VIOLATIONS = 4`; v2 uses `MAX_TAB_VIOLATIONS = 4`. The fourth event opens the new blocking modal and delayed submission state, while the first three events retain the warning flow. The immediate button and timeout paths converge on guarded/single-flight finalization.

## Verification and Deployment

- `assessment-react-v2`: 226 tests passed, ESLint passed, and the production Next.js build passed.
- `Assessment-React`: the production webpack build passed. Its repository-wide lint remains unusable as a release gate because of pre-existing baseline violations unrelated to this change.
- DEV and UAT containers were rebuilt on their target hosts. Both legacy endpoints returned HTTP 200, both v2 endpoints resolved through their canonical redirect, and all four running bundles contained the new "more than 3 times" modal copy.
