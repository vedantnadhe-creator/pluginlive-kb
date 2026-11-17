# PilVidya (aividya) — Board curriculum: official sources

Status as of 2026-11-17: live on UAT (`8e5f4172`, branch `feat/chat-simulations`). There is no PilVidya PROD deployment.

## Where a student's subjects and topics come from

- Global topics live in `curriculum_topics` (`is_global = true`, keyed by `board`, `class_level`, `subject`).
- A school's own rows (`school_id`) add to them. Examples: the state language (Tamil for a Tamil Nadu school, from the TN textbook corporation), and books published through the school curriculum agent (`build_id`).
- Robo Teacher, Portion Tracker, Worksheets, Robo Classes and AI Coach list whatever these rows contain for the student's board and class.
- My Curriculum (`/student/curriculum`) also adds generic "NEP 2020 default" topics from `nep2020DefaultMapping.ts`. It now does this **only for subjects that have no verified source**. A subject with any `textbook_verified` row or a school build shows only those rows.

## CBSE Classes 3-10, 2026-27 (official)

- Source file `supabase/seed/cbse_2026_27_sources.json` holds 36 books and 386 chapters, each with its official link:
  - NCERT textbooks (`https://ncert.nic.in/textbook.php?<code>`, contents pages marked "Reprint 2026-27"): Maths, Science, Social Science and English for Classes 6-10. This includes the new Class 6-8 books (Ganita Prakash, Curiosity, Exploring Society, Poorvi) and the new Class 9 books (Ganita Manjari, Exploration, Kaveri, Understanding Society).
  - CBSE Computational Thinking & AI student handbooks for Classes 3-8 (`cbseacademic.nic.in/web_material/CurriculumMain27/CTAI_Pri<n>SH_2026-27.pdf`).
- Generator `supabase/seed/cbse_2026_27_topics.py` (with `--check`) produces migration `20261203010000_cbse_2026_27_official_topics.sql`. The migration is data only and idempotent:
  - each book is upserted into `curriculum_sources` as `source_key = cbse-2026-27-<code>`;
  - rows whose topic equals a chapter are kept, with textbook, chapter, `academic_year 2026-27`, `nep_stage` and `textbook_verified` set;
  - all other global CBSE rows of a covered class and subject are retired (`board = 'cbse-retired'`, `is_global = false`). They are never deleted, because 18 tables point at topics (progress, Robo sessions and assignments, portions, sims);
  - missing chapters are inserted.
- UAT run: 10 rows kept, 265 retired, 376 inserted. Backup: `~/pilvidya-checks/curriculum-source/backups/cbse_topics_pre_20261117T140936Z.csv`.
- Rollback: `UPDATE curriculum_topics SET board='cbse', is_global=true WHERE board='cbse-retired'`, then delete the inserted 2026-27 rows.
- Before this fix, global CBSE (and ICSE/State) Classes 6-10 Maths, Science and Social held the old NCERT **Class 9** syllabus copied into every class. English was 6 placeholders, and CT & AI had no topics while the card said "Computer Science".

## Subjects

- `ctai` "Computational Thinking & AI" replaces `computer` and `ai` for **CBSE Classes 3-8** (`subjectMatrix.ts`). ICSE, State and IB are unchanged.
- `LANGUAGE_SUBJECT_IDS` (`constants.ts`) lists the language subjects. Robo Teacher's subject picker has a **Subjects** group and a **Languages** group (English, Tamil, Hindi…), and English is labelled "English" there.

## Fetching sources

- `ncert.nic.in` serves an incomplete TLS chain, so use `curl -k` and check the content. `cbseacademic.nic.in` works normally.
- Kit: `~/pilvidya-checks/curriculum-source/` (`fetch_contents.sh <codes>` keeps only the contents text, `contents/*.txt`). The NCERT book codes come from the JS on `textbook.php`.
- Hindi and Sanskrit NCERT PDFs extract as garbled Devanagari, so they are not seeded. Enter them manually or publish them through the school curriculum agent.

## Checks

- Vitest: `cbseOfficialTopics.test.ts` (official links only, coverage, Class 6 is not the Class 9 list, no duplicates) and `subjectMatrix.boards.test.ts` (CBSE 3-8 has `ctai`).
- UAT: `~/pilvidya-checks/curriculum-source/robo-ui.cjs` (student 9820065335, CBSE Class 6). It checks groups, topics per subject and My Curriculum counts: 16/16 on `8e5f4172`.

## Open

- ICSE and State Classes 6-10 global rows are still the copied Class 9 list. They need official sources (CISCE / state textbook corporations) or school builds.
- CBSE Classes 11-12 are partly wrong: Class 11 Maths is the Class 9 list, Class 12 Chemistry repeats Class 11, and Physics and Biology 12 start with Class 11 chapters.
- About 15 open Robo assignments and 15 portion entries point at retired topics, so teachers need to reassign them.

Related: [School curriculum agent](pilvidya-school-curriculum-agent.md), [Robo Teacher](pilvidya-robo-teacher.md).
