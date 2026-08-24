# Frontend Static Delivery Policy

Updated 2026-08-24 after the Admin and Student portal login-load fix.

## Why it matters

Webpack emits content-hashed asset names (for example, `main.<hash>.js`). Those
files are immutable for the lifetime of a release. Serving them with
`no-cache` made browsers re-download multi-megabyte application bundles after
each login, even when the user already had the current release.

## Required HTTP behavior

| Response | Policy |
|---|---|
| `index.html` / SPA fallback | `Cache-Control: no-cache, no-store, must-revalidate` |
| Hashed JS, CSS, fonts and images | `Cache-Control: public, max-age=31536000, immutable` |
| Text assets over 1 KB | gzip/Brotli compression when the client accepts it |

The HTML must remain fresh because it selects the current hashed asset names.
Assets can be cached for a year because a changed asset receives a new hash and
therefore a new URL.

## Current app status

- `admin-react`: Express `compression` middleware plus immutable static cache;
  UAT commits `8dc5d82a` / `45bcbe17`.
- `student-react`: same Express configuration; UAT commits `b269062b` /
  `e76a0719`.
- `corporate-react` and `institute-react`: nginx already serves gzip and
  30-day immutable caches for hashed assets.

For Express frontends, declare `compression` both in `package.json` (DEV uses
the systemd Node server) and in the runtime Docker install command (UAT uses
the Docker image).
