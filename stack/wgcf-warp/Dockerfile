# ---------------------------------------------------------------------------
# Stage 1: build microsocks from source as a STATIC binary (musl).
#
# microsocks (https://github.com/rofl0r/microsocks) is a ~50KB single-binary
# SOCKS5 server. We previously used dante-server here but it busy-looped at
# ~95% CPU and returned malformed SOCKS5 replies on this kernel/glibc combo.
#
# The runtime base (neilpang/wgcf-docker) is Ubuntu 20.04 (glibc 2.31). A
# dynamically-linked microsocks built on bookworm/trixie pulls in
# GLIBC_2.34+ symbols and won't run there. Building static against musl
# (Alpine) avoids the glibc-version coupling entirely.
# ---------------------------------------------------------------------------
FROM alpine:3.20 AS microsocks-builder

RUN apk add --no-cache git build-base musl-dev linux-headers

RUN git clone --depth=1 https://github.com/rofl0r/microsocks /src/microsocks \
    && cd /src/microsocks \
    && make CFLAGS="-O2 -static" LDFLAGS="-static" \
    && install -m 0755 microsocks /usr/local/bin/microsocks \
    && /usr/local/bin/microsocks -h 2>&1 | head -1 || true

# ---------------------------------------------------------------------------
# Stage 2: final image — wgcf base + microsocks binary.
# ---------------------------------------------------------------------------
FROM neilpang/wgcf-docker:latest

# Make sure no dante is lurking from prior layers; also install the small set
# of tools the entrypoint needs (ip, curl for healthcheck, etc.).
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get purge -y dante-server || true \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        net-tools \
        iproute2 \
        curl \
        ca-certificates \
        iptables \
    && DEBIAN_FRONTEND=noninteractive apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Pull in the statically-linked-ish microsocks binary from the builder stage.
COPY --from=microsocks-builder /usr/local/bin/microsocks /usr/local/bin/microsocks

# Combined entrypoint: bring up wgcf in the background (reuses the upstream
# script's logic), then run microsocks in the foreground.
COPY combined-entry.sh /combined-entry.sh
RUN chmod +x /combined-entry.sh

WORKDIR /wgcf

ENTRYPOINT ["/combined-entry.sh"]
