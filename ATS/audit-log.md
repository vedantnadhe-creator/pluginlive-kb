# Audit log (Admin / Corporate / Institute)

> An append-only audit trail shared by all three portals, each scoped to its own
> tenant. Admin sees it as **Audit Log**; Corporate and Institute see it as
> **Activity Log**.
>
> **Status:** DEV + UAT (2026-08-07; entity/actor names and onboarding events,
> dynamic entity filter and the System Config safety net 2026-08-18; student
> module coverage, the Who-column fixes, row summaries and the readable details
> panel 2026-08-19). PROD pending.
>
> Note on the 2026-08-19 promotion: `admin-node` and `admin-react` were taken to
> UAT as **audit-only commits, not a Development merge**. Both branches were
> carrying in-flight "Mix & Match float as one assessment" work whose halves
> were not ready together, and merging would have shipped a frontend against a
> backend that was not there. Verified afterwards that the UAT tips changed one
> file (`auditActions.js`) and two (`modules/AuditLog/`) respectively.

## Where the data lives

One `audit` schema in the **same database** as the service that writes to it —
not a separate database. The table is `audit.audit_logs`, partitioned monthly on
`occurred_at`, so the primary key is composite (`audit_log_id`, `occurred_at`).

DEV and UAT both have the partition set `audit_logs_2026_08` … `_2026_11` plus
`audit_logs_default`.

Rows are never updated or deleted — a `BEFORE UPDATE OR DELETE` trigger enforces
this at the database level.

> **Checking whether the schema exists:** `information_schema.tables` is
> privilege-filtered, and the read-only reporting roles have no `USAGE` on the
> `audit` schema — so the tables look *missing* through `ro-query.sh`. Query
> `pg_class`/`pg_namespace` instead, which is not filtered:
>
> ```sql
> select c.relname, c.relkind from pg_class c
> join pg_namespace n on n.oid = c.relnamespace
> where n.nspname = 'audit' and c.relkind in ('r','p');
> ```

## Connection string

Each service builds its own audit client. `DATABASE_URL_AUDIT` is read first,
and **when unset it is derived** from that service's own database URL with
`schema=audit&connection_limit=2&pool_timeout=10`:

| Service | Derives from |
|---|---|
| `admin-node` | `DATABASE_URL_ADMIN` |
| `corporate-node` | `DATABASE_URL` |
| `institute-node` | `DATABASE_URL` |
| `student-node` | `DATABASE_URL_STUDENT` |
| `user-management-node` | `DATABASE_URL` |

So an environment that forgets the variable still audits into its **own**
database rather than silently falling back to a hardcoded one. As of
2026-08-07 no UAT service sets `DATABASE_URL_AUDIT` explicitly — they all
derive it, and that is fine. The small pool is deliberate: auditing must never
starve the request path of connections.

## Endpoints

All three services expose the same routes, all requiring a JWT:

| Route | Notes |
|---|---|
| `GET /audit/logs` | Cursor-paginated (`cursorOccurredAt` + `cursorId`) |
| `GET /audit/actions` | The action taxonomy, so the UI never hardcodes it |
| `GET /audit/entity-types` | `admin-node` only. Distinct `entity_type` values **present in the table** |
| `GET /audit/logs/export` | XLSX; capped, with `X-Audit-Row-Count` and `X-Audit-Truncated` headers |

**Tenant scope comes from the JWT, never from a request param.** Corporate reads
`corporate_id` and Institute reads `institute_id` off the token. This is
deliberately different from the rest of these services, where handlers take
`instituteCampusId` from the URL — for an audit trail that would let any
authenticated user read another tenant's history by editing the path. A token
with no tenant scope gets `403`, not an unfiltered list.

### Why the Entity filter is data-driven, not a taxonomy

The Admin **Entity** dropdown used to be a hardcoded list. It offered types
nothing had ever written, so picking one returned an empty page and the filter
read as broken. `GET /audit/entity-types` returns
`SELECT DISTINCT entity_type ... WHERE entity_type IS NOT NULL ORDER BY 1`, so
every option is guaranteed to have rows behind it.

On UAT (2026-08-18) that is: `assessment`, `audit_log`, `campus`, `course`,
`job_role`, `subscription`, `user`.

The trade-off is deliberate: a brand-new entity type does not appear in the
filter until its first row exists. That is the correct behaviour for a filter
over an append-only table — the dropdown describes the data, not the code.

## Who and What are shown as names, not ids

