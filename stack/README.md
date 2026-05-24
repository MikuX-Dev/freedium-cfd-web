# Observability stack

Self-contained Docker Compose stack for the new-web frontend, the
freedium-library backend, and Prometheus + Loki + Grafana.

## One-command up

```bash
cd stack
cp .env.example .env
docker compose up -d --build
```

Open:
- **http://freedium.localhost** — the Freedium web frontend
- **http://grafana.localhost** — Grafana (default: admin/admin or whatever `GF_ADMIN_PASSWORD` is)
- **http://traefik.localhost** — Traefik dashboard (routing table, health)

All traffic enters via Traefik on port 80.

## What runs where

| Service     | Internal port | External route              |
|-------------|:-------------:|:---------------------------:|
| traefik     | 80, 8080      | port 80 (host), traefik.localhost |
| web         | 3000          | freedium.localhost          |
| backend     | 7080          | — (internal only)           |
| mongo       | 27017         | — (internal only)           |
| prometheus  | 9090          | — (internal only)           |
| loki        | 3100          | — (internal only)           |
| promtail    | 9080          | — (internal only)           |
| grafana     | 3000          | grafana.localhost           |

## Errored-link logs

The backend writes one JSON line per errored Medium URL to
`/var/log/freedium/errored-links.jsonl` inside its container. The
shared volume `errored_logs` mounts the same directory read-only into
the Promtail container, which ships records to Loki. Grafana queries
them via the dashboard's two log panels.

To tail them directly:

```bash
docker compose exec backend tail -f /var/log/freedium/errored-links.jsonl
```

## Render cache

The backend caches Medium GraphQL responses in MongoDB (`mongo` service,
collection `freedium_cache.post_cache`). Values are zstd-compressed.
Set `CACHE_ENABLED=false` in `.env` to bypass the cache and hit Medium on
every request — useful for debugging.

Cache hit/miss rate is exposed at `/metrics` via
`freedium_cache_hits_total` and `freedium_cache_misses_total`. The
Grafana dashboard does not surface them yet — add a panel in a
follow-up.

To migrate data from a legacy PostgreSQL `cache` table, see
`freedium-library/README.md`.

## Verifying the stack

Run the smoke test:

```bash
./test-stack.sh
```

The script brings the stack up, hits a known-bad URL, asserts the
counter incremented in Prometheus and the URL reached Loki, then tears
the stack down.
