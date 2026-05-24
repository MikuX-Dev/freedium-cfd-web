"""TaskIQ broker + background tasks for Freedium.

The broker connects to Redis and dispatches async tasks to worker
processes. Tasks here are designed to be fire-and-forget from the
request handler — failures are logged but never propagate to the user.
"""
from taskiq_redis import ListQueueBroker, RedisScheduleSource
from taskiq import TaskiqScheduler
import os

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

broker = ListQueueBroker(url=REDIS_URL)

scheduler = TaskiqScheduler(
    broker=broker,
    sources=[RedisScheduleSource(REDIS_URL)],
)

# Import task submodules so they register with the broker on worker startup.
# This must come AFTER broker is defined (tasks reference it).
from freedium_library.tasks import cache as _cache  # noqa: E402, F401
from freedium_library.tasks import random_posts as _random_posts  # noqa: E402, F401