The table stores **ids** — an id is the record of fact, and an audit row must
never appear to change because someone later renamed a role or edited a profile.
Names are resolved when a page is **rendered**, which also means existing rows
gain names with no backfill.

| Column | Source | Where |
|---|---|---|
| **Who** (`actorName`) | one batched read of `user_management.users` per page | `admin-node` only (`app/models/AuditActor.js`) |
| **Entity** (`entityLabel`) | one batched read per entity type per page | all three services (`app/models/AuditEntity.js`) |

### Who: an id must never reach the screen

Three separate faults each surfaced as a raw id in the Who column, all fixed on
2026-08-19 and all found by querying the UAT trail rather than reading code:

1. **Rows with no actor at all, shown as "Unknown".** A route only runs
   `verifyToken` if it sets `isPrivate: true`. Where it does not, `setAuditActor`
   is never called and the row lands anonymous. Two separate cases hit this:
   `admin-node`'s `subscription.assigned` (37 routes in `app/routes/assessment.js`
   have `isPrivate` *commented out*), and `institute-node`'s
   `system_config.changed` from
   `PUT /institutes/instituteCampus/:instituteCampusId/course/:courseId`, which
   never had the flag.

   **All four services** now call `setAuditActorFromRequest` from their
   `onRequest` hook, which decodes the token when one is sent. It deliberately
   **rejects nothing** — whether a route enforces auth stays the route's
   decision, and this is only about attribution. Those routes are still
   unauthenticated; that is a separate, open issue.

   Because the table is append-only, **rows written before the fix keep reading
   "Unknown" forever**. There is no backfill and there should not be: inventing
   an actor for a row that never recorded one is exactly the kind of thing an
   audit log must not do. Only new rows carry the actor.
2. **22 rows carried an actor id present in no user table**
   (`63e4de1011d6db2f8d400580`, role `system`) — later identified as the shared
   **service-account** token, not a deleted user; see the service-accounts
   section below. `AuditActor.findNamesByIds` now
   searches `admin.admin_users` as well as `user_management.users`, with
   user_management winning a collision since that is where login tokens are
   minted.
3. **An unresolved actor rendered as the raw id.** `toActorDisplayName` now
   returns a label instead: the resolved name, else the email, else `System` for
   a `system` role, else `Unknown user`, else `Unknown`. A deleted user is
   deliberately **not** called "System" — that would assert something false about
   who acted, and an audit row must never be more confident than its evidence.

`admin-react` renders `actorName` and keeps the id in a tooltip, so the exact
identifier is still one hover away for incident work. Verified on UAT: 0 of 60
rows display a raw id.

Note that login tokens carry `role` and `_id` and **no email**, which is why
`actor_email` is null on essentially every row — the name lookup is the only
thing standing between a reader and a hex string.

The entity resolver only fills rows whose `entity_label` is **null**. A label a
call site captured at write time is what the entity was called at the time and
always wins.

What each service can name (2026-08-18):

| Service | Entity types resolved |
|---|---|
| `admin-node` | assessment, subscription (college *or* company), corporate, institute, job_role, student_list, student |
| `corporate-node` | job_role, drive |
| `institute-node` | job_role, drive, institute, campus |

Notes that matter when adding a type:

- The masters are **not consistent about id type** — `institute.institutes`,
  `corporate.corporates` and `corporate.job_roles` key on `text`, while
  `assessment.assessment_institute_map` and `assessment.student_lists` key on
  `uuid`. Match the column's own type or the query either errors (`operator does
  not exist: text = uuid`) or stops using the index.
- A subscription row stores only the **subscriber id**, and that is a college or
  a company depending on the screen, so both masters are searched.
- A drive has no name of its own; it is labelled from
  `institute."institute_campus_jobRole_drive_map"` as `role_name — drive #N`.
- Resolution **never throws**. A failed lookup leaves the label null and the UI
  falls back to the id, because the audit log is the screen people reach for
  when other things are broken.
- The frontends render `entityLabel || entityId`, so adding a type is a backend
  change only.

On UAT this took the trail from 74 unlabelled rows to 172 of 173 labelled; the
one that stays blank is `audit_log.exported`, which has no entity.

## Portal attribution: who did it, not who wrote it

`portal` records the portal the action was **initiated from**, not the service
that wrote the row. Several Admin screens are served by other services, so those
call sites pass `portal: PORTALS.ADMIN` explicitly and override the service
default:

