# Mail Service (per-environment relay)

## What it is

An HTTP front for OCI Email Delivery. Everything that sends email on the
platform — assessment invites, reminders, OTPs, assign-job summaries,
normalisation export notifications — POSTs to it.

Repo: `PluginLive-Technologies/Mail-Server`.

## Topology (as of 2026-09-03)

One instance per environment. Before this date there was exactly **one**
instance, on the DEV box, and DEV, UAT and PROD all sent through it.

| Env | Public URL | What callers on the box use | Runs as | Allowlist |
|---|---|---|---|---|
| DEV | `https://mail.dev.pluginlive.com` | `http://172.17.0.1:5010/send-email` | `mail.service` (systemd, gunicorn) | none |
| UAT | `https://mail.uat.pluginlive.com` | `http://172.17.0.1:5010/send-email` | container `mail-server-uat` | `pluginlive.com,icanio.com` |
| PROD | *(none — in-cluster only)* | `http://mail-server.api.svc.cluster.local/send-email` | Deployment `mail-server`, ns `api`, 2 replicas | none (must reach real candidates) |

All send as `mandate@pluginlive.com`; UAT tags subjects `[UAT]`.

**Same-box callers deliberately use the internal address, not the public URL.**
Routing a container out to the public IP and back in through nginx adds DNS, TLS
and nginx as failure modes for traffic that never needs to leave the host. The
public hostnames exist for off-box callers and so the relays are addressable by a
stable name. PROD has no public URL at all — it is reachable only inside the
cluster.

**The DEV and UAT relays bind to the docker bridge IP (`172.17.0.1`), not
`0.0.0.0`.** Neither box filters INPUT, so binding publicly would expose an
endpoint that sends as `mandate@pluginlive.com` to the internet.

**PROD traffic never leaves the cluster.** Callers use the Service DNS name, so
there is no public hostname, no TLS certificate and no DNS record in the path.

### DNS: the apex is Route 53, the environment subdomains are OCI

Easy to get wrong. `dig NS pluginlive.com` returns AWS (`ns-*.awsdns-*`), but
**`dev.pluginlive.com`, `uat.pluginlive.com` and `prod.pluginlive.com` are each
delegated to OCI DNS** (`ns*.p201.dns.oraclecloud.net`) and exist as zones in the
matching OCI compartment. They are writable with the OCI CLI on the DEV box:

```bash
oci dns record domain get --zone-name-or-id prod.pluginlive.com \
  --domain mail.prod.pluginlive.com --compartment-id <PluginLivePROD ocid>
```

So any `*.dev|uat|prod.pluginlive.com` hostname can be created without AWS access.
Only apex-level records — `pluginlive.com` itself, `MX`, `SPF`, `DMARC` — need
Route 53. (The NS *delegation* for each child zone lives in the Route 53 parent;
the zone *contents* live in OCI. Both statements are true at once, which is what
makes this confusing.)

`mail.uat.pluginlive.com` and `mail.dev.pluginlive.com` were created this way on
2026-09-03, with Let's Encrypt certificates via `certbot --nginx` (renewal timers
active on both boxes):

```bash
oci dns record rrset update --zone-name-or-id uat.pluginlive.com \
  --compartment-id <PluginLiveUAT ocid> --domain mail.uat.pluginlive.com --rtype A \
  --items '[{"domain":"mail.uat.pluginlive.com","rtype":"A","rdata":"<ip>","ttl":300}]' --force
```

### The `mail.prod.pluginlive.com` trap (historical)

That hostname resolves to **129.154.231.72 — the DEV box's public IP**. The name
was aspirational; the instance behind it was always the DEV one. Until
2026-09-03 the PROD k8s ConfigMap `auth-api-config` pointed at it, PROD
admin-node reached it through a hardcoded source fallback, and PROD
form-data-normalization reached it through a settings.py default. Production
invites, reminders and OTPs were therefore relayed by a developer machine
running two gunicorn workers; UAT sends against it were returning intermittent
504s (17 on the morning of the cutover).

The hostname still resolves to the DEV box and still serves the side projects on
it (ucat, pilvidya, banking, medverse). It is no longer in any platform path.

**Retiring it is now unblocked**: since `mail.dev.pluginlive.com` exists, those
side projects can be repointed at it, after which the DEV box can stop answering
for `mail.prod.pluginlive.com` entirely. Each app bakes the endpoint in at build
time (ucat via `PLUGINLIVE_MAIL_ENDPOINT`), so this needs a rebuild per app.

