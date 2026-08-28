# Assessment Media Retention

Policy for proctoring snapshots, video/audio answers and AI-interview responses:
**Infrequent Access at 90 days, delete at 365 days**, uniform across all attempt media.

> **Current state (2026-08-27): the application side is deployed to DEV and UAT but the
> sweep is DISABLED, and no OCI bucket lifecycle rule exists yet.** Nothing is being
> tiered or deleted in any environment. `RETENTION_ENABLED` is unset everywhere, which
> evaluates false. PROD has neither the schema nor the code.

## The split: who deletes what

The application **cannot delete an object**. Bucket deletion is done by OCI Object
Lifecycle Management rules keyed on name prefix and object age. The cron only marks
rows, clears dangling pointers, and writes an audit trail.

That split is the safety model, not an implementation detail. A retention job holding
delete credentials over ~1.13M irreplaceable proctoring images is the failure mode worth
designing out — the worst a bug in the sweep can do is hide rows, which is one `UPDATE`
to undo.

Planned lifecycle rules (**not yet created on any bucket**):

```
proctor/  → INFREQUENT ACCESS at 90 days, DELETE at 365 days
videos/   → INFREQUENT ACCESS at 90 days, DELETE at 365 days
audio/    → INFREQUENT ACCESS at 90 days, DELETE at 365 days
images/   → no rule (question/option media is content, not candidate data)
```

Enumerate the three prefixes explicitly. A single bucket-wide rule with exclusions is the
misconfiguration that would consume `images/` or `resumes/`.

## Two phases

| Phase | When | What |
|---|---|---|
| `mark` | `RETENTION_DELETE_DAYS` (365) | Sets `purged_at`. The object still exists; the UI stops serving it. Reversible by clearing the column. |
| `sunset` | + `RETENTION_GRACE_DAYS` (14) | OCI has removed the bytes by now, so null the dangling keys. |

The grace window must stay **shorter** than the gap between the app-level cutoff and the
bucket rule's DELETE age, or sunset nulls keys for objects OCI has not removed yet and
orphans them — bytes still billed, nothing in the database pointing at them.

**Sunset never deletes a row.** It nulls `snapshot_key` / `object_key` /
`response_object_key`. Snapshot rows in particular must survive: the Admin report's
"IP Addresses" view and its per-snapshot face counts are derived from them
(`uniqueIps = log.snapshots.map(s => s.ipAddress)` in admin-node `Assessment.js`).
Deleting them would destroy audit evidence unrelated to the privacy concern — the row is
not the liability, the object is. At PROD's ~1.13M snapshots the rows are ~275 MB against
~110 GB of object storage reclaimed.

Deleting the `proctoring_logs` parent instead would be worse: only `proctoring_snapshots`
has that foreign key, so `proctoring_events` and `proctoring_reports` (which carry
`proctoring_log_id` with **no constraint**) would be stranded rather than cascaded.

## The sweep — `student-node/script/purgeExpiredAssetsCron.js`

Registered in `script/scheduler.js`, daily at 02:40. Batches are claimed with
`SELECT … FOR UPDATE SKIP LOCKED` because the scheduler runs in every pod. The per-asset
loop is serialised on purpose — concurrent `$queryRaw` on one Prisma client panics the
engine on ARM64.

```
RETENTION_ENABLED=false      # ships disabled; must be opted into per environment
RETENTION_DELETE_DAYS=365
RETENTION_GRACE_DAYS=14
RETENTION_BATCH_SIZE=500
RETENTION_SEGMENTS=institute # institute | corporate | both
RETENTION_DRY_RUN=false
```

The IA threshold is deliberately absent — lifecycle rules handle tiering, so the
application never needs to know about it.

**`RETENTION_DRY_RUN=true`** counts and audits what would be swept without changing
anything. Its count is **not batch-capped** — a batch-limited count would echo the batch
size back and say nothing about the size of the job. Use it to size and sign off a
catch-up before touching anything.

**Drain rate is `RETENTION_BATCH_SIZE` per asset type per daily run** (500/day). PROD's
institute backlog (937 rows) takes ~2 days; both segments (2,243) ~5 days.

### Rollout is institute-first

`RETENTION_SEGMENTS` gates which segment is swept, because corporate assessment evidence
may be covered by client contract terms. Segment comes from
`assessment_assigned_students`, which carries both `assessment_corporate_map_id` and
`assessment_institute_map_id` with exactly one populated — a column test, not a join.

PROD snapshot split: **institute 979,389 (88%), corporate 131,872 (12%)**, plus 14,898
(1.3%) unattributable to either (their assigned-student row is gone). The asymmetry
inverts on the delete-eligible backlog: **corporate holds ~55% of it** despite being 12%
of volume, because its data skews older. Institute-first therefore makes the first
production action 937 rows rather than 2,243.

The unattributable rows are never marked — nothing can attribute them. The prefix-based
lifecycle rule collects them on object age instead.

## Read paths — both are gated

A presigned URL can be minted for an object that no longer exists; signing does not check
existence. Without a gate the caller gets a valid URL that 404s in the browser.

| Endpoint | Gate |
|---|---|
| `GET /students/assessments/proctoring/get_image_url/:snapshot_key` | Looks the row up; returns `{ parUrl: null, expired: true }` for a purged **or unknown** key. |
| `POST /students/assessments/getMediaUrls` | Looks up `student_answers` + `ai_interview_interactions`; returns the refused filenames in `data.expired[]` alongside `data.urls`. |