| Action | Written by | Filed under |
|---|---|---|
| `corporate.created` | `corporate-node` | ADMIN |
| `institute.created` | `institute-node` | ADMIN |
| `degree.created`, `department.created` | `institute-node` | ADMIN |
| `course.created` | `institute-node` | INSTITUTE |

`tenantId` stays the new company/college, so the tenant's own Activity Log shows
its creation too. There is **one row per action** — the Admin trail is unscoped
and reads every portal's rows, so a second copy would only double-count in a
table where nothing can be corrected later.

Onboarding events were added on 2026-08-18: `corporate.created` was not audited
anywhere before that, and `institute.created` was filed under INSTITUTE and read
`entityLabel` from an `instituteName` field that neither the created record nor
the request body has, so it stored a null label. The corporate row is written
only after the admin user is created, because the handler deletes the corporate
when that step fails.

## The student module: audited by route hook, with two exclusion lists

`student-node` joined the trail on 2026-08-19. It is a **writer only** — it has
no `/audit/*` routes, because the Admin portal already reads every service's
rows out of the shared `audit` schema, and a student-facing read path over a
cross-tenant table would be a liability.

Coverage comes from an `onResponse` hook (`app/helpers/studentAudit.js`), for
the same reason System Config does: 182 hand-wired `audit()` calls would leave
each new endpoint silently unaudited until somebody remembered it.

**A blanket "record every POST/PUT/PATCH/DELETE" rule is wrong here**, and this
is the part to understand before touching the file. 80 of the 182 mutating
routes are not writes:

- **Reads sent as POST/PUT.** `/students/details/list`, `/students/skills/list`,
  `/appliedstudents/list/:roleId`, `/students/count/:instituteCampusId` and every
  `.../export` route are queries with a request body. Recording them as changes
  buries real edits under search traffic.
- **Assessment delivery telemetry.** Per-question autosave, proctoring frames,
  media uploads, score recomputation and backfills fire many times per attempt.
  They belong in assessment reporting, not in a log read to answer "who changed
  this record?".

That leaves **102 audited routes**. Anything matching neither list is audited,
so the maintenance burden is inverted: you exclude noise rather than remember to
include signal.

Only writes to the student record itself get a named action — `student.created`,
`student.updated`, `student.deleted`. Everything else is `student_record.changed`
with `metadata.route` and `metadata.area` carrying the detail, because a filter
dropdown with forty near-identical entries is not one anybody uses.
`STUDENT_RECORD_ROUTES` lists the record routes **explicitly**: matching on shape
(`/students/<anything>`) also catches `/students/map-with-drive` and
`/students/saveBehaviourSpecialisation`, which are not student-record writes.

Two things differ from every other service:

- **`portal` is not a service constant.** All four portals call `student-node` —
  an institute TPO, a corporate recruiter, an admin and the student — so it is
  derived per request from the token by `portalFromUser`: `student_id` → STUDENT,
  `corporate_id` → CORPORATE, `institute_id` → INSTITUTE, none of them → ADMIN.
  A student's own token omits `institute_id`, so their rows carry no `tenantId`;
  the Admin trail is unscoped and still shows them.
- **The audit client is required lazily, inside a try/catch.**
  `prisma/generated-audit` is gitignored and built into the image, so a
  top-level require would take the whole service down on any box where that step
  has not run. Losing the trail is bad; failing to boot because of it is worse.

For a row pointing at a real student the hook sends **no** `entityLabel`, so the
Admin trail resolves the id to the student's name. The area name ("Student
resume", "Offer") is only used for the generic rows, which point at no single
named record.

## user-management-node: locations, accounts and authentication

Added 2026-08-20. Until then this service had **no audit wiring at all** — 69
mutating routes, none recorded — which is why *editing a Location in Admin →
System Configuration never appeared in the Audit Log*. The location masters live
here, not in institute-node where the System Config hook runs, so the request
never reached an audited service. Location was simply the one that got noticed.

### Two hooks, and why they cannot be one

| Hook | Records | Rule |
|---|---|---|
| `userAudit` | 26 CRUD routes | successful (2xx) mutations only |
| `authAudit` | 11 auth routes | **success *and* failure** |

The split is load-bearing. The CRUD hook ignores non-2xx because a rejected edit
changed nothing. For authentication the opposite holds: **a failed sign-in is
the event most worth having**, and a 2xx-only rule throws exactly that away. So
`authAudit` reads the status code and files the two outcomes as different
actions (`auth.signed_in` / `auth.sign_in_failed`), because that is how a reader
filters them.

