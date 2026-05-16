#!/usr/bin/env bash
# End-to-end smoke test for the observability stack.
#
# 1. Bring everything up.
# 2. Wait for backend health.
# 3. Hit a known-bad URL through the web.
# 4. Assert the metric incremented in Prometheus.
# 5. Assert the URL reached Loki.
# 6. Tear down (always, even on failure).

set -euo pipefail

cd "$(dirname "$0")"

cleanup() {
    docker compose down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Bringing the stack up..."
docker compose up -d --build

echo "==> Waiting for backend to become healthy..."
for i in $(seq 1 60); do
    state=$(docker inspect -f '{{.State.Health.Status}}' freedium-backend 2>/dev/null || echo "starting")
    if [[ "$state" == "healthy" ]]; then
        break
    fi
    sleep 2
done
[[ "$state" == "healthy" ]] || { echo "Backend never became healthy"; exit 1; }

BAD_URL="https://example-not-a-known-service.test/article"

echo "==> Triggering a known-bad render via the web..."
docker compose exec -T web wget -qO- "http://localhost:3000/${BAD_URL}" >/dev/null || true
sleep 5  # give Promtail time to ship the line + Prometheus time to scrape

echo "==> Asserting Prometheus saw the counter..."
result=$(docker compose exec -T prometheus wget -qO- \
    'http://localhost:9090/api/v1/query?query=freedium_errored_links_total')
echo "$result" | grep -q '"resultType":"vector"' || { echo "bad Prom response"; exit 1; }
echo "$result" | grep -q '"value"' || { echo "no errored-links samples in Prometheus"; exit 1; }

echo "==> Asserting Loki saw the URL..."
# Loki rejects log-stream selectors on /query (instant) since v2.6 — those
# must go to /query_range. Use a 1-hour window ending now.
loki_end=$(date +%s)000000000
loki_start=$((${loki_end%000000000} - 3600))000000000
loki=$(docker compose exec -T loki wget -qO- \
    "http://localhost:3100/loki/api/v1/query_range?query=%7Bjob%3D%22freedium%22%2Csource%3D%22errored_links%22%7D&start=${loki_start}&end=${loki_end}")
echo "$loki" | grep -q "example-not-a-known-service" \
    || { echo "URL did not reach Loki"; echo "$loki" | head -c 500; exit 1; }

echo "==> SMOKE TEST PASSED"
