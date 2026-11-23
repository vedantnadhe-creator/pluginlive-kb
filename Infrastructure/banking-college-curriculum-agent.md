# Banking LMS — College curriculum agent

Current code: **UAT `7be6da98d`** and **PROD `9ffb360b5`**, `release/prod-v1.1`, tag **`v1.1.32`** (2026-11-22). PROD: `https://lms.pluginlive.com/academic-curriculum`. SRM Python's 49 approved topic packages and their files are published in both environments; see the production scope below.
Code: `bankingjobreadiness` — `supabase/functions/college-curriculum-agent`, `supabase/functions/_shared/curriculum-agent-checks.ts`,
`src/components/college/CurriculumAgentPanel.tsx`, `src/lib/curriculumAgentApi.ts`. Migrations `20261116150000_college_curriculum_agent.sql`,
`20261116160000_curriculum_agent_offering_link_no_fk.sql` (DB-Scripts folder *Banking LMS College Mode*).

**Quality controls** (source provenance, duplicate check, evidence-checked lessons, HOD maker-checker; see the section below) are
live on **UAT** (`e89cd43bb` + `69cf6c3ae`, 2026-11-18) and **PROD** (`release/prod-v1.1` `b831175c2`, tag `v1.1.27`, 2026-11-18, backup
`/data/backups/prod-20261118T045457Z`). Migration `20261118100000_curriculum_quality_controls.sql` is applied on DEV, UAT and PROD.

## Production release and content scope (2026-11-22)

The user explicitly requested GitHub push and PROD deployment. Release `5bc68b2c0dada9a810392d59229b39e95a84304e`
(tag `v1.1.30`) promoted the academic reader/preparation/source verification dependencies and Fetch More YouTube.
The subsequent authorised promotion, `703fa3de7bd94fdf453697d4d5bbb09bdd0ff0d5` / `v1.1.31`, publishes the SRM
Python learning content and Semester 1 outline repairs and enables same-institute peer certificate editing. Corporate trainer delivery stays separate. The held
student LMS v2/designer changes and lesson-video watch-gate/AI-checker changes remain excluded. The `/v2` app is separate.

All six academic migrations are applied on PROD: `20261121120000`, `20261121130000`, `20261121190000`,
`20261121193000`, `20261121203000`, and `20261122023507`. Canonical application status is recorded in DB-Scripts /
*Banking LMS College Mode*. They were first applied and tested on an isolated production database copy, including both
academic SQL access/approval suites, then replayed successfully to check idempotency. No UAT database was restored over PROD.

PROD's 37 SRM syllabus PDFs had no fingerprint/official URL metadata. Every stored PDF was downloaded and byte-for-byte
compared with the current official Anna University CAC PDF and the prior verified UAT hash before updating provenance.
The migration then restored 74 existing SRM build/batch approvals; one verified TCET legacy mapping was backfilled by the
initial migration. No new curriculum authority, batch applicability or HOD identity was invented.

**SRM Python content is published in PROD.** The user's explicit content-promotion request was completed on 2026-11-22:
49 approved topic packages and lesson PDFs, 147 questions, 49 frozen approved simulation versions, 37 approved videos
across 25 topics, and eight permitted supplementary learning sources. All 57 transferred PDF objects are byte-identical
to UAT; the existing syllabus makes nine source downloads and 58 downloadable PDFs in total. Original maker/checker
identities, approval timestamps, source rights and citations are preserved. Both review actors already existed in PROD;
no users, student progress or personal recommendations were copied. The 74 rejected video candidates remain unpublished
audit rows and cannot be rediscovered as new candidates. The other 24 topics retain their approved no-video reasons;
students can use Fetch More on every topic.

The same guarded transaction restored the 25 empty Semester 1 subject outlines and consolidated MBA MB25C01 from
12 duplicated unit rows to six distinct units. It changed only the selected course content/link fields and outline fields,
after checking the exact live baseline. It did not overwrite other college data, enrolments or syllabus builds. The
transaction was rehearsed on a disposable production database copy before application; no new schema was required.

Production verification: all 49 topic pages render, all 37 approved video embeds appear, all 58 signed PDF downloads
work, quiz grading/progress survive reload, and the simulation player opens. Enrolment denial and hidden quiz/simulation
answers were checked. All 59 existing certificate tests and live owner/peer/other-institute/admin-catalogue/lock checks
passed. Final browser checks had no application JS errors, failed backend calls or mobile horizontal overflow. All five
temporary accounts, two QA institutes, two QA modules and their progress/consent were removed; the rehearsal database
was dropped. No paid content or simulation generation ran during promotion.

The v1.1.31 release was built on the PROD VM with the unchanged PROD environment through `auto_deploy.sh banking release/prod-v1.1`.
Its bundle was `index-DumayiN-.js`; only `module-certificate-settings` code changed from v1.1.30. Backup:
`/data/backups/prod-20261122T052441Z`; pre-import snapshot and SQL logs: `/data/backups/srm-content-20261122T051448Z`.
Operational evidence: `/home/ubuntu/banking-checks/srm-production-promotion-20261122/`. Student LMS redesign, video-watch
completion gate and AI video checker remain excluded under the existing hold.

Earlier v1.1.30 validation: 127 feature/navigation checks passed, plus 54 simulation checks. One additional unchanged baseline assertion
in `simulationAuthAndLogoutRegression.test.ts` still expects old inline ContentManager code in the wrapper file; both files
are unchanged by this release. Two obsolete academic navigation assertions were corrected to test the dedicated reader
and legacy redirect. New frontend files lint clean. Live isolated QA used the approved Python Error messages text: search
returned a retained Python video; owner-only storage, reload without another search, mobile width, region/Tamil controls,
unenrolled/foreign-topic denial, real YouTube player rendering and the simulation entry point passed. No application JS
errors or failed app calls in the final browser checks. The initial shorter synthetic topic produced a legitimate no-match;
this is not a promise of four results for every topic. No paid lesson/simulation generation was invoked.

All four temporary identities, their isolated institute/course/package/scenario, enrolments, consent and personal videos
were removed. The rehearsal database was dropped. No real student's progress or personal recommendations changed.
Evidence: `/home/ubuntu/banking-checks/academic-prod-20261122/` (deployment, SQL rehearsal, provenance hashes and browser logs).
Built on the PROD VM using its unchanged `.env`; bundle `index-DumayiN-.js` contains only the production API origin.
Deployment used `~/auto_deploy.sh banking release/prod-v1.1`; backup `/data/backups/prod-20261122T035809Z`, previous code
`7e561218b` / `v1.1.29`. Existing `main`, `mcp` and `live-session-rsvp` Edge overlays and the OTP relay were preserved.

## PROD journey verification and fixes — v1.1.32 (2026-11-22)

