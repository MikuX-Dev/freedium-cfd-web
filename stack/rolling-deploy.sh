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

# web AND backend run as replicas behind Traefik → roll one at a time so a
# healthy backend always serves. Both have dynamic names freedium-obs-<svc>-N.
case "$SVC" in
  web|backend)
    filt="freedium-obs-$SVC"
    total=$(docker ps --filter "name=$filt" -q | wc -l)
    if [ "$total" -lt 1 ]; then
      # First cutover (e.g. backend migrating off a fixed container_name) or
      # nothing running yet: plain up to create the replicas, then done.
      echo "==> $SVC not yet replicated; creating replicas"
      docker compose up -d --no-deps "$SVC"
    else
      echo "==> rolling $total $SVC replicas (one at a time)"
      for c in $(docker ps --filter "name=$filt" -q); do
        name=$(docker inspect -f '{{.Name}}' "$c" | sed 's#^/##')
        echo "  -> replacing $name"
        docker stop "$c" >/dev/null   # graceful SIGTERM; Traefik health-drops it
        docker rm "$c" >/dev/null
        # Recreate ONLY the missing replica with the fresh image; --no-recreate
        # leaves the still-serving replicas untouched so >=1 is always healthy.
        docker compose up -d --no-deps --no-recreate --scale "$SVC=$total" "$SVC" >/dev/null
        wait_healthy "$filt" "$total"
        echo "     OK ($total/$total healthy)"
      done
    fi
    ;;
  *)
    # Truly single-container services (mongo, redis, …): plain recreate.
    echo "==> recreating $SVC"
    docker compose up -d --no-deps --force-recreate "$SVC"
    ;;
esac

# Reclaim space from the now-superseded image + this build's cache. Every
# deploy builds a fresh image; without this the dangling layers pile up and
# eventually fill the disk (which silently breaks Mongo/backend writes →
# articles stop rendering). image prune -f only removes untagged/dangling
# images, never anything a container references.
echo "==> pruning dangling images + build cache"
docker image prune -f >/dev/null 2>&1 || true
docker builder prune -f >/dev/null 2>&1 || true

echo "==> done"
