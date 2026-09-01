# Corporate ATS v2 — strangler-fig (LIVE on PROD since 2026-07-30)

The Corporate portal is being rebuilt vertical-by-vertical behind a strangler-fig,
the same pattern as institute-react-v2. Two new repos sit alongside the v1 app:

| Repo | Checkout | Stack | Where it runs |
|---|---|---|---|
| `corporate-react-v2` | `~/frontend/corporate-react-v2` | Next.js + TS + Tailwind, `basePath=/v2` | DEV: systemd :3012 · UAT: systemd :3014 · **PROD: k8s ns `frontend`** |
| `corporate-node-v2` | `~/api/corporate-node-v2` | Fastify + TS + Zod + Kysely/pg (no Prisma) | DEV: systemd :4001 · UAT: systemd :4001 · **PROD: k8s ns `api`** (API + worker) |

## UAT (since 2026-08-19)

Both services run as systemd units on the UAT box, not containers:
`corporate-react-v2` :3014 behind `corporate.uat.pluginlive.com/v2`, and
`corporate-node-v2` :4001 with no public route. Deploy the frontend with
`./auto_deploy.sh corporate-react-v2 UAT` (menu 24); the API is built and
restarted by hand. Env, secrets, queue isolation and the score webhook are
documented in
[Infrastructure/v2-apps-uat-topology.md](../../Infrastructure/v2-apps-uat-topology.md).

The 11 agentic migrations **are** applied to UAT (verified 2026-08-19, 58 tables
in the `corporate` schema). `deploy/prod/RELEASE-v1.37.md` in the repo still
claims UAT is pending — that is stale.

## PROD topology (release-v1.37, deployed 2026-07-30)

| Object | ns | Notes |
|---|---|---|
| `corporate-node-v2` Deployment + Service | api | port 4001, Service `:80→4001`, probes `/v2/health`. **No Ingress** — cluster-internal only |
| `corporate-node-v2-worker` Deployment | api | same image, `command: ["node","dist/worker.js"]`, `replicas: 1`, `strategy: Recreate` |
| `corp-v2-api-config` ConfigMap | api | mounted `/app/.env` via `subPath` |
| `corporate-react-v2` Deployment + Service | frontend | port 3000, Service `:80→3000` |
| `corporate-v2-reminders` CronJob | api | hourly `POST /v2/reminders/run` |
| `/v2` path on `corporate-react-ingress` | frontend | → `corporate-react-v2:80`, same host as v1 |

Images: `pl-corporate-api-v2`, `pl-corporate-react-v2` (OCIR). Env files:
`repositories/envs/api/corporate-node-v2.env`, `repositories/envs/ui/corporate-react-v2.env`.

**The worker must stay `replicas: 1`.** `installSchedules()` clears the five
repeatable jobs by name and re-adds them at boot; two workers doing that
concurrently can leave duplicates registered, and the agent then runs twice per
tick — meaning candidates mailed twice.

The Evaluation Agent ships disarmed on PROD (`EVALUATION_AGENT_ENABLED=false`,
`SHADOW=true`) and `REMINDER_ENABLED=false`, so no candidate mail moves until
those are deliberately flipped.

## Gotcha — PROD Postgres is hostssl-only; DEV and UAT are not

`corporate-node-v2` builds its pg Pool from `connectionString` with no explicit
`ssl`, so on PROD every query fails with:

```
no pg_hba.conf entry for host "...", user "plproduction", database "prod_pluginlive", no encryption
```

`/v2/health` answers `503 {"status":"degraded","db":"down"}` and the pod
crash-loops on its liveness probe. **This cannot reproduce on DEV or UAT** —
neither requires TLS.

The fix is in the URL, not the code: append **`sslmode=no-verify`**.
`require` and `prefer` both fail with `self-signed certificate in certificate
chain`, because the PROD cert chain is self-signed and those modes validate it.
v1 `corporate-node` never hit this because Prisma negotiates TLS without
validating by default.

## Gotcha — the frontend and the backends are in DIFFERENT namespaces

`corporate-react-v2` runs in ns `frontend`; `corporate-node-v2` and `auth-node`
run in ns `api`. A bare Service name only resolves within its own namespace, so
the BFF's `CORP_V2_API_URL` / `AUTH_API_URL` **must be FQDNs**:

```
CORP_V2_API_URL=http://corporate-node-v2.api.svc.cluster.local
AUTH_API_URL=http://auth-node.api.svc.cluster.local
```

A short name here fails every BFF call at runtime while the pod stays happily
`1/1 Running`. `student-node`'s `CORPORATE_ATS_URL=http://corporate-node-v2` is
fine unqualified — student-node is itself in ns `api`.

