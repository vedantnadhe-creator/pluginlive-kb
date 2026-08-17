---
type: reference
tags: [service, api, python, fastapi, parsing, cv, jd, ai]
---

# CV & JD Document Parsers (inside fastapi-ai-engine)

**Repo:** `/home/ubuntu/api/fastapi-ai-engine`
**Package:** `DocumentParsing/` · **Routers:** `routers/cv_parser.py`, `routers/jd_parser.py`
**Runs in:** the `fastapiai` container (port 8011), *not* as separate services
**Public (UAT):** `https://fast-api.uat.pluginlive.com`

---

## What changed (2026-08-17, DEV code + UAT deployed)

CV and JD parsing used to be **two standalone services**. Both are now folded
into `fastapi-ai-engine`, so the platform has one FastAPI service and one LLM
gateway path:

| Was | Now |
|---|---|
| CV parser — **Flask**, `resume-parser.<env>.pluginlive.com`, container `resumeparser` (UAT 5011→5012). On DEV it is not even a container: a bare `/usr/bin/python3.10` process behind nginx on `:5012` | `POST /cv-parser/parseResume`, `POST /cv-parser/parseResumeAndUpload` |
| JD parser — FastAPI, `llma-api.<env>.pluginlive.com`, container `llama-backend` / `jdparser-backend` (UAT 8012→8000) | `POST /jd-parser/parse/text`, `/jd-parser/parse/file`, `/jd-parser/parse/s3` |

The other two "LLM calls via FastAPI" workloads needed no move — **Form Data
Normalization** and **CV↔JD Match & Score** were already FastAPI (the latter is
`ResumeMatchScoring/` + `/resume-match/*` in this same engine).

⚠️ **`Jd_Parser` and `mistral-jd-parser` under `~/api/` are dead** — experiments,
no container, no caller. The live JD service was always `Llama-JD-Parser`, and
despite the name **it calls Gemini, not Llama**.

**The old services are still running.** This change only repointed the callers;
nothing has been retired yet (see *Retirement* below).

---

## The rule that matters: PDF extractors are pinned per route

The legacy paths did **not** share one PDF text extractor:

| Route | Extractor |
|---|---|
| CV `/parseResume` | **pdfminer.six** |
| CV `/parseResumeAndUpload` | **PyMuPDF (fitz)** |
| JD `/parse/*` | **PyPDF2** |

These genuinely disagree on the same file (whitespace, line order, multi-column
handling), and the extracted text **is the LLM's prompt input** — so unifying
them silently changes parsed output that lands on candidate profiles and job
records. `DocumentParsing/document_source.py` therefore takes `pdf_engine=` as a
**required parameter with no default**. Do not "tidy" this into one engine.

Two further JD quirks are deliberately preserved: pages are joined with a
**space**, and **empty extracted text is not an error** (the legacy service fed
it to the LLM anyway). JD also dispatches on the **filename extension**, not
magic bytes, so an extension-less URL is rejected as unsupported.

Versions are pinned in `requirements.txt` for the same reason — they were read
off the live processes, not guessed: `pdfminer.six==20240706`, `docx2txt==0.8`
(DEV CV parser), `PyPDF2==3.0.1` (llama-backend image). Re-run
`tests/test_parser_consolidation.py` (38 guards) before bumping any of them.

---

## Callers and configuration

Both callers now reach the engine through the env var they **already had** for
it — no new variable was introduced, and none needed adding on UAT:

| Caller | Env var | UAT value | Calls |
|---|---|---|---|
| `student-node` (`app/services/CvSerice.js`) | **`FASTAPI_URL`** | `https://fast-api.uat.pluginlive.com/` | `cv-parser/parseResume` |
| `corporate-node` (`app/services/jdService.js`) | **`FASTAPI_AI_ENGINE_URL`** | `http://172.17.0.1:8011` | `jd-parser/parse/s3` |

`CV_BE_BASE_URL` and `JD_BE_BASE_URL` are **retired**, along with their
hardcoded DEV fallbacks. `beBaseUrl.AI` is the single engine base URL in both
services and is the one to reuse for any future engine call.

> **This fixed a live cross-environment leak.** `JD_BE_BASE_URL` was never set in
> corporate-node's `.env.uat`, so `beBaseUrl.JD` fell through to its hardcoded
> default `https://llma-api.dev.pluginlive.com/` — **UAT JD parsing was being
> served by the DEV JD parser.** Pointing at the engine removes that.

### Route prefixes and the legacy aliases

Routes are mounted **twice**: under the `/cv-parser` and `/jd-parser` prefixes
(this repo's convention), and at the **legacy root paths** (`/parseResume`,
`/parse/s3`, …) via a `legacy_router` in each module. The aliases exist so a
caller can be rolled back with an env-var change instead of a redeploy. They are
`include_in_schema=False`, so they do not appear in `/docs`. **Delete them —
and the two `include_router(...legacy_router)` lines in `main.py` — once every
caller is on the prefixed paths.**