Following the user's request to exercise and fix candidate/faculty journeys in PROD, release `9ffb360b5` adds two
scoped fixes. Certificate settings validate persisted fields even when certification is disabled; invalid module codes
and zero/fractional planned duration return field-specific HTTP 400 responses instead of database HTTP 500s. Invalid
fields remain editable after switching certification off. Faculty video discovery now uses the same subject anchor as
learner Fetch More: every query retains the subject, and actual video metadata must contain subject evidence. An
isolated Python Error messages test had previously accepted tax/boiler videos; the corrected test returned four Python
error-handling videos. The AI video checker remains held; these are metadata checks followed by independent review.

The full simulation conversation exposed a separate PROD gateway configuration defect: `pl/sim-persona-turn` was
missing from the live policy, and both Gemini routes returned depleted-credit errors. Restored the task with an existing
available provider chain and registered `pl/banking-simulation` for generation/debrief calls. Both tasks use the PROD
banking service key and passed normal and forced-fallback probes. The candidate's actual reply and scored debrief then
passed through `sim-attempt`; no provider credentials or billing settings changed. Current policies are documented in
[centralized LLM routing](centralized-llm-routing.md).

Live checks used disposable faculty, HOD, same-institute peer, unrelated trainer, enrolled and unenrolled candidates:
PDF upload/parser; maker self-approval denial; HOD return with reason; returned-draft rebuild; Prepare missing topics;
cited lesson/three-question/simulation creation; four matching videos; independent HOD publication; enrolled candidate
visibility; all 49 real SRM topic pages; 37 approved embeds; quiz/read persistence; mobile layout; Fetch More retention;
full simulation turn and scored feedback; certificate save/preview, audit actor, institute lock and access denials.
All 58 signed PDF downloads passed, including byte checks on all 57 promoted objects. The 25 repaired subject outlines
and MBA's six distinct units still match the promotion. All 127 targeted automated tests passed.

Seven temporary auth identities (six test roles plus a harness helper), two institutes, two modules, the isolated course,
generated packages/scenarios, attempts, progress, enrolments, consent and uploaded QA PDF were removed. Real SRM
learning content and real-user progress were not changed. No schema migration or UAT deployment occurred. Built on
the PROD VM via `auto_deploy.sh banking release/prod-v1.1`; bundle `index-D6lmR_sT.js`; backup
`/data/backups/prod-20261122T115733Z`. Evidence: `/home/ubuntu/banking-checks/prod-journeys-20261122/`.
Student LMS redesign, video-watch completion gate and AI video checker remain excluded.

## UAT backport of journey fixes (2026-11-22)

The user requested the same fixes in UAT and GitHub. Commit `7be6da98d6d5b85537af149fb55a09629bf5c08d` on
GitHub `UAT` cherry-picks PROD `9ffb360b5`: certificate field validation while disabled, editable invalid fields, and
subject-anchored faculty video discovery. Only the six reviewed source/test files were backported; no schema migration
or production deployment was performed. Existing UAT features and environment settings were retained.

UAT simulation configuration now matches the corrected PROD routing: `pl/sim-persona-turn` uses gpt-5.4-mini then
gpt-6-luna; `pl/banking-simulation` uses gpt-6-luna then gpt-5.4-mini. Both use UAT's own gateway/service key and passed
normal and forced-fallback probes. The `simulation` LLM settings row now names the registered task instead of physical
Gemini. Unrelated tasks, provider credentials and billing settings were preserved.

All 127 targeted tests passed. Live UAT checks passed for candidate navigation, Fetch More with saved videos after
reload, a simulation reply and scored debrief, certificate validation/save/preview by an institute peer, correct audit
actor, cross-institute/student denial, catalogue restrictions and institute lock enforcement. Faculty discovery returned
Python-context videos for Error messages and retained the independent publication gate. The HOD saw the discovered
videos and returned the draft with a reason. All six temporary auth identities, two institutes, two modules, the test
course/package/scenario, simulation attempt, recommendations, progress and consent were removed; SRM's published
content was retained.

Built on UAT using its own environment via `auto_deploy.sh banking UAT`; live commit matches GitHub, bundle
`index-DlK7wPHB.js`, changed function hashes match the PROD fix, and no DEV/hosted API origins appear in the bundle.
Snapshot: `~/banking-sb/snapshots/20261122T121252Z`; gateway policy backup:
`~/litellm/policy-backups/tasks-20261122T121151Z.json`; simulation settings baseline:
`~/banking-sb/snapshots/uat-journeys-config-20261122/simulation-before.txt`. Evidence:
`/home/ubuntu/banking-checks/uat-journeys-20261122/`. The existing production hold remains unchanged.

## Fetch more academic YouTube videos (UAT + PROD, 2026-11-22)

UAT release `16204d925` (initial action `fe905c491`) adds **Academic Curriculum → subject → topic → Videos → Fetch More YouTube videos**.
The button is available even when the approved lesson has zero videos. It searches for up to four additional matching
videos and retains them in the learner's account. The choices are all permitted groups, English India, English
US/UK/Europe, English Asia/Middle East, and Indian languages (including Tamil). An Indian-language search requires
selecting a language. The platform's discovery tier permissions, caching and YouTube quota still apply.

- This fixes the missing student-side search action; the previous Videos tab only displayed links published with the
  lesson. It does not mean all syllabus topics already have faculty-approved video coverage.
- `college-curriculum-agent` action `fetch_academic_videos` checks the caller's enrollment and source/batch validation
  through `academic_subject_content` and `my_academic_subjects`. Search context comes from the approved subject/lesson,
  never a client-supplied title. Invalid, unpublished, cross-offering and inaccessible topics are refused before search.
- The shared metadata/relevance/embeddability checks run without generating new lessons or calling a generative model.
  Existing curriculum candidates (including rejected links) and the learner's saved links are excluded.
  Every query retains the subject context, and a subject anchor must appear in actual video metadata. This closes a
  gap caught during live QA: a bare fallback for Python "Error messages" accepted an unrelated boiler-repair video.
  That result existed only in the temporary QA account and was removed. Query text alone cannot pass the subject check.
- New links are **personal recommendations**, visibly separate from **faculty-approved lesson videos**. They do not
  change the published package or bypass its independent approval. Spoken language is not claimed as verified.
- Retention reuses `student_saved_videos`, with `module_id=academic:<offering UUID>` and `topic_key=<lesson UUID>`.
  The caller-scoped `save_student_module_videos` RPC atomically merges links; reloads do not repeat searches. It cannot
  overwrite the corporate curriculum's saved links or show another learner's discoveries. No new schema is required.
- Loading, empty-result and quota/configuration errors remain visible. Search is disabled while a request is running;
  a delayed result cannot appear under a different topic. Existing links remain visible after an unsuccessful search.

