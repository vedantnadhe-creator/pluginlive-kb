---
type: reference
tags: [service, frontend, supabase, lovable, banking, overview]
---

# Banking Job Readiness — Application Overview

> **Start here.** This page explains what the app is and how it is built. It describes the code
> at Banking `main` **`dff50a1`** (2026-10-08), which is also what UAT runs.
> The deploy log, every incident and the local-patch inventory are in
> `Infrastructure/banking-job-readiness.md`. The self-hosted Supabase stack on UAT is in
> `Infrastructure/banking-postgres-migration.md`.

## What it is

**Candidate Job Readiness Journey** (branded *BankReady*). It is a learning and assessment platform that
gets freshers ready for banking jobs: BFSI knowledge, aptitude, interviews and soft skills. A separate
"Tech" journey covers AI, LLMs and coding. Trainers and institutes deliver content and admins run the
platform. Most of the content is AI-generated and then approved by a person.

It is **separate from the main PluginLive stack**. It has no Node/Prisma services, no
`auto_deploy.sh` and no shared DB. It is a Lovable-generated SPA that talks straight to Supabase
(PostgREST + Auth + Storage + Edge Functions).

| | |
|---|---|
| Repo | `PluginLive-Technologies/bankingjobreadiness`, branch `main` (Lovable bot `gpt-engineer-app[bot]` commits most of it; ~2,200 commits since 2025-01; force-pushed once on 2026-09-28) |
| Frontend | Vite + React 18 + TypeScript + shadcn/ui + Tailwind, TanStack Query, react-router |
| Backend | Supabase: 261 SQL migrations, **92 Deno edge functions** + `_shared/`, RLS on every table, pgvector for RAG |
| UAT | `https://banking.uat.pluginlive.com/`, with a self-hosted Supabase stack at `/sb` (containers `banking-sb-{db,rest,auth,storage,functions,realtime,gateway}`, DB `banking_uat`, 171 public tables) |
| PROD / hosted | Lovable-hosted Supabase project `kbwjokmmzkgjwiqelrdc`. We have **no** service-role or DB access, and fixes made on UAT are not applied there |
| Deploy | Manual, on the UAT box: `~/banking-sb/deploy.sh` (migrations via fixups → grants → `sync-functions.sh` → `vite build`). See the deploy doc |

## Roles and login

The roles live in `user_roles` (enum `app_role`): `candidate`, `student`, `trainer`, `admin`,
`taxonomy_editor`, `super_admin`, and also `institute`, `teacher` and `moderator`. UAT counts on 2026-10-08:
85 candidate, 73 student, 16 trainer, 13 admin, 10 taxonomy_editor, 1 super_admin.

| Route | Who | How |
|---|---|---|
| `/login/candidate` | candidates and students | mobile + OTP screen |
| `/login/trainer` | trainers | mobile + OTP screen |
| `/login/admin` | admins | email + password. The console is **only** at `/admin/dashboard` |

**How the OTP login works.** An OTP account is a GoTrue user with the email `<10-digit-mobile>@bankready.app`.
Its password is *derived* from the mobile number: `Otp_<mobile>_1234`, with a legacy `otp_` variant
(`src/lib/candidateMobileAuth.ts`, `supabase/functions/_shared/otp-login.ts`). The login screen calls
`signInWithPassword` with that derived value. Two things follow from this:
- The derived password is the account's **only** credential. An admin "Reset Password" bricks the
  account, so it is now guarded (`3a4d977`, 2026-08-28).
- ⚠ **Security gap (open):** the formula ships in the client bundle. Anyone who knows a candidate's or
  trainer's mobile number can sign in as them without an OTP, straight against `/auth/v1/token`. The real
  fix is server-side OTP verification that mints the session (or random per-user passwords). As of
  `dff50a1` this is not fixed.

Route guards: `ProtectedRoute` (any signed-in user), `TrainerRoute`, `InstituteRoute` and `AdminRoute`
(`allowTaxonomyEditor` lets taxonomy editors into `/admin`). New sign-ups that need approval land on
`/waiting-for-approval`. Menus are also gated per plan by `menu_access_controls` (Admin → Plan Menu Access).

## Content model

```
domains (19) → module_groups (22) → admin_modules (70) → admin_module_topics (591) → lessons / quizzes / videos
```
- `modules.module_group_id` is the only parent. Triggers copy the group's domain and subject down to
  its modules (realign script: `scripts/release/realign-domain-group-module-hierarchy.sql`).
- **Module groups have a status.** A `draft` group is invisible to candidates even when it is mapped.
  Fixed in `4480728` (new groups publish by default and the mapping UI flags drafts).
- Content reaches users through `module_group_assignments`, with scope candidate, cohort or institute.
  Assessments are scoped by `assessment_institute_mapping`: a mapped assessment is visible only to
  that institute, and unmapped ones stay open.
- **Trainer-uploaded curricula** (`trainer_curricula` + `curriculum_*`): AI lessons and quizzes are built
  **only** from the trainer's own files (`curriculum_resources`) by `build-curriculum-from-content`.
  Student access goes through `student_has_curriculum`. Module documents live in the private
  `module-resources` bucket, and `extract-resource` turns them into `module_resource_chunks`.
- Topic videos: `ai-video-suggest` / `youtube-search` link YouTube videos (YouTube Data API key,
  10k units/day, and it runs out). `suggested_videos` holds *search queries*, not URLs.

## Feature map

