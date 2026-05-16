# Observability stack

Self-contained Docker Compose stack for the new-web frontend, the
freedium-library backend, and Prometheus + Loki + Grafana.

## One-command up

```bash
cd stack
cp .env.example .env
docker compose up -d --build
```

Open http://localhost:3001 (default password: whatever you set in
`.env` as `GF_ADMIN_PASSWORD`). The provisioned dashboard is
**Freedium / Freedium Overview**.

## What runs where

| Service     | Internal port | Host port            |
|-------------|--------------:|---------------------:|
| backend     | 7080          | —                    |
| web         | 3000          | `${WEB_PORT:-3000}`  |
| prometheus  | 9090          | —                    |
| loki        | 3100          | —                    |
| promtail    | 9080          | —                    |
| grafana     | 3000          | `${GRAFANA_PORT:-3001}` |

Only `web` and `grafana` are reachable from the host.

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

## Verifying the stack

Run the smoke test:

```bash
./test-stack.sh
```

The script brings the stack up, hits a known-bad URL, asserts the
counter incremented in Prometheus and the URL reached Loki, then tears
the stack down.
