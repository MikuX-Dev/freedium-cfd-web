#!/usr/bin/env python3
"""Replay collected URLs through the render endpoint to warm the caches.

Reads a URL list (e.g. produced by fetch_medium_sitemap.py) and POSTs each to
the backend /render endpoint — the exact call the frontend makes — so the
result lands in L1 (post_cache) and L2 (rendered_cache). Cold renders are
dispatched to the TaskIQ worker (the endpoint returns a task_id); this script
polls /render/poll/{id} to completion, which is what gives it BACKPRESSURE:
only --concurrency renders are ever in flight, matched to WARP/worker capacity,
so it never floods the queue or the shared WARP exit IPs.

Resumable + gentle, like the crawler:
  * a done-file (one URL per line) is the source of truth; on restart already-
    warmed URLs are skipped — no double work.
  * --concurrency caps parallelism; each slot waits for its render to finish
    (poll-to-done) before taking the next URL.
  * graceful SIGINT/SIGTERM; done-file flushed continuously.

Usage (run inside the backend container — hits localhost:7080/api):
    python warm_render.py --in /var/log/freedium/medium-urls.txt \
        --done /var/log/freedium/warm-done.txt \
        --base http://localhost:7080/api --concurrency 4 \
        --filter '/[0-9a-f]{12}$'
"""
from __future__ import annotations

import argparse
import asyncio
import re
import signal
import sys
import time
import urllib.parse

import httpx

STOP = False


def _looks_renderable(url: str) -> bool:
    """Cheap pre-check: reject obviously-malformed URLs (empty @handle, no
    host, non-http) so we never spend a render on a guaranteed 404. Sitemaps
    contain junk like https://medium.com/@/slug-<id> (no username)."""
    if "/@/" in url:  # empty username
        return False
    try:
        u = urllib.parse.urlparse(url)
    except ValueError:
        return False
    return u.scheme in ("http", "https") and bool(u.netloc)


def _stop(signum, _frame):
    global STOP
    print(f"\n[signal] {signal.Signals(signum).name} — finishing in-flight, stopping", flush=True)
    STOP = True


async def warm_one(client: httpx.AsyncClient, base: str, url: str, poll_timeout: float) -> str:
    """Render one URL to completion. Returns an outcome tag."""
    if not _looks_renderable(url):
        return "skip:malformed"
    try:
        r = await client.post(f"{base}/render", json={"content": url, "frontmatter": True})
    except httpx.HTTPError as e:
        return f"neterr:{type(e).__name__}"
    if r.status_code == 422:
        return "unsupported"
    if r.status_code == 404:
        return "notfound"
    if r.status_code >= 400:
        return f"http{r.status_code}"
    try:
        data = r.json()
    except ValueError:
        return "badjson"
    task_id = data.get("task_id")
    if not task_id:  # synchronous render / cache hit
        return f"ok:{data.get('cache_status', 'sync')}"
    # cold render dispatched to the worker — poll to completion (backpressure)
    deadline = time.monotonic() + poll_timeout
    delay = 1.0
    while time.monotonic() < deadline and not STOP:
        await asyncio.sleep(delay)
        delay = min(delay * 1.5, 8.0)
        try:
            p = await client.get(f"{base}/render/poll/{task_id}")
        except httpx.HTTPError:
            continue
        try:
            status = p.json().get("status")
        except ValueError:
            continue  # poll returned non-JSON (e.g. transient error page) — retry
        if status == "done":
            return "ok:worker"
        if status == "error":
            return "rendererr"
    return "polltimeout"


async def worker(name, queue, client, base, done_f, lock, stats, poll_timeout):
    while not STOP:
        try:
            url = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        # Never let one URL's unexpected error kill the worker (which would
        # silently shrink in-flight concurrency to zero and stall the run).
        try:
            outcome = await warm_one(client, base, url, poll_timeout)
        except Exception as e:  # noqa: BLE001
            outcome = f"err:{type(e).__name__}"
        # Graceful backoff: a render error (rate-limit, WARP soft-block, dead
        # cluster) gets a short pause so we ease off instead of hammering.
        # Successes and cheap skips run at full speed.
        if not outcome.startswith(("ok", "skip", "unsupported", "notfound")):
            await asyncio.sleep(1.0)
        async with lock:
            done_f.write(url + "\n")
            done_f.flush()
            stats[outcome] = stats.get(outcome, 0) + 1
            stats["_total"] = stats.get("_total", 0) + 1
            if stats["_total"] % 50 == 0:
                ok = sum(v for k, v in stats.items() if k.startswith("ok"))
                print(f"[progress] {stats['_total']} done | ok {ok} | {dict(sorted(stats.items()))}", flush=True)


def load_lines(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]
    except FileNotFoundError:
        return []


async def main() -> int:
    ap = argparse.ArgumentParser(description="Warm caches by replaying URLs through /render.")
    ap.add_argument("--in", dest="inp", required=True, help="input URL list (one per line)")
    ap.add_argument("--done", required=True, help="done-file (resumable; one URL per line)")
    ap.add_argument("--base", default="http://localhost:7080/api", help="backend API base")
    ap.add_argument("--concurrency", type=int, default=4, help="parallel renders in flight")
    ap.add_argument("--filter", default=None, help="regex; only matching URLs are warmed")
    ap.add_argument("--limit", type=int, default=0, help="max URLs this run (0 = all)")
    ap.add_argument("--poll-timeout", type=float, default=180.0, help="max wait per cold render")
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    pat = re.compile(args.filter) if args.filter else None
    done = set(load_lines(args.done))
    urls = load_lines(args.inp)
    todo = [u for u in urls if u not in done and (not pat or pat.search(u))]
    if args.limit:
        todo = todo[: args.limit]
    print(
        f"[start] {len(urls)} in file | {len(done)} already done | "
        f"{len(todo)} to warm | concurrency {args.concurrency}",
        flush=True,
    )
    if not todo:
        print("[done] nothing to warm", flush=True)
        return 0

    queue: asyncio.Queue = asyncio.Queue()
    for u in todo:
        queue.put_nowait(u)

    stats: dict[str, int] = {}
    lock = asyncio.Lock()
    limits = httpx.Limits(max_connections=args.concurrency + 2)
    with open(args.done, "a", encoding="utf-8") as done_f:
        async with httpx.AsyncClient(timeout=args.poll_timeout + 30, limits=limits) as client:
            tasks = [
                asyncio.create_task(
                    worker(i, queue, client, args.base, done_f, lock, stats, args.poll_timeout)
                )
                for i in range(args.concurrency)
            ]
            await asyncio.gather(*tasks)

    print(f"[exit] {stats.get('_total', 0)} processed this run | {dict(sorted(stats.items()))}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