Code: `AcademicVideosPanel.tsx`, `useAcademicVideos.ts`, `academicVideosApi.ts`, and
`college-curriculum-agent/learner-videos.ts`. Validation: 67 focused tests passed; new frontend files lint clean.
TypeScript reports the same 24 existing diagnostics outside these changes. Built on UAT with UAT environment values;
final UAT snapshot `~/banking-sb/snapshots/20261122T031015Z`, bundle `index-CUbH-0IM.js`. PROD promotion is recorded above.
Operational checks: `~/banking-checks/academic-fetch-videos-20261122/`.
Live validation passed ten journey/access checks: the previously empty **Error messages** lesson fetched two Python
recommendations, rendered both links, and retained them across a full reload without another search. A separate player
check loaded the real YouTube embed with no console errors. Region/language controls (including Tamil selection), mobile
width, per-topic isolation, duplicate-free retention and owner-only access passed. The 49 approved packages were unchanged.
Both temporary learner accounts, their enrolment, personal video rows and QA consent were removed; no real learner's
recommendations, progress or consent was changed. This checks discovery and embedding, not full audiovisual/language review.

## Complete topic preparation and student downloads (UAT + PROD)

Live on UAT at `405d5a499` (2026-11-22; original feature `8b6b31e24`, source-rights fix `e71af26f3`, shared video formatter fix `6cb0ca2ca`).
Included in PROD `v1.1.30`. Original UAT snapshots: `20261121T170108Z`, `20261121T171019Z`. Migrations
`20261121190000_academic_learning_packages.sql` and `20261121193000_academic_source_permission_snapshots.sql`
are applied on DEV, UAT and PROD; canonical copies are in DB-Scripts / Banking LMS College Mode.

- Faculty/trainer: **My Courses → Open course → Lessons from textbook** now has source/batch verification, PDF URL
  import, topic preparation and review. Existing manual upload remains available. Trainer registration must also be approved.
- Verification downloads the public syllabus, compares SHA-256 with the uploaded copy and checks college/regulation
  evidence for the admission batch. A separate scoped HOD/principal/admin checks the submission. Autonomous mode
  rejects a non-autonomous syllabus; university mode remains available. SRM's user-confirmed Anna University mappings
  have **not** been replaced by Easwari's autonomous syllabus.
- `import_learning_source` accepts a permitted public PDF URL with permission confirmation and distribution evidence.
  Existing SSRF/redirect/size/PDF checks apply; file and extracted-text duplicates are rejected. Original book distribution
  is `reference_only`, `open_licence` or `college_permission`, independently of permission to prepare lessons.
- **Prepare topic / Prepare missing topics** generates one cited lesson, three evidence-checked MCQs and one academic
  application simulation per selected topic. At most 25 missing topics run sequentially; keep the browser open. Stop finishes
  the current topic. Saved packages are reused on retry. Generation uses the Admin `pl/college-curriculum` gateway/fallback.
- YouTube discovery follows preparation and uses the shared quota/cache/verification pipeline. All four region choices
  are available: English India, English US/UK/Europe, English Asia/Middle East, and Indian languages (including Tamil).
  Platform order uses permitted groups. Up to four distinct matching videos are saved. Metadata, embedding and relevance
  are checked; HOD must verify teaching quality/spoken language. Genuine no-match can be reviewed with a reason;
  quota/configuration errors block publication and must be retried.
- HOD sees the lesson, quotes/pages, permission evidence, questions/answers, video links and simulation goal/model answer/rubric.
  Self-approval is blocked. Return allows draft rebuild. Approval freezes the simulation and publishes only to validated,
  enrolled batches. Legacy unit review/rebuild cannot bypass this workflow or overwrite published topic packages.
- A different authorised reviewer can **Reject video** on a pending topic after entering a reason. The candidate stays in
  the audit record with the reviewer identity/time and is excluded from publication. A maker, unrelated reviewer, or caller
  targeting another topic or a published package cannot reject it. A topic with all candidates rejected returns to
  `no_match`; its maker may search again. Retries exclude prior candidates, fill only the remaining slots up to four, and
  reuse four retained videos without another search. English/Indian-language choices are also included in search text;
  this improves discovery but is not proof of spoken language, which still requires review.
- Generation asks for three source facts with exact quotes and zero-based citation indexes, and descriptive MCQ options
  rather than punctuation-only choices. MCQ option comparison preserves code punctuation (`/` versus `//`, empty strings,
  assignment versus equality). Citation pages are attributed deterministically to the actual selected PDF pages, including
  a quote spanning two consecutive pages. Citation checks tolerate PDF ligatures and line-break hyphenation only when the
  normalized text matches exactly; invented passages still fail. Rejected drafts report unsupported/duplicate/invalid
  question counts and are not saved.
- Student **Academic Curriculum** includes **Download source PDF**, **Download lesson PDF**, Read, Videos, Check understanding
  and Simulation. Signed downloads expire after 120 seconds. Original books require reviewed distribution permission;
  changing its evidence removes book-download access until reviewed again. Lesson PDFs are cached by content hash,
  cite sources/pages and exclude quiz answers and simulation solutions.
- Statuses: source missing, validation pending, preparation pending, review pending, revision requested and published.
  Existing `sim-attempt`/SimPlayer handles academic application practice with academic reasoning criteria. Corporate
  subscriptions/assignments do not grant academic access. Practice scores do not change college marks. Robo Faculty
  excludes pending topic drafts and textbook grounding for unvalidated batches.
- New tables: `academic_syllabus_validations`, `academic_topic_packages`; existing curriculum and immutable simulation
  tables are reused. Service-only atomic saves prevent partial package publication.

Checks: 96 automated tests; rolled-back DEV/UAT SQL access/approval tests; 37 distinct live API/browser checks.
One paid test produced a source-checked lesson/quiz/simulation; YouTube returned four videos. Faculty → HOD → student,
PDF downloads/A4 layout, quiz 3/3, simulation launch, mobile width and zero app errors passed. URL import, duplicate
rejection, private-address rejection and unenrolled download denial passed. A full paid simulation conversation was not run.
Test kit: `~/banking-checks/academic-packages-20261121/`. TypeScript retains 24 unchanged baseline diagnostics.

Real SRM Python preparation now uses the existing platform admin as maker and a **different existing authorised admin**
as checker, at the user's explicit instruction; no HOD identity is fabricated. Other real-course packages still need their own
preparation/review. Official Easwari R2023 was fetched and validated only in an isolated QA programme; this does not override
the earlier user-approved Anna University choice. Do not report all Semester 1 subjects as published.

UAT release `405d5a499` includes `0283d4001`, `500f39b1f`, `93e2551cc`, `a4f559959` and `dc756d9f6`.
Snapshots include `/home/ubuntu/banking-sb/snapshots/20261122T020135Z`, `20261122T020825Z`, `20261122T021755Z`
`20261122T022725Z` and final `20261122T023651Z`. Validation: 61 checks passed; one existing Robo Play source-location assertion fails because
`ttsAttemptId` moved from the page into `useVoiceRun.ts` in `7be86e04b` (both files unchanged by this release).
TypeScript has the same 24 existing baseline diagnostics.

