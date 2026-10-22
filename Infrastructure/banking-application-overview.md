---
type: reference
tags: [service, frontend, supabase, lovable, banking, overview]
---

# Banking Job Readiness — Application Overview

> **Start here.** This page explains what the app is and how it is built. It describes the code
> at Banking `main` **`6e0757f5`** (2026-10-22), which UAT runs with the documented
> self-hosted compatibility overlays.
> The deploy log, every incident and the local-patch inventory are in
> `Infrastructure/banking-job-readiness.md`. The self-hosted Supabase stack on UAT is in
> `Infrastructure/banking-postgres-migration.md`.

## What it is

**Candidate Job Readiness Journey** (branded *BankReady*). It is a learning and assessment platform that
gets freshers ready for banking jobs: BFSI knowledge, aptitude, interviews and soft skills. A separate
"Tech" journey covers AI, LLMs and coding. Trainers and institutes deliver content and admins run the
platform. Most of the content is AI-generated and then approved by a person.

It is **separate from the main PluginLive stack**. It has no Node/Prisma services or
shared DB. It is a Lovable-generated SPA that talks straight to Supabase
(PostgREST + Auth + Storage + Edge Functions).

| | |
|---|---|
| Repo | `PluginLive-Technologies/bankingjobreadiness`, branch `main` (Lovable bot `gpt-engineer-app[bot]` commits most of it; ~2,200 commits since 2025-01; force-pushed once on 2026-09-28) |
| Frontend | Vite + React 18 + TypeScript + shadcn/ui + Tailwind, TanStack Query, react-router |
| Backend | Supabase: 310 SQL migrations, **99 application edge-function entry points** + `_shared/`, RLS, pgvector for RAG |
| UAT | `https://banking.uat.pluginlive.com/`, with a self-hosted Supabase stack at `/sb` (containers `banking-sb-{db,rest,auth,storage,functions,realtime,gateway}`, DB `banking_uat`, 226 public tables) |
| PROD / hosted | Lovable-hosted Supabase project `kbwjokmmzkgjwiqelrdc`. We have **no** service-role or DB access, and fixes made on UAT are not applied there |
| Deploy | On UAT: `~/auto_deploy.sh banking main` dispatches to `~/banking-sb/deploy.sh` for full releases; `~/auto_deploy.sh banking-functions` for reviewed functions-only releases. See the deploy doc |

## Roles and login

The roles live in `user_roles` (enum `app_role`): `candidate`, `student`, `trainer`, `admin`,
`taxonomy_editor`, `super_admin`, and also `institute`, `teacher` and `moderator`. UAT counts on 2026-10-08:
85 candidate, 73 student, 16 trainer, 13 admin, 10 taxonomy_editor, 1 super_admin.

| Route | Who | How |
|---|---|---|
| `/login/candidate` | candidates and students | mobile + OTP screen |
| `/login/trainer` | trainers | mobile + OTP screen |
| `/login/admin` | admins | email/User ID (including ten-digit mobile) + password. The console is **only** at `/admin/dashboard` |

**How OTP login works on UAT (2026-10-16).** `candidate-otp-login` verifies the mobile/OTP server-side and returns a magic-link token for `auth.verifyOtp`; browser login no longer depends on a mobile-derived password. Mobile-backed GoTrue accounts commonly use `<10-digit-mobile>@bankready.app`, though linked accounts can use real emails. Temporary OTP is configured in SMS Gateway settings and remains enabled on UAT.

Internal OTP-account passwords are random and rotate on successful OTP sign-in, including older derived credentials. The UAT fix `03bfb448` keeps generated passwords below GoTrue's 72-byte limit and fails the login if rotation fails. It does not bulk-rotate users who have not signed in.

**Admin password reset on UAT:** both reset endpoints permit mobile-backed targets whose database role is admin/super_admin, and record `app_metadata.admin_password_set=true`. Those passwords work on Admin Login and survive subsequent OTP login while the target retains an admin role. Mobile candidates/trainers continue to use OTP and are refused a password reset; user-editable metadata cannot enable this exception. PR #1 merged these fixes into GitHub `main` at `b7df31d5`. The full UAT release now uses the repository versions; the four former auth overlay files were retired. Hosted deployment status is not verified here.

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
- Topic videos: `ai-video-suggest` / `youtube-search` link YouTube videos. The YouTube key is read from
  Admin → LLM Settings (`llm_provider_configs`, provider `youtube`) via `_shared/youtube-key.ts`, env
  `YOUTUBE_API_KEY` only as fallback. The project allows **99 `search.list` calls/day**; one fetch uses at most
  8 (stops at the first region tier with results) and reports "YouTube daily search limit reached" when spent.
  `suggested_videos` holds *search queries*, not URLs. Video quizzes (`generate-lesson-video-quiz`) use the
  video description as evidence (YouTube caption lists come back empty) and refuse with 422 without it.

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
  The candidate list (My Simulations, Robo Play, module tabs) = assigned packs + open published packs for
  modules the learner can access (`user_can_access_module`, called as `service_role`, which needs USAGE on
  schema `private`), gated by the `module_simulation` menu control for the learner's `subscription_tier`.
- **My SWOT Analytics** (`/learning-swot`): deterministic readiness, competency gaps, four SWOT quadrants
  and action plans from assessment, quiz, coding-practice and completed simulation history. Content
  exposure does not create mastery. Reports are saved in `swot_reports`; AI narratives are not enabled.
- Leaderboard, progress, reminders, daily practice plan, live-session RSVP, and credits / plan upgrade
  (`student_credits`, `payment_requests`; upgrades are requested and then approved by an admin).

**Trainer** (`/journey/trainer`): builds curricula from uploaded content, generates topics, lessons
and quizzes with AI, approves simulation packs, runs live sessions, bulk-imports, exports CSVs
(`trainer-export-*`), and sees their own cohorts. The RBAC Trainer filter limits them to assigned candidates.
SWOT Analytics permits reports for assigned learners and filters the trainer intervention queue to that scope.

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

## Known risks (authentication updated 2026-10-16)

1. **Legacy credentials and temporary OTP.** Older accounts rotate away derived passwords at their next successful OTP sign-in; this release performs no bulk rotation. Temporary OTP remains enabled on UAT (see *Roles and login*).
2. **Hosted PROD drifts from UAT.** UAT schema/grant/compatibility overlays are not automatically applied to `kbwjokmmzkgjwiqelrdc`. Some application fixes are now merged into GitHub; hosted deployment state requires separate verification.
3. **Lovable regenerates code.** Upstream commits have deleted data, pointed queries at missing columns,
   and re-introduced security regressions. Review every pull; never deploy blind.
4. **Silent AI fallback.** Dead provider keys show up as canned content, not errors. Check the
   `[llm-fallback]` logs in `banking-sb-functions`.
5. **Older migrations replay badly.** New migrations often need an idempotent fixup in `~/banking-sb/fixups/`.
