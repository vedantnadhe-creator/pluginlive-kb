# Audit log (Admin / Corporate / Institute)

> An append-only audit trail shared by all three portals, each scoped to its own
> tenant. Admin sees it as **Audit Log**; Corporate and Institute see it as
> **Activity Log**.
>
> **Status:** DEV + UAT (2026-08-07; entity/actor names and onboarding events,
> dynamic entity filter and the System Config safety net 2026-08-18).
> PROD pending.

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

The entity resolver only fills rows whose `entity_label` is **null**. A label a
call site captured at write time is what the entity was called at the time and
always wins.

What each service can name (2026-08-18):

| Service | Entity types resolved |
|---|---|
| `admin-node` | assessment, subscription (college *or* company), corporate, institute, job_role, student_list |
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

Applied to `corporate-node` and `institute-node` on 2026-08-07. **`admin-node`
still uses the `datasourceUrl` shorthand** and works only because its current
images carry the 6.19.3 client — a clean rebuild will break it the same way.

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
