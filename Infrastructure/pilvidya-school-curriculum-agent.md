# PilVidya (aividya) — School curriculum agent

LIVE on UAT 2026-11-17 (`eduspeak-india` branch `feat/chat-simulations`, `66192661` + fixes `ac70da77`, `6ab4d912`). PROD: not deployed.

## What it does
**School Operations → Curriculum Setup** (principal of the school, or a platform admin for the school picked in School Operations;
teachers do not see it — server check `can_manage_school_curriculum(school_id)`):
1. Add the approved textbook: board (CBSE/ICSE/State + state code/IB), academic year (`2026-27`), class (NEP 2020 stage shown:
   Foundational 1–2, Preparatory 3–5, Middle 6–8, Secondary 9–12), medium, subject (subject ids already used for that board/class),
   title, authors, publisher, edition, ISBN, licence (private to the school unless "openly licensed"). PDF ≤ 50 MB, stored at
   `pilvidya/curriculum-books/<school>/<sha256>.pdf`.
2. **Duplicate check (book):** same file hash, or same title + edition + class + subject + medium + year → existing book returned.
3. **Read:** page text via unpdf. Scanned PDFs (< 100 chars/page) and **legacy Indic fonts** (text not in the medium's script, e.g.
   Kruti Dev Hindi NCERT) are read by the AI from page images (PDF slices).
4. **Draft** (one bounded step per request, client loops `step`): ≤ 10 pages / 18k chars per call → chapters, topics, subtopics,
   learning outcomes, cited pages, one verbatim quote. Contents page → `toc`.
5. **Self-repair:** chapters in the contents with no topics are re-read once (pages found by the chapter title). Topics filed under a
   chapter number the contents lack but titled like a contents chapter are moved there (Gemini read "Aged (above 59 years)" as ch. 59).
6. **Hallucination checks:** quote must be on a cited page (±1, deterministic; missing = error, blocks publish; reworded = warning);
   a **second AI from another provider** checks every doubtful topic + 8 sampled ones, batched so each topic travels with its pages
   (unsupported = error, or warning if the exact quote was found); coverage vs contents.
7. **Duplicate check (topics):** same topic in two chapters; already published from another textbook for the same scope.
8. **Review:** chapters/topics with pages, quote, issues, "show pages" (page text); edit a title, hold a topic back. Publish is
   blocked while any non-held topic has an error.
9. **Publish** (`publish_school_curriculum_build`, atomic): one `curriculum_topics` row per topic/subtopic with `textbook_*`,
   `academic_year`, `medium`, `nep_stage`, `learning_outcomes`, `build_id`; rows matching the previous version are updated in place
   (ids/progress kept, `locked` rows keep their text), others removed **unless in use** (progress, Robo assignments, portion plan,
   lessons). One published version per school + board + class + subject + medium; older ones archived.
10. **Delete / regenerate:** draft → deleted; published → unpublish (archived, in-use topics kept); regenerate = new version with a
    diff (added/removed/changed); leader edits carried over. A book with a published version cannot be deleted.
11. **Students/teachers:** a subject published from the school's textbook replaces the global topics (and generated lessons/videos
    for other topics) of that subject for that school (`preferSchoolCurriculum`).

## Data
`school_textbooks`, `school_curriculum_builds`, `school_curriculum_build_items` — read for the school's staff
(`ops_school_access` / `can_manage_school_curriculum`), no client writes (edge function with service role after the check).
Migration `supabase/migrations/20261201010000_school_curriculum_agent.sql`; DB-Scripts `EduSpeak Postgres Migration/…__pilvidya_school_curriculum_agent.sql`.

## AI (LiteLLM gateway only)
`pl/school-curriculum-extract` gemini-2.5-flash (thinking off) → gpt-6-luna, 45 s; `pl/school-curriculum-verify` gpt-5.4-mini →
gemini-2.5-flash, 40 s; key `aividya-app`. Calls go through the public UAT gateway path (≈60 s cut), hence one step per request.
Observed: 2–9 s per call; 76-page book drafted in ~90 s, 176-page book in ~95 s of calls.

## Checks
- Rules: `frontend/src/test/schoolCurriculumChecks.test.ts` (12 tests).
- AI harness without DB: `~/pilvidya-checks/curriculum-agent/harness.ts` (`INJECT=1` fabricated topic → `not_in_book`; `--fallback`).
  NCERT Class 6 Science (EN, 176 p): 16/16 chapters, 102 topics, 0 errors. Hindi NCERT (legacy font) read as images.
- UAT E2E: `e2e.mjs` (16 checks: duplicate, teacher refused, read, draft, edit/hold, publish, regenerate diff, edit kept, delete
  draft, book delete blocked) and `ui.cjs` (7 checks incl. student view) on PilVidya Test School A, NCERT Class 9 "Contemporary
  India" (QA-E2E edition) — left published there as sample data. NCERT's site TLS-fails from DEV/UAT; archive.org copies used.
- Variability: regenerating gives different topic granularity run to run — review the diff before publishing.
- Not yet: EPUB, per-medium student filter, NCF competency codes.
- Board-wide (global) topics and their official sources: [pilvidya-board-curriculum-sources.md](pilvidya-board-curriculum-sources.md).