---

## AI cost attribution

The two parsers each had their **own LiteLLM virtual key** (`resume_parser`,
`llama_jd_parser`), so the gateway dashboard showed a spend line per parser.
Inside the engine every call carries the **engine's** key, so that split would
have been lost. Attribution now comes from the usage ledger instead:
`utils/ai_usage/context.py` maps `cv-parser → CV_Parser` and
`jd-parser → JD_Parser`, plus an exact-path map so the legacy root aliases don't
land in `Unattributed` during the cutover.

Both parsers call **`gemini-2.5-flash`** — the same model
`ResumeMatchScoring` uses. Note the engine has **no central model config**;
model names are hardcoded per call site (`gemini-3-flash-preview` is the
standard for assessment scoring). All LLM calls go through
`utils/get_ai_client.get_gemini_client()` → the LiteLLM gateway. An audit at
consolidation time confirmed **every HTTP endpoint** in the engine already
routes that way; only internal utilities (chroma embeddings, image generation)
still build raw SDK clients.

---

## Blocker before retiring the old services

The engine image does **not** carry the CV parser's credential files —
`auth_creds.json` (Google Drive service account), `oci_config`, `oci_api_key.pem`
(OCI object storage). The UAT `~/api/Resume_parser/USING API/` checkout has all
three.

Consequence:

- **`/cv-parser/parseResume` is unaffected** — it downloads Drive links through
  the public flow and never touches OCI. This is the route `student-node` calls,
  and it is verified working on UAT.
- **`/cv-parser/parseResumeAndUpload` will fail on the engine** until those
  files are provisioned into the image/mount. It archives the original CV to OCI
  and needs the Drive service account for private files.

`/parseResumeAndUpload` has **no in-repo caller** — it is invoked externally with
an `AUTH_KEY` header. It still works on the standalone `resumeparser` container,
which is why nothing broke. **Identify that caller and provision the credentials
before switching it over or retiring `resumeparser`.**

Auth for that route resolves `CV_PARSER_AUTH_KEY` → `AUTH_KEY` → the standalone
service's original key, kept as the fallback so existing callers keep working.
It is a shared secret that has lived in the source tree; rotate it once the
caller is known.

---

## Verification on UAT (2026-08-17)

- `POST /jd-parser/parse/text` → `status: success`, 38 keys, correct title /
  company / skills / cities / CTC, `token_usage` reporting the legacy
  `"Not available"` sentinel (the gateway's usage object uses OpenAI field
  names, not google-genai's — read defensively so it cannot 500 mid-parse).
- `POST /cv-parser/parseResume` → correct student-profile shape
  (`admin`/`education`/`workExperience`/`currentCourse`), education and work
  rows matching the source document.
- Legacy alias `POST /parseResume` → identical result (rollback path intact).
- `student` container → `fast-api.uat.pluginlive.com/cv-parser/parseResume` and
  `corporate` container → `172.17.0.1:8011/jd-parser/parse/s3` both reachable.
  (`corporate` has **no `curl`** — test it with `docker exec corporate node -e`.)

Parity with the old code was checked against the **live** `llama-backend`
container on identical bytes: PDF text extraction and markdown→HTML are
**byte-identical**. Moving pdfminer off its fixed-name scratch file (`./temp.pdf`,
which two concurrent requests clobbered) is likewise byte-identical.

---

## Deploy

Standard `auto_deploy.sh`; the parsers ship with the engine:

```bash
ssh ubuntu@uat.pluginlive.com "cd ~ && ./auto_deploy.sh fastapi-ai-engine <branch>"
ssh ubuntu@uat.pluginlive.com "cd ~ && ./auto_deploy.sh student-node <branch>"
ssh ubuntu@uat.pluginlive.com "cd ~ && ./auto_deploy.sh corporate-node <branch>"
```

`antiword` is already installed in the engine image, so legacy `.doc` support
carried over with no Dockerfile change.

---

## Retirement checklist (not yet done)

1. Provision Drive/OCI credentials into the engine, then move
   `/parseResumeAndUpload`'s external caller.
2. Drop the `legacy_router` mounts once no caller uses the root paths.
3. Stop + remove `resumeparser` (UAT 5011) and `jdparser-backend` (UAT 8012);
   on DEV also kill the bare `Resume_Parser_New.py` process on `:5012` and the
   `llama-backend` container.
4. Delete the dead `~/api/Jd_Parser` and `~/api/mistral-jd-parser` trees.
5. Retire the `resume_parser` / `llama_jd_parser` LiteLLM virtual keys.

⚠️ **Unrelated but live:** the DEV CV parser runs Flask with `debug=True`
publicly reachable — an empty `POST /parseResume` returns a **Werkzeug debugger
page** with a stack trace. That disappears when the standalone service is
retired, but it is worth fixing sooner.
