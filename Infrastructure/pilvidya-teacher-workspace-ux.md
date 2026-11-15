# aividya — Teacher workspace UX (UAT, feat/chat-simulations 104a20c9)

The teacher workspace is organized around a daily teaching loop rather than a long catalogue of screens. This is a frontend-only release; it adds no tables, migrations, or new RPC contracts.

## P0 — start with today's work

- `/teacher` opens **My Day**. `/teacher/today` remains a supported direct route.
- My Day shows the current or next period, register completion, pending homework/marks/doubts, class-teacher registers, and a first recommended action.
- The teacher sidebar is grouped as **Today**, **Classes**, **Plan & teach**, **Assess & improve**, **Growth & support**, **School**, and **More**.
- **Insights** replaces the visible legacy **Dashboard** label. The legacy `/teacher#analytics` destination remains in the route catalogue but is hidden from the sidebar so old links and plan keys continue to work.
- School Admin and Fees are hidden for ordinary teaching staff. School leaders and authorised accounts/finance staff retain those entries.

## P1 — close the daily loop

- The header has one global **Create** menu for homework, tests, lessons, Teach Mode, and My Class.
- My Class shows student count, attention count, attendance risk, missing-homework count, filters for follow-up cohorts, and links to attendance, homework, and assessments.
- Doubt Desk sorts waiting questions oldest first, shows waiting/answered counts and age, preserves the AI answer for context, and has actionable error and empty states.

## P2 — make planning and teaching contextual

- My Lessons opens with all classes and subjects for the selected board; it no longer silently assumes Class 12 and Mathematics.
- Creating a lesson requires an explicit class and subject, followed by title, topic, and subtopic. The existing draft → approve → publish workflow is unchanged.
- Navigation places Curriculum Mapping, My Lessons, Teach Mode, and Portion Tracker together under **Plan & teach**. Assessments, Exams & Marks, Homework, Worksheets, and Test Series are together under **Assess & improve**.

## P3 — give teachers a reason to return

- My Growth has direct next actions to open a class or practise a teaching skill.
- Teacher Development shows **Continue where you stopped** for an unfinished course and keeps certificate progress intact.
- Copy is framed as a private weekly review against the teacher's own previous period; teachers are not ranked against colleagues.

## Compatibility and verification

- Existing hashes, menu keys, plan gates, and direct teacher routes remain supported.
- UAT release verification: `eduspeakreact:104a20c9`, public page HTTP 200, chunk manifest version `104a20c9`, no DEV pluginlive URLs in the served bundle.
- Focused frontend verification before release: 40 teacher/navigation tests passed, TypeScript passed, ESLint had no errors.

