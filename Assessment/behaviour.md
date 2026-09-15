# Behaviour Assessment

Behaviour measures a candidate against a set of **competencies** and reports a
**proficiency level** per competency, plus a list of **suitable job roles** the
candidate is capable of.

Backend lives entirely in `student-node`:

| Concern | Location |
|---|---|
| Scoring / proficiency storage | `app/models/BehaviorCalculations.js` -> `storeBehaviorScores` |
| Suitable job role matching | `app/models/BehaviorCalculations.js` -> `getSuitableJobRoles` |
| JSON report | `app/models/Assessment.js` -> `getAssessmentReport`, `type === "behavior"` branch |
| PDF report | `app/models/Assessment.js` -> `generateBehaviorReport` + `public/behaviorReport.html` |

## Data model

| Table | Holds |
|---|---|
| `assessment.behavior_competencies` | competency per **assessment domain** (`competency_name`, `assessment_domain_id`) |
| `assessment.behavior_proficiency_scores` | the candidate's level per competency for one attempt |
| `assessment.job_roles` | role catalogue: `role_name`, `role_description`, `skills`, `assessment_domain_id`, `degree` (varchar) |
| `assessment.job_role_requirements` | role -> competency -> required `proficiency_level` |

Proficiency ladder (rank 1..8):
`Novice, Beginner, Developing, Apprentice, Practitioner, Advanced, Expert, Master`.

**Catalogue shape (DEV, 2026-09-01).** 123 `job_roles` rows but only **70 distinct
role names** -- the same role is catalogued once per degree, so any consumer must
dedupe by name. 8 assessment domains exist, but only **two are populated**:
Engineering (6 competencies, 40 role rows) and Management (9 competencies, 83 role
rows). `job_roles.degree` is a display string combining degree and specialisation,
e.g. `B.E. - Computer Science and Engineering`, `MBA - Finance`.

**Requirement levels are extreme:** of 251 requirement rows, **136 are Expert and
112 are Master** -- only 3 are Practitioner. Any pass/fail matching rule will
therefore report almost every candidate as capable of nothing. This is the single
most important fact about this feature.

## Suitable job role matching (current behaviour)

`getSuitableJobRoles(assessment_assigned_id)` -- one argument.

1. Load the candidate's proficiency scores and index their level **by competency
   name**, not competency id.
2. Load the **entire role catalogue** with its requirements.
3. For each role, require that the candidate was measured on **every** competency
   the role requires. An unmeasured competency is not evidence, and the role is
   dropped rather than guessed at.
4. Score **attainment proportionally**: `min(studentLevel / requiredLevel, 1)`
   averaged across the role's requirements, as a percentage.
5. Dedupe by role name, keeping the candidate's best score.
6. Emit `match_type: 'full'` for 100% (meets every requirement, sorted by name)
   and `match_type: 'partial'` for the rest, sorted by match percentage desc.

The PDF splits these into a full-potential section and a partial section.

### Why matching is by competency *name*

Competencies are stored **per domain**, and every one of the 251
`job_role_requirements` rows is same-domain. Walking
`candidate competency -> requirements` therefore could only ever reach roles in the
domain the candidate tested in. Because the domain follows the candidate's degree,
this looked exactly like a degree/department filter even after the explicit
degree filter was deleted. Matching on the competency **name** lets evidence carry
across domains.

**Gotcha:** the bridge is exact name equality. Only `Customer Orientation` and
`Project Management` are spelled identically in both populated domains. Near
synonyms do **not** bridge -- `Creative Mindset` vs `Creative Approach`,
`Sales & Business Acumen` vs `Sales Acumen`. In practice this lets an Engineering
candidate reach 14 Management roles and a Management candidate reach 9 Engineering
roles. Widening the cross-domain reach is a **data** change (align competency
names, or add cross-domain requirement rows), not a code change.

## What was removed (2026-09-01)

- The `assessmentDomainId` restriction on the role query.
- The `studentDegreeId` / `studentStreamId` parameters, unused since commit
  `a0f2a7e3` (2026-05-14) but still threaded through both callers.
- The dead specialisation-to-stream narrowing block in `generateBehaviorReport`
  (~90 lines, including a per-report raw SQL join against
  `institute.specialisation_master_stream_map`) whose computed degree/stream were
  already ignored by the matcher.
