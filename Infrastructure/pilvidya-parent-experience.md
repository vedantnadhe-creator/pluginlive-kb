# aividya — Parent experience (UAT, feat/chat-simulations ce01ad9f)

The parent portal is a calm, child-first shell for a linked parent or guardian. This release is frontend-only: no
database migration was added. Existing parent session, child-link, plan-access, RLS and edge-function boundaries remain
the source of truth.

## Navigation

`ParentNavigation` groups the parent menus into five areas:

- **Today**: Today and Alerts.
- **Learning & growth**: This Week, Report Cards, Whole-Child Card, Progress overview, Support signals, Learning
  support, and Language progress.
- **School**: Messages, News, Upcoming, Attendance, and Meetings.
- **Money & transport**: Fees and Transport.
- **Family & settings**: Wellbeing, Alert Preferences, and Family & privacy. Family & privacy exports the linked child's data (parent session required) and files erasure requests for the admin queue; see [pilvidya-dpdp-compliance.md](pilvidya-dpdp-compliance.md).

The tab configuration lives in `frontend/src/components/parent/parentNavigationConfig.ts`; the shell is rendered by
`ParentDashboard` and remains compatible with the existing `/parent#<tab>` links.

## Today home

The parent home is `ParentTodayView`. It starts with the selected child’s name, class, board and school, then shows:

- **Needs your attention**: at most three actionable items from today’s attendance, open homework, fee reminders,
  unread school updates, and due learning revisions. Each item opens the relevant parent tab.
- **Quick read**: today’s attendance state, latest result, and open task count.
- **Today’s AI Digest**: a short summary grounded in school and learning activity; it states when the update is not
  ready rather than inventing a result.
- **Try this together**: a small family learning prompt based on the child’s subject signal.

Attendance that has not been marked is explicitly shown as pending, rather than silently treated as absent. Empty
attention state is a positive “You’re all caught up” state.

## Session and data behavior

- A parent can select among all verified linked children; digest, results and schedule reload for the active child.
- Pending child links remain reviewable before they enter the verified child list.
- A transient bootstrap/network failure keeps the stored parent session and shows a retryable state. Only an invalid or
  expired server session causes the normal sign-in recovery path.
- Notifications and today’s attendance refresh through the parent API and subscribe to relevant realtime changes.
- Notification read state is updated optimistically and persisted through the parent API.
- Plan access controls parent tabs. A disabled feature opens the existing upgrade prompt instead of rendering an empty
  or misleading page.
- Admin View as Parent uses the same shell in read-only preview mode; it does not create a parent login session.

## Parent-facing retention intent

The home prioritises a small number of useful actions instead of a long dashboard: check what happened today, resolve
one immediate issue, understand progress, and choose a simple way to support the child. The UI should preserve facts,
timestamps and school-provided data before AI explanation.

## Verification

Focused frontend checks for ce01ad9f:

- `parentExperience.test.tsx`: five navigation groups, no duplicate destinations, actionable attendance and family
  learning prompt.
- `parentSessionBehavior.regression.test.ts`: transient failure recovery, invalid-session handling, display-name
  persistence, canonical role keys, and parent navigation wiring.
- `commercialPlanMenus.regression.test.ts`: parent plan-menu gating remains intact.

The focused suite passed 13 tests before the UAT push. There is no aividya PROD deployment.

The first UAT smoke after 701c4b8f found a missing `CalendarCheck2` import in the authenticated parent home. The
one-line fix is included in ce01ad9f; the parent login smoke must be rerun after deployment.