The subject RPC previously repeated programme-wide permission checks for every lesson, including every PDF request.
`20261122023507_academic_content_scope_once.sql` checks enrolment and curriculum/batch access once, then selects only
approved packages for that course (or approved legacy unit material). SRM Python response hash was identical before/after;
database execution fell from **21.613 s to 53 ms**. The 28 rolled-back source, batch, outsider, maker-checker and publication
checks passed on DEV and UAT. Canonical DB-Scripts commit `0e5c11e`:
`Banking LMS College Mode/20261122T023507Z__academic_content_scope_once.sql` (DEV/UAT/PROD applied).
This performance follow-up adds no tables or columns; it is included in PROD `v1.1.30`.

## Real SRM Python topic publication (UAT + PROD, 2026-11-22)

The approved UAT records and private PDF objects were promoted to PROD with v1.1.31, preserving the review evidence below.

The user authorised preparation and approval using existing admin accounts. The maker and checker are different existing
platform admins; each review note explicitly records **user-authorised agent-assisted admin review**, rather than claiming
a human HOD performed it. Course `22ab4950-b7cd-4976-8fdf-0a27dee78d88`, CS25C02 **Computer Programming: Python**, Robotics
and Automation Semester 1, has **49 approved topic packages across six units**, 147 questions and 49 published simulation
versions. Student offering: `ce1f534b-bd03-4f07-b6bd-077a0d748835`. This is one subject, not every Semester 1 subject.

Eight permitted supplementary sources were imported through the source workflow: official Python 3.12.11 Tutorial,
Language Reference and Standard Library excerpts (PSF licence); official NumPy, SciPy, pandas and scikit-learn documentation
print extracts (BSD licences); and original PluginLive problem-solving notes (CC BY 4.0). Licences, origin URLs, fingerprints
and page citations are retained. They are supplementary learning materials, not asserted to be the college's prescribed
textbooks. The previously user-approved Anna University syllabus mapping remains in place.

Dictionary drafts that overgeneralised key eligibility and a SciPy draft that generalised all linear-algebra results to
2-D arrays were returned and rebuilt through the maker-checker workflow. Exact duplicate topic keys/questions: zero.
All 49 packages completed video discovery. Rejected candidates remain audited and unpublished. Retained video review is
based on titles, channels, relevance and embedding metadata; it is **not** a full spoken-language/audiovisual audit.
There are **37 published video links across 25 topics**. The other 24 topics have no retained suitable video; their cited
reading, quizzes and simulations were independently reviewed and approved with an explicit no-video reason. Four videos
is a maximum, not a coverage guarantee.

Read-only verification as the actual enrolled SRM student: all 49 topic pages and 147 question options render; each unit's
simulation entry opens; a video tab embeds the approved links; the browser download button works; mobile width is 390px
without horizontal overflow; no application page errors or failed backend calls. Student content API measured 97 ms.
All **nine source PDFs and 49 lesson PDFs** downloaded; the 49 lesson PDFs span 69 pages and had no empty pages or text
outside page margins. PDF and desktop/mobile screenshots were inspected. No real student quiz, simulation attempt,
reading progress or privacy-consent record was created or removed during this verification.
Operational kit: `~/banking-checks/srm-python-publication-20261121/` (preparation, review, publication and verification records).

## Historic published syllabus validation repair (UAT, 2026-11-21)

UAT runtime revision `a95b1f051` (status-record commit `5f361e77b`; snapshot
`/home/ubuntu/banking-sb/snapshots/20261121T180704Z`) restores the source/batch wiring for already-published curricula.
The same verified legacy repair was applied on PROD on 2026-11-22. The problem was not a student-menu or Robo Faculty route defect: published legacy builds pre-dated
`academic_syllabus_validations`, so `private.academic_validation_ok` correctly but misleadingly denied them as unvalidated.

- All 37 SRM Anna University syllabus PDFs were re-read from storage and byte-for-byte matched to their official Anna
  University CAC source URLs before their provenance fields were repaired. No textbook/e-book material was fetched or
  generated by this repair.
- Migration `20261121203000_backfill_verified_legacy_syllabus_validations.sql` created **75** historical records: 74 SRM
  build/admission-batch mappings and one already verified TCET mapping. It only includes a published/archived pre-workflow
  build with an accepted offering, a ready syllabus, a stored SHA-256 and an official source URL. New curricula still use
  faculty submission plus independent HOD review.
- The historical row records the original publisher/creator and explicitly says that no current HOD identity was inferred.
  It is not a blanket approval: `academic_validation_ok` still requires the saved hash and official URL to match the live
  source, so a source replacement immediately removes student and Robo Faculty access until it is revalidated.
- Exact read-only UAT check: the SRM Robotics & Automation 2026 student's **CS25C02 — Computer Programming: Python** now
  opens with the official source, **Download source PDF** and an available **Ask Robo Faculty** entry point; it has no failed
  app calls and no `validation pending` state. At that point it said **Preparation pending** because no licensed textbook
  topic package had been prepared. The 2026-11-22 Python publication above resolves that state for all 49 topics.

Canonical migration: DB-Scripts → *Banking LMS College Mode* →
`20261121T203000Z__backfill_verified_legacy_syllabus_validations.sql` (DEV/UAT/PROD applied).

## What it does

**Academics → Curriculum agent** (college-mode institutes; academic admins and platform admins build syllabus versions). Faculty,
HODs and principals work on lessons from the course workspace (tab **Lessons from textbook**) and the HOD inbox (see below).

