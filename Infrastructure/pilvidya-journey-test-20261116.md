# PilVidya (aividya) — 5-journey UAT test and fixes (2026-11-16)

LIVE on UAT `d5d1e328` (`eduspeak-india` branch `feat/chat-simulations`). PROD: not deployed.

## Behaviour now
- **Student pages need a sign-in.** Every `/student` and `/student/...` route goes through `StudentPathGuard` (applied in `AppLayout`): a signed-out visitor — including browser Back after Logout — is sent to `/student-entry`; a parent goes to `/parent`, teacher/principal to their home; admins can still preview. Before, `/student/homework` and `/student/fees` rendered the shell for anyone and queried with an empty student id.
- **Library is scoped to the School Operations school** for platform admins too (books by `school_id`; loans and reservations through their book). Before, an admin who switched to School B still saw School A's catalogue (admins pass RLS for every school).
- **Parent–teacher chat** refreshes quietly every 20 s when the realtime channel fails. The PilVidya UAT self-hosted stack has **no realtime container** (websocket 501), so this fallback is what keeps chats current on UAT.
- **Chat simulations:** assigning shows "Simulation assigned"; assigning the same class/section again (active, whole-class) asks for confirmation first.
- **Transport:** empty state when a school has no routes, labelled inputs, load/delete errors shown, confirm before deleting a route.
- `my_plan` / `my_school_branding` are not called when signed out (removed 401s on login pages).

## Test kits (~/pilvidya-checks)
- Crawls: `student-9820065335/crawl.cjs` (21 menus), `teacher-jy1/crawl.cjs` (34), `principal-demo/crawl.cjs` (34, principal@pilvidya.in), `parent-9820065336/crawl-areas.cjs` (5 areas × 19 tabs — parent has no sidebar), `admin-prakash/crawl.cjs` (64), `school-ops/ops-crawl.cjs` (WHO=principal, 48 tools).
- Flows: student 18, teacher 15, parent 10, admin 9, `school-ops/ops-e2e.cjs` (24 checks, School A/B isolation), `school-ops/principal-ui.cjs`.
- After student flows reset assignment `98200653-5335-4d05-9000-000000005003` to pending (F1 submits it). Cleanup: `teacher-jy1/cleanup.sql`, `parent-9820065336/cleanup.sql`, `school-ops/cleanup-uat.sh` (run on the UAT box).
