# Corporate Roles v2 (ATS) on corporate-node

Live on DEV since 2026-10-29 and on **UAT since 2026-11-04**. PROD pending.

The Roles screens in `corporate-react-v2` (`/v2/roles`, `/v2/roles/new`, `/v2/apply/<id>`, short links `/v2/a/<code>`) are served by **corporate-node**. `corporate-node-v2` is no longer used for Roles; on UAT its service still runs but nothing routes Roles traffic or the score webhook to it.

## Flow

1. Recruiter creates a role (paste or attach a JD), picks the application form, and floats it. Each invited campus gets one invite mail (POCs + wizard contacts + campus email, with the recruiter's CC).
2. Candidate applies on the PluginLive form. An uploaded CV goes to the private bucket under `role-applications/`; the answers go to `job_role_response` and the role's Google Sheet in the FormData folder. A contact-only form can be submitted without a CV, address or education.
3. form-data-normalization picks the sheet up, normalizes it and calls student-node `create-full`, which creates the applicant (`job_role_student_map`) and, when provided, copies the CV to the public docs bucket as `cv_url`.
4. The evaluation engine (BullMQ, 5-minute scan plus events) starts applicants in the live workflow. With an enabled Screening stage, corporate-node AI match scores the applicant and a candidate with no CV is held for the recruiter. Without Screening, applicants go straight to the first enabled stage; an assessment stage sends its invite.
5. student-node posts each score to `/v2/hooks/assessment-scored`, which queues the advance pass. A recruiter fit override holds a candidate only in the round it was made in.

## Evaluation setup gate

A process can't be saved until every **enabled** stage is configured. The green tick on a stage row and the save button read the same check (`isStageConfigured` in `roles/[id]/_constants.ts`): the stage has a type, and an assessment type passes `configIssues`. This covers **Setup Now / Save changes** in the Setup evaluation dialog and **Continue** on Quick Evaluation's "Set up evaluation" step. While a Role Based or AI Interview stage is still being prepared, or its prefill failed, the button stays off and a note names the stages ("Still to set up: ..."). Disabled stages don't count: they are never prefilled, and corporate-node's `unconfiguredStages` skips them too. A live process with an unfinished enabled stage can't save edits until that stage is fixed. Quick Evaluation's Start evaluation retry only runs on a live process with no unsaved edits.

AI interview stages use the assessment module's own forms: stage type `ai_interview` opens the single scrolling form and floats `AI_Interview`; `complete_ai_interview` opens the five-step form and floats `AI_Interview_v2` (package `assessment-creation` 0.1.2-bugfix.28, adapter `src/lib/stageConfig/interviewPanels.ts`). Both store instructions and the second language. Communication & Language's 20% comes out of the other parameters, so the total stays 100. Dispatch keeps the ids the form sent, because the scorer finds the locked parameter by id `communication`; only a parameter with no id gets a name slug. Setup Now also refuses a Complete AI Interview flow admin-node would reject at float time: a reading, listening or custom row with no instructions, more than 50 questions on a row, more than 50 voice questions, or a parameter weight of 0. Hand-written choice questions are still only checked by admin-node at float time. Only companies subscribed to `AI_Interview_v2` see the stage type.

## Degree & department master

The picker offers the degree/stream master, the same list v1 role creation uses: corporate-node `GET /corporates/:corporateId/degrees/v2` calls institute-node's `institutes/search/degreeStreams?pageLimit=700&status=1` and returns `{ degree, level, departments }` (BFF `/api/roles/degrees`, hook `useDegreeCatalogue`). That list also carries inactive rows whatever `status=1` asks for, so corporate-node keeps active degrees with active streams only and merges duplicate names; degrees with no stream aren't offered. PHD counts as PG, PG diplomas as Diploma, and ITI (stored as a DIPLOMA) as ITI.

Specialisations (since 2026-11-12): `degrees/v2` also returns, per degree, `specializations` ({ department: names }) and the master's `shortForm` ("B.COM", matched by the picker's search). They come from the platform search service `POST /search/degrees/streams/specialisations`, called by corporate-node (`services/evaluation/degreeSpecialisations.js`, env `SEARCH_API_URL` + `SEARCH_API_KEY`, cached 1 h per pod; an outage only drops specialisations). Its ids are `institute.specialisation_master` ids, names are read from that table. Specialisations are matched to a department by master ids (degree id + stream id), never by name, since several stream rows share a name; a `specialisation_master_stream_map` link scoped to another degree (`degreeStreamMapId`) is dropped, case duplicates merge, and ALL-CAPS names read as words. The picker's search matches from the start of a word only. The picker (since 2026-11-17, corporate-react-v2 `d2fe441`) shows each degree as an accordion with "Select all" and one option per department plus one per specialisation, labelled "Department with Specialisation"; every option is its own pick and a tick applies at once (no Clear / Apply). Chips read "Degree · Department with Specialisation". A department pick saves as `Degree · Department` and still means the whole department, any specialisation; a specialisation pick saves as `Degree · Department · Specialisation`, which `resolveEligibility` writes exactly as v1 does: the item's `specialisationId: [id]` plus `job_roles.specialisations` / `specialisations_ids`. A specialisation not offered under that department is refused (422), never widened. Up to 500 eligibility labels. Picker layout (since 2026-11-17, corporate-react-v2 DEV 53f2bed / UAT 20e9400, frontend only): the menu is placed only between the wizard's top bar (`.wz-topbar`) and its Back/Continue bar (`.wz-actions`), flipping up only when there's more room above; long chips truncate with "…" (full text on hover) and keep their ×. The four-row cap on the active chip field (eca4f1d) was ROLLED BACK on 2026-11-18 (DEV 72f92e0, UAT 0e4ad88): `.rd-degree` is shared by Office location, Skills and Qualifications, whose menus render inside the box, so `overflow-y: auto` + `max-height` clipped them and their dropdowns stopped opening. Never put overflow on `.wz-root .rd-degree.is-active`; scope any cap to the Degree picker's own class. Master data quirk: specialisations hang off the stream, so some odd ones appear (e.g. under B.Com · Accountancy), and names keep the master's mixed casing.

Degree-picker interaction follow-up (2026-11-19, DEV `6a4a14b`, UAT `27f002c`): clicking anywhere in the field, including chips and the "+N more" area, opens the menu. The chevron toggles it and each chip's × removes only that pick. The four-row scrolling cap is scoped to the degree picker's own field; other wizard dropdowns retain their existing overflow behavior.

Candidates tab Degree & Department filter (client-side, since 2026-11-17): grouped per degree; a "Department" option matches candidates in that department **without** a specialisation, "Department with Specialisation" matches that specialisation. Applicants: `profile.specialization` comes from `current_course.specialisation` (rarely filled; may hold several, comma-separated). The applicants Export Sheet adds Specialization, "Avg. Performance Score" (the table's rule: status until scored, then the finished scores summed over ALL the role's assessments — an unfinished one counts as 0 — with "X/N assessments"; `helpers/rolePerformance.js`; since 2026-11-17). The match column is headed "Resume Match Score" and one column per assessment when there are several, once the process is live.

Saving: `resolveEligibility` maps a master label ("Bachelor Of Technology · Civil Engineering", or the bare degree for every stream) to its `degree_stream_map` rows. Curated labels on older drafts and JD-inferred picks ("B.Tech / B.E. · Civil") still resolve through `DEGREE_CATALOGUE`, show as chips, and aren't ticked in the tree. Unknown labels get a 422.

