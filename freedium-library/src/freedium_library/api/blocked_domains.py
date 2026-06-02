"""Hardcoded denylist of sites that are definitely NOT paywalled articles.

Freedium unlocks article paywalls (Medium, etc.). Pasting a YouTube / social /
search / shopping link should be rejected immediately — rather than burning a
WARP fetch + GraphQL attempt and returning a confusing 404/500.

Matching is suffix-based, so a bare entry like "google.com" also blocks every
subdomain (mail.google.com, docs.google.com, …). Update this list by hand and
redeploy.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Bare registrable domains. Keep alphabetised within each group.
BLOCKED_DOMAINS: frozenset[str] = frozenset(
    {
        # video
        "youtube.com", "youtu.be", "vimeo.com", "twitch.tv", "dailymotion.com",
        # social
        "x.com", "twitter.com", "facebook.com", "fb.com", "fb.watch",
        "instagram.com", "tiktok.com", "threads.net", "reddit.com",
        "linkedin.com", "pinterest.com", "snapchat.com", "t.me", "telegram.org",
        "whatsapp.com",
        # search / portals
        "google.com", "bing.com", "duckduckgo.com", "yahoo.com", "yandex.com",
        # shopping
        "amazon.com", "ebay.com", "aliexpress.com", "etsy.com", "walmart.com",
        # dev / reference (not articles)
        "github.com", "gitlab.com", "stackoverflow.com", "wikipedia.org",
        "npmjs.com", "pypi.org",
        # streaming / apps
        "netflix.com", "spotify.com", "apple.com", "music.apple.com",
    }
)

# SvelteKit collapses the "//" in /https://… paths to "https:/…", so normalise
# a single-slash scheme back before parsing.
_COLLAPSED_SCHEME = re.compile(r"^(https?):/(?!/)", re.IGNORECASE)


def _host(url: str) -> str:
    s = _COLLAPSED_SCHEME.sub(r"\1://", url.strip())
    if "//" not in s:
        s = "https://" + s
    try:
        host = (urlparse(s).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def is_blocked_domain(content: str) -> bool:
    """True if `content` is a URL whose host is (a subdomain of) a denylisted
    domain. A bare Medium post id (no host) is never blocked."""
    host = _host(content)
    if not host or "." not in host:
        return False
    return any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)