`userAudit` excludes everything `isAuthRoute` matches, and a test asserts the
two sets stay disjoint — an append-only table cannot be de-duplicated after the
fact.

### The actor on a failed sign-in

There is no token, so no authenticated user. The **email that was attempted** is
in the body and is stored as `actorEmail`, which the Admin trail resolves to a
name at render time. It is never proof the account holder acted; it is what the
request claimed, which is what an audit log should store.

`metadata.payload` is explicitly **null** on every auth route. `AuditService`
would redact anything password-shaped anyway, but the safest payload on a
credentials endpoint is no payload.

### What is excluded, and why

43 of the 69 routes are not audited, in three groups:

- **Reads sent as POST** — `/users/by-login-email` is a lookup with a body;
  `/signedURL`, `/uploadSignedURL`, `/download` mint object-storage URLs.
- **Message delivery** — email, WhatsApp, in-app notifications, reinvitations
  and reminders fire in bulk and are already tracked by the delivery pipeline.
- **Presence** — `heartbeat` / `offline` are per-tab telemetry.

Two traps the route review caught before this shipped, both worth remembering
when editing the patterns:

- A single `/notification/` pattern also matched
  `/user/:userId/notification-preference`, silently excluding **a setting the
  user changed**. The pattern now anchors on the notification *noun*.
- `removeGoogleCalendarIntigration` contains `GoogleCalendar`, so the disconnect
  was being described as a connect. Order the specific pattern first.

### The Dockerfile change is load-bearing in both directions

```dockerfile
# stage 1
RUN npm ci --omit=dev && npx prisma generate \
 && npx prisma generate --schema=./prisma/schema-audit.prisma
# stage 2
COPY . .
COPY --from=deps /app/prisma/generated-audit ./prisma/generated-audit
```

Stage 2 copies only `node_modules` from `deps`, so `generated-audit` has to be
carried across **explicitly** or it is missing from the image entirely. And that
copy must come **after** `COPY . .`, or the build context overwrites it. The
directory is gitignored, so the context cannot supply it either way.

The audit client is required lazily inside a try/catch: its output is built at
image time, and a top-level require would take the service down on any box where
that step has not run — and this service owns sign-in.

## Which door a student came through

Five routes create a student, and "was this typed in, uploaded, or imported?" is
the question people ask first when a record looks wrong. That is a property of
the **action**, not of the actor, so the action carries it and WHO keeps meaning
who.

| Route | Auth | Action | Channel |
|---|---|---|---|
| `POST /students/:instituteCampusId/:courseId` | `isPrivate` | `student.created` | typed in at the institute |
| `POST /students/bulkcreate` | `isPrivate` | `student.bulk_created` | bulk upload |
| `POST /students/tally/create` | **none** | `student.imported` | Tally form |
| `POST /students/create-full` | `privateByKey` | `student.imported` | form normalization |
| `POST /students` | **none** | `student.self_registered` | public sign-up |

Both imports share one action because they are two hops of the same channel —
the Tally form feeds normalization, which calls `create-full`. The summary says
which hop.

**The Action chip must not repeat that guess** (fixed 2026-08-20, `3dde5dce`).
Because both routes raise `student.imported`, the chip labelled every such row
`(Tally form)` — including rows whose own summary read "from form
normalization", so the two halves of one row contradicted each other. The chip
no longer names a channel; the summary is the single place that says which hop
it was.

### Naming the submitter on a route with no token

`create-full` is authenticated by a shared `auth-key` that carries **no
identity**, and the Tally and public routes by nothing at all. There is no JWT
to name an actor from — but those requests are not anonymous. The person who
filled the form is in the payload, and they are the honest answer to "who did
this?".

`identityFrom` (in `studentAuditRoutes.js`) pulls it out — the Tally route posts
`{ email, firstName }` flat, `create-full` and the public sign-up nest the same
fields under `admin` — and a descriptor opts in with `actorFrom`. The submitted
**email becomes the row's actor**; `admin-node` then resolves it to a name at
render time via `AuditActor.findNamesByEmails`, which searches
`user_management.users` **and** `student.student_personal_profile`, because on
these routes the submitter is usually the student being created.

**Only the email is stored.** Names are resolved on read everywhere else in this
trail, so a name written into the row would be the one thing that could never be
corrected later. The spelling as submitted is kept in `metadata.submittedBy`.