A whole-degree pick is stored as a degree-only item with no map id, so every save rebuilds `degree_stream_map_ids` and `domainIds` for kept items from the master. Without that, the next autosave left the ids empty and AI Suggested showed 0 colleges.

AI Suggested lists every match, not a page: the wizard calls `matched-institutes` with `limit=100000` (the route's ceiling, above the whole campus table) in one response, about 0.9 KB a college. So the tab count, search, tiers and Select all cover all matches on the client. Cards and the Selected column mount 100 at a time as they scroll (`useRevealOnScroll`). Measured on DEV: 13,497 colleges for an 809-map draft took 7.8 s and 12 MB. Other colleges still loads 40 rows per search from `institutes/v2`. Publish inserts and mails invited campuses one at a time in the request, so a very large Select all is slow there.

A draft stores invited campuses as ids (`invite_email_template.campusIds`); the role response adds `inviteCampusNames` (`findCampusNames`), which the wizard seeds its name map from so Resume draft lists them by name.

Known gap: `12th` and `Certifications` are offered by the picker but exist in neither the master nor `DEGREE_CATALOGUE`, so picking one fails on save with "Some degrees are not known". Test rows in the master ("BACHELOR OF TEST DEGREE") show up on DEV and UAT.

## Applicant export

**Export Sheet** on the candidate list's selection bar downloads the server workbook for the ticked rows: `POST /corporates/:corporateId/roles/v2/:roleId/applicants/export.xlsx` with `{ applicantIds }` (BFF `POST /api/roles/:id/applicants/export`, `exportApplicants` permission, up to 5,000 ids, 422 otherwise). `GET` on the same path exports by list filter. Both add one column per application form question from `job_role_response`; FILE_UPLOAD questions are left out. The stage and final-candidates drawers still export their own short CSV of the tier on screen.

## Empty lists

The Roles and Assessments lists tell "nothing exists" from "filters hid everything" with `isNarrowed` (a status tab, search or filter is on; `useRoleFilters`, `useAssessmentFilters`). Not narrowed: the first-run empty state, "No roles yet" / "No assessments yet" / "No candidates yet", with no button of its own because the top bar's Create action is already there and permission-aware. Narrowed: "No ... match these filters" with Clear filters, which also returns the list to the All tab.

## Resuming a draft and the JD parser

Autosave stores every wizard field, blanks included. On resume, only values the recruiter set (`recruiterSetFields` in `roles/new/_utils.ts`: filled in and different from the form default) are protected from a JD parse, so an upload fills a blank draft and never overwrites their edits. DEV + UAT, 2026-11-04.

The parser's text is not stable: the same PDF has returned about 1,400 to 3,100 characters across runs.

## Evaluation stages follow the subscription

A role can only use assessment stages when the company has Assessment access (Feature Access, ASSMT. column) and a current subscription to that type (`assessment.subscribed_corporates`, not past `end_date`). Turning access off leaves the subscription rows in place, so `blockedStageTypes` checks access first and blocks every assessment stage type without it. DEV + UAT, 2026-11-04. Rule: `services/evaluation/subscribedStages.js`. AI proposals, the default process and copied processes leave the others out, `GET assessment-options/v2` returns `unsubscribedStageTypes` for the Stage type dropdown, and Setup Now answers 422 naming the stage. A live role keeps a stage it already runs. Multiple Assessments shows only with two or more subscribed assessment types (the dropdown offers only Screening and Human Round until `assessment-options` has loaded, never every type), and Complete AI Interview only with an `AI_Interview_v2` subscription; a type that cannot be dispatched yet is left out of the Stage type dropdown altogether (`NOT_SENDABLE_STAGE_TYPES`), though a stage already set to it still shows, with its notice. UAT hides both; on DEV Complete AI Interview is being enabled. Running out of tokens is not part of this rule; it is checked at float.

## Screening Auto-Pilot is opt-in (since 2026-11-17, DEV + UAT)

The Screening card has an Auto-Pilot switch (corporate-react-v2 `9fe6dd1`). corporate-node honours it only when `config.autoPilot === true` (`rounds.stageAutoPilot`); unset or false = screening scores everyone but moves and closes nobody (strong fits held as recommended, medium/weak held for the recruiter). On: strong fits advance to the next stage, weak fits are closed, medium is held. A recruiter fit override or a missing resume is always held. The frontend reads an unset Screening as off (`useWorkflow.defaultAutoPilot`); rounds still default on.

Data reset at rollout: the frontend used to write `autoPilot: true` on every stage, Screening included, before any switch existed, so those were reset to false (DEV 80 rows 2026-11-16, UAT 26 rows 2026-11-17; rollback id lists `~/deploy-backups/screening-autopilot-true-ids-2026111{6,7}.txt` on each box). **PROD: run the same reset BEFORE deploying corporate-node with this change:**
`update corporate.workflow_stages set config = config || '{"autoPilot": false}'::jsonb, updated_at = now() where stage_type='screening' and config->>'autoPilot'='true';`

Before 2026-11-17 (from 2026-11-05) screening never moved anyone regardless of config.

## Workflows without Screening start at stage 1 (since 2026-11-19, DEV + UAT)

`screenRole` checks the enabled stages with `hasScreeningStage`. Without Screening, it batches eligible applicants through `dispatchToStage` for the first stage, sending an assessment invite or entering a human round as appropriate. This path does not run resume screening, save a screening verdict, or request an AI match. It does not require a CV or resume-match score. Later scans leave already-dispatched or decided applicants alone and retry failed dispatches.

Recruiter **Advance** on an applicant with no workflow dispatch also enters stage 1. Previously the Screening fallback treated that applicant as already in stage 1, so Advance skipped to stage 2; the automatic pass assigned the stage without sending its assessment. Workflows with Screening keep their existing rules. Closing an application still uses the first-stage fallback when Screening is absent.

corporate-node DEV `ec313b50`, UAT `f9d5e589`. Both running containers verified on 2026-11-19. Tests in `test/roleEngineV2.spec.js` cover the first-stage invite, no duplicate on the next scan, no screening verdict or AI-match request, unchanged Screening holds, and manual Advance to stage 1. No schema migration or historical-data rewrite is included.

## Stage deadline and candidate validity (since 2026-11-17, DEV + UAT)

Each assessment stage's config carries `candidateValidityDays` (days each candidate gets; Review Assessment drawer, required in the UI) and optional `stageDeadline` (`YYYY-MM-DD`, stage card). corporate-node (`rounds.stageWindowOf / windowEnd`, `dispatch.js`):
- the deadline, when set, is the float's end date (wins over the role's end date); otherwise the validity (else `durationDays`, floor `ROLES_V2_MIN_RUNWAY_DAYS` = 7) sets how long the float stays open from now;
- Setup Now fails if the deadline has passed or is sooner than today + validity (IST day, same wording as the frontend's `windowIssue`);
- moving a candidate into a stage whose deadline has passed fails ("closed on <date> — move its stage deadline…");
- a Multiple Assessments (Mix & Match) round sends `assessmentValidityDays`, so each candidate gets their own days from their invite;
- since 2026-11-19, single-assessment stages send `candidateValidityDays` to admin-node on creation, later additions, role resends and reopening reminders. Values are whole days from 1 through 365. admin-node stores each candidate's real UTC expiry in the existing `assessment_assigned_students.valid_until`: the earlier of the stage's closing instant and `max(assignment created_at, stage opening instant) + validity`. Map dates contain IST wall-clock digits and are converted before this calculation.

Queued assignments persist the policy in `configSnapshot` and set the expiry when inserting the assignment. Synchronous assignments set it before issuing the invite. A delivery retry or reminder preserves the stored expiry; a role resend resets the attempt and starts a fresh window capped by the stage deadline. Existing integrity-retry deadlines and Mix & Match group policies are preserved. Invite text, short-link expiry and student-node's existing start gate read the same `valid_until`; manual reminders prefer it over the shared map date. Legacy requests without a candidate-validity policy keep their existing behavior. No schema migration is needed on DEV/UAT.

Code: corporate-node DEV `ee5f352d` / UAT `5f6182bc`; admin-node DEV `4cb6da1` / UAT `d20db60`. PROD pending.

## Contact-only application form and screening (since 2026-11-19, DEV + UAT)

New roles start with **First Name, Last Name, Primary Email Address and Mobile Number**, retaining the server's question IDs and validation. Selecting a PluginLive template loads its full questions; company templates retain their saved questions. Reset returns to the four contact fields. Resumed drafts and edited roles keep their saved forms. A CV remains required when the recruiter includes a required upload question.

The intake and normalization pipeline accepts missing CV/address/education. Applicants expose missing facts as null or empty collections. With a Screening stage, an applicant without a CV and score is immediately held for the recruiter, with a missing-resume reason rather than a pending scoring message. The screening pass does not queue a CV match for this state. Once a CV is available, the missing-resume hold permits a scoring retry, including after an earlier failed match. Workflows without Screening still enter the first enabled stage.

Frontend: DEV `f714083`, UAT `af842be`. Screening: corporate-node DEV `ee5f352d`, UAT `5f6182bc`. Verification covers four-field intake, required-CV validation, sparse applicant responses, holds and retry after a CV is added.

## Completed attempt awaiting a score (since 2026-11-19, DEV + UAT)

The role round outcome reads **Attempted — Awaiting Score** when `attempt === "COMPLETED"` and `score == null`. The shared `roundOutcome()` helper in `CandidateDrawer.tsx` supplies the candidates table and drawer. Once a score exists, the pass-bar outcome still takes precedence; rejected, failed and manual states retain their existing labels. This replaces "Sat it — awaiting scoring" without changing assessment state or scoring. corporate-react-v2 DEV `e0d8a7a`, UAT `7195702`.

## Applied vs in screening (since 2026-11-17, DEV + UAT)

Applied = in (ACTIVE), in no stage or round, and untouched by screening: no AI match score/summary/error, no `screening_results` row, no fit override (`helpers/rolesV2.AWAITING_SCREENING_SQL`; same rule as the frontend's `isApplied`). `GET /roles/v2` sends `pipeline.applied` and leaves those out of `underEvaluation` (the bar's Applied segment). The roles-list caption "N Applied" under the bar is everyone who applied (`pipeline.applicants`), not that segment (corporate-react-v2 `3e657d6`, UAT `37cb7ae`, 2026-11-17). Each applicant carries `awaitingScreening` with the same rule.

## Dashboard "Actions to be taken" (since 2026-11-17, DEV + UAT)

`GET /corporates/:id/dashboard/v2/application-tracking` → `needsAttention`, ordered by tier then largest backlog (`corporateRolesDashboardV2Handler.buildNeedsAttention`): deadlines (`role_closing`) → broken (`invites_failed` = current round dispatch failed, `resumes_unscreened` = AI match failed / screening error and no score) → offers (`hiring_target_reached` offers ≥ vacancies, `offers_declined`, `offered_no_offer` = SELECTED with offer NOT_RELEASED, `offers_awaiting_response` = RELEASED/NEGOTIATED) → decide (`awaiting_decision` = human round, `results_ready` = every part COMPLETED/DROPOUT, `held_for_review` = screening held a medium fit) → `strong_matches` → chase (`yet_to_start` = every part PENDING) → set-up (`no_applicants` open 7+ days, `no_activity`, `draft_roles` corporate-wide with `roleId: null`). Counts come from one grouped query (`RolesDashboardV2.roleRows`, current dispatch + latest assignment per part) plus `draftCount`. Candidate rows cover open and application-closed roles; offer rows every scoped role. `offer_outcome_pending` and `awaiting_review` are no longer sent. The frontend skips a kind it doesn't know instead of crashing — ship corporate-react-v2 ≥ `7775b43` (UAT `35f6d22`) with corporate-node ≥ `ea1d0498` (UAT `217532e0`).

## Moving a candidate back

Move to a Stage warns on a move to an earlier stage, and says when an assessment goes out again. A move back to an assessment round the candidate already has a row on resends it (`resendMapIdFor`, `resendStageAssessment`): the assessment window is extended if needed, then admin-node `resendInvites` with a selection resets the attempt and re-invites. admin-node archives the old attempt first, but its score leaves the screens. The resend runs before anything moves, so a failure leaves the candidate where they were. Forward moves, same-stage moves, and human or screening rounds send nothing. Moving forward to a round they left reactivates it with no new invite.

A candidate moved off an assessment round without starting it can no longer take it: Move, Not selected, Shortlisted and drawer Advance call admin-node `POST /assessment/candidateAccess`, which sets `valid_until` to now on an untouched attempt (student-node `assignmentWindowState` then answers "This assessment is no longer available."). Nothing is deleted, because removing an assessment's last assignment row loses its question set. Coming back reopens it with a reminder; `resendInvites` clears `valid_until` too. Attempts already started or finished are left alone, as are candidates moved before 2026-11-06 and candidates deleted from a role. PROD needs the `valid_until` column.

The candidates list ignores `moved_back` dispatch rows, so it shows the round the candidate is on now.

## Fixes 2026-11-11 (DEV + UAT)

- Closing or cancelling a role closes every assessment round its candidates were sent to (`setRoleAssessmentAccess`, admin-node candidateAccess). Reopening opens only each candidate's current round. A role reaching its end date keeps evaluating.
- Stage assessments are named "<role> — <stage>" with no stage id. `findMapId` only adopts maps no workflow stage owns, so a duplicated role never joins the original's assessment. The 17 existing UAT names were renamed; a backup is at ~/backups/acm_names_backup_20261111.json on the UAT box.
- New Aptitude stages default to every section, with topics spread across sections (`completeAptitudeSelection`).
- Candidates filter: "Current arrears", from the form's current arrears/backlogs answers (the highest).
- Degree and department search, and filter-panel search, match short forms (CSE, ECE, BE, MBA, btech) via `lib/nameSearch.ts`.
- Campus invites: an institute with an ATS subscription (`institute.institute_subscription.accessLevel` 1 = ATS or 3 = ATS + Assessment) gets the invite **Pending** (status 0) and approves or rejects it on its Roles page; every other institute is accepted at once (status 1). The wizard (`inviteCampuses`) and the role page's Invite institutes drawer, re-invites included, both apply it through `CorporateSavedAssetsV2.acceptNonAtsInvites`. Apply and evaluation never read that status (since 2026-11-12; earlier invites keep theirs).
- Duplicate role saves the copy at step 2, so the wizard opens on Role details and never re-runs the AI JD fill over the copied fields.
- Apply form: a date question whose label names a work end date (`end`, `leaving`, `last working`, e.g. "End Month-Year") offers "Currently working here". Ticking it answers `Present`; corporate-node `validateAnswers` accepts that even on a required question and stores a blank end date, which normalization reads as still employed. A date or the tick is required.
- Setup evaluation on a new role keeps the "Designing the evaluation process" loader until every assessment stage is built (a role-based paper takes about 40 s), or a build fails, or 90 s pass. Stages still building later show "AI is building…" on their row.
- Add contact details (TPO contacts) mounts 100 colleges at a time as it scrolls and only the open college's fields.
- A user without dashboard access lands on Roles whenever the company has Roles (`DashboardAccessGate`).
- A Custom Assessment round has no PDF report: the timeline and Export Reports download that candidate's Custom sheet (`exportCandidates`, `.xlsx`) instead (`getRoundReport`).
- Other colleges count subtracts only the suggested campuses the search returned. The Roles empty state names the search. Role screens say "already applied for this role".

## Passing score and Auto-Pilot

An assessment stage's pass bar is its "Passing score: N%" evaluation parameter. With Auto-Pilot on, that row can't be removed and only its number is editable (0-100; left blank, it goes back to the previous value). Turning Auto-Pilot on, or loading a stage with parameters but no bar, adds the line at the stage's bar or 60, the backend default. A stage with no parameters gets it from the AI build. UI rule only: a save without a bar still runs on 60.

## Apply form details

"Same as permanent address" sits above the first Current Address question (after Permanent Address - Pincode), when the form has matching Permanent and Current Address questions (`addressCopies`). While ticked, Permanent Address answers copy into Current Address as they are typed; editing a Current Address field unticks it. Not in the form builder, and nothing extra is stored.

"Let AI fill this in from my resume" sits above the resume upload, which is pinned first, so it is directly below College. Date and month fields open the calendar on a click anywhere in the box (`showPicker`); typing still works.

## Locked application form fields

On a locked field with options, a recruiter can add options (DEV + UAT, 2026-11-04). PluginLive's own options stay read-only because normalization relies on them; added ones can be edited or removed. `withLockedOptions` folds them into the question.

Known gap: normalization validates Gender against `gender_normalizer._GENDER_MAP`, so a candidate who picks an unrecognised added value can fail normalization and never reach the role. Safe additions: Transgender, Intersex, Non-binary, Prefer not to say, Other. State and year fields are checked too. Nothing warns the recruiter yet.

## One application per email

A role takes one application per email (DEV + UAT, 2026-11-04). `RoleIntakeV2.hasApplied` counts a stored response or an applicant row, including one the recruiter soft-deleted, so a deleted candidate cannot apply to that role again. Submit answers 422 on the email question. The form also calls `POST /public/roles/v2/:roleId/apply/check-email` when the email field loses focus (60 checks per 10 minutes per IP). A candidate can no longer resubmit to correct an application. Matching is by email only, and Tally-form roles are not covered.

The form's dropdowns and College picker are the DS `CreatableSelect` without `onCreate`: a searchable select.

## Custom Assessment stages

A Custom Assessment stage uses the assessment module's builder (package `assessment-creation` 0.1.2-bugfix.29): saved question banks, Excel or manual sections. A stage references sections by id, so Apply saves each new or edited section through `/api/assessments/custom-banks`; an unedited bank is reused, and a reopened stage reads its questions back. Saving needs `createAssessment` or `manageEvaluation`. Apply refuses what corporate-node would drop the whole section list for: more than 20 sections, a name over 200 characters, marks below 1, or a time that isn't whole minutes.

## Resend Assessment (candidates bulk bar)

The Roles bulk bar resends each candidate's current assessment round, through `POST /api/roles/:id/applicants/resend`, with `remindCandidates`. It reaches any candidate sitting in an assessment stage, in any state, and resets the attempt. A finished candidate's score is cleared (admin-node archives the attempt to `assessment_attempt_archive` first), the dialog says so, and the round scores the retake normally, so with Auto-Pilot on a retake can advance or reject them. admin-node's `onlyDroppedOff` option on `resendInvites` exists but nothing sends it. Selected emails match regardless of case, and a mix-match float where nobody was reset mails nobody.

## Moves and offers

A Move can carry a reason per candidate (`moves[].reason`, 500 characters). It is stored as the dispatch's `move_reason` and shown in the activity feed as "Reason: …". The engine's default reason is not shown. An offer answer (accepted or rejected) no longer needs the offered step: `/applicants/offers` moves the candidate into Offer first, and the final round accepts it from `offered` or `offer_sent`. A candidate marked not selected can't get an answer recorded. Deploy the backend before the frontend, because the frontend no longer sends the offered step.

## Assign Training (LMS, since 2026-11-17, DEV + UAT)

Hires whose offer is accepted (`_applyRoleStatus` SELECTED and `_offerStatus` ACCEPTED) can be given an LMS training from the bulk bar: **Assign Training (n)**, needs `assignTraining`. The LMS is **lmsv2**; the ATS only assigns, and learning, progress and certificates stay in the LMS.

- **Catalogue:** `GET /corporates/:corporateId/trainings` (BFF `GET /api/trainings`) lists **every published** lmsv2 module group ("Programmes": name, module count, total `learning_minutes`) and every published module. It is not limited to the corporate's own LMS content. Ids are `group:<uuid>` or `module:<uuid>`.
- **Assign:** `POST .../roles/v2/:roleId/applicants/training { applicantIds (1-500), trainingId }`. The training is re-checked against the catalogue; hires without an accepted offer, without an email, or who already have that training are skipped with the reason. One training per hire: a new pick replaces the old one, and the LMS removes the old access.
- **Delivery:** each assignment is a row in `corporate.training_assignments` (`queued` -> `assigned` | `failed`), delivered by the roles v2 worker job `training.enroll` (5 attempts, exponential backoff from 30 s; on an env with the engine off it is sent in-process, one attempt). An LMS 4xx is final at once. The row shows "Training: <name>", "sending to the LMS" while queued, and "Not delivered · Retry" (risk colour, error in the tooltip) when failed. Retry: `POST .../applicants/training/retry { applicantIds }`. Activity log: `training.assigned`.
- **LMS side** (lmsv2 edge function `ats-training`, routes `/catalogue` and `/enroll`): server to server only, gateway anon key plus header `x-ats-key` compared with the function secret `ATS_SHARED_KEY`. `/enroll` finds the learner by email or creates a `students` row (`metadata.source = 'ats'`) under the corporate's LMS entity, then grants a group (`module_group_assignments`, scope `student`) or a module (`user_module_access`, or `pending_module_access` until first sign-in). It is idempotent. New learners get the LMS welcome email and sign in with their email and a one-time code; the first sign-in creates their login and releases held module access.
- **Corporate <-> LMS entity:** `corporate.corporates.lms_institute_id`. If it's empty, the LMS matches a `corporate` institute by exact name (case-insensitive) or creates one (`notes` "Created from the PluginLive ATS"), and the ATS stores the id. Two LMS corporates with the same name answer 409; set `lms_institute_id` by hand then.
- **Env (corporate-node):** `LMS_ATS_URL` (`http://172.17.0.1:8240/functions/v1/ats-training` on DEV and UAT, the lmsv2 gateway's bridge port), `LMS_ATS_ANON_KEY` (lmsv2 anon key), `LMS_ATS_KEY` (= lmsv2 `ATS_SHARED_KEY`). Missing values fail loudly ("Couldn't load trainings"). The secret is read when the edge-runtime container is created: after changing it run `docker compose up -d --no-deps functions` in `~/lmsv2-sb`, not a restart.
- **Picker rules (2026-11-18):** a training every selected hire already has (delivered or queued) is shown but disabled ("Already assigned"); one only some of them have says how many will be skipped. The server skips them too, so nothing is assigned twice.
- **Offer state (2026-11-18):** the role page treats a hire as accepted when the application says so (`Offer accepted` recorded from the Applicants tab), even if the final round's dispatch still reads `offer_sent`; `/applicants/offers` updates the application only, not the final-round dispatch (open).
- **DB:** DB-Scripts `ATS LMS Training Assignment/20261117T064737Z__ats_lms_training_assignments.sql` (DEV + UAT applied, PROD pending). Apply it before corporate-node: the applicants list joins `training_assignments`.

## Apply form colleges

`GET /public/roles/v2/:roleId/apply/colleges?search=&limit=` searches active colleges by name or city (2+ characters, 25 results, 300 per minute per IP). It returns id, name and city, never contacts. The College field lists invited colleges first, then the search, and removes duplicate master rows by name and city. Submit accepts any active college and stores it by name, like Others. Off-campus roles show no College field, because the answer was never saved (`collegeSearch` on the apply response). Every CV upload is an autofill call, limited to 60 per 10 minutes per IP.

Invites carry `tier` (the company's own tier first), and applicants carry `assessmentTitle` for their current stage.

## Normalized data on applicants

The candidate drawer's Candidate details and the Export Sheet show normalized values, not what the candidate typed. `RoleApplicantsV2.withNormalizedAnswers` overlays the form answers (`helpers/normalizedAnswers.js`): college, degree and department for UG, PG, Diploma and ITI come from the current course and education rows, Select Your College from the campus, current and permanent address city and state from the frozen personal profile (`role_application_personal_profile.corr_*` / `perm_*`, since 2026-11-17), and education city and state from `response_data`. For an existing student the frozen `response_data` is their old profile (payload capture keeps scalar columns only), while the personal profile is overlaid from this application, so it carries the normalized city (e.g. `chnai` → Chennai). A blank work end date whose start date is answered shows as **Currently working** in the drawer (`formOf`), matching how normalization reads it. A blank answer stays blank, nothing normalized leaves the form answer, and custom questions are never changed.

Experience reads `work_experience`, then the stated `total_experience` when that is 0. `work_experience` is derived from the resume, and a role with no end date yields 0, so the card, export and experience filter use the stated figure.

form-data-normalization matches each `education_<level>_city` through the city matcher without the candidate's pincode, which would steer a college's city (`_match_education_cities`). Arrears fall back to the form's own column (`PG - No. of Current Arrears/Backlogs`) when the LLM leaves a level out. Both apply to new applications only; rows ingested earlier keep their stored values.

The fix lives in the worker, and `auto_deploy.sh form-data-normalization` only replaces the API container. Recreate `datanormalization-worker` and `-cron` on the new image too.

## Role assessments stay on the role

A stage's assessment name ends in ` · <first 8 of the stage id>` (`assessmentNameFor`); dispatch finds the assessment by that name, so it stays stored. The Assessment performance tab hides it (`withoutStageId`). Anything else that reads the stored name still shows it.

Add candidates (role page drawer, Quick Evaluation) accepts sheets, CVs and manual entry. A sheet is read by admin-node `parseCandidateSheet` for the count only; accepted headers are `SHEET_COLUMN_ALIASES` in `app/helpers/candidateSheetRows.js` and match exactly (`Email Ids` is on the list, `Secondary Email` is not). The screen shows "N candidates from your sheet", not rows; to change a sheet, remove the file and upload again. CV and manual rows stay listed. The Assessment page drawer still lists sheet rows.

On save the original file goes through `/bulk-upload/inspect` then `/commit` (`addRoleCandidates`), on the mapper's proposed mapping with no review step; a tab with no email mapping is skipped, and a workbook with none is refused. CV and manual rows go first, as a small built workbook, so someone in both keeps the CV. A CSV is converted to a workbook in `inspectUpload`. A row already on the role counts as a duplicate, so a retry is safe.

Mapped columns reach normalization. Unmapped columns are stored in `job_role_response.response` but are not written to the role's Google Sheet (`buildSheetRow` keeps only the sheet's headers), so normalization never sees them.

Assessments a role floats for itself (evaluation stages, Quick Evaluation) stay off every assessment surface: the Assessments list, candidate-wise list, dashboard KPIs and Active Assessments, week rail, Schedule and financial-year counts. One rule covers them: `NOT_ROLE_EVALUATION` in `helpers/corporateAssessmentSql.js`. The Usage quota in the header still counts them. DEV + UAT (2026-11-04).

## Sign-in lands on v2

Corporate users land on `/v2/signin#token=` and then `/v2/dashboard`, on DEV and UAT since 2026-11-04.

- `CORPORATE_LOGIN_V2="true"` in user-management-node `.env.dev` / `.env.uat` drives password, Google and account-selector sign-ins (`utils.getLoginUrl`). PROD: not set, so corporate logins still open v1.
- An admin Checkin (`/user/portal/signin`, journey CORPORATE) always returns the v2 link, with or without the flag.
- The v2 menu has no links back to v1, so v1-only screens such as the Interviewer dashboard are reachable by direct URL only. v2 ignores the multi-account token (`mat`).
- Rollback: remove the flag from the env file and redeploy user-management-node.
- `/user/portal/signin` (check-in and check-out) needs the caller's JWT and only re-scopes their own internal account (`helpers/portalCaller.js`), on DEV and UAT since 2026-11-04. It is not `isPrivate` on purpose: check-out signs out first and then calls it with that token, so a token signed out in the last 2 minutes is still accepted. PROD code does not have this check yet.

## Permissions

24 Application Tracking actions in `app/helpers/corporatePermissions.js` (same list as the frontend `ActionKey`). Routes declare `can: "<action>"`; `helpers/requireAction.js` answers 403 and caches a user's access for 30 s. `GET .../users/v2/me/access` returns `knownActions`, which turns frontend enforcement on.

`shareRoleLink` and `editInviteEmail` only hide buttons. `assignTraining` guards the training catalogue, Assign Training and Retry (see below).

**Order matters:** run `scripts/sql/backfill-application-tracking-permissions.sql` before the corporate-node deploy, or saved users lose Roles access. A missing key means off.

## Company Feature Access

`corporate.corporates."accessLevel"` (admin Feature Access, ATS and ASSMT. columns: 0 neither, 1 ATS, 2 Assessment, 3 both) limits v2 for everyone in the company, Admins and PluginLive check-ins included. `CorporateUserAccessService.getMyAccess` removes the off module's actions from `permissions` (`limitToCompanyModules`) and returns `modules: { ats, assessment }`, so `can:` route guards refuse them too. User Management actions are never removed.

- Sidebar: Roles needs `modules.ats`; Dashboard and Assessments need `viewAssessmentDetails`.
- Landing: `/roles` without ATS goes to the dashboard gate. That sends an ATS-only company to Roles, a company with neither to Manage Users (or "no access" without User Management).
- A change takes up to about 90 s: 60 s `FeatureAccessService` cache plus the 30 s `requireAction` cache. The browser reads it on page load.
- The roles list API has no check of its own; only the page is gated.

## Env (corporate-node)

`ROLES_V2_ENGINE_ENABLED`, `ROLES_V2_REMINDERS_ENABLED`, `ROLES_V2_INTERNAL_TOKEN` (equals student-node `CORPORATE_ATS_TOKEN`), `OCI_*` (same private bucket as student-node), `NORMALIZATION_API_URL` (use the docker bridge IP, not localhost), `NORMALIZATION_API_KEY`, `LITELLM_PROXY_URL`, `LITELLM_VIRTUAL_KEY`, `CORPORATE_V2_APPLY_BASE_URL`, `MSGPACKR_NATIVE_ACCELERATION_DISABLED=true`. student-node `CORPORATE_ATS_URL` must point at corporate-node.

UAT values: engine on, reminders off, bucket `pl-uat-assessment`, `CORPORATE_ATS_URL=http://172.17.0.1:8080`. UAT mail goes through real SES, so floating a role really emails campus contacts.

## Gateway tasks

`pl/corp-workflow-design`, `pl/corp-stage-prefill`, `pl/corp-assessment-paper`, `pl/corp-interview-guidance`, `pl/corp-apply-autofill`, `pl/corp-resume-contact`, `pl/corporate-jd-generation`. Service key alias `corporate-node`.

## Database

DB-Scripts folder `Corporate ATS v2 Roles Integration` (11 scripts, DEV + UAT applied). PROD pending.

## UAT vs Development differences

- `corporate-node` UAT carries the Roles commits by cherry-pick; the branches stay diverged. `index.js` needs `efc21261` (`BACKGROUND_JOBS`): the Roles worker block reads `runsBackgroundJobs`.
- `corporate-react-v2` UAT is a merge of Development (design system, ui 0.2.6, wizard 0.1.2-bugfix.27), so the old `-uat` wizard line ended there. UAT keeps the revert of `ffba377`: the Assessments list has no scoped search or status tabs.
- The UAT-only rule hiding ATS from assessment-only corporates (`hasAtsAccess`) went with the Back to ATS bridge, and Roles has no access-level gate: assessment-only corporates see Roles in the sidebar.
- Design catalogue labels (`empty_states`, `negative_actions`) drop the `.dev.` host on UAT, because the UAT deploy refuses a bundle containing `dev.pluginlive.com`.
- Held `[attempt-integrity]` commits in admin-node and institute-node were not moved by this release.

## Known limits

12th and Certifications eligibility labels return 422. Applicant matching ignores qualifications and age (lives in normalization). The apply form skips captcha while `ROLES_V2_CAPTCHA_SECRET` is unset.

## Testing the form by script

The file part name must be the normalized label (`upload cv pdf`). Any other name is ignored silently, the application still returns 200, and the CV answer is stored as null.

- Complete AI Interview stages open built (since 2026-11-13): the stage prefill does what the five-step form's Generate does — role parameters from admin-node `suggest-parameters` (max 7), Communication & Language first at 20 with the rest sharing 100, one flow row per parameter (Introduction voice, then subjective, 2 questions each), `maxQuestions` and `interviewDuration` from the flow (`prefillCompleteAiInterview` in `stageConfigService.js`). A flow or parameters already set are kept. Complete AI Interview is offered only to companies subscribed to `AI_Interview_v2`; Multiple Assessments sends since 2026-11-13 (see below).


## Multiple Assessments rounds (since 2026-11-13)

A `multiple` stage holds its parts in `config.assessments[]` (`{ stageType, settings }`). **Since 2026-11-13 (DEV + UAT) the round floats ONE admin-node Mix & Match group**: the first dispatch calls `POST /assessment/assignMixMatchAssessment` (inside the create lock), which creates `assessment.mix_match_groups` + one `assessment_corporate_map` per part tagged `mix_match_group_id`; the stage records the group and per-part map ids in `config.mixMatch`. Later joiners are added to the group (`addStudentsToAssessment` with the group id), so each candidate gets **one invite / one link** for all parts. Resend, move-back retake, reopen and the reminder sweep go through the group too (one mail per candidate; `rounds.stageInviteIdsOf` = group id, else each map); deadline extension and access close/reopen stay per part map. An edited setup gives later joiners a new group. Rounds dispatched per part before this keep working per part (UAT role `6f076f3c`, stage `8e4c20be`). Gap: a Role_Based part is floated without its locked paper (admin-node's group path only takes queued parts), so admin-node generates the paper from the same role/skills — the recruiter's preview is not what candidates sit (`ponytail:` in `dispatch.js`; fix = admin-node background Role_Based path accepting `generatedQuestions`). Before 2026-11-13 each part was its own assessment with its own invite.

Each dispatch row has `assessment_type = 'Multiple'`, `external_ref.parts = [{ mapId, assessmentType, name }]` (`assessmentCorporateMapId` = the first part) and `external_ref.mixMatchGroupId`. `scores.loadRoundResults` reads every part (`DISPATCH_MAPS`) and `combineParts` gives the round: COMPLETED, scored with the average of its scored parts, only when every part is completed and released (a Behaviour part counts as released with its level and is left out of the average — since 2026-11-18); otherwise INPROGRESS once any part is started or done, DROPOUT if one was dropped, else PENDING. The applicants API passes each part's standing as `results[].parts`; the Applicants table's Performance expand splits a Mix & Match round into one column per part (score or status), the collapsed cell keeps the round average (`_performance.ts`). Auto-Pilot decides on the combined result. Move back (resend), moving on (close), reopen, role close/reopen and reminders act on every part (`stageMapIdsOf`); the candidate drawer's timeline Download report (since 2026-11-18) fetches every finished part (`?part=n`, from applicant detail `rounds[].parts`) and saves one `<stage>-reports.zip` — a single assessment still saves as its PDF (corporate-node DEV e8b249ee / UAT 553a533b; corporate-react-v2 DEV 38c936b / UAT c317e56; helpers `roles/[id]/_reportFiles.ts`, shared with the bulk download). Bulk **Report Download** on the Candidates table (since 2026-11-18) downloads one file per finished part: `GET …/applicants/:applicantId/rounds/:stageId/report?part=<n>` (1-based `results[].parts[].partNo`, the dispatch's `external_ref.parts` order) serves that one part; without `part` it behaves as before. Files are named `<candidate>-<stage>-<part type>-report.pdf` (Custom = .xlsx). Several files are fetched one after another and saved as ONE `<role>-reports.zip` (built in the browser with `lib/xlsx.ts` `zipStore`, uncompressed; a lone report saves as itself) — so one click is one download (since 2026-11-18: corporate-react-v2 DEV b761c82 / UAT 137c3ff). Setup Now needs each part complete (`stageConfigIssues`) and every part's type subscribed. The type shows in the builder when the company has 2+ subscribed assessment types.


## One assessment per round, resends on the current setup (since 2026-11-13)

- **Create race:** inside the create lock, dispatch re-reads the stage's recorded assessment (`roundsRepository.getStageMapId`) before `findMapId` (which skips maps a stage owns) or creating one; a request that didn't get the lock waits on the stage record. Before this, two concurrent dispatches could create two assessments for one round (UAT role `b51b06a0`: 106 + 105 candidates on two Aptitude maps). Those rows are not repaired: everything below reads the candidate's own assessment.
- **The candidate's own assessment:** applicant detail `rounds[].assessmentIds` and the round report download use the dispatch row's `external_ref` (parts, else `assessmentCorporateMapId`), the stage's only as fallback.
- **Setup fingerprint:** when a stage's assessment is created, the stage records `config.assessmentFingerprint` (hash of `settingsFromConfig`); dispatch rows carry it too. After an edit, later joiners get a new assessment built from the current setup, named `… · <fingerprint 8>`.
- **Resend** (`POST …/roles/v2/:roleId/applicants/resend { applicantIds }`, `remindCandidates`; BFF `/api/roles/:id/applicants/resend`): a candidate whose row was built from the current setup is resent their own assessment (attempt reset); one whose setup changed or was never recorded gets the new assessment (created once per round), their row moves to it and the old link is closed. A Multiple Assessments round resends through its Mix & Match group (one mail); older per-part rounds resend each part. A role without a workflow answers 409 and the BFF resends directly as before. A candidate whose current-round invite **failed** (`status = 'failed'`, e.g. the question set wasn't ready) is dispatched afresh through `dispatchToStage` (added to the assessment, row set to `sent`, invite mailed) instead of being reported as "skipped"; if it fails again the reason is shown in the message (since 2026-11-19: corporate-node DEV 0f6db60e / UAT 835e94f0; PROD release-v1.43 still skips them).
- **Candidate UI:** admin-node `getInviteTokenPayload.isRoleEvaluation` also matches an assessment a dispatch row was sent (own map or Multiple part), so those invites open the v2 candidate journey.
- **Review assessment drawer:** Multiple Assessments has an editor (parts list, Add assessment pre-built via stage-prefill, each part edited with its own type's form; role-based papers generated on Apply). Module Select menus (`ul.pl-assessment-overlay.sf-panel`) open above drawers.

## Candidates list Institute filter (since 2026-11-13)

Each applicant carries `instituteLocation` ("City, State") from `institute.institutes_campuses.city/state` of their campus. A candidate who typed their college (no campus id) gets it from the campus master by name (`RoleApplicantsV2.fillLocationsByName`, indexed name lookup) only when every campus with that name has one location; an ambiguous name (e.g. "Thiagarajar School of Management" in Chennai and Madurai) stays blank rather than guessed. The Institute filter shows the location under each name and its search matches any part of the name or the city/state ("garajar", "madurai", "sikkim"), plus short forms. Wrong cities in the campus master (e.g. IIM Bangalore → "Chennai, karnataka" on DEV) show as stored — a data fix, not code. DEV + UAT.

## Evaluation step keeps a draft's edits (since 2026-11-13)

In Create role, the evaluation builder autosaves a **draft** process 1.5 s after an edit (`useWorkflow.autosave`: PUT `/workflow` with `autosave: true`; new stages take the ids the server returns, so later saves update them). Going back to the JD and returning reopens the recruiter's process; the AI tailored design only auto-applies over the untouched seeded placeholder. corporate-node records no `workflow.saved` activity event for an autosaved draft. Edits made while the first AI design is still building are not saved until it settles. Also: the Applicants tab requests `/final-round` only for a live workflow (no more 400s), and `public/data/skills.json` is shipped again (was a 404). DEV + UAT.


## Feature Access subscribed types vs live rows (2026-11-13)

What a company can use is the live `assessment.subscribed_corporates` rows (Roles stage types, admin Create Assessment). The admin Feature Access screen used to pre-tick from the copied `corporates."subscriptionType"` list, which drifts (UAT Client Demo Corporate `94ced481`: list = AI_Interview only, rows = Aptitude, AI_Interview, Behavior, Custom_Assessment), so admins thought types were unsubscribed while Roles offered them. admin-react (DEV f4110541, UAT 8ea516a3) now also ticks every type that has a live row (once per entity) and clears ticks when another entity is picked; untick + save deletes the row as before.

## Campus invite emails and Add new institute (2026-11-13)

- Publish / Manage institutes invite / remind mails (`helpers/roleInviteEmail.js`) go out as the signed-in recruiter: From name `<First Last> (<Company>)`, Reply-To the recruiter's email (`inviteSender`, user from `getAuditContext().actorId` → user-management `GET /user/:id`). The From **address** stays the verified sender (`mandate@pluginlive.com`) so DMARC passes. Chain: corporate-node → user-management `/notification/bulkEmail` (`fromName`, `replyTo`, schema max 120 / email) → Mail-Server `send-email` `fromName` (`_sender_name`: CR/LF stripped, 120 chars, default `MAIL_SENDER_NAME`). Lookup failure falls back to the default sender. UAT's mailer builds from `~/mail-server` (lowercase checkout, not pulled by `auto_deploy.sh mail-server` — `git pull` it first); DEV runs `mail.service` from `~/Mail-Server`.
- Add new institute (`POST …/institutes/new`): city and contact phone are optional (a given phone must match `PHONE_RE`); institute-node accepts empty strings.

## Role assessments stay off the Assessments surfaces (2026-11-16)

`NOT_ROLE_EVALUATION` (`helpers/corporateAssessmentSql.js`; Assessments list, candidate view, dashboard, calendar) now excludes every id in `ROLE_EVALUATION_IDS`: `workflow_stages.assessment_corporate_map_id`, `config.mixMatch.groupId` + `parts[].mapId`, older per-part `config.assessments[].settings.assessmentCorporateMapId`, and each dispatch row's `external_ref` (`assessmentCorporateMapId`, `mixMatchGroupId`, `parts[].mapId`). Before, a Multiple Assessments (Mix & Match) round and a round's re-built assessment showed on the corporate Assessments page (UAT: "AR caller (experience) — Operations Technical Round"). One uncorrelated array per query, nulls dropped; ~20 ms over 1,471 UAT maps. corporate-node DEV be660d78, UAT 2ba03fee.

## Select lists above stacked drawers (2026-11-16)

Select option lists (`.sf-panel`, and the assessment module's `ul.pl-assessment-overlay.sf-panel`) use `--z-popover` (90). Manage evaluation process → Review assessment opens a drawer at z 71 (above the modal scrim at `--z-tooltip` 70), so lists at 70 opened behind it and e.g. the AI Interview primary/second language could not be changed. corporate-react-v2 DEV 78d5f6d, UAT 306244b (`src/styles/ds/app.css`). The assessment module's own dialogs (`div.pl-assessment-overlay.modal-scrim`) use `--z-dialog` (80) (DEV d4a89fc, UAT 7cfff48). Complete AI Interview → Set Instructions (`CustomiseContentModal`) also needed a module change: it portalled into the first `.wz-root` in the page, which on a role is the Setup evaluation modal behind the drawer, so no z-index could lift it. Since assessment-creation 0.1.2-bugfix.34 (design-system 6b92464, local branch `fix/customise-modal-portal-0.1.2-bugfix.34`) it portals to `<body>` in a `display: contents` wrapper (`.pl-assessment-creation.wz-root.pl-portal`) that keeps the style scopes. corporate-react-v2 DEV 5b3d9ca, UAT a9e57f0 (2026-11-18). A dialog portalled into `.wz-root` lands in whichever modal comes first in the DOM; portal new ones to `<body>`.

## Candidate profile facts are frozen at apply; Gender falls back to the form (since 2026-11-17)

The candidates list, filters, facets, drawer and export (`corporate-node` `app/models/RoleApplicantsV2.js`, `baseCte`) read the
candidate's profile from the **applied-role snapshot** (`student.role_application_*`, see
`ATS/Student/AppliedRoles/applied-role-snapshots.md`) when `APPLIED_SNAPSHOT_READS=true` (DEV + UAT), joined on
`(student_id, role_id)` from `corporate.job_role_student_map` (`is_applied = 1`). There is **no per-row fallback to the live
profile**: an applicant without a snapshot would show blank profile fields and drop out of every profile filter
(coverage on 2026-11-17: DEV 97/97, UAT 766/766 PluginLive-form applicants).

- Profile-based filters (frozen): gender, institute, degree, department, passing year, marks per level, skills (must hold all),
  age, experience. Degree/department match on text, case-insensitive.
- Application-based filters (live): search, stage, fit, score, applied date, form answers.
- **Gender** = the frozen profile gender, else the apply form's `gender` answer (`FORM_ANSWER_SQL("gender")` over
  `job_role_response`). The drawer already showed the form answer, so a candidate whose profile had no gender showed "Male" in
  the drawer but never matched the Male filter. Fixed: corporate-node DEV `6ccf54fe`, UAT `ccf44bbb`.

## Location filter and "Applied time" (since 2026-11-19, DEV + UAT)

Candidates filter → **Add More Filters → Location** (first category; removable like any custom filter). One search box and an
accordion per kind: **Current location**, **Permanent location**, **Preferred location**. AND across kinds, OR within one
("Current = Pune AND Permanent = Nagpur"); chips read "Current location: Pune". A kind with no data for the role's applicants
is left out and named in one muted note ("Preferred location isn't recorded for these candidates yet."). Filtering is
client-side; picks live in the filter state under `custom["pl:location"]` as `deptKey(kind, city)` and are never sent to the
API. The role's location form questions (Current city, Current Address - City, Preferred location…) are no longer offered
as their own custom filters. The **Applied on** filter is renamed **Applied time** (same date range).

The Location pane (and Degree & Department) scrolls inside the filter panel: `.fp-custom:has(> .dept-tree)` is a flex
column in `styles/ds/app.css`, so the `.dept-tree` gets a bounded height. Before 2026-11-20 a long list was clipped at the
panel's bottom with no scrollbar (corporate-react-v2 DEV `688bf01`, UAT `d0f724c`).

**Role header location tag** (`RoleMetaTags.tsx`): first location + "+N more" (all in a popover). With no location a
Complete role shows a muted "Location not set"; a Quick Evaluation role (`mode: "quick"` from the role detail GET) shows no
location tag, since that path never asks for one (DEV `688bf01`, UAT `d0f724c`, 2026-11-20).

- **Data** — `GET .../roles/v2/:id/applicants` sends, on each applicant's `profile` (`RoleApplicantsV2.baseCte`, from the
  frozen personal profile `spp`):
  - `currentLocation` = `spp.corr_city`
  - `permanentLocation` = `spp.perm_city`
  - `preferredLocations[]` = city names from `spp.preferred_job_location` (jsonb array). Entries with `selected: false`
    are dropped (the picker saves unchosen rows); a state-only entry (`{state_name: "Tamil Nadu"}`) is sent as the state.
- The frontend (`candidateLocations()` in `RoleCandidateFilters.tsx`) prefers those fields and only falls back to the role's
  location form answers (matched by label) when the profile has none; values are sentence-cased so "pune" = "Pune".
- Coverage depends on the profile: on UAT role "Normalisation logic with cv parser" 38/38 applicants carry the fields, 28 with
  a current city, none with a preferred one.
- Code: corporate-node DEV `d648ec4a`, UAT `9d0811fa`; corporate-react-v2 DEV `6793919` `bd33dd5` `d4e0dd6` `b90d82d`,
  UAT `8aa4c73` `1fd2b37` `064ae16` `045b9d1`. `d4e0dd6` also restyles the shared `DegreeTree` (every Degree & Department
  picker) to the DS Accordion: chevron on the right, 1px rule between items, animated open. PROD: not deployed.

## Behaviour results on the candidates table (since 2026-11-17)

A Behaviour assessment has no score: its result is a level. Round results (`services/evaluation/scores.js` `loadRoundResults`) carry `level` on a single Behaviour round and on each Mix & Match part, as the median of the attempt's `assessment.behavior_proficiency_scores` levels (`helpers/behaviorLevel`, the assessment roster's rule; an even count takes the lower middle). The applicants list passes it through (`results[].level`, `results[].parts[].level`), and the Performance column shows the level ("Practitioner") instead of "Preparing Report"; "Preparing Report" now means completed with neither a score nor a level. Behaviour still counts as unscored in the Performance average. corporate-node DEV 0d3284cd / UAT 09095a35; corporate-react-v2 DEV 8d2a04b / UAT cfca8fb. Fixed 2026-11-18: a Mix & Match round with a Behaviour part used to stay unscored ("Sat it — awaiting scoring", counted 1/3 instead of 2/3); its score is now the average of the scored parts (UAT "AR caller (experience)" Sanjay R: Ops Technical Round 61%). corporate-node DEV ccb2e7ae / UAT b8dfc1f3; corporate-react-v2 DEV e32d663 / UAT 1310925.


## 2026-11-19 fixes: stage deadlines and Communication score timing

- **Assessment stages with a deadline could not be sent** (since 7683ec21, 11-16): `evaluation/dispatch.js` checks the stage deadline with `istDayOf` from `./rounds`, which `rounds.js` never exported, so every such dispatch failed with "istDayOf is not a function" and the candidate showed "Invite could not be sent". Fixed by exporting it; `test/evaluationImports.spec.js` now fails if dispatch.js imports a name rounds.js does not export. Failed dispatches are retried by the engine's next 5-minute pass, no manual step.
- **Later joiners saved as failed while the round's assessment was still being built** (PROD, 2026-11-19): a candidate joining an assessment another request is creating waits for its question set (`adminNode.waitForSet`). That wait was 30 s; creation took ~64 s, so two candidates got "has no questions yet" and a `failed` row, and Resend skipped them (it only accepted `sent`). Since 2026-11-19 (DEV 0f6db60e / UAT 835e94f0) the wait is up to 3 min (60 × 3 s) and Resend retries `failed` rows. Test: `test/resendFailedDispatch.spec.js`. PROD not yet deployed.
- **Communication score showed in the assessment list before the drawer report was ready**: `helpers/assessmentScoreSql.js` summed `communication_scores` section rows as they landed, while the drawer (`RESULT_RELEASED_SQL`) waits for `scores_calculated`. The section aggregate is now gated on `aas.scores_calculated = true` (as `AI_V2_SETTLED` does for AI Interview v2), so an in-progress attempt reads "Preparing Report" in both. PROD check: all 13,165 scored Communication attempts already had the flag.
- corporate-node DEV 2fc416fd/1879690f, UAT f58e0a70/c7338ffc, **PROD `release-v1.43-hotfix-1`** (image `pl-corporate-api:2026-11-19-07-03-59-release-v1.43-hotfix-1`; rollback `…2026-11-18-14-44-28-release-v1.43`). Known pre-existing failure: `test/aiInterviewV2Wiring.spec.js` expects `RESULT_RELEASED_SQL` without the `scores_held_at` line.

## Bulk candidate upload on PROD (2026-11-19)

PROD form-data-normalization ran `release-v1.38-hotfix-1` (4 Sep), which has no `/api/corporate-bulk/*` endpoints, and PROD corp-node had no `NORMALIZATION_API_*`, so "Add candidates → upload" returned "not configured". Fixed:
- form-data-normalization **`release-v1.38-hotfix-2`** = hotfix-1 + only the 4 corporate-bulk commits (d652813, f39068d, c99d9b8, f2a86bb as 57d8e66/071ec96/c4fca66/45ff30d). Image `form-data-normalization:2026-11-19-07-11-54-release-v1.38-hotfix-2` on all three deployments (api, worker, cron — always move them together). Built with `~/fdn_deploy_v138hf2.sh build|deploy <image>` on the PROD builder. Rollback image `…2026-09-04-05-31-54-release-v1.38-hotfix-1`. The DB script (`Corporate Bulk Candidate Upload/20260831T083545Z…`) was already applied on PROD 2026-09-01.
- Tests: the image has no pytest (the hotfix-1 script's test step never ran anything). Run per file in a throwaway container with pytest installed: 101 pass incl. 18 corporate-bulk; `test_arrears_slug_families`, `test_current_course_from_erp_sheet`, `test_export_email_delivery`, `test_languages_from_sheet` hang without network on the builder on the OLD image too.
- corp-node `corp-api-config`: `NORMALIZATION_API_URL=http://form-data-normalization`, `NORMALIZATION_API_KEY` = normalization's own `API_SECRET_KEY`. Verified from the corp-node pod: no key → 401, key → 422 (field validation), i.e. reachable and authorised. A real upload was not run on PROD.
