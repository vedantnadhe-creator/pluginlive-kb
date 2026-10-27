---
type: reference
tags: [service, frontend, uat, supabase, lovable]
---

# Banking Job Readiness (Candidate Job Readiness Journey)

**Repo:** `PluginLive-Technologies/bankingjobreadiness`, branch `main`
**UAT path:** `/home/ubuntu/bankingjobreadiness` (on the UAT box, directly under `~/`)
**Live URL:** `https://banking.uat.pluginlive.com/`
**Stack:** Vite + React + shadcn/ui SPA — not part of the PluginLive Node/Prisma stack.

> **What the app is (roles, features, content model, AI layer, risks):** see
> `Infrastructure/banking-application-overview.md`. This page is the deploy/incident log.

> **UAT moved off hosted Supabase on 2026-08-07.** UAT now talks to a self-hosted
> Supabase-compatible stack on the same box (`~/banking-sb/`, proxied at
> `https://banking.uat.pluginlive.com/sb`) backed by our own PostgreSQL. The browser still speaks
> `supabase-js`; only the origin changed. **PROD is still on hosted project
> `kbwjokmmzkgjwiqelrdc`.** See `Infrastructure/banking-postgres-migration.md` — read it before
> touching UAT `.env`, migrations or edge functions.

## Why it's off the standard deploy path

This app (and its sibling `ailearning.uat.pluginlive.com`) came in as a Lovable-generated SPA cloned straight into the UAT box's home directory, not under `~/frontend/`. Full Banking releases use `~/banking-sb/deploy.sh`. Since 2026-10-16, `~/auto_deploy.sh banking-functions` dispatches to `~/banking-sb/sync-functions.sh` for functions-only releases (repo functions plus the UAT overlay, then an edge-runtime restart); it does not pull, migrate or rebuild the frontend. Snapshot and review overlay changes first.

## Deploying (frontend)

```bash
cd ~/bankingjobreadiness
cp -a dist ../bankingjobreadiness-dist-backup-$(date +%Y%m%d-%H%M%S)   # nginx serves dist/ live; keep a rollback
git pull origin main   # if package-lock.json is dirty from a prior install, `git checkout -- package-lock.json` first
nvm use 20 && npm install && npm run build
```

### Deploy log

| Date | Commit | Migration applied | Notes |
|---|---|---|---|
| 2026-08-09 | `6c0429b` | `20260808045623` (as idempotent fixup) | 41 commits; date-fns repin removed the need for `--legacy-peer-deps` |
| 2026-08-10 | `8877a68` | `20260810100000_admin_subscription_rbac_menu_access` | 18 commits; adds **Subscriptions & Access** and **RBAC & Reports** to the admin nav; edge functions 81 → 82 (`request-password-reset`) |
| 2026-08-12 | `bade695` | **none** | 9 commits; multilingual AI coach; edge functions 82 → 83 (`elevenlabs-tts`). Ships **three upstream defects** — see *Upstream defects in the 2026-08-12 release*. One needed a local patch to avoid data loss. |
| 2026-08-24 | `6815d28` | `20260824183000_interview_proctoring_lifecycle` (additive, no fixup) | 6 commits; admin password reset across roles, auth-lock re-entry, assessment question dedup, interview proctoring lifecycle. `interview_sessions` 19 → 48 columns. Unit suite 291/301 → **335/335**. |
| 2026-08-25 | `423fd65` | `20260824220000_assessment_question_canonical_uniqueness` (0 rows deleted, no fixup) | 9 commits; raises `LLM_PROVIDER_TIMEOUT_MS` 15000 → 45000 and widens provider failover to 400/404/422 (fixes generation timeouts), adds a DB-level unique index rejecting duplicate prompts per assessment, fixes a detached-ArrayBuffer bug in Gemini TTS. Unit suite 340/341 (1 stale test literal, not a regression — see below). |
| 2026-08-27 | `5b4b5f2` | none (161 migrations unchanged, no new files) | 7 commits (`423fd65`→`5b4b5f2`); fixes taxonomy 400 errors, bulk-created-candidate OTP compatibility (`bulk-create-users` now writes `Otp_<mobile>_1234`, matching the login policy fix from 2026-08-21). No `supabase/migrations` or fixed-up edge function touched. Unit suite 348/349 (same stale `LLM_PROVIDER_TIMEOUT_MS = 15000` literal from 2026-08-25, still not a regression). |
| 2026-08-28 | `6f87c4c` | none | 1 commit; **module topics now auto-link real YouTube videos** — see *Module videos: search queries vs. playable URLs*. Also the day the UAT **YouTube Data API key was finally configured**. Unit suite 370/371 (same stale `LLM_PROVIDER_TIMEOUT_MS` literal). |
| 2026-08-28 | `9ab7c00` | `20260828083515_llm_settings_tts_columns_and_audit_actor_text` (applied) | Schema-only; **no rebuild** (the commit touches no `src/`). Fixes both Admin → LLM Config save failures — see *Admin → LLM Config could not save*. |
| 2026-09-21 | `b505d58` | `20260919100000_institute_city_management` (verbatim), `20260919110000` (verbatim, no-op), `20260919110001_fix_super_admin_enum` (**fixup** — verbatim would CASCADE-drop `has_role`) | 19 commits; **RBAC role filter gains Trainer**; institute/city masters on registration; hallucination-risk badge in AI coach. See *2026-09-21* section. |
| 2026-09-22 | `d0ebf23` | none | 5 commits; `.env.local` finally removed upstream; types.ts regenerated for yesterday's cities/institute_city tables |
| 2026-09-23 | `420de1d` | 3 applied (remediation via fixup), 1 skipped (PilVidya file), UAT delta file | 30 commits; RLS lockdown on 27 tables; trainers see only mapped students; refresh logs out without Remember me. See *2026-09-23*. |
| 2026-09-24 | `b8008e6` | 7 applied verbatim, repair_missing_modules still skipped | 14 commits + admin-login race fix (AuthContext); trainers RLS lockdown; role_master. See *2026-09-24*. |
| 2026-09-25 | `1205677` | 11 applied verbatim; restore_module_topic_catalog skipped | 36 commits: video studio, simulations, curriculum setup workflow. See *2026-09-25*. |
| 2026-09-25 | `0538e22` | 2 applied verbatim | 8 commits: module save fixes; **all published modules now DB-readable by any signed-in user** (entitlement gate frontend-only). See *2026-09-25 (later)*. |
| 2026-09-26 | `1322956` | 3 verbatim, 2 fixups (menu upsert → DO NOTHING; drop+recreate payment RPC) | 23 commits: AI registry/grounding/quality; 4 new VITE gates set true. See *2026-09-26*. |
| 2026-09-28 | `6bf8a7f` (new line after force-push) | 2 new, via fixup (broken role/column refs) | upstream main force-pushed (112 commits discarded, backup bundle kept); ai-content isTechTrack crash + banking persona fixed. See *2026-09-28*. |
| 2026-10-08 | `8de2037` | none | 1 commit: candidate **module view no longer reloads on click / tab switch**. `useAdminModules` + `useAssignedModuleIds` set `loading=true` on every window `focus`, so `TechStudentJourney` swapped `ModuleDetailView` for a skeleton (remount → lost topic/video position). Focus refetches are now silent; the ~5 MB catalog refetch on focus is throttled to 1/min. Same day: **gzip enabled in `banking-react.conf`** (see nginx note). Checks: `~/banking-checks/modfocus.cjs` (remount regression), `modperf.cjs` (Modules tab timing/payload). |
| 2026-10-08 | `365bd2f` | none | 1 commit: **student plan no longer reverts to Free on the next login**. The plan lives in two places: `profiles.subscription_tier` (what the student console shows) and `students.subscription_tier`. `candidate-otp-login` copies the students value onto the profile at **every** OTP sign-in for institute/trainer-onboarded candidates, so a plan set in Admin → Student Plan Mapping (profiles only) was overwritten at the next login. Both admin plan screens (Student Plan Mapping, Student Tier Manager) now write both tables. ~53 existing candidates still have mismatched values (41 = profile free / students beginner); each will take the students value at their next login unless aligned. Checks: `~/banking-checks/planmap.cjs` (admin UI writes both), `tierlogin.cjs` (plan survives login). |
| 2026-10-08 | `598dbc4` | none | 1 commit: **practice transcripts are speech-only and server-transcribed**. Practice Hub → AI Virtual Video Interview used only browser `SpeechRecognition` (missing in Firefox, `network` errors in Brave/Edge, stops after a pause in Chrome) so transcripts were empty; it now records an audio-only track alongside the video and transcribes it via `ai-interview` `action: transcribe` (Gemini native audio, ~2–4 s); browser text is only a live preview; mic-only fallback when no camera. Transcript boxes on Practice Hub and `/practice/interview` are **read-only** (re-record / Retry transcribe instead of typing). Assessment video answers (`StudentAssessmentTaker`) called `transcribe-audio` with `{audio}` but it requires `audioDataUrl` → always 400, empty transcript; now uses the same `ai-interview` path. Note: `VITE_AI_PRACTICE_SESSION_PERSISTENCE_ENABLED` is not set on UAT, so practice interview sessions/answers are scored but not stored. Check: `~/banking-checks/practicestt.cjs` (fake mic → transcript → scored). |
| 2026-10-08 | `eba2249` | none | 1 commit: **Admin → Modules "Map to Module Group" no longer fails with `duplicate key … module_group_items_group_id_module_id_key` (409)**. `syncLegacyModuleGroup` deleted all of a module's `module_group_items` rows then inserted one, while the `modules` trigger `modules_sync_parent_item` already links the new group; two overlapping calls (re-pick before the list reloads, or Save Module) raced delete/delete/insert/insert. Now: delete only links to *other* groups + upsert `ON CONFLICT DO NOTHING`; re-picking the current group is a no-op. Mapping is two-way trigger-synced (`modules.module_group_id` ⇄ `module_group_items`). Check: `~/banking-checks/groupmap.cjs`. |
| 2026-10-14 | `60a67d3c` | 4 applied: `20261014153000_instant_assessment_reports`, `20261014153000_trainer_menu_workspace` (10 new trainer/teacher menu rows; only existing change = `modules` label → "Modules"), `20261014170000_sim_candidate_attempt_isolation` (**fixed before applying**: `x.mode` with no `mode` column parsed as the ordered-set aggregate `mode()` → "WITHIN GROUP is required"; both mode fields now `a.mode`), `20261015120000_practice_assessment_catalog_rows` (45 catalog ids as unpublished drafts) | 14 commits incl. upstream f25d6873/430449dc/faf4994d/7b550207 (+`livekit-client`). Fixes: **Generate Quiz** 500 (ai-quiz redeclared `response` → worker boot SyntaxError); **AI Coach** 401 for signed-in users (`loadCoachContext` called `auth.getUser()` without the JWT; ai-coach pins supabase-js 2.39.3, ai-personal-coach/chat 2.45.0, which ignore the global Authorization header — JWT now passed explicitly); **simulation typed reply** 400 (`confidence: null` rejected by `.optional()` → `.nullish()`); **practice (catalog) assessments** now save a graded attempt with `proctoring_status='practice'` and no proctoring evidence — My Assessment Analytics shows a Practice badge, Proctoring Analytics lists them as "proctoring not recorded"; **trainer My Students search** blank screen (null email/mobile `.toLowerCase()`); trainer accounts tagged **Trainer** (user_roles) instead of "Admin created"; **copy/paste blocked** in text + voice simulations; proctoring **camera box black** (stream attached before the in-test video mounted — snapshots/face checks were black too); **MCQ option lag** (memoized options + transition, whole row clickable, per-question serialized saves). Known upstream issue: `pil-admin/AssessmentAnalytics.tsx:522` uses `Badge` without import. Checks in `~/banking-checks/`: admin5, trainersearch, trainertag, coachprobe, fnprobe, proctorcam, optlag. |
| 2026-10-23 | `3febbbe1` | 3 applied: `20261023090000_get_my_attempt_result`, `20261023100000_learning_hours_report_onboarded_trainer`, `20261023110000_delete_module_group` | 3 commits on top of f5d01e5e. **View Results blank page** (406 on `assessments`): the results page read the assessment + questions through table RLS, which hides an assessment once the candidate's mapping/window ends and always hides practice drafts (18 of 29 completed UAT attempts) — now via `get_my_attempt_result(attempt_id)` (SECURITY DEFINER, owner or admin only, NULL without a session; questions only after completion), practice note, and "This result isn't available" instead of a blank screen. **Admin dashboard Student Learning Tracker trainer filter** was empty: `learning_hours_report` read only `trainer_students` (0 rows on UAT) — now also `students.onboarded_by`, and the dropdown lists the trainer directory. **Trainers could not delete their (assigned) module groups**: direct table delete blocked by admin-only RLS, error ignored ("Group deleted" shown) — now `delete_module_group(group_id)` (SECURITY DEFINER; admin, owning trainer = trainers.id of auth.uid(), or owning institute user; removes `module_group_assignments`, items/access cascade) with real error toasts and an assigned-group warning. Open product decisions (not built): trainer module visibility inherits every module of the institute's students (Demo Trainer sees 56 with none assigned); trainers see every published assessment (no admin→trainer publish mapping). Checks: resultspage, trainerdropdown, admin5. |
| 2026-10-23 | `4e627b90` + `94012d3f` | none | Frontend only. **Live mic audio wave while recording a spoken/video answer** — shared `src/components/shared/AudioWave.tsx` (bar heights from `src/lib/voice/voiceBars.ts`, voice band ~85 Hz–4 kHz) shown only while recording in all 4 recorders: TakeAssessment video question, StudentAssessmentTaker video answer, Practice Hub interview (`PracticeInterview.tsx`) and the module Video Interview Runner. Reads the already-open stream through its own AudioContext → AnalyserNode (never routed to speakers, does not touch the recording or transcript); status flips from "Listening…" to "Can't hear you — speak up or check your mic" after 2.5 s below the `mouthLevel` noise floor. Checks: `~/banking-checks/audiowave.cjs` (practice interview with a speech fake mic: wave hidden before record, bars move, no page errors; does not submit), admin5, journeytabs, swotadmin. |
| 2026-10-25 | `e464c147` (round 13 merge of `feature/ffmpeg-long-form-render`, 16 commits) | 2 applied: `20261024180000_metabase_student_kpi_reconciliation` (rewrites `metabase_student_dashboard_summary/_evidence` views; anon/authenticated revoked, 03_grants metabase% revoke still applies — probe 401), `20261024190000_curriculum_audience_assignment` (`curriculum_assignments.institute_id`, unique trainer audience index after de-dup — 0 duplicate rows on UAT, `assign_curriculum_audiences_v1` SECURITY DEFINER admin/trainer only, `student_has_curriculum`) | **Curriculum delivery**: admins/trainers assign a curriculum to students, trainers, institutes or cohorts; student dashboard shows assigned curriculum activity and learning time. **BI dashboards**: student/trainer/admin period filters, Metabase student KPI reconciliation. **Email**: onboarding emails from bulk-create-users / trainer-bulk-import / send-onboarding-email, `test-email-notification`, password reset via Resend when `notification_gateway_settings.email_provider='resend'`. UAT has provider `generic` and **no `RESEND_API_KEY`** → onboarding emails count as failed (users still created), password reset keeps the old path; set the key + provider to turn email on. Behaviour change: `bulk-create-users` now rejects rows without a valid email. Trainer dashboard duplicate hydration reads removed; signup location list fixed. Merge conflict in `LearningHoursDashboard.tsx` resolved keeping both the trainer directory (d86eb887) and the new load-error/retry state. Rehearsed both migrations in BEGIN…ROLLBACK first; merged tree: build ok, 11 touched test files / 117 tests pass, 4 new type-only tsc errors (unknown→string in MyAILearningPath/StudentCurriculumDashboard, `Object.hasOwn` lib in metabase-embed). Checks: admin5 5/5, journeytabs, swotadmin, metabase (student+trainer embeds), trainermods, resultspage, trainerdropdown (20 options), audiowave, anon probes on new views/RPC (401/42501). |
| 2026-10-25 | `e8330a6b` (round 14 merge of `feature/ffmpeg-long-form-render`, 6 commits) | 2 applied **via new UAT fixups** (`~/banking-sb/fixups/<same name>.sql`): `20261025120000_metabase_reporting_scope_deduplicate` (journey_track from `modules.metadata` — UAT `modules` has no `track`; UNION NULLs cast to the existing view types numeric(6,2)/trend numeric(8,3), else CREATE OR REPLACE VIEW refuses — upstream bug on any DB that already has the view), `20261025130000_metabase_extended_journey_analytics` (`m.id::text = ls.module_id` for text `module_live_sessions.module_id`; `live_session_rsvps` has no `created_at` on UAT → `COALESCE(attended_at, rsvp_at)`; `student_module_topic_progress.module_title` exists in no migration → `m.title`; freshness view `project_progress` branch `student_id::uuid` — the project view emits text, UNION with uuid fails everywhere). New table `curriculum_resource_activity` (RLS on, 0 policies: anon reads `[]`, insert 42501) written via `record_curriculum_resource_activity` (authenticated). 20+ new `metabase_*` views (student/trainer/admin learning paths, curriculum delivery, extended activity, project progress, subscription, cohort benchmarks, interventions, freshness) — anon/authenticated revoked by the 03_grants metabase% tail (probe 401), `metabase_readonly` can read. | Role-based Metabase dashboard filters (track/comparison flags `METABASE_TRACK_FILTER_ENABLED`, `METABASE_COMPARISON_FILTER_ENABLED`, unset on UAT) + de-duplicated metrics; assigned curriculum shown separately from the module catalogue; **students now see a trainer curriculum only when it is assigned to them** (deff7f4a). Rehearsed in BEGIN…ROLLBACK until clean (5 failures fixed in fixups). Merged tree: build ok, 7 touched test files / 101 tests; only new tsc errors are `Object.hasOwn` lib (Deno-safe). Checks: admin5 5/5, journeytabs, metabase (student+trainer embeds), swotadmin, trainermods, resultspage, trainerdropdown, anon probes. |
| 2026-10-27 | `37572bf1` (main = `64b8c2cb` merge of `feat/otp-relay-sms-fallback` + an `-s ours` merge retiring UAT fallback `1118f2c5`) | 2 applied: `20261026180000_email_login_otp` (upstream; challenges/rate-limit tables, drops `sms_gateway_settings.temporary_otp*`), `20261027190000_student_trainer_email_unique` (case-insensitive unique `students_email_unique_ci` / `trainers_email_unique_ci`, `@bankready.app` placeholders exempt; 0 existing duplicates) | **Real login OTP, `1234` gone.** Student/trainer login = registered email or mobile → **6-digit** code, 5 min, single use (upstream HMAC challenge + per-account/network throttle). Delivery: **email first via new provider `pluginlive_relay`** (PluginLive mail relay, sends as `mandate@pluginlive.com`; secrets `MAIL_SERVICE_URL=http://172.17.0.1:5010/send-email` + `MAIL_SERVICE_AUTH_KEY` in `~/banking-sb/functions-secrets.env`, nothing in `email_provider_credentials`, no `EMAIL_CREDENTIALS_ENCRYPTION_KEY` needed); **SMS fallback** via MSG91 DLT OTP template (`MSG91_AUTHKEY`, `MSG91_SMS_OTP_TEMPLATE_ID`, same as assessment platform) when the account has no real email or email fails. Accounts need one deliverable contact. UAT `notification_gateway_settings`: provider `pluginlive_relay`, from `mandate@pluginlive.com`, domain `pluginlive.com`, `login_otp` on — so onboarding / password-reset emails now really send on UAT too. New students/trainers: email mandatory + unique (forms, admin bulk upload rejects missing/repeated emails, bulk-create-users pre-check). Fixed upstream: 4 files ended with a literal `\n` (syntax error; both OTP functions could not boot, migration could not apply). `functions-secrets.env` changes need `docker compose up -d functions`. Verified live: codes issued for QA trainer + test student, relay POST /send-email 200 ×2, wrong code and `1234` rejected, unknown account generic, resend throttled 429, login page 6 slots, admin5 5/5. **Not verified live:** SMS send (would text a real number) and a full sign-in with a received code. `~/banking-checks` candidate scripts that typed `1234` no longer log in. |

`20260810100000` needed **no fixup** — it is `ALTER COLUMN … SET DEFAULT` plus a distinct-union
`UPDATE`, so it is naturally idempotent. Effect on UAT: per-admin `allowed_tabs` went 56 → 58 and
15 → 54 rows, and every row now carries `subscriptions`, `rbac-reports` and
`admin-journey-payment-verification`.

**On UAT, the frontend build is only step 3 of 4.** Since the self-hosted move, a pull that brings
new migrations or edge functions needs those applied too, or the new UI calls tables/functions that
do not exist yet:

```bash
# 1. preserve the self-hosted patches across the pull. As of 2026-08-12 there are FOUR files,
#    not two -- see "Local patches carried on the UAT checkout" below. `git stash push` with an
#    incomplete list silently drops the omitted patch on the next pull.
git stash push -- .env src/lib/adminErrorLogger.ts \
  src/components/pil-admin/LearningPathsManager.tsx src/hooks/useLearningPaths.ts \
  && git merge --ff-only origin/main && git stash pop
# 2. any NEW migration -> add an idempotent copy in ~/banking-sb/fixups/ and apply just that file,
#    then re-run sql/03_grants.sql and SIGUSR1 banking-sb-rest to reload PostgREST's schema cache.
#    Do NOT re-run the whole replay: it would re-execute data backfills against real data.
# 3. ~/banking-sb/sync-functions.sh          # edge functions + fixup overlay
# 4. npm install && npx vite build           # frontend
```

If that `git pull` 403s, the org GitHub token has expired — see `Infrastructure/github-access.md` (the checkout's `origin` URL carries its own token, so the credential store alone is not enough).

### Local patches carried on the UAT checkout

These live **only** on the UAT box as uncommitted working-tree changes. `git status` is the
inventory; every one is marked with a comment naming the reason.

| File | Why | Drop when |
|---|---|---|
| `.env` | self-hosted backend URL + locally-signed keys | never (UAT-specific) |
| `src/lib/adminErrorLogger.ts` | hardcoded hosted URL broke the fetch-interceptor matchers | upstream derives it from env |
| `src/components/pil-admin/LearningPathsManager.tsx` | upstream `2e0fdfb` deletes the learning path on save | upstream fixes the remap |
| `src/hooks/useLearningPaths.ts` | same remap, read side | upstream fixes the remap |

`package-lock.json` also shows modified after an install; that one is disposable
(`git checkout -- package-lock.json`).

### `ELEVENLABS_API_KEY` — SET on UAT since 2026-08-12; AI coach speaks in real voices

`~/banking-sb/functions-secrets.env` (mode `600`) now holds `ELEVENLABS_API_KEY`. It is the **first
and only** third-party secret populated on this stack; the other 13 are still absent.

**`env_file` is read at container create, so `docker restart` does NOT pick up a new secret.** Use:

```bash
cd ~/banking-sb && docker compose up -d functions   # recreates the container
docker exec banking-sb-functions sh -c 'echo $ELEVENLABS_API_KEY' | cut -c1-7   # verify, masked
```

Verified end to end with the exact payload `ttsClient.ts` sends
(`{text, language: lang.code, voiceId: lang.voiceId}`): **15/15 languages return real MP3**
(`ID3` header, ~30–50 KB for a short line, 225 KB for a paragraph), each with its own voice from
`src/lib/indianLanguages.ts`. Every voice id in that file is valid on this account. Distinct
sha256 per request — no caching artefacts.

No frontend rebuild is needed for this: the key is server-side only.

**Cost note:** ElevenLabs bills per character, so every spoken AI-coach reply now draws credits.
Before this key existed the function returned `503 {"error": "ElevenLabs is not connected to this
project"}` and `ttsClient.ts` fell back to `window.speechSynthesis` — that fallback is still the
behaviour if the key is removed or the account runs out of credits, so the feature fails soft.

- **gzip (since 2026-10-08) lives in the banking server block, not global `nginx.conf`** — the global config only gzips `text/html` and never proxied responses, so `/sb/rest` JSON and the JS bundle went out raw. Now: `gzip_proxied any` + JSON/JS/CSS/SVG types, and `gzip off` in `/sb/functions/` (SSE streams must not be buffered). Effect on the candidate Modules tab: API 4.9 MB → 1.1 MB on the wire, main bundle 4.57 MB → 1.30 MB. Backup: `/etc/nginx/sites-available/banking-react.conf.bak-20261008*`.
- **Known slow spot (open):** the Modules tab downloads every module's full topic content (`admin_module_topics` + `topics`, `select=*`, ~4.5 MB raw) because `ModuleDetailView` reads content from the same `useAdminModules` catalog; and `topics` takes ~1.2 s server-side because the RLS policy calls `module_visible_to()` per row (735 rows). Fix = list-columns-only catalog + lazy per-module content, and a set-based RLS check; needs an RLS dry run.
- nginx (`/etc/nginx/sites-enabled/banking-react.conf`) serves `dist/` as static files directly — no service/container restart needed, nginx picks up the new build immediately. Because there is no container swap, a failed build leaves a **half-updated live site** — back `dist/` up before building.
- `.env` holds the backend URL + anon key; `VITE_*` vars are baked in at build time. **On UAT these
  now point at `https://banking.uat.pluginlive.com/sb` and the keys are signed with the self-hosted
  stack's `JWT_SECRET`, not the hosted project's** — the two sets are not interchangeable.

### `--legacy-peer-deps` — NO LONGER NEEDED (as of 2026-08-09)

Upstream repinned `date-fns` from `^4.4.0` to `3.6.0`, which satisfies
`react-day-picker@8.10.1`'s `^2||^3` peer range. Plain `npm install` now succeeds; verified on the
UAT box at commit `6c0429b`. Keep the note below for context on older checkouts.

### (historical) `--legacy-peer-deps` was mandatory (2026-08-04 → 2026-08-09)

Plain `npm install` **and** `npm ci` both fail with `ERESOLVE`: `react-day-picker@8.10.1` declares `peer date-fns@"^2.28.0 || ^3.0.0"` but the repo pins `date-fns@4.4.0`. This is stale peer metadata in `react-day-picker`, not a real incompatibility. Use `npm ci --legacy-peer-deps` — `ci` keeps the install lockfile-exact, `--legacy-peer-deps` just skips the peer check.

### The repo now ships a tracked `.env.local` — check it before every build

As of the 2026-08-04 pull, `.env.local` and `.env.example` are **committed to the repo** (`.gitignore` has no env entries), left over from a Lovable/vly scaffold. `.env.local` contains dead Convex vars (`VITE_CONVEX_URL`, `CONVEX_DEPLOYMENT="dev:quaint-gecko-803"`) plus `VITE_VLY_APP_ID` / `VITE_VLY_MONITORING_URL`.

**Vite loads `.env.local` at higher priority than `.env`.** Today this is harmless because `.env.local` defines no `VITE_SUPABASE_*` keys, so the Supabase config in `.env` still wins — but it is a live landmine: if anyone ever commits a `VITE_SUPABASE_*` value into `.env.local`, it will **silently override the UAT `.env` and repoint the built bundle at another backend**, with no build error. Diff `.env.local` after every pull.

The app is still entirely Supabase — 229 source files reference Supabase, zero reference Convex, there is no `convex/` directory and no `convex` dependency. The Convex vars are dead weight, not a migration in progress.

### Verifying a build before you walk away

`dist/` is live the instant it's written, so verify in place:

```bash
# 1. Correct backend baked in, no stray envs
cd ~/bankingjobreadiness/dist
# On UAT since 2026-08-07 this must be EMPTY — any hit means a stale, pre-migration
# build that would send UAT traffic back to the hosted project.
grep -rhoE 'https://[a-z0-9]+\.supabase\.co' . | sort | uniq -c        # expect NONE on UAT
grep -rhoE 'https://banking\.uat\.pluginlive\.com/sb' . | sort -u      # expect this instead
grep -rhoE '([a-z0-9-]+\.convex\.(cloud|site)|[a-z-]+\.dev\.pluginlive\.com)' . | sort -u   # expect empty

# 2. Site actually renders (SPA — a 200 on index.html proves nothing)
curl -s https://banking.uat.pluginlive.com/ | grep -o 'assets/index-[A-Za-z0-9_-]*\.js'   # must match dist/index.html
```

Then headless-load the page (`playwright-core` lives in `~/browser-mcp/node_modules`, browser at `/usr/bin/chromium-browser`) and expect **no `pageerror`** and a non-empty `#root`.

A `localhost:9999` string in the bundle is expected — it comes from vendor code (`undici`'s mock-agent and the `supabase-js` UMD build), not app code.

**Expected-noise gotcha:** on load you will see three Supabase REST calls to `/rest/v1/{assessments,profiles,modules}` report `net::ERR_ABORTED` in devtools. They are **not** failures — each returns HTTP 200 first and is then aborted by the app's own `AbortController`/React StrictMode cleanup. Log the `response` event, not just `requestfailed`, before chasing these.

## Upstream defects in the 2026-08-12 release (`bade695`)

Three separate problems shipped in these 9 commits. All were found during the deploy; one was
patched locally, two are reported and left as upstream's call.

### 1. `2e0fdfb` "Fix database schema errors" DELETES learning paths — patched locally

The commit remapped `learning_path_assignments` → `learning_paths` in four places. Assignments are
a **different entity**, and one of those places is the edit-save path:

```js
// upstream, LearningPathsManager.tsx handleSave()
await supabase.from("learning_paths").update({...}).eq("id", pathId);   // update the path
await supabase.from("learning_path_modules").delete().eq("path_id", pathId);
await supabase.from("learning_paths").delete().eq("id", pathId);        // ...then DELETE it
```

Editing and saving any learning path deletes it. It fails **silently**: there is no FK from
`learning_path_modules`, and neither that call nor the follow-up assignment insert checks `.error`,
so the code reaches `toast.success("Learning path updated")` with the row already gone. 11 real
learning paths on UAT were exposed to this, one admin click each.

Reverted on the UAT checkout in `LearningPathsManager.tsx` (2 spots) and `useLearningPaths.ts`
(2 spots), each marked `LOCAL PATCH (2026-08-12)`. `learning_path_assignments` exists here with
exactly the columns the code inserts (`path_id, college, department, degree`). **Drop the patch
once upstream fixes it.**

### 2. The same commit points 4 admin queries at columns that do not exist

Also part of `2e0fdfb`, but read-only, so it was **left as shipped**. It remaps `rbac_*` → `admin_*`
and `quiz_question_bank` → `assessment_questions`, and **23 of the selected columns do not exist**
on the new tables. Every column the *old* code selected does exist on the *old* tables, so this is a
regression against this schema, not a fix:

| Frontend now queries | Result | What it replaced |
|---|---|---|
| `admin_tab_permissions(id, role_code, menu_key, menu_label, actions, scope)` | **400** | `rbac_role_permissions` — **142 rows** |
| `admin_tab_permissions(id, user_id, menu_key, action, effect, reason, created_at)` | **400** | `rbac_user_permission_exceptions` — 0 rows |
| `admin_audit_log(id, actor_name, action, entity_type, entity_id, reason, occurred_at)` | **400** | `rbac_audit_log` — 2 rows |
| `admin_audit_log(id, user_id, tenant_name, menu_key, …)` | **400** | `rbac_menu_access_log` — 0 rows |

`admin_tab_permissions` really has `(user_id, allowed_tabs, updated_by, updated_at, created_at, role)`;
`admin_audit_log` has `(id, actor_user_id, action, target_user_ids, details, created_at)`.

Visible effect: **Admin → RBAC & Reports → Permission Matrix renders empty** (the header counts come
from `profiles`/`user_roles`, which still work). `rowsOrEmpty()` swallows the error into `[]`, so
there is no crash and no toast — only a `console.warn` and a 400 in the nginx log. `QuestionBankViewer`
is hit the same way via the non-existent `assessment_questions.metadata`.

These four 400s are the **only** non-2xx `/sb/` responses in a full authenticated admin walkthrough.
Expect them until upstream fixes the mapping; don't chase them as a stack problem.

### 3. `bade695` "Update MCP function bundle" cannot run anywhere — pinned via fixup

Upstream replaced the 174-line inlined `supabase/functions/mcp/index.ts` with an 8-line stub whose
entry import is a **Windows absolute path** passed as an `npm:` specifier:

```ts
import mcp from "npm:C:\\Users\\Prakash\\OneDrive\\Documents\\Default Project\\bankingjobreadiness\\src\\lib\\mcp\\index.ts";
```

The Lovable Vite plugin regenerated it on a Windows dev machine and baked in that machine's local
path. Proof it cannot resolve on any other host:

```
$ docker exec banking-sb-functions edge-runtime bundle --entrypoint .../mcp/index.ts
Error: failed to create the graph
Caused by: npm package 'C:\Users\Prakash\...\index.ts' does not exist.
```

**But this file is a build artifact, not source.** `vite.config.ts` loads `mcpPlugin()` from
`@lovable.dev/mcp-js/stacks/supabase/vite`, which **regenerates
`supabase/functions/mcp/index.ts` on every `npm run build`** from `src/lib/mcp/index.ts`, baking
`projectRef` in from `VITE_SUPABASE_PROJECT_ID`. Two consequences:

* Our own build **overwrites** the Windows stub with a correct inlined bundle, so the committed
  breakage never reaches the stack — *provided you build before syncing functions*. The documented
  4-step order (functions at 3, frontend at 4) is backwards for this one file; run
  `sync-functions.sh` again after the build, or accept the fixup below as the thing that ships.
* That file showing as `modified` in `git status` after a build is **normal**, not a hand patch.
  Do not add it to the stash list.

`~/banking-sb/function-fixups/mcp/index.ts` pins a known-good bundle and wins over both versions.
Note the general hazard: `function-fixups/` entries are *whole files*, so a fixup that outlives its
reason silently reverts upstream work on the next `sync-functions.sh`. Diff each fixup against the
repo after a pull that touches it.

### `edge-runtime bundle` is the side-effect-free way to check all functions

Better than probing endpoints, which can fire real work (`seed-admin-user` resets the admin
password; MSG91/Twilio send real messages). `bundle` builds the full module graph without executing
anything, and it is what caught defect 3:

```bash
docker exec banking-sb-functions sh -c '
for d in /home/deno/functions/*/; do
  edge-runtime bundle --entrypoint "$d/index.ts" --output /tmp/b.eszip -q >/tmp/err 2>&1 \
    || { echo "FAIL: $(basename $d)"; tail -3 /tmp/err; }
done'
```
83/83 resolve as of 2026-08-12. Note `OPTIONS` is **not** a boot probe — the dispatcher
short-circuits it before spawning a worker.

## `mcp` is broken on the self-hosted stack (not fixable in the app)

Independent of the bundle regression above, the `mcp` function cannot serve on this stack.

`@lovable.dev/mcp-js` rejects a non-https `auth.issuer` at module init. The fixup derived it from
`Deno.env.get("SUPABASE_URL")`, which inside `banking-sb-functions` is the **internal** origin
`http://gateway:80` — so every call died with `500 function worker failed`
(`auth.issuer must use https://`). This had been broken since the migration; earlier "all functions
boot clean" checks did not catch it because a resolvable module graph is not a working function.

Repointed to the public origin (`SUPABASE_PUBLIC_URL`, defaulting to
`https://banking.uat.pluginlive.com/sb`). The worker crash is gone, but it now returns a clean
`500 {"error":"oauth configuration error"}`, because **self-hosted GoTrue serves no OAuth discovery
document** — both `/.well-known/oauth-authorization-server` and `/.well-known/openid-configuration`
404, and our GoTrue mints tokens with **no `iss` claim** at all (`GOTRUE_JWT_ISSUER` unset). Hosted
Supabase provides those endpoints; that is the gap.

Fixing it means serving a discovery document at that well-known path (e.g. a static JSON via nginx)
— a deliberate change, not a redeploy step. The app UI does not use `mcp`; nothing else is affected.

## Backend (Supabase) — separate deploy step, not covered by the frontend build

`supabase/functions/*` (Edge Functions, Deno) and `supabase/migrations/*` (SQL) live in the same repo but are **not** deployed by `npm run build`.

> **On UAT this is no longer a Supabase-CLI step.** Since 2026-08-07, functions deploy with
> `~/banking-sb/sync-functions.sh` (rsync + fixup overlay + restart the edge runtime), and all
> **119** migrations are applied to `banking_uat` via `~/banking-sb/replay-migrations.sh`. The
> drift described below is **resolved on UAT** and applies only to the hosted project, which still
> backs PROD. See `Infrastructure/banking-postgres-migration.md`.

**The frontend deploy and the Supabase deploy have drifted apart — treat the backend as a separate, explicit step.** As of 2026-08-04 the UAT checkout carries **81 edge functions and 118 migrations**. A fresh `npm run build` ships UI that calls tables and functions which do not exist in the Supabase project. If a newly-deployed screen 404s or errors on a `/functions/v1/...` call, this drift is the first thing to check — not the frontend build.

### Half the migrations have NEVER been applied — split by who authored them (verified 2026-08-04)

**Scope: the hosted project only (which now backs PROD). On UAT all 119 are applied.**

The 118 migrations fall into two groups, and **only one group is live on hosted**:

| Filename style | Author | Count | Applied to Supabase? |
|---|---|---|---|
| `<ts>_<uuid>.sql` (e.g. `20260727022209_774a0969-…`) | Lovable editor | 57 | **Yes** — Lovable applies these automatically when created |
| `<ts>_<description>.sql` (e.g. `20260728000000_module_prerequisites_…`) | hand-written by a developer | 61 | **No — never** |

Nobody has ever run `supabase db push` from this box, so every hand-written migration from **`20260630073000_llm_provider_configs.sql` (2026-06-30) through `20260801000000_interview_proctoring_settings.sql` (2026-08-01)** exists only in git. The date is *not* the discriminator — a Lovable migration from 2026-07-27 is live while a hand-written one from 2026-07-10 is not.

Verified by probing PostgREST with the anon key (a missing table returns `404 PGRST205`, an RLS-blocked one returns `200 []`) — 8/8 sampled hand-written tables missing, 6/6 sampled Lovable tables present:

```bash
KEY=$(grep '^VITE_SUPABASE_PUBLISHABLE_KEY=' ~/bankingjobreadiness/.env | cut -d= -f2- | tr -d '"')
curl -s "https://kbwjokmmzkgjwiqelrdc.supabase.co/rest/v1/<table>?select=*&limit=1" \
  -H "apikey: $KEY" -H "Authorization: Bearer $KEY"
```

Confirmed **missing**: `students`, `payment_requests`, `ai_practice_sessions`, `rbac_role_permissions`, `ai_coach_threads`, `module_group_assignments`, `admin_modules`, `module_prerequisites`, `module_live_sessions`, `live_session_rsvps`, `student_module_topic_progress`, `module_analytics`, `trainer_module_assignments`, and the column `interview_sessions.proctoring_settings` (`42703`).

Confirmed **present**: `agent_threads`, `domains`, `module_taxonomy_history`, `institutes`, `coding_submissions`, `module_trainers`, `assessments`, `profiles`, `modules`.

**Consequence:** any feature delivered by a hand-written migration — payments/journey access, admin RBAC entitlement reports, AI coach threads, tech AI-practice sessions, domain/module group visibility, module prerequisites, live sessions, trainer assignments, AI-interview proctoring settings — is **dead on UAT** no matter how many times the frontend is rebuilt. Applying them needs the Supabase CLI (not installed on the box) plus project credentials, and should be reviewed first: several are `resync`/`seed`/`backfill` scripts that mutate data, and `20260728150000_fix_security_vulnerabilities.sql` changes RLS.

**Resolved:** the `bulk-create-users` "Not authorized" bug (service-role client calling `rpc("has_role")`, which lives in the locked-down `private` schema and is executable only by `authenticated`) was previously carried as an uncommitted local patch on the UAT box. It has since **landed upstream** — `supabase/functions/bulk-create-users/index.ts` now authenticates the caller with an anon-key client and reads `user_roles` directly via the service-role client, matching `admin-confirm-candidates` / `bulk-export-enqueue` / `assessment-report`. No local patch to preserve across pulls anymore. It still needs to be *deployed* to Supabase per the drift note above.

## 2026-08-20 — redeployed to `4a67e19`

Advanced Banking UAT by 14 commits from `6119771` to `4a67e19`. Applied the one new migration,
`20260821000000_assessments_schema_cache_repair.sql`, which preserves the existing
`assessments.assigned_colleges` default and requests a PostgREST schema reload. PostgREST was then
fully restarted, the changed `generate-assessment-questions` edge function was synced, and the
frontend rebuilt with the self-hosted `/sb` configuration.

Verification: site and both REST/Auth API roots return 200; unauthenticated `seed-admin-user`
returns 401; all Banking stack containers are up; function logs contain no new boot/worker errors;
browser E2E passed landing, admin login, protected modules, and the authenticated admin console
with zero page errors, hosted-Supabase requests, or API errors. Snapshot:
`~/banking-predeploy-20260820T092104Z/`.

## 2026-08-20 (second run) — redeployed to `a79370c`

Advanced Banking UAT by 4 commits from `4a67e19` to `a79370c` (`6c46066` Sync remote mcp index
changes, `b5a3e13` Work in progress, `06213f7` Changes, `a79370c` Removed stale vite config file).
Clean fast-forward, **no new migrations**, so this was a function sync plus a frontend rebuild.

### The release is a near no-op, and its one real change is a type regression

The four commits look substantial per-commit (±171 lines in `supabase/functions/mcp/index.ts`, a
stray `vite.config.ts.timestamp-*.mjs` added then deleted), but they add and revert each other.
The **net** `git diff 4a67e19..a79370c` is three deleted lines in
`src/integrations/supabase/types.ts`: `assigned_colleges: string[]` removed from the `assessments`
`Row`/`Insert`/`Update` types.

That removal is wrong, and it directly contradicts the migration applied the day before:

* `banking_uat.public.assessments.assigned_colleges` **exists**, `ARRAY`, default `'{}'::text[]`
  — put there by `20260821000000_assessments_schema_cache_repair.sql`.
* PostgREST serves the column fine (`/rest/v1/assessments?select=id,title,assigned_colleges` → 200
  with `"assigned_colleges":[]`).
* The app reads and writes it in four places — `useAssessments.ts`, `AssessmentCreator.tsx`
  (`assigned_colleges: assignedColleges` on save) and `StudentAssessmentTaker.tsx`
  (`a.assigned_colleges.length === 0 || a.assigned_colleges.includes(studentCollege)`, i.e. the
  college-scoping rule for which assessments a student may see).

**It is inert for the deployed bundle** only because `npm run build` is plain `vite build` with no
`tsc` step — Vite strips types without checking them. So the shipped JS is unchanged. The cost is
that the generated types now lie about the schema: anyone running `tsc`, relying on IDE
type-checking, or regenerating from these types will be told a live column does not exist. If a
typecheck is ever added to the build, this breaks it. Fix belongs upstream (regenerate types
against the current DB), not on the box.

### Local patches on the UAT checkout survived the pull — re-verify after every deploy

The UAT checkout carries four **uncommitted** local patches. The pull was done as
`git stash push -- src/ supabase/ package-lock.json` → `git merge --ff-only origin/main` →
`git stash pop`, which kept all four:

| File | Patch |
|---|---|
| `src/components/pil-admin/LearningPathsManager.tsx` | edit-save deletes `learning_path_assignments`, **not** `learning_paths` |
| `src/hooks/useLearningPaths.ts` | assignments read points at `learning_path_assignments` |
| `src/lib/adminErrorLogger.ts` | `SUPABASE_URL` from `import.meta.env.VITE_SUPABASE_URL`, not the hosted project |
| `supabase/functions/mcp/index.ts` | `projectRef = "banking-uat-selfhosted"` |

**Upstream still has not fixed the learning-path data-loss bug** (`2e0fdfb`), so the patch is still
load-bearing: without it, editing and saving any learning path deletes it while the UI reports
success. Verified in the *built bundle*, not just the source — the only
`from("learning_paths").delete()` in `dist/` is the explicit "Learning path deleted" button; the
edit-save path emits `from("learning_path_modules").delete()...from("learning_path_assignments").delete()`.
`learning_paths` still holds its 11 rows.

### Verification

Site 200; `/sb/rest/v1`, `/sb/auth/v1/settings`, `/sb/storage/v1/bucket` all 200; unauthenticated
`seed-admin-user` → 401; 83 edge functions synced with 3 fixups (`live-session-rsvp`, `main`,
`mcp`), dispatcher intact, zero boot errors; all 7 stack containers up.

* **AI coach** — 200, first byte **51 ms**, streamed SSE chunks from real `gemini-2.5-flash`
  (not the built-in fallback). Both earlier fixes still hold: the `llm_provider_configs` gemini key
  and `proxy_buffering off` in nginx.
* **TTS** — 200, `provider: elevenlabs`, `mimeType: audio/mpeg`, 28,465 bytes of real MP3 (`ID3`).
* **Payments RPC** — `submit_payment_request` resolves in the PostgREST schema cache and its
  ownership check fires (`42501 Not allowed to submit payment for this student` for a bogus
  student). `payment_requests` still 0 rows — the probe wrote nothing.
* **Browser E2E** — 6 anonymous routes and the authenticated admin console (User Management,
  Institutes, Subscriptions): **0 page errors, 0 hosted `*.supabase.co` requests, 0 `/sb` 4xx/5xx**.
* **Unit tests** — 291 passed / 10 failed (301). Identical at the previous commit `4a67e19`
  (run in a throwaway worktree), so this release adds **no** test regressions.
* **Data** — 121 public tables, 62 profiles, 62 auth users, 13 assessments, 11 learning paths.

Backups: `~/banking-sb/banking_uat_predeploy_20260820T113939Z.dump`,
`~/banking-sb/functions-predeploy-20260820T113939Z.tar.gz`,
`~/bankingjobreadiness/dist.bak-predeploy-20260820T113939Z/`, `.env.bak-predeploy-20260820T113939Z`.

## 2026-08-21 — candidate OTP login policy fix (`2a2a477`)

Candidate `9820065335` appeared correctly in the admin candidate list but candidate login returned
"Account not found". The data was not missing: `profiles.user_id` matched the confirmed
`auth.users.id`, the profile was active/approved, and the auth email was the expected
`9820065335@bankready.app`.

The actual defect was the demo OTP password contract in `Login.tsx`. It generated
`otp_<mobile>_1234`, while self-hosted GoTrue requires at least one lowercase letter, uppercase
letter and digit. GoTrue rejected that value as `weak_password`, and existing imported identities
could not authenticate with the password the UI always submitted. Changed the internal derived
password to policy-compliant `Otp_<mobile>_1234`; the visible OTP remains `1234`.

Reset only `9820065335@bankready.app` through GoTrue's admin API using
`set-user-password.sh`, rebuilt the frontend, and pushed the source fix. Verification: the exact
password-grant request now returns HTTP 200 with the expected user UUID and an access token; the
served bundle contains the new contract; the linked profile remains active and approved. Rollback
frontend copy: `~/bankingjobreadiness-dist-backup-loginfix-20260821T*`.

Follow-up browser verification used a fresh Chromium context against `/login/candidate`: mobile
`9820065335` + visible OTP `1234` submitted the new `Otp_` credential, authenticated successfully,
redirected to `/candidate/home`, and rendered the student console. An already-open tab from before
the build continued executing the old in-memory JavaScript and produced one more 400 until reloaded;
GoTrue logs distinguished that stale-client attempt from the fresh successful flow.

## 2026-08-21 — redeployed to `251f18a`

Advanced two commits from `2a2a477` (one feature commit plus its merge). Applied the one new
migration, `20260822000000_module_group_id_columns.sql`, transactionally as `banking_owner`; no
self-hosted fixup was needed. It adds nullable `module_group_id uuid` foreign keys to both `modules`
and `admin_modules`, referencing `module_groups(id) ON DELETE SET NULL`, plus indexes on both
columns. Existing data was unchanged: `modules` has 51 rows and `admin_modules` has 65, with zero
mapped values until admins begin assigning groups.

Reapplied grants, fully restarted PostgREST, rebuilt the frontend with the UAT environment, then
resynced all 83 edge functions with the three standing fixups. Verification: site and auth settings
200; both new columns return 200 through PostgREST; both foreign keys and indexes exist; all seven
containers are up and the database is healthy; zero new function boot errors; no hosted Supabase
data-plane URL in the bundle. A fresh Chromium candidate login for `9820065335` using OTP `1234`
successfully redirected to `/candidate/home` and rendered the student console.

Rollback assets use stamp `20260821T071010Z`: database dump and functions archive under
`~/banking-sb/`, frontend copy at `~/bankingjobreadiness-dist-backup-20260821T071010Z`, and the
checkout-local `.env` backup in `~/bankingjobreadiness/`.

## 2026-08-21 (third run) — redeployed to `5add773`

Advanced two frontend-only commits from `251f18a`: improved password-recovery session/error
handling and added missing dialog descriptions to admin domains, module groups, RBAC and admin
dialogs. There were no new migrations and no edge-function source changes, so no database work was
required. Preserved all four standing UAT source patches and the self-hosted `.env`, rebuilt the
frontend, then resynced the generated MCP bundle and the three function fixups.

Verification: new `index-UREdX1mg.js` asset is served; site and auth settings 200; all seven stack
containers up with the database healthy; zero function boot errors; no hosted Supabase data-plane
URL in the bundle. Fresh Chromium loads of `/reset-password` and `/login/candidate` had zero page
errors and zero `/sb` API errors. Candidate `9820065335` with OTP `1234` still authenticates and
lands on `/candidate/home`. Frontend and `.env` rollback copies use stamp `20260821T110647Z`.

## 2026-08-21 (fourth run) — deployed `f56a5d5`, repaired to `e44a897`

The incoming commit changed `ai-assessment` to use the shared multi-provider LLM path and added a
deterministic fallback; there was no migration. It also committed the recurring invalid Windows-path
MCP artifact. The build regenerated MCP and the standing UAT fixup overlaid it, so that artifact was
not deployed.

An authenticated live generation probe found two independent upstream API-contract defects that a
static bundle check did not catch: `fallbackJsonForFeature` existed in `_shared/llm.ts` but was not
exported, causing a worker boot error; after exporting it, both call sites destructured a nonexistent
`response` property even though `callLlmChatCompletion` returns `Response` directly. Fixed and pushed
as `b502309` and `e44a897`, then resynced all 83 functions with three fixups.

Final verification: an authenticated `ai-assessment` generation request returns HTTP 200 with one
MCQ and no error; site and auth settings 200; all seven containers up with the database healthy;
clean post-fix function logs; deployed MCP has no Windows path; candidate `9820065335` still logs in
with OTP `1234` and reaches `/candidate/home`. No database migration was required. Rollback assets
use stamp `20260821T153931Z`: function archive under `~/banking-sb/`, frontend and `.env` copies in
the usual Banking paths.

### Probing the stack with a minted JWT — the `session_id` trap

To test authenticated paths without touching anyone's password, mint an HS256 token with the stack
`JWT_SECRET` (claims: `sub`, `aud`/`role` = `authenticated`, `email`, `iat`, `exp`).

**Do not add a `session_id` claim.** GoTrue validates it against `auth.sessions`, so an invented one
makes `/auth/v1/user` return **403**; supabase-js then tries to refresh, fails, and every following
request 401s. That produces a browser run full of `/sb` 4xx that look like a broken deploy but are
purely an artefact of the probe. Confirmed by running both tokens side by side: with `session_id`,
`/auth/v1/user` → 403; without it, `/auth/v1/user`, `/rest/v1/institute_subscriptions` and
`/functions/v1/admin-candidate-auth-status` all → 200.

Two more gotchas when probing:

* `ai-personal-coach` takes `{studentId, messages:[{role,content}]}` — `message` is rejected, and
  `studentId` must be the **auth user id** or a `students.id` the caller owns; `profiles.id` is a
  different key (`profiles.user_id` is the auth link) and yields `403 Student does not belong…`.
* The stack database is **`banking_uat`**, not `postgres`. `psql -U postgres` with no `-d` lands in
  an empty database and reports 0 public tables — not a wiped stack.

## 2026-08-24 — redeployed to `63d9eb3` (13 commits, 2 migrations)

Advanced Banking UAT from `c8a66c9` to `63d9eb3`. The five standing UAT source patches were stashed
across the pull and restored intact (two `LOCAL PATCH` blocks each in `LearningPathsManager.tsx` and
`useLearningPaths.ts`, the `import.meta.env` derivation in `adminErrorLogger.ts`, the
`banking-uat-selfhosted` MCP project ref, and the self-hosted `.env`). None of the 13 incoming
commits touched a patched file, so the pull was conflict-free.

### Both migrations were partially pre-applied — replay was still required

`20260823105238` creates `student_module_progress`, `student_assessment_scores` and
`proctoring_defaults`. **All three tables already existed** and held live data (123 / 18 / 1 rows),
so every `CREATE TABLE IF NOT EXISTS` was skipped. What the file did add was a **second, wider set of
RLS policies** on tables that already had narrower ones. Postgres OR-combines permissive policies, so
on `student_module_progress` the pre-existing `student_module_progress owner write` policy is now
superseded by the migration's `FOR ALL TO authenticated USING (true) WITH CHECK (true)` — **any
authenticated user can now write any student's progress row**. This is the same widening pattern
already recorded for `public.students`; it is upstream's shipped migration, applied as-is.

`20260824015329` adds `provider_key` to `llm_provider_configs` and keeps it in sync with `provider`.
The **column already existed** but the trigger, the unique index and the `provider` `DROP NOT NULL`
did not — the file was genuinely half-applied. Replaying it completed the other three steps. Checked
for duplicate `(provider_key, application_feature)` pairs first; there were none, so the unique index
built cleanly. Both files replayed under `--single-transaction -v ON_ERROR_STOP=1` with no errors.

PostgREST was **fully restarted** (not `HUP` — see the 2026-08-18 note). Logs confirm the reload:
128 Relations, 52 Relationships, 32 Functions. All four affected tables and the `provider_key`
column return 200 through `/sb/rest/v1`.

### Candidate `9820065335` was locked out again — by a deliberate password change, not a regression

The OTP login broke again between deploys. The auth row was intact (confirmed, `role=authenticated`,
not banned), but `extensions.crypt()` proved the stored bcrypt hash **did not match** the derived
`Otp_<mobile>_1234`, and `updated_at` was `2026-08-23 10:49:58` — **58 seconds after a successful
login at 10:49:00**. `recovery_sent_at` is NULL, so this was not the forgot-password flow: it was
`PasswordChangeForm.tsx` (`supabase.auth.updateUser({password})`) from inside the candidate
dashboard.

**This is a product defect, not a deploy problem.** The candidate login screen is **OTP-only** — it
derives the password from the mobile number and has no password field — yet the candidate dashboard
ships a change-password form. Any candidate who uses it permanently locks themselves out of the only
candidate login path. `ResetPassword.tsx` and the candidate "Forgot Password?" link have the same
end state. Either remove the candidate change-password affordance or give the candidate tab a real
password field.

The credential was restored with `~/banking-sb/set-user-password.sh 9820065335 'Otp_9820065335_1234'`.
Note this **overwrites whatever password the account holder set on 08-23**; that profile is
`Prakash Chinnadurai`, `role=admin`, so if that password was deliberate for the Admin tab it must be
set again.

Scope check across all 46 `@bankready.app` users: **51 auth users have no password at all**
(the imported-CSV accounts described under `set-user-password.sh`), and 10 have a password that is
not the derived OTP one. Only `9820065335` was repaired.

### Verification

Site 200 (89 ms); `/sb/rest/v1` and `/sb/auth/v1/settings` 200; `student_module_progress`,
`student_assessment_scores`, `proctoring_defaults`, `llm_provider_configs` and the new `provider_key`
column all 200; 83 functions synced with the three standing fixups; zero function boot errors; all
seven stack containers up with the database healthy. The bundle contains **no hosted
`*.supabase.co` data-plane URL** and 19 self-hosted `/sb` references. The deployed `mcp` bundle has
no Windows path. `ai-personal-coach` streams SSE from a real `gemini-2.5-flash` (200, TTFB 50 ms);
`elevenlabs-tts` returns 200 with a 39 KB base64 MP3 (`ID3`). Candidate `9820065335` with OTP `1234`
returns a 200 token and reads its profile 200. A Chromium load of `/login/candidate` rendered the
full candidate tab with no page errors.

Rollback assets use stamp `20260824T035130Z`: `~/banking-db-20260824T035130Z.sql.gz`,
`~/banking-functions-20260824T035130Z.tar.gz`, `~/banking-localpatches-20260824T035130Z.patch`,
`~/bankingjobreadiness-dist-backup-20260824T035130Z`, and the checkout-local
`.env.bak-predeploy-20260824T035130Z`.

## 2026-08-24 (second run) — redeployed to `2492621` (3 commits, 1 migration)

Advanced from `63d9eb3`: `0755fd7` fixes the domain/tech assessment lifecycle, `8effba9` adds an
end-to-end curriculum assessment journey test, `2492621` tightens that test's types. None of the
three touched a locally patched file, so the stash/pull/pop cycle was clean and all five standing
UAT patches were verified back in place afterwards.

### The migration is destructive — pre-count it before applying

`20260824143000_assessment_lifecycle_integrity.sql` starts with a **`DELETE`** of duplicate
`assessment_questions` rows (same `assessment_id`, same case-folded/trimmed prompt, higher `id`),
then adds a partial unique index on `(assessment_id, md5(lower(btrim(prompt))))`, a
`sync_assessment_question_totals()` function plus an AFTER INSERT/UPDATE/DELETE trigger, and finally
backfills totals for every assessment.

**`assessment_responses.question_id` has `ON DELETE CASCADE`**, so that opening `DELETE` can silently
take student answers with it. Always quantify first:

```sql
-- rows the DELETE will remove, and the responses that would cascade
select count(*) from public.assessment_questions d
join public.assessment_questions r
  on d.assessment_id = r.assessment_id and d.id > r.id
 and lower(btrim(coalesce(nullif(d.question,''), d.question_text,''))) =
     lower(btrim(coalesce(nullif(r.question,''), r.question_text,'')))
where btrim(coalesce(nullif(d.question,''), d.question_text,'')) <> '';
```

Here it was **5 rows across 1 assessment** ("Banking Domain Readiness Assessment", 10 → 5 questions)
with **0 attached responses**, so nothing cascaded. Applied under `--single-transaction -v
ON_ERROR_STOP=1`: `DELETE 5`, index and both functions created, trigger created, backfill ran.
`assessment_questions` 734 → 729; `assessment_responses` unchanged at 11241. PostgREST reloaded to
128 Relations / 52 Relationships / **33** Functions (was 32 — the new `sync_assessment_question_totals`).

The `assessments` table has no `coding_count` column; the migration only uses `coding_count` as a
local record field inside `question_mix`, so it does not fail. Verified before applying.

### Verification

Site 200 (53 ms), REST and auth settings 200; served bundle `index-BQ1ZYkOP.js` matches the freshly
built `dist`; no hosted `*.supabase.co` in the bundle, 19 self-hosted `/sb` refs; 83 functions synced
with the three fixups; deployed `mcp` has no Windows path; zero function boot errors; all seven
containers up with the database healthy.

Both edge functions changed by this release were probed live, since a previous release shipped
runtime defects that only a live call caught. `generate-assessment-questions` and
`grade-assessment-attempt` both return 401 unauthenticated and validate correctly when authenticated.
A real generation call (`{topic_or_skills, track, difficulty, mix:{mcq:1,…}}` — note it is `mix` and
`topic_or_skills`, not `questionMix`/`topic`) returned **HTTP 200 in 2.7 s with a valid MCQ**, and
`assessment_questions` stayed at 729, confirming the probe does not persist.

**Full browser login run, not just a token check:** filled `9820065335`, Send OTP, `1234`, Verify →
landed on `/candidate/home` with the whole student console rendered and **zero page errors**; the
`/assessments` page then listed all 64 assessments with the migration's resynced counts
(e.g. the deduped assessment now correctly reads "5 questions 5 marks 5 MCQ"). API-level: correct OTP
200, wrong OTP 400, unknown mobile 400.

One pre-existing data oddity the totals backfill made visible: **"Axis Securities Assessment" shows
0 questions / 0 marks yet still renders a Start Assessment button.** Not caused by this release —
the assessment genuinely has no questions — but it is now plainly wrong in the UI.

Rollback assets use stamp `20260824T084231Z`: `~/banking-db-20260824T084231Z.sql.gz` (taken *before*
the destructive migration), `~/banking-functions-20260824T084231Z.tar.gz`,
`~/banking-localpatches-20260824T084231Z.patch`,
`~/bankingjobreadiness-dist-backup-20260824T084231Z`, and `.env.bak-predeploy-20260824T084231Z`.

---

## 2026-08-24 (third run) — redeployed to `6815d28` (6 commits, 1 migration)

`2492621` → `6815d28`: `e4bd2c8` + `6815d28` fix admin password reset across account roles,
`2044488` fixes Supabase auth-lock re-entry, `5e36e1a` fixes duplicate assessment question
generation, `11ccdb0` adds the interview proctoring lifecycle, `ead7b42` reformats the practice
plan widget. 28 files, +1060/−218.

All five local patches (`.env`, `LearningPathsManager.tsx`, `useLearningPaths.ts`,
`adminErrorLogger.ts`, `functions/mcp/index.ts`) survived the pull untouched — none of the six
commits touches those files, so no stash dance was needed.

### Migration `20260824183000_interview_proctoring_lifecycle.sql`

Purely additive and already idempotent (`add column if not exists` ×30, `create index if not
exists` ×2, then `notify pgrst`). **No fixup needed.** `public.interview_sessions` went
**19 → 48 columns** (one of the 30 already existed), both indexes created, all 3 rows preserved.

One thing to know about the backfill: `started_at` is added `not null default now()`, so the three
pre-existing sessions now claim a `started_at` of the migration timestamp rather than their real
start. Harmless at 3 rows, but do not read `started_at` as truth for anything created before
2026-08-24.

The migration's trailing `notify pgrst, 'reload schema'` worked — the new columns
(`proctoring_score`, `object_detections`, `attention_pct`) were reachable over PostgREST
immediately, with **no restart needed**. That is the reliable path; contrast with the
`kill -HUP 1` failure documented under the payment-request incident.

### Verification

Site / REST / auth all 200 (49 ms). Served bundle `index-BWuAW6Kb.js` matches the freshly built
`dist`; **no hosted `*.supabase.co` in the bundle**, 19 self-hosted `/sb` refs. 83 functions synced
with the three fixups, **zero boot errors**. All seven containers up, database healthy.
123 tables, 62 profiles, 62 auth users, 25 assessments, 3 interview sessions.

**Unit suite: 335/335 passing across 30 files** — up from 291/301 at `2492621`, so this release
also repaired the ten tests that were failing before it.

Both behavioural fixes were probed live rather than trusted from the diff:

- **`ai-assessment` dedup (`5e36e1a`)** — note the real contract is
  `{action:"generate", topicContent, assessmentTitle, mcqCount, descriptiveCount, videoCount,
  excludedQuestions[]}`; calling it with `{feature, topic, count}` silently returns
  `{"questions":[]}` with HTTP 200, which reads like a broken deploy but is just a bad payload.
  A correct call returned 3 MCQs; re-calling with the first question in `excludedQuestions`
  returned 3 **different** questions, so the `uniqueQuestionResult` filter works end-to-end.
- **`admin-reset-password` (`e4bd2c8`/`6815d28`)** — tested against a throwaway auth user rather
  than a real account: reset returned `{"success":true, userId, email}` (the new echo fields),
  login with the new password 200, with the old password 400, and the probe user was deleted
  afterwards (0 remaining). The new 404 branch also fires correctly: an unknown UUID returns
  *"The selected account is not linked to a valid login user."* Both admin functions still return
  401 unauthenticated.

The `resolveAuthUserId` change is the actual fix — it now checks `auth.admin.getUserById` **first**
for anything UUID-shaped, so a missing optional table in PostgREST can no longer block a reset for
a Student / Trainer / Institute / Admin account.

**Browser E2E** (`~/e2e-banking.cjs` on the DEV box, now extended with a candidate-OTP leg since
that is the path `2044488` rewrote): anon routes 200 with non-empty `#root`; candidate
`9820065335` / OTP `1234` → `/candidate/home` with the full student console; admin sign-in →
`/admin` with the full admin console. **0 page errors, 0 hosted-Supabase requests, 0 `/sb` 4xx/5xx.**

Note the candidate mobile field is `#loginMobile`, not `#mobile` — the latter does not exist and
the leg times out on it.

Rollback assets use stamp `20260824T150630Z`:
`~/bankingjobreadiness/dist.bak-predeploy-20260824T150630Z`,
`.env.bak-predeploy-20260824T150630Z`, and
`~/banking-localpatches-20260824T150630Z.patch`. No pre-migration DB dump was taken this time —
the migration is additive-only and destroys nothing. Disk on the UAT box is at **90 % (13 G free)**;
the accumulated `dist.bak-*` / `.env.bak-*` directories are the obvious thing to prune.

---

## 2026-08-25 — redeployed to `423fd65` (9 commits, 1 migration)

`6815d28` → `423fd65`: `8927a13` fixes the domain/tech assessment lifecycle, six `Changes` commits,
`69a244c` enforces unique assessment question generation, `423fd65` ("Fixed generation failures &
bugs") reworks the shared LLM helper's timeout and failover behaviour. 19 files, +478/−51. All five
local patches survived — none of the nine commits touches them.

### Migration `20260824220000_assessment_question_canonical_uniqueness.sql`

Same shape as the 2026-08-24 lifecycle migration (delete duplicates by canonicalised prompt, then
add a matching unique index) but this run **deleted 0 rows** — the earlier migration had already
cleaned every duplicate, so this one only added the permanent guard:
`assessment_questions_unique_prompt_idx`, a unique index on
`(assessment_id, md5(canonicalized prompt))`. Verified live by inserting an exact duplicate of an
existing row inside a rolled-back transaction — Postgres correctly rejected it with
`duplicate key value violates unique constraint "assessment_questions_unique_prompt_idx"` before the
rollback discarded the probe.

### The actual bug fix in `_shared/llm.ts`

`LLM_PROVIDER_TIMEOUT_MS` went **15000 → 45000**, which is the real content of "Fixed generation
failures & bugs" — AI question/content generation was being aborted at 15s before providers like
Gemini could finish a longer completion. Provider failover was also widened from
`[401,402,403,...retryable]` to also cover `400/404/422` ("model not available on this provider"
should fail over, not abort the whole request), `elevenlabs`/`youtube` were excluded from the
chat-provider pool via a new `NON_CHAT_PROVIDERS` set, and Gemini TTS now copies its decoded audio
into a fresh `Uint8Array` before returning it (fixes a detached-ArrayBuffer class of bug).

**One test was not updated to match:** `llmFallbackCoverage.test.ts` still asserts the shared
source contains the literal `"LLM_PROVIDER_TIMEOUT_MS = 15000"`; it now reads `45000`, so that one
assertion fails (340/341 passing). This is a stale test, not a regression — the 45000 value is the
deliberate fix. Not corrected locally since it's upstream's file to fix and doesn't affect runtime
behaviour.

### Verification

Site / REST / auth 200/200/200. Served bundle `index-DzQ1eYgD.js` matches the freshly built `dist`;
no hosted `*.supabase.co`, 19 self-hosted `/sb` refs. 83 functions synced, 3 fixups, **0 boot
errors**. All seven containers up, database healthy. 123 tables, 62 profiles, 62 auth users,
25 assessments, 729 assessment questions (unchanged by the migration).

**`generate-assessment-questions` probed live twice** — once cold, once with the first returned
question passed back in `excludedQuestions` — both HTTP 200 in ~8s with real Gemini-generated MCQs
on "KYC norms and AML compliance", and the second call's three questions were all distinct from the
excluded one, confirming semantic dedup still works with the new timeout/failover logic layered on
top of it.

**Browser E2E** (`~/e2e-banking.cjs`, same candidate + admin legs as the prior release): anon routes
200 with non-empty `#root`; candidate `9820065335` / OTP `1234` → `/candidate/home`; admin → `/admin`
with full console. **0 page errors, 0 hosted-Supabase requests, 0 `/sb` 4xx/5xx.**

Rollback assets use stamp `20260825T015122Z`:
`~/bankingjobreadiness/dist.bak-predeploy-20260825T015122Z`,
`.env.bak-predeploy-20260825T015122Z`, `~/banking-localpatches-20260825T015122Z.patch`. No DB dump
taken — the migration deleted 0 rows and is otherwise additive. **Disk remains at 90% (13G free)** —
now three releases running without a prune of the accumulated `dist.bak-*`/`.env.bak-*` directories;
worth clearing on the next deploy.

## 2026-08-26 — repaired candidate OTP login for `9769440000`

Candidate **Himanshu Bhagat** (`9769440000`) received the candidate-login toast "Account not
found" after entering the correct demo OTP `1234`. The public profile was present, active and
approved, and its reconstructed auth identity (`9769440000@bankready.app`) was confirmed, but
`auth.users.encrypted_password` was empty. This is one of the imported identities documented in
`banking-postgres-migration.md`; the hosted password hash was unavailable during reconstruction.

Provisioned the app's policy-compliant derived credential with
`~/banking-sb/set-user-password.sh 9769440000 'Otp_9769440000_1234'`. No source change, frontend
deployment or migration was required. Exact fresh-browser verification against the live candidate
form — mobile `9769440000`, Send OTP, OTP `1234`, Verify — redirected to `/candidate/home`, rendered
Himanshu's full student console, and produced **0 page errors and 0 `/sb` API errors**.

## 2026-08-27 — redeployed to `5b4b5f2` (7 commits, no migrations)

`423fd65` → `5b4b5f2`: `1240e26` work in progress, `426ed22` fixes module creation with schema
drift, `83fab4d` fixes bulk-candidate mobile login compatibility, two `Changes` commits, `77e9d0a`
`Changes`, `5b4b5f2` fixes taxonomy 400 errors. `supabase/migrations` stayed at 161 files (`git diff
--stat` between the two commits shows no path under `supabase/migrations`), so this release is a
functions + frontend deploy only — no `replay-migrations.sh` or `sql/` fixup step needed.

`83fab4d` changes `supabase/functions/bulk-create-users/index.ts`'s derived password from
`otp_<mobile>_1234` to `Otp_<mobile>_1234`, i.e. it upstreams the same policy-compliant capitalization
fix that was hand-patched into `Login.tsx` on 2026-08-21 (see "candidate OTP login policy fix"
above) — new bulk-imported candidates now get a GoTrue-acceptable password on creation instead of
needing a follow-up `set-user-password.sh` repair.

### Local patches — verified as five, matching the standing inventory

`git status` after the pull showed exactly the five expected dirty files (`.env`,
`src/components/pil-admin/LearningPathsManager.tsx`, `src/hooks/useLearningPaths.ts`,
`src/lib/adminErrorLogger.ts`, `supabase/functions/mcp/index.ts`) plus the disposable
`package-lock.json`. None of the 7 incoming commits touched a patched file, so `git pull` fast-forwarded
cleanly with zero stash/merge dance required. Deployed edge functions are unaffected by the working-tree
`mcp/index.ts` diff either way — `sync-functions.sh` always overlays `~/banking-sb/function-fixups/mcp/`
on top of whatever the repo ships (verified: deployed `banking-sb/functions/mcp/index.ts` and
`banking-sb/functions/live-session-rsvp/index.ts` byte-match their fixup-dir source both before and
after this sync).

### Verification

Site / REST / auth-health all 200. Served bundle `index-4Krcghy0.js` matches the freshly built `dist`
(confirmed via the live page's script tag). No hosted `*.supabase.co` data-plane URL in the bundle (the
one `api.supabase.co`-shaped grep hit is the documented inert `AdminSecurityMigration.tsx` Management-API
remnant, not a data-plane leak) and no `.dev.pluginlive.com` leak. 83 edge functions synced with the
three standing fixups (`live-session-rsvp`, `main`, `mcp`); functions container restarted clean with zero
new boot errors. All seven `banking-sb-*` containers up, `banking-sb-db` healthy.

**Browser E2E**, two independent candidate accounts plus admin, via a fresh headless Chromium context
each: mobile `9820065335` (task-specified) and `9100000021` (standing demo account) both Send OTP →
`1234` → Verify → `/candidate/home` with the full student console, **0 page errors, 0 `/sb` API
errors**. Trainer `9100000022` → `/journey/trainer`. Admin `demo.admin@bankready.app` /
`Demo@Admin2026` signs in with 0 errors, landing on `/` — the guarded `/admin` console route is
separate, per the existing note above.

Unit suite: 348 passed / 349 (1 failing — the same stale `llmFallbackCoverage.test.ts` literal
documented under the 2026-08-25 release; not touched by this release's commits, not a regression).

Rollback assets use stamp `20260827T023655Z`: `~/bankingjobreadiness/dist.bak-predeploy-20260827T023655Z`.
No DB dump or functions-predeploy archive was taken — no migration and no fixed-up function changed, so
there was nothing destructive to snapshot beyond the frontend `dist/`.

## 2026-08-28 — admin login for `prakash.chinnadurai@gmail.com`: two distinct causes

Reported as `POST /sb/auth/v1/token?grant_type=password` → **400 Bad Request**, "Login failed /
Invalid credentials", on the Admin tab. Two independent problems, neither a deploy regression.

**1. The Admin tab cannot accept a personal email that has no auth user.** `handleAdminLogin` in
`src/pages/Login.tsx` passes the User ID straight through as the GoTrue email, only appending the
domain when there is no `@`:

```js
const email = adminId.toLowerCase().includes("@") ? adminId : `${adminId.toLowerCase()}@bankready.app`;
```

There is **no auth user with email `prakash.chinnadurai@gmail.com`** (`auth.users` has exactly one
non-`@bankready.app` address, `banking.admin@pluginlive.com`). So GoTrue correctly returns 400. The
gmail address only exists as a **`public.profiles.email` value**, on profile
`6f18325e-5f93-4499-87bd-74d77086054a` → user `ce86d36b-8987-4d0e-b685-3d3ebf953761`, whose auth
identity is the mobile-derived `9820065336@bankready.app`. **`profiles.email` is display data and is
never consulted at sign-in** — do not read a profile email as a usable login.

**2. That account's password hash did not match the app-derived password.** `ce86d36b` holds
`admin` + `trainer` + `candidate` roles, but was part of the **2026-08-09 04:46:48 import batch** —
the same batch as `9769440000` (repaired 2026-08-26). Both `Otp_9820065336_1234` and the legacy
lowercase `otp_` variant returned `invalid_grant`, and `last_sign_in_at` was NULL, i.e. the account
had **never once been able to log in**, by any route — admin *or* mobile OTP.

Repaired in place, matching the earlier fix:

```sql
update auth.users
   set encrypted_password = extensions.crypt('Otp_9820065336_1234', extensions.gen_salt('bf')),
       updated_at = now()
 where id = 'ce86d36b-8987-4d0e-b685-3d3ebf953761';
```

Note `pgcrypto` lives in the **`extensions` schema** on this DB — bare `gen_salt()`/`crypt()` fail
with `function gen_salt(unknown) does not exist`; schema-qualify them.

Setting this password is **not** a side-effect-free admin reset: the mobile OTP path
(`src/lib/candidateMobileAuth.ts`) signs in with exactly `Otp_<mobile>_1234`, so the admin password
and the OTP-derived password are the same secret. Setting it to anything else would silently break
that user's Candidate/Trainer OTP login. Here it was already broken, so this restored both.

Verified live: password grant returns an access token; through the real UI, Admin tab User ID
`9820065336` + password `Otp_9820065336_1234` signs in as **Prakash** and `/admin` renders the full
console (67 candidates, all sidebar groups), 0 page errors.

**Working admin logins on UAT:** `9820065336` (Prakash, above), `demo.admin@bankready.app` /
`Demo@Admin2026`, `banking.admin@pluginlive.com`. If a gmail-addressed admin login is genuinely
wanted, it needs a **new** auth user — renaming `ce86d36b`'s auth email would break mobile OTP for
`9820065336`, since that path looks up `<mobile>@bankready.app`.

## 2026-08-28 — the four source local patches are now upstream (`d6b9e0c`)

The long-standing "five local patches carried on the UAT checkout" inventory is **now one**. The four
*source* patches were committed and pushed to `origin/main` as `d6b9e0c`, so a fresh clone builds
correct code and there is nothing to reapply after a pull:

| File | What it fixes |
|---|---|
| `src/components/pil-admin/LearningPathsManager.tsx` | saving an existing path ran `delete from learning_paths where id = pathId` — **it deleted the path being saved**, silently, while the UI said "Learning path updated" |
| `src/hooks/useLearningPaths.ts` | both assignment reads selected from `learning_paths`, so every path rendered as an unscoped assignment |
| `src/lib/adminErrorLogger.ts` | `SUPABASE_URL` was the hardcoded hosted project URL, so post-migration none of the `startsWith()` prefix checks matched and admin error logging **recorded nothing** |
| `supabase/functions/mcp/index.ts` | pins `@lovable.dev/mcp-js` to `0.26.3` so the function boots |

**`.env` remains the one deliberate local patch** and must never be committed — it holds the UAT
self-hosted keys. `package-lock.json` also shows as modified on the box; that is npm-version noise
(`libc` fields dropped by the older npm on the UAT host), not a real change — leave it uncommitted.

So the post-pull check is now: **`.env` intact, and `git status` shows only `.env` +
`package-lock.json`** (plus the `*.bak-predeploy-*` / `dist.*` rollback dirs, which are untracked by
design). Anything else appearing modified means a patch regressed.

Also note the earlier inventory table in this doc that lists only four patch files is stale — it
predates the `mcp/index.ts` entry. The authoritative list is the one above.

## 2026-08-28 — admin "Reset Password" bricked every mobile/OTP account (fixed, `3a4d977`)

**Historical behavior:** mobile-backed admins can now reset passwords and use Admin Login; the UAT fix on 2026-10-16 below supersedes the blanket refusal. Mobile candidate/trainer accounts still use OTP.

**The bug.** Candidates and trainers sign in with mobile + OTP on a screen that has **no password
field** — `src/lib/candidateMobileAuth.ts` calls `signInWithPassword` with a password *derived from
the mobile number* (`Otp_<mobile>_1234`, with a legacy lowercase `otp_` fallback). That derived value
is the account's only usable credential. So the admin console's **Reset Password** action, which
stored an admin-chosen password via `admin.auth.admin.updateUserById`, left the account in a state
where the OTP screens could no longer authenticate it **and there was nowhere to type the new
password** — locked out of every route, silently, while the UI reported success.

Worse, the natural reaction to the lockout is to reset the password again, which re-breaks it. The
audit log shows exactly that loop: resets on **2026-08-18, 08-21, 08-23, 08-24** and four more on
**08-28 05:35–05:36**, across five accounts, every one of them an attempt to fix the previous one.
Five logins were dead at the time of the fix (`9820065335`, `9820098200`, `5555555555`,
`7777777777`, and `9820065336`).

**The fix** (`supabase/functions/_shared/otp-login.ts` + both reset paths): look the target up first
and **refuse** when its auth email matches a 10-digit mobile at `bankready.app`, returning 400 with a
message that names the mobile and points at OTP 1234. The lookup was moved *ahead of* password
validation so the admin sees the real reason instead of a password-strength complaint.

Two details that matter:

- **`admin-reset-password` needed the same guard.** `src/lib/adminPasswordReset.ts` calls
  `admin-user-actions` first and falls back to `admin-reset-password`; that function is also callable
  directly. Guarding only one leaves the hole open.
- **The match is anchored** (`^(\d{10})@bankready\.app$`, case-insensitive) so real email accounts —
  `demo.admin@bankready.app`, `banking.admin@pluginlive.com` — stay resettable, and a lookalike
  domain like `...@bankready.app.evil.com` is not mistaken for an OTP login.

Verified live against the deployed functions with a real admin token: resetting `9820065336` is
refused on **both** endpoints with the OTP message; a throwaway email user
(`guardprobe@example.com`) still resets successfully and logs in with the new password (probe
deleted afterwards, 0 rows left). Unit tests `src/lib/otpLoginGuard.test.ts` (6 cases) cover
detection, the lookalike domain, and the derived-password format. Full suite 360 passed / 361 — the
one failure is the long-standing stale `LLM_PROVIDER_TIMEOUT_MS` literal in
`llmFallbackCoverage.test.ts`, untouched by this change.

**Data repair.** The five already-bricked accounts were restored to the derived credential:

```sql
update auth.users
   set encrypted_password = extensions.crypt('Otp_' || substring(email,1,10) || '_1234',
                                             extensions.gen_salt('bf')),
       updated_at = now()
 where email in ('9820065335@bankready.app', ...);
```

All five now return 200 on a password grant, and `9820065335` was driven through the real UI —
Send OTP → `1234` → Verify → `/candidate/home` as "Prakash Chinnadurai", zero page errors.

Deployed by copying the three files into `~/banking-sb/functions/` and restarting
`banking-sb-functions` (zero boot errors). No frontend rebuild was needed: `adminPasswordReset.ts`
already surfaces the function's `error` string, and a 400 does not trigger its
`shouldTryDedicatedReset` fallback (that requires status >= 500).

---

## 2026-08-28 — plan upgrade returned 409 on every submit (`fd0355a`)

Selecting a plan in **Upgrade Plan — Manual Payment** and hitting *Submit for Verification* failed
for every candidate:

```
POST /sb/rest/v1/rpc/submit_payment_request  ->  409 Conflict
insert or update on table "payment_requests" violates foreign key constraint
"payment_requests_student_id_fkey"
```

### Cause — two migrations disagree about `student_id`, and the newer one silently lost

`payment_requests` is declared **twice** in the repo, by two different authors, with two different
meanings for `student_id`:

| Migration | `student_id` means | What it did |
|---|---|---|
| `20260711113000_payment_requests_and_journey_access.sql` | a row in `public.students` | `create table` + FK `student_id -> public.students(id) on delete set null not valid` |
| `20260818080751_4527d448-...sql` | the **auth user id** | `create table if not exists` — a **no-op** on any DB that already had the table |

Everything shipped by the August migration reads `student_id` as the auth uid: RLS is
`student_id = auth.uid()`, `admin_list_payment_requests` joins
`profiles.user_id = r.student_id or profiles.id = r.student_id`, and
`admin_approve_payment_request` updates `public.profiles`, not `public.students`. The frontend
agrees — `TechStudentJourney.tsx` passes `sessionStorage.studentId || user.id`.

But because its `create table if not exists` never fired, the July FK survived, still pointing at
`public.students` (52 legacy rows, no candidates in it). `not valid` only exempts *existing* rows —
**new inserts are still checked** — so every submission was rejected. The live function bodies were
the August ones while the live constraint was the July one.

**The general trap:** this repo uses `create table if not exists` to "redefine" tables across
merges. It never alters an existing table. Only the `alter table ... add column if not exists`
lines in those files actually take effect. Check `pg_constraint` / `information_schema.columns`
against the live DB before trusting the newest migration file.

### The fix

`supabase/migrations/20260828070000_payment_requests_drop_legacy_students_fkey.sql`:

```sql
alter table public.payment_requests
  drop constraint if exists payment_requests_student_id_fkey;
```

The profiles-based design is the live one, and the table had 0 rows, so nothing was orphaned.
**Do not re-point the FK at `auth.users` instead** — `ai_coach_student_allowed` also accepts a
`profiles.id` that differs from `auth.uid()`, so that would just move the breakage. No frontend
rebuild was needed; this is purely a DB constraint.

### Verification

Driven through the real UI (candidate `9100000021` / OTP `1234` → *Subscriptions Status* →
*View Upgrade Options* → Beginner ₹499 → UTR `1234567` → Submit):
`submit_payment_request` **200**, **0 `/sb` 4xx**, **0 page errors**, and the dialog's *Your
Submissions* list read the row back as `beginner · ₹499 … Pending`.

The rest of the chain was exercised with a real admin token: `admin_list_payment_requests` returned
the request with the candidate resolved via `profiles` ("Demo Candidate"), and
`admin_approve_payment_request` flipped `profiles.subscription_tier` to `beginner` with
`subscription_expires_at` +30 days.

Test data removed afterwards — `payment_requests` back to 0 rows and the demo candidate restored to
`enterprise` / `active` / `expires_at NULL`.

### PROD is still broken

PROD runs on hosted Supabase `kbwjokmmzkgjwiqelrdc`, where **both** migrations also ran, so it has
the identical stale constraint and identical 409. Applying the fix there needs dashboard/DB
credentials for that hosted project, which nobody on the team currently holds (see
`banking-postgres-migration.md`). **Pending.**

## Module videos: search queries vs. playable URLs

The student **Videos** tab renders a topic's video only if the stored string parses as a real
YouTube URL (`getYouTubeId()` in `ModuleVideosPanel`). Anything else — a search phrase, a
`youtube.com/results?search_query=…` link — is filtered out and the tab reads
*"No videos linked to \<topic\> yet."* Two independent sources kept producing exactly that.

**1. AI module generation stores queries, not links.** `AIModuleCreator` prompts the LLM for
"2-3 suggested YouTube video **search queries**" and writes those raw strings into
`admin_module_topics.suggested_videos` (`text[]`). Every AI-created module therefore shipped with an
empty Videos tab. As of `6f87c4c`, `autoLinkTopicVideos()` runs immediately after the topics are
inserted: one `ai-video-suggest` call per topic, sequential with a 1.5 s gap (the YouTube Data API
is quota-limited and the function issues ~3 searches per topic), writing the resolved URL to the
front of `suggested_videos` via `withResolvedVideoFirst()`. The original queries stay behind it as
reading hints. Progress is shown as *"Fetching YouTube videos — 2 of 6"*.

**2. The old fallback payload was persisted.** When `ai-video-suggest` cannot verify a video it
returns `{fallback: true, video_url: "https://www.youtube.com/results?search_query=…", reason}`
rather than an error. Before `isPersistableVideoSuggestion()` gated the write, those search-results
URLs were saved as if they were videos. **510 rows in `public.topics` still hold one** — they render
as "no videos" and are only fixable by re-resolving. The 10 topics of the *Quantum Physics* module
(`0eb1c470-098d-425d-a9d7-3868a4e03ce4`) were re-resolved on 2026-08-28; the rest were not.

**Manual recovery for an empty topic.** Any viewer now gets a **"Fetch video from YouTube"** button
in the empty state. The result plays immediately for whoever clicked it, but is only written back
when the viewer is an admin or trainer — the RLS write policy on `admin_module_topics` is
`has_role(admin) OR has_role(trainer)`, so a student write would fail. `AdminModuleTopic` carries
`source_table` so the write reaches the right column: `suggested_videos` on `admin_module_topics`,
`video_url` on the legacy `topics` table (which has no `suggested_videos` column at all — that is
why `useAdminModules` folds `video_url` into a one-element `suggested_videos` array for legacy rows).

### The YouTube Data API key

`getYouTubeApiKey()` in both `ai-video-suggest` and `youtube-search` reads the key from the
`llm_provider_configs` row where `provider_key = 'youtube'` (Admin → **LLM Settings** → *YouTube Data
API*), using the service-role client; `Deno.env.get("YOUTUBE_API_KEY")` is only a fallback and is
**not** set on UAT. That row existed with `api_key IS NULL` from the start, so every suggest call
silently returned the fallback payload. A key was written into it on **2026-08-28** and video
resolution works on UAT now.

Two traps when sourcing a key:

- The ATS Google-Sheets export credential is a **service account**
  (`sheet-reader-dev@data-eng-dev-486917`). YouTube Data API v3 **does not accept service accounts** —
  it needs an API key or user OAuth. It cannot be reused here.
- A Gemini key is also an `AIza…` Google API key but is normally restricted to the Generative
  Language API. Test any candidate key before wiring it in:
  `curl -s -o /dev/null -w '%{http_code}\n' 'https://www.googleapis.com/youtube/v3/search?part=snippet&q=test&type=video&maxResults=1&key=<KEY>'`

### Calling the function directly

nginx exposes the edge functions under `/sb/`, so `https://banking.uat.pluginlive.com/functions/v1/…`
returns **405** — use `/sb/functions/v1/<name>` with the `ANON_KEY` from `~/banking-sb/.env` as the
bearer. Note also that reads on `public.topics` require the `authenticated` role (`anon` gets `[]`);
mint a candidate token with a GoTrue password grant against `<mobile>@bankready.app` /
`Otp_<mobile>_1234`.

**The deployed function lags the repo.** `~/banking-sb/functions/ai-video-suggest/index.ts` is the
304-line version (LLM query maker + LLM picker); the repo copy is 395 lines and adds a deterministic
metadata checker that rejects non-public, non-embeddable, too-short or off-topic candidates before
the LLM ever sees them. Until `~/banking-sb/sync-functions.sh` is run, match quality on UAT is the
weaker of the two. Relevance is also capped by the topic titles themselves: AI-generated titles that
fuse two domains ("Wave-Particle Duality: The Dual Nature of *Financial Systems*") send the search to
one domain or the other and never both.

## Admin → LLM Config could not save (2026-08-28)

Two unrelated failures on the same screen, both schema drift, both fixed by
`20260828083515_llm_settings_tts_columns_and_audit_actor_text.sql` (app repo
`supabase/migrations/`, mirrored in DB-Scripts under *Banking Supabase to Postgres*).
**The frontend was already correct** — nothing needed rebuilding, only the database.

**1. "Could not find the `tts_default_language` column of `llm_settings` in the schema cache."**
`LLMSettings.tsx` has written `tts_voice_id`, `tts_languages`, `tts_default_language`,
`tts_enabled` and `tts_stream_audio` since the multilingual AI coach release (2026-08-12), but no
migration ever added them — this is the same class of gap as the hand-written migrations that live
only in git. The five columns were added with defaults copied from the component's own fallbacks
(`21m00Tcm4TlvDq8ikWAM`, `{en,hi}`, `en`, `true`, `false`), so the single existing row renders
unchanged.

**2. Save Key → HTTP 500, `invalid input syntax for type uuid: "admin"`.**
`llm_provider_configs.created_by` and `updated_by` were declared `uuid`, but every writer records an
actor *string*: `manage-llm-providers` computes `body.updatedBy || body.adminEmail || "admin"`, and
the admin UI sends `sessionStorage.getItem("adminEmail") || "admin"`. There is no `auth.users` id in
that path to write. `llm_settings.updated_by` is already `text`, so these two columns were the
outliers — both were widened to `text`. Nothing references them by foreign key and every row was
NULL, so the change was lossless.

Note the failure mode is asymmetric and easy to misread: **Test** and the key *display* both worked
(the UI read `AIzaSy…Oa7k (stored)` and reported *"Key works — found video ID …"*) because those
paths only `SELECT`. Only the `UPDATE` carrying `updated_by` blew up. A working Test button does not
mean the key was saved through the UI.

**Always `NOTIFY pgrst, 'reload schema'` after adding columns here.** PostgREST caches the schema, and
the error text names the cache explicitly — without the reload the new columns stay invisible and the
save keeps failing identically after a correct migration.

## 2026-08-31 — interview auto-transcription was broken for every recording (fixed, `4d88c18`)

`/practice/interview` showed **"Transcribe failed"** and *"Auto-transcription unavailable for Qn —
Edge Function returned a non-2xx status code"* on every answer. Grading still worked because the
candidate could type the transcript by hand, which is why this survived unnoticed.

**Cause.** `ai-interview`'s `transcribe` action sent the recording to Gemini through its
**OpenAI-compatibility layer** as an `input_audio` content part. That layer accepts only two
container formats:

```
Invalid audio format "webm" for audio generation. Valid formats are: [wav, mp3]
```

The browser records `video/webm` (`new MediaRecorder(stream, { mimeType: "video/webm" })`), so the
call was rejected **400 every single time**. The fetch fallback then walked the remaining providers —
`openai` has **no api_key** in `llm_provider_configs`, and `nvidia`'s nemotron is **text-only** — and
whatever text came back contained no JSON, so `extractJson` threw and the function returned a **500
`No JSON found`**. The real reason never reached the UI.

**Fix.** Gemini's **native** `generateContent` endpoint *does* accept `audio/webm` inline data —
confirmed against the live API with a real WebM/Opus clip before writing any code. Transcription now
calls it directly via `transcribeAudioWithGemini()` in `_shared/llm.ts`.

Three details worth keeping:

- **The stored `base_url` points at the shim.** `llm_provider_configs.base_url` for gemini is
  `https://generativelanguage.googleapis.com/v1beta/**openai**`; the helper strips the trailing
  `/openai` to reach the native API. Don't "fix" that column — the chat path needs the shim.
- **The JSON wrapper was the trap.** The old prompt asked the model to reply
  `{"transcript":"..."}`, so *any* provider failure became the misleading `No JSON found`.
  Transcription now takes plain text, and when both paths fail the function returns **502 with the
  provider's own message**, so the toast says something actionable.
- **The chat-completions path is kept as a fallback** for the wav/mp3 inputs it can genuinely handle.

**Verified on UAT** through both input modes — inline `audioBase64`, and the `storagePath` mode the
interview page actually uses (server downloads from the `interview-recordings` bucket) — each
returning 200 with an accurate transcript of a real spoken clip. `generate` and `grade` still 200.
Tests 370 passed / 371 (the one failure is the standing stale `LLM_PROVIDER_TIMEOUT_MS` literal in
`llmFallbackCoverage.test.ts`).

**Note on the checkout:** it was **32 commits behind** origin/main when this was written (heavy
upstream activity that day, including a default-model bump to `gemini-3.6-flash`). The fix was
committed, rebased onto latest main, pushed, and only then redeployed — `git fetch` before assuming
the UAT box is current.

## 2026-08-31 — "we have 24k videos but they don't show": there were none

Reported against `Banking - AML Basics` (`5d7bd4c6-…`) — the module's **Videos** tab was empty
despite a belief that ~24,000 YouTube videos already existed in the app. Measured, rather than
assumed:

| Store | Rows | Real watchable videos |
|---|---|---|
| `admin_module_topics.suggested_videos` (what the Student Journey reads) | 555 | **0** |
| `topics.video_url` (legacy) | 532 | **22** — 505 are `youtube.com/results?search_query=…` placeholders |
| `curriculum_videos` / `video_lessons` / `curriculum_topics` | 0 / 0 / 0 | — |

**There is no 24k video store in this database.** The largest table of any kind is
`assessment_responses` at ~11k rows. The belief almost certainly comes from the **505 placeholder
rows**, which look populated in the DB but are YouTube *search* links, not videos —
`getYouTubeId()` returns null for them, so the panel renders "no videos". This is not a display bug:
the module genuinely had nothing linked.

**Where the placeholders come from — and the trap.** `ai-video-suggest` returns a *fallback* payload
(`{video_url: "…/results?search_query=…", fallback: true}`) instead of erroring when its checker
can't verify a video. Anything that writes that response without gating on
`isPersistableVideoSuggestion()` mints another dead placeholder. **Never store a `results?search_query`
URL.**

**Fixed / done:**

- Deployed the current `ai-video-suggest` (repo 395 lines; the running copy was a stale 304-line
  build) plus `_shared/youtube-video-validator.ts`, **which was not deployed at all** — so the
  deterministic metadata checker had never run on UAT.
- Verified the YouTube Data API key in `llm_provider_configs` (`provider_key='youtube'`) works — a
  live `search.list` returns 200.
- Backfilled `Banking - AML Basics`: **9 of 15 topics** now carry real `watch?v=` URLs, confirmed
  through the candidate's own PostgREST read (RLS-scoped), which is exactly what the Videos tab
  fetches. The other 6 returned the search-query fallback and were **deliberately not written**.

**Backfill tool:** `~/banking-sb/backfill-topic-videos.sh <module_id>` on the UAT box. It calls the
maker→YouTube→checker pipeline per topic and writes only approved `watch?v=` URLs; it stops early if
YouTube reports quota exhaustion. Two shell traps were hit writing it and are fixed in the saved
copy: both `curl` and `docker exec -i` **consume the loop's stdin**, silently ending the `while read`
after one iteration (it reported "linked=1" on a 15-row module twice before this was spotted).

**The binding constraint for a full backfill is YouTube quota, not time.** `search.list` costs 100
units against a default 10,000/day project quota, i.e. **~100 topic resolutions per day**, and
`ai-video-suggest` may issue up to 3 searches per topic. **546 topics still have no video**
(`Banking - Key Duties…` 21, `Banking - AML/KYC…` 17, `Cloud Computing Fundamentals` 15, …), so
completing them needs either a raised quota in the Google Cloud console or several days of batched
runs. The 505 legacy `topics.video_url` placeholders are a separate re-resolution job.

### 2026-08-31 (same day) — full backfill attempted, stopped by YouTube quota at 17 topics

Ran `~/banking-sb/backfill-all-topic-videos.sh` across all 555 module topics. It linked **17** before
the project's YouTube **daily search quota** ran out:

```
"Quota exceeded for quota metric 'Search Queries' and limit 'Search Queries per day'
 of service 'youtube.googleapis.com' for consumer 'project_number:167734609581'"   HTTP 429
```

| Module | Linked / topics |
|---|---|
| Banking - AML Basics | 9 / 15 |
| Advanced Banking | 5 / 9 |
| AI Agents | 2 / 4 |
| AI Agents & Workflow Automation | 1 / 10 |
| **Total** | **17 / 555** |

**The failure mode is silent and worth knowing.** `ai-video-suggest` catches the YouTube 429 and
returns its normal fallback payload with `reason: "No YouTube videos found for generated queries"` —
the words *quota*, *429* and *rateLimitExceeded* never appear in the function's response. A caller
watching for quota strings therefore sees nothing and keeps going; the run produced **154 skips** in
a row before this was spotted by querying the YouTube API directly. Note the reason string is
`rateLimitExceeded` / `RESOURCE_EXHAUSTED`, **not** the `quotaExceeded` / `dailyLimitExceeded` most
guards look for.

The script now probes `youtube/v3/search` directly whenever it sees that fallback and aborts the run
on a real quota error, so a rerun stops in seconds instead of walking the whole list.

No placeholders were written at any point (`placeholders = 0`) — skipped topics were left empty
rather than filled with `results?search_query=` URLs.

**To finish the remaining 538 topics**, one of:
1. Raise **Search Queries per day** for project `167734609581` in the Google Cloud console
   (default 10,000 units/day ÷ 100 per search ≈ 100 searches, and the function may issue up to 3 per
   topic — so ~33-100 topics/day at default). Then a single run completes it.
2. Rerun the script daily; it skips already-linked topics, so it resumes where it stopped.

Quota resets at **midnight Pacific**.

### 2026-09-01 — second API key, +32 topics, exhausted again at 49/555

A second YouTube API key (`AIzaSyBKcVhGAp…`, a different Google Cloud project) was supplied and
written into `llm_provider_configs.api_key` for `provider_key='youtube'`. The previous key
(`AIzaSyAYeE6qO1…`) is preserved in that row's `metadata.previous_api_key_2026_08_31`. The edge
function picks the key up from the DB at call time — **no redeploy or restart needed**.

Run linked **32 more topics** before that key hit the same daily wall — total now **49 / 555
linked, 506 pending, 0 placeholders**.

**The important correction to the earlier note:** the ~50% skip rate observed on 2026-08-31 was
**not** the quality checker rejecting videos — it was quota exhaustion being reported as
"No YouTube videos found". With fresh quota the real rate is **32 linked / 4 skipped (89%)**. So
throughput per quota-day is ~33 topics attempted and ~30 linked, not ~17.

The fixed quota guard worked as intended: the run stopped at topic #37 with
`QUOTA EXHAUSTED … rerun tomorrow` instead of walking the remaining 500 producing false skips.

Modules fully done: `AI Agents & Workflow Automation` (10/10), `AI Tools for Candidates` (5/5),
`AI & social responsibility` (4/4), `AI SaaS Development` (4/4), `AI Agents` (4/4).

**Each key is its own 10,000-unit/day bucket**, so rotating a key from a *separate, legitimately
owned* project is the only way to get more throughput per day short of Google approving a quota
extension. At 301 units/topic that is ~33 topics per key per day; 506 pending ≈ **17 key-days**.
Quota resets midnight Pacific.

### 2026-09-01 — 100 / 555 linked; the "raised" quota did NOT take effect

Ran the backfill to exhaustion on **both** keys. Total is now **100 linked / 455 pending /
0 placeholders**.

**The quota increase was not in effect on either project.** Both keys hit
`Search Queries per day` at the usual ~33-topic mark, which is the untouched 10,000-unit default:

| Key | Project | Topics before exhaustion |
|---|---|---|
| `AIzaSyBKcVhGAp…` | `438222755561` | ~25 |
| `AIzaSyAYeE6qO1…` | `167734609581` | 38 (26 linked) |

So a YouTube quota-extension request either had not been approved yet, or was filed against a
different project. **Verify the fix by project number**, not by the console showing a new value —
the 429 body names the project (`consumer 'project_number:…'`), which is the only reliable check.

**The two keys are separate daily buckets and can be alternated.** When one 429s, swapping
`llm_provider_configs.api_key` to the other resumes immediately — the edge function reads the key
per call, so no restart or redeploy. That doubled today's throughput (74 → 100).

**Success rate with real quota is ~70-89%**, not the ~50% first assumed (that figure was polluted by
quota-induced skips). Today: 26 linked / 38 processed, and earlier 32/36.

**Do not be alarmed by two `backfill-all-topic-videos.sh` PIDs** — the script's
`while … done < <(psql …)` process substitution forks a second copy of the script under the same
name. It is one run, not a duplicate. Distinguish real concurrency by counting
`=== backfill started` markers in the log, not by `pgrep -c`.

**The log is append-only across runs** (`tee -a`), so `grep -c '^OK'` counts *all history*. Rotate
it (`mv backfill-all.log backfill-all.log.hist-$(date +%H%M%S)`) before a run, or count only after
the last start marker, otherwise progress looks stalled when it is not.

Modules now fully covered: `Banking - AML in Practice` 12/12, `Banking - AML Attributes` 12/12,
`AI Agents & Workflow Automation` 10/10, `Advanced Banking` 9/9, plus 8 smaller AI modules.

## 2026-09-03 — redeployed to `d579c84` (17 commits, 5 migrations)

17 commits forward from `4d88c18`. Trainer curriculum delivery, a `super_admin` role, privileged
admin menu access, student platform-usage reporting, and a legacy topic video library.

| Check | Result |
|---|---|
| Migrations | 5 applied, `--single-transaction`, no errors |
| Destructive statement | one dedup `DELETE` on `curriculum_assignments` — table was **empty (0 rows)**, so nothing removed |
| Schema verified | `curriculum_assignments.student_user_id`/`student_profile_id`, `super_admin` enum value, `student_usage_daily`, `uq_curriculum_assignments_student_user` all present |
| Edge functions | 3 changed synced; **2 were missing from the deployment entirely** (`candidate-otp-login`, `generate-curriculum-video`) and were deployed — 84 → 86 dirs |
| Frontend | rebuilt, served `index-D7UQOY7I.js` matches fresh `dist`; 19 self-hosted `/sb` refs, no data-plane leak |
| Containers | 7/7 up, db healthy; PostgREST restarted for the new columns |
| Logins | candidate/trainer/admin all 200; `9820065335` driven through the real UI to the student console |
| Prior fixes | OTP-reset guard still refuses correctly; interview transcription still 200 |
| Tests | **402 passed / 403** |
| Rollback | `~/banking-predeploy-20260903T083834Z/` (public-schema dump + env) and `dist.bak-predeploy-20260903T083834Z` |

**`pg_dump` of the whole DB fails as `banking_owner`** — `permission denied for schema _realtime`
while taking the LOCK. Use `-n public`, which is what these migrations touch anyway.

**Two upstream test-suite changes worth noting:**

- The long-standing stale `LLM_PROVIDER_TIMEOUT_MS = 15000` failure in `llmFallbackCoverage.test.ts`
  is **fixed upstream** — that file now passes 10/10. It should no longer be waved off.
- A **new** failure took its place: `src/test/videoAutoLink.test.ts > persistTopicVideo > writes
  video_url on legacy topics and reports failures` (`expected "spy" to be called with { table:
  'topics', … }`). It is upstream's, from this release's own `ae872f8` / `b196f75` "curriculum
  YouTube playback" work — no local source was modified during this deploy. Not a deploy regression,
  but it is a real red test on `main`.

**The `mcp/index.ts` local patch came back.** Upstream regenerated that bundled file to
`@lovable.dev/mcp-js@0.26.2`, undoing the `0.26.3` pin that was committed earlier. The working tree
kept `0.26.3` and the deployed copy was resynced from it, because `0.26.2` is what fails to boot.
Expect this to reappear on any release that regenerates the Lovable MCP bundle — check it after
every pull.

`package-lock.json` had to be discarded (`git checkout --`) before the pull would proceed; it only
ever holds npm `libc`-field noise from the older npm on this box.

## 2026-09-03 — console errors on the module page: two real bugs, one benign

Three distinct errors were visible on `/journey/student/tech?tab=modules`. They are unrelated.

### 1. `student_module_progress` 400 ×2 — prerequisite lookup queried columns that do not exist

`PrereqCard` in `src/components/module/ModulePrerequisites.tsx` selected **`is_completed`** and
filtered on **`user_id`**. The table has neither — the columns are `completed` and `student_id` —
so PostgREST answered 400 (`column student_module_progress.is_completed does not exist`, with a hint
naming the right column). One request per prerequisite card, hence two in the console.

**The failure was invisible in the UI**: the result only toggles a tick, so a prerequisite the
candidate had already completed simply rendered as incomplete. Nobody would report it as a bug.

Fixed in `b554217`. `student_id` is read from **sessionStorage `"studentId"`** rather than derived
from `user.id`, because that is what the writer uses (`ModuleVideosPanel`, set by
`TechStudentJourney`). That value is the students-row id when a students row exists and **falls back
to the auth user id when it does not** — which is why the column holds a mix: of 263 rows, 140 match
`auth.users.id` and 123 match `students.id`. Filtering by `user.id` would have missed whichever rows
the writer stored under the other identifier.

**Follow-up bug the first fix introduced, then fixed in `727cbea`:** `(student_id, module_id)` has
**no unique constraint** and real duplicates exist — **9 pairs across 144 rows, one pair with 14
rows** — so the `maybeSingle()` answered **406 PGRST116** instead. The query now orders
completed-first and takes one row. Pinned by `src/test/modulePrerequisitesProgress.test.ts`.

### 2. `update-sms-gateway` 401 — deployed function was 10 lines behind and used a spoofable gate

The **deployed** copy gated on a client-supplied header:

```ts
const ADMIN_EMAILS = new Set(["prakash.chinnadurai@gmail.com"]);
const adminEmail = (req.headers.get("x-admin-email") || "").toLowerCase().trim();
if (!adminEmail || !ADMIN_EMAILS.has(adminEmail)) return json(401, …);
```

Any admin whose email was not that one literal got 401 — including `demo.admin@bankready.app` with a
perfectly valid JWT. **The same token worked on `admin-user-actions`, which is how the drift was
spotted:** if one admin function accepts a token and another rejects it, suspect a stale deployment
before suspecting the token.

The repo already had the fix (JWT + `user_roles` admin check). Synced it. Verified: admin **200**,
non-admin candidate **403 "Admin role required"**, spoofed `x-admin-email` with no JWT **401**. The
old gate was trivially bypassable by setting one request header, so this closes that too.

### 3. YouTube `postMessage` origin warnings — benign, not ours

`Failed to execute 'postMessage' on 'DOMWindow': target origin (https://www.youtube.com) does not
match recipient window's origin` comes from YouTube's own `www-widgetapi.js` handshake on embedded
players. It is noise from the third-party iframe API, appears on every page with an embed, and has
no effect on playback. Nothing to fix.

**Also still open (not touched):** `InstituteAnalytics.tsx`, `InstituteDashboard.tsx` and
`InstituteStudentManager.tsx` all filter `student_module_progress` on **`institute_id`**, which does
not exist on that table either — a guaranteed 400 on institute dashboards, same class of bug,
different screen. Left alone because the right fix (join through `students`, or add the column) is a
design decision rather than a rename.

## 2026-09-04 — redeployed to `473cd03` (5 commits pulled, then 3 fix commits) — two security regressions caught and reverted before shipping

5 commits forward from `727cbea`: CORS on OTP login, an Assessment Reports student menu, a
candidate-not-found fallback, and a "Fix SMS gateway auth" commit that was reviewed line-by-line
before deployment because its own diff looked wrong.

### Two real security regressions were caught and NOT deployed

**1. `update-sms-gateway` — the spoofable admin bypass came back.** The incoming commit replaced
the JWT + `user_roles` admin check (fixed 2026-09-03, see above) with a fallback: when no
`Authorization` token is present, it trusts a client-supplied `x-admin-email` header outright. Any
caller could set that header to any admin's address and reach SMS gateway settings with zero
authentication — the exact hole the earlier fix closed. It also doesn't compile as written:
`adminEmail` is declared `const` inside the `else` block and assigned without declaration in the
`if` branch above it, which throws at runtime for the no-token path. **Reverted** — restored the
JWT-only version.

**2. `previewAuthStorage.ts` — session token broadcast to any origin.** Changed
`window.parent.postMessage(msg, origin)` (looped over `editorOrigins`, a validated allowlist) to
`window.parent.postMessage(msg, '*')` — directly under a comment reading *"targetOrigin per trusted
editor origin, so a session token never reaches an arbitrary embedder."* The wildcard defeats
exactly the protection that comment describes; any page that embeds the app as `window.parent` could
read the brokered Lovable-preview session token. **Reverted** to the per-origin loop. This file is
marked "automatically generated. Do not edit it directly" — the generator itself produced the
regression.

Both reverts pushed as `c81721d`, with the legitimate part of that commit
(`student_module_progress.last_accessed` on save) kept.

### One real syntax bug found and fixed

`generate-candidate-path`'s new "candidate not found → beginner path" branch was missing its closing
brace **and** a return statement. Execution fell through into the found-candidate code path — which
queries `student_solved_challenges` keyed on `candidate.name` while `candidate` was still null in
that branch. `src/test/edgeFunctionSecurity.test.ts` (parses every edge function entrypoint) caught
it: `TS1005 'try' expected` / `TS1472 'catch' or 'finally' expected`. Fixed by closing the block and
adding `return new Response(JSON.stringify({ success: true, path }), ...)`, matching every other
branch's response shape. Verified live: an unknown `candidateId` now returns 200 with a real
beginner path instead of throwing. Pushed as `af0fd4d`.

### One RBAC gap found and fixed

`src/test/menuRbacReconciliation.test.ts` failed: the new `assessment-reports` menu key (added to
`AppSidebar.tsx` / `candidateAccess.ts` by the "Add Assessment Reports menu" commit) was never added
to `20260717203000_commercial_plan_menu_rbac_mapping.sql`, so it had no per-plan access row — every
other student menu item has one. Added, gated the same as `my-analytics` (excluded from free tier,
included from beginner up). **Note the test reads one specific migration file by path, not a live DB
query** — a standalone new migration file satisfies the DB but not the test; the fix has to land in
that seed file's own `values` list. Applied directly to the live DB (idempotent `ON CONFLICT`
upsert) and added to the seed migration for the next fresh environment. Pushed as `473cd03`.

### Standard checks

| Check | Result |
|---|---|
| Migration (`supabase/fix_student_usage.sql`, loose file not under `migrations/`) | fully idempotent against current state — `students`/`student_usage_daily`/`record_student_usage` already existed with matching shape from the 2026-09-02 release; effectively a no-op confirming consistency |
| Edge functions synced | `candidate-otp-login`, `generate-candidate-path` (post-fix); `update-sms-gateway` deliberately **not** synced from origin |
| Frontend | rebuilt (`index-ClWmF_mQ.js`); hash matches the 42P10-fix build since the RBAC change is DB-only |
| Tests | 406 passed / 407 — the one failure is the standing upstream `videoAutoLink` issue |
| Logins | candidate driven through the real UI to `/dashboard`; "Assessment Reports" now renders in the sidebar |
| Auth regression re-verified post-fix | admin JWT → 200; spoofed `x-admin-email` with no token → 401 |
| Rollback | `~/banking-predeploy-20260904T083302Z/` + `dist.bak-predeploy-20260904T083302Z` |

**Process note:** this release is the reason to actually read a "fix" commit's diff before deploying
it, not just its message — a commit titled "Fix SMS gateway auth" reintroduced the exact
vulnerability an earlier fix had closed, and "Fix candidate not found 404" shipped a syntax error
that would have taken the function down for every caller, not just the 404 case.

## 2026-09-05 — pulled `e0d0303`, test-only, no redeploy action needed

1 commit forward from `473cd03`: "Add Assessment Reports navigation tests and student journey
enhancements to E2E test suite" — adds `tests/e2e/student-journey.spec.ts` (a mocked-fixture
Playwright spec) and a committed `test-results.txt` binary artifact. **No migration, no app source,
no edge function.**

Pulled clean, `.env` untouched. No frontend rebuild or function restart performed — nothing shipped
to users changes when only a test file lands. Verified anyway: `npx vitest run` still 406/407 (same
standing `videoAutoLink` failure, unaffected), all 7 containers up, site/REST/auth all 200, served
bundle hash unchanged (`index-ClWmF_mQ.js`, expected since no source changed).

Worth a nudge to the team: `test-results.txt` is a binary Playwright output artifact committed
straight to `main` — that's normally `.gitignore`d, not tracked, since it's regenerated on every
run and only bloats history. Not fixed here since it's a repo-hygiene call, not a deploy blocker.

## 2026-09-07 — "Generate quiz" never worked: UUID module id into a bigint column (`9c4924b`)

"Generate quiz" on a module video always failed with the generic
**"Edge Function returned a non-2xx status code"**. Calling
`generate-lesson-video-quiz` directly exposes the real error the UI swallows:

```
invalid input syntax for type bigint: "0eb1c470-098d-425d-a9d7-3868a4e03ce4"
```

`video_lessons.module_id` is **bigint** — it holds ids from the legacy *numeric* module catalog, and
`generate-uploaded-video-mcqs` / `VideoMcqManager` both type it `number | null`. But
`InModuleVideoQuiz` on the Student Journey passes the **UUID** of an `admin_modules` row.

The function had `const moduleId: number | null = body?.moduleId ?? null` — **a compile-time claim
only.** Deno does not validate the request body, so the UUID string went straight to Postgres. The
insert is the *first* write in the flow, so every call died before any generation work:
`video_lessons` was **empty (0 rows)** — this path had never once succeeded.

Fixed by coercing rather than trusting the annotation: a genuinely numeric id still populates the
bigint column, and a non-numeric one is preserved as `metadata.source_module_id` instead of being
silently dropped, so the lesson stays traceable to its module. **The column and the other two
writers were left alone** — the numeric contract is intentional for the legacy catalog, so changing
the column type would have broken them.

Verified with the exact failing payload: **HTTP 200**, lesson row created with `module_id` null and
`source_module_id` = the UUID, `generation_status: success`, **8 MCQs** persisted. Probe row and its
questions deleted afterwards (`video_lessons` back to 0).

**Pattern worth noting:** this is the third Banking bug in a row where a TypeScript annotation on an
edge-function request body was mistaken for validation. Deno edge functions receive untrusted JSON;
`const x: number = body?.x` proves nothing at runtime.

### Same deploy — 22 upstream commits, 2 migrations

Rebased onto 22 commits that landed mid-work (none touched the quiz function). Applied
`20260904143000_assessment_reports_menu_access` and
`20260906090000_release_readiness_high_priority` — only idempotent `drop policy if exists`
recreations, no data deletion. Synced 5 changed functions; frontend rebuilt (`index-7wATd1Lx.js`).

**Both earlier fixes survived upstream this time:** `update-sms-gateway` still has the JWT +
`user_roles` gate (`x-admin-email` now appears only in the CORS allow-list, not the auth path), and
the `generate-candidate-path` syntax fix is intact. The `mcp@0.26.3` local patch also still holds.

**Test suite moved to 435/436.** The long-standing `videoAutoLink` failure is now fixed upstream; a
different one took its place: `authLockRegression.test.ts` asserts
`TIMEOUT = 600` / `RETRY_DELAY = 100` in `previewAuthStorage.ts`, but upstream commit `e832518`
("Work in progress") raised them to **2000 / 250**. Worst-case broker wait goes from 1.3s to 4.25s —
still under GoTrue's 5s lock-recovery window, so the test's *stated intent* holds while its literals
no longer match. **Not touched**: it is an upstream WIP change, the code path is inert outside
Lovable preview hosts (it returns `localStorage` unless on a preview zone *and* framed), and whether
4.25s is acceptable or the literals should be updated is their call.

## 2026-09-07 — "YouTube returned no playable video links" was an exhausted quota (`74db0f2`)

"More YouTube videos" on a module showed **"YouTube returned no playable video links"**. The
video catalogue was fine; the daily YouTube quota had been spent. **The banking key had already been
swapped to a fresh one (`AIzaSyBw9UaMng…`) by the time this was investigated**, so the symptom had
self-resolved — `ai-video-suggest` returns 5 valid `watch?v=` URLs again, and `getYouTubeId` parses
all 5 correctly. Nothing was wrong with the parser or the videos.

Two defects made an expired allowance look like a broken feature, both now fixed:

**1. Only 403 was treated as quota.** `ai-video-suggest` checked `response.status === 403`, but
YouTube reports a spent daily allowance as **429 `rateLimitExceeded` / `RESOURCE_EXHAUSTED`**
(observed directly against the live API several times this session). A real exhaustion therefore hit
`continue` and ended at the generic *"No YouTube videos found for generated queries"*. Now matches
403, 429, **and** the quota markers in the response body, reporting *"YouTube daily quota exhausted -
resets at midnight Pacific"*.

**2. The UI threw away the explanation.** In `mode: "bulk"` the fallback is
`{ best: fallback, alternatives: [fallback] }` — so `alternatives` is **non-empty** and passes the
frontend's `!data?.alternatives?.length` guard, but every entry is a `results?search_query=` URL that
`getYouTubeId` correctly refuses. That left 0 videos and the generic message, while the function had
already put the real cause in `verification.reason`. `ModuleVideosPanel` now surfaces that reason.

**This is the third occurrence of the same trap** in this codebase — a YouTube 429 surfacing as a
misleading "no videos" message (the others: the module-video backfill script, and PilVidya's
curriculum videos). Fixed in the shared paths rather than at the call site.

**Not verified against a live 429** — forcing one would mean deliberately exhausting the quota and
breaking the feature for real users. The old key's quota had already reset, so it could not be used
to reproduce. The happy path was regression-tested: 5 alternatives, 5 parseable watch URLs.

Also confirmed in the same screenshot: the 2026-09-07 quiz fix is working — the module showed
**"8 questions ready"**.

## 2026-09-07 (later) — "Checker agent rejected candidates" is non-determinism, not a broken catalogue (`b5262ee`)

After the quota-message fix above started surfacing the real reason, the message became:

> Could not fetch more videos: Checker agent rejected candidates: None of the candidate videos cover
> 'The Dual Nature of Financial Systems', which is a critical part of the requested topic...

**That is the improved error reporting working** — but it exposed the actual cause.

Topic titles in these AI-generated modules follow **"Concept: editorial framing"**. The Quantum
Physics module (`0eb1c470…`, a physics module inside a *banking* app) has:

- `Wave-Particle Duality: The Dual Nature of Financial Systems`
- `Entanglement: Interconnectedness in Global Financial Systems`
- `Heisenberg Uncertainty Principle: The Trade-off in Financial Information`
- `Superposition: Navigating Probabilistic Outcomes in Banking Decisions`

No real YouTube video covers the grafted-on finance framing, so the checker agent — **an LLM** —
judges these borderline titles **inconsistently**. Measured directly on the reported topic:

| Run | Hybrid title | Concept only |
|---|---|---|
| 1 | rejected | — |
| 2 | rejected | — |
| 3 | 2 playable | — |
| — | — | **5 playable, reliably** |

So it was a **coin flip (~2 in 3 failing)**, not a broken feature — which is exactly why it looked
intermittent to the reporter and why it had "fixed itself" between screenshots.

**Fix:** when the full title yields no approved candidates, `ModuleVideosPanel` retries **once** with
the text before the colon and uses that result if it produces videos. The retry goes through the same
verification pipeline, so it recovers from an over-strict pass **without weakening any check**, and it
never fires for titles lacking that pattern.

**Deliberately not addressed:** whether a Quantum Physics module with finance-flavoured topic titles
belongs in a banking app at all. That is an editorial/content decision, not something to paper over in
video search — flagged for the team rather than silently "corrected".

**Diagnostic note:** when an LLM-judged step reports a plausible-sounding rejection, run it 3+ times
before believing it. Both this and the earlier quota trap presented as deterministic feature failures
and were not.

## 2026-09-07 (later still) — LLM checker + relevance gating disabled for ai-video-suggest (`ca1516b`)

Requested: *"skip the video checker and stick with maker as of now."* **Two** layers were rejecting
candidates, and skipping only the first was not enough:

1. **The LLM checker agent** — non-deterministic on hybrid titles (rejected 2 of 3 identical runs).
2. **The deterministic RELEVANCE gate** — this became the new failure once the LLM checker was off.
   `overlapRatio` divides matched tokens by the number of **topic** tokens, so
   `"Wave-Particle Duality: The Dual Nature of Financial Systems"` is diluted by words no real video
   can match (*financial, systems, nature*), pushing genuine physics videos below the score-35 bar.
   A 4-run check still failed twice with *"No public, embeddable, topic-relevant videos passed
   verification"*.

**Still enforced:** public, embeddable, not-live, sane-duration. An unplayable video can never be
attached. The relevance score is still computed and still **ranks** results — it just no longer
rejects.

**One switch: `AI_VIDEO_LLM_CHECKER`.** Unset (current) = maker-only. `on` = previous behaviour (LLM
checker + full relevance gating), no code change required.

`relevanceGating` is **opt-out on the shared validator, defaulting to true**, so
`generate-trainer-curriculum` and `src/test/youtubeVideoValidation.test.ts` keep strict behaviour —
only `ai-video-suggest` opts out.

**Result:** the reported topic returned **5 playable videos on 5 consecutive runs** (previously
failing ~2 in 3), all confirmed public + embeddable against the YouTube API.

**The trade-off, accepted deliberately — worth knowing before this is called "fixed":** without
relevance gating, hybrid titles pull in videos matching the *finance* half rather than the concept.
That same verified run returned **"The Dual Nature of Bitcoin"**, **"The Green Dot and the dual
system"**, **"Efficient Market Hypothesis"** and **"The Keynesian Beauty Contest"** alongside one
genuine photoelectric-effect lesson. Reliability was chosen over precision; **the durable fix is the
topic titles**, not the search pipeline. If precision matters more later, set
`AI_VIDEO_LLM_CHECKER=on` and fix the titles instead.

## 2026-09-09 — redeployed to `1d1d81b` (student journey and challenge workflow)

Banking UAT moved 15 commits from `ca1516b` to `1d1d81b`. The release adds resumable module
navigation, completion certificates, challenge integration and an explicit **Save Challenges**
action; it also repairs the candidate-home route, candidate mobile normalization, OTP/password-reset
handling, lesson-video quiz generation, assessment difficulty handling, and text fallback when an AI
model cannot accept image input.

Migration `20260811113000_add_difficulty_to_assessment_questions.sql` applied transactionally. It
adds the non-null `assessment_questions.difficulty` column constrained to `Easy`, `Medium`, or
`Hard`, defaulting existing rows to `Medium`. Verified after application: 919 existing questions,
all 919 `Medium`; no rows were removed or rewritten beyond the defaulted new column.

Changed edge functions (`candidate-otp-login` shared helper, YouTube validator,
`generate-lesson-video-quiz`, and `request-password-reset`) were synchronized. The UAT-only MCP
patch remains in place: `@lovable.dev/mcp-js@0.26.3` and project ref `banking-uat-selfhosted`.

Verification: build succeeded; 7/7 self-hosted backend containers are up and the database is
healthy; site, candidate login, REST, and Auth health return 200. A real fresh-browser candidate OTP
login (`9820065335` / `1234`) reached `/candidate/home`, and admin login reached `/admin`, with zero
page errors, zero `/sb` API errors, and zero hosted-Supabase requests. Unit/security suite retains
the same single stale `authLockRegression` assertion (435/436 baseline); its generated preview-only
timeout literal changed upstream, while the runtime path remains below GoTrue's lock recovery
window.

Rollback snapshot: `~/banking-predeploy-20260909T140819Z/` (database dump, function archive,
previous `dist`, env, source SHA, and local patch diff).

## 2026-09-10 — lesson-video quiz generation compile failure fixed (`556b2ea`)

`generate-lesson-video-quiz` returned HTTP 500 for every video because its AI-response parsing
block had been duplicated, redeclaring `aiJson` and `args` in the same scope. The edge worker could
not compile (`SyntaxError: Identifier 'aiJson' has already been declared`). Commit `556b2ea`
removes the duplicate six-line block; there is no schema migration or frontend change.

The corrected function was synchronized to Banking UAT and verified through the public gateway:
an end-to-end request returned HTTP 200 with a lesson id and two generated questions. The probe
lesson and its questions were deleted afterward. All seven `banking-sb-*` containers remained up,
the database remained healthy, and site/Auth health returned 200.

Rollback snapshot: `~/banking-predeploy-20260910T091638Z/` (previous function archive, UAT env,
source SHA, and local patch diff).

## 2026-09-12 — redeployed to `63a49d2` (student credits and coding persistence)

Banking UAT advanced eight commits from `556b2ea` to `63a49d2`. The frontend adds the student
credits dashboard/link and awards ten credits from the module-completion path. The
`student_credits` table and `award_module_completion_credits(uuid, integer)` RPC were applied, and
the coding-challenge persistence migration was reconciled against the already richer UAT tables.

Three incoming scripts were deliberately not executed verbatim: the duplicate assessment baseline
would recreate already-established objects/policies; `20260911131000` targets nonexistent
`public.storage_buckets` instead of self-hosted `storage.buckets`; and the two RLS/function
hardening scripts contain incompatible `has_role(uuid,text)` calls plus invalid PostgreSQL policy
syntax on a function. Their transactions were preflighted and rolled back without partial changes.

The frontend was rebuilt on UAT and serves `index-B3-bR9Wx.js`. Site/Auth health return 200, all
seven backend containers are up, and the database is healthy. Rollback snapshot:
`~/banking-predeploy-20260912T090241Z/`.

## 2026-09-16 — `bulk-export-worker` re-ran a job forever (~300 Gemini calls/hour); fixed in `f3c706f`/`6295e0a`, UAT routed through the LiteLLM gateway

**Symptom (hosted project):** Google AI Studio showed a flat ~340K input tokens/hour on
`gemini-3.6-flash` for 18+ hours. Every request body started with
`Evaluate banking job readiness.\nCandidate: … Assessment: Banking - AML and KYC …` — the
per-attempt "job readiness" prompt built in `supabase/functions/bulk-export-worker/index.ts`
(Assessment Analytics → Bulk Export PDF/Excel). Model was `gemini-3.6-flash` because the hosted
project has no usable gemini row in `llm_provider_configs`, so `_shared/llm.ts` falls to the env
`GEMINI_API_KEY` with `PROVIDER_DEFAULTS.gemini.model`.

**Root cause:** the worker is cron-invoked every minute, picks a `pending` job or a `running` job
whose `heartbeat_at` is > 3 min old, processes a 20-attempt chunk (one LLM call per attempt) and
writes progress. Every `bulk_export_jobs` write ignored its `{ error }` (supabase-js does not
throw), and `max_attempts` was only enforced on a path `Promise.allSettled` can never reach. If the
chunk/finalize write failed — or the isolate was killed before persisting — the job stayed
`running`, went stale, and was re-picked indefinitely: 20 calls every ~4 min = 300/hour, ~1.1K
tokens each. UAT still holds two rows from the hosted era with `total = 1` and
`attempts = 14976 / 15058` (2026-07-02 → 08-09, when `processed_results` did not exist yet).
`Cancel` in the admin panel was also clobbered by an in-flight invocation writing `running`/`pending`.

**Fix (`main` `f3c706f` + `6295e0a`):**
- every `bulk_export_jobs` write goes through `updateJob()` — a failed write fails the job;
- stale-heartbeat recoveries count against `max_attempts` (a chunk that persisted normally comes
  back as `pending` and does not count) → `failed` with
  `abandoned after N failed recoveries at <progress>/<total>`;
- all writes carry `.neq("status","cancelled")`, and a job fetched by `job_id` that is no longer
  `pending`/`running` is skipped;
- `_shared/llm.ts`: a provider row whose `provider = 'litellm'` gets the header
  `x-litellm-tags: service:banking-app,module:<feature>` so the gateway attributes the call.

**UAT (deployed 2026-09-16, `~/banking-sb/sync-functions.sh`):** `llm_provider_configs` has a
per-feature row `application_feature = 'bulk-export-worker'`, `provider = 'litellm'`,
`base_url = https://uat.pluginlive.com/ai-gateway/v1`, `default_model = gemini-2.5-flash`,
priority 1, api_key = UAT gateway virtual key alias **`banking-app`** (`~/litellm/banking_app_vkey.txt`).
`selectFeatureConfigs` puts feature rows ahead of `global`, so only this function is routed;
everything else still uses the global gemini row. Verified: a 2-attempt export completed and both
calls appear in `LiteLLM_SpendLogs` with `request_tags = [service:banking-app, module:bulk-export-worker]`
under key alias `banking-app`; a seeded stale job with `attempts = 2` was marked `failed` with zero
LLM calls; a `cancelled` job invoked by `job_id` stayed `cancelled` with zero LLM calls.

**Hosted / PROD is NOT deployed** — nobody on the team holds credentials for `kbwjokmmzkgjwiqelrdc`.
Until it is, kill the runaway in the hosted SQL editor:
`update public.bulk_export_jobs set status='failed', last_error='killed: infinite re-pick loop', finished_at=now() where status in ('pending','running');`
(the panel's Cancel button is not enough on the old code). The authoritative call count lives only in
Google AI Studio usage-by-model for that key; the app's `llm_usage_logs` is written by the `chat`
function alone.

**Note on the UAT box:** at 04:15 UTC on 2026-09-16 the banking, pilvidya and eduspeak nginx vhosts
were unlinked and their containers removed. Banking was brought back for this deploy
(`docker compose up -d` in `~/banking-sb`, vhost re-linked); pilvidya and eduspeak were left down.
UAT has no pg_cron, so only the enqueue kick runs the worker — a job with > 20 attempts stalls after
its first chunk there (pre-existing, unchanged).

## 2026-09-19 — restored after the 09-18 teardown + redeployed to `a8c32ef` (60 commits, 8 migrations)

Banking UAT had been taken down 2026-09-18 with `docker compose stop` and the vhost unlinked. By
the next morning the stopped containers were **gone**: `/usr/local/bin/system-cleanup.sh` (root
cron `/etc/cron.d/system-cleanup`, 03:00 daily) runs `docker image prune -af` and
`docker container prune -f --filter until=24h`, so any stopped container older than a day and every
image not attached to a running container is deleted nightly. Named volumes survive (`volume prune`
without `--all` only takes anonymous ones), so `banking-sb_banking-pgdata` / `banking-sb_banking-storage`
were intact — 70 profiles, 70 auth users, 52 students, 9 trainers, all present. **"compose stop" is
not a restorable state on this box, and no rollback image survives a night.** Restore is
`docker compose up -d` in `~/banking-sb` (recreates from the compose file against the volumes).
Predeploy: `~/banking-sb/banking_uat_predeploy_20260919T143901Z.dump`,
`~/bankingjobreadiness/dist.bak-predeploy-20260919T143901Z/`, `.env.bak-predeploy-20260919T143901Z`.

**Release content:** trainer workspace & portal (`/login/trainer`, `/journey/trainer`), module
builder flow wired, trainer bulk student onboarding (`trainer_bulk_jobs` + `bulk-create-users`),
curriculum submissions with revision history, trainer diff pins, cursor-paged trainer CSV/PDF
export jobs (`trainer_export_jobs` + ten `SECURITY DEFINER` RPCs gated by
`trainer_request_allowed()`), per-module question bank (`module_questions`), curriculum
subject/topic/subtopic hierarchy, `findAndLinkMigratedStudent` fallback for students with no
email/mobile, `students.onboarded_by`, unique `students.user_id` / `trainers.user_id`.

**The `.env.local` landmine fired.** `a8c32ef` commits `VITE_SUPABASE_URL` /
`VITE_SUPABASE_ANON_KEY` for a hosted project (`pfzstzxffbentcxlrior`) in `.env.local`, which Vite
loads above `.env`. A plain `npm run build` would have shipped a UAT bundle pointing at that
hosted URL. Built instead with the three `VITE_SUPABASE_*` values from `.env` exported as **shell
env**, which outranks every `.env*` file. Bundle audit after build: the only `supabase.co`/project-ref
strings are the `AdminSecurityMigration` panel's default form value and a vendor `api.supabase.co`
constant — not endpoints; `https://banking.uat.pluginlive.com/sb` appears 10×. Do this on every
banking build from now on.

**Migrations — three needed `fixups/` (the replay mechanism where a same-basename file wins):**

| File | On UAT |
|---|---|
| `20260311153726_4dc873b4…` | **No-op fixup.** Added upstream in "Connected to Lovable Cloud" as a fresh-project baseline (`CREATE TYPE app_role`, `CREATE TABLE profiles/user_roles/modules/…`). Everything exists here from the 118-file replay and `CREATE TYPE` has no `IF NOT EXISTS`. |
| `20260919082444`, `082524` | Verbatim. Dedupes by `user_id` (0 duplicates here) then unique indexes on `students.user_id` / `trainers.user_id`. |
| `20260919083047`, `083502`, `092440` | Verbatim (`IF NOT EXISTS` throughout). |
| `20260919085510_6785f3d3…` | **Fixup.** Upstream's own `20260710120000_pil_feature_merge_compat.sql` already created stub `curriculum_submissions` / `curriculum_submission_history` / `trainer_export_jobs` with different columns (the stub `trainer_export_jobs` had `export_type` and none of `trainer_email`, `format`, the cursor columns the new RPCs insert), and this file re-creates them with bare `CREATE TABLE` — so it fails on any DB that ran the compat file, which is an upstream self-inconsistency. All three stubs were empty. The fixup is a DO-block guard that raises if any of them has rows, `DROP TABLE … CASCADE`, then the upstream file verbatim, then re-adds `trainer_export_jobs` to the `supabase_realtime` publication (`sql/04_realtime_publication.sql` had it). |
| `20260919091651_8cbeaf45…` | **Fixup**, same reason: compat stubs for `curriculum_subjects` / `curriculum_topics` / `curriculum_subtopics` (subjects/topics had no `updated_at`, yet this file attaches an `updated_at` trigger to them). Empty; guard + drop + upstream verbatim. |

`sql/03_grants.sql` + `04_realtime_publication.sql` reapplied. 87 functions synced with the 3
standing function-fixups (`main`, `mcp`, `live-session-rsvp`), 0 boot errors.

Verification: `/`, `/admin/dashboard`, `/sb/rest/v1/`, `/sb/auth/v1/health` 200; all new tables
200 through PostgREST; `candidate-otp-login` → its validation body, `bulk-create-users` → "Not
authenticated", `ai-personal-coach` / `generate-daily-practice-plan` → 400 validation (handlers
load). Headless browser on `/`, `/admin/dashboard`, `/login/trainer`, `/journey/trainer`: 0 page
errors, 0 failed requests, 0 `supabase.co` requests, 0 `/sb` ≥400.

### 2026-09-19 (later) — "migration is not done properly": full reconciliation of all 190 files

The morning pass applied only the 8 files that were *new in the diff*. That was the wrong unit of
work for this stack: `replay-migrations.sh` runs each file as one transaction and **records
nothing durable**, so `migration-run/ok.txt` / `failed.txt` were a stale 2026-08-22 snapshot
(157 of the then-files; 43 of the 44 "failures" were benign "already exists" on the first
statement — which says nothing about whether the *rest* of that file ever landed). Several
files had in fact never fully applied and nobody could tell.

**New tool — `~/banking-sb/reconcile.py`** (source of truth from now on). Walks every migration
in replay order (fixup wins over upstream), extracts what each expects to exist — tables,
columns, functions, policies, indexes, triggers, enum values, views, storage buckets — honours
later `DROP`/`RENAME`s, then diffs against the live catalog and prints MISSING grouped by file.
First run: **118 missing objects across 10 files.** After this pass: 12, all explained below.
`~/banking-sb/apply_list.sh dry|real` runs a named list of files fixup-aware (dry = each file in
a rolled-back transaction, so pre-file dependencies show as false failures there).

**What had never landed, and why:**

| File | Root cause | Resolution |
|---|---|---|
| `20260811015532` | `module_group_assignments` / `trainer_students` pre-existed as compat stubs with fewer columns → `CREATE TABLE IF NOT EXISTS` skipped, bare `CREATE POLICY` aborted the file on 08-22. `created_by`, `updated_at`, `assigned_by` never added. | fixup: explicit `ADD COLUMN IF NOT EXISTS` + `DROP … IF EXISTS` guards; rest verbatim |
| `20260811113000_assessment_tables_schema` | never applied (six `*_select_authenticated` policies missing) | verbatim |
| `20260811113000_minimal_assessment_tables` | **broken upstream everywhere**: `format('…"_%_auth_select"…')` — `%_` is not a specifier. Its table shapes (`selected_answer`, `event_type`/`payload`) also contradict hosted `types.ts` (`selected_option`, `violation_type`), so hosted never ran it either | no-op fixup |
| `20260811163000` | never applied | verbatim (admin_section_content repair) |
| `20260822041849` | failed 08-22 ("permission denied for schema extensions"), never revisited; also assumes `trainers.department/password` and `students.password` exist. So the bcrypt password trigger, `verify_trainer_password()`, `trainers_college_idx`, the four trainers policies and the reminder_deliveries fix were all missing | pre-file `20260822041848_uat_…` adds the columns; upstream verbatim |
| `20260823105238` | tables pre-existed as stubs → `student_module_progress.student_name/completed_at/score`, `student_assessment_scores.student_name/module/max_score/created_at`, `proctoring_defaults.config` never added (all present on hosted per `types.ts`) | pre-file `20260823105239_uat_…` adds them |
| `20260828133000` | never applied: **`video_generation_jobs` did not exist**, nor `curriculum_videos.media_*`/`generation_*`, the taxonomy validators/triggers, `save_module_group_mapping()` | verbatim |
| `20260829164121` | `sms_gateway_settings` pre-existed as a compat stub (`api_key_encrypted`, `settings`; none of the OTP/provider columns `candidate-otp-login` reads), file uses bare `CREATE TABLE` | fixup: guard-if-rows → drop stub → verbatim; pre-file `20260829164122_uat_…` recreates the `sms_gateway_public` view the drop cascaded away, with the four columns `update-sms-gateway/index_test.ts` specifies |
| `20260911130000` (security RLS fix) | calls `has_role(uuid, text)` which this DB never had; also bare-creates three `student_solved_challenges` policies that `20260811140000` already created → aborts on any DB incl. hosted | pre-file `20260911125900_uat_has_role_text_overload.sql`; fixup adds `DROP POLICY IF EXISTS` before each create so this file's later definitions win, except the two `practice_plans` policies the even-later `132000` redefines |
| `20260911132000` (function hardening) | **broken upstream everywhere**: `LANGUAGE plpgsql` with a bare SQL body (syntax error), `CREATE POLICY … ON <function> FOR EXECUTE` (not SQL), and a `practice_plan_tasks.student_id` predicate on a column the table has never had (ownership is via `plan_id`) | fixup: `LANGUAGE sql`, function "policy" as `REVOKE/GRANT EXECUTE`, task-read policy via `plan_id → practice_plans.student_id` (the form `20260811235500` uses) |

Remaining 12 "missing" after the pass, all intentional: the compat stub's `sms_gateway_settings.api_key_encrypted/settings` (superseded by the real hosted shape), the nine never-real columns from `assessment_tables_schema`, and a `pg_temp` function.

**Column-level boundary — `sql/05_sensitive_columns.sql`** (wired into `rebuild.sh` step 6 after
`03_grants.sql`; re-run it after any migration that adds columns to those tables). Postgres
cannot revoke one column out of a table-level grant, so upstream's `REVOKE SELECT (password)`
is a silent no-op — on hosted too. The script recomputes the allow-list from the catalog:
`students.password` / `trainers.password` hidden from **anon only** — the frontend does
`.select("*")` on both tables as the signed-in user (TrainerProfile, StudentProfilePage,
Institute*Manager, useTrainerData), so restricting `authenticated` would break those screens;
hosted behaves the same. **Residual upstream defect: signed-in users can read bcrypt hashes.**
`sms_gateway_settings`: anon sees only `provider, enabled, otp_length, otp_validity_minutes`
(the test file's spec); `authenticated` keeps the full row.

`trainer_curricula.module_id` is `text` here (today's `20260919091651` declared it so and ran
first); in upstream order `20260828133000` would have made it `uuid` FK→`modules`. Kept `text`
(superset, both rows null, hosted `types.ts` can't distinguish).

Verification: reconcile clean (12 explained); `video_generation_jobs`, `student_module_progress`,
`student_assessment_scores`, `trainers` 200 via PostgREST; anon `trainers?select=password` and
`sms_gateway_settings?select=*` → 401, `sms_gateway_public` → 200 with the four fields; triggers
`students_hash_password`, `trainers_hash_password`, `validate_trainer_curricula_taxonomy`,
`update_sms_gateway_settings_updated_at` present; functions 0 boot errors; browser E2E on `/`,
`/admin/dashboard`, `/login/trainer`, `/journey/trainer`, `/login/candidate` 0 errors / 0 hosted /
0 `/sb` ≥400. Two real trainer signups (`/auth/v1/signup` → token 200) happened mid-pass —
data counts moved 70→72 profiles, 9→11 trainers for that reason, not from the migrations.

## 2026-09-21 — redeployed to `b505d58` (19 commits, 3 migrations; RBAC Trainer filter)

Trigger: Admin → User Management → **Roles & Access** role filter listed only *All / Admin /
Taxonomy Editor / Candidate* — `trainer` was never added to the hardcoded `<Select>` in
`src/components/admin/AdminRBAC.tsx`, even though the per-row badges and the `filtered`
predicate (`u.roles.includes(filterRole)`) already handled any `user_roles.role`. Fix is one
`<SelectItem value="trainer">` (our commit `b505d58`, rebased onto upstream `abe40cb`, pushed to
`main`). Verified live headless as `demo.admin`: options now `All Roles / Admin / Taxonomy
Editor / Trainer / Candidate`; selecting Trainer → `Select all (12)`, 12 rows all badged
`trainer`, 0 page errors, 0 `/sb` ≥400.

**Deliberately NOT added:** Trainer to the per-row *Roles ▸ Assign roles* menu
(`ASSIGNABLE_ROLES` stays `admin | taxonomy_editor`). Trainer login needs a matching
`trainers` row (see *Login.tsx* trainer branch: "Trainer profile not found" + forced signOut);
granting only the `user_roles` row from RBAC would mint accounts that cannot log in. Trainer
provisioning stays on the registration → *Trainer / Teacher Journey* approval path.

**Upstream carried in (`a8c32ef`→`abe40cb`, 18 commits):** LLM hallucination-detection hook +
`RiskLevelBadge` in the AI coach widget; institute/city masters on the registration form
(`Login.tsx` now loads `institutes` + `cities` and can add new ones inline); vitest/CI scaffolding
(`.github/workflows/test.yml`, `supabase/tests/`). No edge function changed — functions not
re-synced. `package.json` change is scripts-only, no `npm install` needed.

**Migrations — 2 of 3 replayed as shipped, 1 via fixup:**

| File | UAT | Why |
|---|---|---|
| `20260919100000_institute_city_management` | applied verbatim | additive: `cities`, `institute_city` (UNIQUE institute+city), `institutes.city_id` + index, RLS admin-write via `has_role`; backfills `city_id` from the legacy `institutes.city` text |
| `20260919110000_add_admin_role_for_sms_gateway` | applied verbatim, **no-op** | inserts `admin` + `super_admin` for `prakash.chinnadurai@gmail.com` only `WHERE admin_role_count = 0`; UAT has 14 admins. Would have failed on hosted-shaped DBs lacking `super_admin` — UAT's enum already had it |
| `20260919110001_fix_super_admin_enum` | **fixup** `~/banking-sb/fixups/<same name>.sql` | upstream recreates `app_role` as `('admin','trainer','student','super_admin')` via `ALTER COLUMN … USING role::text::temp_app_role` then `DROP TYPE app_role CASCADE`. On UAT it fails on the 69 `candidate` / 8 `taxonomy_editor` rows, and the CASCADE would drop `has_role()` plus ~255 dependents (every RLS policy). Also has bare `RAISE NOTICE` outside a DO block (syntax error). Fixup keeps the intent: enum value already present, so only the guarded `super_admin` backfill for that email runs (1 row) |

Do **not** let `20260919110001` run verbatim on any environment that has candidates — which is
all of them. Its own header claims "the enum only has admin and trainer", which is false
everywhere this app has ever been deployed.

Post-apply: `NOTIFY pgrst, 'reload schema'` (anon `cities?select=id` → 200); `reconcile.py` at
the known 12 explained leftovers; `candidate` rows still 69; `super_admin` rows 0→1.

Build: `set -a; . ./.env; set +a` then `npm run build -- --outDir /tmp/banking-dist-new`,
audited (`api.supabase.co` vendor hit only, self-hosted `/sb` URL present, `value:"trainer"`
option compiled), then atomically swapped into `dist/`. Snapshot
`~/banking-predeploy-20260921T075713Z/` (dist + env) and
`~/banking-sb/banking_uat_predeploy_20260921T075713Z.dump`. Local UAT-only diffs (`.env`,
`supabase/functions/mcp/index.ts`) carried across the rebase via stash, still present.

## 2026-09-22 — redeployed to `d0ebf23` (5 commits, no migration/functions)

Trivial follow-on to the 09-21 deploy: `.env.local` finally deleted upstream (the tracked-file
landmine flagged since 08-04 is gone from `main` now — still worth diffing after every pull in
case it comes back), and `src/integrations/supabase/types.ts` regenerated to match yesterday's
`cities`/`institute_city` tables. No `supabase/migrations` or `supabase/functions` changed, so
this was a pure frontend rebuild: snapshot (`~/banking-predeploy-20260922T040437Z/`, dist+env
only, no DB dump needed since nothing DB-side changed) → `npm run build`, audited (`api.supabase.co`
vendor hit only, self-hosted `/sb` URL present) → swapped into `dist/`. 7/7 containers up, site
+ auth 200, headless check on `/`, `/login/admin`, `/login/trainer`, `/login/candidate`: 0
page errors, 0 API errors.

## 2026-09-23 — redeployed to `420de1d` (30 commits, security remediation + 3 fixups)

30 commits: role-based home/login revamp, gamification (XP/streak/daily quests), trainer
journey completion, idempotent coding-challenge saves, admin journey hardening, 11 edge
functions changed, `vite.config.ts` manual chunks. Snapshot `~/banking-predeploy-20260923T145521Z/`
(dist, env, functions tarball) + `~/banking-sb/banking_uat_predeploy_20260923T145521Z.dump`.

**Behaviour users will see**
- Candidates land on the new `/onboarding/diagnostic` after OTP login; admins land directly on
  `/admin/dashboard` (the old bounce-to-`/` described in the demo-logins note no longer happens).
- **Session no longer survives a browser refresh unless "Remember me" is ticked** (e3a5f08
  session hardening). Verified both ways headlessly. Intended, but expect "refresh logged me out".
- **Trainers now see only their own profile + profiles of students mapped to them in
  `trainer_students` — which has 0 rows on UAT.** Before this deploy every signed-in user
  (not only trainers) could read all 72 profiles via `USING (true)` policies. Trainer screens
  that list student profiles will be empty until mappings exist (Admin → Trainer Assignments).

**Migrations**

| File | UAT | Why |
|---|---|---|
| `20260922160000_student_gamification` | verbatim | new `student_gamification`, `daily_quests`, XP trigger |
| `20260923000000_repair_missing_modules` | **skipped** | invalid SQL (`DO BEGIN … END` with no `$$`) and it is a PilVidya file: FKs to `student_profiles`, touches `live_classes`/`school_events`/`curriculum_content`, none of which exist in Banking. Same cross-repo workspace leak as 09-21/09-22 |
| `20260923032440_…` | verbatim | `coding_challenges` +4 cols; its "any trainer reads every profile" policy is dropped by the next file |
| `20260923100000_security_audit_remediation` | **fixup** (2 changes) | drops *every* policy on 27 sensitive tables and rebuilds owner / admin / mapped-trainer policies; private buckets + signed-URL paths for `attachments`. Fix 1: its `has_role` service-role bypass read `request.jwt.claim.role`, which PostgREST 12 no longer sets (probed live: `null`; only `request.jwt.claims` is set) — as shipped, every service-role `has_role` check (`mcq-admin-action`, `tech-modules-bulk-import`) returns false → admin actions 403. Fixup also reads `request.jwt.claims->>'role'`. Fix 2: `practice_plan_tasks` has no `student_id` here; owner check goes through `plan_id → practice_plans.student_id` |
| `20260923100001_uat_deltas_from_edited_migrations` | UAT-only | upstream **edited five already-applied migrations** (never re-run on an existing DB). All superseded by the remediation except: student `my-learning` menu row (inserted `DO NOTHING` — re-running that seed would `DO UPDATE` over admin-customised menus) and `admin_list_ai_coach_audit` — SECURITY DEFINER and **anon-executable**, i.e. the whole AI-coach audit log was anonymously readable. Upstream's fix declares it `plpgsql` with a bare SELECT (won't compile); applied as `language sql` + in-body admin check + revoke anon |

`video-lessons` stays public: the old-file edit made it private, but the remediation (the later,
deliberate file) leaves it out; followed the remediation.

**`~/banking-sb/sql/03_grants.sql` now ends with REVOKEs** (backup `.bak-20260923`): its blanket
`GRANT EXECUTE ON ALL FUNCTIONS … TO anon` silently re-opened `admin_list_ai_coach_audit` and
`has_role` on every run. Re-run it any time; the revokes now stick.

**Verification.** Dry-run of all files in one rolled-back transaction with impersonation:
admin 72 profiles / is_admin true; pure trainer 1 profile; candidate 1 profile, cannot probe
another user's admin role; `service_role` (claims-only, as PostgREST 12 sets it) `has_role` true;
anon 0. Live: 7/7 containers, 87 functions synced (3 fixup overlays) with 0 runtime errors,
bundle has no hosted/DEV URLs, headless candidate + trainer OTP login and admin login all 0 page
errors / 0 `/sb` ≥400, admin Roles & Access lists 72 users and the Trainer filter returns 12.
`reconcile.py` now reports 143 "missing": the known 12, the skipped PilVidya file, a
parser false-positive on the gamification columns (verified present), and **the old policies
the remediation deliberately dropped**. Expected; don't "restore" them.

## 2026-09-24 — redeployed to `b8008e6` (14 upstream commits + 1 auth fix, 7 migrations)

Snapshot `~/banking-predeploy-20260924T015735Z/` + `~/banking-sb/banking_uat_predeploy_20260924T015735Z.dump`.
All 7 new migrations applied verbatim after a rolled-back dry-run with admin / pure-trainer /
candidate impersonation: `student_diagnostics` (onboarding diagnostic, owner/admin RLS),
trainers journey-track columns, `app_role` values (all already present), `role_master` catalog
(admin-read; drives the Roles & Access filter, which now lists all 9 roles), role→menu permission
backfill + trigger on `user_roles` insert (admin_tab_permissions 5→15, candidate_menu_permissions
3→71; existing rows never overwritten), **trainers RLS rebuilt** — before this, every signed-in user
had `ALL USING (true)` on `trainers` (could edit any trainer); now self/admin/onboarded-student only,
and `user_roles` self-read. `20260923000000_repair_missing_modules` was edited upstream (FKs now
point at `profiles`) but is **still invalid SQL** (`DO BEGIN … END` without `$$`) and its four
tables are used nowhere in Banking — still skipped.

**Admin login regression found and fixed (`b8008e6`, pushed to main).** After this release every
admin login bounced `/admin/dashboard → /login/candidate → /candidate/home` (8/8 fresh sessions).
Cause: `AuthContext` sets `user` on sign-in but `isLoading` was already false from the first load and
roles arrive later; `Login.tsx` read that window as "signed-in non-admin" and redirected. Upstream
`1d13084` (login forms follow the URL) made the race lose every time. Fix: expose `isLoading` until
roles are loaded **for the current user id** (not on every auth event — token refreshes would blank
admin pages). After fix: 8/8 admin logins reach the console; tsc error set identical to upstream (6).

Verification: 7/7 containers, site/auth 200, bundle has no hosted/DEV URLs, headless candidate +
trainer OTP and admin login all 0 page errors / 0 `/sb` ≥400, Roles & Access Trainer filter → 12.

## 2026-09-25 — redeployed to `1205677` (36 commits, 11 of 12 migrations, 13 functions)

Curriculum video studio, topic learning simulations (+ AI generation), guided curriculum setup
workflow, unified module/video quiz contract, module child menus. Snapshot
`~/banking-predeploy-20260925T054018Z/` + `~/banking-sb/banking_uat_predeploy_20260925T054018Z.dump`.
`package.json` gained a script only (`npm ci` run anyway). Our `AuthContext` admin-login fix
(`b8008e6`) is still in upstream.

Dry-run in one rolled-back transaction with a before/after diff of `modules`, `topics`,
`module_groups`, `menu_access_controls`: the 11 applied files change **no existing rows** —
+15 `modules` (admin-created modules not yet in the learner catalogue; published only if the admin
published them), +16 child menus (new keys only, existing access flags untouched).

**Skipped `20260925090000_restore_module_topic_catalog`.** Its header targets deployments that
*lost* the seeded catalogue; UAT's is intact (it fails on `admin_modules_source_module_unique`
because the seed rows already exist). It also `UPDATE`s every module/group whose title matches a
seed row: forces `is_published = true`, rewrites `sort_order`, and stamps `track = tech` — i.e. it
would re-publish modules an admin unpublished and relabel domain modules as tech. Not a safe replay
on a live catalogue.

Verification: 7/7 containers, 90 functions synced (3 fixup overlays) 0 runtime errors, bundle clean,
headless admin login 5/5 to `/admin/dashboard`, candidate + trainer OTP 0 errors, and Jev goal
runs (PC/Chromium) PASS for admin login.

## 2026-09-25 (later) — redeployed to `0538e22` (8 commits, 2 migrations)

Module save/pipe fixes, canonical module creation, legacy quiz writes. No function or dependency
changes. Snapshot `~/banking-predeploy-20260925T074938Z/` + `banking_uat_predeploy_20260925T074938Z.dump`.
Both migrations applied verbatim after a rolled-back dry-run.

**Behaviour change — module entitlement is no longer enforced by the database.**
`20260925073204` (Lovable edit `22d2b89` "Added modules read access") adds
`"Authenticated users can view published modules" USING (is_published OR admin modules tab)`
alongside the existing `"Users can view accessible modules"` (published AND granted via
`user_module_access` / module group). RLS OR-combines, so every signed-in user now reads **all**
published modules: the demo candidate went 9 → 75. Applied because it is an explicit, named team
change and module rows are catalogue content, not PII — but if per-user/plan module gating is meant
to hold, the gate now lives only in the frontend. `20260925073402` adds topic columns
(`learning_minutes`, `description`, `metadata`), admin update on `topic_attachments`, module-question
policies equivalent to the existing trainer/admin ones, and lets any signed-in user read the
`attachments` storage bucket (1 admin-uploaded file on UAT).

Verification: 7/7 containers, site/auth 200, bundle clean, admin login 5/5 to `/admin/dashboard`,
candidate + trainer OTP 0 page errors / 0 `/sb` ≥400.

## 2026-09-25 — "Persistence Disabled" on Admin → Coding Challenges (UAT env flags, fixed)

Symptom: Coding Challenges listed only the bundled catalogue (`bundled-tech-catalog`, 200 rows) and
saving showed "Persistence Disabled — apply the coding challenges migration". Not a migration gap:
`coding_challenges` exists on UAT with every column the page uses and 365 rows. The bundle gates DB
use on **build-time** flags (`src/lib/optionalDatabaseFeatures.ts`):
`VITE_OPTIONAL_DATABASE_SCHEMA_READY=true` (master gate, enables nothing alone) **and**
`VITE_CODING_CHALLENGE_PERSISTENCE_ENABLED=true` **and**
`VITE_CODING_CHALLENGE_SCHEMA_VERSION=20260811103000`. UAT `.env` had none. Added all three
(backup `.env.bak-*`), rebuilt, swapped. Verified: page loads 365 from DB (GET 200, 0 bundled), no
toast, admin insert+delete through PostgREST works.

**Still off on UAT — same mechanism, each needs its own flag (+ schema version) in `.env` and a rebuild:**
admin modules (`20260812021000`), admin section content, AI coach history (`20260813163337`),
AI practice settings (`20260812010000`) / sessions, LLM usage (`20260811234500`), practice plans
(`20260811235500`), proctoring analytics, projects (`20260811200000`), RAG documents, student
assessment scores (`20260811233000`), student learning (`20260812010000`), video lessons. The
required values are the literals in `optionalDatabaseFeatures.ts`; `.env.example` ships them all
`false`/empty. Enable per feature only after confirming its tables/columns exist.

Also noticed (not changed): `coding_challenges` carries a legacy `"coding_challenges authenticated
write" FOR ALL USING (true)` policy — any signed-in user can edit or delete any challenge.

## 2026-09-26 — redeployed to `1322956` (23 commits, 5 migrations, 29 functions)

AI model registry + generation audit, source grounding & review workflow, AI quality/entitlement
contract, video-MCQ cancellation, admin preview-resource reconciliation, bulk simulation studio.
Snapshot `~/banking-predeploy-20260926T050353Z/` (dist, env, functions, and the old local mcp
working-copy patch) + `banking_uat_predeploy_20260926T050353Z.dump`.

| Migration | UAT | Why |
|---|---|---|
| `20260925143000`, `…160000`, `…190000` | verbatim | additive |
| `20260925173000_ai_quality_and_entitlement_contract` | **fixup** | its `menu_access_controls` seed was `ON CONFLICT DO UPDATE` on 6 existing menus; UAT admins had them open to all plans (set 08-28 / 09-21). Verbatim, 51 free candidates lose Assessments / Video Quiz / Proctoring Analytics and 3 free trainers lose Content Studio / Create Assessment. Fixup = `DO NOTHING`; apply the tiering via Plan Menu Access if the team wants it |
| `20260925210000_reconcile_admin_preview_resources` | **fixup** | UAT's `admin_list_payment_requests()` returned extra `student_name/student_email` + integer `amount_inr`; `CREATE OR REPLACE` can't change a return type → `drop function if exists` first. Frontend (`PaymentVerification.tsx`) reads only `students{}` + `amount_inr` |

**New build-time gates** in `optionalDatabaseFeatures.ts`: `VITE_SIMULATION_PERSISTENCE_ENABLED`,
`VITE_PAYMENT_REQUESTS_PERSISTENCE_ENABLED`, `VITE_RBAC_REPORTS_PERSISTENCE_ENABLED`,
`VITE_TRAINER_CANDIDATES_RPC_ENABLED`. These screens read their tables unconditionally before this
release, so leaving them unset would have blanked working screens. All tables/RPCs verified on UAT
and the four set to `true` in UAT `.env`.

`mcp` function: upstream change is cosmetic (`var`→`const`); UAT still deploys the
`~/banking-sb/function-fixups/mcp` overlay (0.26.3 + self-hosted projectRef). The redundant local
working-copy patch was discarded before the pull (backed up in the snapshot) — no more stash conflicts.

Verification: dry-run clean (0 menu access changes); 90 functions synced, 0 runtime errors; bundle
clean; admin login 5/5, candidate + trainer 0 errors; Coding Challenges 365 from DB; as admin
`admin_list_payment_requests` 200 (0 rows — table empty) and `list_trainer_candidates` 200 (12).

## 2026-09-26 — "Module catalog migration required" on Save Module (UAT env flag, fixed)

Same class as the Coding Challenges fix: `src/pages/Admin.tsx` refuses to save/delete canonical
modules and topics unless `ADMIN_MODULES_PERSISTENCE_ENABLED`
(`VITE_OPTIONAL_DATABASE_SCHEMA_READY` + `VITE_ADMIN_MODULES_PERSISTENCE_ENABLED=true` +
`VITE_ADMIN_MODULES_SCHEMA_VERSION=20260812021000`). The migrations
(`20260812020000`/`20260812021000`) were already applied (reconcile: no missing objects; 68
`admin_modules`, 557 `admin_module_topics`); every column the insert/update payloads write exists.
Added the two flags to UAT `.env` (backup `.env.bak-*`), rebuilt, swapped. The flag also moves the
admin dashboard, domains, module analytics, assessments and institute dashboards off their fallback
data. Verified headless as admin: dashboard + Modules page 0 `/sb` ≥400; edit module → Save Module →
"Module saved" (`PATCH admin_modules 204`), no migration toast, 0 page errors.

Still-off gates on UAT: admin section content, AI coach history, AI practice settings/sessions, LLM
usage, practice plans, proctoring analytics, projects, RAG documents, student assessment scores,
student learning, video lessons.

## 2026-09-26 — "Generate Topics with AI" produced banking topics for non-banking modules (fixed, `d84b6d9`)

Report: Mechanical Engineering → Generate Topics with AI → "Digital Banking and FinTech". That topic
was created 2026-09-25 10:59, before the 09-26 deploy added the curriculum quality gate
(`_shared/curriculum-quality.ts` + an LLM checker in `ai-content`). With the gate live, the module
got the fixed fallback list every time — never real AI topics — because of two gate bugs:

1. **Substring stop-list.** `containsAnchor` used `text.includes(term)`; the banking stop-list for
   mechanical modules includes `rbi` and `aml`, which match inside tu**rbi**ne and strea**ml**ine.
   Two hits → "unrelated rbi, aml terminology" → rejected. Fix: stop-list terms match whole words
   (`containsWholeTerm`); coverage anchors keep prefix matching (thermodynamic → thermodynamics).
2. **Checker score scale.** The LLM checker tool schema declared `score: number` with no range;
   Gemini answers 0–1 (1 = perfect) while the code required `>= 80` → every approved review was
   rejected ("align directly … no domain drift", score 1). Fix: schema describes 0–100 and a 0–1
   answer is normalised ×100.

Verified via direct `ai-content` calls as admin (empty moduleId, nothing persisted): Mechanical
Engineering, Retail Banking and Data Science all return AI topics in their own discipline
(`checker: llm`, `fallbackApplied: false`). Pushed to Banking `main` as `d84b6d9`; functions synced.
The stale "Digital Banking and FinTech" topic on admin module `7dbd389b` (Mechanical Engineering)
was left in place — delete it from the module card.

## 2026-09-28 — upstream `main` FORCE-PUSHED; UAT moved to the new line (`fd03135` + fix `6bf8a7f`)

Between 09-26 07:47 and 09-28 06:16 UTC `main` was force-pushed to a line forked from `8a257b2`
(09-22) plus new commits, discarding **112 commits** (09-22→09-26: video studio, simulations,
curriculum setup workflow, AI registry/grounding/quality contract, RLS security remediation, and our
fixes `b8008e6` AuthContext race + `d84b6d9` topic quality gate). No remote branch holds them.
**Backups:** branch `backup/pre-force-push-20260928T061627Z` in `~/bankingjobreadiness` (UAT) and
`~/banking-main-pre-force-push-20260928T061627Z.bundle` on UAT + DEV (verified full history).

On explicit request, UAT was moved to the new line (checkout `reset --hard origin/main`, `.env` kept).
The DB was **not** rolled back: every migration from the discarded line stays applied (tables,
RLS lockdown, menus), the new code simply no longer references some of them. Snapshot
`~/banking-predeploy-20260928T074647Z/` + `banking_uat_predeploy_20260928T074647Z.dump`.

- New migrations `202609XX_llm_config.sql` / `202609XX_video_projects.sql` fail as written (policies
  `TO admin`/`TO trainer` name DB roles that don't exist; reference a `created_by` column never
  defined). Applied as fixup `~/banking-sb/fixups/202609XX_llm_config_and_video_projects.sql`: adds
  `created_by DEFAULT auth.uid()`, admin-all / trainer-own policies via `private.has_role`,
  "ready videos" readable by signed-in users (not anon). `llm_config.api_key` is stored in plaintext.
- Functions: `ai-audit-curriculum`, `evaluate-learning-simulation`, `generate-learning-simulation`
  gone; `compose-video`, `generate-simulation`, `generate-video` added.
- **Topic generation regression fixed (`6bf8a7f`, pushed to main):** `ai-content` declared
  `isTechTrack` only inside `topic_content`, so `module_topics` threw `isTechTrack is not defined`
  on every call → generic fallback topics; and every non-tech module got the "Indian banking
  educator" persona. Persona now per module: tech → tech, banking/finance keywords → banking, else
  discipline-neutral. Mechanical Engineering → 5 AI mechanical topics with 0 banking terms.
- VITE flags in `.env` still apply (new `optionalDatabaseFeatures.ts` reads the same names minus
  the 4 gates added on the discarded line, whose screens now read unconditionally).

Verification: build clean in an isolated worktree first; admin login 5/5, candidate
(`/onboarding/diagnostic`) + trainer 0 errors; Coding Challenges 365 from DB; Save Module "Module
saved"; 90 functions, 0 runtime errors; bundle clean.

## 2026-09-29 — redeployed to `4556bda` (28 commits, 7 migrations: 5 applied, 2 skipped)

Fast-forward from `6bf8a7f`, no force-push this time. No dependency or `.env` changes. Changed edge
functions: analyze-proctoring, chat, compose-video, generate-simulation, generate-video (the `mcp`
function-fixup overlay still applies).

| Migration | UAT action |
|---|---|
| `20260923000000_repair_missing_modules` | **Skipped**: invalid `DO BEGIN…END` syntax; references PilVidya's `student_profiles` |
| `20260928120000_daily_mission_institute_backfill` | Applied as shipped (fills null `profiles.institute_id` by institute name; matched 0 rows on UAT) |
| `20260928130000_video_projects` | **Fixup**: the table already existed on UAT, so `CREATE TABLE IF NOT EXISTS` would have skipped the new `provider_key` column. The fixup adds it, then runs the file |
| `20260928140000_candidate_diagnostic_results` | **Fixup**: upstream allowed any signed-in user to read and insert anyone's diagnostic results. On UAT: read = own row (`candidate_id = auth.uid()`) or admin/trainer; insert = own only. `candidate_id` is the auth uid (DiagnosticAssessmentDialog/StudentOverview) |
| `20260928150000_fix_profiles_rls_recursion` | **Skipped**: UAT has no recursion. The file adds `USING (true)` reads on `profiles` + `user_roles` (every candidate would see every email/mobile; `Leaderboard.tsx` does `profiles.select("*")`) and drops `profiles_owner_or_scoped_trainer_read`. Needs a team decision (e.g. a names-only leaderboard view) |
| `20260928150000_student_diagnostics` | Applied as shipped (the table already exists; the file only adds owner policies and an index) |
| `20260928160000_add_my_learning_menu_access` | Applied as shipped (`my-learning` menu, DO NOTHING insert) |

Fixups live in `~/banking-sb/fixups/`. Snapshot: `~/banking-sb/snapshots/20260929T0552*Z` (dist, functions, DB dump).
**Build gotcha:** a non-interactive ssh shell resolves `/usr/local/bin/node` = **v16**, and Vite fails with
`TransformStream is not defined`. Build with `PATH=~/.nvm/versions/node/v20.20.2/bin:$PATH`, into a temp outDir, then swap.
Verified: admin login 5/5, candidate/trainer/admin e2e, Coding Challenges (370, no persistence toast), Save Module.

## 2026-09-29 — Admin → Plan Menu Access → Student Tier Management: search blanked the page (fixed, `3d3d072`)

`StudentTierManager.tsx` filtered with `s.name/email/college.toLowerCase()`, but those `students` columns are
nullable (UAT: 10/63 no name, 39 no email, 15 no college: imported or unlinked students). The first keystroke
threw a TypeError and React unmounted the page. The match is now null-safe, and empty cells render "—". Deployed to UAT
(bundle `index-C-ORsuHc.js`) and verified headlessly: searches `s`/`prabha`/`IIT`/`zzzz` give 0 page errors.
The blank rows are real data gaps, not an RLS problem.

## 2026-09-29 (pm) — redeployed to `4aaaa32` + auth fix `d4cdc6b` (2 migrations, 4 bootstrap functions)

Upstream: separate `/login/candidate|trainer|admin` pages (`lockedTab`), AI-upskilling sections on Home,
`project_assignments` migration, trainer/student `institute_id` link, and the admin bootstrap functions now
require an `x-bootstrap-token` header (`BOOTSTRAP_ADMIN_TOKEN`) and `BOOTSTRAP_ADMIN_PASSWORD` from env.

| Migration | UAT action |
|---|---|
| `20260928160000_project_assignments` | **Fixup** (`~/banking-sb/fixups/`). The table already existed with all app columns. Upstream's four `USING (true)` policies would let any candidate read, edit or delete every assignment. UAT: **read** = the student (auth uid *or* own `students.id`), the assigning trainer (`trainers.id` = `assigner_id` or `trainer_id`), admin; **write** = the assigning trainer or admin only. Dry-run verified: trainer insert ok, trainer spoofing another assigner blocked, candidate sees 0 and cannot write or delete |
| `20260928170000_trainer_student_institute_link` | Applied as shipped. The backfill matched **0/68 students, 0/15 trainers**: free-text `college` never equals an `institutes.name` on UAT. The column stays null until mapped |

- **Bootstrap functions:** `BOOTSTRAP_ADMIN_TOKEN` is deliberately **not** set on UAT, so all four functions reject requests (fail closed). The frontend never calls them.
- **Known app gap:** trainers write `project_assignments.student_id = students.id`, but the candidate view reads `.eq("student_id", <auth uid>)`. On UAT those never match (0/63 students have `id = user_id`), so a candidate won't see trainer-assigned projects until upstream fixes the ID form. RLS already allows both forms.
- **Admin login regression, fixed in `d4cdc6b`:** the role-loading race from 09-21 (`b8008e6`, lost in the force-push) resurfaced. `AdminRoute` redirected before `user_roles` loaded, and the new candidate-locked page sent admins to `/candidate/home` (1 of 5 logins succeeded). `AuthContext` now reports `isLoading` until the roles belong to the current user. Result: 5/5.

Verified: admin 5/5, candidate/trainer/admin e2e, Coding Challenges 370, Save Module, Student Tier search (0 page errors).
Snapshot `~/banking-sb/snapshots/20260929T102719Z`.

## 2026-09-30 — redeployed to `9be7373` (14 commits, 8 migrations: 4 as shipped, 4 with UAT fixups)

Upstream sprints 1–3: admin Institutes master and trainer↔institute mapping, trainer plan mapping,
institute-UUID scoping for assessments, module groups and learning paths (text columns kept one more release),
R2 mapping-gated content, R9 candidate/student identity unification, R5 multi-institute curricula, any-format
curriculum uploads, AI quizzes (10 questions), AI 3D video per topic (Veo→Runway fallback). No new function secrets;
the vite CSP header is dev-server only.

| Migration | UAT action |
|---|---|
| `…180000_institute_data_reconciliation` | **Fixup**: step 1 syncs `institutes.institute_name`, which UAT never had. Dropped; the rest applied. Matched 0 rows (report: unmapped profiles 80, trainers 15, students 68) |
| `…180000_r9_unify_candidate_student_identity` | **Fixup**: (1a) a mobile match also requires non-conflicting emails. Upstream bound student `prabha+priya12@` to **jershini.y@**'s account via the placeholder mobile `1234567890`. (3) The `student` role is not added to admin/trainer accounts (upstream added it to 4). Result: 1 student linked (yash.manjrekar, same mobile and email) |
| `…181000_r2_mapping_gated_content_visibility` | As shipped. It **drops every SELECT policy** on modules/topics/assessments/assessment_questions, including the existing `USING (true)` ones, so this narrows access. Measured before→after: mapped candidate 82→**6** modules, 659→75 topics, 30→24 assessments; **unmapped candidate 82→0 modules**; trainer 82 modules (topics 659→644, unpublished hidden); admin unchanged (85). Candidates now see only modules granted via `user_module_access`/module groups. UAT has 18 `candidate` + 13 `student` role users with no mapping |
| `…190000_assessments_institute_ids` | As shipped |
| `…190000_r5_curriculum_institute_map` | **Fixup**: manage is **admin-only**. Upstream let any trainer rewrite any curriculum's institute map; only the admin path in `TrainerCurriculumBuilder` writes it. Read stays authenticated-wide (id pairs only) |
| `…192000_module_group_assignments_institute_id` | As shipped (the `save_module_group_mapping` body is identical to UAT's apart from the new `institute_id`) |
| `…193000_learning_path_assignments_institute_id` | As shipped |
| `…194000_trainer_students_trainer_read` | **Fixup**: upstream's predicate had no row link (`exists trainer where user_id = auth.uid()`), so every trainer could read all assignments. Added `t.id = trainer_students.trainer_id` |

**Pre-existing, not changed by this deploy:** `trainer_students` still carries `authenticated read USING (true)` and
`authenticated write FOR ALL USING (true)`. Any signed-in user can rewrite trainer↔student links. Needs a team decision.

Verified: admin 5/5 (`d4cdc6b` role-race fix still upstream), candidate/trainer/admin e2e, Coding Challenges 370,
Save Module, Student Tier search, and all 25 admin sidebar pages with 0 page errors and 0 API ≥400.
Snapshot `~/banking-sb/snapshots/20260930T054733Z`.

## 2026-10-02 — redeployed to `0b24031` (108 commits, 17 migrations: 9 as shipped, 8 with UAT fixups)

Upstream: Live Sessions (trainer-scheduled + candidate-requested, RSVPs, attendance), module prerequisites,
AI Coach usage quotas + cost log, video pipeline/topic videos, job roles → role-mapped modules (`students.target_role_id`),
curriculum resources/quizzes/topic progress mapped to students, trainer→student institute cascade, restructured
admin sidebar (Module Analytics tab), trainer module creation. New UAT build flags adopted from upstream `.env`:
`VITE_PROJECT_PERSISTENCE_ENABLED`, `VITE_SIMULATOR_ENGINE_ENABLED`, `VITE_TOPIC_GENERATION_ENABLED`, `VITE_VIDEO_PIPELINE_ENABLED`
(UAT `.env` kept; upstream's tracked `.env` points at the hosted project, so never take it wholesale).

| Migration | UAT action |
|---|---|
| `20260930120000_live_sessions_and_prerequisites` | **Fixup**: UAT's tables predate upstream with **uuid** `trainer_id`/`student_id` plus 6 legacy policies. Legacy policies dropped, both columns converted to text, then upstream applied |
| `20260930120000_trainer_institute_cascade` | As shipped (0 rows realigned) |
| `20260930130000_ai_coach_usage_controls` | **Fixup**: `check_ai_coach_rate_limit` was SECURITY DEFINER with no search_path, executable by everyone for **any** `p_student_id`, and trusted caller-supplied limits. UAT: search_path pinned; callers may meter only themselves (auth uid or own `students.id`; service role exempt); limits come from `ai_coach_user_limits` or the 50/10 defaults; the previous request time is read *before* stamping. `log_ai_coach_cost` is service-role only |
| `20260930150000_video_projects_scope` | As shipped. **Contains its own `begin;…commit;`** (see incident) |
| `20260930190845` (video_lessons columns), `20261001130000` (admin tab), `20261002031030` (topic_videos write), `20261002033047` (job roles), `20261002034643`, `20261002040325`, `20261002040352`, `20261002040603` (curriculum) | As shipped |
| `20261002021655` (modules write) | **Fixup**: upstream let any trainer/teacher UPDATE **every** module, including admin catalogue modules. UAT: trainers/teachers update only modules with `metadata.created_by_trainer` = their `trainers.id`; admin + taxonomy_editor update all. Insert/delete as upstream |
| `20261002022504` (staff read all modules) | **Fixup**: made re-runnable (`DROP POLICY IF EXISTS`) |
| `20261002023429` (solved challenges + curriculum_videos) | **Fixup**: `student_solved_challenges` already existed (no `user_id`). Upstream let anyone insert/edit `user_id IS NULL` rows under any `student_name`. UAT: `user_id DEFAULT auth.uid()`, writes own rows only (admin all), the existing unique index serves the upsert |
| `20261002030950` (topic_videos FKs) | **Fixup**: `topic_videos` is in **no** migration (hosted-only), so it never existed on UAT and the video panels 404'd. Created it from `types.ts`, plus read policy and realtime publication |
| `20261002034610` (live sessions v2) | **Fixup** prefix: the same legacy-policy drops (idempotent) |

**Incident: part of this release was applied to the live DB during the "dry run".** `video_projects_scope.sql` carries its own
`begin;`/`commit;`. Inside the rolled-back rehearsal transaction that inner `COMMIT` committed everything before it, and
later statements ran in autocommit. So `…120000` (live sessions fixup) through `…022504` and the first statement of the `…023429` fixup
landed for real ~20 min before the code deploy. All were the reviewed UAT versions and idempotent, and the old frontend kept working.
**Rule since:** the rehearsal strips transaction-control lines from each file
(`sed -E '/^[[:space:]]*(begin|commit|rollback)[[:space:]]*;[[:space:]]*$/Id'`) and confirms a not-yet-created object is still absent afterwards.

Rehearsal probes (all as expected): candidate meters only self (2nd call rate_limited, other id → 42501); solve rows owned by the
recorder, spoof blocked; trainer edits own module only, cannot create sessions as another trainer; admin edits any module.
**Open, by upstream design:** `module_live_sessions` reads are open to every signed-in user (meeting URL/password included), and
`list_session_trainers()` returns all approved trainers' names and emails to candidates when a module has no assigned trainer.
**Pre-existing, unchanged:** `curriculum_videos` and `video_lessons` carry `authenticated write FOR ALL USING (true)`.

Verified: admin 5/5, candidate/trainer/admin e2e (×4; 1 candidate miss right after the REST/edge restart), Coding Challenges 370,
Save Module (now at `/admin?tab=modules`), Student Tier search, all 12 admin sidebar sections with 0 errors.
Checks now live in `~/banking-checks/` (README inside) because `/tmp` is cleaned. Snapshot `~/banking-sb/snapshots/20261002T042723Z`.

## 2026-10-02 (pm) — redeployed to `fb23bac` (50 commits, 8 migrations: 6 as shipped, 2 UAT fixups) — incl. a 500s incident

Upstream: Simulation Studio v2 (`sim_packs`/versions/assignments/attempts/events/score reviews/skill profile, owner- and
staff-scoped RLS), module resource uploads (curriculum files → `extract-resource`), Student Groups screen, cascading module
groups, trainer approve/upload fixes. `private.user_can_access_module` gains the module-group cohort path (college/department/degree/
institute, archived groups excluded). No dependency or `.env` changes.

| Migration | UAT action |
|---|---|
| `20261002090828` / `090856` / `094821` (simulation tables + RLS) | As shipped. Rehearsal: trainer creates pack + version; candidate sees 0 packs and cannot create one |
| `20261002092705` (module_resources FKs/check + storage policies) | **Fixup**: `module_resources` / `module_resource_chunks` are hosted-only (in no migration). Created from `types.ts` (module_id text), plus a **private** `module-resources` storage bucket |
| `20261002094303` (staff write module_resources), `095038` (`get_user_display_names`, staff-only), `103626` (module access) | As shipped |
| `20261002103229` (students/institutes policies) | **Fixup after incident**: as shipped it caused infinite RLS recursion (see below). `"Trainers view their students"` now calls SECURITY DEFINER `private.is_my_trainer_row(onboarded_by)` |

**Incident (≈10 min, UAT only):** the new `students` policy `"Trainers view their students"` subqueries `trainers`, whose RLS
subqueries `students`. Result: `infinite recursion detected in policy` → **HTTP 500 for every role** on `students`, `profiles`,
`modules` (Save Module), `institute_subscriptions`, Users & Roles / Grading / Reports / Billing pages; the trainer login bounced
to `/login/trainer`. The rehearsal missed it because no probe read those tables. Fixed live by moving the check into a SECURITY DEFINER
helper. **Rehearsals now read profiles/students/trainers/modules/institutes as every role** (`~/banking-checks/dryrun_template.sh`).

**Open, needs a team decision (pre-existing, unchanged):** `students` still carries `students authenticated read USING (true)` and
`students authenticated write FOR ALL USING (true)`. Measured after this deploy, a **candidate reads all 74 student rows** (names/emails/
mobiles) and could edit any of them. Upstream's new scoped policies (admin manage / own row / trainer's own students) are all in place,
so dropping the two open policies would be the fix. Check trainer onboarding + bulk import first (they may rely on the open write).

Verified after the fix: admin 5/5, candidate/trainer/admin e2e ×2, Coding Challenges 370, Save Module, Student Tier search, all 12 admin
sections with 0 errors; bucket `module-resources` private. Deploy script is now `~/banking-sb/deploy.sh` (source in `~/banking-checks/deploy.sh`).
Snapshot `~/banking-sb/snapshots/20261002T110924Z`.

## 2026-10-02 (eve) — redeployed to `633efc5` (21 commits, no migrations) + function overlay for video quizzes

Upstream: trainer dashboard, Live Sessions page, restored and de-duplicated menu items, YouTube video quizzes raised to 10 questions.
No migrations, dependency or `.env` changes.

**New UAT function overlay `~/banking-sb/function-fixups/generate-lesson-video-quiz/index.ts`.** Upstream changed this function to
call `ai.gateway.lovable.dev` **directly** with `LOVABLE_API_KEY`, to stop the shared helper's deterministic stub from producing
generic title-only MCQs. UAT has no Lovable key (all LLM traffic goes through LiteLLM via `llm_config`), so on UAT every video quiz
would have failed with a 401. The overlay calls the shared `chatCompletionWithFallback` (configured providers) and keeps upstream's
intent: if every provider fails (`X-LLM-Fallback` header), it returns 502 instead of stub questions. It is a **whole-file** overlay of
upstream as of `633efc5`, so re-derive it if upstream edits this function. Verified live as admin: KYC transcript → 10 topic-specific
questions in ~11 s (test `video_lessons` row deleted afterwards). `sync-functions.sh` now applies 4 overlays (live-session-rsvp, main, mcp,
generate-lesson-video-quiz).

Verified: admin 5/5, candidate/trainer/admin e2e ×2, Coding Challenges 370, Save Module, Student Tier search, all 12 admin sections
with 0 errors. Snapshot `~/banking-sb/snapshots/20261002T120602Z`. Still open: `students` authenticated read/write `USING (true)` (see above).

## 2026-10-03 — redeployed to `9f8a535` (66 commits, 6 migrations: 5 as shipped, 1 UAT fixup)

Upstream: institute onboarding (location master `institute_locations`, programs `institute_programs`, onboarding status/step),
a strict **domain → module group → module** hierarchy (`modules.module_group_id` + sync triggers between modules, module groups and group items),
topic completion tracking (students insert their own `student_module_topic_progress`), trainer module builder (trainers manage topics
of modules they own via SECURITY DEFINER `trainer_owns_module`), unified assignments dashboard, reorganised student nav. No function,
dependency or `.env` changes; all 4 function overlays still apply.

| Migration | UAT action |
|---|---|
| `20261003033829` (institute locations + onboarding) | **Fixup**: UAT `institutes` lacked hosted columns `location`, `pin_code`, `address`, `contact_person`, `email`, `website`, `institute_name`. Without `location`/`pin_code` the backfill fails and the new `sync_institute_location` trigger breaks institute saves; the new institute screens select the others. All added as nullable text (from `types.ts`) before upstream runs |
| `20261003034954` (programs + assessment_institute_mapping policies), `040341` (module hierarchy), `053524`, `053828`, `053854` | As shipped |

Rehearsal (inner BEGIN/COMMIT stripped, core tables read as every role): admin creates a location, then an institute bound to it (PIN code
synced by the trigger), then a program. A trainer adds a topic to their own module, is blocked on admin modules and blocked from editing
locations. A candidate is blocked from writing programs. No RLS recursion. Rollback confirmed. UAT has **0 institutes**, so the location
backfill had nothing to move.

Verified: admin 5/5, candidate/trainer/admin e2e ×2, Coding Challenges 370, Save Module, Student Tier search, all 12 admin sections
(new "Access Control") with 0 errors. Snapshot `~/banking-sb/snapshots/20261003T054517Z`.
Still open: `students` authenticated read/write `USING (true)` (team decision pending).

## 2026-10-03 (later) — redeployed to `4d8dd6a` (4 commits, no migrations)

Frontend + one function, no schema/dependency/`.env` changes; the 4 function overlays are unaffected.
- Module AI Coach: replies in the student's selected language (native script; banking terms kept in English) when not `en-IN`.
- `ttsClient` server-TTS timeout 5 s → 30 s (slow voices no longer drop to the browser fallback mid-request).
- `ai-video-suggest`: relaxed second YouTube search (topic / topic+module / module, no duration or language filter) when the
  first pass finds nothing. UAT has an enabled YouTube key in `llm_provider_configs` (provider `youtube`), not in the function secrets.

Verified: admin 5/5, candidate/trainer/admin e2e ×2, Coding Challenges 370, Save Module, Student Tier search, all 12 admin
sections with 0 errors. Snapshot `~/banking-sb/snapshots/20261003T062528Z`. Still open: `students` read/write `USING (true)`.

## 2026-10-04 — redeployed to `bb0ac4d` (11 commits, 1 migration with UAT fixup)

Upstream: cohorts (`cohorts` table, `profiles.cohort_id` + `last_active`), institute student manager cohort column, completion
funnel fix, "Fixed OpenAI test error" in `admin-llm-providers` / `manage-llm-providers`, blank-screen crash handling.
**Not run:** `scripts/release/demo-institute-seed-part1-identities.sql` / `part2-transactions.sql` (manual demo-data seeds outside
`supabase/migrations`; would create demo identities and transactions — run only if the team asks for demo data on UAT).

| Migration | UAT action |
|---|---|
| `20261004034123` (cohorts) | **Fixup**: upstream let any trainer/teacher/institute user insert/update/**delete every institute's** cohorts. UAT: admins manage all; other staff manage global cohorts (no institute) or cohorts of their own institute, resolved by SECURITY DEFINER `private.my_institute_ids()` (no RLS re-entry). Read stays open (names only) |

Rehearsal: admin creates a cohort in institute A; trainer creates a global cohort, deletes 0 of A's and is blocked creating one in A;
candidate blocked; core tables read cleanly as every role (no recursion); rollback confirmed.
Verified: admin 5/5, e2e ×2, Coding Challenges 370, Save Module, Student Tier search, all 12 admin sections with 0 errors.
Snapshot `~/banking-sb/snapshots/20261004T064712Z`. Still open: `students` read/write `USING (true)`.

## 2026-10-04 — fixed: "AI Generated Videos" (Bucket not found) and "AI Simulations" (AI is not configured)

Both were UAT-environment gaps, not app bugs; fixed with UAT overlays/fixups that `deploy.sh` re-applies on every deploy.

1. **AI Generated Videos → `google_veo: Bucket not found | elevenlabs: Bucket not found`.** `generate-video` uploads every render to
   storage bucket **`videos`** and signs a 1-year URL. That bucket was created by hand on hosted and is in no migration. Fixup
   `~/banking-sb/fixups/20261004T000000_uat_videos_bucket.sql` creates it **private**.
   **Second bug found while verifying:** inside the stack `SUPABASE_URL=http://gateway:80`, so every storage signed URL came back as
   `http://gateway/storage/...`, which browsers can't load. The same bug affected **`trainer-export-download`** (trainer export downloads).
   Fix: `SUPABASE_PUBLIC_URL=https://banking.uat.pluginlive.com/sb` in `functions-secrets.env` (backup `.bak-20261004T-publicurl`), plus
   whole-file overlays `function-fixups/generate-video` and `function-fixups/trainer-export-download` that rewrite only the returned
   URL's origin. 1 already-stored `video_projects.video_url` repaired. Verified: two topics of "Secured Loans & Unsecured loan – Senior
   Sales Manager – Unity Bank" rendered by Veo (~70 s each); public links return `206 video/mp4`. Those two videos are kept as content.
2. **AI Simulations → "AI is not configured" (500 from `sim-generate-pack`).** `_shared/sim-ai.ts` calls `ai.gateway.lovable.dev`
   (Responses API) with `LOVABLE_API_KEY`, which UAT lacks. Overlay `function-fixups/_shared/sim-ai.ts` replaces only `aiJson`: same
   prompt + JSON schema, routed through `_shared/llm.ts` `callLlmChatCompletion` (feature `simulation`, configured providers,
   `response_format: json_object`). It throws instead of accepting the deterministic stub. **This also fixes `sim-attempt`** (candidates playing a
   simulation), which uses the same helper. Verified: API ~22 s, full spec (3 stages, persona); real UI click on "Generate draft"
   creates a draft with 0 function errors (both test packs deleted).

Overlays now applied by `sync-functions.sh` (7): `_shared` (sim-ai.ts only), generate-lesson-video-quiz, generate-video, live-session-rsvp,
main, mcp, trainer-export-download. **Each whole-file overlay pins upstream `bb0ac4d`**, so re-derive it if upstream edits that function (check
`git diff --stat` on those paths at every deploy). Upstream-side improvement worth proposing: fall back to `_shared/llm.ts` when
`LOVABLE_API_KEY` is unset, and sign storage URLs against a public base URL. Both would retire these UAT overlays.

## 2026-10-04 — the AI-video / AI-simulation / video-quiz fixes are now in Banking `main` (`dc1e418`); 4 UAT overlays retired

Environment-safe versions pushed upstream (hosted behaviour unchanged):
- `_shared/sim-ai.ts`: with no `LOVABLE_API_KEY`, `aiJson` goes through `_shared/llm.ts` configured providers (JSON-schema prompt,
  `response_format: json_object`, AIError on stub/failure). Covers `sim-generate-pack` and `sim-attempt`.
- `generate-lesson-video-quiz`: same fallback, stub still suppressed.
- `generate-video`, `trainer-export-download`: `toPublicUrl()` rewrites the signed-URL origin to `SUPABASE_PUBLIC_URL` when set.
- Migration `20261004100000_videos_storage_bucket.sql` (idempotent private `videos` bucket). UAT already had it from the 10-04 fixup.

Overlays moved to `~/banking-sb/function-fixups-retired-20261004/` (`_shared`, generate-video, trainer-export-download,
generate-lesson-video-quiz). **Remaining overlays: live-session-rsvp, main, mcp.** UAT still needs `SUPABASE_PUBLIC_URL` in
`functions-secrets.env` (kept). Verified with the overlays removed: simulation draft (3 stages), 10-question video quiz, Veo video for
"Introduction to Home Loans and Regulatory Landscape" playable from its public link (206 video/mp4); test packs and lessons deleted;
admin 5/5 + 3-role e2e.

## 2026-10-05 — redeployed to `80fe876` (31 commits, 4 migrations as shipped)

Upstream: videos split into YouTube / AI tabs, Save/Exit on the video panel, multi-select UI, simulation publish-list and student
journey link fixes, plan-gated student module sections, simulation assignment picker, students' saved videos. No function changes;
my upstreamed fixes (`dc1e418`) and the admin-login guard are intact; overlays still 3.

| Migration | UAT action |
|---|---|
| `20261005012629` (student module-section menus) | As shipped: upserts 5 `module_*` menus on `(audience, menu_key)`; on conflict only label/sort/metadata change, never the per-plan access flags |
| `20261005013843` (path regeneration settings) | As shipped (table already existed; new policy names don't collide) |
| `20261005025935` (`list_sim_assignable_students`) | As shipped: admins get all students + self-registered candidates; trainers get only students they onboarded; others get 0 |
| `20261005030244` (`student_saved_videos`) | As shipped: own rows only |

Rehearsal: admin 81 assignable students, trainer 7, candidate 0; saved-video spoof blocked; core reads clean as every role.
Verified: admin 5/5, e2e ×2, Coding Challenges 370, Save Module, Student Tier search, 12 admin sections with 0 errors.
Snapshot `~/banking-sb/snapshots/20261005T034357Z`. Still open: `students` read/write `USING (true)`.

## 2026-10-05 (later) — redeployed to `93994b4` (16 commits, 2 migrations as shipped)

Upstream: Live Sessions calendar and invites (trainers invite their own/institute students; students see their mapped trainers),
**simulation "unlocked mode"**: any signed-in student can practise every *published* simulation pack (open entries next to assigned
ones, 99 attempts), and the quiz-score lock is removed (access is now plan/RBAC-menu based). Sim notes allow 20k chars (trimmed).

| Migration | UAT action |
|---|---|
| `20261005053623` | As shipped: SECURITY DEFINER `list_live_session_invitees()` (admin all; trainer onboarded/junction/institute; institute role own institute) and `list_my_mapped_trainers()`. Live-session insert adds the `institute` role. RSVP insert by a trainer now requires the student to be one of their invitees (**narrower** than before) |
| `20261005053649` | As shipped (revokes anon on both functions) |

Rehearsal: admin 67 invitees, trainer 0, candidate 0; trainer RSVP for a non-invitee blocked; the policy→function call causes no recursion.
Verified: admin 5/5, e2e ×2, Coding Challenges 370, Save Module, Student Tier search, 12 admin sections 0 errors, and `sim-generate-pack`
still generates through the configured-providers fallback (test pack deleted). Snapshot `~/banking-sb/snapshots/20261005T061511Z`.

## 2026-10-05 (eve) — redeployed to `ab1e75c` (15 commits, 1 migration as shipped)

Upstream: new admin **Masters** menu section, independent role buttons, simulations mapped to modules, Vite `resolve.dedupe` for
react/react-dom/jsx-runtime/react-query (fixes duplicate React copies). `sim-attempt`: open "unlocked" packs are now shown only for modules the
student can access (`user_can_access_module`), and starting an unassigned pack's module is refused with a 403. This tightens the 10-05 unlocked mode.

| Migration | UAT action |
|---|---|
| `20261005084733` (`sync_institute_name` trigger) | As shipped. Relies on `institutes.institute_name`, which UAT has since the 10-03 fixup. Rehearsal: name-only and legacy-name-only inserts both fill both columns (trimmed); rollback confirmed |

Verified: admin 5/5, e2e ×2, Coding Challenges 370, Save Module, Student Tier search, 13 admin sections (new "Masters") with 0 errors.
Snapshot `~/banking-sb/snapshots/20261005T085409Z`. Still open: `students` read/write `USING (true)`.

## 2026-10-05 (night) — redeployed to `36fb076` (upstream `6f41efd` + 1 fix pushed to main), no migrations

Upstream: trainer/student login wiring, and non-UUID `created_by` / user ids filtered out of the module "Created by" filter and the simulation
dashboard. **`candidate-otp-login` change:** trainer/institute-onboarded students (`students.onboarded_by` or `institute_id` set, row
active) may log in even if their *profile* looks inactive, and on login the profile is re-approved, re-activated and given the trainer's or
institute's plan (`subscription_tier`, else `institutes.default_plan_code`).

**Fix pushed (`36fb076`):** that override also defeated **Admin → RBAC "Revoke ALL access"**, which writes only
`profiles.is_active=false`. A revoked onboarded student could log in again and be silently re-activated. An explicit
`profiles.is_active=false` now always blocks; only a stale `approval_status` is overridden. (`admin-user-actions` set_status writes both
profiles and students, so it was never affected.) Verified live on `7738060032`: normal OTP login issues a session; with
`is_active=false` the login is refused ("inactive or rejected") and the profile stays revoked; profile restored after the test.

Verified: admin 5/5, e2e ×2, Coding Challenges 370, Save Module, Student Tier search, 13 admin sections 0 errors.
Snapshot `~/banking-sb/snapshots/20261005T111510Z`. Still open: `students` read/write `USING (true)`.

## 2026-10-06 — redeployed to `b60f146` (7 commits, 4 migrations as shipped)

Upstream: persisted candidate video discoveries (`save_student_module_videos`, valid YouTube ids only, deduped, max 100/request),
module-assignment reconciliation and counts, candidate narration (Gemini TTS Indian-English read-aloud prompt; `skipElevenLabs`
option), console navigation fixes, display-name lookups, coding history queries. **Upstream adopted my 10-05 login fix**: new
`_shared/login-account-status.ts` (`loginAccountStatus`) keeps `profiles.is_active=false` as a hard block. My other upstream fixes
(sim-ai fallback, `toPublicUrl`, video-quiz fallback) and the admin-login guard are intact; overlays still 3.

| Migration | UAT action |
|---|---|
| `20261005120000` (display names) | As shipped (staff-only gate kept) |
| `20261006100000` (module hierarchy repair) | As shipped (file has its own BEGIN/COMMIT, stripped in rehearsal). New SECURITY INVOKER RPCs `replace_module_group_members` / `move_module_group_member` (all writes still go through the caller's RLS). **`private.user_can_access_module` tightened:** self-granted `user_module_access` rows (`granted_by = user_id`, 72 on UAT) no longer grant access, and only published/active groups count. Measured: candidate×module visible pairs **1,036 → 932** |
| `20261006101000` (quiz bank module identity) | As shipped (`quiz_question_bank.source_module_id`) |
| `20261006120000` (student video retention) | As shipped |

Verified: admin 5/5, e2e ×2, Coding Challenges 370, Save Module, Student Tier search, **all 37 admin pages** (expanded sidebar) with 0 errors.
Note: the 2 `admin_error_logs` "Network error: Failed to fetch" rows per Save Module check are aborted requests from the test's own navigation (seen before the deploy too).
Snapshot `~/banking-sb/snapshots/20261006T151721Z`. Still open: `students` read/write `USING (true)`.

## 2026-10-07 — redeployed to `09c83c1` (upstream `41374ac` + 1 follow-up migration pushed to main), 3 migrations

Upstream "Fixed module mapping access": SECURITY DEFINER `staff_can_manage_student` (moved to `private`), staff writes on
`module_group_assignments` and `user_module_access` (trainers/teachers/institute users for students they manage; `granted_by = self`,
never for themselves), `module_visible_to` shows explicitly assigned modules even if unpublished, and curriculum matching via the profile's
institute.

| Migration | UAT action |
|---|---|
| `20261007082238` | **Fixup** (`~/banking-sb/fixups/`): (1) **dropped UAT's open `module_group_assignments authenticated write` (FOR ALL USING/WITH CHECK `true`)**, a pre-existing UAT-only hole that let any candidate assign module groups to themselves; hosted never had it. (2) Non-admin staff cohort-wide rows (`student_id` NULL) are limited to their own institute (`private.my_institute_ids()`) or own college (new `private.my_trainer_colleges()`); scope-less rows (grant nobody) stay allowed. Upstream let any trainer target any college, department, degree or institute |
| `20261007082311` | As shipped (function moved to `private`; policies keep working by OID) |
| **`20261007090000_assessment_access_keep_published_and_student_visible`** (new, pushed to main as `09c83c1`) | Upstream's rewrite of `private.user_can_access_assessment` dropped the `is_published` gate (drafts visible to students with matching modules) and the `metadata.student_visible` path (24/32 seeded banking assessments vanished for every candidate: visible pairs **1,737 → 517**). Restored both, keeping the new `user_can_access_module`-based check and overrides. Live after deploy: **1,734** pairs (−3 from the 10-06 self-grant rule) |

Rehearsal probes: candidate cannot self-assign a module group or self-grant module access; trainer can add own-college and scope-less
cohorts, and is blocked for another college or a department across all colleges; core reads clean as every role. Pre-migration DB dump
`~/banking-sb/snapshots/20261007T083247Z-premig`; deploy snapshot `20261007T083249Z`.
Verified: admin 5/5, e2e ×2, Coding Challenges 370, Save Module, Student Tier search, all 44 admin pages 0 errors.
Still open: `students` read/write `USING (true)`.

## 2026-10-07 (pm) — redeployed to `5978c42` (4 commits: release scripts + e2e tests only)

No migrations, function, dependency or `.env` changes; the frontend bundle is unchanged (`index-D3b-SqAu.js`). Added:
- `scripts/release/` paste-ready SQL for the **hosted** project. `5978c42` records that hosted still had the broken
  `private.user_can_access_assessment` from `20261007082238` (3 draft assessments candidate-visible) and was repaired with the body of my
  follow-up `20261007090000`. Running their read-only `probe-assessment-gate.sql` on UAT returns `gate_student_visible=1
  gate_is_published=1 gate_body_chars=548`, i.e. UAT already has the correct gate. These scripts are **not** run on UAT.
- `tests/e2e/qa-*` Playwright journeys (student/trainer/admin, transactions, load) on a mocked backend.

Verified: admin 5/5, e2e ×2, Coding Challenges 370, Save Module, Student Tier search, all 44 admin pages 0 errors.
Snapshot `~/banking-sb/snapshots/20261007T122203Z`. Still open: `students` read/write `USING (true)`.

## 2026-10-07 (eve) — deployed `4480728`: mapped module groups invisible to candidates (draft status)

**Symptom:** a candidate mapped to a Module Group (Group Mapping → Bulk Assign) saw none of its modules in the journey.
**Cause:** `module_groups.status` defaults to `'draft'`, and **Curriculum Setup → Module Groups** (`AdminModuleGroups.tsx`) created
groups without a status and had no publish control (the pil-admin `ModuleGroupsManager` sets `published`). Both the journey hook
(`useAssignedModuleIds`) and RLS (`private.user_can_access_module`, see the 10-06 tightening above) count only published/active
groups, so the mapping rows existed but granted nothing. On UAT, 10 draft groups held ~92 candidate mappings.

Fix (frontend only, no migration):
- New groups are created `published`; save errors are now surfaced instead of a false "Group saved".
- Draft groups show a **"Draft · hidden from candidates"** badge and a **Publish** button on the Module Groups page.
- Bulk Assign shows a **Draft** badge per group and a red "Draft group selected" warning in Preview.
- One shared rule `isModuleGroupLive()` (`src/lib/moduleAssignments.ts`, mirrors the RLS check) used by the hook and both admin screens.

Data fix on UAT: 9 draft groups set to `published` (MBA - Finance - 1st Semester, Axis Securities, AQM Technologies, Life Insurance,
Yes Securities, Industrial Engineering & Management, Orientation & Wealth Sales Foundation, Syrma SGS - Tech Skills, Equity Derivatives
Certification Examination). "Banking Testing" (0 modules) left draft. Previous statuses in `public._bak_module_groups_status_20261007`.
Verified as the candidate under RLS: the MBA module became visible (11 → 13 visible modules).

**Hosted/PROD:** the same code defect exists there, and draft groups mapped to candidates will need publishing (via the new Publish
button once hosted is deployed).

Known gap (not fixed): Bulk Assign lists every profile, including staff. Roles can't separate them because staff accounts also carry
`candidate`/`student` in `user_roles`.

Verified: admin 5/5; headless: Module Groups shows 1 Draft badge + Publish (Banking Testing); Bulk Assign Draft badge + warning; 0 page errors.
Snapshot `~/banking-sb/snapshots/20261007T123153Z`.

## 2026-10-07 (night) — redeployed to `937135a` (7 commits)

- **Migration `20261007132257`** (as shipped, no fixup): rewrites `private.user_can_access_module` so cohort/institute group
  assignments also match a candidate through `profiles` when there is no `students` row (institute_id, `profiles.institute` as
  college, `profiles.course` as degree) and picks the oldest `students` row deterministically. Rehearsed in BEGIN…ROLLBACK:
  user×module visible pairs **1,833 → 1,833** (no gains or losses on UAT data); candidate reads modules/topics/assessments clean.
- Frontend (Lovable): Group Assign surfaces delete/insert errors and fires `lovable:modules-updated` so open journeys refresh;
  Module Groups revoke surfaces errors; candidate **My Trainer Curricula** also shows curricula returned by the
  `my_assigned_curricula()` RPC (server rule `student_has_curriculum`). The 4480728 draft-group fix is intact.
- `scripts/release/paste/probe-*.sql` read-only probes for the hosted project's migration ledger and live
  `user_can_access_module` body (not run on UAT); QA load-spec tweak.

Verified: admin 5/5; Module Groups Draft badge + Publish and Bulk Assign draft warning still present; 0 page errors; live function has
the profile fallback; `my_assigned_curricula()` callable as a candidate. Snapshot `~/banking-sb/snapshots/20261007T134509Z`.

## 2026-10-07 (eve) — redeployed to `631a9a36`

Since my `5978c42` deploy another session deployed twice (`44807285` module-group publish/draft flag; then up to `937135a9`), which
applied `20261007132257` (rewrites `private.user_can_access_module`: falls back to the **profile's** institute/college/degree when a candidate
has no `students` row; picks the oldest students row). Verified live: the body contains the `me` CTE (upstream's read-only
`probe-module-access-version.sql`: `has_me_cte=1 private_chars=2172`), and my assessment gate is intact (`student_visible` + `is_published`).
The only new commit for this deploy was a release-probe tweak (`631a9a36`); the bundle is unchanged (`index-BTlhk-P0.js`).

Visibility now: candidate×module **986** (was 960; +26 from profile-based matching), candidate×assessment **1,735**.
Verified: admin 5/5, e2e ×2, Coding Challenges 370, Save Module, Student Tier search, 44 admin pages 0 errors.
Snapshot `~/banking-sb/snapshots/20261007T155823Z`. Still open: `students` read/write `USING (true)`.

## 2026-10-07 (night) — redeployed to `d35998ab` (16 commits, no Supabase migrations)

Upstream: deadlines section / smart reminders, refined trainer assign panel, curriculum content studio with background build polling
(`build-curriculum-from-content`), LLM Config provider picks, institute→department change in a form. All my guards and upstreamed fixes intact; overlays 3.

**Not applied on UAT, deliberately:** `drizzle/migrations/0000_assessment_uploads_policies.sql` (commit `c38fb314` "Fixed upload storage
area"). It grants **every signed-in user read on the whole `assessment-uploads` bucket**, which holds candidates' recorded assessment answers
(`StudentAssessmentTaker`) and trainer curriculum files. UAT already has scoped `storage_assessment_uploads_scoped_read/_write` (admin,
own-uid folder, trainer-curricula). Raise with the team before hosted keeps it.

**Deploy script change:** `package.json` gained dev-only drizzle/postgres deps without a regenerated `package-lock.json`; `npm ci` would refuse.
`deploy.sh` now runs `npm ci` only when `package-lock.json` changes (`~/banking-checks/deploy.sh` → `~/banking-sb/deploy.sh`).

Verified: admin 5/5, e2e ×2, Coding Challenges 370, Save Module (the first listed module is now a new group-less one, so no
group-items POST, which is expected and was confirmed against the pre-deploy dump), Student Tier search, 44 admin pages 0 errors.
Snapshot `~/banking-sb/snapshots/20261007T183412Z`. Still open: `students` read/write `USING (true)`.

## 2026-10-08 — fixed: trainer "Build topics, lessons & quizzes from my content" → "No working AI provider" (`dff50a13`, pushed to main)

Reported on the trainer AI Curriculum Builder (NISM Series X-B Level 2 PDF). The **Gemini key was already mapped** (Admin → LLM Config,
provider `gemini`, `gemini-3.6-flash`, global, enabled) and valid. Root cause from the function logs: `build-curriculum-from-content` sent
the PDF to every provider through the **OpenAI-compatible** path as a `file` content part, and **Gemini's OpenAI endpoint rejects that**
(`400 Invalid content part type: file`). OpenAI timed out on the document; NVIDIA (403) and DeepSeek (401) keys are dead.

Fix: when files are attached, call Gemini's **native** `generateContent` with the PDF as `inline_data` (key: `GEMINI_API_KEY` or the `gemini`
row), with the curriculum schema as `responseSchema` (JSON-Schema-only keywords stripped, so output is constrained and always parses) and
`maxOutputTokens 32768`; accept a bare topics array. The configured-provider and Lovable paths are unchanged as fallbacks. Iterations seen while
fixing: a bare array instead of `{topics}`, then malformed JSON before `responseSchema` was added.
Verified: the trainer's own curriculum built **6 topics** in ~2 min (`finishReason STOP`, 36k chars); admin 5/5 and 3-role e2e after.

**Open:** NVIDIA (403) and DeepSeek (401) provider keys in LLM Config are dead, and OpenAI times out on large documents. Replace or disable them.

## 2026-10-08 (pm) — redeployed to `d577d3a5` (6 commits since another session's `eba2249c` deploy; no migrations)

Upstream: video generation adds providers and lengths, 2D style and Indian languages (`generate-video` now reads `SARVAM_API_KEY`,
`ELEVENLABS_VOICE_ID`). On UAT neither is set (ElevenLabs uses its configured key/default voice; there is no Sarvam provider row), so the Sarvam
option will not work on UAT until a key is added. My `toPublicUrl` and Gemini PDF changes are intact; overlays 3.
Verified: admin 5/5, e2e ×2, Coding Challenges 370, Save Module, Student Tier search, 44 admin pages 0 errors.
Snapshot `~/banking-sb/snapshots/20261008T155237Z`. Still open: `students` read/write `USING (true)`; dead NVIDIA/DeepSeek keys.

## 2026-10-08 (eve) — fixed: AI Generated Videos → "runway is not configured" (409) + ElevenLabs "lang is not defined" (`32d303c1`)

Reported for two modules with Visual Provider = **Runway**. Causes:
1. **Runway row disabled.** `llm_provider_configs` had `runway` (feature `video_generation`, model `gen4.5`, key present) with
   `enabled=false` since its creation on 09-24, never tested. `generate-video` only reads enabled rows, so an explicit
   Runway choice returned 409. The key was validated read-only (`GET /v1/organization`: valid, 500 credits, `gen4.5` on tier) and **enabled**
   (DB config, UAT only).
2. **Code bug from `d577d3a5`:** `callElevenLabs` was called with `(…, voiceId, lang)` and uses both, but its signature ended at `targetMinutes`,
   so every ElevenLabs narration threw `ReferenceError: lang is not defined`, both on the forced narration path and the audio fallback.
   Fixed and pushed to main (`32d303c1`).

Verified: the UI path (provider runway, 2D explainer, en-IN) for "The Balance Sheet (The Nucleus of Accounting)" → Runway video + narration
in ~126 s, public link 206 video/mp4; forced ElevenLabs narration → audio in ~2 s. (The narration test overwrote that topic's project with
audio-only; restored to the Runway video by re-signing the stored `videos/runway/<topic>.mp4`.) Admin 5/5 + 3-role e2e after.

**Cost warning:** one Runway video used **96 credits** (500 → 404), so about 4 more fit. Use Veo or "auto" for bulk "Generate Missing", or top up Runway.
Topics already marked Failed must be regenerated from the panel.

## 2026-10-11 — redeployed to `57552460` (104 commits since `32d303c1`, 16 migrations)

Upstream: Robo Assistant / voice simulation layer (`sim-voice`, human banker avatar), in-conversation task workspaces with
server-side validators, speech metrics, assessment experience level + lowercase question difficulty, fail-closed proctoring
telemetry, learning-path intake (`students.job_description/skills/experience`), Admin LLM Config save fix, RBAC table policies.

New schema on UAT: `sim_voice_sessions`, `sim_utterances`, `sim_consent_records`, `sim_avatar_assets`, `sim_voice_profiles`,
`sim_task_fixtures`, `sim_task_submissions`, `sim_validator_runs` (staff-only, holds the answer key), `sim_speech_metrics`,
private bucket `sim-voice-audio`; `sim_events.seq`; `assessments.experience_level` (fresher/intern/experienced);
`assessment_questions.difficulty` now easy/medium/hard (was Easy/Medium/Hard); proctoring pct columns have no default (NULL = not captured).
Menus `simulations`, `live_sessions`, `robo_assistant` registered in menu access + RBAC (all tiers on).

Behaviour changes:
- **Publish = student-visible.** A trigger sets `metadata.student_visible=true` on publish unless the author set it; 8 published
  UAT assessments without the flag became visible (candidate×assessment 2,195 → 2,248).
- **Institute scope is now a server rule** (`private.assessment_institute_open_to`): an assessment mapped via
  `assessment_institute_mapping` or `institute_ids` is visible only to that institute's students (6 scoped published rows on UAT).
- Sim attempt updates limited to the pack manager (was any curriculum staff).
- `llm_settings` readable by every signed-in user (no secrets in it; keys stay in `llm_provider_configs`), writable by admins only.

UAT fixups (`~/banking-sb/fixups/`): `20261010091500_topic_videos_student_read_policy` (UAT `topic_videos.module_id` is text, upstream uuid —
guarded cast); `20261010160000_tech_assessment_catalog_backfill` (UAT `quiz_question_bank.source_module_id` is uuid — compare as text;
UAT has 0 tech questions, so it wrote no papers). Drizzle `0001_create_llm_usage_logs` not needed (table already exists with admin-read RLS).
The modified `20260911132000` is superseded by `20261010203000`, which ran.

Rehearsed in BEGIN…ROLLBACK with candidate/trainer/admin probes first. Verified after: admin 5/5, Coding Challenges 375, Save Module,
Student Tier search, 45 admin pages 0 errors, 3-role e2e ×2. Snapshot `~/banking-sb/snapshots/20261011T115700Z`.
Still open: `students` read/write `USING (true)` (candidate still reads 79 student rows); UAT keeps the older open
"signed in read topic_videos" policy; dead NVIDIA/DeepSeek keys; Runway credits ~404.

## 2026-10-11 (pm) — redeployed to `4193d9f4` (22 commits since `57552460`; no migrations)

Upstream: Robo Assistant fixes + voice/animation enabled, track filter applied to simulations (filter-tracking bug fixed),
Key Features section. `elevenlabs-tts` gains a Gemini TTS path whose default voice reads optional `GEMINI_TTS_VOICE`
(unset on UAT → "Kore"; male/female pick Charon/Kore). `vite.config.ts` adds `optimizeDeps` (dev server only).
Verified: admin 5/5, Coding Challenges 375, Save Module, Student Tier search, 45 admin pages ✓, 3-role e2e ×2.
Snapshot `~/banking-sb/snapshots/20261011T132713Z`.

## 2026-10-11 (eve) — redeployed to `90a654e0` (8 commits since `4193d9f4`; no migrations, no new env)

Upstream: Robo Assistant voice — hands-free listening resumes after the persona speaks; `elevenlabs-tts` / `_shared` tweaks.
Verified: admin 5/5, Coding Challenges 375, Save Module, Student Tier search, 45 admin pages ✓, 3-role e2e ×2.
Snapshot `~/banking-sb/snapshots/20261011T145133Z`.

## 2026-10-11 (late) — redeployed to `2da98562` (3 commits since `90a654e0`) — Simulation performance dashboard

Upstream: candidate "Performance" dashboard (`SimPerformanceDashboard.tsx`, linked from My Simulations and Robo Assistant),
backed by RPC `public.sim_candidate_dashboard()` — SECURITY DEFINER, returns the caller's own non-preview attempts (`mine`)
plus every candidate's scored attempts anonymised by `dense_rank` (`peers`: module, mode, score, time; no user ids).
**The RPC ships only as drizzle `0002_sim_candidate_dashboard.sql`** (not in `supabase/migrations`), so `deploy.sh` does not apply it:
it was rehearsed (BEGIN…ROLLBACK, as a candidate: mine=7 peers=3) and applied by hand; copy kept in `~/banking-sb/drizzle-applied/`.
`03_grants.sql` re-grants anon EXECUTE on all public functions, so it now ends with an explicit revoke for this RPC (anon=false, authenticated=true).
Gotcha for future releases: check `drizzle/migrations` for new SQL too — the deploy script only reads `supabase/migrations`.
Verified: admin 5/5, Coding Challenges 375, Save Module, Student Tier search, 45 admin pages ✓, 3-role e2e ×2.
Snapshot `~/banking-sb/snapshots/20261011T161123Z`.

## 2026-10-14 — redeployed to `4f808d6d` (31 commits since `2da98562`, 11 migrations + drizzle 0003)

Upstream: AI Coach sprints 1–6 (trusted grading, evidence outbox/ledger, skill graphs, learner model, server-side quiz
sessions, pilot controls + shadow runs), trainer workspace + student "module tutor" menu rows, taxonomy write repair
(`can_manage_taxonomy_v1`, admin/super_admin/taxonomy_editor only), persistent sim voice rooms + private `sim-avatar-assets`
bucket (GLB runtime), bulk "generate missing simulations", learning-hours tracking (`learning_hours_report`,
`my_assigned_module_hours` — drizzle 0003, applied by hand, copy in `~/banking-sb/drizzle-applied/`), new
`grade-coding-challenge` function (JDoodle), Vite `manualChunks` (9 `vendor-*` chunks).

**Coach capture triggers** (`coach_source_capture`) now fire on every write to quiz_attempts, assessment_attempts,
student_solved_challenges, module_progress, student_module_topic_progress, sim_attempts, curriculum_topic_progress, plus
`assessment_responses` / `assessment_questions` (invalidate receipts). Rehearsed: ≤100 ms per 20-row write.

**UAT fixup** `20261012120000_coach_sprint3_adapters`: upstream `NOT EXISTS(SELECT 1 FROM topics WHERE id=topic AND
module_id=content)` is ambiguous (42702) because `topics` has a `content` column and the PL/pgSQL variable is also `content`;
the error is not in the adapter's quarantine list, so it would roll back every submitted simulation whose pack names a topic.
Rewritten as `(SELECT tp.module_id FROM topics tp WHERE tp.id=topic) IS DISTINCT FROM content`. Upstream still has the bug.

**Deploy-script change — function ACLs are preserved.** `03_grants.sql` grants anon + authenticated EXECUTE on ALL public
functions, which silently reopened functions upstream revokes (e.g. `coach_enqueue_evidence_v1` — any signed-in user could have
forged graded evidence). `deploy.sh` now snapshots function ACLs after migrations (`~/banking-checks/fn_acl_snapshot.sql`
→ `snapshots/<TS>/fn_acl_restore.sql`), runs 03/05, then restores them. Verified live: enqueue/outbox not callable by
authenticated/anon (anon REST → 401); browser RPCs (coach_contract_v1, submit_quiz, configure_pilot, learning_hours_report) still callable.

Gotchas this release: upstream `package-lock.json` is out of sync with `package.json` (`npm ci` → "Missing: @esbuild/win32-x64");
the only new dep is dev-only `@electric-sql/pglite` (tests), so the build ran on the existing node_modules. Fix upstream with a regenerated lock.
`sim-voice` signs `sim-avatar-assets` GLB URLs with `createSignedUrl` (internal `http://gateway` origin on self-hosted) — harmless
until an approved avatar asset exists (0 on UAT), then it needs `toPublicUrl` like `generate-video`.
Coding: UAT has no `JDOODLE_CLIENT_ID/SECRET`, so Run (`execute-code`) and the new hidden-test grader both fail (pre-existing for Run);
0 of 375 challenges carry `metadata.module_id`, which the grader also requires.

Verified: admin 5/5, Coding Challenges 375, Save Module (now also calls `learning_hours_report` 200), Student Tier search,
admin crawl 42 sidebar pages ✓ 0 ✗ (menu rows changed), 3-role e2e ×2. Candidate×module 1,619 / ×assessment 2,304 unchanged.
Snapshot `~/banking-sb/snapshots/20261014T031415Z`.

## 2026-10-14 (pm) — redeployed to `a8ae5769` (2 commits since `4f808d6d`, 1 migration)

Upstream: in-app, admin-triggered content / AI quality audits (`content-quality-audit`, `coach-in-app-runner`, `_shared/content-quality.ts`;
tables `content_quality_jobs` + `content_quality_reviews`, admin-only RLS, no cron), AI quality gates in the question/coding/curriculum/
sim-pack generators, WebRTC avatar transport, `npm run test:providers` smoke script (package.json only, lock unchanged).
Rehearsed (candidate insert blocked, admin insert ok, rollback clean). The function-ACL restore ran (287 functions;
`coach_enqueue_evidence_v1` still closed) and the sprint-3 `topics.content` fixup is still the live adapter body (upstream still unfixed).
Verified: admin 5/5, Coding Challenges 375, Save Module, Student Tier search, admin crawl 42 ✓ 0 ✗, 3-role e2e ×2.
Snapshot `~/banking-sb/snapshots/20261014T061900Z`.

## 2026-10-14 (late) — redeployed to `4a2cd7e6` (5 commits since `60a67d3c`, 2 migrations)

(Between my `a8ae5769` deploy and this one, another session deployed up to `60a67d3c` — snapshot `20261014T081541Z`.)

Upstream: trainer module visibility scoped to explicit mappings (`trainer_can_access_module`, `trainer_can_access_admin_module`;
new read policies "Scoped authenticated module reads" / "Scoped admin module reads" / "Scoped admin module topic reads" replace
the old open reads), student curriculum visibility across all identity keys (`student_has_curriculum` rewritten,
`curriculum_assignments.student_user_id/student_profile_id` backfilled — 3 rows on UAT), paginated candidate assessments,
trainer module-import blank-screen fix.

**UAT fixup** `20261014160000_trainer_explicit_module_visibility`: UAT `admin_modules.source_module_id` is **uuid** (text upstream) →
`uuid = text` error; three `::text` casts, nothing else changed.

Measured in rehearsal (per role, summed over every trainer / 30 candidates / admin):
- Candidates: `admin_modules` 2,130 → 372 and `admin_module_topics` 17,910 → 4,007 — the old `USING (true)` reads let every candidate
  read the whole admin catalogue; now only modules they can access. `modules`/`topics` and candidate×module (1,623) / ×assessment (2,304) unchanged.
- **Trainers: effectively unchanged (modules 480 → 470, admin_modules 355 → 355).** Upstream's new scoping is undone by its own older
  policies still on the tables: `admin_modules staff write` / `admin_module_topics staff write` are `FOR ALL` to admin+trainer (so they also
  grant SELECT of every row), and `modules mapped read` → `module_visible_to()` lets any trainer read every published module. Same on hosted.
  Making trainer scope real needs those split into INSERT/UPDATE/DELETE policies and `module_visible_to` narrowed — team decision.
- `curriculum_assignments` still has an open `authenticated read USING (true)` policy (pre-existing).

Verified: admin 5/5, Coding Challenges 375, Save Module ×5 (all 200), Student Tier search, admin crawl 42 ✓ 0 ✗, 3-role e2e ×2.
`admin_error_logs` "Network error: Failed to fetch" rows come from headless checks closing pages (seen on earlier days too);
one "Failed to fetch dynamically imported module" right after the dist swap — the chunk exists, index.html is no-store.
Snapshot `~/banking-sb/snapshots/20261014T090904Z`.

## 2026-10-14 (eve) — redeployed to `afcb5272` (2 commits since `4a2cd7e6`, 1 migration)

Upstream: candidate Learn menu shows "My Simulations" and "My Robo Assistant" again
(`20261014160000_candidate_simulation_menu_access_repair` — note it shares a timestamp with the trainer-visibility file; fixups
are keyed by full basename so no clash), and assessment filters stay wired across Domain/Tech tracks.
The migration re-labels the two `menu_access_controls` rows (tier switches untouched, still all on) and adds both keys to
`candidate_menu_permissions` rows missing them — 7 on UAT, all created 10-12/10-14 from the app's 48-menu default that lacked
these keys (not admin removals), so the backfill is the intended fix.
Verified: admin 5/5, Coding Challenges 375, Save Module, Student Tier search, admin crawl 42 ✓ 0 ✗, 3-role e2e ×2.
Snapshot `~/banking-sb/snapshots/20261014T101301Z`.

## 2026-10-15 — redeployed to `65bd7b0b` (11 commits since `afcb5272`, 5 migrations)

Upstream: role-scoped Metabase dashboards (`metabase-embed-token` function + 6 `metabase_*` reporting views), proctoring
snapshots linked to the attempt via atomic RPC `append_assessment_proctoring_snapshot` (own, unfinished attempts only),
simulation menus tied to module plans (`simulation_module_plan_catalog`: dedups `menu_access_controls`, tags 7 legacy
aliases `deprecated` + `canonical_key` so Plan Menu Access hides them; tier switches unchanged on UAT — 0 switched on or off),
module-group mapping across both catalogs (`save_module_group_mapping` / `replace_module_group_members` write `modules` and
`admin_modules`), AI video requested/actual duration + quality metadata on `topic_videos`, grounded 3D video controls,
Robo Assistant navigation/continuity/transport fallback, multi-domain AI context (MCP server renamed "Multi-domain Learning Platform").

**Metabase views were a PII exposure on this stack — closed.** They are plain views owned by postgres, so they bypass RLS,
and `03_grants.sql` grants anon SELECT / authenticated ALL on every relation in `public`: as shipped, anyone holding the public
anon key could have read every student's names, scores and proctoring counts over PostgREST. The app never reads them
(only Metabase, with its own DB role), so the UAT fixup revokes them from PUBLIC/anon/authenticated (service_role keeps SELECT)
and `03_grants.sql` now ends with the same REVOKE. Verified live: anon REST → 401 "permission denied for view".
Hosted Supabase's default grants expose these views the same way — upstream should revoke them (or use security_invoker).

UAT fixup `20261014170000_metabase_reporting_views` also: `quiz_question_bank.module_id` and `module_live_sessions.module_id` are text
on UAT (compare as text); `modules` has no `track` column on UAT (track lives in `metadata`), so `m.track` → NULL in the COALESCE.
Metabase itself is not configured on UAT: `metabase-embed-token` answers 503 "Metabase is not configured" until
`METABASE_URL`, `METABASE_JWT_SECRET` and the three `METABASE_*_DASHBOARD_ID` secrets exist.

`mcp` overlay rebased onto upstream (rename + UAT issuer line). The checkout carried a stale working-copy edit to
`supabase/functions/mcp/index.ts` that blocked the fast-forward (deploy aborted before any migration); saved to
`snapshots/20261015T044757Z/mcp-working-copy.patch` and restored — the overlay is the source of truth.

Verified: admin 5/5, Coding Challenges 375, Save Module, Student Tier search, admin crawl 42 ✓ 0 ✗, 3-role e2e ×2;
candidate×module 1,669 / ×assessment 2,354 unchanged. Snapshot `~/banking-sb/snapshots/20261015T044806Z`.

## 2026-10-15 (am) — redeployed to `ea46395e` (3 commits since `65bd7b0b`; no migrations, no function changes)

Upstream: platform text parameterised for multi-domain learning (50 files, copy/branding), student assessment catalogue
browsing improved and its filters wired. New optional build var `VITE_CANONICAL_APP_URL` (Home page site URL) is unset on UAT and
falls back to `window.location.origin`, i.e. UAT. Bundle audit: hosted refs unchanged vs previous build (the `kbwjokmmzkgjwiqelrdc`
hits are the admin security-migration form default; `*.lovable.app` hits are SEO/OG strings).

Deploy-script change: the Vite build regenerates the bundled MCP server into `supabase/functions/mcp/index.ts` (e.g. mcp-js
0.26.2 → 0.26.3) — that, not a person, was the recurring dirty file that aborted the 10-15 fast-forward. `deploy.sh` now runs
`git checkout -- supabase/functions/mcp/index.ts` before merging; the deployed MCP still comes from the function-fixups overlay.
Verified: admin 5/5, Coding Challenges 375, Save Module, Student Tier search, admin crawl 42 ✓ 0 ✗, 3-role e2e ×2.
Snapshot `~/banking-sb/snapshots/20261015T054107Z`.

## 2026-10-15 (pm) — redeployed to `8130bbf8` (2 commits since `ea46395e`, 1 migration)

Upstream: trainer console gets a "Create Assessment" menu entry and a clearer candidate bulk upload ("Bulk Upload Candidates",
required vs optional template columns); AI-video progress skips non-UUID fallback topics and topics owned by another module
(stops opaque 409s). Migration `20261015143000_reconcile_topic_progress_upsert` dedups `student_module_topic_progress` by
(student_id, topic_id) keeping the newest row, then adds a unique index — on UAT a no-op: 0 duplicates (15 rows before/after) and
the equivalent `student_module_topic_progress_student_id_topic_id_key` constraint already existed (the new index is redundant).
Verified: admin 5/5, Coding Challenges 375, Save Module, Student Tier search, admin crawl 42 ✓ 0 ✗, 3-role e2e ×2.
Snapshot `~/banking-sb/snapshots/20261015T121602Z`.

## 2026-10-15 (eve) — redeployed to `04130d70` (6 commits since `8130bbf8`, 2 migrations) — identity/RLS/billing hardening

Upstream closes most P1s from the 10-15 E2E QA (see `~/banking-qa-20261015` report):
- **students/profiles RLS rebuilt** (`20261015170000_identity_rls_and_billing_hardening`): every legacy policy on both tables is
  dropped (incl. UAT's open `students authenticated read/write USING (true)`) and replaced by scoped policies — self, admin, or
  trainer/teacher/institute within `current_user_institute_ids()` (+ trainer's own onboarded students). Rehearsed per role:
  candidate students 93 → 1, trainer 93 → 10 (own institute/onboarded), admin unchanged; candidate cannot edit another student (0 rows).
- **Trigger `prevent_client_identity_control_mutation`** on profiles/students: only admin or `service_role` (auth.role() from JWT
  claims) may change subscription_tier/status/expiry, approval_status, is_active (profiles) or status (students) → candidate
  self-upgrade blocked. Note: a plain psql session (no JWT claims) counts as untrusted too — set
  `request.jwt.claims` role=service_role for manual data fixes on those columns.
- `admin_approve_payment_request` now writes both profiles and students (approved plan no longer reverted on next login).
- `candidate-otp-login`: random auth passwords + rotation of legacy derived passwords on successful OTP (closes the derived-password
  login bypass). The fixed OTP that used to be hard-coded "1234" is now admin-configurable in SMS Gateway settings
  (`sms_gateway_settings.temporary_otp_enabled/temporary_otp`, default on/"1234" — UAT behaviour unchanged; turn off for real SMS).
- New `notification_gateway_settings` (admin-only), password-reset delivery hardening (`RESEND_API_KEY`, `PASSWORD_RESET_ALLOWED_ORIGINS`
  optional), server-side duplicate module-group guard (UAT has 1 existing duplicate group; editing its name/taxonomy will now be refused).

**UAT fixup** for `20261015170000` (two changes, rest verbatim):
1. Students policies subqueried `trainers` directly while UAT's trainers read policy subqueries `students` — the 10-02 infinite-recursion
   pattern; both now call `private.is_my_trainer_row(onboarded_by)` (same predicate, SECURITY DEFINER).
2. Upstream trigger bug: one combined condition referenced `NEW.subscription_expires_at` for students rows; `students` has no such column
   on UAT, so **every non-admin students UPDATE failed** (candidate editing own location). Rewritten as nested IFs per table. Upstream still
   has the bug — it breaks on any DB whose students table lacks that column.

Verified: admin 5/5, Coding Challenges 375, Save Module, Student Tier search, admin crawl 42 ✓ 0 ✗, 3-role e2e ×2 (candidate OTP login
works after password rotation); candidate×module 1,700 / ×assessment 2,459 unchanged. Snapshot `~/banking-sb/snapshots/20261015T164830Z`.
Still open from QA: trainer module scoping (older FOR ALL staff policies), JDoodle/Metabase config.

## 2026-10-16 — redeployed to `fef5fe39` then `9968cc19` (27 commits since `04130d70`; 3 migrations + drizzle 0005)

Upstream: advanced simulation task workspaces with a code/SQL execution ledger (`sim_execution_runs`, own-or-staff read;
Judge0 via optional `JUDGE0_URL`/`JUDGE0_API_KEY` — unset on UAT → runs report "unavailable"), financial-modelling solver,
trainer visibility of modules granted directly to their institute's students and to the trainer (by module or group,
`user_module_access` "Trainers can view own mapped content"), subscription entitlement/plan display fixes, trainer crash fixes,
transient module-catalog read retry. Domains list made private (drizzle `0005_keep_domains_private`, applied by hand, copy in
`~/banking-sb/drizzle-applied/`; supersedes 0004): readable by signed-in users only — no logged-out page reads it.
Notification gateway settings now persist (UAT `.env`: `VITE_NOTIFICATION_GATEWAY_PERSISTENCE_ENABLED=true`,
`VITE_NOTIFICATION_GATEWAY_SCHEMA_VERSION=20261015160000`). `mcp` overlay rebased (upstream rename).

**UAT fixup** `20261015200000_trainer_direct_group_module_visibility`:
1. `admin_modules.source_module_id` is uuid on UAT → compared/matched as text.
2. **Content-entitlement leak closed:** upstream now builds the trainer scope from the caller's profile for ANY user, and
   "Scoped admin module topic reads" calls `trainer_can_access_admin_module` for every role, so a candidate would have read the admin
   topics of every module granted to classmates in their institute (rehearsed over 30 candidates: 3,849 → 16,257 rows). Both trainer
   functions now return false unless the caller holds trainer/teacher/institute. Rehearsed after fix: candidates 3,849 (unchanged),
   trainers modules 793 → 800 (the intended widening), candidate×module 1,714 / ×assessment 2,507 unchanged.

**Known gap, not fixed on purpose:** the admin Platform Usage Report (admin dashboard + Coding Challenges page) selects
`profiles.plan_tier`, a column UAT doesn't have (no upstream migration creates it) → 400, report shows no profile names/institutes.
Do NOT just add the column: the app takes the highest of `subscription_tier` and `plan_tier` (`resolveEffectiveSubscriptionTier`) and
`prevent_client_identity_control_mutation` does not guard `plan_tier`, so a candidate could self-upgrade by PATCHing it. Upstream should
drop `plan_tier` from the select, or add the column together with the trigger guard (check hosted for the same hole).

Verified: admin 5/5, Coding Challenges 375, Save Module, Student Tier search, admin crawl 42 ✓ 0 ✗, 3-role e2e ×2 (only API error = the
plan_tier 400). Snapshots `~/banking-sb/snapshots/20261016T040345Z`, `20261016T040813Z`.

## 2026-10-16 (am) — redeployed to `f23f2035` (2 commits since `9968cc19`; functions only)

Upstream: `generate-assessment-questions` fallback hardened and bulk fallback questions de-duplicated (`_shared` + function; no
migrations, no new env/provider calls). Verified: admin 5/5, Coding Challenges 375, Save Module, Student Tier search, admin crawl 42 ✓ 0 ✗,
3-role e2e ×2 — only API error is the known `profiles.plan_tier` 400 on the admin Platform Usage Report (deliberately not "fixed" by adding
the column; see 2026-10-16 entry). Snapshot `~/banking-sb/snapshots/20261016T064946Z`.

## 2026-10-16 — mobile admin password reset fixed on UAT (`03bfb448`, functions only)

The reported failure was **Admin → User Management → All Users → Reset Password** for a mobile-backed admin (`<mobile>@bankready.app`). Both `admin-user-actions` and its directly callable fallback `admin-reset-password` still carried the 08-28 blanket OTP-account refusal, although Admin Login has a password field and candidate/trainer OTP now uses a server-issued magic link.

Both reset endpoints now read the target's **database `user_roles`** before changing its password. A target with `admin` or `super_admin` can reset a mobile-backed account, then sign in at `/login/admin` using the ten-digit mobile as User ID and the new password. Ordinary mobile candidate/trainer targets remain refused with OTP guidance; neither client-supplied roles nor `user_metadata.role` can bypass the check. Password strength and caller-admin checks remain enforced.

Successful admin resets atomically store the password and service-managed `app_metadata.admin_password_set=true`, preserving existing app metadata. `candidate-otp-login` preserves that password only while this marker is a boolean true **and the current database role is still admin/super_admin**. Other OTP accounts still rotate their internal password. The previous rotation generated a 77-byte password that UAT GoTrue rejected (72-byte bcrypt ceiling), silently continuing with the old credential; passwords now use one random UUID plus the strength suffix (40 bytes), and a rotation failure aborts the login. No existing user passwords were changed by the release; legacy credentials rotate when those accounts next complete OTP sign-in.

Deployment scope: the frontend/main checkout remains `f23f2035`; no migrations, frontend build, new config or provider calls. Original fix commits `8906ce2e` + `03bfb448` are saved on DEV branch `fix/mobile-admin-password-reset` and the **local UAT repo branch** `uat/mobile-admin-password-reset`. They are now also published on GitHub branch `fix/mobile-admin-password-reset` as `d68c767a` + `91dbd3df`, in [draft PR #1](https://github.com/PluginLive-Technologies/bankingjobreadiness/pull/1). They remain outside GitHub `main`: `.github/workflows/deploy-candidate-auth.yml` automatically deploys changes to `candidate-otp-login` or `_shared` on `main` to the separate hosted Supabase project `kbwjokmmzkgjwiqelrdc`; the current deployment authorization covers self-hosted UAT. Four persistent UAT overlays are installed under `~/banking-sb/function-fixups/`: `_shared/otp-login.ts`, `admin-user-actions/index.ts`, `admin-reset-password/index.ts`, `candidate-otp-login/index.ts`. Future releases must compare/rebase these whole-file overlays when upstream edits them.

Deployed through `~/auto_deploy.sh banking-functions`; only `banking-sb-functions` restarted. Snapshot: `~/banking-sb/snapshots/20261016T071114Z-mobile-admin-reset` (DB, prior live functions, prior overlay tree, deploy entry point and release record). Rollback restores the saved overlay tree and re-runs the function sync; no DB restore is needed for this code change.

Verification: **46/46 focused unit checks**, both live reset endpoints, rejected old password after reset, successful new password before/after OTP, preserved app metadata, rejected anonymous/non-admin callers, weak-password validation, mobile-student refusal despite forged user metadata, normal email-account resets, and OTP rotation for the non-admin account. `~/banking-checks/mobile-admin-reset.cjs` also reproduces the exact All Users dialog in Chromium and confirms a successful reset with zero page errors. All disposable auth users were removed (verified zero remaining); the reported account still has its existing admin role and its password was not changed by testing. Admin login 5/5; all 42 admin sidebar destinations load without page errors; candidate/trainer/admin reach their home pages; Coding Challenges 375, Save Module and Student Tier search pass. The previously documented `profiles.plan_tier` report 400 remains separate from this reset fix. No edge-runtime boot errors or password-rotation failures after the final deploy.

## 2026-10-16 — assessment question generation 503 fixed on UAT and GitHub (`9eae016b`)

Admin → Assessments → Create Assessment could return repeated 503 responses for a JD-based request of **35 MCQ, 3 descriptive and 2 video questions**. The function itself returned `Could not produce the requested unique question mix`; this was not an edge-runtime boot failure. Its deterministic fallback emitted only the requested number of candidates before semantic de-duplication, repeated a long source prefix in every prompt, and cycled a small set of objectives/settings. A long JD could collapse the first five-question batch to fewer than five questions. Separately, AI MCQ relevance was checked against `topic_or_skills` even in JD mode, so an absent topic became the literal context `undefined` and rejected valid JD questions.

`generate-assessment-questions` now validates MCQs against the declared source (JD or topic) plus module labels. Its fallback uses a short source anchor and distinct task/scenario descriptions, searches the bounded bank after excluding earlier prompts, then takes the exact requested counts. The common semantic de-duplication rule, five-question request limit and exact-mix guards are retained. No fake uniqueness from incrementing a variant number. **Fallbacks remain deterministic templates requiring author review**, with `generated_by=deterministic`; valid AI questions are preserved when only part of a batch needs filling. The bank has 48 scenario/objective combinations per type; exhaustion still fails rather than repeating questions.

Code: original local commit `151a3592`, published directly to [GitHub main as `9eae016b`](https://github.com/PluginLive-Technologies/bankingjobreadiness/commit/9eae016b24936ad62c7a97dca287fabb3a99b526). Only the generator and its HTTP-handler regression tests changed in that push. The auth fixes were published separately in draft PR #1 to avoid triggering the hosted auth deployment described above.

UAT deploy: `~/auto_deploy.sh banking-functions`; persistent overlay `~/banking-sb/function-fixups/generate-assessment-questions/index.ts`. The source/front-end checkout remains `f23f2035`; newer upstream SWOT features and migrations were not part of this function fix. No frontend build, database changes or provider configuration changes. All four existing auth overlay hashes were checked unchanged after deployment. Eight fixup directories are now overlaid by the function sync. Rebase the generator overlay when upstream edits that function.

Rollback snapshot: `~/banking-sb/snapshots/20261016T080537Z-assessment-generation` (DB dump, prior live functions, prior overlay tree, sync/deploy scripts and base SHA). `rollback-generation.sh` in that directory checks the overlay's release marker, removes only the new generator overlay, then runs `~/auto_deploy.sh banking-functions` against the unchanged checkout. The snapshot also contains the prior function tree. No database restore is required.

Verification: **89/89 focused checks** on the current GitHub code plus both fixes (54 generation/lifecycle/de-duplication/provenance/input checks, 35 authentication checks). The handler tests reproduce the reported 35/3/2 mix over eight fallback batches, provider errors/exceptions, exclusion-aware retries, JD-backed AI preservation, mixed AI/template provenance, each non-MCQ type, and refusal after the bounded bank is exhausted. Live UAT checks: admin login 5/5, all 42 sidebar destinations load, Coding Challenges 375, Save Module, Student Tier search, candidate/trainer/admin home pages. Both live password-reset endpoints and the All Users dialog passed again after the function restart; all three disposable auth accounts were removed. The separate admin Platform Usage Report `profiles.plan_tier` 400 remains as previously documented.

Live generation API verification: eight sequential real UAT calls, passing prior question texts as exclusions, returned **HTTP 200 ×8**, exactly **35 MCQ + 3 descriptive + 2 video**, 40 distinct prompts, **all 40 labelled `ai`**. Individual MCQ calls took approximately 60–72 seconds; the final descriptive/video batch took 42 seconds. Large mixed sets therefore still take several minutes with the current provider chain.

Live browser verification: `node ~/banking-checks/assessment-generation.cjs --stable-network` completed the exact Admin → Assessments → Create Assessment → JD → Generate 40 questions flow in **464 seconds**. Eight five-question batches returned HTTP 200; the editor rendered exactly 40 questions with the requested 35/3/2 mix, **37 `ai` + 3 labelled `deterministic` templates**, zero generation errors and zero page errors. The draft was left unsaved. Earlier unproxied Chromium runs were interrupted by `net::ERR_NETWORK_CHANGED` (not server 503s), so this check forwarded identical live UAT requests/responses through Playwright's HTTP client; no response data was mocked. The independent direct API run above also passed all eight batches. Templates must still be reviewed/replaced before publication, as the existing UI warning states.


## 2026-10-16 — full UAT release `b7df31d5`: all three pending SWOT migrations applied

UAT advanced from `f23f2035` to GitHub main `b7df31d543353625e62459af6a6b8e1ffde0961b`
(PR #1 merged). This deploy includes the newer SWOT frontend/function, subscription-menu alias
consolidation, TypeScript fixes, the question-generation fix, and the now-merged mobile admin
password-reset fix. All three pending migrations applied successfully, with no new Drizzle migrations:

- `20261016123000_learning_swot_analytics`: 20 new tables, report/catalog RLS, scoring rules and role permissions.
- `20261016130000_learning_swot_menu_wiring`: existing admin/candidate allowlists include `learning-swot`.
- `20261016140000_rename_swot_menu_labels`: **My SWOT Analytics** for students; **SWOT Analytics** for staff.

All three first passed a `BEGIN…ROLLBACK` rehearsal against the actual UAT schema. The full release
ran through `~/auto_deploy.sh banking main`, which now dispatches to `~/banking-sb/deploy.sh`.
The deploy script has `pipefail` enabled so function-sync failures cannot be hidden by its log pipeline.
It preserved the UAT environment, refreshed grants while restoring 295 function ACL statements,
synced the edge stack, and rebuilt the Vite bundle **on UAT**. Bundle inspection found no DEV,
localhost Supabase or hosted-project API URLs. Current inventory: 310 application SQL migration files,
99 application edge-function entry points, 226 public tables, seven running stack containers.
All 20 SWOT tables have RLS enabled. No added migration files remain between the UAT checkout and
this GitHub release, including the Drizzle directory.

**Current SWOT behavior.** `/learning-swot` and the journey menus show readiness, competency gaps,
Strengths/Weaknesses/Opportunities/Watch-outs, and a weekly action plan. The report aggregates existing
assessment, quiz, coding-practice and completed learning-simulation attempts and saves a versioned
`swot_reports` snapshot. Content views never create mastery. This release uses deterministic templates;
AI narratives remain behind their checker gate and no new LLM configuration/provider call was needed.
The new evidence/catalog tables are foundations for later processing, not a backfilled event ledger.
Student reports target the caller; trainer requests and intervention queues are limited to assigned
learners; admins may request other learners. Assigned job-role names resolve through
`students.target_role_id -> job_roles.name`; the report target score defaults to 70 unless supplied.
Subscription plan cards now combine legacy menu aliases into one row while preserving their enabled flags.

**Necessary UAT function compatibility overlay:** `learning-swot-report/index.ts`, saved locally as
commit `b4d7dadf` on DEV branch `fix/learning-swot-uat-compat-20261016` (not pushed to GitHub).
Upstream constructed a service-key client but overwrote its Authorization header with the user JWT,
so report writes hit user RLS and were silently discarded. The overlay verifies the caller with
`auth.getUser(token)` and keeps the verified server-side client on the service key; existing explicit
learner/trainer/admin scope checks remain in place. It also uses the existing job-role foreign key
instead of selecting nonexistent `students.target_role/target_score`, queries simulation attempts by
`user_id` instead of nonexistent `student_id`, and includes completed attempts only. A failed report
save now returns an explicit error instead of an apparently successful unsaved report. Persistent copy:
`~/banking-sb/function-fixups/learning-swot-report/index.ts`. Rebase this overlay when upstream edits the function.

**Merged patches retired.** PR #1 is now on GitHub main. The `_shared/otp-login.ts`,
`admin-user-actions`, `admin-reset-password`, `candidate-otp-login` and `generate-assessment-questions`
overlays were moved to `~/banking-sb/function-fixups-retired-20261016`. All five deployed files were
verified byte-for-byte equal to `b7df31d5`; the password/reset and generation fixes therefore run from
the repository rather than old whole-file overrides. Four overlay directories remain: `main`,
`live-session-rsvp`, `mcp`, and `learning-swot-report`. Hosted deployment status was not checked.

**Verification:** 46 focused scoring/menu/error/auth/generation checks passed. Admin login 5/5;
all 43 sidebar destinations load, including SWOT; Coding Challenges 375; Save Module and Student Tier
search pass. Candidate, trainer and admin reach their home pages and separately open `/learning-swot`
with HTTP 200, saved report IDs, all four quadrants and zero page errors. The mobile-admin-reset API
and All Users dialog checks pass after retiring the auth overlays, including password preservation
across OTP. The new runnable `node ~/banking-checks/swot.cjs` checks actual report persistence,
candidate isolation, assigned-trainer access, exclusion of unassigned cohort reports, admin access,
and RLS rejection of client-forged report snapshots. All disposable users, mappings and reports were
removed; `profiles` and `auth.users` returned to 114 each, with zero remaining QA auth probes.
No edge-runtime errors were found after release. The separate existing Platform Usage Report
`profiles.plan_tier` 400 remains unchanged; adding that unguarded field is still not a safe fix.
A local full TypeScript check was limited by the stale shared DEV dependencies: four pre-existing
SQL test files import missing `@electric-sql/pglite`; no other compiler errors were reported.
The UAT production build and the focused/runtime checks above passed.

SQL archived with UAT applied / PROD pending in **DB-Scripts** commits `248eed2`, `5571330`,
`ab587a9`, under *Banking Supabase to Postgres*:
`20261016T085929Z__banking_learning_swot_analytics.sql`,
`20261016T085930Z__banking_learning_swot_menu_wiring.sql`,
`20261016T085931Z__banking_learning_swot_menu_labels.sql`.
The archive adds explicit catalog-policy drops for safe repeat execution; all three archived copies
also passed a transactionally rolled-back replay against the deployed schema. DEV is n/a for this
self-hosted Banking stack; no PROD migration was performed.

Rollback material: `~/banking-sb/snapshots/20261016T085651Z` contains the pre-release database dump,
frontend and function archive plus `release-verification.json`. The earlier preparation snapshot
`~/banking-sb/snapshots/20261016T085621Z-swot-release` contains the original deployment scripts,
all original overlay files, and base/target commit records. Restore frontend/functions independently
when possible; review post-release writes before restoring the database snapshot.

## 2026-10-16 — UAT `639fdf9a`: admin SWOT Analytics renders (was an empty tab)

**Symptom:** Admin → Insights → Assessment Reports → **SWOT Analytics** opened `/admin?tab=learning-swot`
but showed nothing. **Cause:** frontend, not database. `Admin.tsx` had no `TabsContent` for
`learning-swot`, so the menu entry selected a tab with no body. Upstream `9e82fe23` adds it, embedding
`LearningSwot` (new `embedded` prop, no second `AppLayout`); `1726ec87` removes a duplicate banner.
The release also carries `38f71683` (Platform Usage Report no longer selects `profiles.plan_tier` →
the long-standing 400 is gone), topic-progress/module-creator fixes and `ai-content` /
`generate-trainer-curriculum` function edits (no new env reads, no direct-provider calls).

**Migrations:** none pending. All three SWOT files were already applied (20 `swot_*` tables, 3
`menu_access_controls` rows, 3 `rbac_role_permissions` rows). Upstream edited
`20261016123000_learning_swot_analytics.sql` in place after it was applied: (1) unique index
`rbac_role_permissions_role_code_menu_key_key` — already present on UAT; (2) a **student `metabase`
"BI Dashboard" menu row** — deliberately NOT applied: unrelated to SWOT, it grants a new student menu
entitlement, and UAT's Metabase views are revoked. Its `ON CONFLICT DO UPDATE SET label` would also
revert the renamed SWOT labels if the file were replayed — never replay it verbatim.

**Verification:** new `node ~/banking-checks/swotadmin.cjs` (admin login → SWOT Analytics → main
content must contain the SWOT page, zero page errors / API ≥400) — passes with readiness cards,
intervention queue and quadrants. `admcrawl.cjs` cannot catch this class of bug: its blank test reads
`#root`, which includes the sidebar. Also passed: admin login 5/5, `swot.cjs` (persistence +
isolation), admin crawl with zero failing destinations, `mobile-admin-reset.cjs`.
Snapshot: `~/banking-sb/snapshots/20261016T131035Z`.

## 2026-10-16 (eve) — AI Generated Videos reach the selected length (`3fd2dc48`, no migrations)

Reported: every topic in the admin **AI Generated Videos** drawer ended as "Preview — needs assembly" with the toast *"Provider returned
a 8s preview; the requested 4 minute lesson is not complete"*. Cause: Veo, Runway and the generic providers render **one 8 s clip**, and nothing
built the 4/8/12-minute lesson from it (`compose-video` is a re-upload placeholder, there is no ffmpeg on the edge). The narration also read only
the topic description (a few seconds). Learners only see `topic_videos.status = 'ready'`, so they saw nothing. Upstream `bb7f18d8` (same day)
only re-labelled the preview as success; `3fd2dc48` supersedes it.

Current `generate-video` flow:
1. Storyboard (LLM) — each scene's `narration` is the exact voiceover, sized at ~2.4 words/s, so the whole script fits the target.
2. **Narration first** (cheap): whole script → ElevenLabs (`mp3_44100_128`, ≤4500-char chunks in parallel, `previous_text`/`next_text`) or
   Sarvam (≤2500-char chunks, WAVs stitched by `_shared/narration-audio.ts`). Non-English scripts go through Sarvam Translate first (all chunks now,
   was capped at 5×900 chars). Duration = bytes/16000 (MP3 CBR) or PCM bytes/byteRate (WAV).
3. Length gate **before paying for visuals**: 4 → 180–300 s, 8 → 300–600 s, 12 → 600–900 s (the bands in the dropdown). Outside → 422 with
   "Narration came out at Ns…"; the row is marked failed.
4. One visual clip from the chosen provider (fallback order as before). If all visual providers fail, the lesson is saved audio-only and the panel
   shows a warning with the provider errors.
5. Result is **ready**: `topic_videos.video_path` = clip, `generation_metadata.narration_url` = narration, `duration_seconds` = narration length.
   `video_projects` gets `video_url` + `audio_url`, `params_json.assembly = "visual-loops-under-narration"`.

Narration is now **required** (ElevenLabs or Sarvam key) — without one the call is 409, never a silent 8 s clip.
Learner player (`ModuleVideosPanel`): when `narration_url` exists, the audio element is the control (play/pause/seek, "watched" at 90 %) and the
clip loops muted behind it. Known limit: the same 8 s visual repeats for the whole lesson; upgrade = one clip per storyboard scene (≈30 Runway
clips per 4-min lesson — cost and the 240 s budget rule it out today). Pre-fix rows with `status = 'preview'` show "Incomplete — regenerate" and are
picked by "Select all missing". Also fixed: the 240 s time budget was stamped at worker boot, starving later requests on a warm worker.

Deployed via `deploy.sh` (snapshot `~/banking-sb/snapshots/20261016T151842Z`, bundle `index-BKZoFW55.js`). Verified: function live (input
validation responds), new chunks in `dist`, admin login 5/5, every admin page passes admcrawl. **Not yet verified with a real generation**
(costs ~$1 of Runway credits + ElevenLabs).

## 2026-10-16 — UAT `d705561f`: student module journey redesign + progress fix (frontend only)

UAT advanced `3fd2dc48` → `d705561f` (3 commits: `5303bcfb` student module learning-journey redesign —
`ModuleDetailView`, `TechStudentJourney`, `CandidateHome`; `d705561f` dashboard progress calculations
via `src/lib/supabaseResult.ts`; candidate menu `robo_assistant` label **"My Robo Assistant" → "My Robo Play"**
(frontend label maps only; `menu_access_controls` rows unchanged)). No migrations, no function changes,
no new `VITE_*` gates, lockfile unchanged.

**Verification:** admin login 5/5 (×2; one earlier pass timed out waiting for the login form right after
the rest restart, not reproducible), `swotadmin.cjs` pass, admin crawl 43/43, Coding Challenges, Save
Module, Student Tier search, and candidate/trainer/admin home pages with zero page errors / API errors.
Snapshot: `~/banking-sb/snapshots/20261016T182515Z`.

## 2026-10-17 — UAT `0ea7f583`: student journey runtime fix

UAT advanced `d705561f` → `0ea7f583` (1 commit). `TechStudentJourney.tsx` used `useMemo` without importing
it after the 10-16 journey redesign (`5303bcfb`); upstream's fix adds the import. The rest of the commit
is e2e test fixtures only (adds the existing `learning-swot` row to the student menu-access fixture). No
migrations, function changes, `VITE_*` gates or lockfile changes.

**Gap closed in our checks:** the 10-16 verification only opened `/candidate/home`, which never mounts
`TechStudentJourney`. New `node ~/banking-checks/journeytabs.cjs` logs in as demo candidate 9100000021
and opens every `/journey/student/tech?tab=…` (module_groups, modules, simulations, robo_assistant,
live_sessions, playground). It fails on any page error, error-boundary text, or an empty `main`.

**Verification:** journeytabs 6/6, admin login 5/5, `swotadmin.cjs`, admin crawl 43/43, Coding Challenges,
Save Module, Student Tier search, and candidate/trainer/admin home pages with zero page/API errors.
Snapshot: `~/banking-sb/snapshots/20261017T022817Z`.

## 2026-10-17 — UAT `0ec72eb8`: AI content maker/checker pipeline, topic persistence, simulation gating

UAT advanced `0ea7f583` → `0ec72eb8` (4 commits): `29d7918e` simulations published through module access,
`c4ad6494` edited topic content visibility, `e048e4b6` AI content quality maker/checker pipeline,
`0ec72eb8` role journey navigation + assessment loading.

**Current behavior**
- **Simulations / Robo Play (candidate):** a sim is listed only if the candidate can access the pack's
  parent module (`user_can_access_module`) AND their plan passes the student `module_simulation` menu row
  (UAT: free=false, beginner=false, advanced/enterprise=true). Legacy `sim_assignments` alone no longer
  grant access. On UAT 47/89 candidates can reach a sim module; 53 are Free. Demo candidate 9100000021
  now sees "No simulations are published for the modules you can access yet" — expected.
- **Topic edits:** Admin topic save writes `content`/`learning_outcome` (`src/lib/topicPersistence.ts`);
  migration backfilled 118 topics whose body lived only in `description`.
- **generate-topics** (new function): maker = LLM via `installLlmFetchFallback` (the hard-coded
  `ai.gateway.lovable.dev` URL is intercepted and routed through UAT's LLM Config providers — no Lovable key
  needed); checker = deterministic `topic-quality.ts`. Writes an evidence pack + `ai_generation_runs` audit
  row. Audit label says `lovable-gateway` even though the call went to the configured provider (cosmetic).
  Measured 68 s for 3 topics. `ai-video-suggest` gains regional video candidates + verification rows.
- **Admin AI Quality Review** reads/updates `video_verification_results` (admin-only UPDATE).

**Migrations (2 upstream, 2 UAT fixups in `~/banking-sb/fixups/`)**
- `20261017130000_topic_content_persistence_repair` — upstream.
- `20261017143000_admin_topic_student_content_visibility` — **fixup**: upstream regex
  `source_module_id ~* '…'` fails on UAT (`uuid ~* unknown`; column is uuid here) → `coalesce(source_module_id, id)`.
  Also keeps the pre-existing direct `private.user_can_access_module(auth.uid(), module_id)` path: upstream
  dropped it and the rehearsal showed 10 candidates losing 9 topics each (topics whose module has no
  `admin_modules` row). After fixup: identical counts for all 89 candidates.
- `20261017150000_ai_topic_video_quality_pipeline` — **fixup**: `ai_generation_runs` already existed (09-25
  shape: actor_id, approval_status, quality_status…) so `create table if not exists` skipped it; fixup adds
  the 13 columns generate-topics inserts (maker_provider, status, response_payload, evidence_pack_id…).
  Without it every audit insert fails (warn only). Note: new policy lets trainers/teachers read all runs.
- `20261017160000_ai_quality_review_controls` — upstream (`quality_score` already numeric → skipped).
- Archived in DB-Scripts *Banking Supabase to Postgres* `20261017T12290{1..4}Z__banking_*` (UAT applied, PROD pending).

**Verification:** rolled-back rehearsal `~/banking-checks/dryrun_20261017.sh` (per-candidate topic visibility
before/after, core reads per role, candidate writes blocked, service audit insert). Live: new
`node ~/banking-checks/topicgen.cjs` (anon reads of 4 new tables = 0 rows; admin generate-topics 200 with
LLM topics, audit row with evidence pack; test rows deleted), journeytabs 6/6, admin login 5/5,
swotadmin, admin crawl 43/43, Coding Challenges, Save Module, Tier search, candidate/trainer/admin homes —
zero page/API errors. Snapshot: `~/banking-sb/snapshots/20261017T121846Z`.

## 2026-10-18 — UAT `38f9f6f2`: live sessions scoped to mapped learners, evidence-grounded video quizzes

UAT advanced `0ec72eb8` → `38f9f6f2` (6 commits: bulk video discovery persistence, student YouTube discovery
fallback, Admin journey transactions/analytics, Trainer lazy-route retry (`lazyWithRetry`), student AI video
schema compatibility, live sessions scoped to mapped learners). No new `VITE_*` gates, lockfile unchanged, no
direct-provider calls added.

**Current behavior**
- **Live sessions (candidate):** visible only if admin, own trainer/requester, the candidate has a non-declined
  RSVP, or the session is `scheduled`/`live`, not a `candidate_request`, and for a module the candidate can access
  (`public.live_session_module_visible` → `private.user_can_access_module`). On UAT 76/89 candidates went from
  2 sessions to 1. **Non-admin trainers now see only their own sessions** (before: all scheduled sessions).
- **Video quizzes:** `video_lessons` / `video_lesson_questions` carry caption/evidence/checker fields; MCQs are
  grounded in an evidence quote (`_shared/video-evidence.ts`); learners get key takeaways.

**Migrations:** `20261017120000_video_quiz_evidence_grounding` (upstream, additive; dated before the 10-17
files but new to UAT). `20261018120000_live_session_module_visibility` — **UAT fixup**: upstream's policy
reads `live_session_rsvps` inline while the rsvps policies read `module_live_sessions` →
`infinite recursion detected in policy` on every read (caught in rehearsal; would have 500'd Live Sessions for
all users). Own-RSVP check moved to SECURITY DEFINER `private.has_live_session_rsvp(session_id, user_id)`.
Both functions: anon EXECUTE false, authenticated true (verified after 03_grants). Archived in DB-Scripts
`20261018T03390{1,2}Z__banking_*` (UAT applied, PROD pending). **Upstream / hosted needs the same fix.**

**Verification:** `~/banking-checks/dryrun_20261018.sh` (reads both live tables as candidate/trainer/admin,
per-candidate session counts). Live: journeytabs 6/6 (now also fails on API ≥400), admin login 5/5, swotadmin,
admin crawl 43/43, Coding Challenges, Save Module, Tier search, candidate/trainer/admin homes — zero page/API
errors. Snapshot: `~/banking-sb/snapshots/20261018T033155Z`.

## 2026-10-18 — UAT `cc737e85`: quiz module-access guard, Robo Play voice diagnostics

UAT advanced `38f9f6f2` → `cc737e85` (2 commits). No migrations, `VITE_*` gates, lockfile or provider changes.
- **AI Quiz (`/quiz`, `ai-quiz`):** candidates can only pick and generate quizzes for modules assigned to them
  (`useAssignedModuleIds`); admins see all published modules. The function now rejects a non-UUID `moduleId`
  (400), inactive accounts (`coach_actor_active_v1` → 403), and modules the caller cannot access
  (`user_can_access_module` → 403); a failed check returns 503 rather than generating. Both RPCs exist on UAT
  and are executable by `authenticated` (verified before deploy).
- **Robo Play voice (`sim-voice`):** failures log a request id + action + DB error shape; missing voice tables/
  columns return "Robo Play voice storage is not ready…" instead of a generic error.

**Verification:** `ai-quiz` with a malformed module id → 400; candidate `/quiz` loads with no page/API errors;
journeytabs 6/6, admin login 5/5, swotadmin, admin crawl 43/43, Coding Challenges, Save Module, Tier search,
candidate/trainer/admin homes — zero errors. Snapshot: `~/banking-sb/snapshots/20261018T055952Z`.

## 2026-10-18 — UAT `02e792ec`: Simulations / Robo Play visible to candidates, video quiz 422, YouTube quota

UAT advanced `cc737e85` → `02e792ec` (4 commits: `0a1122dd` Robo Play sprints 1–6, `d9e947f3` Robo Play plan
entitlement, `1652bb95`, `02e792ec`). Migrations applied: `20261018120000_robo_sprint1_voice_usage_events`,
`20261018130000_robo_sprints5_6_pilot_feedback`, `20261018140000_private_schema_service_role_access`
(rehearsed in BEGIN…ROLLBACK first, `~/banking-checks/dryrun_20261018c.sh`). No `VITE_*` or lockfile changes.

- **Published Simulations / Robo Play were empty for every non-staff candidate.** Two causes, both in
  `sim-attempt` → `_shared/sim-core.ts`:
  1. The plan check selected `profiles.plan_tier`, which does not exist on UAT → PostgREST 42703 → profile read
     as `free` → `module_simulation` is off for free → `{items: []}`. It now selects `*` (keeps the
     highest-of-two-projections rule from `d9e947f3`) and throws if the profile read fails.
  2. Edge functions run as `service_role`, but schema `private` was granted only to `authenticated`, so
     `user_can_access_module` (a wrapper over `private.user_can_access_module`) failed with "permission denied
     for schema private" and every open pack was skipped. Migration `20261018140000` grants `service_role`
     USAGE on `private` + EXECUTE on its functions. This also unblocks any other edge function that calls a
     private-backed RPC with the service client. **PROD (hosted) likely has the same gap — pending.**
- **Video "Generate quiz" returned 422** ("No captions or usable description"): `generate-lesson-video-quiz`
  read the YouTube key from env only, but on UAT it lives in Admin → LLM Settings (`llm_provider_configs`,
  provider `youtube`), so the description was never fetched (YouTube's `timedtext` caption list returns empty,
  so description is the only evidence). New `_shared/youtube-key.ts` (`getYouTubeApiKey`, LLM Settings first,
  env fallback) is now used by `generate-lesson-video-quiz`, `generate-video-mcqs`, `ai-coach` (video mode) and
  `generate-section-content`. `InModuleVideoQuiz` shows the function's reason instead of the generic non-2xx toast.
- **"Fetch more videos" burned the YouTube quota and showed the wrong error.** The Banking Google project's
  `search.list` limit is **99 calls/day** (`defaultSearchListPerDayPerProject`). `ai-video-suggest` ran 3 queries
  × 9 region tiers (27 searches) per request, and its quota `throw` was caught by the loop's own `catch`, so users
  saw "No YouTube videos found for generated queries". It now stops at the first tier with candidates, caps a
  request at 8 search calls (`MAX_SEARCH_CALLS`, `ponytail:` note), logs `YouTube search calls used: N`, and
  returns "YouTube daily search limit reached… resets at midnight Pacific" when exhausted. More than ~12–30
  fetches/day needs a Google quota increase.

**Verification:** `sim-attempt list` for QA candidate `9302610153` (advanced) 0 → 3 items; Jev goal runs on
UAT PASS for My Simulations (`20261018T074006Z-3bc9828f`) and My Robo Play (`20261018T074006Z-8fb17fcd`), each
showing 3 packs (baseline run `20261018T065433Z-6fe374a1` showed "No simulations are published…").
`generate-lesson-video-quiz` for `aMJtqLjAJ24` → HTTP 200, 10 questions, evidence = description (~110 s).
`ai-video-suggest` with exhausted quota → 1 search call + the quota message. journeytabs 6/6, admin crawl and
candidate/trainer/admin logins — zero errors. Snapshots: `~/banking-sb/snapshots/20261018T073432Z`,
`20261018T073651Z`.

## 2026-10-18 — UAT `a25cd761`: Robo Play "malformed JSON" and "More YouTube videos" always failing

UAT advanced `02e792ec` → `a25cd761` (1 commit, functions only; no migrations, `VITE_*` or lockfile changes).

- **Robo Play / simulation turns failed with "The AI returned malformed JSON".** UAT has no `LOVABLE_API_KEY`, so
  `_shared/sim-ai.ts` uses the configured providers. Of those only **Gemini `gemini-3.6-flash`** works (openai `gpt-5`
  rejected every call, nvidia 403, deepseek 401, glm 401 — keys to fix in Admin → LLM Settings). It is a thinking
  model: hidden reasoning counts against `max_tokens`, and at 320 the persona reply stopped mid-JSON
  (`finish_reason: length`, ~12 visible tokens). Configured-path caps are now persona 2048 / default 4096 /
  debrief 6000 (the Lovable path keeps 320/1200/1800). `_shared/llm.ts` sends `max_completion_tokens` instead of
  `max_tokens` to the `openai` provider, so the gpt-5 fallback works (verified directly: ~12 s, valid JSON).
- **"More YouTube videos" → "No public, embeddable, topic-relevant videos passed verification".** Search worked,
  but `checkVideoEvidence` (`_shared/topic-quality.ts`) demanded ~50% of up to 32 concepts from the topic's whole
  content paragraph in a video's title + description; every candidate scored 7–36 vs a 45 pass mark. Without a
  transcript it now scores against the topic **title's** concepts and passes at **30** (`ponytail:` note) —
  calibrated on 516 audited linked videos: passes 86% of directly relevant ones, but also ~half of loosely related
  ones (token overlap is weak; captions or an LLM judge are the upgrade).

**Verification:** `sim-attempt` turns (2) and `sim-voice` turns (3, the screenshot's "yes", "yes" sequence) as QA
candidate `9302610153` all returned in-character replies in ~4–6 s; `llm_usage_logs` since deploy: 6 success,
0 error. Jev on the Robo Play text screen: persona replied (Jev then mis-navigated → BLOCKED, run
`20261018T090201Z-be01c4b5`, shot `005`). `ai-video-suggest` (bulk) for "Wealth Management RM sales mindset:
Regulatory and Risk Context" returned 2 videos with 3 search calls. Vitest (sim/robo/llm/video/topic/module):
696 pass. journeytabs 6/6, admin crawl 43/43. Snapshot: `~/banking-sb/snapshots/20261018T090015Z`.

## 2026-10-19 — UAT `7566a275`: traceable YouTube transcript evidence, admin-only video QA, Robo Play hardening

UAT advanced `a25cd761` → `7566a275` (7 commits: Robo Play voice turns + JSON output hardening (`_shared/sim-json.ts`),
simulation auth/logout fixes, topic-grounded AI video generation, traceable YouTube transcript evidence, media
verification hardening, admin video QA aligned to the scoped payload). No `VITE_*` gates, lockfile unchanged.

**Current behavior**
- **Video discovery audit** (`ai-video-suggest`) writes evidence pack + run + candidates + checks atomically through
  `public.persist_video_quality_audit(jsonb)` (SECURITY DEFINER; EXECUTE only `service_role` — anon/authenticated false,
  verified after 03_grants).
- **AI-quality tables are admin/super_admin only:** `topic_evidence_packs`, `video_candidates`,
  `video_verification_results` (trainers/teachers lost read; on 10-17 they could read). `ai_generation_runs`: admins
  all, other users only their own rows (09-25 actor policy still present on UAT).
- **Transcript evidence:** new `save-video-transcript` function (verify_jwt) stores staff-attested / owner-OAuth /
  caption-file transcripts in `video_transcript_evidence` (service-role only; no RLS policies → 0 rows to clients).
- **compose-video** is a stub that returns 501 until a real long-form assembly worker exists (fake assembly disabled).
- **Known gap (pre-existing, not introduced here): `generate-video` has no caller check.** It validates the body and
  then uses the service client + paid providers; the anon key passes the gateway JWT check (see the `main` overlay
  comment), so an anonymous caller with a valid `topicId` can start a paid generation. Needs a staff check
  (`is_curriculum_staff`) upstream or as an overlay.

**Migrations (both upstream verbatim):** `20261018160000_video_quality_audit_atomic_and_scoped` — its guarded
`review_status` CHECK is skipped on UAT because the same-named 10-17 constraint exists (`…deferred`, which is what the
app uses). `20261018170000_traceable_youtube_transcripts`. Archived in DB-Scripts `20261019T02310{1,2}Z__banking_*`.

**Verification:** rolled-back `~/banking-checks/dryrun_20261019.sh` (RPC as service_role, candidate RPC blocked, role
reads of quality/transcript tables, admin review update). Live: anon REST reads of the new tables = `[]`, anon
`save-video-transcript` 401; journeytabs 6/6, admin login 5/5, swotadmin, admin crawl 43/43, Coding Challenges, Save
Module, Tier search, candidate/trainer/admin homes — zero page/API errors. Snapshot `~/banking-sb/snapshots/20261019T022330Z`.

## 2026-10-19 — UAT `2b2d6411`: "More YouTube videos" checker-agent rescue

UAT advanced `7566a275` → `2b2d6411` (3 commits, `ai-video-suggest` only; no migrations).

- **Why it failed again after `a25cd761`:** `8ae6dab8` ("Harden media verification", 2026-10-18 19:02 IST) set
  `relevanceGating: true` in `checkYouTubeVideo`, so the validator's "Topic relevance score N is below 35" gate (off since
  2026-09-07) stacked on the topic-evidence gate. Long editorial topic titles ("Wealth Management RM sales mindset: Core
  Processes and Workflows") dilute both word-overlap scores: all 49 candidates in the 4 fetches of 2026-10-19 were rejected
  (11–34). The message became "No public, embeddable, topic-relevant videos passed metadata verification".
- **Fix:** both gates stay. When they reject everything, the checker agent (`llmPickVideo`, configured providers via
  `installLlmFetchFallback` — Gemini on UAT) reviews the top 5 playable, hallucination-flag-free candidates against the
  topic title, learning outcome and a 1,200-char content excerpt using `RESCUE_CHECKER_SYSTEM_PROMPT` (useful
  *supplementary* video; partial coverage OK; promos, motivation and personal-finance tips rejected). Approved →
  `verification.checker = "llm-video-quality-checker-rescue"`; otherwise the rejection stands. Logged as
  `Video checker rescue: N candidates; approved=…`. The normal path and `AI_VIDEO_LLM_CHECKER` are unchanged; the original
  strict prompt is `CHECKER_SYSTEM_PROMPT`.
- **Replay evidence (real 10-18/19 pools, Gemini, 3 runs each):** Foundations pool → approved "Wealth Management Industry
  Overview" 3/3; Core Processes pool → approved "Selling to Wealthy Clients"/"Industry Overview" 3/3; pool of negotiation /
  CRM / money-habits / myths videos → rejected 3/3. The strict prompt rejected all three pools.
- **Live:** the rescue ran on UAT (3 candidates, correctly rejected as negotiation/CRM content) before the YouTube quota ran
  out. **YouTube quota:** key in LLM Settings now belongs to project `641154247196` (changed 2026-10-18 08:31 UTC);
  122 fetches / 185 search calls since the 10-18 reset exhausted both projects' 99/day `search.list` allowance.

Vitest (video/youtube/sim/robo/llm/topic/module, 737 tests): only the 3 failures that also fail on `7566a275`
(`curriculumTaxonomyVideoGeneration` bulk discovery, 2× `roboHandsFree`). journeytabs 6/6. Snapshot
`~/banking-sb/snapshots/20261019T030237Z`.

## 2026-10-19 — UAT `a48ed9d8`: 12–15 minute AI lesson videos failed (storyboard timeout, short script)

UAT advanced `2b2d6411` → `a48ed9d8` (functions only; no migrations). Admin → Modules → AI Generated Videos at
"12-15 minutes" failed with 422 for both Wealth Management topics:
- **"Storyboard quality gate failed"**: the whole 15-minute storyboard was one LLM call. Gemini (only live provider)
  hit the 45 s per-provider timeout, OpenAI `gpt-5` rejected `temperature: 0.2`, so the deterministic fallback
  storyboard was used and the gate rejected it.
- **"Narration came out at 626s; needs 720–900s"**: the prompt assumed 2.4 words/s (ElevenLabs actually ~2.0,
  measured on 4 lessons) and the model writes 15–40% fewer words than asked; the check ran only after narration
  had been paid for.

Now (`generate-video/index.ts`): an outline call (`sceneCount = max(4, round(targetSeconds/75))`) then parallel
part calls of ~`STORYBOARD_PART_SECONDS` = 240 s each; `NARRATION_WORDS_PER_SECOND = 2.0`; one retry when a
storyboard reply is not valid JSON; the script is word-checked against the band minimum (×0.95) **before**
narration ("Script is N words; about M are needed…"). `_shared/llm.ts` drops `temperature`/`top_p` for OpenAI
reasoning models (`gpt-5*`, `o*`). Logged: `video storyboard: <source> <scenes> scenes, <words> words for <s> s`.

**Verification:** UAT rehearsal of the storyboard steps (Gemini, real topic content, 900 s): Foundations 1,667 words
(~834 s), Core Processes 1,674 words (~837 s); outline 12–15 s, 4 parallel parts ~15–16 s. Live: function boots
(400 on invalid duration), journeytabs 6/6, admin crawl 43/43. A full paid generation (ElevenLabs + Runway) was
not run. Visuals are still one 8 s provider clip looping under the narration. Snapshot `20261019T143739Z`.

## 2026-10-20 — UAT `6f17f057`: every route lazy-loads with stale-chunk recovery (frontend only)

UAT advanced `a48ed9d8` → `6f17f057` (8 Lovable commits). No migrations, functions, `VITE_*` gates or
`package-lock.json` changes (`bun.lock` only; not used by the UAT build).
- **Routes:** `src/App.tsx` and the journey pages (Admin, Trainer, Institute, TechStudent, PilFeatureMerge) now
  wrap every lazy page in `lazyWithRetry` (generic over the component type; route key defaults to the current
  path). After a deploy, a browser still on the old manifest that hits a missing chunk reloads once per route
  (sessionStorage `lazy-chunk-retry:<route>`), and only errors if the retry fails too.
- `types.ts` gains `trainer_can_access_admin_module` / `trainer_can_access_module` RPC types; both functions
  already exist on UAT and are executable by `authenticated` (no frontend caller yet).

**Verification:** journeytabs 6/6, admin login 5/5, swotadmin, admin crawl 43/43, Coding Challenges, Save Module,
Tier search, candidate/trainer/admin homes — zero page/API errors. Snapshot `~/banking-sb/snapshots/20261020T164405Z`.

## 2026-10-21 — UAT `12371cef`: trainer "Assign module" (Module Builder) blocked by RLS

UAT advanced `6f17f057` → `12371cef` (frontend only; no migrations, functions unchanged). Trainer Portal → Module
Builder → **Assign to students → Assign module** failed for every trainer with *"new row violates row-level security
policy for table user_module_access"*. `TrainerModuleCatalog.assignModule` inserted `{user_id, module_id}` without
`granted_by` (NOT NULL, no default); the only trainer write policy, **"Staff manage mapped student access"**, requires
`granted_by = auth.uid()` and `private.staff_can_manage_student(auth.uid(), user_id)`. Rows now carry
`granted_by: user.id` (session-expired guard added). Admin mapping screens already set it.

Notes: students without a sign-in account (`students.user_id` null, shown as "no login yet") are skipped by design.
Of the 71 `admin_modules`, 4 have no same-id row in `modules` (AUTOMOBILE INSURANCE, Banking app testing,
AQM - Full Stack Developer (Tech), AQM - Retail Banking (Domain)); `user_module_access.module_id` references
`modules(id)`, so direct per-student assignment of those 4 would fail on the FK until they are mirrored.

**Verification:** as trainer Mahalakshmi Prakash in a rolled-back transaction — insert without `granted_by` → the RLS
error; with it → accepted. Served chunk `TrainerModuleCatalog-*.js` contains `granted_by`; journeytabs 6/6, admin crawl
43/43; `tsc` 0 errors. Snapshot `~/banking-sb/snapshots/20261021T051722Z`.

## 2026-10-21 — UAT `7cd1d8ac`: `feature/ffmpeg-long-form-render` merged into main (25 commits, 9 migrations)

Merged by us on request (GitHub main `12371cef` + branch `11559c7f` → merge `7cd1d8ac`). Conflicts: `src/App.tsx`,
`src/pages/TrainerJourney.tsx` (kept main's `lazyWithRetry` on every route + branch route keys `admin`/`admin-journey`
and its new `ModulesAndVideos` import) and `supabase/functions/ai-video-suggest/index.ts` (kept main's checker/rescue
prompts + branch `moduleDescription` param). Pre-push: vite build OK, 44/44 tests in 7 key suites.
`subscription/validity-v1` was NOT merged (582 commits behind main; needs a rebase first).

**What the release adds:** long-form video render jobs (`topic_video_render_jobs`; FFmpeg worker via
`VIDEO_RENDER_WORKER_URL/TOKEN` — **not configured on UAT**, so long-form assembly stays off), YouTube discovery
operations (quota/day + cache + bulk jobs, `manage-youtube-discovery-settings`, `video-bulk-jobs`), YouTube OAuth
caption import (`youtube-oauth-start/-callback`, `youtube-caption-import` — **no OAuth client on UAT**; status call
returns 503 "not configured", the settings card shows not connected; `youtube-oauth-callback` is `verify_jwt=false`
upstream but stays blocked by the UAT gateway allowlist until OAuth is configured), curriculum-grounded topic
generation, scoped trainer curriculum assessments + attempts, spreadsheet module resources (xls/xlsx/csv),
`job_roles.competencies`, tenant-scoped `public_payment_instructions` (learners read active global/own-institute
rows; admin-only writes).

**Access model change (`20261020120000_trainer_module_content_scope`):** `admin_modules`, `topics`,
`admin_module_topics`, `module_questions`, `module_resources(_chunks)`, `topic_videos`, `admin_section_content` and the
`module-resources` storage bucket now use `can_manage_module_content` (admin/taxonomy_editor, or trainer/teacher with
`trainer_can_access_module`/`trainer_can_access_admin_module`) and `module_content_visible_to` (adds learner access via
`private.user_can_access_module` on the module id or the admin module's source module). **Non-admin trainers now see
only modules they manage** (UAT sample trainer: admin_modules 71→63, topics 851→630, admin_module_topics 597→544).
Candidate visibility unchanged in the sample (direct module_id path kept upstream). The 10-17 UAT fixup on the
`admin_module_topics` read policy is superseded. Old open `USING (true)` policies on `curriculum_assessments` removed.

**UAT fixup:** `20261020120000` — `module_resources`/`module_resource_chunks`/`topic_videos.module_id` are TEXT on UAT →
wrapped in new `private.uuid_or_null(text)`; `admin_section_content.module_id` is UUID on UAT while section helpers take
text → `module_id::text`. Upstream verbatim failed with `function can_manage_module_content(uuid, text) does not exist`.
The two in-place edits to applied migrations (10-14, 10-15) only add uuid/text casts UAT already had via fixups.

**Performance regression (open):** per-row RLS helpers are slower. Candidate Modules tab: `topics?select=*` 3.6 s,
`admin_module_topics?select=*` 2.5 s (was ~1.2 s for topic RLS on 10-08). Rehearsal sample (count of 4 content tables):
candidate 1.7 s → 4.9 s, trainer 0.24 s → 6.5 s. A full per-user rehearsal over 89 candidates + trainers did not finish
in 10 min and was cancelled (it holds DDL locks — **cap rehearsal statements with `statement_timeout`**).

**Verification:** live role probes (anon reads 0 on all new tables, no anon EXECUTE on new helpers, candidate cannot
write admin_modules/topics/curriculum_assessments/payment instructions, trainer cannot update unmanaged modules or
payment rows); journeytabs 6/6, admin login 5/5, swotadmin, admin crawl 42/43 (only the expected OAuth-status 503),
Coding Challenges, Save Module, Tier search, candidate/trainer/admin homes. DB-Scripts `20261021T13000{1..9}Z__banking_*`.
Snapshot `~/banking-sb/snapshots/20261021T125057Z`. Scripts: `~/banking-checks/dryrun_20261021.sh`, `timing_20261021.sh`.

## 2026-10-22 — UAT `f9457aee`: ffmpeg branch round 2 (12 commits, 3 migrations) — assessments follow module assignment

Merged by us (main `7cd1d8ac` + branch `1291bf40`); conflict only in `TechStudentJourney.tsx` (kept main's
`lazyWithRetry`, dropped `AIPlayground` which the branch removed). Pre-push: build OK, 78/78 tests in 16 suites.

**Behaviour change — candidate assessment visibility (`private.user_can_access_assessment`):** published assessments
are visible when the candidate has an explicit override, OR one of the assessment's `selected_modules` / `module_id`
is accessible via `private.user_can_access_module`, OR the assessment is **unlinked** (no modules) and
`metadata.student_visible = true`. `student_visible` no longer opens a module-linked assessment to everyone.
UAT: visible candidate×assessment pairs **2,706 → 1,003**; all 89 candidates lost some (e.g. NISM VIII, Test Engineer
series, Functional Tester); none gained. Deployed as upstream intends (two branch commits + e2e
`student-mapped-assessments`); the 10-07 reverse fix is superseded. To restore old behaviour, re-add the
`student_visible` branch for linked assessments in that function.

Other: student analytics report exports, assessment report list/role-access fixes, SWOT intervention labels, single
student AI chat entry (playground removed), BankReady assistant branding removed, student report tables
(`project_assignments`, `student_project_progress`, `proctoring_*`) now owner(auth uid or students.id)/admin only via
`private.current_user_owns_student_id(text)` — trainers no longer read candidates' proctoring rows directly.

**UAT fixup:** `20261021160000_student_report_identity_access` — `project_assignments.student_id` and
`student_project_progress.student_id` are UUID on UAT → `student_id::text`. DB-Scripts `20261022T*__banking_*` (3 files).

**Verification:** rehearsal `~/banking-checks/dryrun_20261022.sh`; journeytabs 6/6, admin login 5/5, swotadmin,
swot.cjs isolation, admin crawl 42/43 (expected OAuth-status 503), Coding Challenges, Save Module, Tier search,
candidate/trainer/admin homes. Snapshot `~/banking-sb/snapshots/20261022T004338Z`.

## 2026-10-22 (later) — UAT `d048aa34`: ffmpeg branch round 3 (6 commits, frontend only)

Merged by us (main `f9457aee` + branch `fc13a267`). Conflict only in `TrainerJourney.tsx`: the branch re-formatted the
lazy imports as plain multi-line `lazy(...)`; kept main's `lazyWithRetry` block. Build OK, 39/39 tests in 7 suites.
No migrations, functions, gates, lockfile or config changes.

**What changed:** learning reminders load correctly with right category counts; trainer dashboard metrics wired to
real data; dashboard metric scope/calculation fixes (+ Playwright `tests/e2e/dashboard-metrics.spec.ts`, new
`npm run test:e2e:dashboard-metrics`); "Modules Coach" removed from student modules; student curriculum content
visibility fix.

**Verification:** journeytabs 6/6, admin login 5/5, swotadmin, admin crawl 42/43 (expected OAuth-status 503), Coding
Challenges, Save Module, Tier search, candidate/trainer/admin homes — zero page/API errors.
Snapshot `~/banking-sb/snapshots/20261022T033500Z`. PilVidya: no new upstream commits (stays `9c3faa77`).

## 2026-10-22 — migration completeness check on UAT `d048aa34`

`~/banking-sb/reconcile.py` (expected objects from all 344 migration files vs live catalog). **Tool fix:** it read
`information_schema.columns/views` as `banking_owner`, which hides objects that role holds no privileges on (every table
the deploy creates as `postgres`) → 1,238 false "missing". Now reads `pg_attribute`/`pg_class`. Result: **159 missing,
all explained — no migration left unapplied:**
- 110 policies — upstream policies UAT deliberately replaced or skipped (e.g. `20260911130000_security_rls_fix` 18,
  `20260928150000_fix_profiles_rls_recursion` 10 — skipped pending team decision, USING(true) on profiles).
- `20260923000000_repair_missing_modules` (4 tables + columns) — **skipped by design**: PilVidya file leaked into this
  repo, invalid SQL, references PilVidya tables; nothing in Banking uses them.
- `staff_can_manage_student` — lives at `private.staff_can_manage_student(_staff, _student_user, _student_id)` (10-07 fixup);
  the 2 policies using it resolve.
- 11 columns from 07-10/08-11 files whose tables pre-existed with another shape; 3 timestamp/created_by columns on
  live_session_rsvps / module_prerequisites / curriculum_videos (fixup-shaped tables; no frontend reference);
  1 `pg_temp` helper (never persistent).
- drizzle: 0001/0002/0003/0005 applied; 0000 superseded by UAT's scoped `storage_assessment_uploads_*` policies; 0004's
  anon grant on `domains` superseded by 0005 (03_grants re-adds the anon GRANT each deploy, but the only read policy is
  `TO authenticated` → anon reads 0 rows).
- 38 tables have RLS on with zero policies — all service-role-only internals (`coach_*`, `swot_*` internals,
  `youtube_*`, `video_bulk_*`, `video_transcript_evidence`); none is read directly by `src/`.

## 2026-10-22 (later) — UAT `6e0757f5`: candidate Assessments page no longer empty (hidden track filter removed)

**Symptom (reported):** candidate Himanshu Bhagat (enterprise, tracks {domain,tech}, `profiles.preferred_journey_track =
tech`) saw "No assessments available yet" although the DB granted 18 (all Domain-track). **Cause:** `5df5e0ef` (deployed in
`f9457aee`) added a hidden filter in `src/pages/Assessments.tsx` that dropped every assessment not matching the profile's
preferred track, before the Track dropdown — so choosing "Domain" could not bring them back. 5 candidates prefer Tech
(would see nothing; only 2 published Tech assessments exist), 13 prefer Domain (lost the Tech ones).
**Fix (upstream `e564b3c6`):** `filterAssessmentsByStudentModuleAccess` only; the preferred track is no longer applied or
pre-selected — the Track dropdown defaults to **All Tracks** and is an optional filter.

**Still stricter than the DB (open, upstream decision):** the page's client-side module check
(`useAssignedModuleIds` + `expandAssignedModuleAliases`) only counts direct `user_module_access` + group mappings, while
`private.user_can_access_assessment` also grants via other module-access paths. Himanshu: DB 18, page 5.

**Verification:** new `node ~/banking-checks/assesslist.cjs` (candidate /assessments lists cards, Track = All Tracks, no
errors); journeytabs 6/6, admin login 5/5, swotadmin, admin crawl 42/43 (expected OAuth 503), Coding Challenges, Save Module,
Tier search, all home pages. Snapshot `~/banking-sb/snapshots/20261022T044328Z`.

## 2026-10-22 (eve) — UAT `5fc5b48f`: readable labels, trainer module titles, topic video batches (ffmpeg round 4)

main `62ae1d0c` (2 commits pushed by the team: readable module/student labels, module titles in trainer progress) +
merge of `feature/ffmpeg-long-form-render` `e1d1ec50` (4 commits: trainer module topic video batches, bulk video discovery
limited to confirmed batches, admin AI topic-generation diagnostics). Clean merge, build OK, 28/28 tests in 7 suites.
No migrations. `video-bulk-jobs` now allows **trainers** (was admin-only) but only for modules they can access
(`trainer can access` check per selected module → 403); anon → 401.

**Open regression (upstream `62ae1d0c`):** `ActivityTimeline`, `StudentOverview`, `StudentProfilePage`,
`LearningAnalytics` query `modules?select=id,title,source_module_id`; **`modules.source_module_id` does not exist**
(only `admin_modules` has it; no migration adds it) → 400 on UAT, so labels for `modules`-table modules fall back to ids.
Pages still render. Fix = select `id,title` from `modules` (or add the column via a migration if hosted relies on it).

**Verification:** assesslist ✓ (All Tracks), journeytabs 5/6 (playground: the 400 above, repeatable), admin login 5/5,
swotadmin, admin crawl 42/43 (expected OAuth 503), Coding Challenges, Save Module, Tier search, all home pages.
Snapshot `~/banking-sb/snapshots/20261022T115213Z`.

## 2026-10-22 (night) — UAT `37ef5db4`: modules label query fixed; admin topic generation diagnosed

**`37ef5db4` (deployed, pushed to main):** `ActivityTimeline`, `StudentOverview`, `StudentProfilePage`, `LearningAnalytics`
now select `id,title` from `modules` (the column `source_module_id` exists only on `admin_modules`) → the 400 is gone;
journeytabs 6/6 again, admin login 5/5, assessesslist ✓. Snapshot `~/banking-sb/snapshots/20261022T122751Z`.

**Admin → Modules → "Generate Topics with AI" → "The configured AI providers did not return grounded content" (503).**
`ai-content` (`type: module_topics`) tries providers in `llm_provider_configs` order with a fixed **45 s per-provider
deadline** (`LLM_PROVIDER_TIMEOUT_MS`, `_shared/llm.ts`). On UAT: `lovable` has no key; the `litellm` (central gateway) row was
scoped to `bulk-export-worker` only; `openai` gpt-5 and `gemini` gemini-3.6-flash time out; `nvidia`/`deepseek`/`glm` keys invalid.
A grounded 3-8 topic answer is ~18k completion tokens: the gateway (gemini-2.5-flash) **completed it in 85 s** (spend log
status success) after the function had already aborted at 45 s.
- **Applied (config, live):** new `llm_provider_configs` row `provider=litellm, application_feature='ai-content', priority 1`
  (copy of the bulk-export-worker row) → ai-content now goes through the gateway first.
- **Prepared, NOT deployed:** `373d1441` on UAT-checkout branch `fix/ai-content-provider-timeout` — per-feature deadline
  (`ai-content` 150 s; default 45 s; worker limit 300 s) + `src/test/llmProviderTimeout.test.ts`. Needed for long sources
  (e.g. "Test Engineer - Product-Level Knowledge - Life Insurance", 4,821-char description).
- **Not a bug:** modules with a very thin source (e.g. Credit Card, 52-char description, no uploads) make the grounded prompt
  return fewer than 3 topics → 422 "empty or unrecognized content response". Add a real description or upload curriculum.
- Probe: `node ~/banking-checks/topicsgen.cjs <moduleId> "<description>" "<title>"` (read-only).

## 2026-10-22 (night, later) — UAT `a61c7014`: Admin "Generate Topics with AI" now completes (4 fixes)

Pushed to main and deployed, verified on the Life Insurance module (`modules` b898449f…, 4,821-char source):
1. **Routing (config):** `llm_provider_configs` row `litellm` / `application_feature='ai-content'` / `gemini-2.5-flash` /
   priority 1 → ai-content goes through the central LiteLLM gateway first (gemini-3.8-flash tried: no better, 149 s — reverted).
2. **`373d1441` per-feature provider deadline:** `providerTimeoutMs("ai-content")` = 150 s (default 45 s unchanged). A
   grounded 3-8 topic set is ~18k completion tokens = 60-90 s; the old 45 s aborted successful gateway calls.
3. **`bf08e20f` case-study headings:** the validator (`ensureRichContent`) requires `### Case Study 1: Foundation`,
   `### Case Study 2: Workplace Application`, `### Case Study 3: Exception and Risk` but no prompt said so → prompts and
   tool schema now state the exact headings; label check accepts "&".
4. **`ae5bd9d8` retry once:** a rejected response (model truncates one topic's content mid-sentence — observed 579 words,
   one case study) is retried once while < 140 s elapsed, so two calls fit the 300 s worker. 502/503 still return at once.
5. **`a61c7014` title rule:** `checkGeneratedModuleTopics` rejects the whole set unless every title has >60% (and ≥2) of its
   words verbatim in the source; the prompt only said "specific" → prompt + schema now state the rule.

**Result:** 0/5 → 2/3 successful runs; successful runs take 160-200 s when the retry is needed (UI spinner the whole time).
Remaining failure mode: the model truncates a topic on both attempts → 422 "AI provider returned an empty or unrecognized
content response"; clicking Generate again usually works. Thin sources (e.g. Credit Card, 52 chars, no uploads) still
yield <3 topics → add a real description or upload curriculum. Probe: `node ~/banking-checks/topicsgen.cjs <id> "<desc>" "<title>"`.
`llmFallbackCoverage` has 1 pre-existing failure on main (expects an older prompt phrase).

## 2026-10-22 (late) — UAT `8a915934`: ffmpeg round 5 merged; topic generation now 3/3

`45377ff7` merges branch `4d50d7b9` (module generation + OAuth setup diagnostics): shared
`_shared/module-content-quality.ts` `checkRichLearningContent` replaces ai-content's local case-study check (accepts any
`##`–`######` heading, with or without the "Case Study" prefix, exactly one of each required type); we carried the "&"→"and"
tolerance into it. Provider failures now return per-provider diagnostics (`summarizeProviderFailures`); LLM Settings and
YouTube Discovery settings show OAuth setup diagnostics, and `youtube-oauth-start` no longer 503s the admin LLM page
(admin crawl 43/43 again). Kept from main: 150 s ai-content deadline, retry-once, heading + title prompt rules.

`8a915934`: after the merge 4/4 attempts failed "three to eight topics" — the Life Insurance source has 10 numbered sections and
the model returned >8. The `topics` tool schema now has `minItems: 3, maxItems: 8` and the prompt says to merge related sections
when the source lists more than 8. **Result: 3/3 Life Insurance runs succeed in ~68 s, first attempt, no retries.**

**Verification:** topicsgen 3/3; journeytabs 6/6, admin login 5/5, assesslist ✓, swotadmin ✓, admin crawl **43/43**, Coding
Challenges, Save Module, Tier search. 31/31 tests in the touched suites (incl. `llmFallbackCoverage`, fixed on the branch).
Snapshot `~/banking-sb/snapshots/20261022T152444Z`.

## 2026-10-22 (night) — UAT `0b5521b0`: YouTube bulk jobs pause on quota exhaustion (ffmpeg round 6)

Merged branch `e2548bf4` (2 commits: pause YouTube bulk jobs on quota exhaustion; harden Admin and Trainer bulk YouTube
generation). Clean merge, build OK, 30/30 tests. Migration `20261022130000_youtube_bulk_quota_pause` (applied, rehearsed in
rollback first) replaces `public.claim_video_bulk_job_item(uuid)`: failed items are **never auto-reclaimed** (only the explicit
retry action re-queues them), so a provider/quota failure ends the run instead of burning the remaining daily YouTube budget
(99 search calls/day on UAT); a job with failed-but-retryable items becomes `paused`; worker leases expire after 3 min and items
stop after 4 attempts. Still `service_role`-only (anon/authenticated EXECUTE false). Functions changed:
`video-bulk-jobs`, `generate-trainer-curriculum`, `_shared/video-discovery-policy.ts`.

**Verification:** journeytabs 6/6, admin login 5/5, assesslist ✓, swotadmin ✓, admin crawl 43/43, Coding Challenges, Save Module,
Tier search, anon `video-bulk-jobs` 401. Snapshot `~/banking-sb/snapshots/20261022T172955Z`.

## 2026-10-23 — UAT `1227b08a`: admin login diagnostics, YouTube key test without quota (ffmpeg round 7)

Merged branch `4009587a` (3 commits). Clean merge, build OK, 20/20 tests. No migrations.
- **Admin login diagnostics:** new `src/lib/adminAuth.ts` + `Login.tsx` show clearer reasons when admin sign-in fails. `AuthContext`
  untouched — the `rolesUserId` role-race gate is intact (admin5 10/10).
- **LLM Settings → YouTube provider "Test":** `manage-llm-providers` no longer spends YouTube search quota on a key test and
  de-duplicates repeated test requests. Function stays admin-only (`requireAdmin`; anon rejected — returns 500 not 401, pre-existing).

**Verification:** admin login 5/5 ×2, journeytabs 6/6, assesslist ✓, swotadmin ✓, admin crawl 43/43, Coding Challenges, Save Module,
Tier search, candidate/trainer/admin homes. Snapshot `~/banking-sb/snapshots/20261023T044442Z`.

## 2026-10-23 — UAT `2501259f`: homepage repositioned as an AI-powered LMS (ffmpeg round 8)

Merged branch `4c85a90e` (3 commits, `src/pages/Home.tsx` + `tests/e2e/home-requirements.spec.ts` only). Public homepage now
positions PluginLive as an AI-powered LMS for four audiences — Corporate Learning & Development, Institutes & Universities,
Hire · Train · Deploy, Software & Testing Teams — with Solutions / Capabilities / Learning journey / FAQ sections (capabilities
consolidated; ~1,000 lines removed). No backend, migration or config changes.

**Verification:** homepage at 1440 px and 390 px: no page errors, no failed requests, no horizontal overflow; admin login 5/5,
journeytabs 6/6, assesslist ✓, candidate/trainer/admin homes clean. Snapshot `~/banking-sb/snapshots/20261023T065605Z`.

## 2026-10-23 — UAT `f5d01e5e`: simulation generation fallback + trainer module scope (ffmpeg round 9)

Merged branch `8b520206` (3 commits; `_shared/sim-ai.ts`, `sim-generate-pack`). Clean merge, build OK, 81/81 tests. No migrations.
- **Simulation AI fallback:** credit, transient gateway (502), stream, empty-output and format failures on the Lovable Responses
  call get one fallback through the configured providers (`aiJsonViaConfiguredProviders` → `_shared/llm.ts`, i.e. LiteLLM on UAT);
  402/429 from that chain are passed through, anything else → 502 "temporarily unavailable; no simulation draft was created".
  Never a fabricated simulation. UAT has no Lovable key, so it already uses the configured-provider path.
- **Trainer module scope:** `sim-generate-pack` now only lets a trainer generate packs for modules they can access. Anon → 401.

**Verification:** admin login 5/5, journeytabs 6/6, assesslist ✓, candidate/trainer/admin homes clean, no function boot errors.
Snapshot `~/banking-sb/snapshots/20261023T082343Z`.

## 2026-10-23 — UAT `c759687c`: bulk-video failure recovery + Trainer video discovery errors (ffmpeg round 10)

On top of `94012d3f` (deployed separately: View Results 406 fix, Learning Tracker trainer filter, trainer module-group
delete, live mic wave for video answers; 3 migrations). Merged branch `f3c83dd4` (2 commits, frontend + e2e only): Admin bulk
video jobs show clearer failure/retry recovery; Trainer journey surfaces video-discovery errors instead of failing silently.
Clean merge, build OK, 15/15 tests. No migrations or function changes.

**Verification:** admin login 5/5, journeytabs 6/6, assesslist ✓, admin crawl 43/43. Snapshot `~/banking-sb/snapshots/20261023T090757Z`.

## 2026-10-23 — UAT `39a51f5d`: Admin "Generate a simulation" 502 fixed

**Symptom:** Admin → Modules → AI Simulations → Generate → `sim-generate-pack` 502 ("The AI returned no response twice" /
"invalid response twice ($.title is required)"). UAT has no Lovable key, so `_shared/sim-ai.ts` uses the configured-provider path
(`callLlmChatCompletion`, feature **`simulation`**), which had no gateway route → global `openai gpt-5` (reasoning used the whole
4096-token budget → empty content) then `gemini-3.6-flash` (truncated).
1. **Config (live):** `llm_provider_configs` row `litellm` / `application_feature='simulation'` / `gemini-2.5-flash` / priority 1
   (same gateway route as `ai-content`). Also covers candidate persona turns and debriefs.
2. **`39a51f5d`:** configured-provider output cap raised from 4096 to **12000** for pack/section generation (persona_turn 2048 and
   debrief 6000 unchanged). A pack spec is ~10 KB JSON; the gateway stopped at 4082/4320 tokens → truncated object → parser fell
   back to an inner object without `title`. A full pack used 8,465 completion tokens.

**Verification:** `node ~/banking-checks/simgen.cjs <moduleId> <topicId> "<topic title>"` (creates a DRAFT pack — delete after):
2/2 Life Insurance topics → 200 in 28-38 s (was 502 after 105 s); test drafts deleted (sim_pack_versions + sim_packs, owner =
admin@bankready.app). journeytabs simulations/robo ✓, admin login 5/5, admin crawl 43/43. Snapshot `20261023T102043Z`.

## 2026-10-24 — UAT `03cb8c37`: Metabase role dashboards, SWOT evidence pipeline, learner-data RLS hardening (ffmpeg round 11)

Merged branch `a26aa150` (11 commits) into `main 39a51f5d`; clean merge. The merge commit also updates the
`roboSprint34Contracts` assertion to the 12000 sim token cap. Build OK. vitest 1867/1872: the same 5 tests already fail on `main` and the branch
(mediaReleaseVerification, roboHandsFree ×2, simulationAuthAndLogoutRegression, plus the fixed roboSprint34 one).

**Migrations (9):** trainer_admin_group_assignment, metabase_role_dashboard_enrichment, learning_swot_evidence_pipeline,
metabase_assessment_score_accuracy, metabase_student_activity_metric_accuracy, metabase_admin_coverage_accuracy,
metabase_trainer_reporting_accuracy, trainer_student_data_rls_hardening, admin_profile_role_escalation_guard.
DB-Scripts `20261024T085749Z`…`T085757Z` (PROD pending).
- **UAT fixups** for `20261023130000_metabase_role_dashboard_enrichment` and `20261024120000_metabase_student_activity_metric_accuracy`:
  drop `m.track::text` (UAT `modules` has no `track`; `track` lives on `domains`) and `aa.updated_at` (UAT `assessment_attempts`
  has no `updated_at`). The COALESCE falls back to `metadata->>'track'` / `started_at`.
- **`~/banking-sb/sql/03_grants.sql`:** the hard-coded 6-view Metabase revoke is now a DO block revoking ALL from
  PUBLIC/anon/authenticated on **every** `public` view/matview named `metabase%` (15 views now). Verified: anon REST → 401/42501.
- **RLS rehearsal (rolled back):** candidate `profiles.role` escalation BLOCKED, candidate score insert BLOCKED, trainer
  self-approve BLOCKED, admin grading update OK, cross-user attempt updates 0 rows, candidate own profile update OK.
- **Cost:** full-table reads of `student_module_progress` went from 16–27 ms to 0.6–1.6 s (admin/candidate/trainer).
  `private.trainer_can_view_student_data` runs once per row, which matters for unfiltered admin/trainer scans. Filtered
  learner reads stay fast. If trainer/admin progress pages slow down as data grows, rewrite the policy as
  `student_id = any((select visible_student_ids()))` (one initplan).

**`learning-swot-report` overlay retired.** The 10-16 whole-file overlay (`function-fixups/learning-swot-report`) predated
upstream's rewrite and crashed (`toFixed` of undefined). Moved to `~/banking-sb/function-fixups-retired/learning-swot-report-20261024`.
Upstream no longer reads `students.target_role` / `learning_simulation_attempts.student_id`. 3 overlays remain.

**Gateway header buffer (new, both layers).** Admin SWOT then failed with `profiles: 502 Bad Gateway`. Upstream batches
100 ids into `user_id=in.(...)` (~3.7 KB URL). PostgREST echoes the query in `Content-Location`, and nginx's 4 KB
`proxy_buffer_size` gave "upstream sent too big header". 80 ids passed and 100 failed. Fix: `proxy_buffer_size 16k; proxy_buffers 8 16k;`
in `~/banking-sb/gateway.conf` (server level; reloaded with `nginx -s reload`) **and** in the host
`/etc/nginx/sites-available/banking-react.conf` banking 443 server block (backups `*.bak-20261024T-hdrbuf`). Each layer
needs it: functions call `http://gateway:80`, and browsers come through the host nginx.

**Verification:** admin login 5/5, journeytabs 6/6, assesslist ✓, swotadmin ✓ (93 learners in scope), admin crawl ✓,
e2e users ✓, cc/mod/tier ✓, trainermods/trainersearch/resultspage ✓. Snapshots `20261024T083745Z`, `20261024T084528Z`.

## 2026-10-24 — UAT `68a98e61`: BI Dashboard in every journey + SWOT gateway retries (ffmpeg round 12)

Merged branch `3cd93aea` (4 commits) into `03cb8c37`; clean merge. Build OK. vitest 1877/1879 after the fix below; the
4 failures already on `main` remain.
- **BI Dashboard:** migration `20261024170000_metabase_bi_dashboard_menu_access` (DB-Scripts `20261024T094520Z`, PROD pending).
  It adds menu_key `metabase` for student/trainer/teacher/admin on all plans, and appends `metabase` to all 27 admin tab
  lists and all 152 candidate menu lists (plus the column defaults). `metabase-embed-token` requires a JWT (anon → 401).
  **UAT has no Metabase** (no container, no `METABASE_*` in `functions-secrets.env`, no `VITE_METABASE_ENABLED`), so students
  see "Metabase is ready to connect — Configure VITE_METABASE_ENABLED…" (a graceful card, no errors).
- **SWOT:** `learning-swot-report` retries transient gateway failures (`_shared/swot-db-retry.ts`) and contains session
  verification failures. The UAT 16k header-buffer fix from round 11 still applies.
- The merge commit adds `metabase: "BI Dashboard"` to `src/test/adminTabsAccessDenied.test.tsx` TAB_LABELS (the test failed upstream).

**Verification:** admin login 5/5, journeytabs 6/6 + metabase tab ✓, assesslist ✓, swotadmin ✓ (93 learners).
Snapshot `~/banking-sb/snapshots/20261024T094102Z`.

## 2026-10-24 — UAT: Metabase BI Dashboard live for admin, trainer and student (config only, no code change)

**Symptom:** every journey's BI Dashboard showed "Metabase is ready to connect — Configure VITE_METABASE_ENABLED…".
The repo ships the views, the `metabase-embed-token` function and `docs/METABASE_DASHBOARDS.md`; the Metabase server,
its dashboards and the secrets are external configuration that UAT never had.

**What runs now (UAT box):**
- **Container `banking-sb-metabase`.** It is a new service in `~/banking-sb/docker-compose.yml` (backup `.bak-20261024T-metabase`).
  Image `metabase/metabase@sha256:7804ce4e…` (v0.64.3.4), `127.0.0.1:8210`, `mem_limit 2g`, `-Xmx1g`, `restart: unless-stopped`.
  Start/recreate it with `cd ~/banking-sb && set -a && . ./.env && . ./metabase.env && set +a && docker compose up -d metabase`.
- **App DB:** database `metabase_app`, owner role `metabase_app`, on `banking-sb-db`.
- **Reporting connection:** role `metabase_readonly`. It has `default_transaction_read_only=on` and `statement_timeout=60s`, with SELECT
  on the 15 `public.metabase%` views only (no tables). `~/banking-sb/sql/03_grants.sql` now re-grants SELECT on every
  `metabase%` view to it on each deploy, so recreated views keep working. Anon/authenticated stay revoked.
- **Public path:** host nginx `location /metabase/ → 127.0.0.1:8210/` in `/etc/nginx/sites-available/banking-react.conf`
  (backup `.bak-20261024T-metabase`); `MB_SITE_URL=https://banking.uat.pluginlive.com/metabase/`. Embeds are same-origin.
- **Secrets:** `~/banking-sb/metabase.env` (chmod 600) holds the app DB password, read-only password, Metabase admin
  (`metabase-admin@bankready.app`) password and the embedding secret. `functions-secrets.env` now has `METABASE_URL`,
  `METABASE_JWT_SECRET`, `METABASE_{STUDENT,TRAINER,ADMIN}_DASHBOARD_ID=2/3/4`. Changing `functions-secrets.env` needs
  `docker compose up -d functions` (env_file is read at create, not restart). `~/bankingjobreadiness/.env` has
  `VITE_METABASE_ENABLED=true`, baked into the bundle by `deploy.sh`.
- **Dashboards** (collection "BI Dashboards", native SQL cards, created by `~/banking-sb/metabase-setup.py`, idempotent by name):
  - Student #2 — assigned/completed modules, average progress, study hours, module progress, weekly effort,
    assessment results, competency readiness. Locked `student_id`.
  - Trainer #3 — assigned/active learners, completion rate, graded average, learner progress,
    weekly active learners, needs-attention list, readiness gaps. Locked `trainer_id`.
  - Admin #4 — overview KPIs, outcomes by institute, weekly active learners, assessments and proctoring,
    curriculum coverage, AI operations daily/by feature, YouTube quota.
  - Every Student/Trainer card uses `WHERE <id> = CAST({{param}} AS uuid)` outside optional brackets, so a token
    without the signed ID errors ("You must specify a value for :student_id in the JWT"). It never returns all rows.
    A URL attempt to override a locked value is rejected.
  - Both IDs are auth user ids. The embed function signs `user.id`, matching `metabase_student_dashboard.student_id`
    (3863/3863 rows) and `metabase_trainer_dashboard.trainer_id` (`trainers.user_id`).

**Verification:** `node ~/banking-checks/metabase.cjs` (admin via sidebar "BI Dashboard" → `/admin?tab=metabase`; candidate
`?tab=metabase`; trainer sidebar). The iframe renders cards for all 3 roles with no API ≥400 or page errors. Admin shows 122 users /
116 candidates / 20 trainers / 105 published modules. A direct signed-token test for a 190-module student returned exactly 190 rows.
admin5 5/5, journeytabs 6/6. Metabase uses ~1.25 GiB.

**For PROD:** run Metabase (or a managed instance) with its own app DB, create `metabase_readonly` with the same view-only
grants, build the dashboards with `metabase-setup.py` (adjust host/URL), then set the 5 secrets and `VITE_METABASE_ENABLED=true`.
The Metabase login page is reachable at `/metabase/`; only the admin account exists.

## 2026-10-26 — UAT: BI Dashboard period / comparison / Combined-Domain-Tech filters enabled (config only)

**Symptom:** after rounds 13–14 (`e8330a6b`), every BI Dashboard showed "Some dashboard filters need Metabase setup".
The embed function only offers the period, comparison and track controls when `METABASE_DATE_FILTER_ENABLED`,
`METABASE_COMPARISON_FILTER_ENABLED` and `METABASE_TRACK_FILTER_ENABLED` are `true`. Per `docs/METABASE_DASHBOARDS.md`,
those may only be set once the `date_range`, `comparison_date_range` and `journey_track` dashboard parameters exist.

**Fix:** `~/banking-sb/metabase-filters.py` (idempotent; rewrites card SQL by name). It adds the 3 parameters as **locked**
embedding params to dashboards 2/3/4 and wires each compatible card through a text variable in an optional clause.
A JWT value of `[]` (All time / Combined) means no filter.
- `date_range` (`YYYY-MM-DD~YYYY-MM-DD`): events → `occurred_at`, assessments → `completed_at`, SWOT → `snapshot_at`,
  AI ops → `report_date`, YouTube quota → `quota_date`.
- `journey_track` (`domain`/`tech`): every card on `metabase_student_dashboard`, `metabase_trainer_dashboard`,
  learning-event views and `metabase_module_catalog`.
- New card "This period vs comparison period" on each dashboard. It shows the selected-period row, plus a
  comparison row when `comparison_date_range` is set.
- Not filtered: cohort KPIs are track-only (no date: they count assigned modules/learners). Admin overview KPIs
  (`metabase_admin_overview`) stay platform totals.
- Flags set in `~/banking-sb/functions-secrets.env` (backup `.bak-20261026T-mbfilters`), applied with
  `docker compose up -d functions`.

**Verified:** signed-token tests for all 3 dashboards (all-time/combined, 30 days + tech + comparison, domain); every card
returns data. Student 95 modules = tech 27 + domain 68; curriculum 107 = 28 + 79; the comparison card has 2 rows only when
comparison is on. `node ~/banking-checks/metabase.cjs` (now also asserts no setup warning and the period/compare controls):
admin, candidate and trainer ✓.

**2026-10-26 — Metabase setup now in the repo:** Banking `main` `71a40a63` adds `deploy/metabase/`. It has the compose
service, nginx location, `readonly_role.sql`, `metabase.env.example`, `metabase_setup.py` and `metabase_filters.py`
(env-configurable via `METABASE_API`, `METABASE_ENV_FILE`, `MB_REPORT_DB_*`), plus a README with the PROD steps.
The `~/banking-sb/metabase-*.py` copies on UAT are superseded. No app code changed; the next `deploy.sh` fast-forwards
the UAT checkout to include it.

## 2026-10-26 — UAT `efc7756d`: BI goal/readiness views + learner-owned learning paths (ffmpeg round 15)

Merged branch `3d97c789` (5 commits) into `main 71a40a63`; clean. Build OK; vitest 1901/1905 (the 4 known upstream failures).
6 migrations; DB-Scripts `716d6b5…b1ac726` (PROD pending).
- **Fixup `20261026120000_metabase_student_goal_progress_display`:** upstream's `metabase_student_competency_readiness_display`
  selects `target_role/target_score/target_date` from `metabase_student_competency_readiness`, which (20261025130000) has no
  goal columns → 42703 on any database. UAT joins the `swot_student_goals` row active at each `evidence_as_of` (the view's stated
  intent); the columns are appended, so `CREATE OR REPLACE` keeps the existing view.
- **Fixup `20261026170000_candidate_learning_path_owner_rls`:** upstream + drops `candidate_learning_paths/_modules
  "authenticated read|write"` (`USING (true)`, from `20260710120000_pil_feature_merge_compat`). OR'd with the new owner
  policy, they let any user read and rewrite every learner's path. **Upstream/hosted still has them.** Now: learner reads own
  (by auth uid or `students.id`), admin manages; generation stays server-side (`generate-candidate-path`).
- Rehearsed: candidate sees 0 others' paths and cannot insert; a candidate-only owner sees 1 path / 10 modules; admin delete OK;
  core RLS probes unchanged. 66 `metabase%` views: anon/auth 0, `metabase_readonly` all.
- The new goal views (`metabase_student_goal_progress[_display]`, trainer goal progress, admin readiness aggregates) are
  not yet on the UAT dashboards (`deploy/metabase/metabase_filters.py` / `metabase_setup.py` own the card list).

**Verification:** admin5 5/5, journeytabs ✓, assesslist ✓, swotadmin ✓, metabase.cjs admin/candidate/trainer ✓. The check now waits
for the iframe swap: the page re-signs the embed once filters resolve. Snapshot `20261026T085836Z`.

## 2026-10-27 — UAT `1118f2c5` on branch `uat/banking-otp-fallback` (round 16; email-OTP login held back)

`main` = `91b5da46` (merge of branch `0145f035`, 12 commits): email OTP login for students/trainers, configurable email
providers (Resend/Outlook/Google/Zoho/SMTP, encrypted credentials), password-reset email, curriculum video analysis,
scoped trainer curriculum access, onboarding identity alignment.

**Why UAT is not on `main`:** `20261026180000_email_login_otp` drops `sms_gateway_settings.temporary_otp`, the shared code
every UAT student/trainer login uses (no SMS provider on UAT). The new login then requires `request-login-otp` to send the
code through an admin-configured provider (credentials in `email_provider_credentials`, plus `EMAIL_CREDENTIALS_ENCRYPTION_KEY`).
UAT has none of these (gateway provider `generic`), so every student/trainer login would fail with "Login email delivery is
not configured".

**`uat/banking-otp-fallback` (GitHub) = `main` + one commit.** It restores the `efc7756d` login path (Login.tsx,
candidateMobileAuth, SMS settings UI, candidate-otp-login, _shared/otp-login, update-sms-gateway, send-test-otp,
bulk-create-users, trainer-bulk-import, trainer-csv-schema and their tests), removes `request-login-otp`, and drops
`20261026180000`. Everything else in round 16 is live. vitest: the 4 known upstream failures, plus 3 source-contract tests
for the held-back email-OTP code. The old flow still blocks deactivated accounts and does not reactivate profiles.

**Deploying while this lasts:** `DEPLOY_REF=origin/<uat branch> bash ~/banking-sb/deploy.sh`. `deploy.sh` now reads
`REF=${DEPLOY_REF:-origin/main}`. Each new round: merge the branch into `main` as usual, then rebuild the UAT branch as
`main` + the same restore commit (re-check the restored files against upstream edits). A plain `deploy.sh` will refuse
(`--ff-only` from the UAT branch).
**To go back to `main`:** configure an email provider in Admin (and `EMAIL_CREDENTIALS_ENCRYPTION_KEY`) and test a code.
Note that real-looking addresses get emails (72/113 students, 16/20 trainers); `@bankready.app` test accounts have no
mailbox. Then `git reset --hard origin/main` in `~/bankingjobreadiness` and run `deploy.sh`; that applies `20261026180000`.

**Migrations applied (3):** `20261026190000_trainer_curricula_table_privileges` (no-op on UAT; policies already scoped),
`20261027120000_login_otp_notification_setting`, `20261027130000_email_provider_configuration`. DB-Scripts `a129a9f…b888ce0`
(PROD pending). `03_grants.sql` tail now revokes `email_provider_credentials` and `auth_login_otp_*` from anon/authenticated
(the blanket grants had re-opened them).

**Verification:** student journey tabs (OTP 1234) ✓, trainer pages ✓, admin5 5/5, assesslist ✓, BI admin/candidate/trainer ✓,
`temporary_otp` columns intact, anon on credentials table false. Snapshot `20261027T054319Z`.
