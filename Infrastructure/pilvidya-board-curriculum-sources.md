# PilVidya (aividya) — Board curriculum: official sources

Status as of 2026-11-17: live on UAT (`73caac86`, branch `feat/chat-simulations`). Source file `supabase/seed/official_curriculum_2026_27_sources.json` and generator `official_curriculum_2026_27_topics.py`; both were renamed from `cbse_2026_27_*`. The latest migration is `20261203030000_official_curriculum_topics_languages_icse.sql`. There is no PilVidya PROD deployment.

## Where a student's subjects and topics come from

- Global topics live in `curriculum_topics` (`is_global = true`, keyed by `board`, `class_level`, `subject`).
- A school's own rows (`school_id`) add to them. Examples: the state language (Tamil for a Tamil Nadu school, from the TN textbook corporation), and books published through the school curriculum agent (`build_id`).
- Robo Teacher, Portion Tracker, Worksheets, Robo Classes and AI Coach list whatever these rows contain for the student's board and class.
- My Curriculum (`/student/curriculum`) also adds generic "NEP 2020 default" topics from `nep2020DefaultMapping.ts`. It now does this **only for subjects that have no verified source**. A subject with any `textbook_verified` row or a school build shows only those rows.

## CBSE Classes 3-12, 2026-27 (official)

- Source file `supabase/seed/cbse_2026_27_sources.json` holds 86 books and 763 chapters, each with its official link:
  - NCERT textbooks (`https://ncert.nic.in/textbook.php?<code>`, contents pages marked "Reprint 2026-27"): Maths, Science, Social Science and English for Classes 6-10, and for Classes 11-12 English (Hornbill, Snapshots, Flamingo, Vistas), Maths, Physics, Chemistry, Biology, Accountancy, Business Studies, Economics, Geography, History, Political Science, Sociology, Psychology, Computer Science and Informatics Practices. This includes the new Class 6-8 books (Ganita Prakash, Curiosity, Exploring Society, Poorvi) and the new Class 9 books (Ganita Manjari, Exploration, Kaveri, Understanding Society).
  - CBSE Computational Thinking & AI student handbooks for Classes 3-8 (`cbseacademic.nic.in/web_material/CurriculumMain27/CTAI_Pri<n>SH_2026-27.pdf`).
- Generator `supabase/seed/cbse_2026_27_topics.py` (with `--check`) produces the migrations `20261203010000_cbse_2026_27_official_topics.sql` (Classes 3-10) and `20261203020000_cbse_2026_27_official_topics_11_12.sql` (the full regenerated set, with Classes 11-12 added). The migration is data only and idempotent:
  - each book is upserted into `curriculum_sources` as `source_key = cbse-2026-27-<code>`;
  - rows whose topic equals a chapter are kept, with textbook, chapter, `academic_year 2026-27`, `nep_stage` and `textbook_verified` set;
  - all other global CBSE rows of a covered class and subject are retired (`board = 'cbse-retired'`, `is_global = false`). They are never deleted, because 18 tables point at topics (progress, Robo sessions and assignments, portions, sims);
  - missing chapters are inserted.
- UAT runs: first run (Classes 3-10) kept 10, retired 265 and inserted 376. Second run (Classes 11-12) retired 118 more. Total: 763 official rows, 383 retired. Backups are in `~/pilvidya-checks/curriculum-source/backups/` (`cbse_topics_pre_*.csv`, `cbse_topics_pre1112_*.csv`).
- Rollback: `UPDATE curriculum_topics SET board='cbse', is_global=true WHERE board='cbse-retired'`, then delete the inserted 2026-27 rows.
- Before this fix, Class 11 Maths held the Class 9 list and Class 12 Physics, Chemistry and Biology repeated Class 11 chapters. Global CBSE (and ICSE/State) Classes 6-10 Maths, Science and Social held the old NCERT **Class 9** syllabus copied into every class. English was 6 placeholders, and CT & AI had no topics while the card said "Computer Science".

## Added 2026-11-17 (round 3): 132 books, 1235 chapters

- **Hindi, Classes 1-12** (NCERT): Sarangi 1-2, Veena 3-5, Malhar 6-8, Ganga 9, Kshitij 2 and Kritika 2 (Hindi Course A) for 10, Aroh and Vitan (Hindi Core) for 11-12.
- **Sanskrit, Classes 6-12** (NCERT): Deepakam 6-8, Sharada 9, Shemushi 10, Bhaswati (Core) 11-12.
- Devanagari topics are stored in Unicode with `medium` Hindi or Sanskrit.
  - pdftotext garbles these books, so they are read with PyMuPDF (`curriculum-source/fetch_contents_u.py`).
  - The older books (Kshitij, Aroh, Vitan, Shemushi, Bhaswati) use the legacy Kruti Dev font, so their titles were decoded by hand.
  - The Malhar 7 title list was checked against a rendered image of its contents page.