`systemActor: true` remains the fallback for a payload with **no** identity at
all, filing the row as `portal: SYSTEM` / `actorRole: "system"` so it reads
**System** rather than "Unknown", which looks like a fault.

Both only apply when no real actor was captured — a signed-in person acting on
one of these routes still gets the credit.

The result on UAT:

| Payload | WHO | Role |
|---|---|---|
| submitter exists | their name, e.g. `r1 k1` | `Tally form` |
| submitter unknown | the email address | `Form normalization` |
| no email at all | `System` | `system` |

The channel still lives in the **action** (`student.imported`), not in WHO —
those answer different questions.

### A read that had been logging as a change

`POST /students/tpo/:instituteCampusId` is `getAllStudentsCount` — a count, with
no `count` anywhere in its path, so the read filter in `studentAudit.js` missed
it and it recorded as a state change. Now excluded explicitly. Worth remembering
when adding routes: **the read filter matches on path text, and this service
names several reads in ways that do not say "read"**.

## Assessment participation: taken, abandoned, never turned up

Three events, covering real and practice attempts alike — `is_practice` is
carried on the row, so practice attendance is the same query with one filter.

| Action | Written by | Volume on PROD |
|---|---|---|
| `assessment.submitted` | the submit routes | ~400–950 / month |
| `assessment.auto_submitted` | `markAutoSubmitted` | part of the above |
| `assessment.dropped` | the dropout sweep (`updateDropoutStatusCron`) | 840 all-time |
| `assessment.window_closed` | `script/assessmentWindowAudit.js`, hourly | one row per schedule |

Submitted and auto-submitted are deliberately **distinct actions**: in one the
candidate chose to finish, in the other the clock finished for them. Conflating
them would misreport what the candidate actually did.

### The descriptor opt-in

The submit routes sit inside the delivery surface `studentAudit.js` filters out
as telemetry, and that exclusion is still correct for autosave, proctoring
frames and media uploads. So `isAuditableRoute` now works like this: **a route
with an explicit descriptor is always audited, even inside the telemetry
surface.** Naming a route in `studentAuditRoutes.js` is how you say "this one is
an event, not noise". A submit happens once per attempt; the traffic around it
does not.

### Why non-attendance is one row per schedule, not one per absentee

This is the one thing in the trail that is **not an event** — nobody makes a
request when they fail to turn up — so it can only be observed when the window
shuts. That is what the hourly sweep does.

It writes **one row per schedule**, carrying counts (invited / taken / not taken
/ dropped / still in progress, plus the practice split) and a **capped sample**
of absentee ids. The reason is arithmetic:

```
PROD assessment_assigned_students:
  PENDING     330,692      ← "did not take"
  COMPLETED    19,421
  DROPOUT         840
```

A row per absentee would put a third of a million entries into a table holding a
few hundred, growing by tens of thousands each cycle, burying every real edit
underneath — the precise failure this trail exists to avoid. The full absentee
list stays a report against `assessment.assessment_assigned_students`, which is
indexed for it and is the right tool for a question about *state* rather than
about events.

**The sample cap is not cosmetic.** `AuditService.capJsonSize` replaces the
*entire* metadata object when it exceeds 32KB, so an uncapped list would have
cost the counts as well as the sample. Measured at 5,000 absentees the row is
752 bytes.

The sweep asks the trail whether it already recorded a schedule before writing,
because an append-only table cannot be corrected and a duplicate would be
permanent. Verified on DEV: first run recorded 50, second recorded 0 and skipped
50. Tunable via `AUDIT_WINDOW_LOOKBACK_HOURS` (default 48) and
`AUDIT_WINDOW_BATCH_LIMIT` (default 50); it runs at minute 7 of each hour,
alongside the dropout sweep in `script/scheduler.js`.

Both the sweep and the dropout rows are written as `portal: SYSTEM` with
`actorRole: "system"`. Nobody performed them — a deadline passed and a timer
noticed — and attributing them to a person would be a lie.

## Service accounts, and the id that was never a deleted user

The Admin trail showed **"System" for 58 of 99 rows**, which tells a reader only
that no human was involved. Both markers turned out to be **service accounts**:

| Actor id | Held by | Renders as |
|---|---|---|
| `63e4de1011d6db2f8d400580` | `AUTH_TOKEN` in **institute, corporate, student and auth** — one shared legacy token | *"Institute service"*, *"Student service"*, … |
| `admin-node-system` | `AUTH_TOKEN` in admin-node | *"Admin service"* |