**Candidate / student** (`/candidate/home`, `/dashboard`, `/my-learning`)
- Modules and topics with lessons, AI-generated quizzes (`/quiz/:moduleId`), video MCQs and a personalised
  learning path (`generate-candidate-path`, `ai-learning-path`, `recommend-next-topics`).
- Practice: MCQ, descriptive (AI-graded), interview and coding (`/practice/*`, with history).
  Coding runs through **JDoodle** (`execute-code`). 370 coding challenges on UAT.
- Assessments: `/assessments` → `/assessment/:id` → `/assessment-results/:attemptId`, with proctoring
  (`analyze-proctoring`, configurable defaults) and AI grading (`grade-assessment-attempt`).
- AI Coach (`/ai-coach`, voice via ElevenLabs with Gemini TTS fallback), Interview Coach (records and
  transcribes, then gives AI feedback), Resume Analyzer, Banking Knowledge, a RAG chat over uploaded docs.
- Scenario simulations: versioned packs (`sim_packs` → immutable approved `sim_pack_versions`). They run only
  through `sim-attempt`, which keeps the persona state and rubric on the server.
- Leaderboard, progress, reminders, daily practice plan, live-session RSVP, and credits / plan upgrade
  (`student_credits`, `payment_requests`; upgrades are requested and then approved by an admin).

**Trainer** (`/journey/trainer`): builds curricula from uploaded content, generates topics, lessons
and quizzes with AI, approves simulation packs, runs live sessions, bulk-imports, exports CSVs
(`trainer-export-*`), and sees their own cohorts. The RBAC Trainer filter limits them to assigned candidates.

**Institute** (`/journey/institute`): an institute-scoped workspace (programs, locations, mapped
modules and assessments). 3 institutes on UAT.

**Admin** (`/admin/dashboard`). There are four workspaces (Assignments, Analytics, Subscriptions, Security) and roughly 45 panels.
They cover: taxonomy hub (domains, groups, modules, topics, history, bulk), module content builder, assessment
builder, mapping and grading, candidate and group assignment, bulk upload, users and RBAC, the access-audit log,
duplicate mobiles, plan menu access and student tiers, practice settings, proctoring settings, review and reports,
engagement, funnel and practice analytics, error logs, LLM providers, testimonials, and bulk export jobs.

## AI layer

- All chat LLM calls go through `supabase/functions/_shared/llm.ts`. It reads an ordered provider chain from
  `llm_provider_configs` (Admin → LLM Config) and falls back to env keys. The built-in defaults are `lovable`
  (Lovable AI gateway), `gemini`, `openai`, `nvidia`, `deepseek-r1` and `litellm`. If every provider fails, it
  returns a **deterministic fallback** ("AI providers are unavailable…"), so a broken AI feature looks
  like canned text, not an error.
- **UAT** goes through the PluginLive LiteLLM gateway (virtual key `banking-app`, tagged per feature).
  Lovable / NVIDIA / DeepSeek keys are dead. PDF reading uses Gemini's native API (`dff50a1`).
- Media: ElevenLabs TTS, Gemini TTS, transcription (`transcribe-audio`), video generation via
  Gemini / Runway / ElevenLabs (`generate-video`, `compose-video`), images (`generate-image`).
- Background work: `bulk-export-enqueue` / `-worker`, `daily-practice-plan-cron`,
  `regenerate-all-paths`. pg_cron is **not** installed on UAT, so cron-style functions only run when
  someone calls them.

## External services and secrets (edge-function env)

`SUPABASE_URL` / `SERVICE_ROLE_KEY` / `ANON_KEY`, `LOVABLE_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`,
`YOUTUBE_API_KEY` (shared with PilVidya, so one bulk job starves the other), `ELEVENLABS_API_KEY` (+ voice ids),
`JDOODLE_CLIENT_ID/SECRET`, SMS (`MSG91_AUTH_KEY`, `TWILIO_AUTH_TOKEN`, `SMS_GENERIC_AUTH_KEY`), `RESEND_API_KEY`
(password-reset mail), `GITHUB_TOKEN` / `GITHUB_WEBHOOK_SECRET`, and the `BOOTSTRAP_ADMIN_*` values.
The frontend has feature flags in `.env` (persistence and module-catalog flags). If one is missing you get
messages like "Persistence Disabled" or "Module catalog migration required". See the deploy doc.

## Tests and release tooling

- `npm test` (vitest) runs the unit tests and the `src/tests/user-journeys/*` specs (student, trainer, admin RBAC, AI quiz, login).
- Playwright e2e: `test:e2e:*` (smoke, auth, perf, security, api-consistency, rbac).
- `release:supabase:verify` checks the schema and edge-function contract before DB-backed flags are turned on.
- PluginLive's own UAT checks live in `~/banking-checks` on the DEV box.

## Known risks (as of 2026-10-08)

1. **Mobile-derived passwords.** Account takeover is possible with just a phone number (see *Roles and login*).
2. **Hosted PROD drifts from UAT.** UAT fixes (the 409 on plan upgrade, grants, fixups) are not on `kbwjokmmzkgjwiqelrdc`.
3. **Lovable regenerates code.** Upstream commits have deleted data, pointed queries at missing columns,
   and re-introduced security regressions. Review every pull; never deploy blind.
4. **Silent AI fallback.** Dead provider keys show up as canned content, not errors. Check the
   `[llm-fallback]` logs in `banking-sb-functions`.
5. **Older migrations replay badly.** New migrations often need an idempotent fixup in `~/banking-sb/fixups/`.
