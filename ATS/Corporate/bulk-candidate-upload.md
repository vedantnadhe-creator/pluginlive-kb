# Bulk candidate upload (LIVE on DEV + UAT since 2026-09-01)

An admin uploads the candidate list a placement cell actually sent — any
columns, no template — instead of waiting for each candidate to fill in the
application form. Every uploaded row becomes a **real applicant** on the role:
it appears under Applicants and enters the evaluation workflow exactly like
someone who applied.

PROD is **pending**.

## Where it lives in the product

Two entry points, both the same flow:

- **Create-role wizard → "Invite institutes & NGOs" (step 4)** — an *Upload
  candidates* card below the two invitation columns.
- **Role page → Applicants tab** — in the empty state, and above the pipeline
  once applicants exist, so a list that arrives later still has a home.

Both offer **Download template** (a two-sheet `.xlsx`, `Candidates` +
`Instructions`) and **Upload candidate list**. The template is a convenience,
never a contract: the pipeline maps whatever columns arrive, so a TPO's own ERP
export works too.

## The mapping review is mandatory

Uploading imports nothing on its own. One LLM call per **workbook** — headers
plus three sample rows, ~1.5K tokens — proposes a header→field mapping, and an
admin confirms or corrects it in a grid before a single row lands. Each row
shows the column, an example value from the file, the destination field, and a
one-clause reason ("sample values are 10-digit").

Mapping once per file rather than reasoning per row is both cheaper and far more
reviewable: a wrong mapping applied to 500 rows is expensive to unpick and
obvious to spot in a grid.

Enforced in the database, not only in service code — `bulk_upload_batches` has a
CHECK preventing a batch leaving `awaiting_mapping` while `confirmed_mapping IS
NULL`.

## Flow

```
upload .xlsx ─▶ corporate-node-v2 stores it (unguessable name)
             ─▶ FDN /api/corporate-bulk/inspect  (fetches the file back by URL)
             ─▶ mapping grid, admin confirms
             ─▶ FDN /api/corporate-bulk/commit
                  · rows → candidates_raw_data (source='corporate_bulk')
                  · returns the applicant projection
             ─▶ corporate-node-v2 enrols each row:
                  insertSubmission() + enqueueScreeningOne()
             ─▶ Applicants tab + evaluation workflow
```

In the wizard the role does not exist yet (its single `POST /roles` fires from
the same screen's **Create role** button), so the mapping is confirmed first and
committed after the role is created. On the role page the commit is immediate.
Import is ordered **after** role creation deliberately: a failure leaves a
retryable batch rather than an orphan.

## Endpoints

`corporate-node-v2` (admin-authed, holds the shared secret):

| Route | Does |
|---|---|
| `GET /v2/roles/candidate-template.xlsx` | the workbook to hand a placement cell |
| `POST /v2/roles/bulk-upload/inspect` | multipart; returns the proposed mapping. Imports nothing, takes no role id |
| `POST /v2/roles/:id/bulk-upload/commit` | applies the confirmed mapping and enrols applicants |
| `GET /v2/roles/:id/bulk-upload/batches` | per-row import status |

`form-data-normalization` (server-to-server, `X-API-Key`):
`/api/corporate-bulk/{inspect,commit,batches}`.

## What screening judges on

The screening stage used to require a résumé. That is wrong for a campus batch —
those candidates have no file, only a spreadsheet row. The **screening stage
card now offers Resume only / Form only / Resume + form**, stored as
`config.screeningSource` on the stage's free-form JSONB config (no migration).

| Mode | Behaviour |
|---|---|
| `resume` | judge the résumé; a candidate without a readable one is recorded as an error, not guessed at |
| `form` | judge the application answers; the résumé is not read |
| `both` *(default)* | use whatever the candidate has, falling back to answers when there is no résumé |

`both` matches the previous behaviour, so roles nobody reconfigures are
unaffected. A résumé that **was** supplied but could not be read still errors
under `resume` and `both` — that signal has caught real parser bugs.

Measured on a 10-candidate campus import: `resume` → all 10 correctly flagged
unjudgeable, `form` → all 10 scored with no errors, `both` → scored via the
answers fallback.

## Gotchas

- **Only sheets the admin mapped are ingested.** Our own template ships an
  `Instructions` tab; without this guard uploading it created 21 junk candidates
  from its prose. Skipped sheets come back as `skipped_sheets`.
- **`PUBLIC_BASE_URL` differs by environment.** It is the app **origin** on DEV
  but already carries `/v2` on UAT. FDN fetches the uploaded workbook over that
  URL, so the builder normalises both forms — otherwise it produces
  `.../v2/v2/api/uploads/...` and 404s. UAT also sets
  `BULK_UPLOAD_FETCH_BASE_URL` explicitly.
- **The fetch URL is unauthenticated.** FDN has no session, so the workbook is
  stored under an unguessable UUID filename — that name is the only protection.
- **The mapper targets a curated 23-field core**, not all 813 slugs in
  `normalized_columns`; that table is self-appending and holds junk like
  `checkbox_testing`. Unmapped columns pass through to `raw_data` untouched for
  the normalization worker, exactly as before.
- **Model is `COLUMN_MAPPER_MODEL`** (default `gemini-2.5-pro`, via the LiteLLM
  gateway). `claude-opus-5` is the intended model once an Anthropic key is
  registered on the gateway.
- **De-duplication is one application per email per role** — the same rule the
  apply form enforces, so re-running an import tops up rather than duplicating.
- **Résumé links are stored but not fetched.** A `Resume Link` column lands in
  `cv_url`; nothing downloads or parses it yet.
- **`chatJson` has no JSON repair**, so roughly 1 in 10 screenings can die on a
  malformed model reply. Pre-existing, affects all screening, not just imports.

## Schema

`candidate_ingestion_schema` (in `uat_pluginlive`, **shared by DEV and UAT**):

- `candidates_raw_data.job_role_id` / `.corporate_id` + `source='corporate_bulk'`
- `bulk_upload_batches` — one row per workbook; proposed vs confirmed mapping
- `candidate_resume_assets` — résumé provenance (created, not yet written to)

DB-Scripts: `Corporate Bulk Candidate Upload/20260831T083545Z__corporate_bulk_candidate_upload.sql`.
Applied DEV + UAT 2026-08-31; PROD pending.

## Deploying

`form-data-normalization` is **excluded from push-to-Development CI/CD** — deploy
it with `./auto_deploy.sh form-data-normalization <branch>` on the target box.
`corporate-react-v2` uses `./auto_deploy.sh corporate-react-v2 UAT` (menu 24);
`corporate-node-v2` is **not** in the UAT deploy menu and is pulled, built and
restarted by hand (`systemctl restart corporate-node-v2.service`).