## Configuration

All settings are `MAIL_`-prefixed. The prefix is load-bearing: the DEV box
exports `SMTP_HOST`/`SMTP_USER` machine-wide (pointing at a personal gmail
account) and the old systemd unit exported a placeholder
`SMTP_USER=...REPLACE_WITH_YOUR_OCI_SMTP_USERNAME`. Unprefixed names would have
been silently hijacked by either.

| Variable | Purpose |
|---|---|
| `MAIL_ENV` | Label in `/health` and every log line |
| `MAIL_SMTP_HOST/PORT/USER` | Relay (default OCI Mumbai) |
| `MAIL_SMTP_PASSWORD` / `MAIL_SMTP_PASSWORD_FILE` | Credential; inline or from a file |
| `MAIL_SENDER`, `MAIL_SENDER_NAME` | From address (must be an OCI approved sender) |
| `MAIL_SUBJECT_TAG` | Prefixed to subjects, e.g. `[UAT]`. Empty on prod |
| `MAIL_ALLOWED_RECIPIENT_DOMAINS` | Comma list; empty = everyone |
| `MAIL_AUTH_KEY`, `MAIL_REQUIRE_AUTH` | Shared secret on `/send-email` |

Every default reproduces the original single-instance behaviour, so an instance
started with no environment is unchanged. Safety features are opt-in per
deployment because this service carries production OTP and invite mail.