v1 (`corporate-react` :3001, `corporate-node` :8080) still serves every vertical.
`corporate-node` is no longer untouched: it now also hosts the ten read
endpoints behind the v2 assessment screens (see
[assessment-dashboard.md](./assessment-dashboard.md)) — those do NOT live in
`corporate-node-v2`. v2 reads the existing corporate tables and owns only additive
tables of its own.

## The handoff: v1's nav is what routes users into v2

v2 is a *separate app on the same origin*, so react-router cannot client-route
into it. The handoff is two lines in v1:

- `src/modules/Nav/navItems.js` — the Roles entry's `path`
- `src/modules/Nav/index.js` — `onItemClick` hard-navigates (`window.location`)
  for any path starting with `/v2`

Flipping a vertical to v2 means pointing that `path` at `/v2/<route>`; reverting
means pointing it back at the v1 route (Roles ↔ `/rolePage`).

**As of 2026-08-27 the flips are: Roles → v1 `/rolePage`, Assessments →
`/v2/dashboard`.** Roles moved back deliberately — v2's own sidebar now bridges
to v1 for Roles, and both ends must agree or the two sidebars point at each
other. The Assessments entry is gated on a per-corporate subscription and its
own env flag; see [assessment-dashboard.md](./assessment-dashboard.md).

**As of 2026-09-01 the v2 sidebar is trimmed to Dashboard · Assessments ·
"Back to ATS"** (DEV + UAT), matching the institute TPO shell. The individual
v1 bridge entries (Roles, Hiring Mandates, Interviewer Dashboard, Reports,
Users, Settings) are commented out in `src/config/nav.tsx` rather than deleted —
uncomment an entry with its icon import to bring a section back to the rail.

The back link targets **`v1("/dashboard")`, not `v1("/")`** as institute's does.
corporate-react's `routes/Components/AuthRouter.js` redirects `/` to `/signin`
unconditionally, regardless of auth state, so bridging to the root bounces a
signed-in recruiter to the login page. Its registered route is `/Dashboard`
(capital D) and the lowercase link resolves only because react-router 6 matches
case-insensitively — v1's own nav item uses the lowercase form too.

`v1()` prefixes `NEXT_PUBLIC_V1_BASE`, which is **empty in every real env**
(v2 is mounted at `<host>/v2`, v1 at `<host>/`), so a bare absolute path is
already an ATS link and the session is shared.

## Gotcha — the nav flip must not reach an env without the v2 app

**The flip and the v2 deployment are in different repos, so they promote
independently.** Nothing stops the v1 flip from being merged to UAT while
`corporate-react-v2` has no container, no systemd unit and no nginx `location /v2`
on that box.

The failure is silent rather than loud: nginx on `corporate.<env>.pluginlive.com`
has only `location /` → :3001, so `/v2/roles` is proxied to the **v1 SPA**, which
answers **200** with `index.html` and then renders `PageNotFound` (v1 has no
`/v2/*` route). Health checks and `curl -o /dev/null -w %{http_code}` both look
fine; the Roles nav item is simply dead.

This happened on UAT: commit `bd4fda92b` (`feat(nav): route Roles nav entry to
corporate-react-v2`) rode a Development→UAT merge and went live in the
2026-07-29 `corporate-react` build. Reverted on 2026-07-30 (`82c33ce0f`), UAT
rebuilt, Roles back on v1 `/rolePage`.

**Before flipping any vertical in an env, confirm on that box:** a running
`corporate-react-v2` (and `corporate-node-v2` it calls), plus a `location /v2`
block in that env's `corp-react.conf`. To check whether a bundle carries a flip:

```bash
docker exec corporatereact sh -c 'grep -rho "/v2/roles" /usr/share/nginx/html | wc -l'
```

On PROD `deploy.sh` now has menu entries **19) Corporate-Node-V2** and
**20) Corporate-React-V2**, but they only *build and roll* — `kubectl set image`
cannot create objects, so the Deployments/Services/ConfigMap/CronJob above were
created by hand once. `deploy.sh` also rolls only `deployment/corporate-node-v2`;
**the worker needs its own `kubectl set image`** or it silently keeps old code.

`deploy.sh` runs `docker system prune -af` on every build. Use
`~/autodeploy_noprune.sh` (or build manually) when another deploy is running on
the box, or the prune will destroy the other build's cache and untagged layers.

### Status on PROD as of 2026-07-30

v2 is deployed and reachable at `https://corporate.pluginlive.com/v2`, but the
v1 nav flip is **still reverted**, so there is no in-product link to it — v2 is
URL-only until `corporate-react`'s Roles entry is pointed back at `/v2/roles`.
That is deliberate: it keeps a rollback lever that needs no deploy.
