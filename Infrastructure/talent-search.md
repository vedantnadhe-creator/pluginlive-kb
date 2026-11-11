# Talent search and student versions

Ranked candidate search over a separate `talent` schema, plus a full version history of each
student profile. Live on DEV and UAT, PROD pending. Backend only: no product screen uses it yet.
The only UI is the test page `/talent-search` on `dev.pluginlive.com` (masked PROD copy) and
`uat.pluginlive.com` (real UAT data), behind basic auth.

## What it never changes

Student tables stay one current row per student, and ATS reads them as before. `institute.tier` is
not used or written by search (it holds unproven legacy values, so search uses its own evidence).
The one exception is **going back to a version**, see below.

## Moving parts

| Part | Where | Notes |
|---|---|---|
| `datanormalization-talent-worker` | form-data-normalization, `python main.py talent_worker` | Its own container. Recreate it with the other siblings. Claims `talent.event_queue` |
| Search API | `POST /api/talent/search` | Needs `X-API-Key`; it returns student data |
| Versions API | `GET /api/talent/students/{id}/versions`, `POST .../versions/{versionId}/restore` | `X-API-Key` |
| Gateway tasks | `pl/talent-classify`, `pl/talent-search` | Registered per environment |
| Who changed it | student-node `app/helpers/studentChangeActor.js` | Prisma middleware calling `talent.note_change` |
| Junk guard | institute-node `app/helpers/masterNameGuard.js` | `kind` = degree, stream or college |

## Flow

1. Triggers on student and master tables queue events. A trigger failure cannot fail the save.
2. The worker classifies values into groups, using rules, then decided spellings, then two AI checks
   that must agree. New spellings go to Default at once and are placed after the save. Limit
   `TALENT_AI_DAILY_SPELLING_LIMIT` (2,000 a day); over that they wait.
3. `talent.student_profile` holds one search row per student.
4. A search makes one AI call to read the sentence into JSON (about $0.0016). Everything else is
   bound SQL composed from `talent.attribute_def`. The AI never writes SQL or sees student data.
   States are match, unknown and no. One person on several rows is listed once (`person_key`).

## Jobs, roles and skills

`talent.student_profile.jobs` keeps every job from `student.resume.work_experience` with the title and
company as typed, whether or not the company is one we know. A job is current when
`isCurrentlyWorking` says so; with no flag, a blank, "present" or future end date counts as current.
`current_role` and `previous_role` are searchable on their own; `role` matches either.

Skills come from `current_course.skills`, each job's `skill_set`, `students.skill_ids` and each job's
free-text `skills` (comma-separated). All are searchable by name. Only picked skills go to AI for an
industry hint; free-text phrases (tens of thousands) do not, to keep cost flat.

Industry evidence: worked 1.0, internship 0.7, skill 0.5, role 0.5 (only roles tied to one kind of
employer, `ROLE_INDUSTRIES` in `talent_facts.py`), department 0.3; at least 0.5 to join an industry.
One skill alone is enough today, which may be generous.

## College tiers

India has no official tiers. Ours: the brand list (IIT, NIT, IIIT, IIM, AIIMS, IISc, IISER, BITS, NLU)
or a NIRF rank within the top 50 (top half of a short list; a band counts as its bottom) is Tier 1.
Any other NIRF rank, including Innovation and SDG lists, or NAAC A++/A+, is Tier 2. NAAC A or B++ is
Tier 3. NAAC below that or declared over 5 years ago is evidence only. Everything else is Unranked,
meaning unknown. NIRF participants never earn a tier.

Sources (`~/scripts/talent_search/accred`, backup on S3 under `nirf-naac-20261106`): NIRF 2025 from
Internet Archive copies, because nirfindia.org refuses automated fetches; NAAC from the official
workbook of 14-08-2025 plus committee results to 12 Dec 2025. `build_seed.py` rewrites the seed, then
run `talent_seed`, which also replaces `talent.institute_evidence` and re-tiers students in search.

Search matches on the name alone, so a name shared across states earns no tier. `institute.tier` is a
separate live column read by ATS filters, ordering and reports. On PROD it was set for 2,406 institutes
on 2026-11-06 with name plus state/city checks (`build_prod_tiers.py`, undo with `prod_tier_revert.sql`).
About 13,000 PROD institutes still hold an unproven tier 1. DEV and UAT `institute.tier` values were not changed.

**Colleges added by students or forms get no tier (DEV + UAT 2026-11-11, PROD pending).** When a student picks
"Others" or a form upload brings an unknown college, student-node calls institute-node
`POST /institutes/crud/studentcollege`. It used to default `tier` to 1, so every typed-in college looked like
Tier 1 in ATS. Now `institute.tier` is nullable (DB-Scripts `Talent Search/20261111T060101Z__institutes_tier_nullable.sql`)
and that endpoint leaves it NULL; only a caller with evidence sets one. ATS tier filters (`tier = ANY/IN`) skip
NULL rows, views pass NULL through, and corporate-node already reads NULL as no tier. Apply the SQL before
deploying institute-node (Development `d82a1c0`, UAT `97f63b8`), or new student colleges fail on NOT NULL.
Old student-created rows keep their tier 1; there is no `source` column to pick them out safely.

## Versions

Student tables update in place, so `talent.student_version` keeps a full snapshot per change. Writes
queue a `version` event 15 seconds ahead, so one save across tables is one version, and an unchanged
hash adds none. Going back: the live student tables are rewritten from the snapshot, versions off the
path to it turn inactive (never deleted), and the next update branches from it. Login email and phone
are not restored. Going back writes `student.*` from form-data-normalization, a deliberate exception
that skips student-node side effects; move it to a student-node endpoint before offering it outside
the test screens. Deleting a student deletes their history. About 2 KB per version, no retention limit.

`changed_by` shows the person, "Form upload", or nothing. Raw SQL writes (admin-node
`linkStudentCampus`, `assignmentDb`), background jobs and bulk writes that do not name the student
are not attributed.

## Deploying

Run DB scripts first, in timestamp order (folder `Talent Search` in DB-Scripts): student-node calls
`talent.note_change`. Deploy institute-node before student-node is not required, but the database is.
Then: `talent_seed` **before** starting the worker (otherwise its first events fail and retry), start
`talent_worker`, then `talent_versions_fill` and `talent_fill`. AI decisions travel in the seed files
(`talent_export` adds new ones), so a new environment does not pay for them again.

## Gotchas

- `snapshot.debian.org` outages fail student-node builds in the apt layer. If only app files changed,
  build a small image `FROM student-node:api` with those files.
- DEV CI updates the student-node checkout but may not rebuild the container: check its uptime.
- `auto_deploy.sh` must run from the home folder (`./deploy.sh` is relative).