- **CBSE 11-12 AI**: subject `ai`, from the CBSE skill curriculum 843 Part B (`skilleducation.cbseit.in/web_material/curriculums/2026-2027/srsec/843-AI-XI.pdf` and `-XII.pdf`). NCERT has no AI book.
- **CBSE PE**: Class 11 from the NCERT book Health and Physical Education (`kehp1`). Class 12 from the CBSE Physical Education curriculum units (NCERT has no Class 12 book).
- **CBSE Fine Art 11-12**: subject `art_education`, NCERT An Introduction to Indian Art, Parts I and II.
- **CBSE Philosophy** is retired and dropped from the CBSE subject list: CBSE and NCERT have no Philosophy course.
- **ICSE 9-10**: from CISCE "Regulations and Syllabuses ICSE 2027" (`cisce.org/wp-content/uploads/2025/03/*.pdf`), the latest published; there is no 2028 page yet, so its Class IX section is used for Class 9.
  - Subjects: Maths, Physics, Chemistry, Biology, History & Civics (subject `history`, topics prefixed Civics: or History:), Geography, Economics, Computer Applications (subject `computer`), and English (Appendix I prescribed texts: Julius Caesar, Treasure Chest).
  - The ICSE 9-10 subject list now shows the separate sciences and humanities, not combined Science and Social.
  - cisce.org is behind Cloudflare: use a real browser (`curriculum-source/probe/cisce*.cjs`); its PDFs download with curl.
- **Retired with no official source**: ICSE 6-8 (CISCE publishes no Class 6-8 syllabus) and State 6-10. These were all the copied CBSE Class 9 list.
- **Tamil Nadu State board books**: official source TN SCERT `https://scert.tnschools.gov.in/textbook` (EMIS e-learn list API, captured in `curriculum-source/tn/std*.json` for English-medium Classes 6-10).
  - The download sits behind a human arithmetic check, so it is not automated.
  - To add State topics, download those PDFs manually, or have schools upload them through Curriculum Setup (school curriculum agent).
  - The site also has Tamil books for CBSE schools (for example `1st_Std_Tamil_CBSE.pdf`). That is the right source for the Tamil language subject, whose school rows are still generic placeholders.
- UAT: retired rows: cbse 408, icse 271, state 275. Backup: `curriculum-source/backups/global_topics_pre_lang_icse_*.csv`. Checks with `robo-ui-senior.cjs` all pass: CBSE 6 Hindi, Sanskrit and Maths; CBSE 12 AI, Hindi and PE; ICSE 10 Physics, Maths, History and English.

## Subjects

- `ctai` "Computational Thinking & AI" replaces `computer` and `ai` for **CBSE Classes 3-8** (`subjectMatrix.ts`). ICSE, State and IB are unchanged.
- `LANGUAGE_SUBJECT_IDS` (`constants.ts`) lists the language subjects. Robo Teacher's subject picker has a **Subjects** group and a **Languages** group (English, Tamil, Hindi…), and English is labelled "English" there.

## Fetching sources

- `ncert.nic.in` serves an incomplete TLS chain, so use `curl -k` and check the content. `cbseacademic.nic.in` works normally.
- Kit: `~/pilvidya-checks/curriculum-source/` (`fetch_contents.sh <codes>` keeps only the contents text, `contents/*.txt`). The NCERT book codes come from the JS on `textbook.php`.
- Hindi and Sanskrit: use `fetch_contents_u.py` (PyMuPDF); decode Kruti Dev books by hand and check them against a rendered page image.

## Checks

- Vitest: `cbseOfficialTopics.test.ts` (official links only, coverage, Class 6 is not the Class 9 list, no duplicates) and `subjectMatrix.boards.test.ts` (CBSE 3-8 has `ctai`).
- UAT: `~/pilvidya-checks/curriculum-source/robo-ui.cjs` (student 9820065335, CBSE Class 6). It checks groups, topics per subject and My Curriculum counts: 16/16 on `8e5f4172`. `robo-ui-senior.cjs <mobile> "Subject=first chapter"…` checks Classes 11-12: 9820000011 (Class 11) and 9820000012 (Class 12) both 4/4.

## Open

- State boards (Classes 6-10) have no global topics, and State 11-12 rows are still copies of the NCERT lists. Tamil Nadu needs its SCERT books, downloaded manually or uploaded per school. ICSE 6-8 has no public CISCE syllabus, so schools need to upload their books.
- About 15 open Robo assignments and 15 portion entries point at retired topics, so teachers need to reassign them.

Related: [School curriculum agent](pilvidya-school-curriculum-agent.md), [Robo Teacher](pilvidya-robo-teacher.md).
