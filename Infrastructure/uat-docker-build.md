# Docker builds — apt failures on the Node API images

Production-truth as of 2026-09-07. Applies to **DEV, UAT and PROD** — the
bullseye EOL failure below is not UAT-specific.

## FIRST: is this the Debian 11 EOL failure? (2026-09-07 onward)

There are now **two unrelated causes** of an apt build failure here. Check this
one first, because it is permanent and retrying cannot fix it.

**Debian 11 (bullseye) LTS ended 2026-08-31.** Two consequences, both of which
break any image on a `*-bullseye` base:

1. The `bullseye-security` **.deb pool is being purged off the Fastly CDN**. The
   package index still advertises a version that the pool no longer serves, so
   you get `404 Not Found` — not a timeout. It is *inconsistent across CDN edge
   nodes*: measured 2026-09-07, five fetches of the same `libcurl4` URL returned
   `200, 404, 404, 404, 404` from different `151.101.x` IPs. **This is why
   `Acquire::Retries` cannot save the build** — it is not a flaky connection,
   most edges genuinely no longer have the file.
2. The final `bullseye-security` `Release` file has **`Valid-Until: 2026-09-07
   21:13 UTC`** and will never be re-published. After that, apt rejects the index
   as expired even where the pool survives.

Ruled out on 2026-09-07: `security.debian.org` fixed most 404s but still lost
`libcurl4`; `ftp.debian.org`, `ftp.us.debian.org`, `mirror.csclub.uwaterloo.ca`
and `debian.mirror.constant.com` have none of it; and **`archive.debian.org` had
not received bullseye-security yet** (404), so the usual "point at archive"
advice did not work either.

### The fix — pin to snapshot.debian.org

`student-node/Dockerfile` (commit `52d78ae7`, on `release-v1.39-hotfix-3`):

```dockerfile
RUN printf 'Acquire::Retries "8";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\nAcquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99-network-resilience \
    && printf 'deb http://snapshot.debian.org/archive/debian/20260901T000000Z bullseye main\ndeb http://snapshot.debian.org/archive/debian-security/20260901T000000Z bullseye-security main\ndeb http://snapshot.debian.org/archive/debian/20260901T000000Z bullseye-updates main\n' > /etc/apt/sources.list \
    && apt-get update && apt-get install -y \
    ... \
    && rm -rf /var/lib/apt/lists/*
```

`snapshot.debian.org` keeps every archive state forever, so this is permanent and
reproducible. The `20260901T000000Z` timestamp sits just after the final LTS
patch set and serves the **identical versions the live index advertises**
(`libcurl4 7.74.0-1.3+deb11u16`, `systemd 247.3-7+deb11u8`,
`libgbm1 20.3.5-1+deb11u1`) — so it is **not a security downgrade**.
`Acquire::Check-Valid-Until "false"` is required: a snapshot's `Release` file is
by definition past its expiry. Verified: rebuild fetched all ~688 packages with
**zero 404s** in ~6 min.

### Scope — this is not fixed everywhere

As of 2026-09-07 the fix exists **only on `student-node`'s
`release-v1.39-hotfix-3`**. `student-node`'s `Development` / `UAT` branches still
point at `deb.debian.org`, so **DEV and UAT student-node builds are broken**, and
the next release cut from `UAT` will reintroduce the break — the same
permanent-divergence trap that hit `admin-node`'s Dockerfile (v1.37) and
`institute-react-v2` (v1.38). Port `52d78ae7` to `Development`/`UAT`.

Any other repo on a bullseye base will fail the same way the moment its apt layer
is rebuilt.

---

## The older, separate cause: network stalls (2026-08-03)

Production-truth as of 2026-08-03. This one *is* a flaky connection, presents as
a **timeout rather than a 404**, and the retry config below does fix it.

## Symptom

`~/auto_deploy.sh <service> UAT` dies during the image build with:

```
E: Failed to fetch http://deb.debian.org/debian-security/pool/.../ffmpeg_..._arm64.deb  Connection timed out [IP: 151.101.x.x 80]
E: Unable to fetch some archives, maybe run apt-get update or try with --fix-missing?
ERROR: failed to solve: process "/bin/sh -c apt-get update && apt-get install -y ..." did not complete successfully: exit code: 100
!!! BUILD FAILED — old container left running, no downtime !!!
```

The old container keeps serving, so there is **no outage** — but the git checkout
on the box has already advanced to the new commit. That is the dangerous state:
`git log` shows the new code while `docker ps` shows a container from days ago.
**Always confirm the container's uptime/image, not just the checkout, after a
failed deploy.**

## Cause

Plain **HTTP** to `deb.debian.org` stalls mid-transfer from the UAT box.
Measured 2026-08-03, same file, same host:

| URL | Result |
|---|---|
| `http://deb.debian.org/.../libmail-java_1.6.5-1_all.deb` | hangs at 43,440 of 694,276 bytes, times out |
| `https://deb.debian.org/...` (same path) | full 694,276 bytes in 0.08s |
| `http://ftp.debian.org/...` | full file in 0.66s |
| `http://cdn-aws.deb.debian.org/...` | full file in 1.03s |

Reproduces identically on the host and inside a container, so it is the box's
egress path to that Fastly POP on port 80 — not Docker, not the Dockerfile.
It is partial: a build fetched 553 MB / 688 packages successfully and failed on
4. Different packages fail on each attempt, so **retrying is a coin flip** and
each attempt costs 5–8 minutes.

## Fix in the images

`student-node/Dockerfile` now writes an apt config before installing:

```dockerfile
RUN printf 'Acquire::Retries "8";\nAcquire::http::Timeout "20";\nAcquire::https::Timeout "20";\n' > /etc/apt/apt.conf.d/99-network-resilience \
    && apt-get update && apt-get install -y \
    chromium ... libreoffice ffmpeg fonts-noto-* fonts-indic \
    && rm -rf /var/lib/apt/lists/*
```

apt's default HTTP timeout is 120s with no retries, so one stalled connection
aborts the whole install. A 20s timeout plus retries drops the dead connection
and re-fetches on a fresh one. Apply the same two lines to any other service
whose build hits this.

## Why this layer is rebuilt on every single deploy

`student-node/Dockerfile` has `COPY . /app` **above** the `apt-get install`
layer, so any code change invalidates the package layer and re-downloads ~553 MB
of Chromium + LibreOffice + ffmpeg + Noto fonts on every deploy. That is why a
flaky mirror is deploy-blocking here rather than a one-time annoyance. Moving the
`COPY` below the apt layer would make deploys cache-hit and take seconds — not
done yet, since it changes layer ordering for DEV/UAT/PROD alike and wants its
own verification pass.

Related consequence: `--no-cache` (which `auto_deploy.sh` uses) and a pruned
buildkit cache both guarantee the full re-download. `DOCKER_BUILDKIT=0` does not
help — the classic builder misses the same layer once `COPY . /app` has changed.

## Rollback

`auto_deploy.sh` overwrites the `<service>:api` tag in place, so tag the running
image before a risky deploy:

```bash
docker tag student-node:api student-node:api-rollback
```

Also note `auto_deploy.sh` re-creates the container and can drop the restart
policy — confirm with
`docker inspect student --format '{{.HostConfig.RestartPolicy.Name}}'`
and re-apply `--restart unless-stopped` if it comes back `no`.