- The no-match fallback that returned 5 arbitrary roles from the candidate's
  domain via `take: 5`. This fallback was what most candidates actually saw, and
  it is why the report looked like a short degree-scoped list.

### Bug fixed at the same time

The old query selected `job_roles.degree_id` and `job_roles.stream_id`. Those
columns are declared in `prisma/schema-assessment.prisma` but **do not exist in the
DEV database**, so the query threw Prisma `P2022`; the caller caught it and the
behaviour report silently rendered **zero** suitable roles on DEV. The current
code does not reference either column.

## Verified behaviour

| Env | Attempt | Result |
|---|---|---|
| DEV | Management, 9 competencies | 44 roles (0 full, 44 partial), incl. 9 Engineering roles cross-domain |
| UAT | Management, 9 competencies | 44 roles, 21 full / 23 partial |
| UAT | Management, 9 competencies | 20 roles, 0 full / 20 partial |

Strong candidates do populate the full-potential section; weaker ones fall
entirely into partial, ranked.

## Candidate paper (assessment-react-v2)

The API (`getBehaviorAssessmentQuestions`) returns questions **grouped by the
behaviour they probe** (`behaviors[].behavior_name`). v2 must not render that
grouping: it told the candidate what each question measured via the
breadcrumb, the left rail and the mobile track.

- `src/lib/examShapes.ts` `behaviourPaper()` flattens every group into one
  anonymous "Behaviour" section and shuffles it with a **seeded** PRNG
  (mulberry32) keyed on the attempt id, so a reload does not re-deal the
  paper and questions from one behaviour do not sit together.
  `liveExam.ts` applies it only for `type === "Behaviour"`.
- **Every question is mandatory.** `requiresEveryAnswer(type)` in
  `_mock/exam.ts` (Communication + Behaviour) drives the reducer `NEXT` guard
  and the disabled Next in `QuestionPanel`. Behaviour has free navigation, so
  the rail can step past that gate; `finishCurrentModule` in `take/page.tsx`
  therefore refuses to close the module while `firstUnanswered()` finds a
  gap, jumps to it and toasts.
- **Deliberately client-side only.** The submit endpoint also carries the
  clock's and the violation cap's forced submissions, which must land
  incomplete, and it has no field to tell those from a voluntary finish.
  Scoring already excludes a missing answer rather than corrupting the
  attempt. Timer expiry and `expireCurrentAssessment` bypass the gate.
- Legacy `Assessment-React` already shuffled, hid names and gated answers.

## Admin wizard question count

The shared `@pluginlive-technologies/assessment-creation` package (design-system
repo, vendored into admin-react-v2 as a tarball) used to say **15 questions**
for Behaviour -- a hardcoded guess. The real bank is one active set per
domain: **Engineering 115, Management 129** (DEV and UAT, 2026-09-15).

- admin-node `GET /assessment/getBehaviorQuestionCounts` -> per domain
  `{ min, max }` across active Behavior sets. A range, because the set is
  drawn `ORDER BY RANDOM()` at create time; today `min === max`.
- admin-react-v2 BFF `/api/entities/assessment-types` rides the call the
  wizard already makes on mount and adds `behaviourQuestionCounts`
  (best-effort, like the quota lookup).
- Package **0.1.6**: `useEntityAssessmentTypes` exposes the counts;
  `assessmentMetrics("behaviour", cfg, counts)` reads `cfg.stream`. Shows 0
  until loaded rather than an invented number. Threaded to the card digest,
  the totals header and the review row.
- To change the package: edit design-system, bump the version, `npm pack`,
  copy the tarball into `admin-react-v2/vendor/`, update `vendor/manifest.json`
  sha and `package.json`, `npm install`. Never edit a tarball.

## Sample report

`samples/behaviour-report-all-roles-John-S-2026-09-15.pdf` in the
`pl-uat-public-docs` bucket: UAT attempt `3726bdad`, 21 full-match roles
including 3 Engineering roles reached cross-domain.

## Status

Suitable-role matching: live on **DEV + UAT** as of 2026-09-01.
Candidate paper (hidden behaviours, shuffle, mandatory answers) and admin
question count: live on **DEV + UAT** as of 2026-09-15. **PROD pending** for
all of it.

## Related

- `admin.md`, `institute.md` -- where behaviour reports are surfaced
- `nps-scale-and-curve.md` -- NPS covers Communication + Aptitude only; behaviour
  has **no score**, only levels
