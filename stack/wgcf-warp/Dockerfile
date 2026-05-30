FROM neilpang/wgcf-docker:latest

# Install Dante SOCKS5 server + tools needed by the original entry.sh
# (net-tools for ifconfig/route, iproute2 for ip, curl for the healthcheck).
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        dante-server \
        net-tools \
        iproute2 \
        curl \
        ca-certificates \
        iptables \
    && rm -rf /var/lib/apt/lists/*

# Dante config — listen on 1080 inside the container, route via the wgcf
# wireguard interface that the original entry.sh brings up.
COPY sockd.conf /etc/sockd.conf

# Combined entrypoint: bring up wgcf in the background (reuses the upstream
# script's logic), then run danted in the foreground.
COPY combined-entry.sh /combined-entry.sh
RUN chmod +x /combined-entry.sh

WORKDIR /wgcf

ENTRYPOINT ["/combined-entry.sh"]