Every backend keeps a long-lived JWT in `AUTH_TOKEN` whose payload is
`{"role":"system","_id":...}`, used for service-to-service calls and background
workers — `assignmentWorker` creates students through `StudentService` with
exactly this token. **No lookup was ever going to resolve them to a person.**

> `63e4de1011d6db2f8d400580` had looked like a *deleted user* for weeks, and was
> documented that way. It is not: it is a shared machine identity, which is
> precisely why it appears in no user table. To check one of these, decode the
> token rather than hunting the id in `user_management.users`:
> `docker exec <svc> sh -c 'grep -oE "eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+" /app/.env' | cut -d. -f2 | base64 -d`

The shared token cannot say *which* of the four services used it — but the audit
row's own `service` column can, so that is what the Who column renders.

`role === "system"` is the discriminator, and it is reliable: a person's token
carries their own role (`Admin`, `TPO`), never `system`.

**Rows with role `system` and no actor id keep reading "System".** Those are
written by the window-closure sweep and the dropout cron — the system observing
something, not a service account holding a token.

Result on UAT: 99 Admin rows, **0 bare "System"**, 0 raw ids.

## Every row leads with a sentence, including the hand-wired ones

Two families of row exist in this trail, and only one of them used to have a
headline:

| Family | Where the summary comes from |
|---|---|
| Route hooks — System Config, student module, user management | built from the request by the hook |
| ~50 hand-wired `audit()` call sites across admin / corporate / institute | **nothing** — a curated `metadata` object and no summary |

So `subscription.assigned` showed a good set of fields with nothing to lead
with, and thinner ones like `job_role.status_changed` showed a bare `{status}`.

Editing fifty call sites would have fixed the actions that exist today and
missed every one added later. Instead `app/helpers/auditSummary.js` generates
the sentence inside `buildEntry`, so **every row gets one** — including actions
added by someone who never reads that file.

```
Assigned a subscription: Friends in the data value — 6 assessment types, subscribed, 365 days
Changed a job role's status: quant Developer — status "OPEN" → "CLOSED"
Updated a campus: neet campus — sections: details, courses
```

Three properties are load-bearing:

- **It reads the redacted, size-capped values, not the raw event.** A token
  limit masked by `redact()` must not reappear in prose, and the sentence still
  attaches when an oversized payload has been replaced by a truncation marker.
- **A call-site summary always wins.** The handler had the request in front of
  it; this only has what was stored.
- **An unknown action is humanised from its own name** —
  `job_role.status_changed` → *"Job role status changed"* — so a new action
  reads properly on day one without touching the phrase table.

`ACTION_PHRASES` holds the nicer wording per action and `DETAIL_FIELDS` decides
which stored fields make it into the headline. Anything not listed still shows
in the Details panel; the table only chooses what is worth saying first.

## Every row says what happened, in words

A hook can only ever report "a PUT happened on this path", which is how the
trail ended up reading as a list of endpoints. Two things fixed that, on
2026-08-19:

**`metadata.summary`.** Written at audit time by `student-node` and
`institute-node`, it is a sentence built from the actual request — *"Updated 3
specialisations on the course mapping"*, *"Moved 3 candidates to SHORTLISTED"*,
*"TPO approval set to Lapsed"*. The route, HTTP method and full payload are
still recorded underneath as the evidence; the summary is only what a reader
sees first. `metadata.area` carries the section name for grouping.

**`student-node/app/helpers/studentAuditRoutes.js`.** A descriptor table mapping
each route to `{ action, entity, label, summary, changes }`. `entity` names the
route param that identifies the record, so the Admin trail can resolve it to a
name; `changes` is only populated where the request actually carries a
transition, because an audit row must record what it was told and never a guess.

Two stored codes are translated on the way in, since neither means anything on
screen: `tpoStatus` (an Int defaulting to `-2`; `-1` is **Lapsed**) and the
numeric opt-out state on `currentCourse` (`2` opt-out pending, `3` opted in,
`4` opt-in pending).

Every descriptor callback runs inside a try/catch. A summary is a nicety and the
audit row is not — a descriptor that trips over an unexpected payload must cost
the sentence, never the record.

### The student actions

Profile areas are named individually because they are what people dispute:
`student_profile.updated`, `student_education.updated`, `student_resume.updated`,
`student_work_experience.updated`, `student_internship.updated`,
`student_course.updated`.

