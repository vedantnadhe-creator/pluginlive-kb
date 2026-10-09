#!/usr/bin/env bash
# Recreates the LiteLLM gateway container. Use this, not a hand-typed docker run:
# config.yaml AND the pl_openai_fallback.py hook are bind-mounted from this
# directory, so a recreate can no longer drop the hook (without it every
# Gemini -> OpenAI fallback 400s on Gemini-shaped params).
# Env (provider keys, DATABASE_URL, master key) lives in litellm.env (chmod 600).
# Pinned to the image the current container runs, so a recreate never upgrades
# LiteLLM by accident; override with LITELLM_IMAGE=... to upgrade on purpose.
set -euo pipefail
cd "$(dirname "$0")"
[ -s litellm.env ] || { echo "litellm.env missing: provider keys + DATABASE_URL" >&2; exit 1; }
python3 test_task_policy.py >/dev/null && python3 test_pl_openai_fallback.py >/dev/null || { echo "hook unit test failed; not recreating" >&2; exit 1; }
IMAGE="${LITELLM_IMAGE:-$(docker inspect litellm -f '{{.Image}}' 2>/dev/null || echo ghcr.io/berriai/litellm:main-stable)}"
docker rm -f litellm >/dev/null 2>&1 || true
docker run -d --name litellm --network litellm-net --restart unless-stopped \
  --log-opt max-size=100m --log-opt max-file=3 \
  -p 127.0.0.1:4000:4000 -p 172.17.0.1:4000:4000 \
  --env-file litellm.env \
  -v "$PWD/config.yaml:/app/config.yaml" \
  -v "$PWD/pl_openai_fallback.py:/app/pl_openai_fallback.py:ro" \
  -v "$PWD/policies:/app/policies:ro" \
  "$IMAGE" --config /app/config.yaml --port 4000 >/dev/null
for _ in $(seq 1 90); do
  if curl -sf -o /dev/null localhost:4000/health/liveliness; then echo "gateway up ($IMAGE)"; exit 0; fi
  sleep 2
done
echo "gateway did not come up" >&2; docker logs --tail 40 litellm >&2; exit 1
