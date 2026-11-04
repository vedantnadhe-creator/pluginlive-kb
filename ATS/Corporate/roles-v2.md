# Corporate Roles v2 (ATS) on corporate-node

Live on DEV since 2026-10-29 and on **UAT since 2026-11-04**. PROD pending.

The Roles screens in `corporate-react-v2` (`/v2/roles`, `/v2/roles/new`, `/v2/apply/<id>`, short links `/v2/a/<code>`) are served by **corporate-node**. `corporate-node-v2` is no longer used for Roles; on UAT its service still runs but nothing routes Roles traffic or the score webhook to it.

## Flow

1. Recruiter creates a role (paste or attach a JD), picks the application form, and floats it. Each invited campus gets one invite mail (POCs + wizard contacts + campus email, with the recruiter's CC).
2. Candidate applies on the PluginLive form. The CV goes to the private bucket under `role-applications/`; the answers go to `job_role_response` and the role's Google Sheet in the FormData folder.
3. form-data-normalization picks the sheet up, normalizes it and calls student-node `create-full`, which creates the applicant (`job_role_student_map`) and copies the CV to the public docs bucket as `cv_url`.
4. corporate-node AI match scores the applicant. The evaluation engine (BullMQ, 5-minute scan plus events) screens and advances. A candidate with no CV is held for the recruiter.
5. student-node posts each score to `/v2/hooks/assessment-scored`, which queues the advance pass. A recruiter fit override holds a candidate only in the round it was made in.

## Permissions

24 Application Tracking actions in `app/helpers/corporatePermissions.js` (same list as the frontend `ActionKey`). Routes declare `can: "<action>"`; `helpers/requireAction.js` answers 403 and caches a user's access for 30 s. `GET .../users/v2/me/access` returns `knownActions`, which turns frontend enforcement on.

`shareRoleLink` and `editInviteEmail` only hide buttons; `assignTraining` has no endpoint yet.

**Order matters:** run `scripts/sql/backfill-application-tracking-permissions.sql` before the corporate-node deploy, or saved users lose Roles access. A missing key means off.

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

Multiple Assessments and Complete AI Interview stages are not dispatched. 12th and Certifications eligibility labels return 422. Applicant matching ignores qualifications and age (lives in normalization). The apply form skips captcha while `ROLES_V2_CAPTCHA_SECRET` is unset.

## Testing the form by script

The file part name must be the normalized label (`upload cv pdf`). Any other name is ignored silently, the application still returns 200, and the CV answer is stored as null.
