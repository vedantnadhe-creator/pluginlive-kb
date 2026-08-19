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
   (`63e4de1011d6db2f8d400580`, role `system`). `AuditActor.findNamesByIds` now
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

### Why some of these say System and it is not a bug

`create-full` is authenticated by a shared `auth-key` that carries **no
identity**, and the Tally and public routes by nothing at all. There is no token
to name an actor from, so those rows previously had `actor_id = NULL` and
rendered as **"Unknown"** — which reads like a fault rather than like a machine
import.

A descriptor can now set `systemActor: true`, and the hook then files the row as
`portal: SYSTEM` with `actorRole: "system"`, so it renders as **System**. It
applies **only when no real actor was captured** — a person acting on one of
those routes still gets the credit.

Note the shape of the fix: the honest answer to "who imported this?" is *nobody,
a machine did* — so WHO says System and the **action** says it came from the
Tally form. Putting the channel in the WHO column would have been the wrong
place for it.

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
