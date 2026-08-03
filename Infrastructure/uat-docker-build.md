# UAT Docker builds — apt failures on the Node API images

Production-truth as of 2026-08-03.

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