The two differ deliberately. `getMediaUrls` blocks only on a **positive** purge signal —
an unknown filename is still signed, because its filenames come from the caller rather
than being read back from a row we wrote, so treating unknown as expired would risk
breaking playback that works today. `get_image_url` receives keys admin-node read out of
the row, so unknown there genuinely means "no such row".

admin-node additionally **skips the fetch entirely** when `snapshot.purgedAt` is set —
correct behaviour and the cheap path, since that fetch is one HTTP round-trip per
snapshot and a purged session is exactly the old report likely to have hundreds.

### What the admin sees

- **Snapshot grid** — "Expired — retention policy" instead of the image. "No image" is
  still used for a genuine upload failure; conflating the two would make a working
  policy read as a bug.
- **Audio/video player** — "Recording expired", noting the score and assessment record
  are unaffected. Previously this fell through to a generic error advising the admin to
  check `media_uploads`, CORS and the backend server, which would send them chasing a
  non-problem.
- **Everything else survives**: violation counts, timeline, verdict, integrity band,
  IP addresses, per-snapshot face counts, scores, transcripts and report PDFs.

## Database

Schema `assessment`. Migrations in `DB-Scripts/Asset Retention and Purge/`:

| Migration | What | DEV | UAT | PROD |
|---|---|---|---|---|
| `20260827T064541Z__asset_retention_purge_tracking.sql` | `purged_at` on `proctoring_snapshots`, `student_answers`, `ai_interview_interactions`; three partial indexes; `asset_purge_audit` | applied | applied | **pending** |
| `20260827T092633Z__snapshot_key_nullable_for_sunset.sql` | `snapshot_key` DROP NOT NULL | applied | applied | **pending** |

Indexes are partial on `WHERE purged_at IS NULL`, so they shrink as the backlog is worked
off rather than growing forever with rows already handled.

`asset_purge_audit` holds one row per batch per run (`asset_type`, `segment`, `phase` ∈
`mark`/`sunset`/`dry_run`, `row_count`, `oldest_item`, `newest_item`, `retention_days`,
`notes`). This is what answers "prove you enforce the policy" without reconstructing it
from application logs.

`admin-node` keeps its **own** `prisma/schema-assessment.prisma` — schema changes must be
mirrored there or its Prisma client cannot see the column.

## Gotchas

- **Object keys are stored BARE in the database**, without the `proctor/` / `videos/` /
  `audio/` folder prefix. `storeProctoringSnapshot` runs the key through
  `getFilenameFromPath()` before insert (`Assessment.js:10571`); the prefix exists only
  on the bucket object, and `generatePreSignedURLImage(key, "proctor")` re-adds it at
  read time. Verified 13,594/13,594 bare on DEV, 573/573 for answer media. Anything
  matching a stored key against a prefixed one silently matches nothing.
- `proctoring_events.evidence_object_key` stores the same bare filename. Those events are
  **kept** — "phone detected at 14:23" is the audit trail and outlives the photo — only
  the pointer is cleared, aged out on the event's own `created_at`.
- **`proctoring_reports.summary` / `timeline` embed no object keys** (0 of 138 reports on
  DEV). They are pure aggregate metrics (`noFaceMs`, `pctEyeContact`, `phoneDetections`).
  A planned JSON scrub was dropped as unnecessary — do not re-add one.
- **DEV and UAT use separate buckets** (`pl_dev_poc` vs `pl-uat-assessment`), so a DEV
  lifecycle rule cannot reach UAT data. PROD's bucket name lives in a ConfigMap, not a
  repo env file.
- **Proctor object keys carry their own date** — `proctor_<assignedId>_<epoch_ms>.jpg` —
  so an orphaned snapshot with no surviving row is still collectable by a prefix rule on
  object age. Video/audio keys are `questionId`-based and carry no date.
- **No environment has data old enough to exercise the sweep naturally.** DEV's oldest
  snapshot is ~218 days and UAT has **0** rows past 365 days, so the job is a permanent
  no-op there and a bug in its SQL would sit unnoticed until PROD, where ~3,000 objects
  are already past retention. `script/purgeExpiredAssets.check.js` exists for this: it
  runs the real mark phase against a shortened window, asserts 29 behaviours, validates
  the destructive SQL with `EXPLAIN` rather than executing it, and reverts everything in
  a `finally`. Run it with
  `set -a; . .env.dev; set +a; node script/purgeExpiredAssets.check.js`.
- **Cost is not the justification for this work.** Everything in scope is roughly
  150–200 GB, about $5/month at Standard rates; tiering saves a couple of dollars. The
  case is privacy exposure and unbounded growth. A cost-based justification will not
  survive scrutiny.
- **Archive tier was rejected deliberately.** Restore takes up to an hour with no
  expedited option, so it would require building a restore-request flow; and its 90-day
  minimum retention makes archive-then-delete cost *more* than staying in Standard.
  Infrequent Access is immediately readable, so the existing presigned-URL path works
  with zero code change.

## Related

- [Proctoring](proctoring.md) — what generates the snapshots
- The `verification/<studentId>.webm` recording is **out of scope** and tracked
  separately: it is student-scoped rather than attempt-scoped, only 3 students of 21,255
  have one on DEV, and no reader was found in admin-, corporate- or institute-node. See
  the device verification gate section in [Proctoring](proctoring.md).
