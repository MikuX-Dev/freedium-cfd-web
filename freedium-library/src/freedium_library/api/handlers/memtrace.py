"""GET /internal/memtrace — per-worker tracemalloc leak diagnostics.

Each uvicorn worker is a separate process; this endpoint reports the
allocations of WHICHEVER worker handles the request (PID + RSS included so
you can tell them apart). First call on a worker stores a baseline snapshot;
subsequent calls return the diff (top growth since baseline), which points
straight at the leaking file:line.

Enable with TRACEMALLOC=1 (the lifespan starts tracemalloc). Secret-gated
with the same X-Internal-Secret as the PDF endpoint. Internal-only —
never exposed publicly via Traefik.

Usage:
  1. start backend with TRACEMALLOC=1
  2. curl -H "X-Internal-Secret: $S" .../internal/memtrace   (baseline per worker)
  3. drive traffic (warmer / replay)
  4. repeat the curl many times — the worker whose RSS grew shows the
     biggest deltas at the leak site.
"""
from __future__ import annotations

import os
import tracemalloc

from fastapi import APIRouter, Depends, Header, HTTPException

# Per-process baseline snapshot (one per worker).
_baseline: tracemalloc.Snapshot | None = None


def _rss_mb() -> float:
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 0.0


def register_memtrace_router(router: APIRouter, secret: str) -> None:
    def require_secret(x_internal_secret: str = Header(..., alias="X-Internal-Secret")) -> None:
        if x_internal_secret != secret:
            raise HTTPException(status_code=403, detail="Forbidden")

    async def memtrace(_: None = Depends(require_secret)):
        global _baseline
        if not tracemalloc.is_tracing():
            raise HTTPException(
                status_code=503,
                detail="tracemalloc not enabled (set TRACEMALLOC=1)",
            )
        snap = tracemalloc.take_snapshot()
        pid = os.getpid()
        rss = round(_rss_mb(), 1)

        if _baseline is None:
            _baseline = snap
            return {"pid": pid, "rss_mb": rss, "mode": "baseline_set", "top": []}

        stats = snap.compare_to(_baseline, "lineno")[:25]
        return {
            "pid": pid,
            "rss_mb": rss,
            "mode": "diff_vs_baseline",
            "top": [
                {
                    "where": str(s.traceback),
                    "size_diff_kb": round(s.size_diff / 1024, 1),
                    "count_diff": s.count_diff,
                    "size_kb": round(s.size / 1024, 1),
                }
                for s in stats
            ],
        }

    router.add_api_route(
        "/internal/memtrace", memtrace, methods=["GET"], include_in_schema=False
    )