**The profile endpoints take a nested body, so the route alone cannot say which
section was edited** — `PUT /students/:studentId/profileUpdate` covers all of
them. The payload keys are the only signal, and they are what decides the
action (`SECTION_ACTIONS`).

The apply-and-evaluate flow reads end to end, which is the point — this is how
you reconstruct what happened to one candidate:

| Action | Raised by |
|---|---|
| `application.applied` / `.saved` / `.declined` | `/students/role/{apply,save,reject}` |
| `application.status_changed` | ATS stage moves, incl. bulk |
| `tpo_approval.changed` | TPO decision and profile approval requests |
| `offer.status_changed` | offer released / accepted / rejected / negotiated |
| `candidate.status_changed` | drive candidate result |
| `opt_out.changed`, `application.withdrawn` | opt-out, opt-in and withdrawal |

**A new action must be added to `admin-node`'s taxonomy too**, or the Action
filter cannot offer it however many rows exist — `admin-node` never writes these,
but its `/audit/actions` feeds the filter for the whole trail.

### The expanded row

`admin-react`'s Details panel leads with the summary, states its own date and
time in IST (an expanded row is what gets screenshotted into a ticket), then
`What changed`, then `Submitted values` as labelled fields. Arrays of objects are
**counted, not printed** — a list of specialisation uuids told a reader nothing.
Endpoint and request id sit in a `Technical` block at the bottom; they stay,
because an audit row has to be verifiable.

## System Configuration: audited by a route hook, not per handler

System Config reuses long-lived CRUD endpoints across many masters, so wiring
`audit()` into each handler meant a new master endpoint stayed silently
unaudited until somebody remembered. Since 2026-08-18 `institute-node` records
**every successful mutation on that route surface** from an `onResponse` hook —
`app/helpers/systemConfigAudit.js`, registered in `index.js`.

It fires only when all of these hold:

- method is `POST` / `PUT` / `PATCH` / `DELETE`
- `reply.statusCode` is 2xx — a rejected edit never produces a row
- the route matches the System Config surface (`/institutes/crud/{domain,degree,
  streams,specialisation,category,degreeType,degreeLevel,
  updateStreamSpecialisationMapIfNotExist}`, `/institutes/admin/*OthersUpdate`,
  `/institutes/instituteCampus/:id/courses`)
- `getAuditContext().auditRecorded` is false

That last check is what makes the hook a **safety net rather than a duplicate**:
a handler that already wrote a richer, domain-specific event (say
`course.created`) sets the flag, and the hook stands down. Everything else lands
as `system_config.changed` under `portal: ADMIN`, with the route, HTTP method
and payload in `metadata`.

### The College screen, and two gaps that had to line up

Creating a college from Admin → System Configuration left **no trace at all**.
Two independent gaps were both required for that, and both are now closed:

- `createInstMaster` never called `audit()`, while `updateInstituteMaster` and
  `deleteInstitute` both did. **Create was the only one of the three missing** —
  which is why editing a college appeared in the trail and adding one did not.
- The hook's route list left `college` out, so the safety net that exists for
  exactly this case did not catch it either.

The handler now writes `institute.created` with the campus name and city, filed
under `portal: ADMIN` because that is the screen it is performed from. The
hook's pattern covers the whole college surface —
`/institutes/crud/(student)?college...` — and because handler-level `audit()`
sets `auditRecorded`, the hook stands down on create/update/delete and only
catches the rest (`studentcollege`, `tierInfo`).

The widened pattern is anchored deliberately: `/institutes/collegeDrive` merely
contains the word and is **not** System Configuration. A test guards that.

Reads as: *"Onboarded a college: Anna Neet Coaching campus — Chennai"*.

Known rough edge: `configArea()` matches lowercase `specialisation`, so
`updateStreamSpecialisationMapIfNotExist` and `specializationOthersUpdate` (capital
S / `z` spelling) fall through to the generic label *"System configuration"*.
The row is still written and `metadata.route` identifies it exactly — only the
display label is coarse.

**A new action must be added to the taxonomy of every service that names it** —
`app/helpers/auditActions.js`. `audit()` is fire-and-forget and turns an unknown
action into a log line, so a taxonomy miss produces **no row at all**, silently.
`admin-node` also carries actions it never writes, because its `/audit/actions`
feeds the Action filter for the whole trail.

## Two gotchas that cost a day

### 1. Prisma 4 rejects `datasourceUrl` → `/audit/logs` returns 500

