#!/usr/bin/env bash
# Zero-downtime rolling deploy.
#
# The web tier runs N replicas behind Traefik (which the edge HAProxy points
# at). Recreating them all at once leaves a window with no healthy backend →
# 502s, and the edge marks the origin down. This replaces them ONE AT A TIME,
# waiting for each new replica to become healthy before touching the next, so
# Traefik always has live backends and the edge never flaps.
#
# Usage (run from the stack/ dir, or anywhere — it cd's to its own dir):
#   ./rolling-deploy.sh            # rolling-deploy the web tier (default)
#   ./rolling-deploy.sh web
#   ./rolling-deploy.sh backend    # single-container services: plain recreate
set -euo pipefail
cd "$(dirname "$0")"
SVC="${1:-web}"

# Serialize deploys. Two overlapping runs (e.g. backgrounded back-to-back)
# race on `docker compose up`/--scale and collide on container names, leaving
# the stack half-recreated. flock makes a second run abort cleanly.
exec 9>/tmp/freedium-deploy.lock
if ! flock -n 9; then
  echo "ERROR: another deploy is already running (holding /tmp/freedium-deploy.lock); aborting." >&2
  exit 1
fi

echo "==> building $SVC"
docker compose build "$SVC"

wait_healthy() {  # $1 = name filter, $2 = expected healthy count
  until [ "$(docker ps --filter "name=$1" --filter health=healthy -q | wc -l)" -ge "$2" ]; do
    sleep 2
  done
}

if [ "$SVC" = "web" ]; then
  total=$(docker ps --filter "name=freedium-obs-web" -q | wc -l)
  [ "$total" -ge 1 ] || total=3
  echo "==> rolling $total web replicas (one at a time)"
  for c in $(docker ps --filter "name=freedium-obs-web" -q); do
    name=$(docker inspect -f '{{.Name}}' "$c" | sed 's#^/##')
    echo "  -> replacing $name"
    docker stop "$c" >/dev/null   # graceful SIGTERM; Traefik drops it from rotation
    docker rm "$c" >/dev/null
    # Recreate ONLY the now-missing replica, with the freshly-built image.
    # --no-recreate leaves the still-serving replicas untouched (they keep the
    # old image until it's their turn), so >=1 replica is always healthy.
    docker compose up -d --no-deps --no-recreate --scale web="$total" web >/dev/null
    wait_healthy freedium-obs-web "$total"
    echo "     OK ($total/$total healthy)"
  done
else
  # Single-container services have no spare replica to roll through, so this
  # is a normal recreate (brief blip). Run 2+ replicas to make it zero-downtime.
  echo "==> recreating $SVC"
  docker compose up -d --no-deps --force-recreate "$SVC"

  # web holds keep-alive connections to backend by container IP. Recreating
  # backend gives it a NEW IP, leaving web replicas with dead connections
  # (FetchError "unable to connect" → 500s on the affected replica) until they
  # reconnect. Roll-restart web one at a time so they re-resolve.
  if [ "$SVC" = "backend" ]; then
    echo "==> rolling web to re-resolve backend"
    for c in $(docker ps --filter "name=freedium-obs-web" --format '{{.Names}}'); do
      docker restart -t 10 "$c" >/dev/null 2>&1
      until [ "$(docker inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null)" = "healthy" ]; do
        sleep 3
      done
      echo "     re-resolved $c"
    done
  fi
fi

# Reclaim space from the now-superseded image + this build's cache. Every
# deploy builds a fresh image; without this the dangling layers pile up and
# eventually fill the disk (which silently breaks Mongo/backend writes →
# articles stop rendering). image prune -f only removes untagged/dangling
# images, never anything a container references.
echo "==> pruning dangling images + build cache"
docker image prune -f >/dev/null 2>&1 || true
docker builder prune -f >/dev/null 2>&1 || true

echo "==> done"
