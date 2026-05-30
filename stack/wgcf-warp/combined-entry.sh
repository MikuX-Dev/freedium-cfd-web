#!/usr/bin/env bash
# Combined wgcf + dante entrypoint.
#
# The upstream neilpang/wgcf-docker entry.sh brings Cloudflare Warp up via
# wg-quick and then `sleep infinity`s. We start it in the background, wait
# for the `wgcf` wireguard interface to appear and start routing traffic
# through Cloudflare, then exec danted (SOCKS5) in the foreground so the
# container's main process is the proxy and `docker stop` is clean.

set -e

# 1) Launch upstream wgcf bootstrap in the background.
#    /entry.sh comes from neilpang/wgcf-docker and lives at the image root.
/entry.sh &
WGCF_PID=$!

# 2) Wait for the wgcf interface to be up AND for outbound traffic to be
#    going through Warp. Without this, danted will start before Warp is
#    ready and fail to bind to `external: wgcf`.
echo "[combined-entry] waiting for wgcf interface + Warp routing..."
for i in $(seq 1 120); do
    if ip link show wgcf >/dev/null 2>&1 \
       && curl -fs --max-time 3 https://www.cloudflare.com/cdn-cgi/trace 2>/dev/null \
            | grep -q -E 'warp=(on|plus)'; then
        echo "[combined-entry] Warp is up."
        break
    fi
    sleep 2
done

if ! ip link show wgcf >/dev/null 2>&1; then
    echo "[combined-entry] FATAL: wgcf interface never came up"
    exit 1
fi

# Even if the Warp trace check above timed out (some ISPs throttle WARP's
# data plane so the trace endpoint hangs), the wgcf interface exists and
# the handshake completed — danted can still bind to it. The compose
# healthcheck remains the source of truth for "fully healthy".

# 3) Exec danted in the foreground. -f points at our config; -D would
#    daemonise which we don't want under docker.
echo "[combined-entry] starting danted on :1080"
exec /usr/sbin/danted -f /etc/sockd.conf