The service refuses to start if no SMTP password is available or if
`MAIL_REQUIRE_AUTH` is on without a key. The container runs `gunicorn --preload`
so a misconfiguration exits immediately rather than looping on worker restarts.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/send-email` | Send. Body: `toAdresses[]`, `subject`, `text`/`html`, optional `ccAddresses`, `replyToAddresses` |
| POST | `/test-email` | Fixed test message to `{"toEmail": "..."}` |
| GET | `/health` | Liveness + effective configuration |
| GET | `/ready` | Readiness: performs a real SMTP connect + login |

Responses carry the `messageId` minted per send — callers persist it so an OCI
delivery/bounce event updates the existing `assessment.email_events` row instead
of inserting a duplicate. Recipients dropped by the allowlist come back in
`blockedRecipients`.

## Auth

`/send-email` had **no authentication at all** while being internet-reachable.
Enforced on **UAT and PROD since 2026-09-03**; **off on DEV**.

The DEV blocker is specific: **MedVerse** (a live product on a separate cluster)
sends through this relay via `mail.prod.pluginlive.com`, and its manifest carries
`PLUGINLIVE_MAIL_AUTH_KEY` set to the same shared key — but its send code
(`reapply-pluginlive-mail.py`) is not on the DEV box, so it cannot be confirmed
that the header is actually transmitted rather than merely configured. If it is
not, enforcing DEV auth silently breaks MedVerse login OTPs.

**To close it:** the DEV relay now runs gunicorn with `--access-logfile -`, so
callers appear in `journalctl -u mail.service`. Watch for a real MedVerse send,
confirm it carries `auth-key`, then set `MAIL_REQUIRE_AUTH=true` in the unit.
Before that change there was no access logging at all, which is why the caller
set was unknown.

**The relay's `MAIL_AUTH_KEY` must equal the `AUTH_KEY` the callers already
send** — do not generate a fresh secret for it. `admin-node` (all five call
sites), `user-management-node` and `form-data-normalization` all send
`auth-key: <their AUTH_KEY>`, and on PROD/UAT that is one shared value. Setting
the relay to anything else 401s every send and takes mail down.

`form-data-normalization` additionally **refuses to send at all** when its
`EMAIL_AUTH_KEY` is unset (`services/mailer.py:225`) — it was unset on PROD, so
export notification mail was silently disabled there until 2026-09-03.

## No fallback endpoint

`admin-node` and `form-data-normalization` used to default `EMAIL_ENDPOINT` to
the prod hostname. Both now **throw at startup** when it is unset
(`admin-node/app/helpers/mailRelay.js`, `form-data-normalization/config/settings.py`).
A missing endpoint is a boot failure rather than a silent cross-environment send,
so **every environment must set `EMAIL_ENDPOINT`** — DEV/UAT in the box-local
`.env`/`.env.uat` (untracked, per box), PROD in the service's ConfigMap.

## Deploying

- **DEV**: `sudo systemctl restart mail.service` (unit at `/etc/systemd/system/mail.service`).
- **UAT**: `./auto_deploy.sh mail-server` on the UAT box; checkout at
  `~/mail-server`, config in `~/mail-server/.env.uat` (chmod 600).
- **PROD**: build for **arm64**, push to `bom.ocir.io/bmv2bqg5gpcd/pl-mail-server`,
  then `kubectl -n api set image deployment/mail-server mail-server=<tag>`.
  Manifest kept at `~/mail-server-prod.yaml` on the PROD box; pull secret
  `oracleregistry`; config in ConfigMap `mail-server-config` and Secret
  `mail-server-secret`.

## Rotating the SMTP credential

Rotated 2026-09-03. **This cannot be done without a gap** — plan for one:

- OCI caps SMTP credentials at **2 per user**, and the mail user's two slots are
  taken by the relay's credential and an unrelated `scheduler-vm` one. So a new
  credential cannot be minted before the old is deleted; delete-then-create is
  the only route and mail is down in between.
- **A new credential takes ~4 minutes to become usable.** It reports
  `lifecycle-state: ACTIVE` immediately but SMTP login returns
  `535 Authentication credentials invalid` until it propagates. Budget for this;
  the 2026-09-03 rotation had a ~7 minute mail outage almost entirely from it.
- **Rotation changes the username, not just the password.** Each credential has
  its own `username` (the suffix differs: `.qj.com` → `.es.com`). `MAIL_SMTP_USER`
  must be updated everywhere alongside `MAIL_SMTP_PASSWORD`, or auth fails.
- Identify which credential a relay is using by matching that username suffix, or
  by SMTP-logging-in with each candidate username and the known password.

Applying the new value per environment:

| Env | How | Gotcha |
|---|---|---|
| DEV | write `~/Mail-Server/ociemail.config`, set `Environment=MAIL_SMTP_USER=` in the unit, `daemon-reload && restart` | — |
| UAT | edit `~/mail-server/.env.uat`, then **`./auto_deploy.sh mail-server`** | **`docker restart` does NOT re-read `--env-file`.** The container keeps its original environment and keeps failing auth while the file on disk looks correct. It must be recreated. |
| PROD | `kubectl -n api patch secret mail-server-secret`, then `rollout restart deployment/mail-server` | New pods fail their `/ready` startup probe until the credential propagates; the rollout stalls and old pods stay up. This is correct behaviour, not a failure. |

Verify with `/ready` (a real SMTP login) on each, then a real send.

## Known gaps

- **The OCI SMTP credential is still shared by all three environments** and sits
  in plaintext (`~/Mail-Server/ociemail.config` on DEV, k8s Secret on PROD).
  Per-environment credentials need **separate IAM users** — the 2-per-user quota
  makes it impossible on one user. Creating a service user is also non-trivial:
  the IDCS domain requires a primary email, so it fires an activation mail at a
  real address, and a new policy is needed because the current credential only
  works by virtue of belonging to a member of `Administrators`.
- **The credential belongs to `neston.alex@pluginlive.com`, a named human in the
  `Administrators` group.** All platform email authenticates as that person; if
  the account is deactivated, every environment stops sending.
- Only `mandate@pluginlive.com` is an approved sender (compartment
  PluginLivePROD), so all environments share a From address and are distinguished
  only by the `[UAT]` subject tag.
- The DEV relay has **no allowlist**, because the side projects on that box send
  OTPs to real external users through it. Those should move to their own instance
  before DEV can be locked down.


## Outbound deliverability: SPF does not cover OCI

The apex SPF record is `v=spf1 include:_spf.google.com ~all` — it authorises
**Google Workspace only**. Everything the platform sends goes out through **OCI
Email Delivery**, whose senders are therefore **not SPF-authorised** for
`pluginlive.com`. With `~all` (softfail) mail is still accepted by most receivers
but is a spam-foldering risk, and it weakens any bounce/complaint story.

There is also **no DMARC policy**. `_dmarc.pluginlive.com` appears to answer, but
that is a **wildcard `*.pluginlive.com TXT "MS=ms24378662"`** catching every
lookup — no record starts with `v=DMARC1`. The same wildcard makes DKIM selector
probing meaningless: every `<anything>._domainkey.pluginlive.com` "resolves".

Fixing this means adding OCI's SPF include to the apex TXT record, publishing the
OCI DKIM selector, and adding a real DMARC record — **all apex records, so all in
Route 53.** MX points at Google Workspace, so tread carefully: a mistake in these
records affects the company's own mail, not just platform sending.