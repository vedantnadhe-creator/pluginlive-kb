# Corporate ATS v2 — strangler-fig, and why it is DEV-only

The Corporate portal is being rebuilt vertical-by-vertical behind a strangler-fig,
the same pattern as institute-react-v2. Two new repos sit alongside the v1 app:

| Repo | Checkout | Stack | Where it runs |
|---|---|---|---|
| `corporate-react-v2` | `~/frontend/corporate-react-v2` | Next.js + TS + Tailwind, `basePath=/v2` | **DEV only** — systemd `corporate-react-v2` :3012, nginx `location /v2` in `corp-react.conf` |
| `corporate-node-v2` | `~/api/corporate-node-v2` | Fastify + TS + Zod + Kysely/pg (no Prisma) | **DEV only** — systemd `corporate-node-v2` :4001, OpenAPI at `/docs` |

v1 (`corporate-react` :3001, `corporate-node` :8080) is untouched and still serves
every vertical. v2 reads the existing corporate tables and owns only additive
tables of its own.

## The handoff: v1's nav is what routes users into v2

v2 is a *separate app on the same origin*, so react-router cannot client-route
into it. The handoff is two lines in v1:

- `src/modules/Nav/navItems.js` — the Roles entry's `path`
- `src/modules/Nav/index.js` — `onItemClick` hard-navigates (`window.location`)
  for any path starting with `/v2`

Flipping a vertical to v2 means pointing that `path` at `/v2/<route>`; reverting
means pointing it back at the v1 route (Roles ↔ `/rolePage`).

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

Note `corporate-react-v2` / `corporate-node-v2` are **not** services in
`auto_deploy.sh`, so a UAT/PROD deploy of them is manual work, not a one-liner —
another reason the flip outruns the app.
