#!/usr/bin/env bash
# Host-level health monitor → Telegram.
#
# Deliberately INDEPENDENT of the Docker stack: a full disk or OOM can crash
# Grafana/Prometheus, so Grafana-based alerting would be down exactly when you
# need it. This is a plain cron script that keeps alerting even if the whole
# stack is down.
#
# Install (on the host):
#   1. echo 'TELEGRAM_BOT_TOKEN=...' >  /opt/freedium/monitor.env   # host-only, NOT in git
#      echo 'TELEGRAM_CHAT_ID=...'   >> /opt/freedium/monitor.env
#      chmod 600 /opt/freedium/monitor.env
#   2. crontab -e  ->  */5 * * * * /opt/freedium/stack/monitor.sh >/dev/null 2>&1
set -uo pipefail

ENV_FILE="${MONITOR_ENV:-/opt/freedium/monitor.env}"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"
: "${TELEGRAM_BOT_TOKEN:?set in $ENV_FILE}"
: "${TELEGRAM_CHAT_ID:?set in $ENV_FILE}"

DISK_WARN=${DISK_WARN:-80}      # % used
MEM_WARN=${MEM_WARN:-92}        # % used
RENOTIFY=${RENOTIFY:-3600}      # re-alert at most once/hour while still in alarm
CRITICAL_CONTAINERS=${CRITICAL_CONTAINERS:-"freedium-backend freedium-mongo freedium-redis freedium-traefik"}

STATE_DIR=/var/lib/freedium-monitor
mkdir -p "$STATE_DIR"
HOST="Freedium"

tg() {
  curl -s --max-time 10 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=$1" -d "parse_mode=HTML" >/dev/null 2>&1 || true
}

# Throttled alert: (re)send at most once per RENOTIFY while the condition holds.
alert() {  # $1=key  $2=message
  local f="$STATE_DIR/$1" now; now=$(date +%s)
  if [ -f "$f" ] && [ $(( now - $(cat "$f" 2>/dev/null || echo 0) )) -lt "$RENOTIFY" ]; then
    return
  fi
  echo "$now" > "$f"
  tg "$2"
}
recover() {  # $1=key  — clears the alarm and pings once on recovery
  local f="$STATE_DIR/$1"
  if [ -f "$f" ]; then
    rm -f "$f"
    tg "✅ <b>$HOST</b> recovered: ${1}"
  fi
}

# --- disk ---
disk=$(df --output=pcent / 2>/dev/null | tail -1 | tr -dc '0-9'); disk=${disk:-0}
if [ "$disk" -ge "$DISK_WARN" ]; then
  alert disk "⚠️ <b>$HOST</b> disk <b>${disk}%</b> used (≥${DISK_WARN}%). Free space — a full disk silently breaks Mongo/backend writes (articles stop rendering)."
else
  recover disk
fi

# --- memory ---
mem=$(free 2>/dev/null | awk '/^Mem:/{printf "%d",$3/$2*100}'); mem=${mem:-0}
if [ "$mem" -ge "$MEM_WARN" ]; then
  alert mem "⚠️ <b>$HOST</b> memory <b>${mem}%</b> used (≥${MEM_WARN}%)."
else
  recover mem
fi

# --- critical single-container services ---
for c in $CRITICAL_CONTAINERS; do
  st=$(docker inspect -f '{{.State.Status}}{{if .State.Health}}/{{.State.Health.Status}}{{end}}' "$c" 2>/dev/null || echo "missing")
  case "$st" in
    running|running/healthy) recover "ct_$c" ;;
    *) alert "ct_$c" "🔴 <b>$HOST</b> <code>$c</code> is <b>$st</b>." ;;
  esac
done

# --- web tier (dynamic replica names): need >=1 healthy ---
web_ok=$(docker ps --filter name=freedium-obs-web --filter health=healthy -q 2>/dev/null | wc -l)
if [ "$web_ok" -lt 1 ]; then
  alert web "🔴 <b>$HOST</b> no healthy web replica."
else
  recover web
fi