`prisma/generated-audit/` is **gitignored**, so the audit client is generated at
image-build time. The Dockerfiles run `prisma generate` in the `deps` stage, but
the later `COPY . .` overwrites that output with whatever happens to be sitting
in the build context. The result is that the client version depends on whether
the build box has a leftover `generated-audit` directory:

| Build box | Generated client | Result |
|---|---|---|
| Has a leftover `generated-audit` | 6.19.3 | works |
| Clean checkout | 4.16.2 (from `prisma ^4.11.0`) | **500** |

`datasourceUrl` only exists from Prisma 5.2; on 4.x the constructor throws
`Unknown property datasourceUrl provided to PrismaClient constructor`, which the
handler turns into a generic `Failed to fetch audit logs` / 500.

The fix is to construct the client with the form that is valid on both 4.x and
6.x:

```js
new AuditPrismaClient({
  datasources: { db: { url: datasourceUrl } },
  log: ["error", "warn"],
});
```

Applied to `corporate-node` and `institute-node` on 2026-08-07, and to
`admin-node` and `student-node` since — all four now use the `datasources`
form, so a clean rebuild is safe everywhere.

### 3. `schema-audit.prisma` must list both OpenSSL engine targets

All four `schema-audit.prisma` files pinned only `linux-arm64-openssl-3.0.x`.
That is fine on DEV and UAT and **dead on PROD**, which runs OpenSSL 1.1 — the
audit engine would have had no matching binary, surfacing as a 500 on the trail
exactly where it matters most. Fixed 2026-08-19; all four now list both:

```prisma
binaryTargets = ["native", "linux-arm64-openssl-1.1.x", "linux-arm64-openssl-3.0.x", "windows"]
```

For `student-node` this is not a PROD-only concern: its image is
`arm64v8/node:18.20-bullseye`, which ships **OpenSSL 1.1.1**, so 1.1.x is the
engine that actually loads on every environment. The other services build on
`node:20-slim` (bookworm, OpenSSL 3).

`native` resolves at build time, which is exactly why the omission was invisible
— it silently produced the right engine on the boxes anyone tested on.

### 2. The audit Prisma engine needs OpenSSL in the image

`node:20-slim` ships without OpenSSL. Without it Prisma logs *"failed to detect
the libssl/openssl version to use"* and the query engine dies with
`Unexpected end of JSON input` — again surfacing as a 500.

Every Dockerfile that packages an audit client needs this in **both** stages:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssl libssl3 ca-certificates && rm -rf /var/lib/apt/lists/*
```

Because it is a Dockerfile change, a container restart is not enough — the image
must be rebuilt.

## Frontend

| Portal | Menu item | Axios instance |
|---|---|---|
| Admin | Audit Log (last nav item) | `utils/adminRequest` |
| Corporate | Activity Log | `utils/corporateRequest` |
| Institute | Activity Log | `utils/instRequest` |

**`institute-react` has two axios instances for the same API** — `instRequest`
and a legacy `instituteRequest`. Only `instRequest` is given the bearer token by
`utils/initializeApp.js`; `instituteRequest` is never initialised, so anything
importing it sends no `Authorization` header and gets
`401 jwt must be provided`. The Audit Log module hit exactly this and was fixed
on 2026-08-07.

Several `TPOApproval` student-resume drawers still import `instituteRequest` and
carry the same latent 401.

Note also that `verifyToken` in these services calls `jwt.verify()` on the **raw**
`Authorization` header — the portals must send the bare token, *not*
`Bearer <token>`.

## Making the menu appear (permissions)

Corporate and Institute run every nav item through `PermittedNavItems(...)`, so
**Activity Log stays hidden until the permission rows exist**, no matter what is
deployed. Three things are required, per journey:

1. A screen named `Activity Log` in `admin.screens` for that `journey`
2. A `View` event under it in `admin.events`
3. A grant per role in `admin.role_event_map`

Created on UAT 2026-08-07 for both `INSTITUTE` and `CORPORATE`; role grants are
assigned by hand in **Admin → Users → Roles and Permissions**. Users must log
out and back in for a new grant to take effect.

The screen/event create endpoints (`POST /screens`, `POST /events` on
`admin-node`) are **additive** — they append and reject duplicates with a 400,
so they cannot clobber an existing screen list. They are also currently
**unauthenticated**, which is worth revisiting.

Admin's own nav item is not gated on a screen permission.

## Related

- `Infrastructure/` — deployment and image-build notes
- Deploy path: `auto_deploy.sh <service> UAT` on the UAT box
