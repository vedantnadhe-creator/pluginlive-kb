# Corporate Roles v2 (ATS) on corporate-node

Live on DEV since 2026-10-29 and on **UAT since 2026-11-04**. PROD pending.

The Roles screens in `corporate-react-v2` (`/v2/roles`, `/v2/roles/new`, `/v2/apply/<id>`, short links `/v2/a/<code>`) are served by **corporate-node**. `corporate-node-v2` is no longer used for Roles; on UAT its service still runs but nothing routes Roles traffic or the score webhook to it.

## Flow

1. Recruiter creates a role (paste or attach a JD), picks the application form, and floats it. Each invited campus gets one invite mail (POCs + wizard contacts + campus email, with the recruiter's CC).
2. Candidate applies on the PluginLive form. The CV goes to the private bucket under `role-applications/`; the answers go to `job_role_response` and the role's Google Sheet in the FormData folder.
3. form-data-normalization picks the sheet up, normalizes it and calls student-node `create-full`, which creates the applicant (`job_role_student_map`) and copies the CV to the public docs bucket as `cv_url`.
4. corporate-node AI match scores the applicant. The evaluation engine (BullMQ, 5-minute scan plus events) screens and advances. A candidate with no CV is held for the recruiter.
5. student-node posts each score to `/v2/hooks/assessment-scored`, which queues the advance pass. A recruiter fit override holds a candidate only in the round it was made in.

## Evaluation setup gate

A process can't be saved until every **enabled** stage is configured. The green tick on a stage row and the save button read the same check (`isStageConfigured` in `roles/[id]/_constants.ts`): the stage has a type, and an assessment type passes `configIssues`. This covers **Setup Now / Save changes** in the Setup evaluation dialog and **Continue** on Quick Evaluation's "Set up evaluation" step. While a Role Based or AI Interview stage is still being prepared, or its prefill failed, the button stays off and a note names the stages ("Still to set up: ..."). Disabled stages don't count: they are never prefilled, and corporate-node's `unconfiguredStages` skips them too. A live process with an unfinished enabled stage can't save edits until that stage is fixed. Quick Evaluation's Start evaluation retry only runs on a live process with no unsaved edits.

AI interview stages use the assessment module's own forms: stage type `ai_interview` opens the single scrolling form and floats `AI_Interview`; `complete_ai_interview` opens the five-step form and floats `AI_Interview_v2` (package `assessment-creation` 0.1.2-bugfix.28, adapter `src/lib/stageConfig/interviewPanels.ts`). Both store instructions and the second language. Communication & Language's 20% comes out of the other parameters, so the total stays 100. Dispatch keeps the ids the form sent, because the scorer finds the locked parameter by id `communication`; only a parameter with no id gets a name slug. Setup Now also refuses a Complete AI Interview flow admin-node would reject at float time: a reading, listening or custom row with no instructions, more than 50 questions on a row, more than 50 voice questions, or a parameter weight of 0. Hand-written choice questions are still only checked by admin-node at float time. Only companies subscribed to `AI_Interview_v2` see the stage type.

## Degree & department master

The picker offers the degree/stream master, the same list v1 role creation uses: corporate-node `GET /corporates/:corporateId/degrees/v2` calls institute-node's `institutes/search/degreeStreams?pageLimit=700&status=1` and returns `{ degree, level, departments }` (BFF `/api/roles/degrees`, hook `useDegreeCatalogue`). That list also carries inactive rows whatever `status=1` asks for, so corporate-node keeps active degrees with active streams only and merges duplicate names; degrees with no stream aren't offered. PHD counts as PG, PG diplomas as Diploma, and ITI (stored as a DIPLOMA) as ITI.

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

A role can only use assessment stages when the company has Assessment access (Feature Access, ASSMT. column) and a current subscription to that type (`assessment.subscribed_corporates`, not past `end_date`). Turning access off leaves the subscription rows in place, so `blockedStageTypes` checks access first and blocks every assessment stage type without it. DEV + UAT, 2026-11-04. Rule: `services/evaluation/subscribedStages.js`. AI proposals, the default process and copied processes leave the others out, `GET assessment-options/v2` returns `unsubscribedStageTypes` for the Stage type dropdown, and Setup Now answers 422 naming the stage. A live role keeps a stage it already runs. Multiple Assessments shows only with two or more subscribed assessment types, and Complete AI Interview only with an `AI_Interview_v2` subscription; a type that cannot be dispatched yet is left out of the Stage type dropdown altogether (`NOT_SENDABLE_STAGE_TYPES`), though a stage already set to it still shows, with its notice. UAT hides both; on DEV Complete AI Interview is being enabled. Running out of tokens is not part of this rule; it is checked at float.

## Resume Screening never moves anyone

Screening scores every applicant but moves and closes nobody (DEV + UAT, 2026-11-05). `stageAutoPilot` is always false for a screening stage, because its card has no switch: strong fits are held as recommended, medium and weak fits are held, and the recruiter decides. Any scored applicant still at screening can be selected in the stage drawer's advance. Later assessment stages keep their own Auto-Pilot switch. Candidates moved or closed before this change were not reversed.

## Moving a candidate back

Move to a Stage warns on a move to an earlier stage, and says when an assessment goes out again. A move back to an assessment round the candidate already has a row on resends it (`resendMapIdFor`, `resendStageAssessment`): the assessment window is extended if needed, then admin-node `resendInvites` with a selection resets the attempt and re-invites. admin-node archives the old attempt first, but its score leaves the screens. The resend runs before anything moves, so a failure leaves the candidate where they were. Forward moves, same-stage moves, and human or screening rounds send nothing. Moving forward to a round they left reactivates it with no new invite.

The candidates list ignores `moved_back` dispatch rows, so it shows the round the candidate is on now.

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

The Roles bulk bar resends each candidate's current assessment round, through `POST /api/roles/:id/applicants/resend`, with `remindCandidates`. It sends `onlyDroppedOff: true` to admin-node `resendInvites`, so only candidates who dropped off are reset; anyone else keeps their attempt and is counted as skipped. Without that flag a selection resets a candidate in any state, which is what the assessment pages do on purpose (the old attempt goes to `assessment_attempt_archive`). admin-node must carry the flag before the frontend relies on it: an older admin-node ignores it. Selected emails match regardless of case, and a mix-match float where nobody was reset mails nobody.

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

`shareRoleLink` and `editInviteEmail` only hide buttons; `assignTraining` has no endpoint yet.

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

Multiple Assessments stages are not dispatched. 12th and Certifications eligibility labels return 422. Applicant matching ignores qualifications and age (lives in normalization). The apply form skips captcha while `ROLES_V2_CAPTCHA_SECRET` is unset.

## Testing the form by script

The file part name must be the normalized label (`upload cv pdf`). Any other name is ignored silently, the application still returns 200, and the CV answer is stored as null.
