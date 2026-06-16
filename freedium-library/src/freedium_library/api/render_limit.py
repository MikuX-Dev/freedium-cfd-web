"""Concurrency cap for expensive article renders.

A burst of uncached-article traffic otherwise spawns unbounded parallel
renders (each = a WARP GraphQL fetch + CPU-heavy medium-parser pass),
saturating the 4-vCPU box → load >100 → 503s. This per-process semaphore
bounds simultaneous renders; excess work waits instead of thrashing.

Per-process by design: each uvicorn worker and the TaskIQ worker get their
own limiter. With RENDER_CONCURRENCY=3 and 4 uvicorn workers, inline renders
top out at ~12 — but in the backend the inline path is also bounded by
INLINE_BUDGET (slow renders offload to the TaskIQ worker), so contention
there just offloads sooner. In the worker the semaphore makes a dispatched
burst queue rather than run all at once.
"""
from __future__ import annotations

import asyncio

from freedium_library.api.config import RenderConfig

RENDER_CONCURRENCY = RenderConfig().CONCURRENCY

render_semaphore = asyncio.Semaphore(RENDER_CONCURRENCY)
