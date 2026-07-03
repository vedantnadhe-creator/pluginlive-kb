# MedVerse — UCAT Prep (ucat-ai-prep)

Standalone **Lovable**-built UCAT preparation web app ("MedVerse — AI-Powered UCAT Preparation Platform"). Repo `PluginLive-Technologies/ucat-ai-prep`, branch `main`. Deployed on **UAT only** at **https://ucatprep.uat.pluginlive.com**. Not part of the core PluginLive platform — it has its own Supabase backend and is **not** managed by `auto_deploy.sh`.

## Stack

- **TanStack Start SSR** app, built via `@lovable.dev/vite-tanstack-config`. Lovable owns the repo and re-publishes constantly (commit messages "Changes"), regenerating `.env` and AI-gateway wiring on each publish.
- Backend = **Supabase** project `yzmsyddukyujtjrrtect` (region **ap-northeast-2 / Seoul**). All app DB tables + auth live here (not the platform Postgres).
- Runs on UAT under **pm2** process `ucatprep` on `127.0.0.1:8090`, fronted by nginx vhost `/etc/nginx/sites-enabled/ucatprep.conf` (pure reverse-proxy; Let's Encrypt cert).
- Must run on **Node 20** (`/home/ubuntu/.nvm/versions/node/v20.20.2/bin/node`) — Vite needs ≥20.19, and `--env-file` needs ≥20. The default shell `node` on the box is v18; always export the v20 path before `npm run build`.

## Build output (changed 2026-06: Nitro)

The Lovable config now emits a **Nitro `cloudflare-module`** build at `.output/server/index.mjs` (default export `{ fetch }`) + static assets in `.output/public/`. (It used to emit `dist/server/server.js` Cloudflare-style — old wrapper paths are stale.)

Run on Node via the wrapper **`~/ucat-ai-prep/server-node.mjs`** (untracked, survives `git reset`): uses **`srvx`** (`serve({ fetch })`) to turn the fetch handler into a real Node HTTP server, binds `env=process.env` (Nitro's `createHandler` fetch signature is `(request, env, context)` — without it `env.ASSETS` throws), and serves `.output/public/**` from disk for `/assets/*` (the `env.ASSETS` Cloudflare binding doesn't exist under Node).

**Nitro-node shim (gotcha):** the Nitro bundle's `augmentReq()` writes `req.ip = …` and replaces `req.runtime`, but Node 20's `Request` makes those **getter-only** → `TypeError: Cannot set property ip` (504s), and clobbering `runtime` wipes srvx's `runtime.node.{req,res}` → `Cannot destructure property 'req' of 'this.runtime.node'` (500 "This page didn't load"). Fix = **`~/ucat-ai-prep/reapply-nitro-node-shim.py`**: `Object.defineProperty` for `ip` and **merge** (not replace) `runtime`. `npm run build` regenerates `index.mjs`, so **re-run the shim after every build**. (Proper upgrade path: switch the build preset to `node-server` and drop the shim.)

**WebSocket polyfill:** Supabase realtime-js needs a global `WebSocket` (Node 20 has none). `ws-polyfill.mjs` (imported first in the wrapper) sets `globalThis.WebSocket`; `ws@8` is installed via `npm install ws --no-save` (re-run after a clean install — it's not a committed dep).

## .env — force to Seoul after every pull

Lovable's repo `.env` points to a **broken** old project `hsxyymmlbleorzcbsmtn` (bogus service_role key) and regenerates it on every publish, so a plain `git pull` reverts `.env`. **Always overwrite `.env` to Seoul after pulling** (all 6 Supabase vars → `yzmsyddukyujtjrrtect` + `GEMINI_API_KEY` + `PORT=8090`). A wrong `.env` baked into the client bundle breaks mobile-OTP login ("No account found"). The live `.env` is backed up to `.env.live.<ts>` before each reset. Verify the bundle after build:
```
grep -rhoE 'https://[a-z0-9]+\.supabase\.co' .output/public/assets/*.js | sort -u   # must be ONLY yzmsyddukyujtjrrtect
grep -rl 'hsxyymmlbleorzcbsmtn|lovable.dev/v1/chat' .output/public .output/server     # must be empty
```

## AI providers

- **AI gateway:** Lovable's gateway key isn't available on the self-hosted deploy, so all in-app AI (coach, question gen, curriculum, mocks, university plan) is re-pointed off `ai.gateway.lovable.dev` to **Google Gemini's OpenAI-compatible endpoint** by **`~/ucat-ai-prep/reapply-gemini.sh`** (sed over `src/**`, re-run after every pull since the patch is not committed).
- **`ai_models_registry` table** (Seoul): admin-managed LLM provider/model registry powering an in-app **LLM fallback gateway** (`src/lib/llm-providers.ts`, added 2026-06-29). Most rows route through **OpenRouter** (`OPENROUTER_API_KEY`) covering GPT-5, Claude Sonnet 4.5, Llama, DeepSeek, Mistral, Qwen, Gemma, etc., with `openrouter/auto` fallback; plus direct Gemini / Lovable rows. Seeded via migrations `…seed_ai_provider_registry.sql` and `…seed_full_llm_provider_registry.sql`.
- **⚠️ Known issue:** the `GEMINI_API_KEY` in `.env` (`AIzaSy…`) is currently **rejected by Google** (`API_KEY_INVALID` even on `GET /v1beta/models`) — direct-Gemini AI features fail until a fresh AI-Studio key is dropped in (no rebuild needed; `.env` is read at runtime, restart pm2 with `--update-env`). The OpenRouter-routed models need `OPENROUTER_API_KEY` set to work.

## DB migrations (Supabase Seoul)

Migrations live in `supabase/migrations/*.sql` in the repo. Apply via the **IPv4 Supavisor pooler** (direct `db.<ref>.supabase.co` is IPv6-only, unreachable from UAT):
```
PGPASSWORD=<seoul-pw> psql "host=aws-1-ap-northeast-2.pooler.supabase.com port=5432 \
  user=postgres.yzmsyddukyujtjrrtect dbname=postgres sslmode=require" -f <file>.sql
```
Apply new files in timestamp order, autocommit (one `psql -f` per file). `ALTER TYPE … ADD VALUE` must NOT be inside a transaction with other DDL. The Lovable migrations are largely idempotent (`CREATE … IF NOT EXISTS`, `ON CONFLICT DO …`). The PROD-box `pg_dump` is PG16 and can't dump this PG17 server — snapshot via `pg_tables` / `pg_enum` SELECTs instead of `pg_dump -Fc`. Schema grew to ~39 public tables (institutes, pricing_plans, entitlements, payments, audit_logs, ai_models_registry, ucat_deciles_2025, …).

## Gotcha: Practice/Mocks stuck on "Loading questions..." (option-count filter)

> **SUPERSEDED 2026-07-03 by upstream commit `d274961` + migrations.** Upstream rewrote all of this natively, so the four hot-patch reapply scripts below (`reapply-mcq-options-v2.sh`, `reapply-practice-fetch-v2.py`, `reapply-mocks-normalize.py`, `reapply-llm-timeouts.py`) are **retired** (moved to `~/ucat-ai-prep/.retired-scripts/`). Current state: migration `20260702193000_clean_question_bank_duplicates_and_options` **permanently trims every row to ≤4 options and dedups the bank in the DB** (deleted 17,115 dup rows: VR 9131→136, SJT 8164→170 — those sections were always only ~52 distinct passages; QR 26.8k / DM 8.3k stay rich). Upstream code replaced the hanging live-LLM fill-loop with a **parallel small-batch generator** (`mapLimit`, ≤12/≤20 per batch, 20s gateway timeout) that falls back to a **local deterministic generator** per batch — so generation never hangs and always returns. **Only two reapply scripts remain active: `reapply-gemini.sh` + `reapply-nitro-node-shim.py`.** The still-relevant operational facts (direct-Gemini registry default, OpenRouter free-tier 402, `.env`-revert-on-checkout) are in the "AI providers" note below. The rest of this section is kept for history.

The seeded question bank is **~99% 6-option** questions (VR 9000×6-opt vs 66×4-opt; DM/QR/SJT similar) — UCAT VR/SJT legitimately have 5-6 options. Upstream commit `ca27067` added `hasFourValidOptions()` (`src/lib/mcq-options.ts`) requiring **exactly 4** options; it's the shared read-filter for both Practice (`getPracticeQuestions`) and Mocks. That filtered out the whole bank → fewer than `count` questions found → and commit `51a4aff` then added a **live-LLM generation-fill loop** to top up, which hangs forever (`All LLM providers failed … 429/404`) because AI generation is offline → the Practice UI sits on "Loading questions..." indefinitely.

**Deeper root cause:** the seed bank has only **52 distinct passages / 130 distinct stems across 9131 approved VR rows** (5 stems × ~1800 near-identical copies). `getPracticeQuestions` fetched with an **unordered** `LIMIT 300`, so PG returned one physical cluster (→ 1 distinct after `removeNearDuplicateQuestions`' 0.88 Jaccard collapse), still < count → hit the LLM fill-loop → hang.

**Fix — do NOT relax the 4-option UI contract; normalize to exactly 4 instead.** Showing 6 raw options to a student is bad UX even though scoring is option-count agnostic. Three reapply scripts (untracked, survive Lovable's `src` rewrites — run in this order after every pull, before `npm run build`):

1. **`~/ucat-ai-prep/reapply-mcq-options-v2.sh`** — keeps `hasFourValidOptions` **strict (exactly 4)**, and adds `normalizeMcqOptions(question)` to `src/lib/mcq-options.ts`: for rows with >4 options, keeps the correct answer + picks exactly 3 distractors via an **FNV1a hash seeded on the row's own `id`** (falls back to `stem|options` if no id) — so the same row always normalizes to the byte-identical 4-option array in the identical order, regardless of when/where it's read.
2. **`~/ucat-ai-prep/reapply-practice-fetch-v2.py`** — same `.order("id")` + widened window (`max(1500, count*60)`) + **bank-only top-up** (no more live-LLM fill-loop) as before, but calls `.map(normalizeMcqOptions)` before the strict filter in `validQuestionRows` and `getApprovedCounts`, instead of relaxing the filter.
3. **`~/ucat-ai-prep/reapply-mocks-normalize.py`** — applies the same `normalizeMcqOptions` to every mock-exam site in `src/lib/mocks.functions.ts` that reads bank rows for students: `bankCounts`, `buildAttemptQuestions` (saved-paper + default-library paths), `loadServedRows`, `buildSectionItems`'s `use_existing` primary+fallback passes, `submitMock` (scoring), and `getMockReport` (review).

**Why determinism matters specifically here:** `submitMock` records the student's answer as a raw **array index**, then **re-fetches** the same question row (fresh, untrimmed) to score it, and `getMockReport` re-fetches it **again** to build the review screen (`options[chosenIndex]`). If the 6→4 trim picked different distractors or order on each of those three separate reads, indices would drift and answers would silently mis-score. The id-seeded hash guarantees serve/score/review always agree. Verified against live bank: VR count=10 → 989/1000 sampled rows normalize to valid exactly-4 options; re-normalizing the same row twice is byte-identical.

Reapply order: `reapply-gemini.sh` → `reapply-mcq-options-v2.sh` → `reapply-practice-fetch-v2.py` → `reapply-mocks-normalize.py` → force `.env` to Seoul → build → `reapply-nitro-node-shim.py` → `pm2 restart`.

**⚠️ Gotcha hit while doing this fix:** `git checkout -- src .env` (to reset before re-running the patch chain) reverts `.env` to the broken Lovable project (`hsxyymmlbleorzcbsmtn`) — if `npm run build` runs in that state, `VITE_*` vars get **baked into the client bundle** pointing at the wrong Supabase project (server-side stays fine, env is read at runtime there, but the browser silently talks to the wrong DB). Always re-force `.env` to Seoul **immediately** after any `git checkout -- .env`, before the next build. Verify post-build: `grep -rhoE 'https://[a-z0-9]+\.supabase\.co' .output/public/assets/*.js` must show only `yzmsyddukyujtjrrtect`.

**Generate-questions timeout (fixed 2026-07-02):** direct Gemini needs ~48s for a 25-question tool-call batch but the gateway default timeout was 45s (`ai-gateway.server.ts`) and mocks pinned 22s — the only working provider got aborted, then the chain burned minutes on dead OpenRouter rows → UI "timed out". Fixes: `~/ucat-ai-prep/reapply-llm-timeouts.py` (both → 120s, run with the other reapply scripts before build), nginx `proxy_read/send_timeout 300s` on ucatprep.conf, registry surgery (disabled all dead-NVIDIA rows which were `is_default`; direct-Gemini `gemini-2.5-flash` now default for chat/qbank/insights/coverage), and deleted the dead `NVIDIA_API_KEY` from `admin_settings` (that table overrides `.env` in `getEffectiveSecret`). NOTE: the OpenRouter account is **free-tier with zero credits** → all paid OpenRouter models 402; OpenRouter rows are decorative until credits are purchased — direct Gemini carries all AI load.

**AI keys (set 2026-07-02):** `GEMINI_API_KEY` now uses the **`AQ.`-format** key (works on the OpenAI-compat `/v1beta/openai/chat/completions` path the app uses — the old `AIzaSy…` key was rejected there) and `OPENROUTER_API_KEY` is set (valid). Both live in `.env`, runtime-read (no rebuild; `pm2 restart --update-env`).

## Deploy procedure (UAT)

```
cd ~/ucat-ai-prep
cp .env .env.live.$(date +%Y%m%d-%H%M%S)         # backup live env
git checkout -- src .env                          # drop Gemini patch + .env so pull is clean
git pull --ff-only origin main
# apply any NEW supabase/migrations/*.sql to Seoul (pooler, timestamp order)
bash reapply-gemini.sh                             # re-point AI off Lovable gateway → Gemini
# (option-normalize / practice-fetch / mocks-normalize / llm-timeout scripts RETIRED 2026-07-03 — upstream d274961 + migration 193000 do this natively)
# After applying any new migrations that touch ai_models_registry, RE-ASSERT direct Gemini as default:
#   disable nvidia rows; clear is_default from openrouter-routed chat/qbank rows (free-tier 402);
#   upsert gemini gemini-2.5-flash (generativelanguage endpoint, GEMINI_API_KEY) is_default=true for qbank/chat/insights/coverage
cat > .env <<EOF ... EOF                            # force 6 Seoul vars + GEMINI_API_KEY + OPENROUTER_API_KEY + PORT=8090
export PATH=/home/ubuntu/.nvm/versions/node/v20.20.2/bin:$PATH
npm install && npm install ws --no-save && npm run build
python3 reapply-nitro-node-shim.py                 # MUST run after build (regenerates index.mjs)
pm2 restart ucatprep --update-env
```
Verify: `curl https://ucatprep.uat.pluginlive.com/` → 200 + title "MedVerse — …"; an `/assets/<file>.js` → 200 `text/javascript`; bundle grep = only `yzmsyddukyujtjrrtect`; pm2 log has no `TypeError` on fresh requests.