1. **Documents.** Per programme the admin uploads the approved syllabus PDF (university / deemed / autonomous) and the prescribed
   textbooks (PDF, max 50 MB, bucket `curriculum-sources`, path `<institute>/<programme>/<uuid>.pdf`). A textbook needs the
   "college holds a licence or library copy" tick; its text is used to draft lessons. On UAT and PROD, original PDF downloads additionally
   require reviewed distribution permission through topic preparation.
   Every upload records its **source** (`issuing_body`: university, deemed university, autonomous, AICTE/UGC model curriculum,
   college website, publisher, author's e-book repository, library copy, other) plus optional link, publisher, edition, ISBN.
   `read_source` extracts text page by page (unpdf); under ~100 characters per page it is marked **scanned**.
2. **Build a version** (`start_build` → `extract_next` until it returns `draft`). The syllabus is read in page ranges of at most
   10 pages / 18,000 characters (8 pages for scanned PDFs, which go to the model as PDF pages). Each range returns courses
   (semester, code, title, credits, L-T-P, type core/elective/lab/project/audit/other, units with topics, prescribed textbooks,
   page numbers) plus the semester credit totals printed in scheme tables. The same code from several ranges is merged.
3. **Checks + self-repair.** Per semester the course credits (audit excluded) must equal the printed total; every non-elective
   course needs a semester and (except audit) credits; missing units / textbooks and odd code formats are warnings. If an error
   remains after the last range, one extra `extract_next` re-reads only the scheme pages with the failures listed and applies
   corrections **only for codes printed on those pages** and never to courses an admin edited. Remaining errors show in red.
3b. **Reconcile (deterministic, before and after the repair pass; `reconcile()` in the shared module).** An elective *option* with a
   real course code loses its semester (only elective *slot* rows belong to a semester). In a semester that matches the printed
   total only when its "audit" courses are counted, those courses become core (Anna University R2025 Life Skills / Physical
   Education are 1-credit and counted). Admin-edited courses are never changed. **Re-check against syllabus** (action `recheck`,
   draft only) re-runs reconcile + one more repair pass + the checks. The repair pass falls back to the first two page ranges
   when no scheme table was detected.
4. **Review.** Per semester: accept / reject / edit (semester, code, title, credits, type), "Accept all without errors".
   Edited courses are marked `edited`.
5. **Publish** (`publish_curriculum_build`): every pending course must be decided. Accepted non-elective courses are upserted
   into each section of the programme whose term has that semester number (`course_offerings`, matched on section + code,
   linked by `build_course_id`); elective options are reported and placed through elective groups. The previous published
   version of the same programme + regulation is archived; its courses that the new version dropped are removed unless they have
   activity (class sessions, grade components, assignments or lectures), which are kept.
6. **Delete** (`delete_curriculum_build`): same activity rule; kept courses are unlinked. **Regenerate**: new draft from the same
   syllabus with `replaces_build_id`; edited courses and already built lessons carry over.
7. **Lessons from the textbook** (`build_content`, per unit): the agent maps units to textbook pages once per textbook
   (`unit_pages`), then writes 3–6 lessons in its own words with page citations and 3 MCQs per lesson into a `trainer_curricula`
   (one subject per unit; rebuilding a unit replaces it), mapped to the institute. Every lesson and question must carry a word-for-word
   quote from the pages; see *Quality controls*. The unit waits for the HOD; the section courses (`course_offerings.curriculum_id`)
   are linked on approval. Scanned textbooks are refused with a message (upload the text PDF / ebook). A unit the book does not
   cover is refused ("… does not seem to cover unit N").

The agent does **not** search for or download textbooks; colleges upload licensed copies.

## Official syllabus-source finder and student curriculum route (UAT, 2026-11-21)

UAT commit `bc3b45a4c` adds a deliberately narrow way for an authorised curriculum contributor to find an
**official syllabus**, before the existing maker-checker flow begins. It is not a web-wide search or an automatic
publication feature.

- In **Curriculum agent → Documents**, the user can select the programme and choose **Find an official syllabus**.
  The finder starts with the institute's registered website and can accept up to four additional public source pages
  (for example, an official university, department, AICTE or UGC page). It follows only relevant links on the same
  site for one hop (at most 12 HTML pages and 30 PDF candidates).
- The Edge function accepts only public HTTP(S) URLs: no credentials, custom ports, localhost/private/reserved
  addresses or hostnames that resolve to them. It checks DNS at every redirect (maximum three), caps HTML at 1.5 MB
  and PDFs at 50 MB, and verifies the downloaded bytes are actually a PDF. A candidate is re-read from its source
  page when **Import & check** is clicked, so a caller cannot submit an arbitrary URL.
- Only an existing contributor (academic admin, principal, department HOD, or faculty teaching in that programme)
  can discover or import a source. `curriculum_source_contributor_access(program)` exposes that existing check to
  the caller-scoped Edge request before it fetches any external page.
- Import records the source URL and issuing body, stores the PDF in `curriculum-sources`, and then invokes the same
  `read_source` fingerprint/text duplicate checks as a manual upload. It does **not** run a generative model during
  discovery, create a curriculum version, or publish content. The HOD's separate review/publish step remains
  mandatory.

The student route was subsequently replaced by a dedicated learning page (below). The earlier
`/my-courses?area=courses&view=curriculum` link now redirects to `/academic-curriculum`.

Navigation: academic admin → **Institute Journey → Academic set-up → Curriculum agent**; eligible faculty/trainer
→ **Trainer Portal → College → Academic curriculum**; student → **Learn → Curriculum & Modules → Academic Curriculum**.

## Separate academic learning and trainer delivery (UAT, 2026-11-21)

UAT commits `43d912d56` + `ab98e4653` + `7a64c09b4` added `/academic-curriculum`; this is included in PROD `v1.1.30`.
This was the first learning-page/audience-separation release. YouTube discovery and a generated simulation per prepared
topic are available through the preparation workflow on both environments.

- **Academic Curriculum** has its own sidebar key (`academic_curriculum`), available through actual section
  enrollment. It shows subject cards, semester/search filters, syllabus units/topics and approved lessons.
  Each lesson offers reading, approved YouTube videos and a practice quiz. Practice scores do not change
  academic grades or attendance. Saving reading/quiz progress refreshes the subject cache so the status survives
  topic navigation. Topic labels in new generated lessons are matched to canonical syllabus labels;
  older lessons without an exact topic mapping remain accessible as unit reading.
- **Ask Robo Faculty** is optional within a unit/topic and prefills that context. Merely opening the curriculum
  does not start a class or generate anything. **My Courses** retains attendance, assignments, timetable and grades.
- **Trainer Curriculum** remains a separate destination and retains existing published corporate/general
  training assignments and module materials. A learner with both kinds of assignment can see both journeys;
  college enrollment no longer replaces the trainer-content menu or grants its subscription entitlement.
- `trainer_curricula.audience_type` is `college_academic`, `corporate_training` or `general_trainer`.
  The migration classifies proven academic links and exclusive corporate institute mappings. Ambiguous
  legacy rows remain general; no assignments or content are deleted. New academic-agent rows are classified
  by a trigger, and an academic row cannot be changed back through the legacy editor.
- `student_has_curriculum` requires academic section enrollment in the matching institute/programme and an
  accepted course in a published/archived syllabus version. A direct or institute-wide training assignment
  cannot grant academic access. Legacy direct/cohort/institute assignments retain their behavior; a trainer-only
  recipient is never interpreted as a student grant. The student training page uses `my_assigned_curricula`
  as the authority, rather than broadening it with client-side cohort matching.
- The training page resolves assigned curriculum IDs first, then restricts curriculum/assignment reads to
  those IDs and the student's recipient/cohort rows. The previous full assignment-table scan took ~43 seconds
  in a live UAT check with 2,706 assignments; it is no longer part of the learner page.
- Restrictive RLS guards on curriculum parents/children cover historical broad authenticated read policies.
  Draft/returned academic units and answer keys are hidden from learners. Academic writes go through the
  college agent and HOD review, not generic trainer editors/generation endpoints. Trainer editors omit academic rows.
- New authenticated RPCs: `my_academic_subjects`, `academic_subject_content(p_offering)` and
  `record_academic_learning(p_offering,p_topic,p_answers)`. The reader returns approved lessons and safe question
  fields only; the server validates enrollment/topic ownership, records reading and scores the submitted choices.
  Answer explanations are returned after submission. Direct academic progress writes are blocked.
- **Content readiness:** at the start of this release UAT had 7,795 parsed course records and **zero linked
  textbook curricula**. Published syllabus topics therefore appear immediately, but missing lesson content
  is shown as awaiting publication. Faculty still upload a licensed textbook, build units, and obtain independent
  HOD approval. No source books were downloaded or bulk-generated as part of this release.

Migration: `20261121120000_academic_curriculum_learning.sql`; archived under DB-Scripts → Banking LMS College Mode
as `20261121T151008Z__academic_curriculum_learning.sql` (DEV/UAT/PROD applied).
Checks: isolated SQL tests cover academic/corporate/dual-context access, cross-institute denial, HOD publication,
hidden drafts/answers, retained legacy subtopic videos and server quiz scoring. UI tests cover subject/topic navigation,
optional tutor context, quiz submission, missing material and unsafe video/source URL rejection.

Release verification: 52 targeted unit/component tests passed; 14 live browser checks passed on UAT, including
dual-context and corporate trainer delivery, server-scored quizzes, saved progress after changing topics, tutor
prefill and mobile overflow. Temporary QA users/institutes/curricula and their consents were removed (verified zero
remaining). Read-only SRM verification found 21 offerings for a sampled enrolled account; one sampled subject
exposed six units / 29 syllabus topics and no approved textbook lessons. Latest UAT deployment backup:
`/home/ubuntu/banking-sb/snapshots/20261121T152153Z`; final app/remote revision `7a64c09b4`.

## SRM Semester 1 journey verification and repairs (UAT 2026-11-21; PROD 2026-11-22)

UAT revisions `fe7dc5cf6` and `7e6cab441` repair extraction and recover completed textbook builds after a lost
browser response. The code is included in PROD v1.1.30; the 25 outline repairs and MBA consolidation were promoted in
v1.1.31 using exact baseline guards. Original UAT backup: `/home/ubuntu/banking-sb/snapshots/20261121T155509Z`.

- The real-data audit covered **201 Semester 1 offerings across 22 SRM Easwari programmes**. All offering/build
  links were valid, with no duplicate course codes within a section. Student curriculum RPC reads were checked
  for all 201 offerings using disposable enrollment inside a rolled-back transaction.
- **25 empty outlines were restored from already-approved syllabus sources.** Twenty-two were matched to
  another approved extraction with identical course-section text; three were transcribed from exact source
  headings/topics (Biomedical EE25C04 and Structural Engineering ST25101/ST25102). This includes CSE English
  Essentials and Makerspace. No lessons or quiz content were invented or published into real student courses.
- MBA MB25C01 had each of its six unit numbers twice. The repair retains each distinct topic under one unit
  number. The exact guarded UAT data repair is tracked as `scripts/release/repair-srm-semester-one-outlines.sql`.
  Six Technical Seminar offerings retain no units because their uploaded sources contain only scheme entries.
- The extractor now explicitly includes unnumbered skill sections and lettered activity groups. `mergeUnits`
  combines repeated unit numbers and preserves distinct topics across extraction chunks. Previously `mergeCourse`
  retained whichever chunk had more units and could discard the other chunk's syllabus content.
- A live QA generation produced four evidence-checked lessons and twelve questions, but its browser connection
  closed before the response arrived. `buildUnitContent` now recovers a saved result after `FunctionsFetchError`:
  it performs up to 20 checks two seconds apart, restricted to the same faculty, book, unit and a save made
  after this request started. It never repeats the generation call. Server validation errors still surface directly;
  unsuccessful recovery asks the faculty to refresh and check before rebuilding.
- Faculty/HOD/student browser testing used four disposable accounts and a separate SRM QA programme/section
  containing copies of CSE's ten Semester 1 courses. Coverage included faculty subject access and PDF upload,
  duplicate rejection, HOD syllabus publication, return with reason, rebuild, independent approval, hidden drafts,
  hidden quiz answers, all ten student subject readers, filters, persisted reading/quiz progress, optional tutor
  context, mobile width, department isolation and self-approval denial. Real student consent/progress was untouched.
- **Real-use setup is still incomplete:** SRM has no faculty assigned to its Semester 1 offerings and no HOD
  mappings. The user was asked for the existing login emails and departments. Real programmes also have no
  textbook uploads or approved textbook lessons; the recovered syllabus outlines do not change that readiness.

Validation: 43 targeted unit/component tests passed. TypeScript has the same 24 pre-existing diagnostics as the
previous release, with no new diagnostics. Test scripts and evidence are in
`/home/ubuntu/banking-checks/srm-sem1-20261121/`; `audit-before.json` preserves the pre-repair outlines.
The final UAT browser smoke passed for all three roles. A controlled lost-response test recovered the saved
unit in the faculty page with exactly one generation request attempt (intercepted; no extra paid call).
Cleanup verified zero remaining owned QA accounts, programme/section, textbook objects or generated content.
All 201 original subject mappings remain; only the documented 26 outline corrections changed real curriculum data.

## Quality controls (UAT + PROD, 2026-11-18)

Roles (`private.can_contribute_curriculum(program)`, `private.can_check_curriculum(program)`):
- **Contributor** — academic admin, principal, HOD of the programme's department, faculty teaching any course in the programme
  (`course_faculty` → offering → section → programme). Contributors read the programme's sources/versions/courses, upload sources
  (storage + row; delete only their own) and build lessons.
- **Checker** — the HOD of the programme's department; when that department has no HOD, the principal or an academic admin.

Checks:
- **Duplicates** (`read_source`): sha256 of the file and sha256 of the normalised text (≥ 2,000 chars). A second copy in the same
  programme + kind, whether the same file or a re-saved copy with the same text, fails with "Duplicate of "<title>" uploaded on
  <date>. Delete this copy." (`duplicate_of` set). Hashes are written only by the agent (trigger `curriculum_quality_guard`).
- **Mapping**: the textbook must belong to the course's programme and institute.
- **Hallucination** (`_shared/curriculum-quality.ts`, `checkUnitContent`): each lesson needs ≥ 1 and each question 1 quote from the unit's
  pages, at least 5 words. A quote counts when it matches the pages exactly (ignoring case, punctuation and spacing), or when 80% of
  its 4-word runs are on the pages. Unsupported lessons and questions are dropped. If nothing survives, nothing is saved (422).
- **Duplicates in content**: lessons with ≥ 0.8 key-word overlap are dropped. Question stems already used in the unit or in other units
  of the course are dropped. Malformed questions (fewer than 2 or more than 6 options, repeated options, bad answer index) are dropped.
- **Report** saved in `curriculum_subjects.metadata.quality` and shown to the HOD: prescribed book yes/no (title match against
  the syllabus textbooks); kept/removed counts; lessons copying ≥ 12 words verbatim (flagged, not removed); syllabus topic
  coverage with the missing topics.

Maker-checker:
- Unit state lives in `curriculum_subjects.metadata` (`review_status` pending/approved/returned, `built_by`, `built_at`,
  `reviewed_by`, `reviewed_at`, `review_note`). The course aggregate is `curriculum_build_courses.content_review_status`
  (+ note, checked by/at). Clients cannot change these (guard triggers); only the agent and the definer RPCs can.
- `review_curriculum_content(course, 'approve'|'return', note)`: checker only. Return needs a reason. **The person who built
  a pending unit cannot approve it.** Approve links the section courses.
- `curriculum_content_for_review(course)` returns units, lessons, quotes, questions, report and `can_check` to contributors.
  `curriculum_review_queue(institute)` is the checker's inbox: draft versions to publish plus courses with pending lessons.
- **Robo Faculty** grounds a class only on units that are not pending or returned. Content without `review_status` (built before
  2026-11-18) counts as approved.
- **Publish** (`publish_curriculum_build` → `private.assert_can_publish_build`): only the programme's checker, and never the
  person who created the version. The academic admin still accepts or rejects courses. The HOD sees a read-only version review
  with **Publish** in the inbox. A college with one admin and no HOD or principal cannot publish its own versions; another admin,
  a principal or a PluginLive admin must.

UI: Trainer portal → **College overview** opens with *Curriculum waiting for your review*, shown only when there are items.
Course workspace → **Lessons from textbook**: pick or add a textbook, Build / Rebuild per unit or Build all, status, built by,
checks, an expandable lesson view with quotes and answers, and HOD Approve / Return. The admin Curriculum agent's "Lessons"
dialog is the same panel.

Measured on UAT 2026-11-18 (CS25C01, 6-page test book): 5 lessons and 15 questions, all verified, prescribed yes, coverage 16–17
of 18 topics. A build takes 16 s to about 3.5 min depending on the gateway (the page waits up to 4 min). If the page is closed
during a build, the result is still saved.

## AI route

Task **`pl/college-curriculum`** (gemini-2.5-flash, reasoning disabled → gpt-6-luna, 120 s per attempt, 0 retries, text; PDF
file parts work on the primary). Registered 2026-11-16 on the UAT gateway (policy backup `policy-backups/tasks-20261116T152521Z.json`,
key `banking-app`) and the PROD gateway (backup `policy-backups/tasks-20261116T152550Z.json` on the PROD builder, key
`banking-app-prod`); normal → gemini-2.5-flash and `mock_timeout` → gpt-6-luna verified on both, PDF input verified on PROD.
DEV banking uses the UAT gateway. Tags `service:banking-app,module:college-curriculum-agent`.

## Measured behaviour (2026-11-16)

- 57-page KCG R2023 B.E. CSE syllabus: 131 courses, ~90 s, all 8 printed semester totals matched on UAT (twice) and in most DEV runs;
  a failed check is fixed by the repair pass or shown in red. 336-page CC-BY textbook: 5 units → 26 lessons, 78 MCQs, ~20 s per unit.
- 30-page ranges made the model skip most courses; `temperature: 0` made it loop until the 16k-token cut-off — don't add either back.
  A cut-off answer is a retryable 503; the browser retries each range twice (240 s timeout) before showing "Retry this part".
- The UAT gateway path cuts a single call at about 60 s; ranges are sized to stay under it.

## SRM Easwari Engineering College — Anna University curricula (UAT + PROD, 2026-11-16)

**PROD (2026-11-16 ~18:05Z, user's go):** the confirmed UAT result was copied, not re-generated: 37 PDFs uploaded to PROD storage at the same paths; `curriculum_sources` (37), `curriculum_builds` (37 published + 4 archived), `curriculum_build_courses` (7,787) and the 899 `course_offerings` imported with the same ids (institute, programme and section ids are identical on UAT and PROD); the 1,172 modelled courses removed (no activity; backup `/data/backups/srm_prod_old_offerings_20261116.csv` on the PROD VM). Fingerprint of (section, code, credits) identical on UAT and PROD; 0 empty sections, 500 memberships unchanged.

 Source: Anna University CAC pages for **non-autonomous affiliated
colleges** (`cac.annauniv.edu/aidetails/ai_ug_cands_2021ft.html`, `…ug_cands_2025ft.html`, `…pg_cands_2025ft.html`).
Batches → regulation: 2023/2024 batches (Sem 5–8) **R2021 (Revised)**, 2025/2026 batches (Sem 1–4) **R2025**; PG (2025/2026
batches) R2025. 37 official PDFs (15 UG × 2 + 7 PG; R2021 books 337–421 pages), one syllabus source + one version per programme
and regulation (`AU R2021` / `AU R2025`), all **published**. Kit: `~/banking-checks/srm-anna/` (`manifest.tsv`, `run.cjs`,
`recheck.cjs`, `publish-all.cjs`, `plan.json`); ~900 AI calls, ~45 min wall time with 8 in parallel.

**Review rule applied (as the reviewing admin):** accept non-elective courses with a real course code in the semesters the
regulation covers; elective slot rows ("PROFESSIONAL ELECTIVE – I") rejected; a semester whose accepted credits exceed the printed
total is **held** (rejected, old courses kept; hand-corrected the same day, see below): R2021 Civil Sem 5–6, CSBS Sem 7, IT Sem 5, and R2025 M.E. Structural Sem 3
(no printed totals, 17 courses). Result: **887** Anna University section courses placed; **1,132** old script courses removed from
sections that received agent courses (backup CSV `~/banking-sb/snapshots/srm_script_courses_removed_20261116.csv` on UAT); 40 old
courses remain only in the held semesters; 0 empty sections; 500 student memberships unchanged. R2021 Sem 5–8 carry few core
credits by design (most credits are elective slots), so the red total checks on those versions count the slot rows.

**Held semesters hand-corrected 2026-11-16 (user confirmed Anna University's affiliated curriculum is right for SRM Easwari).**
New versions copied from the published ones (no AI), corrected from the PDF scheme tables, published (old versions archived):
R2021 Civil Sem 5 CE3501/CE3502/CE3503/CE3511 lab/CE3512 project (12 cr = 21 − 3 PE) and Sem 6 CE3601/CE3602/AG3601/CE3611 lab
(11 cr = 23 − 3 PE − OE); R2021 CSBS Sem 7 GE3791 (2 cr = 14 − 4 slots); R2021 IT Sem 5 CS3591/IT3501/CS3551/CS3691/IT3511 lab
(16 cr = 22 − 2 PE); R2025 M.E. Structural Sem 2 ST25201/ST25202/ST25203/ST25204 lab (12 cr; 5 elective options removed) and
Sem 3 ST25301 training + ST25302 Project Work I (8 cr). Mixed-in elective options became unplaced electives; corrected rows are
marked `edited` (kept on regenerate). Script `~/banking-checks/srm-anna/held_fix.sql` (one transaction, temporary admin removed).
The last 40 script courses were removed (CSV `srm_script_courses_removed_held_20261116.csv` in UAT `~/banking-sb/snapshots/`).
**SRM on UAT now: 899 section courses, all from the agent, 37 published versions, 0 empty sections.**

Caveat (resolved — user confirmed Anna University's curriculum is correct): SRM Easwari is an **autonomous** institution with its own R2023 curriculum (codes like `231CSC301T`); Anna University's
affiliated-college curriculum was used on the user's instruction.

## Swaminarayan University catalogue and official-source map (UAT and production, 2026-11-23)

At the user's request, **Swaminarayan University** was mapped from its official current programme brochure, faculty pages and
official syllabus pages. Its registered website is `https://www.swaminarayanuniversity.ac.in/`. The catalogue has **159 active
degree/specialisation pathways across 18 faculties**. Specialisations are separate programme rows so a future syllabus or
admission batch cannot accidentally be attached to a neighbouring specialisation.

Production has its own active university record. Its campus is in Saij, Kalol, Gandhinagar district, Gujarat 382725,
as listed on the [university contact page](https://www.swaminarayanuniversity.ac.in/contact).
The release check matched all 159 programme records and their official PDF mappings on UAT and production.
Each of the 132 private production files was downloaded and verified against UAT by SHA-256, totalling 195,377,672 bytes.
The catalogue and repeatable verification queries are in the [Banking LMS release](https://github.com/PluginLive-Technologies/bankingjobreadiness/tree/d41baa36173537ef7ee1fe2b629ddc47c0e2cbb8/QA/swaminarayan-university).

- **132 public, official University PDF sources** were imported through `import_official_source`, each with its public URL,
  SHA-256, page count and parsed text. They cover **42 programme paths / 6,185 pages** in the faculties where the University
  currently publishes programme-specific syllabus or teaching-scheme PDFs: Nursing, Law, Arts & Humanities, Education,
  Physiotherapy, Homoeopathy, Science and Engineering. The exact current/revised or honours document was selected where the
  source page also retained old-scheme material. One byte/text duplicate identified by the importer was removed; final source
  check: 132 ready, zero failed, zero duplicate URLs, zero missing URL/hash/page fields.
- At release, production had zero curriculum builds and no appointed Dean or HOD. Creating the production Dean appointment
  requires a verified production login. For student access, academic staff prepare a version from the applicable sources,
  obtain an independent review, validate the admission batch and assign the published courses to sections.
- On UAT the Dean received the institute role needed to start a build. The official 34-page B.Sc. (Hons.) Physics
  syllabus produced a 15-course draft. A separate one-course QA run verified HOD review, admission-batch validation
  and the enrolled student's PDF download. The fixtures were removed. The release rerun passed the UAT Dean access
  check and the academic learning-package regression.
- The University library points to its controlled e-resource / RemoteXs access at
  `https://library.swaminarayanuniversity.ac.in/Resources.aspx`. Both environments record the library link. Title-specific
  permission is pending for e-books used in lesson preparation.
- The official channel is `https://www.youtube.com/@swaminarayanuniversity7767`. It is recorded in the institute notes, but
  promotional channel videos are **not** curriculum videos. The platform discovers candidates only after a source-backed topic
  package exists, then requires a separate reviewer to assess relevance, teaching quality and language before publication.

### Demo access on UAT and production

For the demo account ending in 5335, **Institute Journey → Academic set-up → College** lists SRM Easwari Engineering College and Swaminarayan University first and labels them **(demo)**. Select **Curriculum agent** after choosing a college. SRM has 22 programmes and the account's existing learner enrolment gives it 11 SRM courses. Swaminarayan has 159 programmes and 132 official syllabus PDFs. Its student course list is empty until the university publishes courses and assigns a section.

The picker reads the account's `profiles.metadata.demo_college_ids` and displays matches from its authorized list of active colleges. Changing a demo preference preserves the user's home organisation, academic roles and class enrolments.

## Known gaps

- A college needs a checker before anything can be approved or published: a HOD per department (Academics → Heads of department),
  or else a principal or academic admin. Rajeev Gandhi College of Management Studies (PROD) had no HOD, no principal and no
  institute-role user on 2026-11-18, so only PluginLive platform admins could approve or publish there.

- Students see HOD-approved `course_offerings` through **Academic Curriculum** and can enter Robo Faculty from each
  subject. My Courses does not separately render a browseable textbook-lesson document library; Robo Faculty uses
  approved lessons as its grounded teaching content.
- Deleting a whole college that has sections fails in one cascade (older college-mode issue: `class_sections` →
  `academic_terms`). Delete in order (see `~/banking-checks/curriculum-agent/cleanup.sql`).
- `Development` has no college-mode code, so DEV deploys remove this function from the DEV stack.

## Checks

Quality controls: `~/banking-checks/curriculum-quality/` on DEV. On PROD (2026-11-18), `prod-rgcms/` ran the whole chain inside
Rajeev Gandhi College of Management Studies, on an isolated QA programme and section created by `fixture.sql`: 21 PASS covering
syllabus maker-checker (the creator cannot publish, faculty cannot, the HOD publishes) and lessons (duplicate refused, build, the maker
cannot approve, HOD approve, and a return with its reason). `db-rules.sql` also gave 20 PASS on PROD. Cleanup: `cleanup-files.cjs`
(storage API, so files leave the bucket), then `cleanup.sql`. `db-rules.sql` runs 20 role/maker-checker checks in a rolled-back
transaction (DEV + UAT 2026-11-18, all PASS). `e2e.cjs` is the live API flow (12 PASS): upload, both duplicate kinds, a student is
refused, build, faculty cannot approve, inbox, HOD approves. `neg.cjs` checks that an uncovered unit is refused. `ui.cjs` drives the
faculty tab and HOD inbox in a browser. Test book from `make_book.py`. Fixtures: `../journeys/fixture.sql` + `approve.sql`; cleanup
with `cleanup.sql`, then `../journeys/cleanup.sql`. Unit tests: `src/test/curriculumQuality.test.ts`.

`supabase/tests/college-curriculum-agent.sql` (rolls back; run on DEV, UAT and PROD 2026-11-16), `src/test/curriculumAgentChecks.test.ts`,
API/browser scripts in `~/banking-checks/curriculum-agent/` on DEV (`flow.cjs`, `content.cjs`, `publish.cjs`, `regen.cjs`, `rep.sh`,
`ui.cjs`; `CAG_ENV_FILE` / `CAG_BASE` point them at UAT). QA fixtures `fixtures.sql` / `cleanup.sql` + `cleanup-files.cjs`.
