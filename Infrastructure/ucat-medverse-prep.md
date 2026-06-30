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

## Deploy procedure (UAT)

```
cd ~/ucat-ai-prep
cp .env .env.live.$(date +%Y%m%d-%H%M%S)         # backup live env
git checkout -- src .env                          # drop Gemini patch + .env so pull is clean
git pull --ff-only origin main
# apply any NEW supabase/migrations/*.sql to Seoul (pooler, timestamp order)
bash reapply-gemini.sh                             # re-point AI off Lovable gateway → Gemini
cat > .env <<EOF ... EOF                            # force 6 Seoul vars + GEMINI_API_KEY + PORT=8090
export PATH=/home/ubuntu/.nvm/versions/node/v20.20.2/bin:$PATH
npm install && npm install ws --no-save && npm run build
python3 reapply-nitro-node-shim.py                 # MUST run after build (regenerates index.mjs)
pm2 restart ucatprep --update-env
```
Verify: `curl https://ucatprep.uat.pluginlive.com/` → 200 + title "MedVerse — …"; an `/assets/<file>.js` → 200 `text/javascript`; bundle grep = only `yzmsyddukyujtjrrtect`; pm2 log has no `TypeError` on fresh requests.
