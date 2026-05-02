"""Real Medium URLs to render on application startup.

Edit this file to control which articles pre-warm the home-page feed.
Each URL is rendered through the standard render pipeline at boot, so
the recorded entries contain *real* Medium metadata (title, author,
collection, reading time, publish date, etc.) — not handcrafted mock
data dressed up to look real.

Behavior:
- Renders run as a background asyncio.Task so startup is non-blocking.
- Failures (Medium unreachable, post deleted, network error) are
  logged and skipped — they don't block other URLs and don't crash
  the app. The feed is decorative, so degrading to empty is fine.
- As real users render articles, those records prepend to the deque
  and naturally push these warmup entries out as the buffer fills.

Leave the list empty in environments where Medium isn't reachable
(e.g. local dev without proxy). The frontend renders an honest empty
state in that case rather than showing mock content.
"""

from __future__ import annotations


# Curate this list with real, public Medium URLs. The renderer accepts
# any form the path validator handles: full URLs, /@user/slug paths,
# or bare post IDs.
SEED_URLS: list[str] = [
    # Examples (verify they're still public before relying on them in prod):
    # "https://medium.com/better-programming/the-best-developer-blog-post-ive-ever-read-2cb9b7e2d13c",
    # "https://medium.com/@matuzo/a-brief-history-of-css-until-2023-56b1d8d1c87f",
]
